# Scoring model

Every number repo-radar prints is derived from what it measured. This page is the
full specification so a reader can reproduce a score by hand from `--json`.

## The composite score

Six sub-scores, each on a 0-100 scale, combined with fixed weights:

| Sub-score | Weight | What moves it |
| --------- | -----: | ------------- |
| risk | 30% | severity-weighted findings, damped by code size |
| tests | 20% | test tree presence, framework detection, test/code ratio |
| docs | 15% | README size, `docs/`, comment ratio, licence file |
| dependencies | 15% | pin ratio, lockfile, manifest presence, dependency count |
| hygiene | 10% | README/licence/CI/hooks/Docker plus entry-point clarity |
| history | 10% | commit volume, authorship spread, uncommitted churn |

```
score = sum(weight_i * sub_score_i) / sum(weight_i)
```

Grades: A >= 90, B >= 80, C >= 70, D >= 60, F < 60.

## risk

```
weighted  = 14*high + 5*medium + 1.5*low + 0*info
size      = clamp(sqrt(code_lines / 1000), 0.55, 1.5)
risk      = 100 / (1 + weighted * size / 100)
```

The square-root size damping is the interesting part: one high-severity finding in
a 200-line script costs more than the same finding in a 50,000-line monorepo,
but a monorepo cannot be excused by sheer size either. The final formula is
bounded by construction, so the score can never go negative.

## tests

```
tests = 40 (tests directory) + 20 (framework detected)
      + min(40, 4 * test_code_lines / code_lines * 100 / 100)
capped at 25 when no test file exists
```

## docs

```
docs = readme_points   (35 if >= 2 KB, 25 if >= 500 B, 5 if present)
     + 20 if a docs/ directory exists
     + min(25, 2.5 * comment_ratio_percent)
     + 20 if a licence file exists
```

## dependencies

```
deps = 30 + 0.6 * pin_ratio        when the project declares dependencies
     = 70                          when it declares none
     + 12                          when a lockfile exists
     - 25                          when no manifest was found
     - 10                          when more than 120 dependencies are declared
```

## hygiene

```
hygiene = 25*readme + 25*licence + 25*ci + 15*pre_commit + 10*docker
hygiene = 0.75 * hygiene + 0.25 * entry_point_clarity
```

`entry_point_clarity` is 30 with no entry point, otherwise `55 + 10 * distinct
entry-point kinds` (plus 5 for a container build), capped at 100.

## history

```
score = 55
      + 10 if >= 100 commits, + 5 if >= 20 commits
      + 5  if >= 2 authors
      * 1.1 if the history spans >= 30 days
      - 12 if one author owns > 85% of commits (and there are > 20 commits)
      - 5  if more than 20 files are uncommitted
```

A repository with no git history scores 40 on this axis: unknown, not bad.

## Reproducing a score

```bash
python -m repo_radar scan . --json | python -c "import json,sys; d=json.load(sys.stdin); print(d['sub_scores'], d['score'])"
```

Because every input is a deterministic function of the file tree, two scans of the
same tree produce byte-identical JSON apart from the `duration_ms` field.
