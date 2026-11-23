"""One fast AST pass per Python module.

Both the import-graph builder and the AST rules need information from the same
parse tree, and a naive implementation walks that tree twice. Here a single
iterative traversal collects everything both consumers need, and the result is
memoised per (path, text).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

_KEY = tuple[str, int, int]
_CACHE: dict[_KEY, ModuleFacts] = {}


@dataclass
class ModuleFacts:
    """Everything repo-radar extracts from one Python module."""

    tree: ast.AST | None = None
    error: str = ""
    imports: list[tuple[int, str, tuple[str, ...]]] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    asserts: list[int] = field(default_factory=list)
    bare_except_pass: list[int] = field(default_factory=list)
    mutable_defaults: list[tuple[str, int]] = field(default_factory=list)
    wildcard_imports: list[tuple[str, int]] = field(default_factory=list)
    nodes: int = 0


def reset_cache() -> None:
    """Forget every parsed module. Called at the start of each scan."""
    _CACHE.clear()


def _key(rel: str, text: str) -> _KEY:
    return (rel, len(text), hash(text))


def _module_symbols(tree: ast.AST) -> list[str]:
    """Public module-level classes and functions, plus __all__ entries."""
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
                        names.extend(str(item) for item in value)
    return sorted(set(names))


def _mutable_defaults(node, facts: ModuleFacts) -> None:
    args = list(node.args.args)
    defaults = list(node.args.defaults)
    if not defaults:
        return
    for arg, default in zip(args[len(args) - len(defaults):], defaults, strict=False):
        if isinstance(default, (ast.List, ast.Dict, ast.Set)):
            facts.mutable_defaults.append((arg.arg, node.lineno))


def _bare_except(node, facts: ModuleFacts) -> None:
    body = node.body
    if node.type is None and len(body) == 1 and isinstance(body[0], ast.Pass):
        facts.bare_except_pass.append(node.lineno)


def _collect(tree: ast.AST, facts: ModuleFacts) -> None:
    """Single iterative traversal; dispatch on the exact node type."""
    imports = facts.imports
    asserts = facts.asserts
    wildcards = facts.wildcard_imports
    stack = [tree]
    push = stack.append
    pop = stack.pop
    for child_of in (ast.iter_child_nodes,):
        while stack:
            node = pop()
            facts.nodes += 1
            kind = type(node)
            if kind is ast.Import:
                for alias in node.names:
                    imports.append((0, alias.name, ()))
            elif kind is ast.ImportFrom:
                names = tuple(alias.name for alias in node.names)
                imports.append((node.level, node.module or "", names))
                if "*" in names:
                    wildcards.append((node.module or "", node.lineno))
            elif kind is ast.Assert:
                asserts.append(node.lineno)
            elif kind is ast.ExceptHandler:
                _bare_except(node, facts)
            elif kind is ast.FunctionDef or kind is ast.AsyncFunctionDef:
                _mutable_defaults(node, facts)
            for child in child_of(node):
                push(child)


def summarize(rel: str, text: str) -> ModuleFacts:
    """Parse and analyse one module, memoised per (path, text)."""
    key = _key(rel, text)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    facts = ModuleFacts()
    try:
        facts.tree = ast.parse(text)
    except (SyntaxError, ValueError) as exc:
        facts.error = str(exc) or "syntax error"
        _CACHE[key] = facts
        return facts
    facts.symbols = _module_symbols(facts.tree)
    _collect(facts.tree, facts)
    _CACHE[key] = facts
    return facts


def cache_size() -> int:
    """Number of analysed modules currently held (used by tests)."""
    return len(_CACHE)
