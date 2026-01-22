# mypy: ignore-errors
"""Tests for run_deletion and handle_exception functions."""

from pathlib import Path

import pytest

import retentions
from retentions import ConfigNamespace, FileCouldNotBeDeleteError, FileStats, IntegrityCheckFailedError, Logger, LogLevel, handle_exception, run_deletion


def _make_args(**overrides):
    defaults = dict(
        path="",
        age_type="mtime",
        list_only=None,
        dry_run=False,
        verbose=LogLevel.INFO,
        fail_on_delete_error=False,
        protected_files=set(),
        delete_companion_set=set(),
        entity_name="file",
        folder_mode=False,
    )
    defaults.update(overrides)
    return ConfigNamespace(**defaults)


def test_run_deletion_dry_run_and_real(tmp_path, capsys) -> None:
    """run_deletion should simulate deletion when dry_run is True and actually delete when False."""
    file_path = tmp_path / "to_delete.txt"
    file_path.write_text("data")
    cache = FileStats("mtime")
    # Dry run: should not delete the file
    args = _make_args(path=str(tmp_path), dry_run=True)
    logger = Logger(args, cache)
    run_deletion(file_path, args, logger, set())
    captured = capsys.readouterr()
    # Check that the file still exists and message contains 'DRY-RUN'
    assert file_path.exists()
    assert "DRY-RUN DELETE" in captured.out
    # Real deletion: should remove the file
    args.dry_run = False
    run_deletion(file_path, args, logger, set())
    captured2 = capsys.readouterr()
    assert not file_path.exists()
    assert "DELETING" in captured2.out


def test_run_deletion_list_only(tmp_path, capsys) -> None:
    """In list_only mode run_deletion should print file paths separated by the given separator."""
    file_path = tmp_path / "list.txt"
    file_path.write_text("x")
    cache = FileStats("mtime")
    args = _make_args(path=str(tmp_path), list_only="\0", dry_run=False)
    logger = Logger(args, cache)
    run_deletion(file_path, args, logger, set())
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
    cache = FileStats("mtime")
    # Use a different base path
    args = _make_args(path=str(tmp_path / "other"), dry_run=False)
    logger = Logger(args, cache)
    with pytest.raises(IntegrityCheckFailedError):
        run_deletion(outer_file, args, logger, set())


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

    original_unlink = retentions.Path.unlink  # <<< WICHTIG

    def unlink_with_permission_error(self, *args, **kwargs):
        if self == protected:
            raise OSError("simulated permission error")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(retentions.Path, "unlink", unlink_with_permission_error)

    cache = FileStats("mtime")
    args = _make_args(path=str(tmp_path), dry_run=False)
    logger = Logger(args, cache)

    # protected file triggers warning
    run_deletion(protected, args, logger, set())
    assert protected.exists()

    err = capsys.readouterr().err
    assert "[WARN]" in err
    assert "Error while deleting file" in err
    assert protected.name in err

    # normal file is deleted
    run_deletion(normal, args, logger, set())
    assert not normal.exists()


def test_exception_for_file_not_deleted(tmp_path, capsys, monkeypatch):
    protected = tmp_path / "protected.txt"
    normal = tmp_path / "normal.txt"

    protected.write_text("do not delete")
    normal.write_text("delete me")

    original_unlink = retentions.Path.unlink

    def unlink_with_permission_error(self, *args, **kwargs):
        if self == protected:
            raise OSError("simulated permission error")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(retentions.Path, "unlink", unlink_with_permission_error)

    cache = FileStats("mtime")
    args = _make_args(path=str(tmp_path), dry_run=False, fail_on_delete_error=True)
    logger = Logger(args, cache)

    # protected file triggers warning
    with pytest.raises(FileCouldNotBeDeleteError) as exc:
        run_deletion(protected, args, logger, set())
    assert "Error while deleting file" in str(exc)
    assert "protected.txt" in str(exc)
    assert protected.exists()
    assert normal.exists()


class _DummyCompanionRule:
    """Minimal stub for CompanionRule to test run_deletion companion handling."""

    def __init__(self, companion: Path):
        self._companion = companion

    def matches(self, file: Path) -> bool:  # noqa: ARG002
        return True

    def replace(self, file: Path) -> Path:  # noqa: ARG002
        return self._companion


def test_run_deletion_with_companion_deleted(tmp_path, capsys) -> None:
    main = tmp_path / "data.tar"
    companion = tmp_path / "data.tar.md5"

    main.write_text("main")
    companion.write_text("companion")

    cache = FileStats("mtime")
    args = _make_args(
        path=str(tmp_path),
        dry_run=False,
        delete_companion_set={_DummyCompanionRule(companion)},
    )
    logger = Logger(args, cache)

    disallowed_companions = set()

    run_deletion(main, args, logger, disallowed_companions)

    assert not main.exists()
    assert not companion.exists()

    out = capsys.readouterr().out
    assert "DELETING" in out
    assert "DELETING (COMPANION)" in out
    assert main.name in out
    assert companion.name in out


def test_run_deletion_with_missing_companion(tmp_path) -> None:
    main = tmp_path / "data.tar"
    missing_companion = tmp_path / "data.tar.md5"

    main.write_text("main")

    cache = FileStats("mtime")
    args = _make_args(
        path=str(tmp_path),
        dry_run=False,
        delete_companion_set={_DummyCompanionRule(missing_companion)},
    )
    logger = Logger(args, cache)

    disallowed_companions = set()

    run_deletion(main, args, logger, disallowed_companions)

    assert not main.exists()
    assert not missing_companion.exists()  # still missing, no error


def test_run_deletion_with_disallowed_companion(tmp_path) -> None:
    main = tmp_path / "data.tar"
    companion = tmp_path / "data.tar.md5"

    main.write_text("main")
    companion.write_text("companion")

    cache = FileStats("mtime")
    args = _make_args(
        path=str(tmp_path),
        dry_run=False,
        delete_companion_set={_DummyCompanionRule(companion)},
    )
    logger = Logger(args, cache)

    disallowed_companions = {companion}

    with pytest.raises(IntegrityCheckFailedError) as e:
        run_deletion(main, args, logger, disallowed_companions)
    assert "must not be deleted" in str(e.value)

    # Companion must not be deleted
    assert companion.exists()


def test_run_deletion_multiple_files_multiple_companions(tmp_path, capsys) -> None:
    # main files
    file_a = tmp_path / "a.tar"
    file_b = tmp_path / "b.tar"

    # companions
    a_md5 = tmp_path / "a.tar.md5"
    a_info = tmp_path / "a.tar.info"
    b_md5 = tmp_path / "b.tar.md5"
    b_info = tmp_path / "b.tar.info"

    for p in [file_a, file_b, a_md5, a_info, b_md5, b_info]:
        p.write_text(p.name)

    # two companion rules, both always matching
    rule_md5 = _DummyCompanionRule(None)
    rule_info = _DummyCompanionRule(None)

    def replace_md5(file: Path) -> Path:
        return file.with_name(file.name + ".md5")

    def replace_info(file: Path) -> Path:
        return file.with_name(file.name + ".info")

    rule_md5.replace = replace_md5
    rule_info.replace = replace_info

    cache = FileStats("mtime")
    args = _make_args(
        path=str(tmp_path),
        dry_run=False,
        delete_companion_set={rule_md5, rule_info},
    )
    logger = Logger(args, cache)

    disallowed_companions = set()

    # delete first file
    run_deletion(file_a, args, logger, disallowed_companions)

    # delete second file
    run_deletion(file_b, args, logger, disallowed_companions)

    # main files deleted
    assert not file_a.exists()
    assert not file_b.exists()

    # all companions deleted
    assert not a_md5.exists()
    assert not a_info.exists()
    assert not b_md5.exists()
    assert not b_info.exists()

    out = capsys.readouterr().out
    assert "DELETING" in out


def test_folder_mode_deletes_directories(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()

    folder = base / "old_folder"
    sub = folder / "sub"
    sub.mkdir(parents=True)

    f = sub / "file.txt"
    f.write_text("data")

    assert folder.exists()
    assert folder.is_dir()
    assert sub.exists()
    assert sub.is_dir()
    assert f.exists()
    assert f.is_file()

    args = _make_args(
        path=str(base),
        folder_mode=True,
        dry_run=False,
    )

    cache = FileStats("mtime", folder_mode=True)
    logger = Logger(args, cache)

    # execute deletion
    run_deletion(folder, args, logger, set())

    # this is the actual regression assertion
    assert not folder.exists()
