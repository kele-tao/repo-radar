"""The scanner: walk, count, parse, score. The single source of truth for the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .findings import (
    MIN_DEAD_LOC,
    SEVERITY_WEIGHT,
    Finding,
    is_test_path,
    scan_files,
    scan_repo_hygiene,
    severity_counts,
)
from .gitinfo import GitInfo, collect_git, history_score
from .importgraph import ImportGraph, build_graph, describe_graph, largest_cycles
from .manifests import Ecosystem, detect, entry_point_score
from .pyast import reset_cache
from .scoring import grade_for, weighted_score
from .utils import human_size, pct
from .walker import FileInfo, WalkOptions, count_lines, iter_files, load_text

MIN_RISK_LOC = 250


@dataclass
class LanguageStat:
    """Aggregated counters per language."""

    name: str
    category: str
    files: int = 0
    code: int = 0
    comments: int = 0
    blanks: int = 0
    bytes: int = 0

    @property
    def loc(self) -> int:
        return self.code + self.comments + self.blanks

    def as_dict(self) -> dict:
        return {
            "language": self.name,
            "category": self.category,
            "files": self.files,
            "code": self.code,
            "comments": self.comments,
            "blank": self.blanks,
            "bytes": self.bytes,
        }


@dataclass
class ScanResult:
    """Everything one scan produces. JSON output is this object, serialised."""

    root: Path
    files: list[FileInfo]
    languages: dict[str, LanguageStat]
    display_root: str = ""
    total_files: int = 0
    total_bytes: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    file_lines: int = 0
    skipped: list[tuple[str, str]] = field(default_factory=list)
    ecosystem: Ecosystem | None = None
    graph: ImportGraph | None = None
    git: GitInfo | None = None
    findings: list[Finding] = field(default_factory=list)
    dead_files: list[str] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    score: float = 0.0
    grade: str = "F"
    duration_ms: float = 0.0
    truncated_findings: int = 0

    @property
    def severity(self) -> dict[str, int]:
        return severity_counts(self.findings)

    def top_findings(self, limit: int = 10) -> list[Finding]:
        return self.findings[:limit]

    def as_dict(self, top: int = 10) -> dict:
        langs = sorted(self.languages.values(), key=lambda s: (-s.code, s.name))
        return {
            "root": str(self.root),
            "root_display": self.display_root,
            "score": self.score,
            "grade": self.grade,
            "sub_scores": {k: round(v, 1) for k, v in self.scores.items()},
            "totals": {
                "files": self.total_files,
                "bytes": self.total_bytes,
                "bytes_human": human_size(self.total_bytes),
                "code_lines": self.code_lines,
                "comment_lines": self.comment_lines,
                "blank_lines": self.blank_lines,
                "file_lines": self.file_lines,
                "comment_ratio": pct(self.comment_lines, self.code_lines + self.comment_lines),
            },
            "languages": [s.as_dict() for s in langs],
            "ecosystem": self.ecosystem.as_dict() if self.ecosystem else None,
            "graph": describe_graph(self.graph) if self.graph else None,
            "cycles": self.cycles,
            "dead_files": self.dead_files,
            "git": self.git.as_dict() if self.git else None,
            "findings": [f.as_dict() for f in self.findings[:top * 3]],
            "finding_totals": self.severity,
            "duration_ms": round(self.duration_ms, 1),
        }


def collect(root: Path, options: WalkOptions | None = None,
            with_git: bool = True, top: int = 10) -> ScanResult:
    """Scan *root*: count lines, detect tooling, build the graph, run rules.

    The result keeps the caller's spelling of the path for display, so a scan of
    'examples/demo-repo' prints that instead of an absolute machine path.
    """
    import time
    started = time.perf_counter()
    root_arg = root
    root = root.resolve()
    reset_cache()
    infos = iter_files(root, options)
    texts: dict[str, str] = {}
    lang_map: dict[str, str] = {}
    languages: dict[str, LanguageStat] = {}
    total_bytes = 0
    code = comments = blanks = file_lines = 0
    skipped: list[tuple[str, str]] = []

    for info in infos:
        total_bytes += info.size
        if info.skipped_reason:
            skipped.append((info.rel, info.skipped_reason))
            continue
        text = load_text(info)
        if not text and info.size:
            skipped.append((info.rel, info.skipped_reason or "unreadable"))
            continue
        count_lines(text, info)
        texts[info.rel] = text
        lang_map[info.rel] = info.language
        stat = languages.setdefault(
            info.language, LanguageStat(info.language, info.category))
        stat.files += 1
        stat.code += info.code
        stat.comments += info.comments
        stat.blanks += info.blanks
        stat.bytes += info.size
        code += info.code
        comments += info.comments
        blanks += info.blanks
        file_lines += info.lines

    ecosystem = detect(root, [i.rel for i in infos])
    graph = build_graph(texts, lang_map)
    code_files = [i.rel for i in infos if i.executable and not i.skipped_reason]
    dead = graph.dead_code_candidates(code_files)
    cycles = largest_cycles(graph, limit=3)
    found = scan_repo_hygiene(root)
    found.extend(scan_files(infos, texts, lang_map, dead))
    found.sort(key=Finding.sort_key)

    git = GitInfo(reason="disabled")
    if with_git:
        git = collect_git(root, {i.rel: i.code for i in infos}, top=top)

    result = ScanResult(
        root=root,
        display_root=root_arg.as_posix(),
        files=infos,
        languages=languages,
        total_files=len(infos),
        total_bytes=total_bytes,
        code_lines=code,
        comment_lines=comments,
        blank_lines=blanks,
        file_lines=file_lines,
        skipped=skipped,
        ecosystem=ecosystem,
        graph=graph,
        git=git,
        findings=found,
        dead_files=[d for d in dead if _code_size(infos, d) >= MIN_DEAD_LOC],
        cycles=cycles,
    )
    result.scores = compute_scores(result)
    result.score = weighted_score(result.scores)
    result.grade = grade_for(result.score)
    result.duration_ms = (time.perf_counter() - started) * 1000.0
    return result


def _code_size(infos: list[FileInfo], rel: str) -> int:
    for info in infos:
        if info.rel == rel:
            return info.code
    return 0


def compute_scores(result: ScanResult) -> dict[str, float]:
    """Six independent 0-100 sub-scores. Weights are declared in SCORE_WEIGHTS."""
    eco = result.ecosystem
    rank = result.git
    sev = result.severity

    # risk: severity-weighted findings, damped by size so a small repo is not
    # wiped out by one finding and a big repo is not excused by its size.
    weighted = (sev["high"] * SEVERITY_WEIGHT["high"]
                + sev["medium"] * SEVERITY_WEIGHT["medium"]
                + sev["low"] * SEVERITY_WEIGHT["low"])
    size_factor = min(1.5, max(0.55, (result.code_lines / 1000.0) ** 0.5))
    risk = 100.0 / (1.0 + weighted * size_factor / 100.0)

    # tests: presence dominates, ratio refines
    test_files = [i for i in result.files if is_test_path(i.rel) and i.executable]
    test_ratio = pct(sum(i.code for i in test_files), max(1, result.code_lines))
    tests = 0.0
    if eco and eco.has_tests_dir:
        tests += 40.0
    if eco and eco.test_frameworks:
        tests += 20.0
    tests += min(40.0, test_ratio * 4.0)
    if not test_files:
        tests = min(tests, 25.0)

    # docs: README, docs dir, comment density
    docs = 0.0
    readme = _readme_size(result)
    docs += 35.0 if readme >= 2000 else 25.0 if readme >= 500 else 5.0 if readme else 0.0
    has_docs_dir = any(i.rel.startswith("docs/") for i in result.files)
    docs += 20.0 if has_docs_dir else 0.0
    comment_ratio = pct(result.comment_lines, max(1, result.code_lines + result.comment_lines))
    docs += min(25.0, comment_ratio * 2.5)
    if eco and eco.has_license:
        docs += 20.0
    docs = min(100.0, docs)

    # dependencies: pinning, lockfile, manifest presence, count sanity
    deps = 50.0
    if eco:
        deps = 30.0 + 0.6 * eco.pin_ratio if eco.dependency_total else 70.0
        if eco.has_lockfile:
            deps += 12.0
        if not eco.manifests:
            deps -= 25.0
        if eco.dependency_total > 120:
            deps -= 10.0
    deps = max(0.0, min(100.0, deps))

    # hygiene: the boring things that predict maintenance pain
    hygiene = 0.0
    if eco:
        hygiene += 25.0 if eco.has_readme else 0.0
        hygiene += 25.0 if eco.has_license else 0.0
        hygiene += 25.0 if eco.has_ci else 0.0
        hygiene += 15.0 if eco.has_pre_commit else 0.0
        hygiene += 10.0 if eco.has_docker else 0.0
    hygiene = min(100.0, hygiene)

    history = history_score(rank) if rank else 40.0
    entry = entry_point_score(eco) if eco else 30.0
    # entry points fold into hygiene: a repo you cannot run is not hygienic
    hygiene = round(0.75 * hygiene + 0.25 * entry, 1)

    return {
        "risk": round(risk, 1),
        "tests": round(tests, 1),
        "docs": round(docs, 1),
        "dependencies": round(deps, 1),
        "hygiene": hygiene,
        "history": round(history, 1),
    }


def _readme_size(result: ScanResult) -> int:
    for info in result.files:
        if info.rel.lower() in {"readme.md", "readme.rst", "readme.txt", "readme"}:
            return info.size
    return 0
