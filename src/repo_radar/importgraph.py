"""Static import graph for Python and the common JS/TS/Go/Rust styles.

Only what the radar needs: does file A reference file B, and which modules are
never referenced. Parsing is defensive - a syntax error is a data point, not a
crash.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .pyast import summarize

JS_IMPORT_RE = re.compile(
    r"""(?:^|\n)\s*(?:import\s+(?:[^'"]*?\s+from\s+)?|export\s+[^'"]*?\s+from\s+|require\(\s*)['"]([^'"]+)['"]"""
)
GO_IMPORT_RE = re.compile(r"""^\s*(?:import\s+)?(?:\(\s*)?"([a-z0-9_./-]+)"\s*\)?\s*$""", re.M)
RS_USE_RE = re.compile(r"^\s*(?:pub\s+)?(?:use|mod)\s+(?:crate::|super::)?([A-Za-z0-9_:]+)", re.M)
RS_MOD_RE = re.compile(r"^\s*(?:pub\s+)?mod\s+([a-z0-9_]+)\s*;", re.M)
PY_DEF_RE = re.compile(r"^(?:async\s+)?def\s+(\w+)|^class\s+(\w+)", re.M)

ENTRY_NAMES = {
    "__init__.py", "__main__.py", "main.py", "cli.py", "conftest.py",
    "setup.py", "manage.py", "wsgi.py", "asgi.py", "app.py", "index.js",
    "index.ts", "main.go", "main.rs", "lib.rs", "svc.py",
}
ENTRY_DIR_HINTS = ("tests/", "test/", "scripts/", "bin/", "examples/", "benchmarks/",
                   "docs/", "migrations/", "tools/")


@dataclass
class ImportGraph:
    """Directed graph of internal file references plus per-file public symbols."""

    edges: dict[str, set[str]] = field(default_factory=dict)
    reverse: dict[str, set[str]] = field(default_factory=dict)
    external: dict[str, set[str]] = field(default_factory=dict)
    symbols: dict[str, list[str]] = field(default_factory=dict)
    parsed: int = 0
    failed: int = 0

    def add_edge(self, src: str, dst: str) -> None:
        if src == dst:
            return
        self.edges.setdefault(src, set()).add(dst)
        self.reverse.setdefault(dst, set()).add(src)

    def add_external(self, src: str, name: str) -> None:
        self.external.setdefault(src, set()).add(name)

    def importers(self, rel: str) -> set[str]:
        return set(self.reverse.get(rel, set()))

    def imported(self, rel: str) -> set[str]:
        return set(self.edges.get(rel, set()))

    def dead_code_candidates(self, code_files: list[str]) -> list[str]:
        """Files with no internal importer and no entry-point excuse."""
        out = []
        for rel in code_files:
            if self.reverse.get(rel):
                continue
            name = PurePosixPath(rel).name
            if name in ENTRY_NAMES:
                continue
            if any(rel.startswith(hint) or ("/" + hint) in rel for hint in ENTRY_DIR_HINTS):
                continue
            out.append(rel)
        return sorted(out)


def _module_candidates(module: str) -> list[str]:
    base = module.replace(".", "/")
    return [base + ".py", base + "/__init__.py", base + ".pyi"]


def _python_source_roots(files: dict[str, str]) -> list[str]:
    """Guess sys.path roots: '', 'src', and every top-level package parent."""
    roots = {""}
    for rel in files:
        parts = rel.split("/")
        if parts[0] in {"src", "lib", "python"} and len(parts) > 1:
            roots.add("/".join(parts[:1]))
        if len(parts) > 2 and rel.endswith("__init__.py"):
            roots.add("/".join(parts[:-2]))
    return sorted(roots, key=len)


def _resolve_path(src_rel: str, spec: str, files: dict[str, str]) -> str | None:
    """Resolve a relative './x' or '../x' specifier against the importing file."""
    base = PurePosixPath(src_rel).parent
    parts = list(base.parts)
    for piece in spec.split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            if parts:
                parts.pop()
            continue
        parts.append(piece)
    target = "/".join(parts)
    candidates = [target]
    tail = target.rsplit("/", 1)[-1]
    stem = target[: len(target) - len(tail)] + tail.rsplit(".", 1)[0] if "." in tail else target
    for suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rs"):
        candidates.append(stem + suffix)
    for suffix in ("/index.ts", "/index.js", "/index.tsx", "/__init__.py"):
        candidates.append(stem + suffix)
    for candidate in candidates:
        candidate = candidate.lstrip("/")
        if candidate in files:
            return candidate
    return None


def _resolve_python(module: str, files: dict[str, str], roots: list[str]) -> str | None:
    for root in roots:
        for suffix in _module_candidates(module):
            candidate = (root + "/" + suffix).lstrip("/")
            if candidate in files:
                return candidate
    return None


def _join_module(module: str, name: str) -> str:
    """Join a dotted module spec and a member name without doubling the dot."""
    if not module:
        return name
    return module + ("" if module.endswith(".") else ".") + name


def _resolve_relative(src_rel: str, module: str, files: dict[str, str]) -> str | None:
    base = PurePosixPath(src_rel).parent
    text = module.lstrip(".")
    ups = len(module) - len(module.lstrip("."))
    for _ in range(max(0, ups - 1)):
        base = base.parent
    target = (base / text.replace(".", "/")) if text else base
    for suffix in ("", ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rs", "/index.ts",
                   "/index.js", "/__init__.py", ".pyi"):
        candidate = (str(target) + suffix).lstrip("/")
        if candidate in files:
            return candidate
    return None


def parse_python_symbols(tree: ast.AST) -> list[str]:
    """Module-level classes, functions and __all__ entries (public API evidence)."""
    names: list[str] = []
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    try:
                        value = ast.literal_eval(node.value)
                    except (ValueError, SyntaxError):
                        continue
                    if isinstance(value, (list, tuple)):
                        names.extend(str(v) for v in value)
    return sorted(set(names))


def build_graph(files: dict[str, str], languages: dict[str, str]) -> ImportGraph:
    """Build the internal import graph for a mapping of rel path -> text."""
    graph = ImportGraph()
    roots = _python_source_roots(files)
    lookup = set(files)
    for rel in sorted(files):
        text = files[rel]
        lang = languages.get(rel, "")
        if lang == "Python":
            facts = summarize(rel, text)
            if facts.tree is None:
                graph.failed += 1
                continue
            graph.parsed += 1
            graph.symbols[rel] = list(facts.symbols)
            for level, module, names in facts.imports:
                if level:
                    target = _resolve_relative(rel, "." * level + module, lookup)
                    if target:
                        graph.add_edge(rel, target)
                    for alias in names:
                        sub = _resolve_relative(rel, "." * level + _join_module(module, alias),
                                                lookup)
                        if sub:
                            graph.add_edge(rel, sub)
                    continue
                if not module:
                    continue
                target = _resolve_python(module, lookup, roots)
                if target:
                    graph.add_edge(rel, target)
                else:
                    graph.add_external(rel, module.split(".")[0])
                for alias in names:
                    sub = _resolve_python(_join_module(module, alias), lookup, roots)
                    if sub:
                        graph.add_edge(rel, sub)
        elif lang in {"JavaScript", "TypeScript"}:
            graph.parsed += 1
            for match in JS_IMPORT_RE.finditer(text):
                spec = match.group(1)
                if spec.startswith("."):
                    target = _resolve_path(rel, spec, lookup)
                    if target:
                        graph.add_edge(rel, target)
                elif not spec.startswith(("http://", "https://")):
                    graph.add_external(rel, spec.split("/")[0].lstrip("@") or spec)
            export_re = (r"^export\s+(?:default\s+)?(?:async\s+)?"
                         r"(?:function|class|const|let)\s+(\w+)")
            graph.symbols[rel] = sorted(set(re.findall(export_re, text, re.M)))
        elif lang == "Go":
            graph.parsed += 1
            package_dir = rel.rsplit("/", 1)[0] if "/" in rel else ""
            for match in GO_IMPORT_RE.finditer(text):
                spec = match.group(1)
                tail = spec.rsplit("/", 1)[-1]
                for candidate in lookup:
                    if candidate.startswith(package_dir) and candidate.endswith("/" + tail + ".go"):
                        graph.add_edge(rel, candidate)
            graph.symbols[rel] = sorted(set(re.findall(r"^func\s+([A-Z]\w+)", text, re.M)))
        elif lang == "Rust":
            graph.parsed += 1
            for match in RS_MOD_RE.finditer(text):
                base = rel.rsplit("/", 1)[0] if "/" in rel else ""
                for candidate in (base + "/" + match.group(1) + ".rs",
                                  base + "/" + match.group(1) + "/mod.rs"):
                    candidate = candidate.lstrip("/")
                    if candidate in lookup:
                        graph.add_edge(rel, candidate)
            pub_re = r"^pub\s+(?:fn|struct|enum|trait)\s+(\w+)"
            graph.symbols[rel] = sorted(set(re.findall(pub_re, text, re.M)))
        else:
            graph.symbols[rel] = []
    return graph


def describe_graph(graph: ImportGraph) -> dict:
    """Compact statistics for the report and JSON payload."""
    nodes = set(graph.edges) | set(graph.reverse)
    edge_count = sum(len(v) for v in graph.edges.values())
    return {
        "files_parsed": graph.parsed,
        "parse_failures": graph.failed,
        "modules_in_graph": len(nodes),
        "internal_edges": edge_count,
        "external_packages": sorted({n for names in graph.external.values() for n in names}),
    }


def largest_cycles(graph: ImportGraph, limit: int = 1) -> list[list[str]]:
    """Find simple import cycles with an iterative DFS (bounded output)."""
    WHITE, GREY, BLACK = 0, 1, 2
    state: dict[str, int] = dict.fromkeys(graph.edges, WHITE)
    cycles: list[list[str]] = []
    seen: set[frozenset] = set()

    def visit(node: str, path: list[str]) -> None:
        if len(cycles) >= limit:
            return
        state[node] = GREY
        path.append(node)
        for nxt in sorted(graph.edges.get(node, ())):
            if state.get(nxt, WHITE) == GREY:
                idx = path.index(nxt)
                cycle = [*path[idx:], nxt]
                key = frozenset(cycle)
                if key not in seen:
                    seen.add(key)
                    cycles.append(cycle)
            elif state.get(nxt, WHITE) == WHITE:
                visit(nxt, path)
            if len(cycles) >= limit:
                break
        path.pop()
        state[node] = BLACK

    for start in sorted(state):
        if state[start] == WHITE:
            visit(start, [])
        if len(cycles) >= limit:
            break
    return cycles
