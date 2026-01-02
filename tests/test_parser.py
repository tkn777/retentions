"""Tests for the argument parser (only the addtions in retentions) and regex compilation."""

import sys

import pytest

from retentions import LogLevel, ModernStrictArgumentParser, create_parser, parse_arguments


@pytest.mark.parametrize(
    "argv",
    [
        ["/tmp", "*.txt", "-d", "1", "-d", "2"],  # duplicate short flag
        ["/tmp", "*.txt", "--days", "1", "--days", "2"],  # duplicate long flag
        ["/tmp", "*.txt", "-d", "1", "--days", "2"],  # combined long and short flag
    ],
)
def test_duplicate_flags_raise_system_exit(argv) -> None:
    """Providing the same flag twice should cause the parser to exit with an error."""
    parser = create_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_known_args(argv)
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "argv, suggest",
    [
        (["/tmp", "*.txt", "--unknown-option"], None),
        (["/tmp", "*.txt", "-Q"], None),
        (["/tmp", "*.txt", "--dais"], "days?"),
    ],
)
def test_unknown_option_suggestion_or_error(argv, suggest, capsys: pytest.CaptureFixture[str]) -> None:
    """Unknown options should result in SystemExit with an appropriate error message."""
    parser = create_parser()
    # Unknown option
    with pytest.raises(SystemExit) as exc:
        parser.parse_known_args(argv)
    assert exc.value.code == 2
    captured = capsys.readouterr()
    if suggest:
        assert "did you mean --" + suggest in str(captured.err)
    else:
        assert "did you mean" not in str(captured.err)


def test_compile_regex_valid_and_invalid() -> None:
    """The internal _compile_regex method should compile valid patterns and collect errors for invalid ones."""
    parser = ModernStrictArgumentParser()
    # Valid regex returns a pattern
    pattern = parser._compile_regex(r"^file.*", "casesensitive")
    assert pattern and pattern.match("file123")
    # Invalid regex should return None and add an error
    parser._errors.clear()
    bad_pattern = parser._compile_regex("[invalid", "casesensitive")
    assert bad_pattern is None
    # After calling _compile_regex with invalid input, there should be an error message stored
    assert parser._errors


def test_size_parsig(monkeypatch) -> None:
    """Test that the --max-size argument is parsed correctly."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", "/tmp", "*.txt", "-s", "1k"])
    args = parse_arguments()
    assert args.max_size == "1k"
    assert args.max_size_bytes == 1024


def test_age_parsig(monkeypatch) -> None:
    """Test that the --max-age argument is parsed correctly."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", "/tmp", "*.txt", "-a", "3", "d"])
    args = parse_arguments()
    assert args.max_age == "3d"
    assert args.max_age_seconds == 259_200


@pytest.mark.parametrize(
    "argv, loglevel",
    [
        (["retentions.py", "/tmp", "*.txt"], LogLevel.INFO),
        (["retentions.py", "/tmp", "*.txt", "--verbose", "DEBUG"], LogLevel.DEBUG),
        (["retentions.py", "/tmp", "*.txt", "-L"], LogLevel.ERROR),
        (["retentions.py", "/tmp", "*.txt", "-L", "-V 0"], LogLevel.ERROR),
        (["retentions.py", "/tmp", "*.txt", "-L", "-X"], LogLevel.ERROR),
        (["retentions.py", "/tmp", "*.txt", "-X"], LogLevel.INFO),
        (["retentions.py", "/tmp", "*.txt", "-X", "-V 3"], LogLevel.DEBUG),
    ],
)
def test_parse_verbose(monkeypatch, argv, loglevel):
    """Test that the verbose arg is set correctly."""
    monkeypatch.setattr(sys, "argv", argv)
    args = parse_arguments()
    assert args.verbose == loglevel


def test_parse_verbose_list_failed(monkeypatch, capsys):
    """Test that the verbose arg is set correctly."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", "/tmp", "*.txt", "-X", "-V 3", "-L"])
    with pytest.raises(SystemExit) as exc:
        parse_arguments()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "--list-only and --verbose (> ERROR) cannot be used together" in captured.err
