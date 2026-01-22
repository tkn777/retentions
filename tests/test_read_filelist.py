"""Tests for the read_filelist function in the retentions module."""

from pathlib import Path

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
        folder_mode=None,
        entity_name="file",
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
    with pytest.raises(NotADirectoryError):
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


def test_read_filelist_folder_mode_top_level_only(tmp_path: Path) -> None:
    folder1 = tmp_path / "folder1"
    folder2 = tmp_path / "folder2"
    file1 = tmp_path / "file.txt"

    folder1.mkdir()
    folder2.mkdir()
    file1.write_text("nope")

    (folder1 / "a.txt").write_text("x")
    (folder2 / "b.txt").write_text("y")

    args = _make_args(
        path=str(tmp_path),
        file_pattern="*",
        folder_mode=True,
        verbose=LogLevel.INFO,
        entity_name="folder",
    )

    cache = FileStats("mtime", folder_mode=True, folder_mode_time_src="youngest-file")
    logger = Logger(args, cache)

    result = read_filelist(args, logger, cache)

    names = {p.name for p in result}
    assert names == {"folder1", "folder2"}


def test_read_filelist_folder_mode_ignores_empty_folders(tmp_path: Path, capsys) -> None:
    blank = tmp_path / "blank"
    full = tmp_path / "full"

    full.mkdir()
    (full / "file.txt").write_text("x")
    blank.mkdir()

    args = _make_args(
        path=str(tmp_path),
        file_pattern="*",
        folder_mode=True,
        verbose=LogLevel.WARN,
        entity_name="folder",
    )

    cache = FileStats("mtime", folder_mode=True, folder_mode_time_src="youngest-file")
    logger = Logger(args, cache)

    result = read_filelist(args, logger, cache)

    assert [p.name for p in result] == ["full"]

    out = capsys.readouterr().out
    assert "blank' is empty -> It is ignored" in out
    assert "is empty -> It is ignored" in out
    assert "blank" in out
    assert "[WARN] " in out


def test_read_filelist_base_symlink_is_resolved(tmp_path: Path, symlinks_supported: bool) -> None:
    if not symlinks_supported:
        pytest.skip("Symlinks not supported on this platform")

    real = tmp_path / "real_dir"
    real.mkdir()

    base_link = tmp_path / "base_link"
    base_link.symlink_to(real)

    args = _make_args(path=str(base_link), file_pattern="*")

    file_stats = FileStats("mtime")
    logger = Logger(args, file_stats)

    result = read_filelist(args, logger, file_stats)

    # behaves exactly like the real directory
    assert isinstance(result, list)


def test_read_filelist_ignores_symlink_files(tmp_path: Path, symlinks_supported: bool) -> None:
    if not symlinks_supported:
        pytest.skip("Symlinks not supported on this platform")

    real = tmp_path / "real.txt"
    real.write_text("x")

    link = tmp_path / "link.txt"
    link.symlink_to(real)

    args = _make_args(path=str(tmp_path), file_pattern="*")

    cache = FileStats("mtime")
    logger = Logger(args, cache)

    result = read_filelist(args, logger, cache)
    names = {p.name for p in result}

    assert "real.txt" in names
    assert "link.txt" not in names


def test_read_filelist_folder_mode_ignores_symlink_folders(tmp_path: Path, symlinks_supported: bool) -> None:
    if not symlinks_supported:
        pytest.skip("Symlinks not supported on this platform")

    base = tmp_path / "base_dir"
    base.mkdir()

    real = tmp_path / "real_folder"
    real.mkdir()

    link = base / "folder_symlink"
    link.symlink_to(real)

    args = _make_args(
        path=str(base),
        file_pattern="*",
        folder_mode="folder",
    )

    file_stats = FileStats("mtime", folder_mode=True)
    logger = Logger(args, file_stats)

    result = read_filelist(args, logger, file_stats)

    assert link not in result
