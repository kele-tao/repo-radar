# Rule reference

20 rules, each with a stable id, a severity, a human title and a concrete fix.
Rules are evaluated per file (or once per repository for RR018) and deduplicated
by location. Findings are sorted by severity, then path, then line.

| ID | Severity | Title | Detection |
| -- | -------- | ----- | --------- |
| RR001 | high | Hardcoded credential | assignment of a literal to a secret-looking name, known token prefixes, private-key blocks |
| RR002 | high | Dynamic code execution | `eval(` / `exec(` calls outside comments |
| RR003 | high | Unsafe deserialisation | pickle/unpickle calls |
| RR004 | high | Shell injection surface | `shell=True`, `os.system`, `os.popen` |
| RR005 | high | TLS verification disabled | `verify=False`, `CERT_NONE`, insecure-request suppressions |
| RR006 | medium | `yaml.load` without SafeLoader | `yaml.load(` without `SafeLoader` |
| RR007 | medium | `assert` used for runtime validation | AST `Assert` outside test files |
| RR008 | medium | Exception swallowed silently | AST `except:` whose only body statement is `pass` |
| RR009 | medium | Mutable default argument | AST default of `[]`, `{}` or `set()` |
| RR010 | medium | Wildcard import | `from x import *` |
| RR011 | medium | Giant file | more than 700 code lines in one source file |
| RR012 | medium | File is never imported | no internal importer, not an entry point, >= 8 code lines |
| RR013 | low | Uppercase unfinished marker | literal marker word in a non-test file |
| RR014 | low | `open()` without an explicit encoding | `open(` without `encoding=` and not binary mode |
| RR015 | low | SQL built by string interpolation | f-string or `%` formatting inside `execute(` |
| RR016 | low | World-writable permissions | `chmod(...777)` |
| RR017 | info | High unfinished-marker density | more than 8 markers per 1000 code lines |
| RR018 | high | Missing repository hygiene file | no README, no licence, or no tests |
| RR019 | info | Very few comments in a large module | >= 200 code lines and comments < 1% of code |
| RR020 | low | Debug print left in library code | `print(` in a library module (scripts and CLI excluded) |

## Severity meaning

- **high**: could be exploited or hides a defect. Fix before shipping.
- **medium**: a real maintenance or correctness risk.
- **low**: a smell that costs review time.
- **info**: context, not a defect.

## Tuning

Each severity has a weight in the `risk` sub-score (14 / 5 / 1.5 / 0). The
threshold for a giant file is `MAX_FILE_LOC = 700`; the dead-code minimum is
`MIN_DEAD_LOC = 8`. Both live in `src/repo_radar/findings.py`.

## Scope and suppression

Line-level rules only run on **code, shell, config and data** files. Documentation,
markup and stylesheets are skipped: a README that *documents* a dangerous snippet
must not itself be reported as carrying the vulnerability. Test modules are skipped
for the same reason - a fixture whose whole job is to contain `eval()` is the input
of a rule, not a defect.

A single line can be exempted with an inline comment containing the token
`radar:ignore`. This repository uses it on the regex definitions that necessarily
contain the patterns the rules look for (otherwise the scanner reports its own
detection patterns). Suppression is per line and shows up in code review.

```python
pattern = re.compile(r"verify\s*=\s*False")  # radar:ignore pattern definition
```
