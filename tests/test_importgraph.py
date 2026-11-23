"""Import graph: internal edges, dead code candidates and cycles."""

from __future__ import annotations

from repo_radar.importgraph import (
    ImportGraph,
    build_graph,
    describe_graph,
    largest_cycles,
    parse_python_symbols,
)


def test_python_absolute_and_relative_imports() -> None:
    files = {
        "pkg/__init__.py": "",
        "pkg/a.py": "from pkg import b\n",
        "pkg/b.py": "from . import c\n",
        "pkg/c.py": "VALUE = 1\n",
    }
    langs = dict.fromkeys(files, "Python")
    graph = build_graph(files, langs)
    assert "pkg/b.py" in graph.imported("pkg/a.py")
    assert "pkg/c.py" in graph.imported("pkg/b.py")
    assert graph.parsed == 4


def test_external_packages_are_tracked_separately() -> None:
    files = {"app.py": "import requests\nimport os\n"}
    graph = build_graph(files, {"app.py": "Python"})
    assert "requests" in graph.external["app.py"]
    assert "os" in graph.external["app.py"]
    assert not graph.edges


def test_javascript_imports() -> None:
    files = {
        "src/app.js": "import { boot } from './boot.js';\nimport react from 'react';\n",
        "src/boot.js": "export function boot() {}\n",
    }
    langs = {"src/app.js": "JavaScript", "src/boot.js": "JavaScript"}
    graph = build_graph(files, langs)
    assert "src/boot.js" in graph.imported("src/app.js")
    assert "react" in graph.external["src/app.js"]


def test_dead_code_candidates_skip_entry_points() -> None:
    graph = ImportGraph()
    graph.add_edge("app.py", "used.py")
    dead = graph.dead_code_candidates(["app.py", "used.py", "orphan.py", "cli.py"])
    assert "orphan.py" in dead
    assert "app.py" not in dead
    assert "used.py" not in dead


def test_syntax_error_is_counted_not_raised() -> None:
    graph = build_graph({"bad.py": "def (:"}, {"bad.py": "Python"})
    assert graph.failed == 1
    assert graph.parsed == 0


def test_cycle_detection() -> None:
    graph = ImportGraph()
    graph.add_edge("a.py", "b.py")
    graph.add_edge("b.py", "a.py")
    cycles = largest_cycles(graph, limit=1)
    assert cycles
    assert "a.py" in cycles[0]


def test_public_symbols_and_dunder_all() -> None:
    import ast

    tree = ast.parse('__all__ = ["Visible"]\n\nclass Visible:\n    pass\n\n'
                     "def _hidden():\n    pass\n\ndef public():\n    pass\n")
    symbols = parse_python_symbols(tree)
    assert symbols == ["Visible", "public"]


def test_describe_graph_reports_counts() -> None:
    files = {"a.py": "import b\n", "b.py": "x = 1\n"}
    graph = build_graph(files, {"a.py": "Python", "b.py": "Python"})
    described = describe_graph(graph)
    assert described["files_parsed"] == 2
    assert described["internal_edges"] == 1
