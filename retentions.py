#
# retentions
#
# A minimal cross-platform CLI tool for file retention management
#
# Copyright (c) 2025 Thomas Kuhlmann
#
# Licensed under the MIT License. See LICENSE file in the project root for license information.
#

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import DefaultDict, NoReturn

VERSION: str = "dev-0.3.0"


def positive_int(value: str) -> int:
    try:
        ivalue = int(value)
        if ivalue <= 0:
            raise ValueError
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid value '{value}': must be an integer > 0")
    return ivalue


class CleanArgumentParser(argparse.ArgumentParser):
    # Adds an empty line between usage and error message
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, f"\nError: {message}\n")


def parse_arguments() -> argparse.Namespace:
    parser = CleanArgumentParser(
        prog="retentions",
        usage=("retentions path file_pattern [options]\n\nExample:\n  retentions /data/backups '*.tar.gz' -d 7 -w 4 -m 6\n"),
        description=("A minimal cross-platform CLI tool for file retention management"),
        epilog="Use with caution!! This tool deletes files unless --dry-run or --list-only is set.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # positional arguments
    parser.add_argument("path", help="Base directory to scan")
    parser.add_argument("file_pattern", help="Regex or glob pattern for matching files (use quotes to prevent shell expansion)")

    # argument flags
    parser.add_argument("-r", "--regex", action="store_true", help="file_pattern is a regex (default: glob pattern)")

    # optional retention arguments (validated, no defaults)
    parser.add_argument("-H", "--hours", type=positive_int, metavar="N", help="Keep one file per hour from the last N hours")
    parser.add_argument("-d", "--days", type=positive_int, metavar="N", help="Keep one file per day from the last N days")
    parser.add_argument("-w", "--weeks", type=positive_int, metavar="N", help="Keep one file per week from the last N weeks")
    parser.add_argument("-m", "--months", type=positive_int, metavar="N", help="Keep one file per month from the last N months")
    parser.add_argument("-y", "--years", type=positive_int, metavar="N", help="Keep one file per year from the last N years")
    parser.add_argument("-l", "--last", type=positive_int, metavar="N", help="Always keep the N most recently modified files")

    # mode flags
    parser.add_argument("-X", "--dry-run", action="store_true", help="Show planned actions but do not delete any files")
    parser.add_argument(
        "-L",
        "--list-only",
        nargs="?",
        const="\n",
        default=argparse.SUPPRESS,
        metavar="sp",
        help="Output only file paths that would be deleted (incompatible with --verbose) (optional separator (sp): e.g. '\\0')",
    )
    parser.add_argument("-V", "--verbose", action="store_true", help="Show detailed output of KEEP/DELETE decisions and time buckets")

    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    args = parser.parse_args()

    # incompatible flags
    if args.list_only and args.verbose:
        parser.error("--list-only and --verbose cannot be used together")

    # dry-run implies verbose (unless list-only)
    if args.dry_run and not args.list_only:
        args.verbose = True

    # default to --last 10 if no retention options given
    if not any([args.hours, args.days, args.weeks, args.months, args.years, args.last]):
        args.last = 10
        if args.verbose:
            print("No retention options specified -> Defaulting to --last 10")

    # normalize list_only separator, if null byte
    if args.list_only == "\\0":
        args.list_only = "\0"

    if args.verbose:
        print(f"Using arguments: {vars(args)}")

    return args


class NoFilesFoundError(Exception):
    pass


def read_filelist(base_path: str, pattern: str, use_regex: bool, verbose: bool) -> list[Path]:
    base: Path = Path(base_path)
    matches: list[Path] = []

    if not base.exists():
        raise FileNotFoundError(f"Path not found: {base}")
    if not base.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {base}")

    # pattern is a regex
    if use_regex:
        pattern_compiled = re.compile(pattern)
        for file in base.iterdir():
            if file.is_file() and pattern_compiled.match(file.name):
                matches.append(file)

    # pattern is a glob
    else:
        matches = [f for f in base.glob(pattern) if f.is_file()]

    if not matches:
        raise NoFilesFoundError(f"No files found in '{base}' using {'regex' if use_regex else 'glob'} pattern '{pattern}'")

    # sort by modification time (newest first), deterministic on ties
    matches = [p for p, _ in sorted(((p, p.stat().st_mtime) for p in matches), key=lambda t: (-t[1], t[0].name))]

    if verbose:
        print(f"Found {len(matches)} files using {'regex' if use_regex else 'glob'} pattern '{pattern}': {[p.name for p in matches]}")

    return matches


def bucket_files(files: list[Path], mode: str) -> DefaultDict[str, list[Path]]:
    buckets: DefaultDict[str, list[Path]] = defaultdict(list)
    for f in files:
        ts = datetime.fromtimestamp(f.stat().st_mtime)
        if mode == "hours":
            key = ts.strftime("%Y-%m-%d-%H")
        elif mode == "days":
            key = ts.strftime("%Y-%m-%d")
        elif mode == "weeks":
            year, week, _ = ts.isocalendar()
            key = f"{year}-W{week:02d}"
        elif mode == "months":
            key = ts.strftime("%Y-%m")
        elif mode == "years":
            key = str(ts.year)
        else:
            raise ValueError(f"invalid bucket mode: {mode}")
        buckets[key].append(f)
    return buckets


def process_buckets(to_keep: set[Path], mode: str, mode_count: int, buckets: DefaultDict[str, list[Path]], verbose: bool) -> None:
    sorted_keys = sorted(buckets.keys(), reverse=True)
    effective_count = mode_count
    current_count = 0
    while current_count < effective_count:
        if current_count >= len(sorted_keys):
            break  # No more buckets
        first_bucket_file = buckets[sorted_keys[current_count]][0]
        if first_bucket_file in to_keep:  # Already kept by previous mode
            effective_count += 1
        else:
            if verbose:
                print(
                    f"Keeping file '{first_bucket_file.name}': {mode} {current_count - (effective_count - mode_count) + 1}/{mode_count} "
                    f"(key: {sorted_keys[current_count]}, mtime: {datetime.fromtimestamp(first_bucket_file.stat().st_mtime)})"
                )
                for file_to_delete in buckets[sorted_keys[current_count]][1:]:
                    print(
                        f"NOT Keeping file '{file_to_delete.name}': {mode} "
                        f"(key: {sorted_keys[current_count]}, mtime: {datetime.fromtimestamp(first_bucket_file.stat().st_mtime)})"
                    )
            to_keep.add(first_bucket_file)  # keep the most recent file in the bucket
        current_count += 1


def delete_file(arguments: argparse.Namespace, file: Path) -> None:
    mtime = datetime.fromtimestamp(file.stat().st_mtime)
    if arguments.list_only:
        print(file.absolute(), end=arguments.list_only)
    else:
        if arguments.dry_run:
            print(f"DRY-RUN DELETE: {file.name} (mtime: {mtime})")
        else:
            file.unlink()
            if arguments.verbose:
                try:
                    print(f"DELETED: {file.name} (mtime: {mtime})")
                except IOError as e:
                    print("Error while deleting file:", e, file=sys.stderr)


def main() -> None:
    try:
        arguments = parse_arguments()
        existing_files: list[Path] = read_filelist(arguments.path, arguments.file_pattern, arguments.regex, arguments.verbose)
        to_keep: set[Path] = set()

        # Retention by time buckets
        for mode in ["hours", "days", "weeks", "months", "years"]:
            mode_count = getattr(arguments, mode)
            if mode_count:
                buckets = bucket_files(existing_files, mode)
                process_buckets(to_keep, mode, mode_count, buckets, arguments.verbose)

        # Keep last N files
        if arguments.last:
            last_files = existing_files[: arguments.last]
            if arguments.verbose:
                for index, file in enumerate(last_files, start=1):
                    if file not in to_keep:
                        print(f"Keeping file '{file.name}': last {index}/{arguments.last} (mtime: {datetime.fromtimestamp(file.stat().st_mtime)})")
            to_keep.update(last_files)

        # Delete files not to keep
        for file in existing_files:
            if file not in to_keep:
                delete_file(arguments, file)

    except IOError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except NoFilesFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(9)


if __name__ == "__main__":
    main()
