"""Tests for FileStatsCache and sorting helper functions."""

import os
import time
from pathlib import Path

from retentions import FileStatsCache, sort_files


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

    cache = FileStatsCache("mtime")
    # Check that the cache returns the correct timestamp and size
    assert cache.get_file_seconds(file_old) == int(old_time)
    assert cache.get_file_bytes(file_old) == len("old")

    # Sorting should return files with newest mtime first
    sorted_files = sort_files([file_old, file_new], cache)
    assert sorted_files == [file_new, file_old]
