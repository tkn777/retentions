"""Tests for the argument parser (only the addtions in retentions) and regex compilation."""

import sys

import pytest

from retentions import LogLevel, ModernStrictArgumentParser, create_parser, parse_arguments


@pytest.mark.parametrize(
    "argv",
    [
        [".", "*.txt", "-d", "1", "-d", "2"],  # duplicate short flag
        [".", "*.txt", "--days", "1", "--days", "2"],  # duplicate long flag
        [".", "*.txt", "-d", "1", "--days", "2"],  # combined long and short flag
    ],
)
def test_duplicate_flags_raise_system_exit(argv) -> None:
    """Providing the same flag twice should cause the parser to exit with an error."""
    parser = create_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_known_args(argv)
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "argv, suggest, error",
    [
        ([".", "*.txt", "--unknown-option"], None, "Unknown option: --unknown-option"),
        ([".", "*.txt", "-Q"], None, "Unknown option: -Q"),
        ([".", "*.txt", "--dais"], "days?", None),
        ([".", "*.txt", "-a 3G"], None, "Invalid time format: '3G'"),
    ],
)
def test_unknown_option_suggestion_or_error(argv, suggest, error, capsys: pytest.CaptureFixture[str]) -> None:
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
    if error:
        assert error in str(captured.err)


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
    monkeypatch.setattr(sys, "argv", ["retentions.py", ".", "*.txt", "-s", "1k"])
    args = parse_arguments()
    assert args.max_size == "1k"
    assert args.max_size_bytes == 1024


def test_age_parsig(monkeypatch) -> None:
    """Test that the --max-age argument is parsed correctly."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", ".", "*.txt", "-a", "3", "d"])
    args = parse_arguments()
    assert args.max_age == "3d"
    assert args.max_age_seconds == 259_200


@pytest.mark.parametrize(
    "argv, loglevel",
    [
        (["retentions.py", ".", "*.txt", "-V"], LogLevel.INFO),
        (["retentions.py", ".", "*.txt", "--verbose", "DEBUG"], LogLevel.DEBUG),
        (["retentions.py", ".", "*.txt", "-L"], LogLevel.ERROR),
        (["retentions.py", ".", "*.txt", "-L", "-V 0"], LogLevel.ERROR),
        (["retentions.py", ".", "*.txt", "-L", "-X"], LogLevel.ERROR),
        (["retentions.py", ".", "*.txt", "-X"], LogLevel.INFO),
        (["retentions.py", ".", "*.txt", "-X", "-V 3"], LogLevel.DEBUG),
    ],
)
def test_parse_verbose(monkeypatch, argv, loglevel):
    """Test that the verbose arg is set correctly."""
    monkeypatch.setattr(sys, "argv", argv)
    args = parse_arguments()
    assert args.verbose == loglevel


def test_parse_list_only_null_byte(monkeypatch):
    """Test that the --list-only null byte is parsed correctly."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", ".", "*.txt", "--list-only", "\\0"])
    args = parse_arguments()
    assert args.list_only == "\0"


def test_parse_list_arbitary_string(monkeypatch):
    """Test an arbitrary --list-only argument."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", ".", "*.txt", "--list-only", "foo"])
    args = parse_arguments()
    assert args.list_only == "foo"


def test_combine_verbose_list_failed(monkeypatch, capsys):
    """Test that the verbose > ERROR must not be combined with list-only."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", ".", "*.txt", "-X", "-V 3", "-L"])
    with pytest.raises(SystemExit) as exc:
        parse_arguments()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "--list-only and --verbose (> ERROR) cannot be used together" in captured.err


def test_combine_companions_list_failed(monkeypatch, capsys):
    """Test that the delete-companions must not be combined with delete-companions."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", ".", "*.txt", "-X", "--delete-companions", "suffix::.bak", "-L"])
    with pytest.raises(SystemExit) as exc:
        parse_arguments()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "--list-only and --delete-companions must not be combined, because list-only is not for companion" in captured.err


def test_parse_folder_mode_default(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["retentions.py", ".", "*", "--folder-mode"],
    )

    args = parse_arguments()

    assert args.folder_mode is True
    assert args.folder_mode_time_src == "youngest-file"


def test_parse_folder_mode_folder_time_src(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["retentions.py", ".", "*", "--folder-mode", "folder"],
    )

    args = parse_arguments()

    assert args.folder_mode is True
    assert args.folder_mode_time_src == "folder"


def test_parse_folder_mode_invalid_value(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["retentions.py", ".", "*", "--folder-mode", "foobar"],
    )

    with pytest.raises(SystemExit) as exc:
        parse_arguments()

    assert exc.value.code == 2

    err = capsys.readouterr().err
    assert "Invalid folder time source: foobar." in err


def test_combine_folder_mode_list_failed(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["retentions.py", ".", "*.txt", "-d", "3", "--folder-mode", "--delete-companions", "suffix::.bak"])
    with pytest.raises(SystemExit) as exc:
        parse_arguments()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "--folder-mode and --delete-companions must not be combined" in captured.err
