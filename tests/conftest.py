"""Shared fixtures: small synthetic trees built on tmp_path."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def clean_repo(tmp_path: Path) -> Path:
    """A tiny, healthy Python project: README, licence, tests, CI, manifest."""
    write(tmp_path, "README.md", "# demo\n\nA small project used by the tests.\n" * 30)
    write(tmp_path, "LICENSE", "MIT License\n")
    write(tmp_path, "pyproject.toml", '[project]\nname = "demo"\nversion = "1.0"\n'
                                     'dependencies = ["requests==2.31.0"]\n')
    write(tmp_path, ".github/workflows/ci.yml", "name: ci\non: [push]\n")
    write(tmp_path, "src/demo/__init__.py", '"""Demo package."""\n\n__all__ = ["add"]\n')
    write(tmp_path, "src/demo/math.py", '"""Arithmetic helpers."""\n\n\n'
                                        "def add(a: int, b: int) -> int:\n"
                                        '    """Add two numbers."""\n'
                                        "    return a + b\n")
    write(tmp_path, "src/demo/app.py", "from .math import add\n\n\n"
                                       "def run() -> int:\n"
                                       "    return add(1, 2)\n")
    write(tmp_path, "tests/test_math.py", "from demo.math import add\n\n\n"
                                          "def test_add():\n"
                                          "    assert add(2, 3) == 5\n")
    return tmp_path


@pytest.fixture
def risky_repo(tmp_path: Path) -> Path:
    """A project with planted problems the rules must catch."""
    write(tmp_path, "main.py", 'DEFAULT_PASSWORD = "hunter2-secret"\n'
                                "\n"
                                "def run(user_input):\n"
                                "    eval(user_input)\n"
                                "    import subprocess\n"
                                "    subprocess.call(user_input, shell=True)\n"
                                "\n"
                                "def fetch(client):\n"
                                "    return client.get('https://example.com', verify=False)\n")
    write(tmp_path, "orphan.py", "def never_called():\n"
                                  "    return 1\n"
                                  "\n"
                                  "# a note that never got finished\n")
    return tmp_path
