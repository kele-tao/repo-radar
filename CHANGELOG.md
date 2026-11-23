# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-23

### Added
- `scan` with a 0-100 health score, six weighted sub-scores and `--fail-under`.
- 20 risk rules (RR001-RR020) with stable ids, severity and a suggested fix.
- Git-aware history: commits, authors, span, churn hotspots (commits x size).
- Python/JS/TS/Go/Rust import graph, import cycles and never-imported modules.
- `explain` for per-module public API, docstring coverage and complexity.
- `report` writing one self-contained HTML dashboard with inline SVG bars.
- Language detection for 30+ languages plus docs, data and config categories.
- `.radar.yml` / `.radarignore` configuration and `REPO_RADAR_*` env overrides.
- Deterministic JSON output for every command.

[1.0.0]: https://github.com/kele-tao/repo-radar/releases/tag/v1.0.0
