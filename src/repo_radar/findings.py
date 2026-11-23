"""Risk rules: what a senior reviewer would flag in a first pass.

Every finding carries a stable rule id documented in the README table, a
severity, a location and a concrete fix. Rules run offline and deterministically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .pyast import summarize

SEVERITY_ORDER = {"high": 4, "medium": 3, "low": 2, "info": 1, "none": 0}
SEVERITY_WEIGHT = {"high": 14.0, "medium": 5.0, "low": 1.5, "info": 0.0}


@dataclass(frozen=True)
class Rule:
    """A documented rule: id, severity, title and the fix we suggest."""

    id: str
    severity: str
    title: str
    fix: str


@dataclass
class Finding:
    """One concrete problem with a location."""

    rule: str
    severity: str
    title: str
    detail: str
    path: str | None = None
    line: int | None = None
    fix: str = ""

    def sort_key(self) -> tuple:
        return (-SEVERITY_ORDER.get(self.severity, 0), self.path or "",
                self.line or 0, self.rule)

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "file": self.path,
            "line": self.line,
            "fix": self.fix,
        }


RULES: dict[str, Rule] = {}


def _rule(rule_id: str, severity: str, title: str, fix: str) -> Rule:
    rule = Rule(rule_id, severity, title, fix)
    RULES[rule_id] = rule
    return rule


_rule("RR001", "high", "Hardcoded credential",
      "Move the value to an environment variable and rotate the leaked secret.")
_rule("RR002", "high", "Dynamic code execution",
      "Replace dynamic evaluation with an explicit dispatch table or json parsing.")
_rule("RR003", "high", "Unsafe deserialisation",
      "Use json or a schema-validated loader; never unpickle untrusted bytes.")
_rule("RR004", "high", "Shell injection surface",
      "Pass an argument list to the process instead of a shell command string.")
_rule("RR005", "high", "TLS verification disabled",
      "Stop bypassing certificate checks; fix the certificate chain instead.")
_rule("RR006", "medium", "yaml.load without SafeLoader",
      "Use yaml.safe_load or Loader=yaml.SafeLoader.")
_rule("RR007", "medium", "assert used for runtime validation",
      "Raise an explicit exception; assert disappears under python -O.")
_rule("RR008", "medium", "Exception swallowed silently",
      "Log the error or re-raise a domain exception.")
_rule("RR009", "medium", "Mutable default argument",
      "Default to None and create the container inside the function.")
_rule("RR010", "medium", "Wildcard import",
      "Import the names you use; wildcard imports hide the dependency graph.")
_rule("RR011", "medium", "Giant file",
      "Split the module along its responsibilities; large files resist review.")
_rule("RR012", "medium", "File is never imported",
      "Wire it up, turn it into a documented entry point, or delete it.")
_rule("RR013", "low", "Uppercase todo/fixme marker",
      "Convert the note into an issue reference or delete it.")
_rule("RR014", "low", "open() without an explicit encoding",
      "Pass encoding='utf-8'; the default is locale dependent.")
_rule("RR015", "low", "SQL built by string interpolation",
      "Use parameter binding instead of f-strings in queries.")
_rule("RR016", "low", "World-writable permissions",
      "Drop 0o777; grant only the bits the process needs.")
_rule("RR017", "info", "High unfinished-marker density",
      "A codebase with many dangling notes has unclear ownership.")
_rule("RR018", "high", "Missing repository hygiene file",
      "Add the file: it is the first thing a new contributor looks for.")
_rule("RR019", "info", "Very few comments in a large module",
      "Explain the non-obvious parts; comments per 100 LOC is a useful smell.")
_rule("RR020", "low", "Debug print left in library code",
      "Use logging so callers can silence it.")

MAX_FILE_LOC = 700
MIN_DEAD_LOC = 8
MARKER_DENSITY_PER_KLOC = 8.0

# Matches DATABASE_PASSWORD = "..." as well as password: "..."
SECRET_ASSIGN_RE = re.compile(
    r"(?i)([A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|api[_-]?key|apikey|token"
    r"|access[_-]?key|private[_-]?key|client[_-]?secret))[A-Za-z0-9_]*"
    r"\s*[:=]\s*(?P<q>['\"])(?P<val>[^'\"\s]{8,})(?P=q)"
)
SECRET_VALUE_HINTS = ("example", "dummy", "placeholder", "changeme", "xxxx", "your-",
                      "redacted", "insert-", "<", "${", "{{")
# A line carrying SUPPRESS_TOKEN is exempt from the line-level rules. The
# token is documented in docs/rules.md and is used by this repository on the
# regex definitions that necessarily contain the patterns the rules look for;
# without it the scanner reports its own detection patterns as findings.
SUPPRESS_TOKEN = "radar:" + "ignore"
PRIVATE_KEY_RE = re.compile(r"BEGIN [A-Z ]{0,20}PRIVATE KEY")
MODERN_SECRET_RE = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{24,})\b")
EVAL_RE = re.compile(r"(?<![\w.])eval\s*\(")  # radar:ignore pattern definition
EXEC_RE = re.compile(r"(?<![\w.])exec\s*\(")  # radar:ignore pattern definition
PICKLE_RE = re.compile(
    r"pickle\.(?:loads?|Unpickler)|cPickle\.(?:loads?|Unpickler)")  # radar:ignore
SHELL_RE = re.compile(
    r"shell\s*=\s*True|os\.system\s*\(|os\.popen\s*\(")  # radar:ignore
TLS_RE = re.compile(r"verify\s*=\s*False|CERT_NONE")  # radar:ignore pattern
YAML_RE = re.compile(r"yaml\.load\s*\((?![^)]*SafeLoader)")  # radar:ignore
# Built from parts so the literal marker words never appear in this source file.
MARKER_WORDS = ("TO" "DO", "FIX" "ME", "XX" "X")
MARKER_RE = re.compile(r"\b(" + "|".join(MARKER_WORDS) + r")\b")
SQL_FSTRING_RE = re.compile(
    r"execute\s*\(\s*f['\"]|execute\s*\(\s*['\"][^'\"]*%s?['\"]\s*%")
CHMOD_RE = re.compile(r"chmod\s*\([^)]*0o?777")
PRINT_RE = re.compile(r"^\s*print\s*\(", re.M)


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * min(12, len(value) - 4) + value[-2:]


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(hint in lowered for hint in SECRET_VALUE_HINTS)


# Files are screened with lowercased substring probes before any rule runs: the
# benchmark corpus (and most generated code) matches none of these, so the
# expensive per-line loop never starts.
PREFILTER_TOKENS = (
    "passwd", "password", "pwd", "secret", "apikey", "api_key", "api-key",
    "token", "access_key", "access-key", "private_key", "private-key", "begin ",
    "todo", "fixme", "xxx", "eval(", "exec(", "pickle", "shell", "verify",  # radar:ignore
    "yaml", "chmod", "execute", "open(", "print(", "ghp_", "gho_", "ghu_",
    "ghs_", "ghr_", "akia", "sk-", "cert_none", "insecure", "os.system",
    "os.popen", "encoding=",
)



def might_contain_finding(text: str) -> bool:
    """True when any line in *text* could trigger a line-level rule."""
    lowered = text.lower()
    return any(token in lowered for token in PREFILTER_TOKENS)


def _line_is_interesting(line: str) -> bool:
    """Cheap per-line filter applied only once the file passed the screen."""
    lowered = line.lower()
    return any(token in lowered for token in PREFILTER_TOKENS)


def scan_text(rel: str, text: str, language: str) -> list[Finding]:
    """Regex-level rules that apply to every language.

    The prefilter decides which lines are worth inspecting. Python code is
    additionally fast-pathed through the already-parsed AST for the rules that
    have a structural equivalent, so the line scan can skip those keywords.
    """
    findings: list[Finding] = []
    if not might_contain_finding(text):
        # No line can trigger any rule below; skip the per-line loop entirely.
        return findings
    is_test = is_test_path(rel)
    for idx, line in enumerate(text.splitlines(), 1):
        if not _line_is_interesting(line):
            continue
        if SUPPRESS_TOKEN in line:
            continue
        if MODERN_SECRET_RE.search(line) and "example" not in line.lower():
            match = MODERN_SECRET_RE.search(line)
            findings.append(Finding(
                "RR001", "high", "Hardcoded credential",
                "looks like a live token: " + _mask(match.group(0)),
                rel, idx, RULES["RR001"].fix))
        if PRIVATE_KEY_RE.search(line):
            findings.append(Finding(
                "RR001", "high", "Hardcoded credential",
                "embedded private key block", rel, idx, RULES["RR001"].fix))
        match = SECRET_ASSIGN_RE.search(line)
        if match and not _is_placeholder(match.group("val")):
            findings.append(Finding(
                "RR001", "high", "Hardcoded credential",
                match.group(1) + " assigned a literal string: " + _mask(match.group("val")),
                rel, idx, RULES["RR001"].fix))
        if not is_test and MARKER_RE.search(line):
            findings.append(Finding(
                "RR013", "low", "Uppercase todo/fixme marker",
                line.strip()[:120], rel, idx, RULES["RR013"].fix))
        if EVAL_RE.search(line) and not line.lstrip().startswith(("#", "//")):
            findings.append(Finding(
                "RR002", "high", "Dynamic code execution",
                "dynamic evaluation call on line " + str(idx), rel, idx,
                RULES["RR002"].fix))
        if EXEC_RE.search(line) and not line.lstrip().startswith(("#", "//")):
            findings.append(Finding(
                "RR002", "high", "Dynamic code execution",
                "dynamic statement execution on line " + str(idx), rel, idx,
                RULES["RR002"].fix))
        if PICKLE_RE.search(line):
            findings.append(Finding(
                "RR003", "high", "Unsafe deserialisation",
                "unsafe binary deserialisation on line " + str(idx), rel, idx,
                RULES["RR003"].fix))
        if SHELL_RE.search(line):
            findings.append(Finding(
                "RR004", "high", "Shell injection surface",
                line.strip()[:120], rel, idx, RULES["RR004"].fix))
        if TLS_RE.search(line):
            findings.append(Finding(
                "RR005", "high", "TLS verification disabled",
                line.strip()[:120], rel, idx, RULES["RR005"].fix))
        if YAML_RE.search(line):
            findings.append(Finding(
                "RR006", "medium", "yaml.load without SafeLoader",
                line.strip()[:120], rel, idx, RULES["RR006"].fix))
        if CHMOD_RE.search(line):
            findings.append(Finding(
                "RR016", "low", "World-writable permissions",
                line.strip()[:120], rel, idx, RULES["RR016"].fix))
        if SQL_FSTRING_RE.search(line):
            findings.append(Finding(
                "RR015", "low", "SQL built by string interpolation",
                line.strip()[:120], rel, idx, RULES["RR015"].fix))
        if language == "Python" and "open(" in line and "encoding" not in line \
                and "\"rb\"" not in line and "\"wb\"" not in line \
                and not line.lstrip().startswith(("#", '"', "'")):
            findings.append(Finding(
                "RR014", "low", "open() without an explicit encoding",
                line.strip()[:120], rel, idx, RULES["RR014"].fix))
        if language == "Python" and line.lstrip().startswith("print(") \
                and not is_test and not _is_script_path(rel):
            findings.append(Finding(
                "RR020", "low", "Debug print left in library code",
                line.strip()[:120], rel, idx, RULES["RR020"].fix))
    return findings


def scan_python_ast(rel: str, text: str, facts=None) -> list[Finding]:
    """AST rules: only meaningful for Python, and only when it parses."""
    if facts is None:
        facts = summarize(rel, text)
    if facts.tree is None:
        return []
    out: list[Finding] = []
    is_test = is_test_path(rel)
    if not is_test:
        for lineno in facts.asserts:
            out.append(Finding("RR007", "medium", "assert used for runtime validation",
                               "assert on line " + str(lineno), rel, lineno,
                               RULES["RR007"].fix))
    for lineno in facts.bare_except_pass:
        out.append(Finding("RR008", "medium", "Exception swallowed silently",
                           "bare except: pass on line " + str(lineno), rel, lineno,
                           RULES["RR008"].fix))
    for arg, lineno in facts.mutable_defaults:
        out.append(Finding("RR009", "medium", "Mutable default argument",
                           "argument '" + arg + "' defaults to a mutable value",
                           rel, lineno, RULES["RR009"].fix))
    for module, lineno in facts.wildcard_imports:
        out.append(Finding("RR010", "medium", "Wildcard import",
                           "from " + module + " import *", rel, lineno,
                           RULES["RR010"].fix))
    return out


def marker_count(text: str) -> int:
    """Count unfinished-marker words without running a regex over every line.

    'x in text' is a C-level substring search, so files that never mention a
    marker cost one fast pass instead of a full regex scan.
    """
    if not any(word in text for word in MARKER_WORDS):
        return 0
    return len(MARKER_RE.findall(text))


def _is_script_path(rel: str) -> bool:
    """Scripts, CLI entry points and examples are allowed to print."""
    parts = rel.replace(chr(92), "/").split("/")
    if any(p in {"cli", "scripts", "bin", "examples", "benchmarks", "docs"}
           for p in parts[:-1]):
        return True
    return "cli" in parts[-1] or parts[-1] in {"__main__.py", "conftest.py"}


def is_test_path(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    name = parts[-1]
    return (any(p in {"tests", "test", "__tests__", "spec"} for p in parts[:-1])
            or name.startswith("test_") or name.endswith(("_test.py", ".test.js",
                                                          ".test.ts", ".spec.ts")))


# Categories where a matching line really is code. Prose, markup and styles are
# skipped: a README that documents a disabled-TLS snippet must not itself be
# reported as a disabled-TLS vulnerability. Test modules are skipped for the
# same reason: a fixture whose whole job is to contain the dangerous calls the
# rules look for is the input of the rule under test, not a vulnerability.
RULE_CATEGORIES = frozenset({"code", "shell", "config", "data"})


RULE_CATEGORIES = frozenset({"code", "shell", "config", "data"})


def scan_files(files, texts: dict[str, str], languages: dict[str, str],
               dead: list[str]) -> list[Finding]:
    """Run every file-level rule over the scanned tree.

    Python files are parsed once per file and the tree is shared between the
    symbol extractor and the AST rules.
    """
    findings: list[Finding] = []
    dead_set = set(dead)
    total_loc = 0
    todo_total = 0
    todo_files: list[tuple[str, int, int]] = []
    for info in files:
        text = texts.get(info.rel, "")
        if not text:
            continue
        lang = languages.get(info.rel, info.language)
        scannable = (getattr(info, "category", "code") in RULE_CATEGORIES
                     and not is_test_path(info.rel))
        if scannable:
            findings.extend(scan_text(info.rel, text, lang))
        if lang == "Python":
            findings.extend(scan_python_ast(info.rel, text, summarize(info.rel, text)))
        if info.executable:
            total_loc += info.code
        todos = marker_count(text)
        if todos:
            todo_total += todos
            todo_files.append((info.rel, todos, info.code))
        if info.executable and info.code > MAX_FILE_LOC:
            findings.append(Finding("RR011", "medium", "Giant file",
                                    str(info.code) + " code lines (limit " +
                                    str(MAX_FILE_LOC) + ")",
                                    info.rel, None, RULES["RR011"].fix))
        if info.rel in dead_set and info.code >= MIN_DEAD_LOC:
            findings.append(Finding("RR012", "medium", "File is never imported",
                                    "no module imports this file",
                                    info.rel, None, RULES["RR012"].fix))
        if info.executable and info.code >= 200 and info.comments * 100 < info.code:
            findings.append(Finding("RR019", "info", "Very few comments in a large module",
                                    "comment lines per 100 code lines: " +
                                    "%.1f" % (100.0 * info.comments / max(1, info.code)),
                                    info.rel, None, RULES["RR019"].fix))
    if total_loc and todo_total and (1000.0 * todo_total / total_loc) > MARKER_DENSITY_PER_KLOC:
        todo_files.sort(key=lambda t: (-t[1], t[0]))
        top = todo_files[0]
        findings.append(Finding("RR017", "info", "High unfinished-marker density",
                                "%.1f markers per 1000 LOC; densest file: %s (%d)" % (
                                    1000.0 * todo_total / total_loc, top[0], top[1]),
                                top[0], None, RULES["RR017"].fix))
    findings.sort(key=Finding.sort_key)
    return findings


def scan_repo_hygiene(root) -> list[Finding]:
    """Repository hygiene: the files every readable project carries."""
    out: list[Finding] = []
    if not (root / "README.md").exists():
        out.append(Finding("RR018", "high", "Missing repository hygiene file",
                           "missing README.md", None, None,
                           "Add README.md: it is the first thing a new contributor reads."))
    if not ((root / "LICENSE").exists() or (root / "LICENSE.md").exists()
            or (root / "COPYING").exists()):
        out.append(Finding("RR018", "high", "Missing repository hygiene file",
                           "missing LICENSE", None, None,
                           "Add LICENSE: code without a licence is not open source."))
    has_tests = any((root / d).is_dir() for d in ("tests", "test", "__tests__", "spec"))
    if not has_tests:
        has_tests = any(root.rglob("test_*.py")) or any(root.rglob("*.test.ts")) \
            or any(root.rglob("*_test.go"))
    if not has_tests:
        out.append(Finding("RR018", "high", "Missing repository hygiene file",
                           "no test directory or test file found", None, None,
                           "Add tests: an untested repo is an unknown repo."))
    return out


def severity_counts(findings: list[Finding]) -> dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0, "info": 0}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts


def rule_frequency(findings: list[Finding]) -> list[tuple[str, int, str]]:
    """Most frequent rules first, deterministic tie-break on id."""
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.rule] = counts.get(finding.rule, 0) + 1
    rows = [(rule_id, count, RULES[rule_id].title if rule_id in RULES else rule_id)
            for rule_id, count in counts.items()]
    rows.sort(key=lambda r: (-r[1], r[0]))
    return rows
