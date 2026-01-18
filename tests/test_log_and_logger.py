"""Tests for LogLevel and Logger classes."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from retentions import FileStats, Logger, LogLevel


def test_logger_add_and_print_decisions(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Logger should accumulate decisions and print them based on the verbosity level."""
    # Reset the class-level decisions store to avoid interference between tests
    Logger._decisions.clear()

    # Prepare a logger with INFO level
    args = SimpleNamespace(verbose=LogLevel.INFO, age_type="atime")
    cache = FileStats(args.age_type)
    logger = Logger(args, cache)

    # Create a file and record a decision
    file_path = tmp_path / "example.txt"
    file_path.write_text("data")
    logger.add_decision(LogLevel.INFO, file_path, "Keep for some reason")
    print(logger._decisions)

    # Print decisions and capture stderr output
    logger.print_decisions()
    captured = capsys.readouterr()
    # Should contain the file name and the message on stderr
    assert "example.txt" in captured.out
    assert "Keep for some reason" in captured.out

    # Now simulate DEBUG level to see history
    Logger._decisions.clear()
    args.verbose = LogLevel.DEBUG
    logger_debug = Logger(args, cache)
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("1")
    file_b.write_text("2")
    # Add decisions with debug messages
    logger_debug.add_decision(LogLevel.INFO, file_a, "Decision A", debug="debugA")
    logger_debug.add_decision(LogLevel.INFO, file_a, "Second A", debug="debugA2")
    logger_debug.add_decision(LogLevel.INFO, file_b, "Decision B")
    logger_debug.print_decisions()
    captured2 = capsys.readouterr()
    # In DEBUG mode, both first and second decision for the same file should appear
    assert "Decision A" in captured2.out
    assert "Second A" in captured2.out
    # The debug messages should be included in parenthesis for the first file only in DEBUG mode
    assert "debugA" in captured2.out
