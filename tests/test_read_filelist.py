"""Tests for the read_filelist function in the retentions module."""

import pytest

from retentions import (
    ConfigNamespace,
    FileStats,
    Logger,
    LogLevel,
    ModernStrictArgumentParser,
    read_filelist,
)


def _make_args(**overrides):
    """Helper to build a ConfigNamespace for read_filelist tests with sensible defaults."""
    defaults = dict(
        path="",
        file_pattern="",
        regex_mode=None,
        regex_compiled=None,
        protect=None,
        protect_compiled=None,
        protected_files=set(),
        age_type="ctime",
        list_only=None,
        verbose=LogLevel.ERROR,
        use_lock_file=False,
        hours=None,
        days=None,
        weeks=None,
        months=None,
        quarters=None,
        week13=None,
        years=None,
        last=None,
        max_size=None,
        max_size_bytes=None,
        max_files=None,
        max_age=None,
        max_age_seconds=None,
        dry_run=False,
    )
    defaults.update(overrides)
    return ConfigNamespace(**defaults)


def test_read_filelist_glob_and_protect(tmp_path) -> None:
    """read_filelist should match files using glob patterns and apply protection rules."""
    # Create files and a lock file
    f1 = tmp_path / "a.log"
    f2 = tmp_path / "b.log"
    f3 = tmp_path / "c.txt"
    lock = tmp_path / ".retentions.lock"
    for f in (f1, f2, f3, lock):
        f.write_text("x")

    args = _make_args(path=str(tmp_path), file_pattern="*.log", protect="b.log", verbose=LogLevel.INFO)
    cache = FileStats("ctime")
    logger = Logger(args, cache)

    result = read_filelist(args, logger, cache)
    # The lock file should be ignored and b.log protected, so only a.log should remain
    assert [p.name for p in result] == ["a.log"]


def test_read_filelist_regex_and_protect(tmp_path) -> None:
    """read_filelist should work in regex mode when regex_mode is provided."""
    f1 = tmp_path / "report1.txt"
    f2 = tmp_path / "data.dat"
    fp = tmp_path / "report2.txt"
    f1.write_text("1")
    f2.write_text("2")
    fp.write_text("protected")
    # Build regex to match names starting with 'report'
    args = _make_args(
        path=str(tmp_path),
        file_pattern=r"^report[0-9]+\.txt$",
        regex_mode="casesensitive",
        verbose=LogLevel.INFO,
        protect=r"^report[2-3]+\.txt$",
    )
    # Precompile pattern as parser would
    parser = ModernStrictArgumentParser()
    args.regex_compiled = parser._compile_regex(args.file_pattern, args.regex_mode)
    args.protect_compiled = parser._compile_regex(args.protect, args.regex_mode)
    cache = FileStats("ctime")
    logger = Logger(args, cache)
    result = read_filelist(args, logger, cache)
    assert result and result[0].name == "report1.txt"


def test_read_filelist_errors(tmp_path, capsys) -> None:
    """read_filelist should raise appropriate errors for invalid inputs."""
    cache = FileStats("mtime")
    # Path does not exist
    args = _make_args(path=str(tmp_path / "nonexistent"), file_pattern="*.txt")
    logger = Logger(args, cache)
    with pytest.raises(FileNotFoundError):
        read_filelist(args, logger, cache)
    # Path is not a directory
    file_path = tmp_path / "file"
    file_path.write_text("data")
    args = _make_args(path=str(file_path), file_pattern="*.txt")
    logger = Logger(args, cache)
    with pytest.raises(NotADirectoryError):
        read_filelist(args, logger, cache)
    # No files found
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    args = _make_args(path=str(empty_dir), file_pattern="*.doesnotexist", verbose=LogLevel.WARN)
    logger = Logger(args, cache)
    assert not read_filelist(args, logger, cache)
    out = capsys.readouterr().out
    assert "No files found in" in out
    # File not a direct child (in subdirectory)
    parent = tmp_path / "parent"
    child_dir = parent / "sub"
    child_dir.mkdir(parents=True)
    file_in_sub = child_dir / "f.txt"
    file_in_sub.write_text("x")
    args = _make_args(path=str(parent), file_pattern="**/*")
    logger = Logger(args, cache)
    with pytest.raises(ValueError):
        read_filelist(args, logger, cache)
