# mypy: ignore-errors
"""Tests main function (only specific logic there, no function calls)."""

import sys

import pytest

import retentions
from retentions import LOCK_FILE_NAME, main


class DummyRetentionLogic:
    def __init__(self, *args, **kwargs):
        pass

    def process_retention_logic(self):
        class Result:
            keep = []
            prune = []

        return Result()


def test_create_lockfile(tmp_path, monkeypatch, capsys):
    """Test that lock file is created and removed on exit."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "*.txt"])

    lock = tmp_path / LOCK_FILE_NAME

    def fake_read_filelist(arg, logger, cache):
        assert lock.exists()
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
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "*.txt"])
    monkeypatch.setattr(retentions, "RetentionLogic", DummyRetentionLogic)
    monkeypatch.setattr(retentions, "read_filelist", lambda args, logger, cache: [])

    main()

    captured = capsys.readouterr()
    assert "Total files found" in captured.out
    assert "Total files keep" in captured.out
    assert "Total files prune" in captured.out
