"""Tests for the RetentionLogic class."""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, no_type_check

from retentions import SCRIPT_START, ConfigNamespace, FileStats, Logger, LogLevel, RetentionLogic


@no_type_check
def _make_args(**overrides) -> ConfigNamespace:  # noqa: F821
    """Helper to build a ConfigNamespace with defaults suitable for retention logic."""
    defaults = dict(
        path="",
        file_pattern="*",
        regex_mode=None,
        regex_compiled=None,
        protect=None,
        protect_compiled=None,
        age_type="mtime",
        list_only=None,
        verbose=LogLevel.ERROR,
        use_lock_file=False,
        minutes=None,
        hours=None,
        days=None,
        weeks=None,
        months=None,
        quarters=None,
        week13=None,
        years=None,
        last=None,
        max_size=None,
        max_size_bytes=None,
        max_files=None,
        max_age=None,
        max_age_seconds=None,
        dry_run=False,
        entity_name="file",
    )
    defaults.update(overrides)
    return ConfigNamespace(**defaults)


def _create_files_with_times(tmp_path: Path, offsets: list[int], mod_time: Optional[int] = None) -> list[Path]:
    base_time = SCRIPT_START if mod_time is None else mod_time
    files: list[Path] = []
    for idx, offset in enumerate(offsets):
        f = tmp_path / f"file{idx}.txt"
        f.write_text(str(idx))
        ts = base_time - offset
        os.utime(f, (ts, ts))
        files.append(f)
    return files


@no_type_check
def test_hours_retention(tmp_path: Path) -> None:
    """When hours retention is specified, one file should be kept per hour for the newest N hours."""
    # Create three files spaced an hour apart: newest first
    files = _create_files_with_times(tmp_path, offsets=[0, 1, 3600, 2 * 3600])  # 0 and 3500 => same bucket (hour)
    args = _make_args(hours=2, verbose=LogLevel.DEBUG)
    cache = FileStats("mtime")
    logger = Logger(args, cache)
    logic = RetentionLogic(files, args, logger, cache)
    result = logic.process_retention_logic()
    # Expect to keep 2 files (newest two hours) and prune the oldest
    assert len(result.keep) == 2
    assert len(result.prune) == 2
    # The kept files should be the two most recently modified files
    logger.print_decisions()
    kept_names = {f.name for f in result.keep}
    expected_kept = {files[0].name, files[2].name}
    assert kept_names == expected_kept


@no_type_check
def test_multiple_retention_modes(tmp_path: Path) -> None:
    """RetentionLogic should apply multiple modes sequentially and honour the 'last' parameter."""
    # Create four files spaced a day apart
    files = _create_files_with_times(tmp_path, offsets=[0, 86400, 2 * 86400, 3 * 86400, 4 * 86400, 5 * 86400])
    # Apply both days and hours retention and keep the last two files regardless
    args = _make_args(hours=2, days=3, verbose=LogLevel.DEBUG)
    cache = FileStats("mtime")
    logger = Logger(args, cache)
    logic = RetentionLogic(files, args, logger, cache)
    result = logic.process_retention_logic()
    # Should keep exactly two files because 'last=2' ensures they are kept even if other rules would prune them
    assert len(result.keep) == 5
    # Ensure that the last two (newest) files are kept
    kept_names = {f.name for f in result.keep}
    expected_kept = {files[0].name, files[1].name, files[2].name, files[3].name, files[4].name}
    assert kept_names == expected_kept
    # All other files should be pruned
    pruned_names = {f.name for f in result.prune}
    expected_prune = {files[5].name}
    assert pruned_names == expected_prune


@no_type_check
def test_multiple_retention_modes_and_last(tmp_path: Path) -> None:
    """RetentionLogic should apply multiple modes sequentially and honour the 'last' parameter."""
    # Create four files spaced a day apart
    files = _create_files_with_times(tmp_path, offsets=[0, 86400, 2 * 86400, 3 * 86400])
    # Apply both days and hours retention and keep the last two files regardless
    args = _make_args(hours=1, days=2, last=5, verbose=LogLevel.DEBUG)
    cache = FileStats("mtime")
    logger = Logger(args, cache)
    logic = RetentionLogic(files, args, logger, cache)
    result = logic.process_retention_logic()
    # Should keep exactly two files because 'last=2' ensures they are kept even if other rules would prune them
    assert len(result.keep) == 4
    # Ensure that the last two (newest) files are kept
    kept_names = {f.name for f in result.keep}
    expected_kept = {files[0].name, files[1].name, files[2].name, files[3].name}
    assert kept_names == expected_kept
    # All other files should be pruned
    assert not result.prune


@no_type_check
def test_month_quarter_year_retention(tmp_path: Path) -> None:
    """RetentionLogic should apply retention rules for months, quarters and years."""
    files = _create_files_with_times(tmp_path, offsets=[i * 2_592_000 for i in range(60)])  # 1 file per month for 60 months
    args = _make_args(months=6, quarters=4, years=5, verbose=LogLevel.DEBUG)
    cache = FileStats("mtime")
    logger = Logger(args, cache)
    logic = RetentionLogic(files, args, logger, cache)
    result = logic.process_retention_logic()
    # 15 files: 6 month, 4 quarter, 5 years -> (effective 3 years, because we have only files for 5 years)
    assert len(result.keep) == 13  # 6 month, 4 quarter, 5 year
    assert len(result.prune) == 47
    assert "Keeping for mode 'months'" in logger._decisions[files[0]][0][0]


@no_type_check
def test_day_week_month_retention_next_bucket(tmp_path: Path) -> None:
    """RetentionLogic should apply retention rules for days, weeks and months and should select next coarse granular bucket."""
    files = _create_files_with_times(tmp_path, offsets=[i * 86_400 for i in range(60)], mod_time=int(datetime(2026, 1, 14, tzinfo=timezone.utc).timestamp()))  # 1 file per day
    cache = FileStats("mtime")
    args = _make_args(days=7, weeks=4, months=3, verbose=LogLevel.DEBUG)
    logger = Logger(args, cache)
    logic = RetentionLogic(files, args, logger, cache)
    result = logic.process_retention_logic()
    assert len(result.keep) == 12  # 7 days, 4 weeks, 1 month
    for d in range(7):
        assert "Keeping for mode 'days'" in logger._decisions[files[d]][0][0]  # 14.-08.01.2026
    for w in range(0, 4, 7):
        assert "Keeping for mode 'weeks'" in logger._decisions[files[w + 10]][0][0]  # 04.01.2026, 28.12.2025, 21.12.2025, 14.12.2025 (sunday, last day of week) -> jump to coarser bucket
    assert "Keeping for mode 'months'" in logger._decisions[files[45]][0][0]  # 30.11.2025 -> jump to coarser bucket


@no_type_check
def test_day_week_month_retention_bucket_boundaries(tmp_path: Path) -> None:
    """RetentionLogic should apply retention rules for days, weeks and months and should select next coarse granular bucket even if it is the next file."""
    files = _create_files_with_times(tmp_path, offsets=[i * 86_400 for i in range(100)], mod_time=int(datetime(2026, 3, 7, tzinfo=timezone.utc).timestamp()))  # 1 file per day
    args = _make_args(days=6, weeks=5, months=10, verbose=LogLevel.DEBUG)
    cache = FileStats("mtime")
    logger = Logger(args, cache)
    logic = RetentionLogic(files, args, logger, cache)
    result = logic.process_retention_logic()
    assert len(result.keep) == 14  # 6 days, 5 weeks, 3 months
    for d in range(6):
        assert "Keeping for mode 'days'" in logger._decisions[files[d]][0][0]  # 07.03.2026 - 02.03.2026 (monday, first day of week)
    for w in range(0, 3, 7):
        assert "Keeping for mode 'weeks'" in logger._decisions[files[w + 6]][0][0]  # starts with 01.03.2026 (sunday, last day of previous week) - until 01.02.2026 (first day of month)
    assert "Keeping for mode 'months'" in logger._decisions[files[35]][0][0]  # starts with 31.01.2026 (last day of month) - until 30.11.2026 (Jan 2025, Dec 2025, Nov 2025)
    assert "Keeping for mode 'months'" in logger._decisions[files[66]][0][0]
    assert "Keeping for mode 'months'" in logger._decisions[files[97]][0][0]


@no_type_check
def test_not_matched_by_retention_rule(tmp_path: Path) -> None:
    """RetentionLogic should prune files that are not matched by any retention rule."""
    files = _create_files_with_times(tmp_path, offsets=[i * 86_400 for i in range(3)])  # 3 file, 1 per day
    args = _make_args(days=1, verbose=LogLevel.DEBUG)
    cache = FileStats("mtime")
    logger = Logger(args, cache)
    logic = RetentionLogic(files, args, logger, cache)
    result = logic.process_retention_logic()
    assert len(result.keep) == 1
    assert len(result.prune) == 2
    assert "Keeping for mode 'days'" in logger._decisions[files[0]][0][0]
    assert "Pruning: not matched by any retention rule" in logger._decisions[files[2]][0][0]


@no_type_check
def test_filter_max_files(tmp_path: Path) -> None:
    """Filtering rules with last = 3 for max_files = 2 should keep just max_files (2)."""
    # Create three files with identical times but increasing sizes
    files = _create_files_with_times(tmp_path, offsets=[0, 86400, 2 * 86400])
    args = _make_args(last=3, max_files=2, verbose=LogLevel.DEBUG)
    cache = FileStats("mtime")
    logger = Logger(args, cache)
    logic = RetentionLogic(files, args, logger, cache)
    result = logic.process_retention_logic()
    # Because there are 3 files but max_files=2, one file should be pruned
    assert len(result.keep) == 2
    assert len(result.prune) == 1
    assert len(logger._decisions[files[0]]) == 1
    assert len(logger._decisions[files[2]]) == 2
    assert "Filtering: max total count of files exceeded" in Logger._decisions[files[2]][0][0]


@no_type_check
def test_filter_max_size(tmp_path: Path) -> None:
    """Filtering rules with days=2, weeks=10 for max_size = 50 bytes by 10 bytes each file => should keep just max_files (2)."""
    offsets = [i * 604800 for i in range(10)]  # 1 file per week
    files = _create_files_with_times(tmp_path, offsets)
    for f, offset in zip(files, offsets):
        f.write_bytes(b"x" * 10)
        os.utime(f, (SCRIPT_START - offset, SCRIPT_START - offset))
    args = _make_args(days=2, weeks=10, max_size=50, max_size_bytes=50, verbose=LogLevel.DEBUG)
    cache = FileStats("mtime")
    logger = Logger(args, cache)
    logic = RetentionLogic(files, args, logger, cache)
    result = logic.process_retention_logic()
    assert len(result.keep) == 5
    assert len(result.prune) == 5
    assert len(logger._decisions[files[0]]) == 1
    assert len(logger._decisions[files[2]]) == 1
    assert len(logger._decisions[files[5]]) == 2
    assert len(logger._decisions[files[7]]) == 2
    assert "Filtering: max total size exceeded" in logger._decisions[files[8]][0][0]


@no_type_check
def test_filter_max_age(tmp_path: Path) -> None:
    files = _create_files_with_times(tmp_path, offsets=[i * 86_400 for i in range(5)])  # 5 file, 1 per day
    args = _make_args(days=5, max_age="3d", max_age_seconds=259_200, verbose=LogLevel.DEBUG)
    cache = FileStats("mtime")
    logger = Logger(args, cache)
    logic = RetentionLogic(files, args, logger, cache)
    result = logic.process_retention_logic()
    assert len(result.keep) == 3
    assert len(result.prune) == 2
    assert "Keeping for mode 'days'" in logger._decisions[files[0]][0][0]
    assert "Filtering: max total age exceeded" in logger._decisions[files[4]][0][0]


@no_type_check
def test_no_retention_rules(tmp_path: Path, capsys) -> None:
    """Keep all files if no retention rules are specified."""
    files = _create_files_with_times(tmp_path, offsets=[0, 1, 2])
    args = _make_args(verbose=LogLevel.DEBUG)
    cache = FileStats("mtime")
    logger = Logger(args, cache)
    logic = RetentionLogic(files, args, logger, cache)
    result = logic.process_retention_logic()
    assert len(result.keep) == 3
    assert len(result.prune) == 0
    out = capsys.readouterr().out
    assert "No retention rules specified, keeping all files" in out


def test_retention_folder_mode_days_two_levels(tmp_path: Path) -> None:
    # two top-level folders
    folder_new = tmp_path / "new"
    folder_old = tmp_path / "old"

    # second level inside each folder
    sub_new = folder_new / "sub"
    sub_old = folder_old / "sub"

    sub_new.mkdir(parents=True)
    sub_old.mkdir(parents=True)

    f_sub_new = sub_new / "file.txt"
    f_sub_old = sub_old / "file.txt"

    f_sub_new.write_text("new")
    f_sub_old.write_text("old")

    now = SCRIPT_START
    os.utime(f_sub_new, (now - 20, now - 20))
    os.utime(f_sub_old, (now - 4 * 86400, now - 4 * 86400))

    args = _make_args(days=1, folder_mode=True, folder_mode_time_src="youngest-file", verbose=LogLevel.DEBUG, entity_name="folder")
    cache = FileStats("mtime", folder_mode=True, folder_mode_time_src="youngest-file")
    logger = Logger(args, cache)

    # IMPORTANT: only top-level folders are retention objects
    logic = RetentionLogic([folder_new, folder_old], args, logger, cache)
    result = logic.process_retention_logic()

    assert folder_new in result.keep
    assert folder_old in result.prune


def test_retention_folder_mode_multiple_weeks_and_months_with_prune(tmp_path: Path) -> None:
    """
    Folder-mode retention with:
    - multiple top-level folders
    - recursive file structure
    - weeks + months retention
    - at least two folders kept by weeks
    - at least two folders pruned
    """

    # --- Top-level folders (retention objects)
    week_1 = tmp_path / "week_1"
    week_2 = tmp_path / "week_2"
    month_1 = tmp_path / "month_1"
    old_1 = tmp_path / "old_1"
    old_2 = tmp_path / "old_2"

    folders = [week_1, week_2, month_1, old_1, old_2]

    # --- Create second-level structure
    for folder in folders:
        (folder / "sub").mkdir(parents=True)

    # --- Files inside subfolders
    (week_1 / "sub" / "file.txt").write_text("w1")
    (week_2 / "sub" / "file.txt").write_text("w2")
    (month_1 / "sub" / "file.txt").write_text("m1")
    (month_1 / "sub" / "file2.txt").write_text("m2")
    (old_1 / "sub" / "file.txt").write_text("o1")
    (old_2 / "sub" / "file.txt").write_text("o2")

    one_week = 7 * 24 * 60 * 60
    one_month = 31 * 24 * 60 * 60

    # --- Assign mtimes (youngest-file semantics)
    os.utime(week_1 / "sub" / "file.txt", (SCRIPT_START - one_week, SCRIPT_START - one_week))
    os.utime(week_2 / "sub" / "file.txt", (SCRIPT_START - 2 * one_week, SCRIPT_START - 2 * one_week))
    os.utime(month_1 / "sub" / "file.txt", (SCRIPT_START - one_month, SCRIPT_START - one_month))
    os.utime(month_1 / "sub" / "file2.txt", (SCRIPT_START - one_month, SCRIPT_START - one_month))
    os.utime(old_1 / "sub" / "file.txt", (SCRIPT_START - 3 * one_month, SCRIPT_START - 3 * one_month))
    os.utime(old_2 / "sub" / "file.txt", (SCRIPT_START - 4 * one_month, SCRIPT_START - 4 * one_month))

    # --- Retention rules:
    # keep 2 per week, keep 1 per month
    args = _make_args(
        weeks=2,
        months=1,
        folder_mode=True,
        verbose=LogLevel.DEBUG,
        entity_name="folder",
    )

    cache = FileStats(
        "mtime",
        folder_mode=True,
        folder_mode_time_src="youngest-file",
    )
    logger = Logger(args, cache)

    logic = RetentionLogic(folders, args, logger, cache)
    result = logic.process_retention_logic()

    logger.print_decisions()

    # --- Expectations
    # kept by weeks
    assert week_1 in result.keep
    assert week_2 in result.keep

    # kept by months
    assert month_1 in result.keep

    # pruned
    assert old_1 in result.prune
    assert old_2 in result.prune

    # sanity checks
    assert len(result.keep) == 3
    assert len(result.prune) == 2

    # ensure only top-level folders are retention objects
    assert all(p.parent == tmp_path for p in result.keep | result.prune)
