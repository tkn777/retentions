# mypy: ignore-errors

from pathlib import Path

import pytest

from retentions import CompanionRule, CompanionType


# ---------------------------------------------------------------------------
# tests for CompanionRule.matches()
# ---------------------------------------------------------------------------


def test_companionrule_matches_prefix_positive(tmp_path):
    rule = CompanionRule(CompanionType.PREFIX, "backup-", "meta-")
    file = tmp_path / "backup-data.tar"
    assert rule.matches(file) is True


def test_companionrule_matches_prefix_negative(tmp_path):
    rule = CompanionRule(CompanionType.PREFIX, "backup-", "meta-")
    file = tmp_path / "data-backup.tar"
    assert rule.matches(file) is False


def test_companionrule_matches_suffix_positive(tmp_path):
    rule = CompanionRule(CompanionType.SUFFIX, ".tar", ".md5")
    file = tmp_path / "archive.tar"
    assert rule.matches(file) is True


def test_companionrule_matches_suffix_negative(tmp_path):
    rule = CompanionRule(CompanionType.SUFFIX, ".tar", ".md5", rule_def=None)
    file = tmp_path / "archive.zip"
    assert rule.matches(file) is False


def test_companionrule_matches_empty_match_always_true(tmp_path):
    rule = CompanionRule(CompanionType.SUFFIX, "", ".bak", rule_def=None)
    file = tmp_path / "whatever.txt"
    assert rule.matches(file) is True


# ---------------------------------------------------------------------------
# tests for CompanionRule.replace()
# ---------------------------------------------------------------------------


def test_companionrule_replace_prefix(tmp_path):
    rule = CompanionRule(
        CompanionType.PREFIX,
        "backup-",
        "meta-",
        rule_def=None,
    )
    file = tmp_path / "backup-data.tar"

    result = rule.replace(file)

    assert result.name == "meta-data.tar"
    assert result.parent == file.parent


def test_companionrule_replace_suffix(tmp_path):
    rule = CompanionRule(
        CompanionType.SUFFIX,
        ".tar",
        ".md5",
        rule_def=None,
    )
    file = tmp_path / "archive.tar"

    result = rule.replace(file)

    assert result.name == "archive.md5"
    assert result.parent == file.parent


def test_companionrule_replace_suffix_empty_match(tmp_path):
    rule = CompanionRule(
        CompanionType.SUFFIX,
        "",
        ".bak",
        rule_def=None,
    )
    file = tmp_path / "file.txt"

    result = rule.replace(file)

    assert result.name == "file.txt.bak"
    assert result.parent == file.parent


def test_companion_symlink_is_ignored(tmp_path: Path, symlinks_supported: bool) -> None:
    if not symlinks_supported:
        pytest.skip("Symlinks not supported on this platform")

    main = tmp_path / "example.log"
    main.write_text("x")

    # real companion
    companion_real = tmp_path / "example.tmp"
    companion_real.write_text("meta")

    # symlink companion
    companion_link = tmp_path / "example.tmp.link"
    companion_link.symlink_to(companion_real)

    rule = CompanionRule(
        CompanionType.SUFFIX,
        ".log",
        ".tmp",
        rule_def="suffix:.log:.tmp",
    )

    companions = {rule.replace(main)}

    # simulate run_deletion() logic
    valid_companions = {c for c in companions if c.exists() and c.is_file() and not c.is_symlink()}

    assert companion_real in valid_companions
    assert companion_link not in valid_companions
