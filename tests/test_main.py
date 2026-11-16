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


@pytest.mark.parametrize("rule_type", ["prefix", "suffix"])
@pytest.mark.parametrize("separator", [os.sep] + ([os.altsep] if os.altsep else []))
def test_invalid_companion_path_is_rejected_before_deletion(tmp_path, monkeypatch, capsys, rule_type, separator):
    newer = tmp_path / "new.txt"
    older = tmp_path / "old.tar"
    for file, age in [(newer, 100), (older, 200)]:
        file.write_text(file.name)
        os.utime(file, (retentions.SCRIPT_START - age, retentions.SCRIPT_START - age))
    match = "old" if rule_type == "prefix" else ".tar"
    rule = f"{rule_type}:{match}:..{separator}checksum"
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "*", "--max-age", "1", "--delete-companions", rule])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2
    assert newer.read_text() == "new.txt"
    assert older.read_text() == "old.tar"
    assert "must not contain path separators" in capsys.readouterr().err


@pytest.mark.parametrize("dry_run", [False, True])
def test_list_only_empty_separator_does_not_delete(tmp_path, monkeypatch, capsys, dry_run):
    file = tmp_path / "backup.txt"
    file.write_text("backup")
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "*.txt", "--max-size", "1", "--list-only", ""])
    if dry_run:
        sys.argv.append("--dry-run")

    main()

    assert file.exists()
    assert capsys.readouterr().out == str(file.absolute())


@pytest.mark.parametrize(
    "option, limit, size, delete",
    [
        ("--skip-by-filesize", "1.1K", 1126, True),
        ("--skip-by-filesize", "1.1K", 1127, False),
        ("--skip-by-filesize", "1126", 1126, False),
        ("--max-size", "1.1K", 1126, False),
        ("--max-size", "1.1K", 1127, True),
        ("--max-size", "1126", 1126, False),
    ],
)
@pytest.mark.parametrize("dry_run", [False, True])
def test_size_limits_round_in_the_correct_direction(tmp_path, monkeypatch, capsys, option, limit, size, delete, dry_run):
    file = tmp_path / "backup.tar"
    file.write_bytes(b"x" * size)
    argv = ["retentions.py", str(tmp_path), "*.tar", "--last", "1", option, limit, "--verbose", "INFO"]
    if dry_run:
        argv.append("--dry-run")
    monkeypatch.setattr(sys, "argv", argv)

    main()

    assert file.exists() == (dry_run or not delete)
    output = capsys.readouterr()
    assert "[ERROR]" not in output.err
    assert f"Total files to delete: {int(delete):03d}" in output.out


@pytest.mark.parametrize("successful_files", [0, 1])
def test_failed_deletion_is_not_counted_as_deleted(tmp_path, monkeypatch, capsys, successful_files):
    file = tmp_path / "backup.txt"
    file.write_text("backup")
    other = tmp_path / "other.txt"
    if successful_files:
        other.write_text("backup")
    original_unlink = retentions.Path.unlink

    def failing_unlink(path, *args, **kwargs):
        if path == file:
            raise PermissionError("simulated deletion failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(retentions.Path, "unlink", failing_unlink)
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "*.txt", "--max-size", "1", "--verbose", "INFO"])

    main()

    assert file.exists()
    assert not other.exists()
    output = capsys.readouterr()
    assert "[ERROR]" in output.err
    assert f"Total files to delete: {successful_files + 1:03d}" in output.out
    assert f"Total files deleted:   {successful_files:03d}" in output.out


def test_failed_folder_deletion_is_not_counted(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "backup-old"
    folder.mkdir()
    (folder / "backup.txt").write_text("backup")

    def failing_rmtree(path, *args, **kwargs):
        raise PermissionError("simulated deletion failure")

    monkeypatch.setattr(retentions.shutil, "rmtree", failing_rmtree)
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "backup-*", "--folder-mode", "folder", "--max-size", "1", "--verbose", "INFO"])

    main()

    assert (folder / "backup.txt").exists()
    output = capsys.readouterr()
    assert "[ERROR]" in output.err
    assert "Total folders to delete: 001" in output.out
    assert "Total folders deleted:   000" in output.out


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


@pytest.mark.parametrize("processing_error", [False, True])
@pytest.mark.parametrize("stacktrace", [False, True])
def test_lock_cleanup_error_preserves_exit_status(tmp_path, monkeypatch, capsys, processing_error, stacktrace):
    lock = tmp_path / LOCK_FILE_NAME
    original_unlink = retentions.Path.unlink

    def failing_unlink(path, *args, **kwargs):
        if path == lock:
            raise PermissionError("simulated lock cleanup failure")
        return original_unlink(path, *args, **kwargs)

    def fake_read_filelist(args, logger, cache):
        if processing_error:
            raise IntegrityCheckFailedError("simulated processing failure")
        return []

    monkeypatch.setattr(retentions.Path, "unlink", failing_unlink)
    monkeypatch.setattr(retentions, "read_filelist", fake_read_filelist)
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "*.txt", *(["--stacktrace"] if stacktrace else [])])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == (7 if processing_error else 1)
    assert lock.exists()
    error = capsys.readouterr().err
    assert "[ERROR]" in error
    assert "simulated lock cleanup failure" in error
    if processing_error:
        assert "simulated processing failure" in error
    assert ("Traceback (most recent call last)" in error) == stacktrace


def test_already_missing_lock_file_during_cleanup(tmp_path, monkeypatch):
    lock = tmp_path / LOCK_FILE_NAME

    def remove_lock(args, logger, cache):
        lock.unlink()
        return []

    monkeypatch.setattr(retentions, "read_filelist", remove_lock)
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "*.txt"])
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


@pytest.mark.parametrize("target_exists", [False, True])
@pytest.mark.parametrize("outside_base", [False, True])
def test_lock_file_symlink_aborts(tmp_path, monkeypatch, symlinks_supported, target_exists, outside_base):
    if not symlinks_supported:
        pytest.skip("Symlinks not supported on this platform")
    base = tmp_path / "base"
    base.mkdir()
    archive = base / "backup.tar"
    archive.write_text("backup")
    target = (tmp_path if outside_base else base) / "actual.lock"
    if target_exists:
        target.write_text("existing target")
    lock = base / LOCK_FILE_NAME
    lock.symlink_to(target)
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(base), "*", "--last", "1", "--skip-by-filesize", "1"])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 5
    assert lock.is_symlink()
    assert os.readlink(lock) == str(target)
    assert archive.read_text() == "backup"
    if target_exists:
        assert target.read_text() == "existing target"
    else:
        assert not target.exists()


def test_locking_with_base_directory_symlink(tmp_path, monkeypatch, symlinks_supported):
    if not symlinks_supported:
        pytest.skip("Symlinks not supported on this platform")
    base = tmp_path / "base"
    base.mkdir()
    link = tmp_path / "linked-base"
    link.symlink_to(base, target_is_directory=True)
    lock = base / LOCK_FILE_NAME
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(link), "*"])

    def check_lock(args, logger, cache):
        assert lock.is_file()
        return []

    monkeypatch.setattr(retentions, "read_filelist", check_lock)
    main()
    assert not lock.exists()
    assert link.is_symlink()


def test_lock_created_between_check_and_creation_aborts(tmp_path, monkeypatch):
    archive = tmp_path / "backup.txt"
    archive.write_text("backup")
    lock = tmp_path / LOCK_FILE_NAME
    original_touch = retentions.Path.touch

    def competing_touch(path, *args, **kwargs):
        if path == lock:
            lock.write_text("other process")
        return original_touch(path, *args, **kwargs)

    monkeypatch.setattr(retentions.Path, "touch", competing_touch)
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "*.txt", "--max-size", "1"])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 5
    assert archive.exists()
    assert lock.read_text() == "other process"


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


@pytest.mark.parametrize("is_companion", [False, True])
@pytest.mark.parametrize("regex_mode", ["casesensitive", "ignorecase"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_regex_protection_does_not_use_glob(tmp_path, monkeypatch, capsys, is_companion, regex_mode, dry_run):
    file = tmp_path / "backup.tar$"
    file.write_text("backup")
    file_pattern = r"^backup[.]tar\$$"
    argv = ["retentions.py", str(tmp_path), file_pattern, "--regex-mode", regex_mode, "--max-size", "1", "--protect", "backup[.]tar$", "--verbose", "INFO"]
    if is_companion:
        archive = tmp_path / "archive.tar"
        archive.write_text("archive")
        argv[2] = r"^archive[.]tar$"
        argv.extend(["--delete-companions", "prefix:archive.tar:backup.tar$"])
    if dry_run:
        argv.append("--dry-run")
    monkeypatch.setattr(sys, "argv", argv)

    main()

    assert file.exists() == dry_run
    if is_companion:
        assert archive.exists() == dry_run
    output = capsys.readouterr()
    assert "[ERROR]" not in output.err
    assert f"[INFO] {'Dry-run: ' if dry_run else ''}Total files deleted:   {2 if is_companion else 1:03d}" in output.out


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


def test_no_lock_file_preserves_lock_file_as_companion(tmp_path, monkeypatch, capsys):
    archive = tmp_path / "backup.tar"
    lock = tmp_path / LOCK_FILE_NAME
    archive.write_text("backup")
    lock.write_text("existing lock")
    monkeypatch.setattr(sys, "argv", ["retentions.py", str(tmp_path), "*.tar", "--max-size", "1", "--no-lock-file", "--delete-companions", f"prefix:backup.tar:{LOCK_FILE_NAME}"])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 7
    assert lock.read_text() == "existing lock"
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
