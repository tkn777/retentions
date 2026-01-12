"""Tests for the RetentionLogic class."""

import os
from pathlib import Path
from typing import no_type_check

from retentions import SCRIPT_START, ConfigNamespace, FileStatsCache, Logger, LogLevel, RetentionLogic


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
    )
    defaults.update(overrides)
    return ConfigNamespace(**defaults)


@no_type_check
def _create_files_with_times(tmp_path: Path, offsets: list[int]) -> list[Path]:
    """Create files whose mtime is offset by the given seconds from now."""
    files: list[Path] = []
    for idx, offset in enumerate(offsets):
        f = tmp_path / f"file{idx}.txt"
        f.write_text(str(idx))
        mod_time = SCRIPT_START - offset
        os.utime(f, (mod_time, mod_time))
        files.append(f)
    return files


@no_type_check
def test_hours_retention(tmp_path: Path) -> None:
    """When hours retention is specified, one file should be kept per hour for the newest N hours."""
    # Create three files spaced an hour apart: newest first
    files = _create_files_with_times(tmp_path, offsets=[0, 1, 3600, 2 * 3600])  # 0 and 3500 => same bucket (hour)
    args = _make_args(hours=2, verbose=LogLevel.DEBUG)
    cache = FileStatsCache("mtime")
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
    cache = FileStatsCache("mtime")
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
    cache = FileStatsCache("mtime")
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
    cache = FileStatsCache("mtime")
    logger = Logger(args, cache)
    logic = RetentionLogic(files, args, logger, cache)
    result = logic.process_retention_logic()
    # 15 files: 6 month, 4 quarter, 5 years -> (effective 3 years, because we have only files for 5 years)
    assert len(result.keep) == 14  # 6 month, 4 quarter, 5 year
    assert len(result.prune) == 46
    assert "Keeping for mode 'months'" in logger._decisions[files[0]][0][0]


@no_type_check
def test_not_matched_by_retention_rule(tmp_path: Path) -> None:
    """RetentionLogic should prune files that are not matched by any retention rule."""
    files = _create_files_with_times(tmp_path, offsets=[i * 86_400 for i in range(3)])  # 3 file, 1 per day
    args = _make_args(days=1, verbose=LogLevel.DEBUG)
    cache = FileStatsCache("mtime")
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
    cache = FileStatsCache("mtime")
    logger = Logger(args, cache)
    logic = RetentionLogic(files, args, logger, cache)
    result = logic.process_retention_logic()
    # Because there are 3 files but max_files=2, one file should be pruned
    assert len(result.keep) == 2
    assert len(result.prune) == 1
    assert len(logger._decisions[files[0]]) == 1
    assert len(logger._decisions[files[2]]) == 2
    assert "Filtering: max total files exceeded" in Logger._decisions[files[2]][0][0]


@no_type_check
def test_filter_max_size(tmp_path: Path) -> None:
    """Filtering rules with days=2, weeks=10 for max_size = 50 bytes by 10 bytes each file => should keep just max_files (2)."""
    offsets = [i * 604800 for i in range(10)]  # 1 file per week
    files = _create_files_with_times(tmp_path, offsets)
    for f, offset in zip(files, offsets):
        f.write_bytes(b"x" * 10)
        os.utime(f, (SCRIPT_START - offset, SCRIPT_START - offset))
    args = _make_args(days=2, weeks=10, max_size=50, max_size_bytes=50, verbose=LogLevel.DEBUG)
    cache = FileStatsCache("mtime")
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
    cache = FileStatsCache("mtime")
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
    cache = FileStatsCache("mtime")
    logger = Logger(args, cache)
    logic = RetentionLogic(files, args, logger, cache)
    result = logic.process_retention_logic()
    assert len(result.keep) == 3
    assert len(result.prune) == 0
    out = capsys.readouterr().out
    assert "No retention rules specified, keeping all files" in out
