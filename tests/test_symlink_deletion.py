"""Behavior expected from --delete-symlinks; intentionally red until implemented."""

import sys
from pathlib import Path

import pytest

import retentions


@pytest.fixture
def backup_links(tmp_path, monkeypatch, symlinks_supported):
    if not symlinks_supported:
        pytest.skip("Symlinks not supported on this platform")
    base = tmp_path / "backups"
    links = base / "links"
    outside = tmp_path / "outside"
    links.mkdir(parents=True)
    outside.mkdir()
    (base / "backup.tar").write_text("backup")
    (base / "backup.sha256").write_text("checksum")
    (links / "latest.link").symlink_to(Path("..") / "backup.tar")
    (links / "absolute.link").symlink_to(base / "backup.tar")
    (links / "chain.link").symlink_to("latest.link")
    (links / "checksum.link").symlink_to(base / "backup.sha256")
    (links / "broken.link").symlink_to(base / "missing")
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
    assert (links / "checksum.link").is_symlink()
    assert (links / "broken.link").is_symlink()
    for name in ["latest.link", "absolute.link", "chain.link"]:
        assert not (links / name).is_symlink(), f"Link was not removed: {name}"


def test_delete_companion_links(backup_links):
    base, links, _ = backup_links
    sys.argv.extend(["--delete-companions", "suffix:.tar:.sha256"])
    retentions.main()
    assert not (base / "backup.tar").exists()
    assert not (base / "backup.sha256").exists()
    assert not (links / "checksum.link").is_symlink()


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
