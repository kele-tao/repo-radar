"""Extension -> language mapping, category classification and comment syntax.

The table is deliberately explicit: an unknown extension is a fact, not a guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path


@dataclass(frozen=True)
class Language:
    """A language the radar can measure."""

    name: str
    category: str          # code | markup | data | config | docs | style | shell | other
    line_comment: str | None = None
    block: tuple[str, str] | None = None
    executable: bool = False   # counts toward source-code LOC


LANGUAGES: dict[str, Language] = {}


def _reg(name: str, category: str, exts: tuple[str, ...], line=None, block=None,
         executable: bool | None = None) -> None:
    lang = Language(
        name=name,
        category=category,
        line_comment=line,
        block=block,
        executable=executable if executable is not None else category == "code",
    )
    for ext in exts:
        LANGUAGES[ext] = lang


_reg("Python", "code", (".py", ".pyi"), "#", ('"""', '"""'))
_reg("JavaScript", "code", (".js", ".mjs", ".cjs", ".jsx"), "//", ("/*", "*/"))
_reg("TypeScript", "code", (".ts", ".tsx", ".mts", ".cts"), "//", ("/*", "*/"))
_reg("Go", "code", (".go",), "//", ("/*", "*/"))
_reg("Rust", "code", (".rs",), "//", ("/*", "*/"))
_reg("Java", "code", (".java",), "//", ("/*", "*/"))
_reg("Kotlin", "code", (".kt", ".kts"), "//", ("/*", "*/"))
_reg("C", "code", (".c", ".h"), "//", ("/*", "*/"))
_reg("C++", "code", (".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx"), "//", ("/*", "*/"))
_reg("C#", "code", (".cs",), "//", ("/*", "*/"))
_reg("Ruby", "code", (".rb",), "#", ("=begin", "=end"))
_reg("PHP", "code", (".php",), "//", ("/*", "*/"))
_reg("Swift", "code", (".swift",), "//", ("/*", "*/"))
_reg("Scala", "code", (".scala",), "//", ("/*", "*/"))
_reg("Elixir", "code", (".ex", ".exs"), "#", None)
_reg("Lua", "code", (".lua",), "--", ("--[[", "]]"))
_reg("Shell", "shell", (".sh", ".bash", ".zsh", ".fish"), "#", None)
_reg("PowerShell", "shell", (".ps1", ".psm1"), "#", ("<#", "#>"))
_reg("SQL", "data", (".sql",), "--", ("/*", "*/"), executable=False)
_reg("HTML", "markup", (".html", ".htm"), None, ("<!--", "-->"), executable=False)
_reg("Vue", "markup", (".vue",), "//", ("<!--", "-->"))
_reg("Svelte", "markup", (".svelte",), "//", ("<!--", "-->"))
_reg("CSS", "style", (".css",), None, ("/*", "*/"), executable=False)
_reg("SCSS", "style", (".scss", ".sass", ".less"), "//", ("/*", "*/"), executable=False)
_reg("JSON", "data", (".json", ".jsonc", ".json5", ".geojson"), None, None, executable=False)
_reg("YAML", "data", (".yml", ".yaml"), "#", None, executable=False)
_reg("TOML", "data", (".toml",), "#", None, executable=False)
_reg("INI", "data", (".ini", ".cfg", ".conf", ".properties"), "#", None, executable=False)
_reg("XML", "data", (".xml", ".plist", ".xaml"), None, ("<!--", "-->"), executable=False)
_reg("GraphQL", "data", (".graphql", ".gql"), "#", None, executable=False)
_reg("Protobuf", "data", (".proto",), "//", None, executable=False)
_reg("Markdown", "docs", (".md", ".mdx", ".markdown"), None, ("<!--", "-->"), executable=False)
_reg("reStructuredText", "docs", (".rst",), None, None, executable=False)
_reg("Text", "docs", (".txt",), None, None, executable=False)
_reg("Dockerfile", "config", (".dockerfile",), "#", None, executable=False)
_reg("Jupyter", "data", (".ipynb",), None, None, executable=False)

FILENAME_LANGUAGES = {
    "Dockerfile": Language("Dockerfile", "config", "#", None, False),
    "Makefile": Language("Makefile", "config", "#", None, False),
    "makefile": Language("Makefile", "config", "#", None, False),
    "GNUmakefile": Language("Makefile", "config", "#", None, False),
    "CMakeLists.txt": Language("CMake", "config", "#", None, False),
    "Rakefile": Language("Ruby", "code", "#", None, True),
    "Gemfile": Language("Ruby", "config", "#", None, False),
    "Procfile": Language("Config", "config", "#", None, False),
    "Jenkinsfile": Language("Groovy", "code", "//", None, True),
}

CATEGORY_COLORS = {
    "code": "#4ade80",
    "shell": "#fbbf24",
    "markup": "#f97316",
    "style": "#a78bfa",
    "data": "#38bdf8",
    "config": "#94a3b8",
    "docs": "#e2e8f0",
    "other": "#64748b",
}


def language_for(path: Path) -> Language | None:
    """Detect the language of *path* from its name or suffix.

    Returns None for binary or unknown files, which are then counted but not read.
    """
    if path.name in FILENAME_LANGUAGES:
        return FILENAME_LANGUAGES[path.name]
    suffix = path.suffix.lower()
    if suffix in LANGUAGES:
        return LANGUAGES[suffix]
    if path.name.startswith("Dockerfile."):
        return Language("Dockerfile", "config", "#", None, False)
    return None


def is_binary_name(name: str) -> bool:
    """Cheap extension check for files no scanner should ever read."""
    lower = name.lower()
    return lower.endswith((
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff",
        ".pdf", ".zip", ".gz", ".tar", ".bz2", ".xz", ".7z", ".rar",
        ".exe", ".dll", ".so", ".dylib", ".o", ".a", ".class", ".jar",
        ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".mov",
        ".avi", ".webm", ".sqlite", ".db", ".pyc", ".pth", ".node", ".wasm",
    ))


DEFAULT_IGNORE = (
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".env", ".tox", ".nox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".idea", ".vscode", "dist", "build", "target", "out",
    "coverage", ".next", ".nuxt", ".cache", "vendor", "bower_components",
    ".gradle", ".DS_Store", "htmlcov", "site-packages", ".terraform",
)


def is_ignored(rel_posix: str, patterns: tuple[str, ...] = ()) -> bool:
    """Gitignore-lite: directory names, '*.ext', 'prefix/' and glob patterns."""
    parts = rel_posix.split("/")
    for part in parts[:-1]:
        if part in DEFAULT_IGNORE:
            return True
    name = parts[-1]
    if name in DEFAULT_IGNORE:
        return True
    for raw in patterns:
        pattern = raw.strip()
        if not pattern or pattern.startswith("!"):
            continue
        pattern = pattern.rstrip("/")
        if pattern in parts[:-1] or pattern == name:
            return True
        if "/" in pattern:
            if fnmatchcase(rel_posix, pattern) or fnmatchcase(rel_posix, pattern + "/*"):
                return True
        elif fnmatchcase(name, pattern):
            return True
    return False
