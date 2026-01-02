"""Tests for run_deletion and handle_exception functions."""

import os
from pathlib import Path

import pytest

from retentions import (
    ConfigNamespace,
    FileStatsCache,
    IntegrityCheckFailedError,
    Logger,
    LogLevel,
    handle_exception,
    run_deletion,
)


def _make_args(**overrides):
    defaults = dict(
        path="",
        age_type="mtime",
        list_only=None,
        dry_run=False,
        verbose=LogLevel.INFO,
    )
    defaults.update(overrides)
    return ConfigNamespace(**defaults)


def test_run_deletion_dry_run_and_real(tmp_path, capsys) -> None:
    """run_deletion should simulate deletion when dry_run is True and actually delete when False."""
    file_path = tmp_path / "to_delete.txt"
    file_path.write_text("data")
    cache = FileStatsCache("mtime")
    # Dry run: should not delete the file
    args = _make_args(path=str(tmp_path), dry_run=True)
    logger = Logger(args, cache)
    run_deletion(file_path, args, logger, cache)
    captured = capsys.readouterr()
    # Check that the file still exists and message contains 'DRY-RUN'
    assert file_path.exists()
    assert "DRY-RUN DELETE" in captured.out
    # Real deletion: should remove the file
    args.dry_run = False
    run_deletion(file_path, args, logger, cache)
    captured2 = capsys.readouterr()
    assert not file_path.exists()
    assert "DELETING" in captured2.out


def test_run_deletion_list_only(tmp_path, capsys) -> None:
    """In list_only mode run_deletion should print file paths separated by the given separator."""
    file_path = tmp_path / "list.txt"
    file_path.write_text("x")
    cache = FileStatsCache("mtime")
    args = _make_args(path=str(tmp_path), list_only="\0", dry_run=False)
    logger = Logger(args, cache)
    run_deletion(file_path, args, logger, cache)
    captured = capsys.readouterr()
    # Output should be on stdout (capsys.out) with the separator
    assert str(file_path.absolute()) + "\0" in captured.out
    # No deletion occurs so file remains
    assert file_path.exists()


def test_run_deletion_not_child(tmp_path) -> None:
    """run_deletion should raise if the file is not a child of the base directory."""
    # File outside of the specified path
    outer_file = tmp_path / "outer.txt"
    outer_file.write_text("1")
    cache = FileStatsCache("mtime")
    # Use a different base path
    args = _make_args(path=str(tmp_path / "other"), dry_run=False)
    logger = Logger(args, cache)
    with pytest.raises(IntegrityCheckFailedError):
        run_deletion(outer_file, args, logger, cache)


def test_handle_exception_exits_and_outputs(capsys) -> None:
    """handle_exception should print the message (and optionally stacktrace) and exit with the given code."""
    with pytest.raises(SystemExit) as exc:
        handle_exception(ValueError("boom"), exit_code=3, stacktrace=False)
    # SystemExit code should match
    assert exc.value.code == 3
    # Should have printed the error label and message to stderr
    captured = capsys.readouterr()
    assert "[ERROR]" in captured.err
    assert "boom" in captured.err


def test_warning_for_file_not_deleted(tmp_path, capsys, monkeypatch):
    protected = tmp_path / "protected.txt"
    normal = tmp_path / "normal.txt"

    protected.write_text("do not delete")
    normal.write_text("delete me")

    original_unlink = os.unlink

    def unlink_with_permission_error(path, *args, **kwargs):
        if Path(path).resolve() == protected.resolve():
            raise OSError("simulated permission error")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", unlink_with_permission_error)

    cache = FileStatsCache("mtime")
    args = _make_args(path=str(tmp_path), dry_run=False)
    logger = Logger(args, cache)

    # protected file triggers warning
    run_deletion(protected, args, logger, cache)
    assert protected.exists()

    err = capsys.readouterr().err
    assert "[WARN]" in err
    assert "Error while deleting file" in err
    assert protected.name in err

    # normal file is deleted
    run_deletion(normal, args, logger, cache)
    assert not normal.exists()

