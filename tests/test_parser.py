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


@pytest.mark.parametrize("options, message", [(["--unknown"], "Unknown option"), (["--days", "0"], "Invalid value"), (["--days"], "expected one argument")])
@pytest.mark.parametrize("list_only", [False, True])
def test_argument_errors_write_only_to_stderr(tmp_path, capsys, options, message, list_only) -> None:
    argv = [str(tmp_path), "*", *(["--list-only"] if list_only else []), *options]
    with pytest.raises(SystemExit) as exc:
        create_parser().parse_args(argv)
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "usage:" in output.err
    assert message in output.err
    assert "Hint: Try '--help'" in output.err


@pytest.mark.parametrize("option, message", [("--help", "usage:"), ("--version", "retentions")])
def test_help_and_version_write_to_stdout(capsys, option, message) -> None:
    with pytest.raises(SystemExit) as exc:
        create_parser().parse_args([option])
    assert exc.value.code == 0
    output = capsys.readouterr()
    assert message in output.out
    assert output.err == ""


@pytest.mark.parametrize("options", [["--day", "2"], ["--day=2"], ["--days", "1", "--day", "2"]])
def test_long_option_abbreviations_are_rejected(tmp_path, capsys, options) -> None:
    parser = create_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args([str(tmp_path), "*", *options])
    assert exc.value.code == 2
    assert "Unknown option: --day" in capsys.readouterr().err


@pytest.mark.parametrize("option", ["--days", "-d"])
def test_explicit_days_options_are_accepted(tmp_path, option) -> None:
    args = create_parser().parse_args([str(tmp_path), "*", option, "2"])
    assert args.days == 2


@pytest.mark.parametrize("options", [["-Xm2"], ["-Xd1", "-d2"], ["-Xd1", "--days", "2"], ["-XL"], ["-XH"], ["-XR"], ["-Hm2"], ["-HL"], ["-HR"], ["-Rd1"], ["-RL"], ["-RH"]])
def test_combined_short_options_are_rejected(tmp_path, capsys, options) -> None:
    with pytest.raises(SystemExit) as exc:
        create_parser().parse_args([str(tmp_path), "*", *options])
    assert exc.value.code == 2
    assert "Combined short options are not supported" in capsys.readouterr().err


@pytest.mark.parametrize(
    "options, attribute, expected",
    [
        (["-m2"], "months", 2),
        (["-d1"], "days", 1),
        (["-d=1"], "days", 1),
        (["-X", "-m", "2"], "months", 2),
        (["-X", "-m2"], "months", 2),
        (["-p-Xm2"], "protect", "-Xm2"),
        (["--protect=-Xm2"], "protect", "-Xm2"),
        (["-L-Xm2"], "list_only", "-Xm2"),
    ],
)
def test_separate_short_options_and_attached_values_are_accepted(tmp_path, options, attribute, expected) -> None:
    args = create_parser().parse_args([str(tmp_path), "*", *options])
    assert getattr(args, attribute) == expected


def test_combined_short_option_text_after_separator_is_positional(tmp_path) -> None:
    args = create_parser().parse_args([str(tmp_path), "--", "-Xm2"])
    assert args.file_pattern == "-Xm2"


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


@pytest.mark.parametrize(
    "size, expected",
    [
        ("9007199254740993", 9_007_199_254_740_993),
        ("9007199254740995", 9_007_199_254_740_995),
        ("8.000000000000001P", 9_007_199_254_740_993),
        ("1K", 1024),
        ("1M", 1024**2),
        ("1G", 1024**3),
        ("1T", 1024**4),
        ("1P", 1024**5),
        ("1E", 1024**6),
        ("1.5M", 1_572_864),
        ("1.1K", 1126),
        ("0.9", 0),
        ("1.", 1),
    ],
)
def test_size_parser_preserves_byte_precision(size, expected) -> None:
    assert ModernStrictArgumentParser()._parse_positive_size_argument(size, round_down=True) == expected


@pytest.mark.parametrize("size, expected", [("1.1K", 1127), ("0.9", 1), ("1.", 1), ("9007199254740993", 9_007_199_254_740_993), ("8.000000000000001P", 9_007_199_254_740_994)])
def test_size_parser_rounds_up_by_default(size, expected) -> None:
    assert ModernStrictArgumentParser()._parse_positive_size_argument(size) == expected


@pytest.mark.parametrize("options", [["--age-type"], ["--age-type", "--dry-run"]])
def test_age_type_requires_a_value(tmp_path, capsys, options) -> None:
    with pytest.raises(SystemExit) as exc:
        create_parser().parse_args([str(tmp_path), "*", *options])
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "--age-type: expected one argument" in output.err
    assert "does not support age-type" not in output.err


@pytest.mark.parametrize(
    "options, expected",
    [
        ([], "mtime"),
        (["--age-type", "mtime"], "mtime"),
        (["--age-type", "ctime"], "ctime"),
        (["--age-type", "atime"], "atime"),
        (["--age-type", "filename=%Y-%m-%d"], "filename"),
    ],
)
def test_age_type_default_and_explicit_values(tmp_path, options, expected) -> None:
    args = create_parser().parse_args([str(tmp_path), "*", *options])
    assert args.age_type == expected
    if expected == "filename":
        assert args.filename_format == "%Y-%m-%d"


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


@pytest.mark.parametrize("separator", ["foo", ""])
def test_parse_list_arbitary_string(monkeypatch, separator):
    """Test an arbitrary --list-only argument."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", ".", "*.txt", "--list-only", separator])
    args = parse_arguments()
    assert args.list_only == separator


@pytest.mark.parametrize("separator", [[], [""]])
def test_combine_verbose_list_failed(monkeypatch, capsys, separator):
    """Test that the verbose > ERROR must not be combined with list-only."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", ".", "*.txt", "-X", "-V 3", "-L", *separator])
    with pytest.raises(SystemExit) as exc:
        parse_arguments()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "--list-only and --verbose (> ERROR) cannot be used together" in captured.err


@pytest.mark.parametrize("separator", [[], [""]])
def test_combine_companions_list_failed(monkeypatch, capsys, separator):
    """Test that the delete-companions must not be combined with delete-companions."""
    monkeypatch.setattr(sys, "argv", ["retentions.py", ".", "*.txt", "-X", "--delete-companions", "suffix::.bak", "-L", *separator])
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


def test_combine_folder_mode_skip_by_file_size_failed(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["retentions.py", ".", "*.txt", "-d", "3", "--folder-mode", "--skip-by-filesize", "1k"])
    with pytest.raises(SystemExit) as exc:
        parse_arguments()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "--folder-mode and --skip-by-filesize must not be combined" in captured.err


def test_by_file_size_without_retention_options_failed(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["retentions.py", ".", "*.txt", "--skip-by-filesize", "1k"])
    with pytest.raises(SystemExit) as exc:
        parse_arguments()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "--skip-by-filesize must be combined with any retention option(s)" in captured.err


@pytest.mark.parametrize("scope", ["directory", "system"])
def test_delete_symlinks_scope(tmp_path, scope):
    args = create_parser().parse_args([str(tmp_path), "*", "--delete-symlinks", scope])
    assert args.delete_symlinks == scope
    assert args.symlink_paths == {}
    assert create_parser().parse_args([str(tmp_path), "*"]).delete_symlinks is None


@pytest.mark.parametrize("options", [[], ["invalid"], ["directory", "--folder-mode"], ["directory", "--list-only"], ["directory", "--list-only", ""]])
def test_delete_symlinks_invalid_options(tmp_path, options):
    with pytest.raises(SystemExit) as exc:
        create_parser().parse_args([str(tmp_path), "*", "--delete-symlinks", *options])
    assert exc.value.code == 2
