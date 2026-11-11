# mypy: ignore-errors
"""Tests main function (only specific logic there, no function calls)."""

import argparse
import os
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
    assert "Total files to retain" in captured.out
    assert "Total files to delete" in captured.out


@pytest.mark.parametrize(
    "file_pattern,protect,regex_mode",
    [
        ("*.tar", "*.sha256", None),
        (r"^.*\.tar$", r"^archive\.sha256$", "casesensitive"),
        (r"^.*\.tar$", r"^ARCHIVE\.SHA256$", "ignorecase"),
    ],
)
@pytest.mark.parametrize("dry_run", [False, True])
def test_protected_companion_outside_file_pattern(tmp_path, monkeypatch, capsys, file_pattern, protect, regex_mode, dry_run):
    archive = tmp_path / "archive.tar"
    companion = tmp_path / "archive.sha256"
    archive.write_text("backup")
    companion.write_text("protected checksum")
    argv = ["retentions.py", str(tmp_path), file_pattern, "--max-size", "1", "--protect", protect, "--delete-companions", "suffix:.tar:.sha256"]
    if regex_mode:
        argv.extend(["--regex-mode", regex_mode])
    if dry_run:
        argv.append("--dry-run")
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 7
    assert companion.read_text() == "protected checksum"
    assert archive.exists() == dry_run
    assert not (tmp_path / LOCK_FILE_NAME).exists()
    assert "must not be deleted" in capsys.readouterr().err


def test_no_lock_file_keeps_disallowed_companion_protection(tmp_path, monkeypatch, capsys):
    archive = tmp_path / "archive.tar"
    companion = tmp_path / "archive.keep"
    archive.write_text("old archive")
    companion.write_text("kept companion")
    os.utime(archive, (1_000_000_000, 1_000_000_000))
    os.utime(companion, (1_700_000_000, 1_700_000_000))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "retentions.py",
            str(tmp_path),
            "*",
            "--last",
            "1",
            "--no-lock-file",
            "--delete-companions",
            "suffix:.tar:.keep",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 7
    assert companion.exists()
    assert "must not be deleted" in capsys.readouterr().err


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


@pytest.mark.parametrize("dry_run", [False, True])
def test_folder_time_source_is_relative_to_each_folder(tmp_path, monkeypatch, dry_run):
    base = tmp_path / "backups"
    old = base / "backup-old"
    new = base / "backup-new"
    for folder, timestamp in [(old, 1_600_000_000), (new, 1_700_000_000)]:
        (folder / "sub").mkdir(parents=True)
        source = folder / "sub" / "text.txt"
        source.write_text("backup")
        os.utime(source, (timestamp, timestamp))
    os.utime(old, (1_700_000_000, 1_700_000_000))
    os.utime(new, (1_600_000_000, 1_600_000_000))
    monkeypatch.chdir(tmp_path)
    argv = ["retentions.py", str(base), "backup-*", "--folder-mode", "path=sub/text.txt", "--last", "1"]
    if dry_run:
        argv.append("--dry-run")
    monkeypatch.setattr(sys, "argv", argv)

    main()

    assert old.exists() == dry_run
    assert new.exists()
    assert not (base / LOCK_FILE_NAME).exists()


@pytest.mark.parametrize(
    "source_kind,message",
    [("absolute", "must be relative to the folder"), ("outside", "must be inside the folder"), ("missing", "must be a file"), ("directory", "must be a file")],
)
def test_invalid_folder_time_source_aborts_before_deletion(tmp_path, monkeypatch, capsys, source_kind, message):
    good = tmp_path / "backup-good"
    bad = tmp_path / "backup-bad"
    for folder in [good, bad]:
        folder.mkdir()
        (folder / "data.txt").write_text("backup")
    source = good / "time.txt"
    source.write_text("time source")
    time_path = "time.txt"
    if source_kind == "absolute":
        time_path = str(source)
    elif source_kind == "outside":
        time_path = "../external.txt"
        (tmp_path / "external.txt").write_text("external")
    elif source_kind == "directory":
        (bad / "time.txt").mkdir()
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "backup-*", "--folder-mode", f"path={time_path}", "--last", "1"])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2
    assert (good / "data.txt").exists()
    assert (bad / "data.txt").exists()
    assert not (tmp_path / LOCK_FILE_NAME).exists()
    output = capsys.readouterr()
    assert "[ERROR]" in output.err
    assert message in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize("time_source", [None, "folder", "path=time.txt", "youngest-file", "oldest-file"])
@pytest.mark.parametrize("seconds", [-1, -0.5])
def test_pre_epoch_timestamp_participates_in_retention(tmp_path, monkeypatch, capsys, time_source, seconds):
    old = tmp_path / "backup-old"
    new = tmp_path / "backup-new"
    sources = []
    for target in [old, new]:
        if time_source is None:
            target.write_text("backup")
            sources.append(target)
        else:
            target.mkdir()
            source = target / "time.txt"
            source.write_text("backup")
            sources.append(target if time_source == "folder" else source)
    os.utime(sources[0], (seconds, seconds))
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "backup-*", "--last", "1", "--verbose", "DEBUG", *(["--folder-mode", time_source] if time_source is not None else [])])

    main()

    assert not old.exists()
    assert new.exists()
    assert not (tmp_path / LOCK_FILE_NAME).exists()
    output = capsys.readouterr()
    assert output.err == ""
    assert "backup-old" in output.out
    assert "Pruning: not matched by any retention rule" in output.out
