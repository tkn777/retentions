"""Symlink cleanup, with system-wide traversal restricted to temporary test roots."""

import sys
from pathlib import Path

import pytest

import retentions


@pytest.fixture
def backup_links(tmp_path, monkeypatch, symlinks_supported):
    if not symlinks_supported:
        pytest.skip("Symlinks not supported on this platform")
    base = tmp_path / "backups"
    links = base
    outside = tmp_path / "outside"
    links.mkdir(parents=True)
    outside.mkdir()
    (base / "backup.tar").write_text("backup")
    (base / "backup.sha256").write_text("checksum")
    (links / "latest.link").symlink_to("backup.tar")
    (links / "absolute.link").symlink_to(base / "backup.tar")
    (links / "chain.link").symlink_to("latest.link")
    (links / "checksum.link").symlink_to(base / "backup.sha256")
    (links / "broken.link").symlink_to(base / "missing")
    nested = base / "nested"
    nested.mkdir()
    (nested / "nested.link").symlink_to(base / "backup.tar")
    (outside / "external.link").symlink_to(base / "backup.tar")
    (base / "escape").symlink_to(outside, target_is_directory=True)
    (base / "alias").symlink_to(links, target_is_directory=True)
    (links / "loop").symlink_to(base, target_is_directory=True)
    monkeypatch.setattr(sys, "argv", ["retentions", str(base), "backup.tar", "--max-size", "1", "--delete-symlinks", "directory"])
    return base, links, outside


@pytest.mark.parametrize("protect", [False, True])
def test_delete_file_links_and_chains_inside_directory(backup_links, protect):
    base, links, outside = backup_links
    if protect:
        sys.argv.extend(["--protect", "*.link"])
    retentions.main()
    assert not (base / "backup.tar").exists()
    assert (outside / "external.link").is_symlink()
    assert (base / "nested" / "nested.link").is_symlink()
    assert (links / "checksum.link").is_symlink()
    assert (links / "broken.link").is_symlink()
    for name in ["latest.link", "absolute.link", "chain.link"]:
        assert not (links / name).is_symlink(), f"Link was not removed: {name}"


def test_delete_companion_links(backup_links):
    base, links, _ = backup_links
    (base / "backup.md5").write_text("checksum")
    (links / "md5.link").symlink_to(base / "backup.md5")
    sys.argv.extend(["--delete-companions", "suffix:.tar:.sha256,.md5", "suffix:.tar:.sha256"])
    retentions.main()
    assert not (base / "backup.tar").exists()
    assert not (base / "backup.sha256").exists()
    assert not (links / "checksum.link").is_symlink()
    assert not (base / "backup.md5").exists()
    assert not (links / "md5.link").is_symlink()


def test_dry_run_reports_links_without_deleting_them(backup_links, capsys):
    base, links, _ = backup_links
    sys.argv.append("--dry-run")
    retentions.main()
    assert (base / "backup.tar").exists()
    assert (links / "latest.link").is_symlink()
    output = capsys.readouterr().out
    assert "Dry-run" in output
    assert "latest.link" in output


@pytest.mark.parametrize("failed_name,retained_link,deleted_link", [("backup.tar", "latest.link", "checksum.link"), ("backup.sha256", "checksum.link", "latest.link")])
def test_cleanup_only_after_successful_target_deletion(backup_links, monkeypatch, capsys, failed_name, retained_link, deleted_link):
    base, links, _ = backup_links
    unlink = Path.unlink

    def failing_unlink(path, *args, **kwargs):
        if path == base / failed_name:
            raise PermissionError("simulated deletion failure")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    sys.argv.extend(["--delete-companions", "suffix:.tar:.sha256"])
    retentions.main()
    assert (base / failed_name).exists()
    assert (links / retained_link).is_symlink()
    assert "[ERROR]" in capsys.readouterr().err
    assert not (links / deleted_link).is_symlink()


def test_without_option_leaves_links_untouched(backup_links):
    base, links, _ = backup_links
    del sys.argv[-2:]
    retentions.main()
    assert not (base / "backup.tar").exists()
    assert all((links / name).is_symlink() for name in ["latest.link", "absolute.link", "chain.link"])


def test_system_search_removes_nested_and_external_links(backup_links, monkeypatch):
    base, links, outside = backup_links
    walk = retentions.os.walk
    searched_roots = []

    def local_walk(root, *args, **kwargs):
        searched_roots.append(Path(root))
        return walk(base.parent, *args, **kwargs)

    monkeypatch.setattr(retentions.os, "walk", local_walk)
    sys.argv[-1] = "system"
    retentions.main()
    assert searched_roots == [Path("/")]
    assert not (base / "backup.tar").exists()
    for link in [links / "latest.link", base / "nested" / "nested.link", outside / "external.link"]:
        assert not link.is_symlink()
    assert (links / "checksum.link").is_symlink()
    assert (base / "escape").is_symlink()


@pytest.mark.parametrize("fail_fast", [False, True])
def test_link_deletion_error(backup_links, monkeypatch, capsys, fail_fast):
    base, links, _ = backup_links
    failed = links / "latest.link"
    unlink = Path.unlink

    def failing_unlink(path, *args, **kwargs):
        if path == failed:
            raise PermissionError("simulated link deletion failure")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    if fail_fast:
        sys.argv.append("--fail-on-delete-error")
        with pytest.raises(SystemExit) as exc:
            retentions.main()
        assert exc.value.code == 1
    else:
        retentions.main()
    assert not (base / "backup.tar").exists()
    assert failed.is_symlink()
    error = capsys.readouterr().err
    assert "[ERROR]" in error and "latest.link" in error


@pytest.mark.parametrize("symlink_companion", [False, True])
def test_companion_protection_with_symlink_cleanup(backup_links, symlink_companion):
    base, links, _ = backup_links
    companion = base / "backup.sha256"
    if symlink_companion:
        companion.unlink()
        companion.symlink_to(base / "backup.tar")
    sys.argv.extend(["--delete-companions", "suffix:.tar:.sha256", "--protect", "*.sha256"])
    if symlink_companion:
        retentions.main()
        assert not companion.is_symlink()
        assert not (links / "checksum.link").is_symlink()
    else:
        with pytest.raises(SystemExit) as exc:
            retentions.main()
        assert exc.value.code == 7
        assert companion.read_text() == "checksum"
        assert (links / "checksum.link").is_symlink()
