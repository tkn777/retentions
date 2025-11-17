#
# retentions
#
# A small, cross-platform CLI tool to apply backup-like retention rules to any file set.
#
# Copyright (c) 2025 Thomas Kuhlmann
#
# Licensed under the MIT License. See LICENSE file in the project root for license information.
#
# https://github.com/tkn777/retentions
#

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime
from os import stat_result
from pathlib import Path
from typing import NoReturn, TextIO


VERSION: str = "dev-0.6.0"


class IntegrityCheckFailedError(Exception):
    pass


class NoFilesFoundError(Exception):
    pass


def verbose(level: int, maximum_level: int, message: str, file: TextIO = sys.stderr) -> None:
    if level <= maximum_level:
        print(message, file=file)


_file_stats_cache: dict[Path, stat_result] = {}


def get_file_mtime(file: Path) -> float:
    return _file_stats_cache.setdefault(file, file.stat()).st_mtime


def get_file_size(file: Path) -> float:
    return _file_stats_cache.setdefault(file, file.stat()).st_size


class CleanArgumentParser(argparse.ArgumentParser):
    # Adds an empty line between usage and error message
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, f"\nError: {message}\n")


def positive_int_argument(value: str) -> int:
    try:
        int_value = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid value '{value}': must be an integer > 0")
    if int_value <= 0:
        raise argparse.ArgumentTypeError(f"Invalid value '{value}': must be an integer > 0")
    return int_value


def parse_positive_size_argument(size_str: str) -> int:
    size_str = size_str.strip().upper()
    re_match = re.match(r"^([0-9]+(?:\.[0-9]*)?)\s*([KMGTPE]?)$", size_str)
    if not re_match:
        raise argparse.ArgumentTypeError(f"Invalid size format: '{size_str}'")
    multipliers = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5, "E": 1024**6}
    return int(float(re_match.group(1)) * multipliers[re_match.group(2)])


def parse_arguments() -> argparse.Namespace:
    parser = CleanArgumentParser(
        prog="retentions",
        usage=("retentions path file_pattern [options]\n\nExample:\n  retentions /data/backups '*.tar.gz' -d 7 -w 4 -m 6\n"),
        description=("A minimal cross-platform CLI tool for file retention management"),
        epilog="Use with caution!! This tool deletes files unless --dry-run or --list-only is set.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        add_help=False,
    )

    # positional arguments
    parser.add_argument("path", help="Base directory to scan")
    parser.add_argument("file_pattern", help="glob pattern for matching files (use quotes to prevent shell expansion")

    # argument flags
    parser.add_argument("-r", "--regex", action="store_true", help="file_pattern is a regex (default: glob pattern)")

    # optional retention arguments (validated, no defaults)
    parser.add_argument("-h", "--hours", type=positive_int_argument, metavar="N", help="Keep one file per hour from the last N hours")
    parser.add_argument("-d", "--days", type=positive_int_argument, metavar="N", help="Keep one file per day from the last N days")
    parser.add_argument("-w", "--weeks", type=positive_int_argument, metavar="N", help="Keep one file per week from the last N weeks")
    parser.add_argument("-m", "--months", type=positive_int_argument, metavar="N", help="Keep one file per month from the last N months")
    parser.add_argument("-q", "--quarters", type=positive_int_argument, metavar="N", help="Keep one file per quarter from the last N quarters (quarter by months)")
    parser.add_argument("--week13", type=positive_int_argument, metavar="N", help="Keep one file per 13-week block from the last N 13-week blocks (quarter by weeks)")
    parser.add_argument("-y", "--years", type=positive_int_argument, metavar="N", help="Keep one file per year from the last N years")
    parser.add_argument("-l", "--last", type=positive_int_argument, metavar="N", help="Always keep the N most recently modified files")

    # filter arguments
    parser.add_argument("-s", "--size", type=str, metavar="N", help="Keep maximum total size N (e.g. 12, 10.5M, 500G, 3E)")

    # behavior flags
    # fmt: off
    parser.add_argument(
        "-L", "--list-only", nargs="?", const="\n", default=None, metavar="sep",
        help="Output only file paths that would be deleted (incompatible with --verbose) (optional separator (sep): e.g. '\\0')"
    )
    parser.add_argument(
        "-V", "--verbose", type=int, nargs="?", choices=[0, 1, 2, 3], default=None, const=2, metavar="lev",
        help="Verbosity level: 0 = silent, 1 = deletions only, 2 = detailed output, 3 = debug output (default: 2, if specified without value)"
    )
    # fmt: on
    parser.add_argument("-X", "--dry-run", action="store_true", help="Show planned actions but do not delete any files")

    # common flags
    parser.add_argument("-R", "--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("-H", "--help", action="help", help="Show this help message and exit")

    args = parser.parse_args()

    # default verbosity
    if not args.verbose:
        args.verbose = 0

    # incompatible flags
    if args.list_only and args.verbose > 0:
        parser.error("--list-only and --verbose cannot be used together")

    # dry-run implies verbose (unless list-only)
    if args.dry_run and not args.list_only and not args.verbose:
        verbose(0, 0, "--dry-run specified without --verbose, setting verbosity to 2")
        args.verbose = 2

    # parse --size
    if args.size:
        args.size_bytes = parse_positive_size_argument(args.size)

    # normalize list_only separator, if null byte
    if args.list_only == "\\0":
        args.list_only = "\0"

    # validate regex
    if args.regex:
        try:
            args.regex_compiled = re.compile(args.file_pattern)
        except re.error:
            parser.error(f"Invalid regular expression: {args.file_pattern}")

    verbose(3, args.verbose, f"Parsed arguments: {args}")

    # --size not implemented yet
    if args.size:
        parser.error("--size option is not implemented yet")

    return args


def read_filelist(arguments: argparse.Namespace) -> list[Path]:
    base: Path = Path(arguments.path)
    if not base.exists():
        raise FileNotFoundError(f"Path not found: {base}")
    if not base.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {base}")

    matches: list[Path] = []
    if arguments.regex:
        matches = [f for f in base.iterdir() if f.is_file() and (arguments.regex_compiled.match(f.name))]
    else:
        matches = [f for f in base.glob(arguments.file_pattern) if f.is_file()]

    if not matches:
        raise NoFilesFoundError(f"No files found in '{base}' using {'regex' if arguments.regex else 'glob'} pattern '{arguments.file_pattern}'")

    # Check, if child of base directory
    for file in matches:
        if not Path(file).parent.resolve() == base.resolve():
            raise ValueError(f"File '{file}' is not a child of base directory '{base}'")

    # sort by modification time (newest first), deterministic on ties
    matches = [p for p, _ in sorted(((p, get_file_mtime(p)) for p in matches), key=lambda t: (-t[1], t[0].name))]

    verbose(2, arguments.verbose, f"Found {len(matches)} files using {'regex' if arguments.regex else 'glob'} pattern '{arguments.file_pattern}': {[p.name for p in matches]}")

    return matches


def create_retention_buckets(existing_files: list[Path], mode: str, verbose_lev: int) -> dict[str, list[Path]]:
    buckets: dict[str, list[Path]] = defaultdict(list)
    for file in existing_files:
        timestamp = datetime.fromtimestamp(get_file_mtime(file))
        if mode == "hours":
            key = timestamp.strftime("%Y-%m-%d-%H")
        elif mode == "days":
            key = timestamp.strftime("%Y-%m-%d")
        elif mode == "weeks":
            year, week, _ = timestamp.isocalendar()
            key = f"{year}-W{week:02d}"
        elif mode == "months":
            key = timestamp.strftime("%Y-%m")
        elif mode == "quarters":
            key = f"{timestamp.year}-Q{(timestamp.month - 1) // 3 + 1}"
        elif mode == "week13":
            year, week, _ = timestamp.isocalendar()
            key = f"{year}-week13-{(week - 1) // 13 + 1}"
        elif mode == "years":
            key = str(timestamp.year)
        else:
            raise ValueError(f"invalid bucket mode: {mode}")
        buckets[key].append(file)  # add file to appropriate bucket by the computed key generated from the timestamp of the file
    if verbose_lev >= 3:
        for key, files in buckets.items():
            verbose(3, verbose_lev, f"Buckets: {key} - {', '.join(f'{p.name} ({datetime.fromtimestamp(get_file_mtime(p))})' for p in files)}")
    return buckets


def process_retention_buckets(to_keep: set[Path], to_prune: set[Path], mode: str, mode_count: int, buckets: dict[str, list[Path]], verbose_lev: int, prune_keep_decisions: dict[Path, str]) -> None:
    sorted_keys = sorted(buckets.keys(), reverse=True)  # newest first
    effective_count = mode_count
    current_count = 0
    while current_count < effective_count:
        if current_count >= len(sorted_keys):
            break  # No more buckets
        first_bucket_file = buckets[sorted_keys[current_count]][0]
        if first_bucket_file in to_keep:  # Already kept by one previous mode
            verbose(3, verbose_lev, f"Skipping '{first_bucket_file.name}' for mode {mode} as already kept by one previous mode")
            effective_count += 1
        else:
            # Keep first entry of bucket, prune the rest
            if verbose_lev >= 2:
                prune_keep_decisions[first_bucket_file] = (
                    f"Keeping '{first_bucket_file.name}': {mode} {(current_count - (effective_count - mode_count) + 1):02d}/{mode_count:02d} "
                    f"(key: {sorted_keys[current_count]}, mtime: {datetime.fromtimestamp(get_file_mtime(first_bucket_file))})"
                )
            to_keep.add(first_bucket_file)
            for file_to_prune in buckets[sorted_keys[current_count]][1:]:
                if verbose_lev >= 2:
                    prune_keep_decisions[file_to_prune] = f"Pruning '{file_to_prune.name}': {mode} (key: {sorted_keys[current_count]}, mtime: {datetime.fromtimestamp(get_file_mtime(file_to_prune))})"
                to_prune.add(file_to_prune)
        current_count += 1


def process_last_n(existing_files: list[Path], to_keep: set[Path], to_prune: set[Path], arguments: argparse.Namespace, prune_keep_decisions: dict[Path, str]) -> None:
    last_files = existing_files[: arguments.last]  # Get the N most recently modified files regardless from any retention rule (newest first)
    if arguments.verbose >= 2:
        for index, file in enumerate(last_files, start=1):
            if file not in to_keep:  # Retention rules may have already kept this file, their message takes precedence
                prune_keep_decisions[file] = f"Keeping '{file.name}': last {index:02d}/{arguments.last:02d} (mtime: {datetime.fromtimestamp(get_file_mtime(file))})"
    to_keep.update(last_files)
    to_prune.difference_update(last_files)  # ensure last N files are not pruned


def run_retention_logic(arguments: argparse.Namespace) -> tuple[list[Path], set[Path], set[Path], dict[Path, str]]:
    # Read file list
    existing_files: list[Path] = read_filelist(arguments)

    to_keep: set[Path] = set()  # Files marked to keep
    to_prune: set[Path] = set()  # Files marked for deletion
    prune_keep_decisions: dict[Path, str] = {}  # For verbose output of decisions

    # Retention by time buckets
    # retention_proceeded = False
    for mode in ["hours", "days", "weeks", "months", "quarters", "week13", "years"]:
        mode_count = getattr(arguments, mode)
        if mode_count:
            # retention_proceeded = True
            buckets = create_retention_buckets(existing_files, mode, arguments.verbose)
            process_retention_buckets(to_keep, to_prune, mode, mode_count, buckets, arguments.verbose, prune_keep_decisions)

    # Keep last N files (additional to time-based retention)
    if arguments.last:
        # retention_proceeded = True
        process_last_n(existing_files, to_keep, to_prune, arguments, prune_keep_decisions)

    # Verbose files to prune but not kept by any retention rule
    for file in [f for f in existing_files if f not in to_keep | to_prune]:
        if arguments.verbose >= 2:
            prune_keep_decisions[file] = f"Pruning '{file.name}': not matched by any retention rule (mtime: {datetime.fromtimestamp(get_file_mtime(file))})"
        to_prune.add(file)

    # If no retention rules specified, keep all files (before applying possible filtering)
    # if not retention_proceeded:
    #    verbose(3, arguments.verbose, "No retention rules specified, keeping all files")
    #    to_keep.update(existing_files)

    # Simple integrity checks
    if not len(existing_files) == len(to_keep) + len(to_prune):
        raise IntegrityCheckFailedError(f"File count mismatch: some files are neither kept nor prune (all: {len(existing_files)}, keep: {len(to_keep)}, prune: {len(to_prune)}!! [Integrity-check]")
    if not len(to_prune) == sum(1 for f in existing_files if is_file_to_delete(to_keep, f)):
        raise IntegrityCheckFailedError("File deletion count mismatch!! [Integrity-check]")

    return existing_files, to_keep, to_prune, prune_keep_decisions


def is_file_to_delete(to_keep: set[Path], file: Path) -> bool:
    return file not in to_keep


def delete_file(arguments: argparse.Namespace, file: Path) -> None:
    mtime = datetime.fromtimestamp(get_file_mtime(file))
    if arguments.list_only:
        print(file.absolute(), end=arguments.list_only)  # List mode
    else:
        if arguments.dry_run:
            verbose(2, arguments.verbose, f"DRY-RUN DELETE: {file.name} (mtime: {mtime})")  # Just simulate deletion
        else:
            verbose(1, arguments.verbose, (f"DELETING: {file.name} (mtime: {mtime})"))
            try:
                file.unlink()
            except OSError as e:  # Catch deletion error, print it, and continue
                verbose(1, arguments.verbose, f"Error while deleting file '{file.name}': {e}", file=sys.stderr)


def main() -> None:
    try:
        # Parse arguments
        arguments = parse_arguments()

        # Run retention logic
        existing_files, to_keep, to_prune, prune_keep_decisions = run_retention_logic(arguments)

        # Output prune / keep decisions
        if arguments.verbose >= 2:
            for file, message in prune_keep_decisions.items():
                verbose(2, arguments.verbose, message)

        # Summary of keep / prune counts
        verbose(2, arguments.verbose, f"Total files found: {len(existing_files):03d}")
        verbose(2, arguments.verbose, f"Total files keep:  {len(to_keep):03d}")
        verbose(2, arguments.verbose, f"Total files prune: {len(to_prune):03d}")

        # Delete files not to keep (or list them)
        for file in existing_files:
            if is_file_to_delete(to_keep, file):
                delete_file(arguments, file)

    except OSError as e:
        verbose(0, 0, f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        verbose(0, 0, f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    except NoFilesFoundError as e:
        verbose(0, 0, f"Error: {e}", file=sys.stderr)
        sys.exit(3)
    except IntegrityCheckFailedError as e:
        verbose(0, 0, f"Error: {e}", file=sys.stderr)
        sys.exit(7)
    except Exception as e:
        verbose(0, 0, f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(9)


if __name__ == "__main__":
    main()
