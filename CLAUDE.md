# CLAUDE.md

**scout** — Python CLI for static code-quality metrics (CC, Cognitive, Halstead, MI, LOC, Duplication, CBO, LCOM) on Python/JS/TS codebases. v0.1 feature-complete; `make check` is green.

## Design Principles

1. One process model, one entrypoint, one config format. No daemon or plugin system.
2. Two output formats only: `text` (rich) and `json`. No SARIF, XML, HTML, CSV.
3. Directories must earn their place. No speculative structure.
4. No premature abstraction. Every class must break something obvious if deleted.
5. Reuse before reinvention. `radon`/`lizard` for metrics; `tree-sitter` for JS/TS parsing.
6. Per-file parse errors never abort. Recorded in `ParsedFile.errors`; processing continues.

## Module Structure

```
src/scout/
├── __init__.py         # version constant
├── __main__.py         # python -m scout entrypoint
├── cli.py              # Typer app
├── config.py           # ScoutConfig, loader, validation
├── discovery.py        # File walk + gitignore + globs → SourceFile
├── runner.py           # ProcessPoolExecutor orchestration
├── parsers/
│   ├── __init__.py     # parse(path, source, language) → ParsedFile
│   ├── base.py         # ParsedFile, FunctionUnit, ClassUnit, Token types
│   ├── python_parser.py
│   ├── js_parser.py
│   └── ts_parser.py
├── metrics/
│   ├── __init__.py     # registry: metric_id → module
│   ├── base.py         # MetricValue, Severity, FileMetric/RepoMetric protocols
│   ├── cc.py, cognitive.py, halstead.py, mi.py, loc.py
│   ├── duplication.py  # Cross-file Rabin–Karp (RepoMetric)
│   ├── cbo.py
│   └── lcom.py
├── aggregator.py       # Per-file results → threshold evaluation
├── output.py           # text (rich) + json only
└── errors.py           # Exception hierarchy, exit codes
```

## Key Invariants

- **Type boundary:** `parsers/base.py` owns `ParsedFile` types; `metrics/base.py` owns `MetricValue` types. Metric modules consume `ParsedFile` without knowing which parser produced it.
- **Config precedence:** `defaults < pyproject.toml [tool.scout] < scout.toml < CLI flags`
- **Concurrency:** One `ProcessPoolExecutor(max_workers=cpu_count)`. Workers load tree-sitter grammars once per process; return `(ParsedFile, list[MetricValue])`.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success, no violations |
| 1 | Threshold violations |
| 2 | ConfigError |
| 3 | IOError / DiscoveryError |
| 4 | Parse errors + `--strict` |
| 130 | KeyboardInterrupt |

## Metric Thresholds

- **CC:** warn/error/critical at [10, 20, 50]
- **Cognitive:** default 15 (Sonar)
- **MI:** green ≥20, yellow 10–19, red <10. Lower = worse.
- **LOC:** warn at SLOC >500/file
- **Duplication:** green <3%, yellow 3–5%, red >5%
- **CBO:** bands [5, 14]
- **LCOM:** 1=cohesive, 2–3=borderline, ≥4=refactor

## Build & Testing

- Backend: `hatchling`; entrypoint: `scout = "scout.cli:app"`; PyPI: `scout-metrics`
- Version: `src/scout/__init__.py` via `hatch-vcs`; CI: ruff → mypy → pytest (3.10–3.13)
- Coverage: ≥85% lines on `src/scout/`; ≥90% branches on `src/scout/metrics/`
- Golden files: `tests/fixtures/golden/`; update via `--update-snapshots`
- Perf targets: 10k SLOC <2s/<200MB · 100k <15s/<500MB · 500k <60s/<2GB

## Known Limitations (v0.1)

1. Arrow functions in class bodies not scored for CBO/LCOM.
2. TS `type`/`interface`/`import type` excluded from CC, Cognitive, logical LOC.
3. No recursion penalty in Cognitive Complexity (needs call-graph; deferred to v0.2).
4. No type-aware CBO in TS (tree-sitter only, not TS Compiler API).
5. LCOM method-call matching is textual; dynamic dispatch invisible.
6. `from foo import *` doesn't contribute to CBO (conservative undercount).

Full spec: `docs/spec/scout-TECH-SPEC.md` · Deep impl context: `/scout-impl`
