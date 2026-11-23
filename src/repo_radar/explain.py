"""Module explainer: what does this file expose, and how hard is it to read?

The summary is heuristic and says so. Every element is derived from the file's
own text (AST where possible, token heuristics otherwise) - never invented.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from .languages import language_for
from .utils import read_text

DECISION_WORDS = ("if ", "elif ", "for ", "while ", "case ", "catch", "except",
                  "&&", "||", " and ", " or ", "?", "match ")
BRANCH_RE = re.compile(r"\b(if|elif|for|while|except|case|catch)\b|&&|\|\||\band\b|\bor\b")
PUBLIC_DEF_RE = re.compile(
    r"^\s*(?:export\s+)?(?:pub\s+)?(?:async\s+)?(?:def|func|fn|function|class|struct|"
    r"interface|enum|const|let)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
IMPORT_LINE_RE = re.compile(
    r"^\s*(?:import\s|from\s+\S+\s+import\s|use\s+|#include\s|require\()", re.M)


@dataclass
class Symbol:
    """A public class or function found in the module."""

    name: str
    kind: str
    line: int
    doc: str = ""
    branches: int = 0
    args: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "line": self.line,
                "doc": self.doc, "branches": self.branches, "args": self.args}


@dataclass
class Explanation:
    """The explain command's payload."""

    path: str
    language: str
    root: str = ""
    lines: int = 0
    code: int = 0
    comments: int = 0
    blanks: int = 0
    docstring: str = ""
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    public_names: list[str] = field(default_factory=list)
    private_names: list[str] = field(default_factory=list)
    complexity: int = 1
    max_function_branches: int = 0
    hardest_function: str = ""
    docstring_coverage: float = 0.0
    comment_ratio: float = 0.0
    has_main_guard: bool = False
    parse_error: str = ""
    summary: str = ""

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "language": self.language,
            "lines": self.lines,
            "code": self.code,
            "comments": self.comments,
            "blanks": self.blanks,
            "docstring": self.docstring,
            "symbols": [s.as_dict() for s in self.symbols],
            "imports": self.imports,
            "public_api": self.public_names,
            "private": self.private_names,
            "complexity": self.complexity,
            "hardest_function": self.hardest_function,
            "max_function_branches": self.max_function_branches,
            "docstring_coverage": self.docstring_coverage,
            "comment_ratio": self.comment_ratio,
            "has_main_guard": self.has_main_guard,
            "parse_error": self.parse_error,
            "summary": self.summary,
        }


def _python_branches(node: ast.AST) -> int:
    count = 0
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
                              ast.With, ast.Assert, ast.IfExp)):
            count += 1
        elif isinstance(child, ast.BoolOp):
            count += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            count += 1
    return count


def explain_python(text: str, rel: str) -> Explanation:
    """AST-accurate summary for a Python module."""
    exp = Explanation(path=rel, language="Python")
    lines = text.splitlines()
    exp.lines = len(lines)
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        exp.parse_error = "line %s: %s" % (exc.lineno, exc.msg)
        return _explain_fallback(text, rel, "Python", exp)
    exp.docstring = ast.get_docstring(tree) or ""
    documented = 0
    total_defs = 0
    exp.imports = _python_imports(tree)
    exp.has_main_guard = "if __name__ ==" in text
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            total_defs += 1
            doc = ast.get_docstring(node) or ""
            if doc:
                documented += 1
            args = [a.arg for a in node.args.args]
            branches = _python_branches(node)
            exp.symbols.append(Symbol(node.name, "function", node.lineno, doc,
                                      branches, args))
        elif isinstance(node, ast.ClassDef):
            total_defs += 1
            doc = ast.get_docstring(node) or ""
            if doc:
                documented += 1
            methods = [n for n in node.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            method_branches = sum(_python_branches(m) for m in methods)
            exp.symbols.append(Symbol(node.name, "class", node.lineno, doc,
                                      method_branches, [m.name for m in methods]))
    exp.symbols.sort(key=lambda s: s.line)
    _finish(exp, text, total_defs, documented)
    return exp


def _python_imports(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            names.extend((base + "." + a.name) if base else a.name for a in node.names)
    return sorted(dict.fromkeys(names))


def _explain_fallback(text: str, rel: str, language: str,
                      exp: Explanation | None = None) -> Explanation:
    """Regex summary for languages we do not parse with an AST."""
    exp = exp or Explanation(path=rel, language=language)
    exp.language = language
    lines = text.splitlines()
    exp.lines = len(lines)
    exp.code = sum(1 for line in lines if line.strip())
    exp.imports = sorted(dict.fromkeys(
        match.group(0).strip() for match in IMPORT_LINE_RE.finditer(text)))
    for match in PUBLIC_DEF_RE.finditer(text):
        line_no = text[:match.start()].count("\n") + 1
        exp.symbols.append(Symbol(match.group(1), "definition", line_no))
    exp.complexity = 1 + len(BRANCH_RE.findall(text))
    if exp.symbols:
        exp.hardest_function = exp.symbols[0].name
        exp.max_function_branches = exp.complexity
    exp.public_names = sorted({s.name for s in exp.symbols if not s.name.startswith("_")})
    exp.private_names = sorted({s.name for s in exp.symbols if s.name.startswith("_")})
    exp.comment_ratio = 0.0
    exp.summary = _summarise(exp)
    return exp


def _finish(exp: Explanation, text: str, total_defs: int, documented: int) -> None:
    exp.complexity = 1 + len(BRANCH_RE.findall(text))
    hardest = max(exp.symbols, key=lambda s: (s.branches, s.name), default=None)
    if hardest:
        exp.hardest_function = hardest.name
        exp.max_function_branches = hardest.branches
    exp.public_names = sorted(s.name for s in exp.symbols if not s.name.startswith("_"))
    exp.private_names = sorted(s.name for s in exp.symbols if s.name.startswith("_"))
    exp.docstring_coverage = round(100.0 * documented / total_defs, 1) if total_defs else 0.0
    comments = 0
    blanks = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            blanks += 1
        elif stripped.startswith("#"):
            comments += 1
    exp.comments = comments
    exp.blanks = blanks
    exp.code = max(0, exp.lines - comments - blanks)
    denom = max(1, exp.code + comments)
    exp.comment_ratio = round(100.0 * comments / denom, 1)
    exp.summary = _summarise(exp)


def _summarise(exp: Explanation) -> str:
    if not exp.symbols:
        return "A %s file with no public symbols; it is configuration or data." % exp.language
    kinds = {}
    for symbol in exp.symbols:
        kinds[symbol.kind] = kinds.get(symbol.kind, 0) + 1
    parts = ["%d %s%s" % (n, kind, "" if n == 1 else "s") for kind, n in sorted(kinds.items())]
    text = "A %s module exposing %s" % (exp.language, ", ".join(parts))
    if exp.public_names:
        shown = ", ".join(exp.public_names[:5])
        text += ": " + shown
        if len(exp.public_names) > 5:
            text += ", and %d more" % (len(exp.public_names) - 5)
    return text + "."


def explain_file(path: Path, root: Path | None = None) -> Explanation:
    """Explain one source file. Raises FileNotFoundError with a friendly message."""
    if not path.exists():
        raise FileNotFoundError("no such file: " + str(path))
    if path.is_dir():
        raise IsADirectoryError("expected a file, got a directory: " + str(path))
    lang = language_for(path)
    language = lang.name if lang else "Other"
    text = read_text(path)
    rel = path.name
    if root is not None:
        try:
            rel = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            rel = path.name
    if language == "Python":
        return explain_python(text, rel)
    return _explain_fallback(text, rel, language)
