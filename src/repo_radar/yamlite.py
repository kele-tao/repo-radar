"""YAML-lite reader for project configuration files (.radar.yml).

Deliberately a small subset: key: value pairs, quoted strings, inline lists,
block lists and one level of nesting. Anything outside that raises a friendly
error instead of guessing, because a silently ignored config key is worse than
a loud failure.
"""

from __future__ import annotations

import re

KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*(.*)$")


class ConfigError(ValueError):
    """Raised when a configuration block cannot be parsed."""


def _split_inline(inner: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    quote = ""
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
            continue
        if ch == ",":
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p for p in (x.strip() for x in parts) if p]


def _coerce_scalar(raw: str):
    text = raw.strip()
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_coerce_scalar(part) for part in _split_inline(inner)]
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    lowered = text.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if lowered in {"null", "~"}:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def parse_simple_yaml(text: str) -> dict:
    """Parse the supported YAML subset into a dict.

    Blank lines and '#' comments are skipped. Raises ConfigError with a line
    number for anything that is not a mapping entry or a list item.
    """
    data: dict = {}
    current_key: str | None = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if stripped.startswith("- ") and current_key is not None:
            item = _coerce_scalar(stripped[2:])
            existing = data.get(current_key)
            if not isinstance(existing, list):
                if existing in ("", None):
                    data[current_key] = []
                else:
                    raise ConfigError("line %d: list item without a list key" % lineno)
            data[current_key].append(item)
            continue
        match = KEY_RE.match(stripped)
        if not match:
            raise ConfigError("line %d: expected 'key: value', got %r" % (lineno, raw))
        key, value = match.group(1), match.group(2)
        if indent and current_key:
            if not isinstance(data.get(current_key), dict):
                if data.get(current_key) in ("", None):
                    data[current_key] = {}
                else:
                    data[current_key] = {"value": data[current_key]}
            data[current_key][key] = _coerce_scalar(value)
            continue
        if not value.strip():
            data[key] = ""
            current_key = key
            continue
        data[key] = _coerce_scalar(value)
        current_key = key
    return data
