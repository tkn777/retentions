# mypy: ignore-errors
"""Tests main function (only specific logic there, no function calls)."""

import argparse
import sys

import pytest

import retentions
from retentions import LOCK_FILE_NAME, ConcurrencyError, IntegrityCheckFailedError, main, parse_arguments


class DummyRetentionLogic:
    def __init__(self, *args, **kwargs):
        pass

    def process_retention_logic(self):
        class Result:
            keep = set()
            prune = set()

        return Result()


def test_create_lockfile(tmp_path, monkeypatch, capsys):
    """Test that lock file is created and removed on exit."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "*.txt"])

    lock = tmp_path / LOCK_FILE_NAME

    def fake_read_filelist(args, logger, cache):
        assert lock.exists()
        args.protected_files = set()
        return []

    monkeypatch.setattr(retentions, "RetentionLogic", DummyRetentionLogic)
    monkeypatch.setattr(retentions, "read_filelist", fake_read_filelist)

    main()

    assert not lock.exists()


def test_create_no_lockfile(tmp_path, monkeypatch, capsys):
    """Test that no lock file is created."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "*.txt", "--no-lock-file"])

    lock = tmp_path / LOCK_FILE_NAME

    def fake_read_filelist(args, logger, cache):
        assert not lock.exists()
        args.protected_files = set()
        return []

    monkeypatch.setattr(retentions, "RetentionLogic", DummyRetentionLogic)
    monkeypatch.setattr(retentions, "read_filelist", fake_read_filelist)

    main()

    assert not lock.exists()


def test_fail_on_existing_lock_file(tmp_path, monkeypatch, capsys):
    """Test failing, if lock file exists."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "*.txt"])

    lock = tmp_path / LOCK_FILE_NAME
    lock.write_text("x")

    monkeypatch.setattr(retentions, "RetentionLogic", DummyRetentionLogic)
    monkeypatch.setattr(retentions, "read_filelist", lambda args, logger, cache: [])

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 5  # ConcurrencyError

    assert lock.exists()


def test_output_help(tmp_path, monkeypatch, capsys):
    """Test that output is printed."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "*.txt", "-V", "debug"])
    monkeypatch.setattr(retentions, "RetentionLogic", DummyRetentionLogic)

    def fake_read_filelist(args, logger, cache):
        args.protected_files = set()
        return []

    monkeypatch.setattr(retentions, "read_filelist", fake_read_filelist)

    main()

    captured = capsys.readouterr()
    assert "Parsed arguments" in captured.out
    assert "Total files found" in captured.out
    assert "Total files protected" in captured.out
    assert "Total files to keep" in captured.out
    assert "Total files to prune" in captured.out


@pytest.mark.parametrize(
    "exception, exit_code",
    [
        (OSError, 1),
        (ValueError, 2),
        (argparse.ArgumentTypeError, 2),
        (ConcurrencyError, 5),
        (IntegrityCheckFailedError, 7),
        (Exception, 9),
    ],
)
def test_exception_handling(monkeypatch, tmp_path, exception, exit_code):
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "*.txt", "-V", "debug"])

    original = main

    def failing_main_wrapper(*args, **kwargs):
        args = parse_arguments()
        raise exception
        return original(*args, **kwargs)

    def asserting_handle_exception(exception: Exception, exit_code: int, stacktrace: bool, prefix: str = ""):
        assert exception == exception
        assert exit_code == exit_code

    monkeypatch.setattr(sys.modules[__name__], "main", failing_main_wrapper)
    monkeypatch.setattr(retentions, "handle_exception", asserting_handle_exception)

    with pytest.raises(exception):
        main()
