"""The shared single-pass AST analyser."""

from __future__ import annotations

from repo_radar.pyast import cache_size, reset_cache, summarize

SOURCE = '''"""Docstring."""

from __future__ import annotations

import os
from typing import Any

from . import sibling
from .module import Thing


def collect(items=[], *, node: Any = None):
    assert items is not None
    try:
        return items
    except:
        pass


from json import *
'''


def test_facts_include_imports_and_symbols() -> None:
    facts = summarize("pkg/mod.py", SOURCE)
    assert facts.tree is not None
    assert facts.error == ""
    assert "collect" in facts.symbols
    modules = {(level, module) for level, module, _ in facts.imports}
    assert (0, "os") in modules
    assert (1, "") in modules or (1, "module") in modules


def test_facts_capture_rule_evidence() -> None:
    facts = summarize("pkg/mod.py", SOURCE)
    assert facts.asserts
    assert facts.bare_except_pass
    assert facts.mutable_defaults
    assert facts.wildcard_imports


def test_syntax_error_is_recorded() -> None:
    facts = summarize("broken.py", "def (:")
    assert facts.tree is None
    assert "line" in facts.error.lower() or facts.error


def test_cache_is_keyed_by_content_and_reset() -> None:
    reset_cache()
    assert cache_size() == 0
    summarize("a.py", "X = 1\n")
    assert cache_size() == 1
    summarize("a.py", "X = 1\n")
    assert cache_size() == 1
    summarize("a.py", "X = 2\n")
    assert cache_size() == 2
    reset_cache()
    assert cache_size() == 0


def test_symbols_exclude_private_and_include_dunder_all() -> None:
    source = '__all__ = ["Visible"]\n\ndef _hidden():\n    pass\n\ndef public():\n    pass\n'
    facts = summarize("m.py", source)
    assert facts.symbols == ["Visible", "public"]


def test_non_python_text_does_not_crash() -> None:
    facts = summarize("style.css", "body { color: red; }")
    assert facts.tree is None
