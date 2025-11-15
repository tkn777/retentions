import argparse

import pytest

from retentions import parse_positive_size_argument, positive_int_argument


@pytest.mark.parametrize("value, expected", [("1", 1), ("42", 42), ("9999", 9999)])
def test_positive_int_argument_valid(value: str, expected: int):
    """Valid positive integer strings should return the correct int."""
    assert positive_int_argument(value) == expected


@pytest.mark.parametrize("value", ["0", "-5", "abc", "4.2", "", " "])
def test_positive_int_argument_invalid(value: str):
    """Invalid values should raise argparse.ArgumentTypeError."""
    with pytest.raises(argparse.ArgumentTypeError, match=rf"Invalid value '{value}': must be an integer > 0"):
        positive_int_argument(value)


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
    assert parse_positive_size_argument(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "abc",
        "-1",
        "1X",
        "1Q",  # ;)
        "2MB",
        "5MM",
        "1.2.3",
        "1,5",
        "10e6",
        "-5M",
    ],
)
def test_parse_positive_size_argument_invalid(value: str):
    """Invalid values should raise argparse.ArgumentTypeError."""
    with pytest.raises(argparse.ArgumentTypeError, match=rf"Invalid size format: '{value.strip().upper()}'"):
        parse_positive_size_argument(value)
