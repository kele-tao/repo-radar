"""Deterministic file walking with gitignore-lite filtering and bounded reads."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .languages import DEFAULT_IGNORE, is_binary_name, is_ignored, language_for
from .utils import decode_bytes, read_text

MAX_FILE_BYTES = 2 * 1024 * 1024


@dataclass
class WalkOptions:
    """User-controllable collection policy."""

    ignore: tuple[str, ...] = ()
    use_gitignore: bool = True
    max_file_bytes: int = MAX_FILE_BYTES
    follow_symlinks: bool = False

    def patterns(self, root: Path) -> tuple[str, ...]:
        pats = list(self.ignore)
        if self.use_gitignore:
            pats.extend(load_gitignore(root))
        return tuple(pats)


@dataclass
class FileInfo:
    """One candidate file discovered on disk."""

    path: Path
    rel: str
    size: int
    language: str = "Unknown"
    category: str = "other"
    executable: bool = False
    line_comment: str | None = None
    block: tuple[str, str] | None = None
    lines: int = 0
    code: int = 0
    comments: int = 0
    blanks: int = 0
    skipped_reason: str | None = None
    text: str = field(default="", repr=False)


def load_gitignore(root: Path) -> list[str]:
    """Read the root .gitignore into simple patterns (no nested files, by design)."""
    path = root / ".gitignore"
    if not path.is_file():
        return []
    try:
        raw = read_text(path)
    except OSError:
        return []
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        out.append(line)
    return out


def iter_files(root: Path, options: WalkOptions | None = None) -> list[FileInfo]:
    """List every non-ignored file below *root*, sorted by relative path.

    Unreadable entries are kept with a skip reason instead of raising: the radar
    has to survive scanning a half-broken checkout.
    """
    opts = options or WalkOptions()
    patterns = opts.patterns(root)
    found: list[FileInfo] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=opts.follow_symlinks):
        current = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if d not in DEFAULT_IGNORE)
        for name in sorted(filenames):
            path = current / name
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:  # pragma: no cover - defensive
                continue
            if is_ignored(rel, patterns) or rel in patterns:
                continue
            if is_binary_name(name):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                found.append(FileInfo(path=path, rel=rel, size=0, skipped_reason="unreadable"))
                continue
            lang = language_for(path)
            info = FileInfo(
                path=path,
                rel=rel,
                size=size,
                language=lang.name if lang else "Other",
                category=lang.category if lang else "other",
                executable=bool(lang and lang.executable),
                line_comment=lang.line_comment if lang else None,
                block=lang.block if lang else None,
            )
            if size > opts.max_file_bytes:
                info.skipped_reason = "too-large"
            found.append(info)
    found.sort(key=lambda f: f.rel)
    return found


def looks_binary(data: bytes) -> bool:
    """True when a sample contains NUL bytes, which no source file does."""
    return b"\x00" in data[:8192]


def load_text(info: FileInfo, max_bytes: int = MAX_FILE_BYTES) -> str:
    """Read a file's text once, remembering the result on the FileInfo."""
    if info.text:
        return info.text
    if info.skipped_reason:
        return ""
    if info.size > max_bytes:
        info.skipped_reason = "too-large"
        return ""
    try:
        data = info.path.read_bytes()
    except OSError:
        info.skipped_reason = "unreadable"
        return ""
    if looks_binary(data):
        info.skipped_reason = "binary"
        return ""
    info.text = decode_bytes(data)
    return info.text


def count_lines(text: str, info: FileInfo) -> None:
    """Fill LOC counters: total, code, comment and blank lines."""
    lines = text.splitlines()
    info.lines = len(lines)
    comment = 0
    blank = 0
    code = 0
    in_block = False
    open_tok, close_tok = info.block if info.block else ("", "")
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            blank += 1
            continue
        if in_block:
            comment += 1
            if close_tok and close_tok in stripped:
                in_block = False
            continue
        if open_tok and stripped.startswith(open_tok):
            comment += 1
            remainder = stripped[len(open_tok):]
            if close_tok and close_tok not in remainder:
                in_block = True
            continue
        if info.line_comment and stripped.startswith(info.line_comment):
            comment += 1
            continue
        code += 1
    info.comments = comment
    info.blanks = blank
    info.code = code
