"""Module explainer behaviour on Python and non-Python inputs."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_radar.explain import explain_file, explain_python
from tests.conftest import write

SAMPLE = '''"""Module docstring."""

from __future__ import annotations


class Widget:
    """A widget."""

    def render(self) -> str:
        """Draw it."""
        if self:
            return "x"
        return ""


def build(count: int = 1) -> Widget:
    for _ in range(count):
        pass
    return Widget()


def _private() -> None:
    pass
'''


def test_public_api_is_extracted() -> None:
    exp = explain_python(SAMPLE, "widget.py")
    assert exp.public_names == ["Widget", "build"]
    assert exp.private_names == ["_private"]
    assert exp.docstring == "Module docstring."
    assert {s.kind for s in exp.symbols} == {"class", "function"}


def test_docstring_coverage_is_measured() -> None:
    exp = explain_python(SAMPLE, "widget.py")
    assert exp.docstring_coverage == pytest.approx(33.3)


def test_complexity_proxy_counts_branches() -> None:
    exp = explain_python(SAMPLE, "widget.py")
    assert exp.complexity > 1
    assert exp.max_function_branches >= 1
    assert exp.hardest_function in {"Widget", "build"}


def test_imports_are_listed() -> None:
    exp = explain_python(SAMPLE, "widget.py")
    assert "annotations" in " ".join(exp.imports)


def test_summary_is_a_sentence() -> None:
    exp = explain_python(SAMPLE, "widget.py")
    assert exp.summary.endswith(".")
    assert "Python" in exp.summary


def test_syntax_error_is_reported_not_raised() -> None:
    exp = explain_python("def (:\n", "broken.py")
    assert exp.parse_error
    assert exp.summary


def test_javascript_fallback(tmp_path: Path) -> None:
    write(tmp_path, "app.js", "import x from 'y';\n\nexport function boot() {\n"
                              "  if (x) { return 1; }\n}\n")
    exp = explain_file(tmp_path / "app.js")
    assert exp.language == "JavaScript"
    assert "boot" in exp.public_names
    assert exp.imports


def test_missing_file_raises_friendly_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError) as info:
        explain_file(tmp_path / "nope.py")
    assert "no such file" in str(info.value)


def test_directory_input_raises(tmp_path: Path) -> None:
    with pytest.raises(IsADirectoryError):
        explain_file(tmp_path)


def test_relative_path_against_root(clean_repo: Path) -> None:
    exp = explain_file(clean_repo / "src/demo/math.py", clean_repo)
    assert exp.path == "src/demo/math.py"
    assert "add" in exp.public_names


def test_empty_file_is_handled(tmp_path: Path) -> None:
    write(tmp_path, "empty.py", "")
    exp = explain_file(tmp_path / "empty.py")
    assert exp.lines == 0
    assert exp.symbols == []
    assert exp.summary


def test_unicode_symbols(tmp_path: Path) -> None:
    write(tmp_path, "m.py", "def 运行() -> int:\n    \"\"\"运行。\"\"\"\n"
                            "    return 1\n")
    exp = explain_file(tmp_path / "m.py")
    assert "运行" in exp.public_names
