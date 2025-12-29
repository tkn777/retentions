#
# retentions
#
# A small, feature-rich cross-platform CLI tool to apply backup-like retention rules to any file set.
#
# Copyright (c) 2025-2026 Thomas Kuhlmann
#
# Licensed under the MIT License. See LICENSE file in the project root for license information.
#
# https://github.com/tkn777/retentions
#

import argparse
import re
import sys
import traceback
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from fnmatch import fnmatch
from os import stat_result
from pathlib import Path
from types import SimpleNamespace
from typing import NoReturn, Optional, TextIO, no_type_check


VERSION: str = "dev-1.0.0"

SCRIPT_START = datetime.now().timestamp()

LOCK_FILE_NAME: str = ".retentions.lock"


class ConcurrencyError(Exception):
    pass


class IntegrityCheckFailedError(Exception):
    pass


class NoFilesFoundError(Exception):
    pass


class ConfigNamespace(SimpleNamespace):
    pass


class FileStatsCache:
    age_type: str
    _file_stats_cache: dict[Path, stat_result]

    def __init__(self, age_type: str) -> None:
        self.age_type = age_type
        self._file_stats_cache: dict[Path, stat_result] = {}

    def get_file_seconds(self, file: Path) -> float:
        return int(getattr(self._file_stats_cache.setdefault(file, file.stat()), f"st_{self.age_type}"))

    def get_file_bytes(self, file: Path) -> int:
        return self._file_stats_cache.setdefault(file, file.stat()).st_size


def sort_files(files: Iterable[Path], file_stats_cache: FileStatsCache) -> list[Path]:
    return sorted(files, key=file_stats_cache.get_file_seconds, reverse=True)


class LogLevel(IntEnum):
    ERROR = 0
    WARN = 1
    INFO = 2
    DEBUG = 3

    @classmethod
    def from_name_or_number(cls, prefix: str) -> "LogLevel":
        try:
            return next(m for m in cls if m.name.startswith(prefix.upper()))
        except StopIteration:
            try:
                return cls(int(prefix))
            except ValueError:
                raise ValueError("Invalid log level: " + prefix)


class Logger:
    _decisions: dict[Path, list[tuple[str, Optional[str]]]] = defaultdict(list)
    _args: ConfigNamespace
    _file_stats_cache: FileStatsCache

    def __init__(self, args: ConfigNamespace, file_stats_cache: FileStatsCache) -> None:
        self._args = args
        self._file_stats_cache = file_stats_cache

    def _get_file_attributes(self, file: Path, args: ConfigNamespace, file_stats_cache: FileStatsCache) -> str:
        return f"{args.age_type}: {datetime.fromtimestamp(file_stats_cache.get_file_seconds(file))}, size: {ModernStrictArgumentParser.format_size(file_stats_cache.get_file_bytes(file))}"

    def has_log_level(self, level: LogLevel) -> bool:
        return level <= int(self._args._logger.verbose)

    def _raw_verbose(self, level: LogLevel, message: str, file: TextIO = sys.stderr, prefix: str = "") -> None:
        print(f"[{prefix or LogLevel(level).name}] {message}", file=file)

    def verbose(self, level: LogLevel, message: str, file: TextIO = sys.stderr, prefix: str = "") -> None:
        if self.has_log_level(level):
            self._raw_verbose(level, message, file, prefix)

    def add_decision(self, level: LogLevel, file: Path, message: str, debug: Optional[str] = None, pos: int = 0) -> None:
        if self.has_log_level(level):
            if level >= LogLevel.DEBUG:  # Decision history and debug message and file details only with debug log level
                self._decisions[file].insert(pos, ((message, f"({(debug + ', ') if debug is not None else ''}, {self._get_file_attributes(file, self._args, self._file_stats_cache)})")))
            else:  # Without debug log level no decision history
                if self._decisions[file]:
                    self._decisions[file][0] = (message, None)
                else:
                    self._decisions[file].insert(0, (message, None))

    def _format_decision(self, decision: tuple[str, Optional[str]]) -> str:
        message, debug = decision
        return message + (f" ({debug})" if debug is not None else "")

    def print_decisions(self) -> None:
        longest_file_name_length = max(len(p.name) for p in self._decisions)
        for file in sort_files(self._decisions, self._file_stats_cache):
            decisions = self._decisions[file]
            if not decisions:
                continue
            self._raw_verbose(LogLevel.INFO, f"{file.name:<{longest_file_name_length}}: {self._format_decision(decisions[0])}")
            if not self.has_log_level(LogLevel.DEBUG):
                continue
            for idx, decision in enumerate(decisions[1:]):
                self._raw_verbose(LogLevel.DEBUG, f"{' ' * ((longest_file_name_length + 2) + idx * 4)}└── {self._format_decision(decision)}")


class ModernHelpFormatter(argparse.HelpFormatter):
    @no_type_check
    def __init__(self, *a, **kw) -> None:  # noqa: ANN002, ANN003
        super().__init__(*a, max_help_position=30, width=160, **kw)

    @no_type_check
    def start_section(self, heading) -> None:  # noqa: ANN001
        super().start_section(heading.capitalize())


class ModernStrictArgumentParser(argparse.ArgumentParser):
    @no_type_check
    def __init__(self, *a, **kw) -> None:  # noqa: ANN002, ANN003
        super().__init__(*a, **kw)
        self._errors: list[str] = []

    def add_error(self, msg: str) -> None:
        if msg not in self._errors:
            self._errors.append(msg)

    def error(self, message: str) -> NoReturn:
        self.print_usage()
        print("\nError(s):")
        for line in message.split("\n"):
            print(f"  • {line}")
        print("\nHint: Try '--help' for more information (or 'man retentions').")
        sys.exit(2)

    # Argument type helpers
    def positive_int_argument(self, value: str) -> int:
        try:
            int_value = int(value)
            if int_value <= 0:
                raise ValueError
        except ValueError:
            raise argparse.ArgumentTypeError(f"Invalid value '{value}': must be an integer > 0")
        return int_value

    def verbose_argument(self, value: str) -> LogLevel:
        try:
            return LogLevel.from_name_or_number(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"Invalid verbose value '{value}' (use ERROR, WARN, INFO, DEBUG or 0, 1, 2, 3)")

    def parse_positive_size_argument(self, size_str: str) -> float:
        size_str = size_str.strip().upper()
        re_match = re.match(r"^([0-9]+(?:\.[0-9]*)?)\s*([KMGTPE]?)$", size_str)
        if not re_match:
            raise argparse.ArgumentTypeError(f"Invalid size format: '{size_str}'")
        multipliers = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5, "E": 1024**6}
        return int(float(re_match.group(1)) * multipliers[re_match.group(2)])

    def parse_positive_time_argument(self, time_str: str) -> float:
        time_str = time_str.strip(" ")
        m = re.fullmatch(r"([0-9]+(?:\.[0-9]*)?)(?: ?([hdwmyq]))?", time_str)
        if not m:
            raise argparse.ArgumentTypeError(f"Invalid time format: '{time_str}'")
        multipliers = {"": 1, "h": 60 * 60, "d": 24 * 60 * 60, "w": 7 * 24 * 60 * 60, "m": 30 * 24 * 60 * 60, "q": 90 * 24 * 60 * 60, "y": 365 * 24 * 60 * 60}
        result = float(m.group(1)) * multipliers[m.group(2) or ""]
        if result < 1:  # Must be >= 1 s
            raise argparse.ArgumentTypeError(f"Time value must be >= 1 s: '{time_str}'")
        return result

    @staticmethod
    def format_size(bytes: int) -> str:
        units = ["", "K", "M", "G", "T", "E", "P"]
        idx, value = 0, float(bytes)
        while value >= 1024 and idx < len(units) - 1:
            value /= 1024
            idx += 1
        return f"{value:.2f}".rstrip("0").rstrip(".") + units[idx]

    @staticmethod
    def format_time(seconds: int) -> str:
        units = [("y", 365 * 24 * 60 * 60), ("q", 90 * 24 * 60 * 60), ("m", 30 * 24 * 60 * 60), ("w", 7 * 24 * 60 * 60), ("d", 24 * 60 * 60), ("h", 60 * 60), ("", 1)]
        value, suffix = float(seconds), ""
        for s, v in units:
            if seconds >= v:
                value = seconds / v
                suffix = s
                break
        return f"{value:.2f}".rstrip("0").rstrip(".") + suffix

    # Internal helper methods
    def _suggest(self, argument: str) -> list[str]:
        opts = [o for a in self._actions for o in a.option_strings if o.startswith("--")]
        cand = [o for o in opts if abs(len(o) - len(argument)) <= 2 and sum(a != b for a, b in zip(o, argument)) <= 2]
        return cand[:1]

    @no_type_check
    def _collect_raw_args(self, args):  # noqa: ANN202, ANN001
        if args is not None:
            return list(args)
        return sys.argv[1:]  # default argparse behavior

    @no_type_check
    def _detect_duplicate_flags(self, raw_args) -> None:  # noqa: ANN001
        # Normalize option strings
        alias = {opt: action.option_strings[0] for action in self._actions for opt in action.option_strings}
        seen = set()

        for tok in raw_args:
            if not tok.startswith("-"):
                continue

            # Extract option (handles -w3, -w=3, --x=5)
            opt = tok.split("=", 1)[0]

            # Handle -w3 → -w
            if len(opt) > 2 and opt.startswith("-") and not opt.startswith("--"):
                opt = opt[:2]

            key = alias.get(opt, opt)

            if key in seen:
                self.add_error(f"Duplicate flag: {key}")
            seen.add(key)

    def _compile_regex(self, regex: str, regex_mode: str) -> Optional[re.Pattern[str]]:
        try:
            return re.compile(regex, re.UNICODE | (re.IGNORECASE if regex_mode == "ignorecase" else 0))
        except re.error:
            self.add_error(f"Invalid regular expression : {regex}")
            return None

    @no_type_check
    def _validate_arguments(self, ns) -> None:  # noqa: ANN001
        # Default verbosity, if none given
        if ns.verbose is None:
            ns.verbose = LogLevel.INFO if not ns.list_only else LogLevel.ERROR

        # dry-run implies verbose
        if ns.dry_run and not ns.list_only and not ns.verbose:
            ns.verbose = LogLevel.INFO

        # normalize 0-byte separator
        if ns.list_only == "\\0":
            ns.list_only = "\0"

        # incompatible options (list-only and verbose > ERROR)
        if ns.list_only and ns.verbose > LogLevel.ERROR:
            self.add_error("--list-only and --verbose (> ERROR) cannot be used together")

        # regex validation (and compilation), also for protect
        if ns.regex_mode is not None:
            ns.regex_compiled = self._compile_regex(ns.file_pattern, ns.regex_mode)
            if ns.protect is not None:
                ns.protect_compiled = self._compile_regex(ns.protect, ns.regex_mode)

        # max-size parsing
        if ns.max_size is not None:
            ns.max_size = "".join(token.strip() for token in ns.max_size)
            ns.max_size_bytes = self.parse_positive_size_argument(ns.max_size)

        # max-age parsing
        if ns.max_age is not None:
            ns.max_age = "".join(token.strip() for token in ns.max_age)
            ns.max_age_seconds = self.parse_positive_time_argument(ns.max_age)

    # Main hook
    @no_type_check
    def parse_known_args(self, args=None, namespace=None) -> tuple[argparse.Namespace, list[str]]:  # noqa: ANN001
        self._errors = []
        raw_args = self._collect_raw_args(args)
        self._detect_duplicate_flags(raw_args)

        ns, unknown = super().parse_known_args(raw_args, namespace or argparse.Namespace())

        if unknown:
            sug = self._suggest(unknown[0])
            if sug:
                self.add_error(f"Unknown option: {unknown[0]} (did you mean {sug[0]}?)")
            else:
                self.add_error(f"Unknown option: {unknown[0]}")

        self._validate_arguments(ns)

        if self._errors:
            msg = "\n".join(f"{e}" for e in self._errors)
            self.error(msg)

        return ns, unknown


def create_parser() -> ModernStrictArgumentParser:
    parser: ModernStrictArgumentParser = ModernStrictArgumentParser(
        description=f"retentions {VERSION}\n\nA small feature-rich cross-platform CLI tool for file retention management",
        usage=("retentions path file_pattern [options]\n\nExample:\n  retentions /data/backups '*.tar.gz' -d 7 -w 4 -m 6 -a 12m"),
        epilog="Use with caution!! This tool deletes files unless --dry-run or --list-only is set.",
        formatter_class=ModernHelpFormatter,
        add_help=False,
    )

    g_main = parser.add_argument_group("Main arguments")
    g_flags = parser.add_argument_group("Flags")
    g_ret = parser.add_argument_group("Retention arguments")
    g_filter = parser.add_argument_group("Filter arguments")
    g_behavior = parser.add_argument_group("Behavior arguments")
    g_common = parser.add_argument_group("Common arguments")

    # positional arguments
    g_main.add_argument("path", help="Base directory to scan (recursion is not supported)")
    g_main.add_argument("file_pattern", help="glob pattern for matching files (use quotes to prevent shell expansion)")

    # argument flags
    # fmt: off
    g_flags.add_argument("--regex-mode", "-r", type=str, choices=["casesensitive", "ignorecase"], metavar="mode", const="casesensitive", nargs="?", default=None,
        help="file_pattern is a regex (default: glob pattern) - mode: casesensitive, ignorecase, default: casesensitive")
    g_flags.add_argument("--age-type", type=str, choices=["ctime", "mtime", "atime"], metavar="time", default="mtime", help="Used time attribute for file age (default: mtime)")
    g_flags.add_argument("--protect", "-p", type=str, default=None, help="Protect files from deletion (using regex or glob, like file_pattern)")
    # fmt: on

    # optional retention arguments (validated, no defaults)
    g_ret.add_argument("--hours", "-h", type=parser.positive_int_argument, metavar="N", help="Keep one file per hour from the last N hours")
    g_ret.add_argument("--days", "-d", type=parser.positive_int_argument, metavar="N", help="Keep one file per day from the last N days")
    g_ret.add_argument("--weeks", "-w", type=parser.positive_int_argument, metavar="N", help="Keep one file per week from the last N weeks")
    g_ret.add_argument("--months", "-m", type=parser.positive_int_argument, metavar="N", help="Keep one file per month from the last N months")
    g_ret.add_argument("--quarters", "-q", type=parser.positive_int_argument, metavar="N", help="Keep one file per quarter from the last N quarters (quarter by months)")
    g_ret.add_argument("--week13", type=parser.positive_int_argument, metavar="N", help="Keep one file per 13-week block from the last N 13-week blocks (quarter by weeks)")
    g_ret.add_argument("--years", "-y", type=parser.positive_int_argument, metavar="N", help="Keep one file per year from the last N years")
    g_ret.add_argument("--last", "-l", type=parser.positive_int_argument, metavar="N", help="Always keep the N most recently modified files")

    # filter arguments
    g_filter.add_argument("--max-size", "-s", type=str, nargs="+", metavar="N", help="Keep maximum within total size N (e.g. 12, 10.5M, 500G, 3E)")
    g_filter.add_argument("--max-files", "-f", type=parser.positive_int_argument, metavar="N", help="Keep maximum total files N")
    g_filter.add_argument("--max-age", "-a", type=str, nargs="+", metavar="N", help="Keep maximum within time span N from script start (e.g. 3600, 1h, 1d, 1w, 1m, 1q, 1y - with 1 month = 30 days)")

    # behavior flags
    # fmt: off
    g_behavior.add_argument("--list-only", "-L", nargs="?", const="\n", default=None, metavar="sep",
        help="Output only file paths that would be deleted (incompatible with --verbose) (optional separator (sep): e.g. '\\0')")
    g_behavior.add_argument("--verbose", "-V", "-v", type=parser.verbose_argument, default=None, nargs="?", const=LogLevel.INFO, metavar="lev",
        help="Verbosity level: 0 = error, 1 = warn, 2 = info, 3 = debug (default: 'info', if specified without value; 'error' otherwise; use numbers or names)")
    # fmt: on
    g_behavior.add_argument("--dry-run", "-X", action="store_true", help="Show planned actions but do not delete any files")
    g_behavior.add_argument("--no-lock-file", action="store_false", dest="use_lock_file", default=True, help="Omit lock file (default: enabled)")

    # common flags
    g_common.add_argument("--version", "-R", action="version", version=f"%(prog)s {VERSION}")
    g_common.add_argument("--help", "-H", action="help", help="Show this help message and exit")
    g_common.add_argument("--stacktrace", action="store_true", help=argparse.SUPPRESS)

    return parser


def parse_arguments() -> ConfigNamespace:
    parser = create_parser()
    args = parser.parse_args()
    return ConfigNamespace(**vars(args))


def read_filelist(args: ConfigNamespace, logger: Logger, file_stats_cache: FileStatsCache) -> list[Path]:
    base: Path = Path(args.path)
    if not base.exists():
        raise FileNotFoundError(f"Path not found: {base}")
    if not base.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {base}")

    matches: list[Path] = []
    if args.regex_mode:
        matches = [file for file in base.iterdir() if file.is_file() and (args.regex_compiled.match(file.name))]
    else:
        matches = [file for file in base.glob(args.file_pattern) if file.is_file()]

    if not matches:
        raise NoFilesFoundError(f"No files found in '{base}' using " + f"{'regex (' + args.regex_mode + ')' if args.regex_mode else 'glob'} " + f"pattern '{args.file_pattern}'")

    # Check, if child of base directory
    for file in matches:
        if not Path(file).parent.resolve() == base.resolve():
            raise ValueError(f"File '{file}' is not a child of base directory '{base}'")

    # Check for protection
    if args.protect:
        protected: set[Path] = set()
        for file in matches:
            if args.regex_mode and args.protect_compiled.match(file.name):
                logger.add_decision(LogLevel.INFO, file, f"Protected by regex: '{args.protect}'")
                protected.add(file)
            elif fnmatch(file.name, args.protect):
                logger.add_decision(LogLevel.INFO, file, f"Protected by glob: '{args.protect}'")
                protected.add(file)
        matches = [file for file in matches if file not in protected]

    # Ignore lock file (in any case, even if it is is disabled by user)
    matches = [m for m in matches if m.name != LOCK_FILE_NAME]

    # sort by time (youngest first)
    return sort_files(matches, file_stats_cache)


@dataclass
class RetentionsResult:
    keep: set[Path]
    prune: set[Path]
    decisions_log: Logger


class RetentionLogic:
    _matches: list[Path]
    _keep: set[Path]
    _prune: set[Path]
    _args: ConfigNamespace
    _logger: Logger
    _file_stats_cache: FileStatsCache

    def __init__(self, matches: list[Path], args: ConfigNamespace, logger: Logger, file_stats_cache: FileStatsCache) -> None:
        self._matches = matches
        self._keep = set()
        self._prune = set()
        self._args = args
        self._logger = logger
        self._file_stats_cache = file_stats_cache

    def _create_retention_buckets(self, retention_mode: str) -> dict[str, list[Path]]:
        buckets: dict[str, list[Path]] = defaultdict(list)
        for file in self._matches:
            timestamp = datetime.fromtimestamp(self._file_stats_cache.get_file_seconds(file))
            if retention_mode == "hours":
                key = timestamp.strftime("%Y-%m-%d-%H")
            elif retention_mode == "days":
                key = timestamp.strftime("%Y-%m-%d")
            elif retention_mode == "weeks":
                year, week, _ = timestamp.isocalendar()
                key = f"{year}-W{week:02d}"
            elif retention_mode == "months":
                key = timestamp.strftime("%Y-%m")
            elif retention_mode == "quarters":
                key = f"{timestamp.year}-Q{((timestamp.month - 1) // 3) + 1}"
            elif retention_mode == "week13":
                year, week, _ = timestamp.isocalendar()
                key = f"{year}-week13-{(week - 1) // 13 + 1}"
            elif retention_mode == "years":
                key = str(timestamp.year)
            else:
                raise ValueError(f"invalid bucket mode: {retention_mode}")
            buckets[key].append(file)  # add file to appropriate bucket by the computed key generated from the timestamp of the file
        if self._logger.has_log_level(LogLevel.DEBUG):
            for key, files in buckets.items():
                self._logger.verbose(LogLevel.DEBUG, f"Retention buckets: {key} - {', '.join(f'{file.name} ({datetime.fromtimestamp(self._file_stats_cache.get_file_seconds(file))})' for file in files)}")
        return buckets

    def _process_retention_buckets(self, retention_mode: str, retention_mode_count: int, buckets: dict[str, list[Path]]) -> None:
        sorted_keys = sorted(buckets.keys(), reverse=True)  # newest bucket-key first => e.g. "2025-01" before "2023-11" for 'months' retention mode
        effective_count = retention_mode_count
        current_count = 0
        while current_count < effective_count:
            if current_count >= len(sorted_keys):
                break  # No more buckets
            first_bucket_file = buckets[sorted_keys[current_count]][0]
            if first_bucket_file in self._keep:  # Already kept by one previous retention mode
                self._logger.add_decision(LogLevel.DEBUG, first_bucket_file, f"Skipping for mode '{retention_mode}' as already kept by one previous retention mode", pos=1)
                effective_count += 1
            else:
                # Keep first entry (file) of bucket, prune the rest
                self._logger.add_decision(
                    LogLevel.INFO, first_bucket_file, f"Keeping for mode '{retention_mode}' {(current_count - (effective_count - retention_mode_count) + 1):02d}/{retention_mode_count:02d}", debug=f"key: {sorted_keys[current_count]}"
                )
                self._keep.add(first_bucket_file)
                for file_prune in buckets[sorted_keys[current_count]][1:]:
                    self._logger.add_decision(LogLevel.INFO, file_prune, f"Pruning for mode '{retention_mode}'", debug=f"key: {sorted_keys[current_count]}")
                    self._prune.add(file_prune)
            current_count += 1

    def _process_last_n(self) -> None:
        last_files = self._matches[: self._args.last]  # Get the N most recently modified files regardless from any retention rule (newest first)
        if self._logger.has_log_level(LogLevel.INFO):
            for index, file in enumerate(last_files, start=1):
                if file not in self._keep:  # Retention rules may have already kept this file, their message takes precedence
                    self._logger.add_decision(LogLevel.INFO, file, f"Keeping last {index:02d}/{self._args.last:02d}")
        self._keep.update(last_files)
        self._prune.difference_update(last_files)  # ensure last N files are not pruned

    def _filter_file(self, file: Path, message: str) -> None:
        self._keep.remove(file)
        self._prune.add(file)
        self._logger.add_decision(LogLevel.INFO, file, message)

    def _filter_files(self) -> None:
        # max-files
        if self._args.max_files is not None and self._keep:
            sorted_keep = sort_files(self._keep, self._file_stats_cache)  # Must be sorted by xtime before applying filters, because set is unfiltered
            for idx, file in enumerate(sorted_keep[self._args.max_files :], start=self._args.max_files + 1):
                self._filter_file(file, f"Filtering: max total files exceeded: {idx:02d} > {self._args.max_files:02d}")

        # max-size
        if self._args.max_size is not None and self._keep:
            sorted_keep = sort_files(self._keep, self._file_stats_cache)  # Must be sorted by xtime before applying filters, because set is unfiltered
            bytes_sum: int = 0
            for file in sorted_keep:
                bytes_sum += self._file_stats_cache.get_file_bytes(file)
                if bytes_sum > self._args.max_size_bytes:
                    self._filter_file(file, f"Filtering: max total size exceeded: {ModernStrictArgumentParser.format_size(bytes_sum)} > {self._args.max_size}")

        # max-age
        if self._args.max_age is not None and self._keep:
            sorted_keep = sort_files(self._keep, self._file_stats_cache)  # Must be sorted by xtime before applying filters, because set is unfiltered
            threshold = SCRIPT_START - self._args.max_age_seconds
            for file in sorted_keep:
                file_time = self._file_stats_cache.get_file_seconds(file)
                if file_time < threshold:
                    self._filter_file(file, f"Filtering: max total age exceeded: {ModernStrictArgumentParser.format_time(int(SCRIPT_START - file_time))} > {self._args.max_age}")

    def process_retention_logic(self) -> RetentionsResult:
        # Retention by time buckets; generation and processing must be done per retention mode sequently in one single loop
        retention_rules_applied = False
        for retention_mode in ["hours", "days", "weeks", "months", "quarters", "week13", "years"]:
            retention_mode_count = getattr(self._args, retention_mode)
            if retention_mode_count:
                retention_rules_applied = True
                buckets = self._create_retention_buckets(retention_mode)
                self._process_retention_buckets(retention_mode, retention_mode_count, buckets)

        # Keep last N files (additional to time-based retention)
        if self._args.last:
            retention_rules_applied = True
            self._process_last_n()

        # If no retention rules specified, keep all files (before applying possible filtering)
        if retention_rules_applied:
            # verbose files to prune but not kept by any retention rule
            for file in [f for f in self._matches if f not in self._keep | self._prune]:
                self._logger.add_decision(LogLevel.INFO, file, "Pruning: not matched by any retention rule")
                self._prune.add(file)
        else:
            self._logger.verbose(LogLevel.DEBUG, "No retention rules specified, keeping all files")
            self._keep.update(self._matches)
            for file in self._matches:
                self._logger.add_decision(LogLevel.INFO, file, "Keeping: no retention rules specified")

        # Filter keep's
        self._filter_files()

        # Simple integrity checks
        if not len(self._matches) == len(self._keep) + len(self._prune):
            raise IntegrityCheckFailedError(f"File count mismatch: some files are neither kept nor prune (all: {len(self._matches)}, keep: {len(self._keep)}, prune: {len(self._prune)}!!")
        if not len(self._prune) == sum(1 for file in self._matches if is_file_to_delete(self._keep, self._prune, file)):
            raise IntegrityCheckFailedError("File deletion count mismatch!!")

        return RetentionsResult(self._keep, self._prune, self._logger)


def is_file_to_delete(keep: set[Path], prune: set[Path], file: Path) -> bool:
    return file not in keep and file in prune


def run_deletion(file: Path, args: ConfigNamespace, logger: Logger, file_stats_cache: FileStatsCache) -> None:
    time = datetime.fromtimestamp(file_stats_cache.get_file_seconds(file))
    if args.list_only:
        print(file.absolute(), end=args.list_only)  # List mode
    else:
        if args.dry_run:
            logger.verbose(LogLevel.INFO, f"DRY-RUN DELETE: {file.name} ({file_stats_cache.age_type}: {time})")  # Just simulate deletion
        else:
            logger.verbose(LogLevel.INFO, f"DELETING: {file.name} ({file_stats_cache.age_type}: {time})")
            try:
                file.unlink()
            except OSError as e:  # Catch deletion error, print it, and continue
                logger.verbose(LogLevel.WARN, f"Error while deleting file '{file.name}': {e}", file=sys.stderr)


def handle_exception(exception: Exception, exit_code: int, stacktrace: bool, prefix: str = "") -> None:
    if stacktrace:
        traceback.print_exc()
    print(f"[{prefix or LogLevel.ERROR.name}] {exception}", file=sys.stderr)
    sys.exit(exit_code)


def main() -> None:
    args: Optional[ConfigNamespace] = None
    lock_file: Optional[Path] = None
    created_lock_file = False

    try:
        args = parse_arguments()

        file_stats_cache = FileStatsCache(args.age_type)
        logger = Logger(args, file_stats_cache)

        logger.verbose(LogLevel.DEBUG, f"Parsed arguments: {args}")

        if args.use_lock_file:
            lock_file = Path(args.path + f"/{LOCK_FILE_NAME}")
            if lock_file.exists():
                raise ConcurrencyError(f"A retention process is already running on {args.path} (or there is a stale lockfile)")
            lock_file.touch()
            created_lock_file = True

        matches = read_filelist(args, logger, file_stats_cache)
        logger.verbose(LogLevel.INFO, f"Found {len(matches)} files using " + f"{'regex (' + args.regex_mode + ')' if args.regex_mode else 'glob'} " + f"pattern '{args.file_pattern}'")
        logger.verbose(LogLevel.DEBUG, "Files found: " + ", ".join(f'"{p.name}"' for p in matches))

        retentions_result = RetentionLogic(matches, args, logger, file_stats_cache).process_retention_logic()

        logger.print_decisions()

        logger.verbose(LogLevel.INFO, f"Total files found: {len(matches):03d}")
        logger.verbose(LogLevel.INFO, f"Total files keep:  {len(retentions_result.keep):03d}")
        logger.verbose(LogLevel.INFO, f"Total files prune: {len(retentions_result.prune):03d}")

        for file in matches:
            if is_file_to_delete(retentions_result.keep, retentions_result.prune, file):
                run_deletion(file, args, logger, file_stats_cache)

    except OSError as e:
        handle_exception(e, 1, args.stacktrace if args is not None else True)
    except ValueError as e:
        handle_exception(e, 2, args.stacktrace if args is not None else True)
    except NoFilesFoundError as e:
        handle_exception(e, 3, args.stacktrace if args is not None else True)
    except ConcurrencyError as e:
        handle_exception(e, 5, args.stacktrace if args is not None else True)
    except IntegrityCheckFailedError as e:
        handle_exception(e, 7, args.stacktrace if args is not None else True)
    except Exception as e:
        handle_exception(e, 9, args.stacktrace if args is not None else True, prefix="UNEXPECTED ERROR")
    finally:
        if created_lock_file and lock_file is not None:
            lock_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
