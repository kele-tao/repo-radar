"""Language detection and ignore-pattern behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_radar.languages import (
    DEFAULT_IGNORE,
    is_binary_name,
    is_ignored,
    language_for,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("app.py", "Python"),
        ("mod.tsx", "TypeScript"),
        ("index.mjs", "JavaScript"),
        ("svc.go", "Go"),
        ("lib.rs", "Rust"),
        ("Main.java", "Java"),
        ("util.cpp", "C++"),
        ("notes.md", "Markdown"),
        ("values.yaml", "YAML"),
        ("Dockerfile", "Dockerfile"),
        ("Makefile", "Makefile"),
    ],
)
def test_language_detection(name: str, expected: str) -> None:
    lang = language_for(Path(name))
    assert lang is not None
    assert lang.name == expected


def test_unknown_extension_returns_none() -> None:
    assert language_for(Path("mystery.zzz")) is None


def test_categories_split_code_from_config() -> None:
    python = language_for(Path("x.py"))
    yaml = language_for(Path("x.yaml"))
    assert python is not None and yaml is not None
    assert python.category == "code"
    assert yaml.category == "data"
    assert python.executable is True
    assert yaml.executable is False


def test_binary_names_are_recognised() -> None:
    assert is_binary_name("logo.PNG")
    assert is_binary_name("archive.tar.gz")
    assert not is_binary_name("module.py")


def test_default_ignore_covers_dependency_dirs() -> None:
    assert "node_modules" in DEFAULT_IGNORE
    assert ".venv" in DEFAULT_IGNORE


def test_is_ignored_handles_directory_and_glob() -> None:
    assert is_ignored("node_modules/react/index.js")
    assert is_ignored("build/out.js")
    assert is_ignored("static/app.min.js", ("*.min.js",))
    assert is_ignored("vendor/lib.c", ("vendor/",))
    assert not is_ignored("src/app.py")
    assert not is_ignored("src/app.py", ("*.min.js",))


def test_is_ignored_supports_prefix_patterns() -> None:
    assert is_ignored("examples/demo-repo/main.py", ("examples/demo-repo",))
