"""Small shared helpers: ANSI styling, human numbers, text tools, atomic writes."""

from __future__ import annotations

import os
import re
import sys
import unicodedata

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def color_enabled(stream=None, force: bool = False) -> bool:
    """True when colour should be emitted.

    Precedence: an explicit --colour flag, then NO_COLOR, then FORCE_COLOR,
    then whether the stream is a terminal.
    """
    if force:
        return True
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    stream = stream or sys.stdout
    return bool(getattr(stream, "isatty", lambda: False)())


class Style:
    """Minimal ANSI palette. Every method degrades to plain text."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return "\x1b[" + code + "m" + text + "\x1b[0m"

    def bold(self, t: str) -> str:
        return self._wrap(t, "1")

    def dim(self, t: str) -> str:
        return self._wrap(t, "2")

    def red(self, t: str) -> str:
        return self._wrap(t, "31")

    def green(self, t: str) -> str:
        return self._wrap(t, "32")

    def yellow(self, t: str) -> str:
        return self._wrap(t, "33")

    def blue(self, t: str) -> str:
        return self._wrap(t, "34")

    def magenta(self, t: str) -> str:
        return self._wrap(t, "35")

    def cyan(self, t: str) -> str:
        return self._wrap(t, "36")

    def grade(self, score: float) -> str:
        """Colour a 0-100 score by band."""
        if score >= 80:
            return self.green("%d" % round(score))
        if score >= 60:
            return self.yellow("%d" % round(score))
        return self.red("%d" % round(score))


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def human_size(num: int) -> str:
    """1234 -> '1.2 KB'. Keeps output stable across platforms."""
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return "%d B" % int(value)
            return "%.1f %s" % (value, unit)
        value /= 1024
    return "%.1f GB" % value


def human_int(num: int) -> str:
    """Group digits with commas so big numbers stay readable."""
    return format(int(num), ",")


def pct(part: float, whole: float) -> float:
    """Percentage rounded to one decimal, safe for whole == 0."""
    if whole <= 0:
        return 0.0
    return round(100.0 * part / whole, 1)


def truncate(text: str, width: int) -> str:
    """Truncate by display width, never splitting a wide character."""
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    out = []
    used = 0
    for ch in text:
        w = 2 if unicodedata.east_asian_width(ch) in {"W", "F"} else 1
        if used + w > width - 1:
            break
        out.append(ch)
        used += w
    return "".join(out) + "\u2026"


def display_width(text: str) -> int:
    """Monospace display width: CJK counts as two columns, zero-width as zero."""
    width = 0
    for ch in text:
        if unicodedata.combining(ch) or ch in "\u200b\u200c\u200d\ufeff":
            continue
        width += 2 if unicodedata.east_asian_width(ch) in {"W", "F"} else 1
    return width


def pad(text: str, width: int) -> str:
    """Left-align text in a display-width aware cell."""
    gap = width - display_width(text)
    return text + " " * gap if gap > 0 else truncate(text, width)


def bar(score: float, width: int = 20, filled: str = "\u2588", empty: str = "\u2591") -> str:
    """Text progress bar used in the terminal dashboard."""
    ratio = max(0.0, min(100.0, score)) / 100.0
    n = round(ratio * width)
    return filled * n + empty * (width - n)


def stable_sort_key(text: str):
    """Deterministic, locale-independent ordering key."""
    return text.encode("utf-8")


def decode_bytes(data: bytes) -> str:
    """Decode bytes with BOM tolerance; never raises on bad bytes."""
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def read_text(path) -> str:
    """Read a text file with BOM tolerance; never raises on bad bytes."""
    return decode_bytes(path.read_bytes())


def write_text(path, text: str) -> None:
    """Write UTF-8 text, creating parent directories, newline deterministic."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def plural(n: int, singular: str, plural_form: str | None = None) -> str:
    """'1 file' / '3 files'."""
    if n == 1:
        return "%d %s" % (n, singular)
    return "%d %s" % (n, plural_form or singular + "s")
