import argparse

import pytest

from retentions import positive_int_argument


@pytest.mark.parametrize(
    "value, expected",
    [
        ("1", 1),
        ("42", 42),
        ("9999", 9999),
    ],
)
def test_positive_int_argument_valid(value: str, expected: int):
    """Valid positive integer strings should return the correct int."""
    result = positive_int_argument(value)
    assert result == expected


@pytest.mark.parametrize(
    "value",
    [
        "0",
        "-5"
        "abc",
        "4.2",
        "",
        " ",
    ],
)
def test_positive_int_argument_invalid(value: str):
    """Invalid values should raise argparse.ArgumentTypeError."""
    with pytest.raises(argparse.ArgumentTypeError):
        positive_int_argument(value)
