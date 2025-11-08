import argparse
import re
from pathlib import Path

VERSION: str = "1.0.0"


def positive_int(value: str) -> int:
    try:
        ivalue = int(value)
        if ivalue <= 0:
            raise ValueError
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid value '{value}': must be an integer > 0")
    return ivalue


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="retentions",
        usage=("retentions path file_pattern [options]\n\nExample:\n  retentions /data/backups '*.tar.gz' -d 7 -w 4 -m 6\n \n"),
        description=("A minimal cross-platform CLI tool for file retention management"),
        epilog="Use with caution!! This tool deletes files unless --dry-run or --list-only is set.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # positional arguments
    parser.add_argument("path", help="Base directory to scan")
    parser.add_argument("file_pattern", help="Regex or glob pattern for matching files (use quotes to prevent shell expansion)")

    # optional retention arguments (validated, no defaults)
    parser.add_argument("-H", "--hours", type=positive_int, metavar="N", help="Keep one file per hour from the last N hours")
    parser.add_argument("-d", "--days", type=positive_int, metavar="N", help="Keep one file per day from the last N days")
    parser.add_argument("-w", "--weeks", type=positive_int, metavar="N", help="Keep one file per week from the last N weeks")
    parser.add_argument("-m", "--months", type=positive_int, metavar="N", help="Keep one file per month from the last N months")
    parser.add_argument("-y", "--years", type=positive_int, metavar="N", help="Keep one file per year from the last N years")
    parser.add_argument("-l", "--last", type=positive_int, metavar="N", help="Always keep the N most recently modified files")

    # mode flags
    parser.add_argument("-X", "--dry-run", action="store_true", help="Show planned actions but do not delete any files")
    parser.add_argument("-L", "--list-only", action="store_true", help="Output only file paths that would be deleted (incompatible with --verbose)")
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

    if args.verbose:
        print(f"Using arguments: {vars(args)}")

    return args


def read_filelist(base_path: str, pattern: str, verbose: bool) -> list[Path]:
    base = Path(base_path)
    matches: list[Path] = []
    used_regex: bool = False

    if not base.exists():
        raise FileNotFoundError(f"path not found: {base}")
    if not base.is_dir():
        raise NotADirectoryError(f"path is not a directory: {base}")

    # pattern is a regex
    if re.search(r"[\\\[\]\(\)\{\}\+\?\|]", pattern):
        used_regex = True
        pattern_compiled = re.compile(pattern)
        for file in base.iterdir():
            if file.is_file() and pattern_compiled.match(file.name):
                matches.append(file)
    # pattern is a glob
    else:
        matches = [f for f in base.glob("*") if f.is_file()]

    if verbose:
        print(f"Found files: {[p.name for p in matches]} using {'regex' if used_regex else 'glob'} pattern '{pattern}'")

    return matches


def main() -> None:
    arguments = parse_arguments()
    read_filelist(arguments.path, arguments.file_pattern, arguments.verbose)


if __name__ == "__main__":
    main()
