# Contributing

Thanks for taking the time to improve repo-radar. It is a small, dependency-free
tool and we would like to keep it that way.

## Development setup

```bash
git clone https://github.com/kele-tao/repo-radar
cd repo-radar
python -m pip install -e ".[dev]"
pytest -q
ruff check .
```

## Ground rules

1. **No new runtime dependencies.** The scanner must stay pure-stdlib so it can
   run on any Python 3.10+ interpreter, including locked-down CI images.
2. **Every number must be reproducible.** If a change alters the scoring
   formula, update `docs/scoring.md`, the tests and the benchmark output in the
   same pull request.
3. **Rules need an id, a severity and a fix.** Add the rule to `RULES` in
   `src/repo_radar/findings.py` and to the rule table in the README.
4. **Determinism.** Sort output with explicit keys; never iterate a set for
   presentation.

## Pull request checklist

- [ ] `pytest -q` is green and the test count in the README matches reality.
- [ ] `ruff check .` is clean.
- [ ] `python -m repo_radar scan examples/demo-repo` still renders correctly.
- [ ] `docs/screenshot.png` regenerated if the terminal output changed.
