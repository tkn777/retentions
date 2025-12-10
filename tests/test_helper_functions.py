# pyright: reportGeneralTypeIssues=false

import argparse

import pytest

from retentions import ModernStrictArgumentParser


@pytest.mark.parametrize("value, expected", [("1", 1), ("42", 42), ("9999", 9999)])
def test_positive_int_argument_valid(value: str, expected: int):
    """Valid positive integer strings should return the correct int."""
    assert ModernStrictArgumentParser().positive_int_argument(value) == expected


@pytest.mark.parametrize("value", ["0", "-5", "abc", "4.2", "", " "])
def test_positive_int_argument_invalid(value: str):
    """Invalid values should raise argparse.ArgumentTypeError."""
    with pytest.raises(argparse.ArgumentTypeError, match=rf"Invalid value '{value}': must be an integer > 0"):
        ModernStrictArgumentParser().positive_int_argument(value)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0", 0),
        ("1", 1),
        ("1K", 1024),
        ("1k", 1024),
        ("2M", 2 * 1024**2),
        ("2.5M", int(2.5 * 1024**2)),
        ("1G", 1024**3),
        ("1 G", 1024**3),
        ("3T", 3 * 1024**4),
        ("1P", 1024**5),
        ("1E", 1024**6),
        ("  3t ", 3 * 1024**4),
    ],
)
def test_parse_positive_size_argument_valid(value: str, expected: int):
    """Valid positive strings should return the correct size in bytes."""
    assert ModernStrictArgumentParser().parse_positive_size_argument(value) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        # --- plain seconds (no unit) ---
        ("1", 1),
        ("0001", 1),
        ("1.0", 1),
        ("99.999", 99.999),
        ("2500", 2500),
        ("3600", 3600),
        ("410000", 410000),
        # --- hours ---
        ("1h", 1 * 60 * 60),
        ("1 h", 1 * 60 * 60),
        ("0.001h", 0.001 * 60 * 60),
        ("12.5h", 12.5 * 60 * 60),
        ("0002 h", 2 * 60 * 60),
        # --- days ---
        ("1d", 1 * 24 * 60 * 60),
        ("1 d", 1 * 24 * 60 * 60),
        ("0.1d", 0.1 * 24 * 60 * 60),
        ("2.999 d", 2.999 * 24 * 60 * 60),
        ("10d", 10 * 24 * 60 * 60),
        # --- weeks ---
        ("1w", 1 * 7 * 24 * 60 * 60),
        ("1 w", 1 * 7 * 24 * 60 * 60),
        ("0.5w", 0.5 * 7 * 24 * 60 * 60),
        ("3.141 w", 3.141 * 7 * 24 * 60 * 60),
        # --- months (30d) ---
        ("1m", 30 * 24 * 60 * 60),
        ("1 m", 30 * 24 * 60 * 60),
        ("0.01 m", 0.01 * 30 * 24 * 60 * 60),
        ("2.5m", 2.5 * 30 * 24 * 60 * 60),
        ("12 m", 12 * 30 * 24 * 60 * 60),
        # --- years (365d) ---
        ("1y", 365 * 24 * 60 * 60),
        ("1 y", 365 * 24 * 60 * 60),
        ("0.001 y", 0.001 * 365 * 24 * 60 * 60),
        ("2.75y", 2.75 * 365 * 24 * 60 * 60),
        ("10y", 10 * 365 * 24 * 60 * 60),
        # --- whitespace ---
        ("   3000   ", 3000),
        # --- tricky ---
        ("123456.789 m", 123456.789 * 30 * 24 * 60 * 60),
        ("3.0000001 d", 3.0000001 * 24 * 60 * 60),
        ("1 w", 1 * 7 * 24 * 60 * 60),
    ],
)
def test_valid_times(text: str, expected: int):
    """Valid inputs should return the expected millisecond value."""
    assert ModernStrictArgumentParser().parse_positive_time_argument(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text",
    [
        # Empty input
        "",
        " ",
        # Result < 1 ms
        "0",
        "0.4",
        "0.0001",
        "0.0000001h",
        "0.0001 s",
        # Negative values
        "-1",
        "-5h",
        "-3 s",
        # More than one space between value and unit
        "1  s",
        "1   s",
        "1    h",
        "2   d",
        # Tabs or other whitespace → not allowed
        "1\ts",
        "1\ts",
        "1 \ts",
        "\t 42 \t",  # tabs allowed *around* expression
        " \n 5s \r",  # mixed outer whitespace
        # Invalid formats
        "ms",
        "s",
        "h",
        "1ms",
        "10x",
        "2d3h",
        "1.2.3",
        "NaN",
        "Infinity",
        "1M",  # uppercase not allowed
        # seconds
        "1s",
        "1 s",
        "0.001 s",
        "2.75s",
        "2.75 s",
    ],
)
def test_invalid_times(text: str):
    """Invalid inputs must raise ValueError."""
    with pytest.raises(argparse.ArgumentTypeError):
        ModernStrictArgumentParser().parse_positive_time_argument(text)
