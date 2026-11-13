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
import os
import re
import shlex
import shutil
import sys
import traceback
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from fnmatch import fnmatch
from functools import lru_cache
from os import stat_result
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Generic, NoReturn, Optional, TextIO, TypeVar, no_type_check


VERSION: str = "dev-1.3.x"

SCRIPT_START = int(datetime.now().timestamp())

LOCK_FILE_NAME: str = ".retentions.lock"

MAX_FILE_SIZE = sys.maxsize


class ConcurrencyError(Exception):
    pass


class IntegrityCheckFailedError(Exception):
    pass


class FileCouldNotBeDeleteError(OSError):
    pass


class ConfigNamespace(SimpleNamespace):
    pass


def split_escaped(delim: str, text: str, type: str, value: str, expected_length: Optional[int] = None) -> list[str]:
    if not text:
        raise ValueError(f"Invalid {type} definition: {value} - Missing value")
    pattern = rf"(?<!\\){re.escape(delim)}"
    parts = [p.replace(f"\\{delim}", delim) for p in re.split(pattern, text)]
    if expected_length is not None and expected_length > 0 and len(parts) != expected_length:
        raise ValueError(f"Invalid {type} definition: {value} - Expect {expected_length} values, got {len(parts)} values by splitting on '{delim}'")
    return parts


T = TypeVar("T")


class Cache(Generic[T]):
    def __init__(self) -> None:
        self._cache: dict[Path, T] = {}

    def compute_if_absent(self, key: Path, factory: Callable[[Path], T]) -> T:
        if key not in self._cache:
            self._cache[key] = factory(key)
        return self._cache[key]


class FileStats:
    _folder_mode: bool
    _folder_mode_time_src: Optional[str]
    _age_type: str
    __file_stats_cache: Cache[stat_result]
    __file_seconds_cache: Cache[Optional[int]]

    def __init__(self, age_type: str, folder_mode: bool = False, folder_mode_time_src: Optional[str] = None, filename_format: Optional[str] = None) -> None:
        self._age_type = age_type
        self._folder_mode = folder_mode
        self._folder_mode_time_src = folder_mode_time_src
        self.__file_stats_cache: Cache[stat_result] = Cache()
        self.__file_seconds_cache: Cache[Optional[int]] = Cache()
        self._filename_extractor = self.make_cached_extractor(filename_format or "")
        self.logger: Optional[Logger] = None

    def make_cached_extractor(self, date_format: str) -> Callable[[str], Optional[int]]:
        edge = {f"%{code}": r"[ \d]" for code in "dmHIMSfjUWVwu"}
        edge.update({"%Y": r"\d{4}", "%G": r"\d{4}"})
        edge.update({"%y": r"\d{2}", "%w": r"\d", "%u": r"\d"})
        tokens = re.findall(r"%.|.", date_format, re.S) or [""]
        starts = re.compile(f"(?={edge.get(tokens[0], '')})")
        stops = re.compile(f"(?<={edge.get(tokens[-1], '')})")

        @lru_cache(maxsize=32)
        def positions(shape: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
            # Never split a contiguous run of digits.
            boundaries = [i for i in range(len(shape) + 1) if not (0 < i < len(shape) and shape[i - 1] == shape[i] == "0")]
            return (
                tuple(i for i in boundaries if starts.match(shape, i)),
                tuple(i for i in reversed(boundaries) if stops.match(shape, i)),
            )

        def extract(filename: str) -> Optional[int]:
            shape = "".join("0" if char.isdecimal() else char for char in filename)
            beginnings, endings = positions(shape)
            # Preserve the same selection order on cache hits and misses.
            for start in beginnings:
                for end in endings:
                    if end <= start:
                        break
                    try:
                        return round(datetime.strptime(filename[start:end], date_format).timestamp())
                    except (ValueError, OverflowError, OSError):
                        continue
                    except re.error as error:
                        if self.logger is None:
                            raise
                        self.logger.verbose(LogLevel.WARN, f"Invalid filename timestamp format '{date_format}': {error} -> File is ignored: {filename}")
                        return None
            if self.logger is None:
                raise RuntimeError(f"Cannot report an invalid filename timestamp without a logger: {filename}")
            self.logger.verbose(LogLevel.WARN, f"No valid filename timestamp found -> It is ignored: {filename}")
            return None

        return extract

    def get_file_seconds(self, file: Path) -> Optional[int]:
        return self.__file_seconds_cache.compute_if_absent(file, lambda f: self._get_file_seconds_internal(f))

    def _get_file_seconds_internal(self, file: Path) -> Optional[int]:
        seconds: Optional[float]
        extractor = self._filename_extractor
        # Use the file itself, or the folder itself with the "folder" time source.
        if not self._folder_mode or self._folder_mode_time_src == "folder":
            if self._age_type == "filename":
                seconds = extractor(file.name)
            else:
                seconds = getattr(self.__file_stats_cache.compute_if_absent(file, Path.stat), f"st_{self._age_type}")
        elif self._folder_mode_time_src is not None and self._folder_mode_time_src.startswith("path="):
            time_file = Path(split_escaped("=", self._folder_mode_time_src, "folder time source", self._folder_mode_time_src, expected_length=2)[1])
            if time_file.anchor:
                raise ValueError(f"The path value for the folder time source must be relative to the folder '{file}': {time_file}")
            time_file = (file / time_file).resolve()
            if not time_file.is_relative_to(file.resolve()):
                raise ValueError(f"The path value for the folder time source must be inside the folder '{file}': {time_file}")
            if not time_file.is_file():
                raise ValueError(f"The path value for the folder time source must be a file: {time_file}")
            if time_file.is_symlink():
                raise ValueError(f"The path value for the folder time source must not be a symlink: {time_file}")
            if self._age_type == "filename":
                seconds = self.__file_seconds_cache.compute_if_absent(time_file, lambda f: extractor(f.name))
            else:
                seconds = getattr(self.__file_stats_cache.compute_if_absent(time_file, Path.stat), f"st_{self._age_type}")
        else:
            # Both youngest-file and oldest-file inspect contained files recursively.
            files = [f for f in file.rglob("*") if f.is_file() and not f.is_symlink()]
            if self._age_type == "filename":
                # Cache parsed timestamps and exclude unrecognized names.
                timestamps = [timestamp for time_file in files if (timestamp := self.__file_seconds_cache.compute_if_absent(time_file, lambda f: extractor(f.name))) is not None]
                if not timestamps:
                    if self.logger is None:
                        raise RuntimeError(f"Cannot report missing filename timestamps without a logger: {file}")
                    self.logger.verbose(LogLevel.WARN, f"Folder '{file}' contains no valid filename timestamps -> It is ignored")
                    return None
            else:
                if not files:
                    raise ValueError(f"Folder '{file}' contains no files, cannot compute time source for folder with mode: {self._age_type}")
                timestamps = [getattr(self.__file_stats_cache.compute_if_absent(f, Path.stat), f"st_{self._age_type}") for f in files]
            if self._folder_mode_time_src == "youngest-file":
                seconds = max(timestamps)
            elif self._folder_mode_time_src == "oldest-file":
                seconds = min(timestamps)
            else:
                raise ValueError(f"Invalid or missing time source for folder mode: {self._folder_mode_time_src}")
        return None if seconds is None else round(seconds)

    def get_file_bytes(self, file: Path) -> int:
        if self._folder_mode:
            return sum(self.__file_stats_cache.compute_if_absent(f, Path.stat).st_size for f in file.rglob("*") if f.is_file() and not f.is_symlink())
        return int(self.__file_stats_cache.compute_if_absent(file, Path.stat).st_size)


def sort_files(files: Iterable[Path], file_stats: FileStats) -> list[Path]:
    files_with_seconds = ((file, seconds) for file in files if (seconds := file_stats.get_file_seconds(file)) is not None)
    return [file for file, _ in sorted(files_with_seconds, key=lambda item: (-item[1], item[0].name))]


class LogLevel(IntEnum):
    ERROR = 0
    WARN = 1
    INFO = 2
    DEBUG = 3

    @classmethod
    def from_name_or_number(cls, prefix: str) -> "LogLevel":
        result = None
        match = next((m for m in cls if m.name == prefix.upper().strip()), None)
        if match is not None:
            result = match
        else:
            try:
                result = cls(int(prefix.upper().strip()))
            except ValueError:
                raise ValueError("Invalid log level: " + prefix)
        return result


class Logger:
    _decisions: dict[Path, list[tuple[str, Optional[str]]]]
    _args: ConfigNamespace
    _file_stats: FileStats

    def __init__(self, args: ConfigNamespace, file_stats: FileStats) -> None:
        self._args = args
        self._file_stats = file_stats
        self._decisions: dict[Path, list[tuple[str, Optional[str]]]] = defaultdict(list)

    def _get_file_attributes(self, file: Path, args: ConfigNamespace, file_stats: FileStats) -> str:
        if (seconds := file_stats.get_file_seconds(file)) is None:
            return ""
        return f"{args.age_type}: {datetime.fromtimestamp(seconds)}, size: {ModernStrictArgumentParser.format_size(file_stats.get_file_bytes(file))}"

    def has_log_level(self, level: LogLevel) -> bool:
        return int(level) <= int(self._args.verbose)

    def _raw_verbose(self, level: LogLevel, message: str, file: Optional[TextIO] = None, prefix: str = "") -> None:
        if file is None:
            file = sys.stdout
        print(f"[{prefix or LogLevel(level).name}] {message}", file=file)

    def verbose(self, level: LogLevel, message: str, file: Optional[TextIO] = None, prefix: str = "") -> None:
        if self.has_log_level(level):
            self._raw_verbose(level, message, file, prefix)

    def add_decision(self, level: LogLevel, file: Path, message: str, debug: Optional[str] = None, append: bool = False) -> None:
        if self._file_stats.get_file_seconds(file) is None:
            return
        if self.has_log_level(LogLevel.DEBUG):  # Decision history and debug message and file details only with debug log level
            if append:
                self._decisions[file].append((message, f"{(f'{debug}, ' if debug else '')}{self._get_file_attributes(file, self._args, self._file_stats)})"))
            else:
                self._decisions[file].insert(0, (message, f"{(f'{debug}, ' if debug else '')}{self._get_file_attributes(file, self._args, self._file_stats)}"))
        elif self.has_log_level(level):
            if len(self._decisions[file]) == 0:
                self._decisions[file].append((message, None))
            else:
                self._decisions[file].insert(0, (message, None))

    def _format_decision(self, decision: tuple[str, Optional[str]]) -> str:
        message, debug = decision
        return message + (f" ({debug})" if debug is not None else "")

    def print_decisions(self) -> None:
        if len(self._decisions) > 0:
            longest_file_name_length = max(len(p.name) for p in self._decisions) + 1
            for file in sort_files(self._decisions, self._file_stats):
                decisions = self._decisions[file]
                if not decisions:
                    continue
                self._raw_verbose(LogLevel.INFO, f"{file.name:<{longest_file_name_length}}: {self._format_decision(decisions[0])}")
                if not self.has_log_level(LogLevel.DEBUG):
                    continue
                for idx, decision in enumerate(decisions[1:]):
                    self._raw_verbose(LogLevel.DEBUG, f"{' ' * ((longest_file_name_length + 2) + idx * 4)}└── {self._format_decision(decision)}")


class CompanionType(Enum):
    PREFIX = 1
    SUFFIX = 2

    @classmethod
    def by_name(cls, name: str) -> "CompanionType":
        try:
            return cls[name.strip().upper()]
        except KeyError:
            raise ValueError(f"Invalid CompanionType: {name}")


@dataclass(frozen=True)
class CompanionRule:
    _type: CompanionType
    _match: str
    _companion: str
    _rule_def: Optional[str] = field(default=None, compare=False, hash=False)

    def __post_init__(self) -> None:
        if self._match == self._companion:
            raise ValueError(f"CompanionRule \"{self._rule_def if self._rule_def is not None else '<unspecified>'}\": 'match' and 'companion' must be different")
        if not self._companion:
            raise ValueError(f"CompanionRule \"{self._rule_def if self._rule_def is not None else '<unspecified>'}\": 'companion' must not be empty")

    def matches(self, file: Path) -> bool:
        if len(self._match) == 0:
            return True
        if self._type is CompanionType.PREFIX:
            return file.name.startswith(self._match)
        if self._type is CompanionType.SUFFIX:
            return file.name.endswith(self._match)
        raise AssertionError(f"Unhandled CompanionType: {self._type}")

    def replace(self, file: Path) -> Path:
        if self._type is CompanionType.PREFIX:
            new_name = self._companion + file.name[len(self._match) :]
            return file.with_name(new_name)
        if self._type is CompanionType.SUFFIX:
            stem = file.name if self._match == "" else file.name[: -len(self._match)]
            new_name = stem + self._companion
            return file.with_name(new_name)
        raise AssertionError(f"Unhandled CompanionType: {self._type}")


class ModernHelpFormatter(argparse.HelpFormatter):
    JOINED_ARGS = {"max_size", "max_age", "skip_by_filesize"}

    @no_type_check
    def __init__(self, *a, **kw) -> None:  # noqa: ANN002, ANN003
        width = shutil.get_terminal_size(fallback=(80, 24)).columns
        max_pos = min(50, max(24, width // 2))
        super().__init__(*a, max_help_position=max_pos, width=width, **kw)

    @no_type_check
    def start_section(self, heading) -> None:  # noqa: ANN001
        super().start_section(heading.capitalize())

    @no_type_check
    def format_help(self) -> str:
        return f"retentions {VERSION}\n\n" + "A small feature-rich cross-platform CLI tool for file retention management\n\n" + super().format_help()

    @no_type_check
    def _format_args(self, action, default_metavar):  # noqa: ANN001, ANN202
        if action.dest in self.JOINED_ARGS:
            return action.metavar
        return super()._format_args(action, default_metavar)


class ExitOnlyVersion(argparse.Action):
    @no_type_check
    def __call__(self, parser, namespace, values, option_string=None):  # noqa: ARG002,ANN001,ANN204
        print(f"retentions {VERSION}")
        parser.exit(0)


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
        print("\nError(s):", file=sys.stderr)
        for line in message.split("\n"):
            print(f"  • {line}", file=sys.stderr)
        print("\nHint: Try '--help' for more information (or 'man retentions' or the README.md at https://github.com/tkn777/retentions).")
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

    def _parse_delete_companions(self, companion_rule_strings: list[str]) -> set[CompanionRule]:
        companion_rule_set: set[CompanionRule] = set()
        for companion_rule_string in companion_rule_strings:
            (type, match, companions_string) = tuple(split_escaped(":", companion_rule_string, "companion", companion_rule_string, expected_length=3))
            companion_rule_set.update(CompanionRule(CompanionType.by_name(type), match.strip(), companion.strip(), companion_rule_string) for companion in split_escaped(",", companions_string, "companion", companion_rule_string))
        return companion_rule_set

    def _parse_positive_size_argument(self, size_str: str) -> float:
        size_str = size_str.strip().upper()
        re_match = re.match(r"^([0-9]+(?:\.[0-9]*)?)\s*([KMGTPE]?)$", size_str)
        if not re_match:
            raise argparse.ArgumentTypeError(f"Invalid size format: '{size_str}'")
        multipliers = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5, "E": 1024**6}
        return int(float(re_match.group(1)) * multipliers[re_match.group(2)])

    def _parse_positive_time_argument(self, time_str: str) -> float:
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
        if bytes < 0:
            raise ValueError("bytes must be >= 0")
        units = ["", "K", "M", "G", "T", "E", "P"]
        idx, value = 0, float(bytes)
        while value >= 1024 and idx < len(units) - 1:
            value /= 1024
            idx += 1
        return f"{value:.2f}".rstrip("0").rstrip(".") + units[idx]

    @staticmethod
    def format_time(seconds: int) -> str:
        if seconds < 0:
            raise ValueError("seconds must be >= 0")
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
        try:
            ns.filename_format = None
            if ns.age_type and ns.age_type.startswith("filename="):
                ns.age_type, ns.filename_format = ns.age_type.split("=", 1)
            if not Path(ns.path).resolve().is_dir():
                self.add_error(f"Path {ns.path} is not a valid directory")
            elif ns.filename_format is None and (ns.age_type not in ("ctime", "mtime", "atime", "birthtime") or not hasattr(Path(ns.path).stat(), "st_" + ns.age_type)):
                self.add_error(f"Your system (OS or FS) does not support age-type '{ns.age_type}'.")

            # Folder mode
            if ns.folder_mode is not None:
                if ns.folder_mode in ("folder", "youngest-file", "oldest-file") or (ns.folder_mode.startswith("path=") and len(ns.folder_mode) > 5):
                    ns.folder_mode_time_src = ns.folder_mode
                    ns.folder_mode = True
                else:
                    self.add_error(f"Invalid folder time source: {ns.folder_mode}.")
                ns.entity_name = "folder"
            else:
                ns.folder_mode_time_src = None
                ns.entity_name = "file"

            # dry-run implies verbose
            if ns.dry_run and not ns.list_only and ns.verbose is None:
                ns.verbose = LogLevel.INFO

            # Default verbosity, if none given
            if ns.verbose is None:
                ns.verbose = LogLevel.ERROR

            # normalize 0-byte separator
            if ns.list_only == "\\0":
                ns.list_only = "\0"

            # regex validation (and compilation), also for protect
            if ns.regex_mode is not None:
                ns.regex_compiled = self._compile_regex(ns.file_pattern, ns.regex_mode)
                if ns.protect is not None:
                    ns.protect_compiled = self._compile_regex(ns.protect, ns.regex_mode)

            # skip by filesize
            if ns.skip_by_filesize is not None:
                ns.skip_by_filesize = "".join(token.strip() for token in ns.skip_by_filesize)
                ns.skip_by_filesize_bytes = self._parse_positive_size_argument(ns.skip_by_filesize)

            # max-size parsing
            if ns.max_size is not None:
                ns.max_size = "".join(token.strip() for token in ns.max_size)
                ns.max_size_bytes = self._parse_positive_size_argument(ns.max_size)

            # max-age parsing
            if ns.max_age is not None:
                ns.max_age = "".join(token.strip() for token in ns.max_age)
                ns.max_age_seconds = self._parse_positive_time_argument(ns.max_age)

            # companion deletes
            ns.delete_companion_set = self._parse_delete_companions(ns.delete_companions) if ns.delete_companions is not None else set()

            # Validate options
            def validate(failed: Callable[[], bool], msg: str) -> None:
                if failed():
                    self.add_error(msg)

            has_retention_options = ns.minutes or ns.hours or ns.days or ns.weeks or ns.week13 or ns.months or ns.quarters or ns.years or ns.last

            validate(lambda: ns.list_only and ns.verbose > LogLevel.ERROR, "--list-only and --verbose (> ERROR) cannot be used together")
            validate(lambda: ns.list_only and ns.delete_companions, "--list-only and --delete-companions must not be combined, because list-only is not for companions")
            validate(lambda: ns.list_only is not None and ns.delete_symlinks, "--list-only and --delete-symlinks must not be combined")
            validate(lambda: ns.folder_mode and ns.delete_symlinks, "--folder-mode and --delete-symlinks must not be combined")
            validate(lambda: ns.folder_mode and ns.skip_by_filesize, "--folder-mode and --skip-by-filesize must not be combined")
            validate(lambda: ns.folder_mode and ns.delete_companions, "--folder-mode and --delete-companions must not be combined")
            validate(lambda: ns.skip_by_filesize and not has_retention_options, "--skip-by-filesize must be combined with any retention option(s)")

            # Init some defaults
            ns.protected_files = set()
            ns.symlink_paths = {}
            ns.symlink_companions = set()

        except BaseException as e:
            self.add_error(str(e))

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
        usage=("retentions path file_pattern [options]\n\nExample:\n  retentions /data/backups '*.tar.gz' -d 7 -w 4 -m 6 -a 12m"),
        epilog="Use with caution!! This tool deletes files unless --dry-run or --list-only is set.",
        formatter_class=ModernHelpFormatter,
        add_help=False,
    )

    g_main = parser.add_argument_group("Main arguments")
    g_flags = parser.add_argument_group("Flags")
    g_ret = parser.add_argument_group("Retention options")
    g_filter = parser.add_argument_group("Filter options")
    g_behavior = parser.add_argument_group("Behavior options")
    g_expert = parser.add_argument_group("Experts options")
    g_developers = parser.add_argument_group("Developers options")
    g_common = parser.add_argument_group("Common arguments")

    # positional arguments
    g_main.add_argument("path", help="base directory to scan (no symlink traversal)")
    g_main.add_argument("file_pattern", help="glob pattern for matching files/folders (use single quotes to prevent shell expansion)")

    # argument flags
    # fmt: off
    g_flags.add_argument("--regex-mode", "-r", type=str, choices=["casesensitive", "ignorecase"], metavar="mode", const="casesensitive", nargs="?", default=None,
        help="file_pattern / protect is a regex (otherwise: glob pattern) - mode: casesensitive, ignorecase, default: casesensitive")
    g_flags.add_argument("--protect", "-p", type=str, default=None, metavar="protect", help="Protect files from deletion (using regex or glob, like file_pattern)")
    g_flags.add_argument("--age-type", type=str, metavar="time-attr", default="mtime", nargs="?",
        help="Used age source: mtime (default), ctime, atime, birthtime, or 'filename=<format>' (Python date/time format). File attributes are OS and filesystem dependent; see README.md or man page.")
    g_flags.add_argument("--folder-mode", type=str, metavar="time-src", default=None, nargs="?", const="youngest-file",
        help="Use folders instead of files. Time source: youngest-file (default), oldest-file, folder, or path=<path> (relative, inside each folder). youngest-file and oldest-file search recursively.")
    # fmt: on

    # retention options
    g_ret.add_argument("--minutes", type=parser.positive_int_argument, metavar="N", help=argparse.SUPPRESS)
    g_ret.add_argument("--hours", "-h", type=parser.positive_int_argument, metavar="N", help="Retain one file/folder per hour from the last N hours")
    g_ret.add_argument("--days", "-d", type=parser.positive_int_argument, metavar="N", help="Retain one file/folder per day from the last N days")
    g_ret.add_argument("--weeks", "-w", type=parser.positive_int_argument, metavar="N", help="Retain one file/folder per week from the last N weeks")
    g_ret.add_argument("--months", "-m", type=parser.positive_int_argument, metavar="N", help="Retain one file/folder per month from the last N months")
    g_ret.add_argument("--quarters", "-q", type=parser.positive_int_argument, metavar="N", help="Retain one file/folder per quarter from the last N quarters (quarter by months)")
    g_ret.add_argument("--week13", type=parser.positive_int_argument, metavar="N", help="Retain one file/folder per 13-week block from the last N 13-week blocks (quarter by weeks)")
    g_ret.add_argument("--years", "-y", type=parser.positive_int_argument, metavar="N", help="Retain one file/folder per year from the last N years")
    g_ret.add_argument("--last", "-l", type=parser.positive_int_argument, metavar="N", help="Always retain the N most recently modified files/folders")
    g_ret.add_argument("--skip-by-filesize", "-i", type=str, metavar="size", nargs="+", help="Skip (and delete) files smaller than <size> (e.g. 12, 2K, 1.5M)")

    # filter options
    g_filter.add_argument("--max-size", "-s", type=str, metavar="size", nargs="+", help="Keep maximum within total size N (e.g. 12, 10.5M, 500 G, 3E)")
    g_filter.add_argument("--max-files", "-f", type=parser.positive_int_argument, metavar="count", help="Keep maximum total files/folders N")
    g_filter.add_argument("--max-age", "-a", type=str, metavar="age", nargs="+", help="Keep maximum within time span N from script start (e.g. 3600, 1h, 1 d, 1w, 1m, 1q, 1y - with 1 month = 30 days)")

    # behavior options
    g_behavior.add_argument("--dry-run", "-X", action="store_true", help="Show planned actions but do not delete any files/folders")
    g_behavior.add_argument("--no-lock-file", action="store_false", dest="use_lock_file", default=True, help="Omit lock file (default: enabled)")
    g_behavior.add_argument("--fail-on-delete-error", action="store_true", default=False, help="Fails and exits if a file/folder could not be deleted (default: disabled and log error)")
    # fmt: off
    g_behavior.add_argument("--list-only", "-L", nargs="?", const="\n", default=None, metavar="sep", help="Output only file/folder paths that would be deleted (incompatible with --verbose) (optional separator (sep): e.g. '\\0')")
    g_behavior.add_argument("--verbose", "-V", "-v", type=parser.verbose_argument, default=None, nargs="?", const=LogLevel.INFO, metavar="lev",
                            help="Verbosity level: 0 = error, 1 = warn, 2 = info, 3 = debug (default: 'info', if specified without value; 'error' otherwise; use numbers or names)")

    # experts options
    g_expert.add_argument("--delete-companions", type=str, metavar="rule", nargs="+", help="Delete companion files defined by the rules (prefix|suffix:match:companions, e.g. 'suffix:tar.gz:sha256,md5')")
    g_expert.add_argument( "--delete-symlinks", choices=["directory", "system"],
                          help="Delete symlinks to deleted files/companions (directory: direct children only; system: recursive from root, current drive on Windows). Ignores --protect; incompatible with --list-only and --folder-mode.", )
    # fmt: on

    # developers options
    g_developers.add_argument("--stacktrace", action="store_true", help="Add output of stacktrace in case of errors")

    # common options
    g_common.add_argument("--version", "-R", nargs=0, action=ExitOnlyVersion, help="show version and exit")
    g_common.add_argument("--help", "-H", action="help", help="Show this help message and exit")

    return parser


def parse_arguments() -> ConfigNamespace:
    parser = create_parser()
    args = parser.parse_args()
    return ConfigNamespace(**vars(args))


def read_filelist(args: ConfigNamespace, logger: Logger, file_stats: FileStats) -> list[Path]:
    base: Path = Path(args.path).resolve()
    if not base.exists() or not base.is_dir() or base.is_symlink():
        raise NotADirectoryError(f"Path is not found or not a directory or a symlink: {base}")

    iterator = base.iterdir() if args.regex_mode else base.glob(args.file_pattern)
    matches: list[Path] = []
    for path in iterator:
        if not (((args.folder_mode and path.is_dir()) or (not args.folder_mode and path.is_file())) and (not args.regex_mode or args.regex_compiled.match(path.name))):
            continue
        if path.is_symlink():
            logger.verbose(LogLevel.WARN, f"{args.entity_name.capitalize()} '{path}' is a symlink -> It is ignored")
            continue
        if args.folder_mode and next(path.iterdir(), None) is None:
            logger.verbose(LogLevel.WARN, f"Folder '{path}' is empty -> It is ignored")
            continue
        matches.append(path)

    if not matches:
        logger.verbose(LogLevel.WARN, f"No {args.entity_name}s found in '{base}' using " + f"{'regex (' + args.regex_mode + ')' if args.regex_mode else 'glob'} " + f"pattern '{args.file_pattern}'")
        return []

    # Check, if child of base directory
    for file in matches:
        if not Path(file).parent.resolve() == base.resolve():
            raise ValueError(f"{args.entity_name.capitalize()} '{file}' is not a child of base directory '{base}'")

    if args.protect:
        protected: set[Path] = set()
        for file in matches:
            if (args.regex_mode and args.protect_compiled.match(file.name)) or fnmatch(file.name, args.protect):
                logger.add_decision(LogLevel.INFO, file, f"Protected by {'regex' if args.regex_mode else 'glob'}: '{args.protect}'")
                protected.add(file)
        args.protected_files |= protected
        matches = [file for file in matches if file not in protected]

    # Ignore lock file (in any case, even if it is is disabled by user)
    matches = [m for m in matches if m.name != LOCK_FILE_NAME]

    if args.delete_symlinks:
        args.symlink_paths = read_symlinks(args, matches, logger)

    # sort by time (youngest first)
    return sort_files(matches, file_stats)


def get_companion_paths(file: Path, args: ConfigNamespace) -> set[Path]:
    return {rule.replace(file) for rule in args.delete_companion_set if rule.matches(file)}


def read_symlinks(args: ConfigNamespace, matches: list[Path], logger: Logger) -> dict[Path, list[Path]]:
    logger.verbose(LogLevel.INFO, "Searching for symlinks")
    directory_only = args.delete_symlinks == "directory"
    root = Path(args.path) if directory_only else Path("/")
    excluded = {"dev", "proc", "sys", "run"}
    excluded_paths: set[Path] = {root.resolve() / name for name in excluded} if not directory_only else set()
    visited: set[Path] = set()
    symlinks: defaultdict[Path, list[Path]] = defaultdict(list)
    matches_set = set(matches)
    for file in matches:
        companions = get_companion_paths(file, args)
        matches_set.update(companions)
        args.symlink_companions.update(path for path in companions if path.is_symlink())

    for directory, dirs, files in os.walk(root, followlinks=not directory_only):
        real_directory = Path(directory).resolve()
        if real_directory in visited or any(real_directory.is_relative_to(path) for path in excluded_paths):
            dirs.clear()
            continue
        visited.add(real_directory)
        if not directory_only and Path(directory) == root:
            dirs[:] = [d for d in dirs if d not in excluded]

        for name in dirs + files:
            try:
                if (path := Path(directory, name)).is_symlink() and (target := path.resolve()) in matches_set:
                    symlinks[target].append(path)
            except (OSError, RuntimeError):
                continue

        if directory_only:
            dirs.clear()

    return symlinks


@dataclass(frozen=True)
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
    _file_stats: FileStats

    def __init__(self, matches: list[Path], args: ConfigNamespace, logger: Logger, file_stats: FileStats) -> None:
        self._matches = matches
        self._keep = set()
        self._prune = set()
        self._args = args
        self._logger = logger
        self._file_stats = file_stats

    def _skip_by_filesize(self, file: Path) -> bool:
        if self._args.skip_by_filesize and self._file_stats.get_file_bytes(file) < self._args.skip_by_filesize_bytes:
            self._prune.add(file)
            self._logger.add_decision(LogLevel.INFO, file, "Skipped (and deleted) because of filesize", debug=f"{ModernStrictArgumentParser.format_size(self._file_stats.get_file_bytes(file))} < {self._args.skip_by_filesize_bytes}")
            return True
        return False

    def _get_bucket_key(self, retention_mode: str, timestamp: int) -> str:
        dt = datetime.fromtimestamp(timestamp)
        if retention_mode == "minutes":
            return dt.strftime("%Y-%m-%d-%H-%M")
        if retention_mode == "hours":
            return dt.strftime("%Y-%m-%d-%H")
        if retention_mode == "days":
            return dt.strftime("%Y-%m-%d")
        if retention_mode == "weeks":
            year, week, _ = dt.isocalendar()
            return f"{year}-W{week:02d}"
        if retention_mode == "months":
            return dt.strftime("%Y-%m")
        if retention_mode == "quarters":
            quarter = ((dt.month - 1) // 3) + 1
            return f"{dt.year}-Q{quarter}"
        if retention_mode == "week13":
            year, week, _ = dt.isocalendar()
            bucket = ((week - 1) // 13) + 1
            return f"{year}-week13-{bucket}"
        if retention_mode == "years":
            return str(dt.year)
        raise ValueError(f"invalid retention mode: {retention_mode}")

    def _create_retention_buckets(self, retention_mode: str) -> dict[str, list[Path]]:
        buckets: dict[str, list[Path]] = {}
        for file in self._matches:
            if self._skip_by_filesize(file):
                continue
            ts = self._file_stats.get_file_seconds(file)
            if ts is None:
                continue
            key = self._get_bucket_key(retention_mode, ts)
            buckets.setdefault(key, []).append(file)
        # newest file first inside each bucket
        for key in buckets:
            buckets[key] = sort_files(buckets[key], self._file_stats)
        return buckets

    def _process_retention_buckets(self, retention_mode: str, retention_mode_count: int, buckets: dict[str, list[Path]], last_keep_time: int) -> int:
        cutoff_key: Optional[str] = None
        if last_keep_time != MAX_FILE_SIZE:
            cutoff_key = self._get_bucket_key(retention_mode, last_keep_time)
        count = 0
        for key in sorted(buckets.keys(), reverse=True):
            if cutoff_key is not None and key >= cutoff_key:  # Skip buckets already consumed by finer-grained retention modes
                continue
            files = [(file, timestamp) for file in buckets[key] if file not in self._keep and (timestamp := self._file_stats.get_file_seconds(file)) is not None and timestamp < last_keep_time]
            if count < retention_mode_count and len(files) > 0:
                file_keep, file_keep_time = files[0]
                self._logger.add_decision(LogLevel.INFO, file_keep, f"Keeping for mode '{retention_mode}' {count + 1:02d} / {retention_mode_count:02d}", debug=f"bucket: {key}")
                self._keep.add(file_keep)
                last_keep_time = file_keep_time
                count += 1
        return last_keep_time

    def _process_last_n(self) -> None:
        kept = 0
        for file in self._matches:
            if self._skip_by_filesize(file):
                continue
            if kept >= self._args.last:
                break
            self._logger.add_decision(LogLevel.INFO, file, f"Keeping last {kept + 1:02d}/{self._args.last:02d}") if file not in self._keep else None
            self._keep.add(file)  # Idempotent
            self._prune.discard(file)  # Idempotent
            kept += 1

    def _filter_file(self, file: Path, message: str) -> None:
        self._keep.remove(file)
        self._prune.add(file)
        self._logger.add_decision(LogLevel.INFO, file, message)

    def _filter_files(self) -> None:
        # max-files
        if self._args.max_files is not None and self._keep:
            sorted_keep = sort_files(self._keep, self._file_stats)  # Must be sorted by xtime before applying filters, because set is unfiltered
            for idx, file in enumerate(sorted_keep[self._args.max_files :], start=self._args.max_files + 1):
                self._filter_file(file, f"Filtering: max total count of {self._args.entity_name}s exceeded: {idx:02d} > {self._args.max_files:02d}")

        # max-size
        if self._args.max_size is not None and self._keep:
            sorted_keep = sort_files(self._keep, self._file_stats)  # Must be sorted by xtime before applying filters, because set is unfiltered
            bytes_sum: int = 0
            for file in sorted_keep:
                bytes_sum += self._file_stats.get_file_bytes(file)
                if bytes_sum > self._args.max_size_bytes:
                    self._filter_file(file, f"Filtering: max total size exceeded: {ModernStrictArgumentParser.format_size(bytes_sum)} > {self._args.max_size}")

        # max-age
        if self._args.max_age is not None and self._keep:
            sorted_keep = sort_files(self._keep, self._file_stats)  # Must be sorted by xtime before applying filters, because set is unfiltered
            threshold = SCRIPT_START - int(self._args.max_age_seconds)
            for file in sorted_keep:
                file_time = self._file_stats.get_file_seconds(file)
                if file_time is not None and file_time <= threshold:
                    self._filter_file(file, f"Filtering: max total age exceeded: {ModernStrictArgumentParser.format_time(int(SCRIPT_START - file_time))} > {self._args.max_age}")

    def process_retention_logic(self) -> RetentionsResult:
        # Retention by time buckets; generation and processing must be done per retention mode sequently in one single loop
        retention_rules_applied = False
        last_keep_time = MAX_FILE_SIZE
        for retention_mode in ["minutes", "hours", "days", "weeks", "months", "quarters", "week13", "years"]:
            retention_mode_count = getattr(self._args, retention_mode)
            if retention_mode_count:
                retention_rules_applied = True
                buckets = self._create_retention_buckets(retention_mode)
                last_keep_time = self._process_retention_buckets(retention_mode, retention_mode_count, buckets, last_keep_time)

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
            self._logger.verbose(LogLevel.DEBUG, f"No retention rules specified, keeping all {self._args.entity_name}s")
            self._keep.update(self._matches)
            for file in self._matches:
                self._logger.add_decision(LogLevel.INFO, file, "Keeping: no retention rules specified")

        # Filter keep's
        self._filter_files()

        # Simple integrity checks
        if not len(self._matches) == len(self._keep) + len(self._prune):
            raise IntegrityCheckFailedError(f"{self._args.entity_name.capitalize()} count mismatch: some files are neither to retain nor to delete (all: {len(self._matches)}, keep: {len(self._keep)}, prune: {len(self._prune)}!!)")
        if not len(self._prune) == sum(1 for file in self._matches if is_file_to_delete(self._keep, self._prune, file)):
            raise IntegrityCheckFailedError(f"{self._args.entity_name.capitalize()} deletion count mismatch!!")

        return RetentionsResult(self._keep, self._prune, self._logger)


def is_file_to_delete(keep: set[Path], prune: set[Path], file: Path) -> bool:
    return file not in keep and file in prune


FILETYPE_PATH = "file"
FILETYPE_COMPANION = "companion"
FILETYPE_SYMLINK = "symlink"


def delete_file(file: Path, args: ConfigNamespace, logger: Logger, type: str) -> int:
    counter = 0
    if (type != FILETYPE_SYMLINK or args.delete_symlinks == "directory") and file.parent.resolve() != Path(args.path).resolve():
        raise IntegrityCheckFailedError(f"{args.entity_name.capitalize()} '{file}' is not a child of parent directory '{file.parent}'")
    if args.dry_run:
        logger.verbose(LogLevel.INFO, f"Dry-run: deleting ({type}): {file.name}")  # Just simulate deletion
    else:
        logger.verbose(LogLevel.INFO, f"Deleting ({type}): {file.name}")
        try:
            if args.folder_mode:
                shutil.rmtree(file)
            else:
                file.unlink()
        except OSError as e:
            error_message = f"Error while deleting ({type}) {args.entity_name} '{file.name}': {e}"
            if args.fail_on_delete_error:
                raise FileCouldNotBeDeleteError(error_message)
            logger.verbose(LogLevel.ERROR, error_message, file=sys.stderr)
            return 0
    for symlink in args.symlink_paths.get(file, []):
        counter += delete_file(symlink, args, logger, FILETYPE_SYMLINK)
    return counter + 1


def run_deletion(file: Path, args: ConfigNamespace, logger: Logger, disallowed_companions: set[Path]) -> int:
    if file.is_symlink():  # Should never happen
        raise IntegrityCheckFailedError(f"Refusing to delete symlink: {file}")
    deletion_count = 0
    if args.list_only:
        print(file.absolute(), end=args.list_only)  # List mode
    else:
        companions = get_companion_paths(file, args)
        deletion_count += delete_file(file, args, logger, FILETYPE_PATH)
        # delete companion files (if any)
        for companion_file in companions:
            if companion_file in args.symlink_companions or companion_file.is_symlink():
                logger.verbose(LogLevel.WARN, f"Companion file is a symlink -> It is ignored: {companion_file}")
                continue
            if companion_file in disallowed_companions or (args.protect and ((args.regex_mode and args.protect_compiled.match(companion_file.name)) or fnmatch(companion_file.name, args.protect))):
                raise IntegrityCheckFailedError(f"Companion file '{companion_file}' must not be deleted, because it is e.g. kept, pruned, protected, the lock-file, ...")
            if companion_file.exists() and companion_file.is_file():
                deletion_count += delete_file(companion_file, args, logger, FILETYPE_COMPANION)
    return deletion_count


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

        file_stats = FileStats(args.age_type, args.folder_mode, args.folder_mode_time_src, args.filename_format)
        logger = Logger(args, file_stats)
        file_stats.logger = logger

        if args.age_type == "filename" and "%Z" in re.findall(r"%.|.", args.filename_format or "", re.S):
            logger.verbose(LogLevel.WARN, f"Unsupported '%Z' directive in filename timestamp format '{args.filename_format}' -> Use '%z' with a numeric UTC offset; no files or folders are processed")
            return

        logger.verbose(LogLevel.INFO, "Command line: " + " ".join(shlex.quote(arg) for arg in sys.argv))
        logger.verbose(LogLevel.DEBUG, f"Parsed arguments: {args}")

        if args.use_lock_file:
            lock_file = Path(args.path + f"/{LOCK_FILE_NAME}").resolve()
            if lock_file.exists():
                raise ConcurrencyError(f"A retention process is already running on {args.path} (or there is a stale lockfile)")
            lock_file.touch()
            created_lock_file = True

        if args.age_type == "atime":
            logger.verbose(LogLevel.WARN, "age-type 'atime' depends on platform, filesystem and mount options (e.g. 'relatime'/'noatime') => results may be misleading")
        if args.age_type == "ctime":
            logger.verbose(LogLevel.WARN, "age-type 'ctime' has platform-dependent semantics")

        matches = read_filelist(args, logger, file_stats)
        logger.verbose(LogLevel.INFO, f"Found {len(matches)} {args.entity_name}s using " + f"{'regex (' + args.regex_mode + ')' if args.regex_mode else 'glob'} " + f"pattern '{args.file_pattern}'")
        if len(matches) > 0:
            logger.verbose(LogLevel.DEBUG, f"Found {args.entity_name}s : " + ", ".join(f'"{p.name}"' for p in matches))

        retentions_result = RetentionLogic(matches, args, logger, file_stats).process_retention_logic()

        logger.print_decisions()

        logger.verbose(LogLevel.INFO, f"Total {args.entity_name}s found:     {len(matches):03d}")
        logger.verbose(LogLevel.INFO, f"Total {args.entity_name}s protected: {len(args.protected_files):03d}")
        logger.verbose(LogLevel.INFO, f"Total {args.entity_name}s to retain: {len(retentions_result.keep):03d}")
        logger.verbose(LogLevel.INFO, f"Total {args.entity_name}s to delete: {len(retentions_result.prune):03d}")

        deletion_started = False
        deletion_count = 0
        disallowed_companions = retentions_result.keep | retentions_result.prune | args.protected_files
        if lock_file is not None:
            disallowed_companions.add(lock_file)
        for file in matches:
            if is_file_to_delete(retentions_result.keep, retentions_result.prune, file):
                if not deletion_started:
                    logger.verbose(LogLevel.INFO, "Deletion phase started")
                    deletion_started = True
                deletion_count += run_deletion(file, args, logger, disallowed_companions)

        if deletion_started:
            logger.verbose(LogLevel.INFO, "Deletion phase completed")
            logger.verbose(LogLevel.INFO, f"Total {args.entity_name}s deleted:   {len(retentions_result.prune):03d}")

    except OSError as e:
        handle_exception(e, 1, args.stacktrace if args is not None else True)
    except (ValueError, argparse.ArgumentTypeError) as e:
        handle_exception(e, 2, args.stacktrace if args is not None else False)
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
