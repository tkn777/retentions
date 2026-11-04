"""Tests for FileStatsCache and sorting helper functions."""

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from retentions import SCRIPT_START, FileStats, sort_files


def test_file_stats_cache_and_sort_files(tmp_path: Path) -> None:
    """FileStatsCache should cache file size and timestamps and sort by newest first."""
    # Create two files with different modification times and sizes
    file_new = tmp_path / "new.txt"
    file_old = tmp_path / "old.txt"
    file_new.write_text("new")
    file_old.write_text("old")

    # Set explicit modification times: old file is 60 seconds older
    now = time.time()
    old_time = now - 60
    os.utime(file_new, (now, now))
    os.utime(file_old, (old_time, old_time))

    cache = FileStats("mtime")
    # Check that the cache returns the correct timestamp and size
    assert cache.get_file_seconds(file_old) == int(old_time)
    assert cache.get_file_bytes(file_old) == len("old")

    # Sorting should return files with newest mtime first
    sorted_files = sort_files([file_old, file_new], cache)
    assert sorted_files == [file_new, file_old]


@pytest.mark.parametrize("names", [("b.txt", "a.txt"), ("a.txt", "b.txt")])
def test_sort_files_equal_timestamps_use_filename(tmp_path: Path, names: tuple[str, str]) -> None:
    files = [tmp_path / name for name in names]
    for file in files:
        file.write_text("x")
        os.utime(file, (SCRIPT_START, SCRIPT_START))

    stats = FileStats("mtime")
    expected = [tmp_path / "a.txt", tmp_path / "b.txt"]
    assert sort_files(files, stats) == expected
    assert sort_files(set(files), stats) == expected


def test_filestats_folder_mode_youngest_file_two_levels(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    sub = folder / "sub"

    sub.mkdir(parents=True)

    f_very_old = sub / "very_old.txt"
    f_old = sub / "old.txt"
    f_new = sub / "new.txt"

    f_very_old.write_text("very_old")
    f_old.write_text("old")
    f_new.write_text("new")

    now = SCRIPT_START
    os.utime(f_very_old, (now - 200_000, now - 200_000))
    os.utime(f_old, (now - 120, now - 120))
    os.utime(f_new, (now - 15, now - 15))

    stats = FileStats("mtime", folder_mode=True, folder_mode_time_src="youngest-file")

    # youngest file is in subdirectory, must still define folder age
    assert stats.get_file_seconds(folder) == now - 15


def test_filestats_folder_mode_oldest_file(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()

    f_old = folder / "old.txt"
    f_new = folder / "new.txt"

    f_old.write_text("old")
    f_new.write_text("new")

    now = SCRIPT_START
    os.utime(f_old, (now - 200, now - 200))
    os.utime(f_new, (now - 20, now - 20))

    stats = FileStats("mtime", folder_mode=True, folder_mode_time_src="oldest-file")

    assert stats.get_file_seconds(folder) == now - 200


def test_filestats_folder_mode_folder_time_src_folder(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    sub = folder / "sub"

    sub.mkdir(parents=True)

    f_old = sub / "old.txt"
    f_new = sub / "new.txt"

    f_old.write_text("old")
    f_new.write_text("new")

    now = SCRIPT_START

    # Dateien haben unterschiedliche mtimes
    os.utime(f_old, (now - 300, now - 300))
    os.utime(f_new, (now - 100, now - 100))

    # Folder-mtime explizit setzen (strukturelle Änderung simulieren)
    folder_mtime = now - 50
    os.utime(folder, (folder_mtime, folder_mtime))

    stats = FileStats(
        "mtime",
        folder_mode=True,
        folder_mode_time_src="folder",
    )

    # Entscheidend: Datei-mtimes dürfen keinen Einfluss haben
    assert stats.get_file_seconds(folder) == folder_mtime


def test_filestats_folder_mode_size_sum(tmp_path: Path) -> None:
    folder = tmp_path / "folder"

    sub_a = folder / "sub_a"
    sub_b = folder / "sub_b"

    sub_a.mkdir(parents=True)
    sub_b.mkdir(parents=True)

    f1 = folder / "root.bin"
    f2 = sub_a / "a.bin"
    f3 = sub_a / "b.bin"
    f4 = sub_b / "c.bin"

    f1.write_bytes(b"x" * 5)
    f2.write_bytes(b"x" * 10)
    f3.write_bytes(b"x" * 15)
    f4.write_bytes(b"x" * 20)

    stats = FileStats("mtime", folder_mode=True, folder_mode_time_src="youngest-file")

    assert stats.get_file_bytes(folder) == 50


@pytest.mark.parametrize("time_path", ["time.txt", "sub/time.txt", "sub/../time.txt"])
def test_filestats_folder_mode_path_time_source_valid(
    tmp_path: Path,
    monkeypatch,
    time_path,
) -> None:
    folder = tmp_path / "folder"
    sub = folder / "sub"
    folder.mkdir()
    sub.mkdir()

    (folder / "data.txt").write_text("x")

    # create time source files
    (folder / "time.txt").write_text("t")
    (sub / "time.txt").write_text("t")

    monkeypatch.chdir(tmp_path)

    time_file = folder / time_path
    ts = int(time_file.resolve().stat().st_mtime)

    stats = FileStats(
        age_type="mtime",
        folder_mode=True,
        folder_mode_time_src=f"path={time_path}",
    )

    result = stats.get_file_seconds(folder)

    assert result == ts


def test_filestats_folder_mode_path_time_source_is_directory(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()

    time_dir = folder / "time_dir"
    time_dir.mkdir()

    stats = FileStats(
        age_type="mtime",
        folder_mode=True,
        folder_mode_time_src=f"path={time_dir.name}",
    )

    with pytest.raises(ValueError, match="must be a file"):
        stats.get_file_seconds(folder)


def test_filestats_folder_mode_path_time_source_missing_file(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()

    missing = folder / "does_not_exist.txt"

    stats = FileStats(
        age_type="mtime",
        folder_mode=True,
        folder_mode_time_src=f"path={missing.name}",
    )

    with pytest.raises(ValueError, match="must be a file"):
        stats.get_file_seconds(folder)


def test_filestats_folder_mode_path_time_source_outside_folder(tmp_path: Path) -> None:
    # folder under retention
    folder = tmp_path / "folder"
    folder.mkdir()

    (folder / "data.txt").write_text("x")

    # time source file OUTSIDE the folder
    external_time_file = tmp_path / "external_time.txt"
    external_time_file.write_text("t")

    stats = FileStats(
        age_type="mtime",
        folder_mode=True,
        folder_mode_time_src=f"path=../{external_time_file.name}",
    )

    with pytest.raises(ValueError, match="must be inside the folder"):
        stats.get_file_seconds(folder)


def test_filestats_folder_mode_youngest_file_empty_folder_raises(tmp_path: Path) -> None:
    folder = tmp_path / "empty_folder"
    folder.mkdir()

    stats = FileStats(
        age_type="mtime",
        folder_mode=True,
        folder_mode_time_src="youngest-file",  # explicit, but also default
    )

    with pytest.raises(ValueError, match="contains no files"):
        stats.get_file_seconds(folder)


def test_filestats_rglob_does_not_follow_symlink_dirs(tmp_path: Path, symlinks_supported: bool) -> None:
    if not symlinks_supported:
        pytest.skip("Symlinks not supported on this platform")

    base = tmp_path / "base"
    base.mkdir()

    real = tmp_path / "real"
    real.mkdir()
    file_inside = real / "inside.txt"
    file_inside.write_text("x")

    link = base / "link"
    link.symlink_to(real)

    files = list(base.rglob("*"))

    # Symlink dir itself may appear
    assert link in files

    # But the file inside the symlink target must NOT
    assert file_inside not in files


def test_filestats_path_time_source_file_ok(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()

    time_file = folder / "time.txt"
    time_file.write_text("x")

    stats = FileStats(
        age_type="mtime",
        folder_mode=True,
        folder_mode_time_src=f"path={time_file.name}",
    )

    ts = stats.get_file_seconds(folder)
    assert isinstance(ts, int)


def test_filestats_path_time_source_not_a_file(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()

    subdir = folder / "subdir"
    subdir.mkdir()

    stats = FileStats(
        age_type="mtime",
        folder_mode=True,
        folder_mode_time_src=f"path={subdir.name}",
    )

    with pytest.raises(ValueError, match="must be a file"):
        stats.get_file_seconds(folder)


@pytest.mark.parametrize("inside", [False, True])
def test_filestats_path_time_source_symlink_is_resolved(tmp_path: Path, symlinks_supported: bool, inside) -> None:
    if not symlinks_supported:
        pytest.skip("Symlinks not supported on this platform")

    folder = tmp_path / "folder"
    folder.mkdir()

    real_file = (folder if inside else tmp_path) / "real.txt"
    real_file.write_text("x")

    link = folder / "time_link.txt"
    link.symlink_to(real_file)

    stats = FileStats(
        age_type="mtime",
        folder_mode=True,
        folder_mode_time_src=f"path={link.name}",
    )

    if inside:
        ts = stats.get_file_seconds(folder)
        assert isinstance(ts, int)
    else:
        with pytest.raises(ValueError, match="must be inside the folder"):
            stats.get_file_seconds(folder)


def test_filestats_path_time_source_outside_folder(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()

    external = tmp_path / "external.txt"
    external.write_text("x")

    stats = FileStats(
        age_type="mtime",
        folder_mode=True,
        folder_mode_time_src=f"path=../{external.name}",
    )

    with pytest.raises(ValueError, match="must be inside the folder"):
        stats.get_file_seconds(folder)


@pytest.mark.parametrize("inside", [False, True])
def test_filestats_path_time_source_rejects_absolute_paths(tmp_path: Path, inside) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()
    source = (folder if inside else tmp_path) / "time.txt"
    source.write_text("x")
    stats = FileStats("mtime", folder_mode=True, folder_mode_time_src=f"path={source}")

    with pytest.raises(ValueError, match="must be relative to the folder"):
        stats.get_file_seconds(folder)


@pytest.mark.skipif(os.name != "nt", reason="Windows rooted and drive-relative paths")
@pytest.mark.parametrize("time_path", [r"\time.txt", "C:time.txt"])
def test_filestats_path_time_source_rejects_windows_anchored_paths(tmp_path: Path, time_path) -> None:
    stats = FileStats("mtime", folder_mode=True, folder_mode_time_src=f"path={time_path}")

    with pytest.raises(ValueError, match="must be relative to the folder"):
        stats.get_file_seconds(tmp_path)


@pytest.mark.parametrize("age_type", ["mtime", "atime", "ctime", "birthtime"])
@pytest.mark.parametrize("time_source", [None, "folder", "path=time.txt", "youngest-file", "oldest-file"])
@pytest.mark.parametrize("seconds", [-1, -0.5, 0, 0.5])
def test_filestats_timestamp_epoch_boundary(tmp_path: Path, monkeypatch, age_type, time_source, seconds) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()
    source = folder / "time.txt"
    source.write_text("x")
    if time_source == "folder":
        source = folder
    original_stat = Path.stat

    def source_stat(path, *args, **kwargs):
        result = original_stat(path, *args, **kwargs)
        if path == source:
            return SimpleNamespace(st_mode=result.st_mode, **{f"st_{age_type}": seconds})
        return result

    monkeypatch.setattr(Path, "stat", source_stat)
    stats = FileStats(age_type, folder_mode=time_source is not None, folder_mode_time_src=time_source)
    target = source if time_source is None else folder
    if seconds < 0:
        with pytest.raises(ValueError, match="before 1970-01-01 00:00:00 UTC") as exc:
            stats.get_file_seconds(target)
        assert str(target) in str(exc.value)
        assert age_type in str(exc.value)
    else:
        assert stats.get_file_seconds(target) == int(seconds)
