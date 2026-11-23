# Architecture

```mermaid
flowchart TD
    cli[cli.py] --> scan[scan.collect]
    scan --> walker[walker.iter_files]
    walker --> languages[languages]
    scan --> pyast[pyast.summarize]
    pyast --> facts[ModuleFacts]
    scan --> graph[importgraph.build_graph]
    graph --> facts
    scan --> findings[findings.scan_files]
    findings --> facts
    scan --> manifests[manifests.detect]
    scan --> gitinfo[gitinfo.collect_git]
    scan --> scoring[scoring.weighted_score]
    scan --> result[ScanResult]
    result --> render[render.render_scan]
    result --> html[htmlreport.build_html]
    result --> json[JSON payload]
```

## Stages

1. **Walk** (`walker.py`). A single `os.walk`, pruned by directory names, a root
   `.gitignore`, `.radarignore`, `.radar.yml`, environment variables and CLI
   patterns. Files are sorted by relative path so the output order is stable.
2. **Read once** (`walker.load_text`). Each file is read as bytes exactly once;
   NUL bytes mark it binary, and decoding tries UTF-8-BOM, UTF-8, then Latin-1.
3. **Summarise** (`pyast.summarize`). One iterative AST traversal gathers imports,
   public symbols, asserts, bare excepts, mutable defaults and wildcard imports.
   The result is memoised on (path, text hash) so the graph builder and the rule
   engine share it. This is the hot path: it is also the reason a 5 MB corpus
   scans in ~3 s.
4. **Graph** (`importgraph.py`). Python imports resolve against the detected
   source roots; relative imports and JS/TS/Go/Rust styles are handled by
   path-based resolution. The reverse adjacency is used for dead-code candidates,
   and an iterative DFS finds import cycles.
5. **Rules** (`findings.py`). A cheap union regex prefilter rejects files and
   lines that cannot match any rule, then the per-rule matchers run. AST rules
   read the shared `ModuleFacts` rather than walking the tree again.
6. **History** (`gitinfo.py`). The git binary is invoked with `-C <root>` and a
   cleared environment; every failure mode degrades to `available: false` with a
   reason instead of an exception.
7. **Score** (`scoring.py`, `scan.compute_scores`). Six independent sub-scores,
   documented in `docs/scoring.md`.
8. **Render** (`render.py`, `htmlreport.py`). Pure functions of `ScanResult`.

## Design constraints

* **No dependency may be added to the runtime.** The scanner must run in a locked
  container with only CPython.
* **The JSON is the contract.** The terminal renderer and the HTML dashboard are
  both derived from the same `ScanResult`; neither recomputes a number.
* **Determinism.** Sets are only used for membership, never for ordering.
  Findings sort on (severity, path, line, rule). JSON keys follow the dataclass
  definition order, not dictionary insertion accidents.
