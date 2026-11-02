"""Matrix tests for filename timestamps and their retention integration."""

import os
import shlex
import sys
from datetime import datetime, timedelta, timezone

import pytest

import retentions
from retentions import ConfigNamespace, FileStats, Logger, LogLevel, create_parser, main, sort_files


@pytest.mark.parametrize("prefix,suffix", [("backup-", ".tar.gz"), ("backup2_", "_v3.tgz"), ("", ""), (" ", " ")])
@pytest.mark.parametrize(
    "date_format",
    [
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%Y%m%d",
        "%y-%m-%d",
        "%Y-%b-%d",
        "%Y-%B-%d",
        "%Y-%j",
        "%G-W%V-%u",
        "%Y-%m-%d_%H-%M-%S",
        "%Y-%m-%d %H-%M-%S",
        "%Y%m%dT%H%M%S",
        "%Y-%m-%d_%I-%M-%S%p",
        "%Y-%m-%d_%H-%M-%S.%f",
        "%Y-%m-%dT%H:%M:%S%z",
        "BEGIN%Y-%m-%dEND",
        "%Y%%-%m-%d",
        "%Y-%m-%d0",
    ],
)
def test_extractor_format_and_filename_matrix(date_format, prefix, suffix):
    value = datetime(2024, 2, 29, 13, 24, 35, 123456, tzinfo=timezone(timedelta(hours=1)))
    text = value.strftime(date_format)
    expected = int(datetime.strptime(text, date_format).timestamp())
    extract = FileStats("filename").make_cached_extractor(date_format)
    assert extract(prefix + text + suffix) == expected
    assert extract(prefix + text + suffix) == expected


@pytest.mark.parametrize(
    "date_format,filename",
    [
        ("%Y-%m-%d", "README.txt"),
        ("%Y-%m-%d", "backup-2026-02-30.tgz"),
        ("%Y-%m-%d", "backup-2026-02-31.tgz"),
        ("%Y-%m-%d", "backup-2026-01-99.tgz"),
        ("%Y-%m-%d", "backup-2026-13-01.tgz"),
        ("%Y-%m-%d", "backup-2026-00-01.tgz"),
        ("%Y-%m-%d", "backup-2026-02-29.tgz"),
        ("%Y-%m-%d", "backup-12026-01-02.tgz"),
        ("%Y-%m-%d", "backup-2026-01-020.tgz"),
        ("%Y%m%d", "backup-20260230.tgz"),
        ("%Y-%m-%d_%H-%M-%S", "backup-2026-01-02_25-00-00.tgz"),
        ("%Q", "backup-2026-01-02.tgz"),
        ("%", "backup-2026-01-02.tgz"),
        ("", "backup-2026-01-02.tgz"),
        ("%Y-%m-%d", ""),
    ],
)
@pytest.mark.parametrize("with_logger", [False, True])
def test_extractor_rejects_invalid_candidates(date_format, filename, with_logger, capsys):
    stats = FileStats("filename")
    if with_logger:
        stats.logger = Logger(ConfigNamespace(verbose=LogLevel.ERROR, age_type="filename"), stats)
    extract = stats.make_cached_extractor(date_format)
    if with_logger:
        assert extract(filename) == -1
        assert extract(filename) == -1
    else:
        with pytest.raises(RuntimeError, match="without a logger"):
            extract(filename)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("history", [[], ["backup-2026-02-31.tgz"], ["backup-2026-01-02.tgz", "README.txt"], [f"shape{chr(65 + i)}-2026-01-02.tgz" for i in range(40)]])
@pytest.mark.parametrize(
    "filename,expected",
    [
        ("backup-2026-01-31.tgz", datetime(2026, 1, 31)),
        ("backup-2026-01-02-to-2025-12-31.tgz", datetime(2026, 1, 2)),
        ("backup-2026-02-30-to-2026-03-01.tgz", datetime(2026, 3, 1)),
        ("backup-2026-1-21.tgz", datetime(2026, 1, 21)),
    ],
)
def test_extractor_selection_is_independent_of_cache_history(history, filename, expected):
    stats = FileStats("filename")
    stats.logger = Logger(ConfigNamespace(verbose=LogLevel.ERROR, age_type="filename"), stats)
    extract = stats.make_cached_extractor("%Y-%m-%d")
    for previous in history:
        extract(previous)
    assert extract(filename) == FileStats("filename").make_cached_extractor("%Y-%m-%d")(filename) == int(expected.timestamp())


@pytest.mark.parametrize("date_format", ["%Y-%m-%d", "%Y-%m-%d %H-%M-%S", "%Y%m%d", "%Q", "%", "", "prefix=%Y"])
@pytest.mark.parametrize("inline", [False, True])
def test_parser_stores_filename_format_without_validation(tmp_path, date_format, inline):
    option = "filename=" + date_format
    arguments = ["--age-type=" + option] if inline else ["--age-type", option]
    args, unknown = create_parser().parse_known_args([str(tmp_path), "*", *arguments])
    assert not unknown
    assert args.age_type == "filename"
    assert args.filename_format == date_format


def test_quoted_filename_format_with_spaces(tmp_path):
    parser = create_parser()
    args, unknown = parser.parse_known_args([str(tmp_path), "*", *shlex.split("--age-type 'filename=%Y-%m-%d %H-%M-%S'")])
    assert not unknown
    assert args.filename_format == "%Y-%m-%d %H-%M-%S"
    assert "'filename=<format>'" in parser.format_help()
    assert "Python date/time format" in parser.format_help()


@pytest.mark.parametrize("age_type", ["filename", "filenamex=%Y", "invalid", "", "size", "mode", "mtime_ns"])
def test_parser_rejects_unknown_age_types(tmp_path, age_type):
    with pytest.raises(SystemExit) as exc:
        create_parser().parse_known_args([str(tmp_path), "*", "--age-type", age_type])
    assert exc.value.code == 2


@pytest.mark.parametrize("age_type", ["mtime", "ctime", "atime", "birthtime"])
def test_existing_age_types_still_use_file_attributes(tmp_path, age_type):
    file = tmp_path / "backup-2026-01-02.tgz"
    file.write_text("data")
    if not hasattr(file.stat(), "st_" + age_type):
        pytest.skip(f"{age_type} is unavailable on this filesystem")
    args, _ = create_parser().parse_known_args([str(tmp_path), "*", "--age-type", age_type])
    assert args.filename_format is None
    assert FileStats(age_type).get_file_seconds(file) == int(getattr(file.stat(), "st_" + age_type))


@pytest.mark.parametrize("verbose", list(LogLevel))
@pytest.mark.parametrize("invalid", [False, True])
def test_filename_seconds_and_failures_are_cached(tmp_path, capsys, verbose, invalid):
    file = tmp_path / ("README.txt" if invalid else "backup-2026-01-02.tgz")
    file.write_text("data")
    stats = FileStats("filename", filename_format="%Y-%m-%d")
    stats.logger = Logger(ConfigNamespace(verbose=verbose, age_type="filename"), stats)
    original = stats._filename_extractor
    calls = []

    def counted_extract(name):
        calls.append(name)
        return original(name)

    stats._filename_extractor = counted_extract
    expected = -1 if invalid else int(datetime(2026, 1, 2).timestamp())
    assert stats.get_file_seconds(file) == expected
    assert stats.get_file_seconds(file) == expected
    assert sort_files(iter([file]), stats) == ([] if invalid else [file])
    assert calls == [file.name]
    output = capsys.readouterr().out
    assert output.count("[WARN]") == int(invalid and verbose >= LogLevel.WARN)


@pytest.mark.parametrize("mode", ["folder", "path", "youngest-file", "oldest-file"])
@pytest.mark.parametrize("valid_count", [0, 1, 2])
@pytest.mark.parametrize("date_format", ["%Y-%m-%d", "%Y%m%d"])
def test_folder_filename_time_source_matrix(tmp_path, capsys, mode, valid_count, date_format):
    dates = [datetime(2026, 1, 2), datetime(2026, 1, 3)]
    folder = tmp_path / (dates[0].strftime(date_format) if valid_count else "no-date")
    sub = folder / "nested"
    sub.mkdir(parents=True)
    files = [folder / (dates[0].strftime(date_format) if valid_count else "README.txt"), sub / (dates[1].strftime(date_format) if valid_count > 1 else "other.txt")]
    for index, file in enumerate(files):
        file.write_text("data")
        os.utime(file, (1_700_000_100 - index * 100, 1_700_000_100 - index * 100))
    source = f"path={files[0]}" if mode == "path" else mode
    stats = FileStats("filename", True, source, date_format)
    stats.logger = Logger(ConfigNamespace(verbose=LogLevel.WARN, age_type="filename"), stats)
    expected = -1 if not valid_count else int(dates[1 if mode == "youngest-file" and valid_count == 2 else 0].timestamp())
    assert stats.get_file_seconds(folder) == expected
    assert stats.get_file_seconds(folder) == expected
    assert sort_files([folder], stats) == ([] if expected == -1 else [folder])
    assert stats.get_file_bytes(folder) == 8
    warnings = capsys.readouterr().out
    if not valid_count:
        assert "[WARN]" in warnings
    assert "[ERROR]" not in warnings


@pytest.mark.parametrize("mode", ["youngest-file", "oldest-file"])
@pytest.mark.parametrize("with_logger", [False, True])
def test_folder_without_any_files_has_no_filename_timestamp(tmp_path, capsys, mode, with_logger):
    folder = tmp_path / "folder"
    (folder / "empty-subdirectory").mkdir(parents=True)
    stats = FileStats("filename", True, mode, "%Y-%m-%d")
    if with_logger:
        stats.logger = Logger(ConfigNamespace(verbose=LogLevel.WARN, age_type="filename"), stats)
        assert stats.get_file_seconds(folder) == -1
        assert stats.get_file_seconds(folder) == -1
    else:
        with pytest.raises(RuntimeError, match="without a logger"):
            stats.get_file_seconds(folder)
    assert capsys.readouterr().out.count("[WARN]") == int(with_logger)


@pytest.mark.parametrize("mode", [None, "folder", "path", "youngest-file", "oldest-file"])
@pytest.mark.parametrize("invalid", [False, True])
def test_missing_logger_only_fails_when_a_warning_is_needed(tmp_path, mode, invalid):
    folder = tmp_path / ("no-date" if invalid else "2026-01-02")
    folder.mkdir()
    source = folder / ("README.txt" if invalid else "2026-01-02.txt")
    source.write_text("data")
    stats = FileStats("filename", mode is not None, f"path={source}" if mode == "path" else mode, "%Y-%m-%d")
    target = source if mode is None else folder
    if invalid:
        with pytest.raises(RuntimeError, match="without a logger"):
            stats.get_file_seconds(target)
    else:
        assert stats.get_file_seconds(target) == int(datetime(2026, 1, 2).timestamp())


@pytest.mark.parametrize("age_type", ["filename", "mtime"])
@pytest.mark.parametrize("source_kind,message", [("missing", "must be a file"), ("directory", "must be a file"), ("outside", "must be inside the folder")])
def test_path_source_validation_is_preserved(tmp_path, age_type, source_kind, message):
    folder = tmp_path / "folder"
    folder.mkdir()
    source = folder / "2026-01-02"
    if source_kind == "directory":
        source.mkdir()
    elif source_kind == "outside":
        source = tmp_path / "2026-01-02"
        source.write_text("data")
    stats = FileStats(age_type, True, f"path={source}", "%Y-%m-%d" if age_type == "filename" else None)
    with pytest.raises(ValueError, match=message):
        stats.get_file_seconds(folder)


@pytest.mark.parametrize("mode", ["path", "youngest-file", "oldest-file"])
@pytest.mark.parametrize("invalid", [False, True])
def test_folder_sources_cache_child_timestamps(tmp_path, capsys, mode, invalid):
    folder = tmp_path / "folder"
    folder.mkdir()
    source = folder / ("README.txt" if invalid else "2026-01-02")
    source.write_text("data")
    stats = FileStats("filename", True, f"path={source}" if mode == "path" else mode, "%Y-%m-%d")
    stats.logger = Logger(ConfigNamespace(verbose=LogLevel.WARN, age_type="filename"), stats)
    original = stats._filename_extractor
    calls = []

    def counted_extract(name):
        calls.append(name)
        return original(name)

    stats._filename_extractor = counted_extract
    expected = -1 if invalid else int(datetime(2026, 1, 2).timestamp())
    assert stats.get_file_seconds(folder) == expected
    assert stats.get_file_seconds(folder) == expected
    assert stats.get_file_seconds(source) == expected
    assert calls == [source.name]
    output = capsys.readouterr().out
    assert output.count(f"It is ignored: {source.name}") == int(invalid)


@pytest.mark.parametrize("regex", [False, True])
@pytest.mark.parametrize("verbose", list(LogLevel))
@pytest.mark.parametrize(
    "options,deleted",
    [([], []), (["--last", "1"], [0]), (["--days", "1"], [0]), (["--max-files", "1"], [0]), (["--max-age", "1d"], [0]), (["--last", "2", "--max-size", "1"], [0])],
)
def test_filename_retention_matrix(tmp_path, monkeypatch, capsys, regex, verbose, options, deleted):
    names = ["backup-2026-01-02.tgz", "backup-2026-01-03.tgz", "backup-2026-02-30.tgz", "README.txt"]
    for index, name in enumerate(names):
        file = tmp_path / name
        file.write_text("x")
        os.utime(file, (1_700_000_100 - index * 10, 1_700_000_100 - index * 10))
    monkeypatch.setattr(retentions, "SCRIPT_START", int(datetime(2026, 1, 3, 12).timestamp()))
    argv = ["retentions.py", str(tmp_path), ".*" if regex else "*", "--age-type", "filename=%Y-%m-%d", "--verbose", verbose.name, *options]
    if regex:
        argv.extend(["--regex-mode", "casesensitive"])
    monkeypatch.setattr(sys, "argv", argv)
    main()
    assert [name for name in names if not (tmp_path / name).exists()] == [names[index] for index in deleted]
    output = capsys.readouterr().out
    assert output.count("[WARN]") == (2 if verbose >= LogLevel.WARN else 0)
    for name in names[2:]:
        assert not any(name in line and any(word in line for word in ["Keeping", "Pruning", "Filtering"]) for line in output.splitlines())


@pytest.mark.parametrize("verbose", list(LogLevel))
@pytest.mark.parametrize("dry_run", [False, True])
def test_ignored_protected_files_have_no_decisions(tmp_path, monkeypatch, capsys, verbose, dry_run):
    invalid = tmp_path / "README.txt"
    invalid.write_text("protected")
    argv = ["retentions.py", str(tmp_path), "*", "--age-type", "filename=%Y-%m-%d", "--protect", "README.txt", "--verbose", verbose.name]
    if dry_run:
        argv.append("--dry-run")
    monkeypatch.setattr(sys, "argv", argv)
    main()
    output = capsys.readouterr().out
    assert invalid.exists()
    assert "Protected by" not in output
    assert "README.txt:" not in output
    assert output.count("[WARN]") == int(verbose >= LogLevel.WARN)


@pytest.mark.parametrize("dry_run", [False, True])
def test_unrecognized_files_can_still_be_deleted_as_companions(tmp_path, monkeypatch, dry_run):
    old = tmp_path / "backup-2026-01-02.tar"
    new = tmp_path / "backup-2026-01-03.tar"
    checksum = tmp_path / "checksum.sha256"
    for file in [old, new, checksum]:
        file.write_text("x")
    argv = ["retentions.py", str(tmp_path), "*", "--age-type", "filename=%Y-%m-%d", "--last", "1", "--delete-companions", f"prefix:{old.name}:{checksum.name}"]
    if dry_run:
        argv.append("--dry-run")
    monkeypatch.setattr(sys, "argv", argv)
    main()
    assert old.exists() == dry_run
    assert checksum.exists() == dry_run
    assert new.exists()
