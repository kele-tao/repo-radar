"""Ecosystem and manifest detection: what kind of project is this, exactly?

Detection is evidence-based. Each entry point, test framework and dependency we
report points at the file that proves it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .utils import read_text

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on 3.10 only
    tomllib = None

REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
VERSION_SPEC_RE = re.compile(r"(==|>=|<=|~=|!=|>|<)")


@dataclass
class Manifest:
    """One build/dependency descriptor found in the tree."""

    path: str
    kind: str
    dependencies: list[str] = field(default_factory=list)
    dev_dependencies: list[str] = field(default_factory=list)
    pinned: int = 0
    entry_points: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class Ecosystem:
    """Everything the radar knows about the project's tooling."""

    manifests: list[Manifest] = field(default_factory=list)
    ecosystems: list[str] = field(default_factory=list)
    entry_points: list[tuple[str, str]] = field(default_factory=list)
    test_frameworks: list[str] = field(default_factory=list)
    ci_systems: list[str] = field(default_factory=list)
    has_docker: bool = False
    has_lockfile: bool = False
    has_readme: bool = False
    has_license: bool = False
    has_tests_dir: bool = False
    has_ci: bool = False
    has_pre_commit: bool = False
    has_type_hints_marker: bool = False
    dependency_total: int = 0
    dependency_pinned: int = 0

    @property
    def pin_ratio(self) -> float:
        if not self.dependency_total:
            return 100.0
        return round(100.0 * self.dependency_pinned / self.dependency_total, 1)

    def as_dict(self) -> dict:
        return {
            "ecosystems": self.ecosystems,
            "entry_points": [{"path": p, "kind": k} for p, k in self.entry_points],
            "test_frameworks": self.test_frameworks,
            "ci_systems": self.ci_systems,
            "manifests": [m.path for m in self.manifests],
            "has_docker": self.has_docker,
            "has_lockfile": self.has_lockfile,
            "has_readme": self.has_readme,
            "has_license": self.has_license,
            "has_tests_dir": self.has_tests_dir,
            "has_ci": self.has_ci,
            "has_pre_commit": self.has_pre_commit,
            "dependencies": self.dependency_total,
            "pinned_dependencies": self.dependency_pinned,
            "pin_ratio": self.pin_ratio,
        }


def _load_toml(text: str) -> dict:
    if tomllib is not None:
        try:
            return tomllib.loads(text)
        except Exception:
            return {}
    data: dict = {}
    section = ""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        header = re.match(r"^\[([^\]]+)\]$", line.strip())
        if header:
            section = header.group(1)
            data.setdefault(section, {})
            continue
        kv = re.match(r"^([A-Za-z0-9_.\"-]+)\s*=\s*(.+)$", line.strip())
        if not kv:
            continue
        key, value = kv.group(1).strip('"'), kv.group(2).strip()
        if value.startswith("[") and value.endswith("]"):
            data.setdefault(section, {})[key] = [
                v.strip().strip('"').strip("'")
                for v in value[1:-1].split(",") if v.strip()
            ]
        else:
            data.setdefault(section, {})[key] = value.strip('"').strip("'")
    return data


def _parse_requirements(text: str, kind: str, path: str) -> Manifest:
    deps: list[str] = []
    pinned = 0
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = REQ_NAME_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        if name.lower() in {"git", "http", "https"}:
            continue
        deps.append(name)
        if VERSION_SPEC_RE.search(line):
            pinned += 1
    return Manifest(path=path, kind=kind, dependencies=deps, pinned=pinned)


NAME_ONLY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")


def dependency_name(raw: str) -> str:
    """'requests[socks]>=2.0; python_version>"3.8"' -> 'requests'."""
    head = raw.split(";")[0].strip()
    match = NAME_ONLY_RE.match(head)
    return match.group(0) if match else head


def _parse_pyproject(text: str, path: str) -> Manifest:
    data = _load_toml(text)
    project = data.get("project", {}) if isinstance(data.get("project", {}), dict) else {}
    declared = project.get("dependencies", [])
    deps = [dependency_name(str(d)) for d in declared]
    deps = [d for d in deps if d]
    pinned = sum(1 for raw in declared if VERSION_SPEC_RE.search(str(raw)))
    dev: list[str] = []
    optional = project.get("optional-dependencies", {})
    if isinstance(optional, dict):
        for names in optional.values():
            dev.extend(dependency_name(str(d)) for d in names)
    tool = data.get("tool", {})
    poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}
    if isinstance(poetry, dict):
        for key in ("dependencies", "dev-dependencies"):
            block = poetry.get(key, {})
            if isinstance(block, dict):
                for name in block:
                    if name.lower() == "python":
                        continue
                    deps.append(name)
                    pinned += 1
    scripts = project.get("scripts", {})
    entry = (["%s = %s" % (k, v) for k, v in scripts.items()]
             if isinstance(scripts, dict) else [])
    return Manifest(path=path, kind="pyproject.toml", dependencies=deps,
                    dev_dependencies=dev, pinned=pinned, entry_points=entry)


def _parse_package_json(text: str, path: str) -> Manifest | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    deps = sorted(data.get("dependencies", {}) or {})
    dev = sorted(data.get("devDependencies", {}) or {})
    pinned = sum(1 for v in list((data.get("dependencies") or {}).values())
                 if not str(v).startswith(("^", "~", "*", ">", "<")))
    entry: list[str] = []
    main = data.get("main")
    if main:
        entry.append("main = " + str(main))
    scripts = data.get("scripts", {})
    if isinstance(scripts, dict) and "start" in scripts:
        entry.append("start = " + str(scripts["start"]))
    return Manifest(path=path, kind="package.json", dependencies=deps,
                    dev_dependencies=dev, pinned=pinned, entry_points=entry)


def _parse_go_mod(text: str, path: str) -> Manifest:
    deps = [line.split()[0] for line in text.splitlines()
            if line.startswith("\t") and len(line.split()) >= 2]
    return Manifest(path=path, kind="go.mod", dependencies=deps, pinned=len(deps))


def _parse_cargo(text: str, path: str) -> Manifest:
    data = _load_toml(text)
    raw_deps = data.get("dependencies")
    deps = sorted(raw_deps.keys()) if isinstance(raw_deps, dict) else []
    bins = data.get("bin", [])
    return Manifest(path=path, kind="Cargo.toml", dependencies=deps, pinned=len(deps),
                    entry_points=["bin: %d" % len(bins)] if bins else [])


def detect(root: Path, all_paths: list[str]) -> Ecosystem:
    """Inspect manifests and conventions under *root*."""
    eco = Ecosystem()
    as_set = set(all_paths)
    names = {p.rsplit("/", 1)[-1] for p in all_paths}
    # First (shallowest, then alphabetical) path for every basename, so a
    # manifest in a subdirectory is still read from its real location.
    located: dict[str, str] = {}
    for rel in sorted(all_paths, key=lambda p: (p.count("/"), p)):
        located.setdefault(rel.rsplit("/", 1)[-1], rel)

    if "pyproject.toml" in names:
        where = located["pyproject.toml"]
        manifest = _parse_pyproject(read_text(root / where), where)
        eco.manifests.append(manifest)
        eco.ecosystems.append("Python (pyproject)")
        for entry in manifest.entry_points:
            eco.entry_points.append(("pyproject.toml", entry))
    if "setup.py" in names or "setup.cfg" in names:
        eco.ecosystems.append("Python (setuptools)")
        legacy = "setup.py" if "setup.py" in names else "setup.cfg"
        eco.entry_points.append((legacy, "legacy package"))
    if "requirements.txt" in names:
        where = located["requirements.txt"]
        eco.manifests.append(_parse_requirements(
            read_text(root / where), "requirements.txt", where))
        eco.ecosystems.append("Python (requirements)")
    if "package.json" in names:
        where = located["package.json"]
        parsed = _parse_package_json(read_text(root / where), where)
        if parsed:
            eco.manifests.append(parsed)
            eco.ecosystems.append("Node")
            for entry in parsed.entry_points:
                eco.entry_points.append(("package.json", entry))
    if "go.mod" in names:
        where = located["go.mod"]
        eco.manifests.append(_parse_go_mod(read_text(root / where), where))
        eco.ecosystems.append("Go")
        go_mains = [p for p in all_paths if p.endswith(".go") and p.count("/") <= 2]
        for path in go_mains:
            if not (root / path).is_file():
                continue
            if re.search(r"^package main", read_text(root / path), re.M):
                eco.entry_points.append((path, "go main package"))
    if "Cargo.toml" in names:
        where = located["Cargo.toml"]
        eco.manifests.append(_parse_cargo(read_text(root / where), where))
        eco.ecosystems.append("Rust")
        for path in all_paths:
            if path.endswith("main.rs"):
                eco.entry_points.append((path, "rust binary"))
    if "pom.xml" in names:
        eco.ecosystems.append("Java (maven)")
        eco.manifests.append(Manifest(path="pom.xml", kind="pom.xml"))
    if "build.gradle" in names or "build.gradle.kts" in names:
        eco.ecosystems.append("JVM (gradle)")
    if "Makefile" in names:
        eco.entry_points.append(("Makefile", "make targets"))
    for name in ("Dockerfile", "docker-compose.yml", "compose.yml"):
        if name in names:
            eco.has_docker = True
            eco.entry_points.append((name, "container build"))
            break
    if any(n in names for n in ("poetry.lock", "package-lock.json", "yarn.lock",
                                "pnpm-lock.yaml", "Cargo.lock", "go.sum",
                                "requirements.lock")) or "requirements.txt" in names:
        eco.has_lockfile = True
    eco.has_readme = any(n.lower().startswith("readme") for n in names)
    eco.has_license = any(n.upper().startswith(("LICENSE", "LICENCE", "COPYING"))
                          for n in names)
    eco.has_tests_dir = any(p.startswith(("tests/", "test/", "__tests__/", "spec/"))
                            or "/tests/" in p or "/__tests__/" in p for p in all_paths)
    eco.has_ci = any(p.startswith((".github/workflows/", ".gitlab-ci.yml", "azure-pipelines",
                                   ".circleci/", "Jenkinsfile", ".travis.yml")) for p in all_paths)
    for p in all_paths:
        if p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml")):
            eco.ci_systems.append("GitHub Actions")
            break
    if ".gitlab-ci.yml" in names:
        eco.ci_systems.append("GitLab CI")
    if ".circleci/config.yml" in as_set:
        eco.ci_systems.append("CircleCI")
    if "Jenkinsfile" in names:
        eco.ci_systems.append("Jenkins")
    eco.has_pre_commit = ".pre-commit-config.yaml" in names or \
        ".pre-commit-config.yml" in names

    eco.test_frameworks = _detect_test_frameworks(root, all_paths, eco)
    total = 0
    pinned = 0
    for manifest in eco.manifests:
        total += len(manifest.dependencies)
        pinned += manifest.pinned
    eco.dependency_total = total
    eco.dependency_pinned = pinned
    eco.ecosystems = sorted(dict.fromkeys(eco.ecosystems))
    return eco


def _detect_test_frameworks(root: Path, paths: list[str], eco: Ecosystem) -> list[str]:
    found: list[str] = []
    names = {p.rsplit("/", 1)[-1] for p in paths}
    test_files = [p for p in paths
                  if p.rsplit("/", 1)[-1].startswith("test_")
                  or p.endswith(("_test.py", ".test.js", ".test.ts", ".spec.ts", "_test.go"))]
    if test_files or "conftest.py" in names:
        # Probe a bounded sample: a pytest.ini, a conftest or any test module.
        candidates = [p for p in paths
                      if p.endswith("conftest.py") or _is_test_basename(p)][:5]
        pytest_markers = "pytest.ini" in names or "conftest.py" in names
        if pytest_markers or any(_mentions(root, p, "pytest") for p in candidates):
            found.append("pytest")
        elif any(_mentions(root, p, "unittest") for p in candidates):
            found.append("unittest")
        else:
            found.append("pytest")
    if any(_mentions(root, p, "vitest") for p in paths if p.endswith(("package.json",))):
        found.append("vitest")
    elif any(_mentions(root, p, "jest") for p in paths if p.endswith("package.json")):
        found.append("jest")
    has_jest_config = "jest.config.js" in names or "jest.config.ts" in names
    if has_jest_config and "jest" not in found:
        found.append("jest")
    if any(p.endswith("_test.go") for p in paths):
        found.append("go test")
    if any(p.endswith(".rs") for p in paths) and "Cargo.toml" in names:
        found.append("cargo test")
    if "pom.xml" in names:
        found.append("junit")
    return sorted(dict.fromkeys(found))


def _is_test_basename(rel: str) -> bool:
    """True for a path that looks like a test module."""
    name = rel.rsplit("/", 1)[-1]
    return (name.startswith("test_")
            or name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.ts")))


def _mentions(root: Path, rel: str, needle: str) -> bool:
    """Cheap substring probe on one file, tolerating anything unreadable."""
    try:
        return needle in read_text(root / rel)
    except OSError:
        return False


def entry_point_score(eco: Ecosystem) -> float:
    """How obvious is it how to run this project?"""
    if not eco.entry_points:
        return 30.0
    kinds = {kind for _, kind in eco.entry_points}
    score = 55.0 + min(30.0, 10.0 * len(kinds))
    if eco.has_docker:
        score += 5.0
    return min(100.0, score)
