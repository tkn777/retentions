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


@pytest.fixture
def bounded_system_search(backup_links, monkeypatch):
    base, links, outside = backup_links
    walk = retentions.os.walk
    visits = []

    def local_path(*parts):
        return base if parts == ("/",) else Path(*parts)

    def bounded_walk(root, *args, **kwargs):
        assert Path(root) == base
        for directory, dirs, files in walk(root, *args, **kwargs):
            assert len(visits) < 30, "Directory traversal did not stop at symlink loops"
            visits.append((Path(directory), dirs))
            yield directory, dirs, files

    monkeypatch.setattr(retentions, "Path", local_path)
    monkeypatch.setattr(retentions.os, "walk", bounded_walk)
    sys.argv[-1] = "system"
    return base, links, outside, visits


@pytest.mark.parametrize("dry_run", [False, True])
def test_system_follows_directory_symlink_to_external_tree(bounded_system_search, dry_run, capsys):
    base, _, outside, visits = bounded_system_search
    if dry_run:
        sys.argv.append("--dry-run")
    args = retentions.parse_arguments()
    logger = retentions.Logger(args, retentions.FileStats("mtime"))
    args.symlink_paths = retentions.read_symlinks(args, [base / "backup.tar"], logger)
    retentions.run_deletion(base / "backup.tar", args, logger, set())
    assert (base / "backup.tar").exists() == dry_run
    assert (outside / "external.link").is_symlink() == dry_run
    assert (base / "escape").is_symlink()
    assert any(directory == base / "escape" for directory, _ in visits)
    assert not any(directory == outside for directory, _ in visits)
    if dry_run:
        assert "external.link" in capsys.readouterr().out


def test_system_stops_loops_and_indexes_each_link_once(bounded_system_search):
    base, links, outside, visits = bounded_system_search
    (base / "second-escape").symlink_to(outside, target_is_directory=True)
    args = retentions.parse_arguments()
    logger = retentions.Logger(args, retentions.FileStats("mtime"))
    found = retentions.read_symlinks(args, [base / "backup.tar"], logger)
    expected = {links / "latest.link", links / "absolute.link", links / "chain.link", base / "nested" / "nested.link", outside / "external.link"}
    captured = found[base / "backup.tar"]
    assert len(captured) == len(expected)
    assert {link.parent.resolve() / link.name for link in captured} == expected
    for alias in [base / "alias", base / "loop"]:
        assert any(directory == alias and not dirs for directory, dirs in visits)
    assert len(visits) < 30


@pytest.mark.parametrize("excluded", ["dev", "proc", "sys", "run"])
def test_system_exclusions_apply_through_directory_symlinks(bounded_system_search, excluded):
    base, _, _, visits = bounded_system_search
    hidden = base / excluded / "child"
    (hidden / "deeper").mkdir(parents=True)
    forbidden = hidden / "forbidden.link"
    forbidden.symlink_to(base / "backup.tar")
    (hidden / "deeper" / "also-forbidden.link").symlink_to(base / "backup.tar")
    alias = base / f"alias-{excluded}"
    alias.symlink_to(hidden, target_is_directory=True)
    args = retentions.parse_arguments()
    logger = retentions.Logger(args, retentions.FileStats("mtime"))
    found = retentions.read_symlinks(args, [base / "backup.tar"], logger)
    assert any(directory == alias and not dirs for directory, dirs in visits)
    assert not any(directory.is_relative_to(base / excluded) for directory, _ in visits)
    assert not any(directory.is_relative_to(alias / "deeper") for directory, _ in visits)
    assert all("forbidden" not in link.name for link in found[base / "backup.tar"])
    assert forbidden.is_symlink()
