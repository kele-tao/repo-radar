"""Per-project configuration: .radar.yml, .radarignore and REPO_RADAR_* env vars.

Precedence is CLI > environment > .radar.yml > .radarignore. Every source that
contributed a value is recorded so 'scan --verbose' can explain the decision.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .yamlite import ConfigError, parse_simple_yaml

CONFIG_NAME = ".radar.yml"
IGNORE_NAME = ".radarignore"
ENV_IGNORE = "REPO_RADAR_IGNORE"
ENV_FAIL_UNDER = "REPO_RADAR_FAIL_UNDER"
ENV_TOP = "REPO_RADAR_TOP"


@dataclass
class Config:
    """Effective options after merging every source."""

    root: Path
    ignore: tuple[str, ...] = ()
    fail_under: float | None = None
    top: int = 10
    sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ignore": list(self.ignore), "fail_under": self.fail_under,
                "top": self.top, "sources": self.sources, "warnings": self.warnings}


def _read_yaml(root: Path, warnings: list[str]) -> dict:
    path = root / CONFIG_NAME
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        warnings.append("cannot read %s: %s" % (CONFIG_NAME, exc))
        return {}
    try:
        return parse_simple_yaml(text)
    except ConfigError as exc:
        warnings.append("%s: %s" % (CONFIG_NAME, exc))
        return {}


def _as_float(value, warnings: list[str], source: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        warnings.append("%s: expected a number, got %r" % (source, value))
        return None


def _as_int(value, warnings: list[str], source: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        warnings.append("%s: expected an integer, got %r" % (source, value))
        return None


def load_config(root: Path, ignore: tuple[str, ...] = (),
                fail_under: float | None = None, top: int | None = None) -> Config:
    """Merge CLI arguments, environment variables and the config files."""
    warnings: list[str] = []
    sources: list[str] = []
    document = _read_yaml(root, warnings)
    if document:
        sources.append(CONFIG_NAME)

    patterns: list[str] = []
    yaml_ignore = document.get("ignore") or []
    if isinstance(yaml_ignore, str):
        yaml_ignore = [yaml_ignore]
    patterns.extend(str(p) for p in yaml_ignore)

    ignore_file = root / IGNORE_NAME
    if ignore_file.is_file():
        try:
            for line in ignore_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
            sources.append(IGNORE_NAME)
        except OSError as exc:
            warnings.append("cannot read %s: %s" % (IGNORE_NAME, exc))

    env_ignore = os.environ.get(ENV_IGNORE, "")
    if env_ignore:
        patterns.extend(p for p in (x.strip() for x in env_ignore.split(",")) if p)
        sources.append("env:" + ENV_IGNORE)
    if ignore:
        patterns.extend(ignore)
        sources.append("cli")

    if fail_under is not None:
        sources.append("cli")
    else:
        fail_under = _as_float(documented_or_none(document.get("fail_under")),
                               warnings, CONFIG_NAME) if document else None
        raw = os.environ.get(ENV_FAIL_UNDER, "")
        if raw:
            parsed = _as_float(raw, warnings, "env:" + ENV_FAIL_UNDER)
            if parsed is not None:
                fail_under = parsed
                sources.append("env:" + ENV_FAIL_UNDER)

    if top is not None:
        sources.append("cli")
    else:
        top = _as_int(documented_or_none(document.get("top")), warnings, CONFIG_NAME) \
            if document else None
        raw_top = os.environ.get(ENV_TOP, "")
        if raw_top:
            parsed_top = _as_int(raw_top, warnings, "env:" + ENV_TOP)
            if parsed_top is not None:
                top = parsed_top
                sources.append("env:" + ENV_TOP)

    return Config(
        root=root,
        ignore=tuple(dict.fromkeys(patterns)),
        fail_under=fail_under,
        top=10 if top is None else top,
        sources=sources,
        warnings=warnings,
    )


def documented_or_none(value):
    """Treat an empty YAML value ('') as absent."""
    return None if value == "" else value
