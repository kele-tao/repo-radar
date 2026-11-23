"""The YAML-lite config parser: happy path and every documented failure mode."""

from __future__ import annotations

import pytest

from repo_radar.yamlite import ConfigError, parse_simple_yaml


def test_scalars_are_coerced() -> None:
    data = parse_simple_yaml(
        "name: demo\nversion: 3\nratio: 0.5\nenabled: true\nmissing: null\n"
    )
    assert data == {"name": "demo", "version": 3, "ratio": 0.5,
                    "enabled": True, "missing": None}


def test_quoted_strings_keep_spaces() -> None:
    assert parse_simple_yaml("title: ' spaced out '\n")["title"] == " spaced out "


def test_inline_and_block_lists() -> None:
    data = parse_simple_yaml("inline: [a, b, c]\nblock:\n  - x\n  - y\n")
    assert data["inline"] == ["a", "b", "c"]
    assert data["block"] == ["x", "y"]


def test_comments_and_blank_lines_are_ignored() -> None:
    data = parse_simple_yaml("# leading comment\n\nkey: value\n")
    assert data == {"key": "value"}


def test_nested_mapping() -> None:
    data = parse_simple_yaml("outer:\n  inner: 1\n  other: 2\n")
    assert data == {"outer": {"inner": 1, "other": 2}}


def test_bad_line_reports_line_number() -> None:
    with pytest.raises(ConfigError) as info:
        parse_simple_yaml("key: value\nnot a mapping\n")
    assert "line 2" in str(info.value)


def test_list_item_without_key_is_an_error() -> None:
    with pytest.raises(ConfigError):
        parse_simple_yaml("- orphan\n")


def test_empty_document_is_empty_dict() -> None:
    assert parse_simple_yaml("") == {}
