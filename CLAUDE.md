# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**scout** is a Python CLI tool that computes static code-quality metrics (Cyclomatic Complexity, Cognitive Complexity, Halstead, Maintainability Index, LOC, Duplication, CBO, LCOM) for Python, JavaScript, and TypeScript codebases. It's designed as a single-pass analyzer with two output formats (text and JSON) for CI gating and quality reporting.

**Status:** v0.1 feature-complete. All parsers (Python, JS, TS), metrics, CLI, runner, and output modules are implemented. `make check` is green (lint, typecheck, ≥85% coverage). See `docs/plan/implementation-from-scratch.md` for the full implementation log.

## Key Design Principles

The spec enforces **simplicity as a hard constraint** (§2.0). Apply these principles when implementing:

1. **One process model, one entrypoint, one config format.** No daemon, plugin system, or alternative invocation modes in v0.1.
2. **Two output formats only:** `text` (human-readable, rich-formatted) and `json` (machine-readable). No SARIF, JUnit XML, HTML, CSV, or CI-integration formats.
3. **Directories must earn their place.** A module in its own file only if non-trivial; subdirectories only if containing multiple non-trivial modules.
4. **No premature abstraction.** Every class/interface must break something obvious if deleted.
5. **Reuse before reinvention.** Call `radon` and `lizard` for metrics they already compute well; call `tree-sitter` for JS/TS parsing.
6. **Per-file parse errors never abort.** Errors are recorded in `ParsedFile.errors` and continue processing.

See §2 of the spec for the full design philosophy.

## Architecture Overview

### High-Level Data Flow

```
CLI (Typer) + Config → Discovery → Runner (ProcessPoolExecutor) → Aggregator → Output (text/json)
                         ↓              ↓                              ↓
                    File walk      Per-file parsing         Repo-level metrics
                    + gitignore    + metric computation     + threshold eval
                    + globs        → ParsedFile → MetricValue
```

### Module Structure

```
src/scout/
├── __init__.py              # version constant
├── __main__.py              # `python -m scout` entrypoint
├── cli.py                   # Typer app, argv dispatch
├── config.py                # ScoutConfig, loader, validation
├── discovery.py             # File walk, gitignore, glob filtering → SourceFile
├── runner.py                # ProcessPoolExecutor orchestration
├── parsers/                 # Language-specific parsing
│   ├── __init__.py          # parse(path, source, language) → ParsedFile
│   ├── base.py              # ParsedFile, FunctionUnit, ClassUnit, Token types
│   ├── python_parser.py     # radon + cognitive_complexity + ast (CBO/LCOM)
│   ├── js_parser.py         # lizard + tree-sitter-javascript
│   └── ts_parser.py         # lizard + tree-sitter-typescript
├── metrics/                 # Metric implementations
│   ├── __init__.py          # registry: metric_id → module
│   ├── base.py              # MetricValue, Severity, FileMetric/RepoMetric protocols
│   ├── cc.py                # Cyclomatic Complexity
│   ├── cognitive.py         # Cognitive Complexity
│   ├── halstead.py          # Halstead Volume/Difficulty/Effort
│   ├── mi.py                # Maintainability Index
│   ├── loc.py               # Lines of Code (physical/sloc/logical)
│   ├── duplication.py       # Cross-file Rabin–Karp (RepoMetric)
│   ├── cbo.py               # Coupling Between Objects
│   └── lcom.py              # Lack of Cohesion of Methods
├── aggregator.py            # Combines per-file results, applies thresholds
├── output.py                # text (rich) + json formatters (only two formats)
└── errors.py                # Exception hierarchy, exit code mapping
```

### Key Type System

All shared types live in two modules:

- **`parsers/base.py`:** `Language`, `SourceLocation`, `Token`, `BranchNode`, `HalsteadReport`, `FunctionUnit`, `ClassUnit`, `ParseError`, `ParsedFile`.
- **`metrics/base.py`:** `Severity`, `MetricValue`, `FileReport`, `RunReport`, `FileMetric` / `RepoMetric` protocols.

**Critical invariant:** Metric modules consume `ParsedFile` (parser output) without knowing which parser created it. Language-specific parsing logic stays in `parsers/`; metric logic is language-agnostic in `metrics/`.

## Implementation Strategy & Dependency Model

### Library Reuse (per §2.2)

| Component | Python | JS/TS |
|-----------|--------|-------|
| CC | `radon.complexity.cc_visit` | `lizard` |
| Cognitive | `cognitive_complexity.api` | In-house (tree-sitter) |
| Halstead | `radon.metrics.h_visit` | In-house (tree-sitter tokens) |
| MI | `radon.metrics.mi_visit` | In-house (composite: CC + Halstead + LOC) |
| LOC | `radon.raw.analyze` | `lizard` (NLOC) + in-house (logical) |
| Duplication | In-house (Rabin–Karp) | In-house (Rabin–Karp) |
| CBO | In-house (`ast` + import resolution) | In-house (tree-sitter + import resolution) |
| LCOM | In-house (Union-Find) | In-house (Union-Find) |

### Parser Division of Labor

**Python parser** calls:
1. `radon.raw.analyze(source)` → physical_loc, sloc, logical_loc
2. `radon.complexity.cc_visit(source)` → CC per function
3. `radon.metrics.h_visit(source)` → Halstead per function + per file
4. `radon.metrics.mi_visit(source, multi=True)` → MI per file
5. `cognitive_complexity.api.get_cognitive_complexity(ast_node)` → Cognitive per function
6. `ast.parse(source)` + walk → FunctionUnit, ClassUnit, imports, CBO/LCOM data

**JS/TS parsers** call:
1. `lizard.analyze_source_code(filename, source)` → CC, NLOC per function
2. `tree_sitter.Parser.parse(source)` → walk for FunctionUnit, ClassUnit, tokens, Cognitive, Halstead, CBO/LCOM

### Configuration Precedence

```
defaults < pyproject.toml [tool.scout] < scout.toml < CLI flags
```

Config is loaded in `ScoutConfig.load()`. Validation happens after merge.

### Concurrency Model

- One `ProcessPoolExecutor(max_workers=cpu_count)` per run.
- Worker initializer loads tree-sitter grammars once per process.
- Each worker receives `SourceFile`, returns `(ParsedFile, list[MetricValue])`.
- Main process collects results, runs `RepoMetric`s (duplication), applies thresholds.

## Dependencies

**Core:**
- `typer>=0.12,<1.0` — CLI framework
- `rich>=13.7,<14.0` — Text/table formatting
- `radon>=6.0,<7.0` — Python metrics (CC, MI, Halstead, LOC)
- `cognitive_complexity>=1.3,<2.0` — Python Cognitive Complexity
- `lizard>=1.17,<2.0` — JS/TS CC and NLOC
- `tree-sitter>=0.23,<0.26` + grammars (python, javascript, typescript) — uses `Parser(language)` constructor (0.23+ API)
- `pathspec>=0.12,<1.0` — .gitignore-compatible glob matching
- `tomli>=2.0,<3.0` — TOML parsing (Python 3.10 compat)

**Dev:**
- `pytest>=8.0`, `pytest-cov>=4.1`, `pytest-xdist>=3.5` — Testing
- `mypy>=1.10` — Type checking
- `ruff>=0.5` — Linting
- `py-spy>=0.3` — Profiling (for performance validation)

Python version: `>=3.10` (required for `match` statement in parser logic).

## Testing Strategy

### Test Layers

1. **Unit tests** per metric module: hand-crafted `ParsedFile` fixtures covering trivial, edge, and threshold-exceeding cases.
2. **Parser tests**: small source files in each language with snapshot-verified `ParsedFile` output.
3. **Integration tests**: fixture repos under `tests/fixtures/repos/` with golden-file outputs (JSON + text).
4. **Property tests** (where applicable): e.g., `cc(empty_function) == 1`, `lcom(single_method_class) == 1`.

### Coverage & CI

- **Lines:** ≥85% on `src/scout/` (excluding CLI glue).
- **Branches:** ≥90% on `src/scout/metrics/` (algorithm-heavy).
- **Test matrix:** Python 3.10, 3.11, 3.12, 3.13 (tree-sitter wheel availability is the constraint).
- **Golden files:** Stored in `tests/fixtures/golden/`, updated via `--update-snapshots`, appear in PR review.

### Performance Testing

Reference targets (§13):
- 10k SLOC: <2s, <200MB
- 100k SLOC: <15s, <500MB
- 500k SLOC: <60s, <2GB

Profile with `py-spy` if targets are missed.

## CLI & Configuration

### Typer Entry Point

```python
scout [PATH] [OPTIONS]
  --language {auto|python|javascript|typescript}   Default: auto-detect
  --metrics METRIC1,METRIC2,...                      Default: cc,cognitive,loc,duplication,mi
  --format {text|json}                               Default: text
  --output PATH                                      Write to file instead of stdout
  --threshold METRIC=VALUE ...                       Per-metric threshold (can repeat)
  --include GLOB ...                                 Include patterns (additive)
  --exclude GLOB ...                                 Exclude patterns (additive to built-ins)
  --no-respect-gitignore                             Ignore .gitignore
  --jobs N                                           Worker processes (default: cpu_count)
  --quiet / -q                                       Suppress warnings
  --no-color                                         Strip ANSI color codes
  --strict                                           Parse errors → exit 4
  --config PATH                                      Load from specific config file
  --version                                          Print version, exit 0
```

Built-in exclusions (always applied unless overridden):
`node_modules/`, `.venv/`, `venv/`, `__pycache__/`, `.git/`, `dist/`, `build/`, `.next/`, `.nuxt/`, `coverage/`, `*.min.js`, `*.map`

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success, no violations |
| 1 | Success, threshold violations detected |
| 2 | `ConfigError` (bad flag, bad config) |
| 3 | `IOError` or `DiscoveryError` (can't read files) |
| 4 | Parse errors AND `--strict` |
| 130 | KeyboardInterrupt |

## Output Formats

### Text (default)

Uses `rich` for formatted tables and color:
```
scout v{version} — scanned {N} files in {duration}s

Summary
  Files:         {count}
  Total SLOC:    {sloc}
  Duplication:   {pct:.1f}%   {check}
  Avg MI:        {mi:.0f}     {check}

{Per-metric sections, only if violations exist}
Metric Name (comparator)
  file:line  symbol    value  {severity icon}
  ...

Exit code: {code} ({n} threshold violations)
```

Color: green=OK, yellow=WARN, red=ERROR, cyan=INFO. Strips ANSI if not a TTY or `--no-color`.

### JSON

Single document with structure:
```json
{
  "version": "x.y.z",
  "scanned_at": "ISO-8601 UTC",
  "duration_ms": 1500,
  "summary": { "files": 42, "sloc": 15000, "duplication_pct": 2.5, "avg_mi": 72 },
  "files": [
    {
      "path": "rel/path/to/file.py",
      "language": "python",
      "physical_loc": 100,
      "sloc": 85,
      "logical_loc": 42,
      "metrics": [ { "metric_id": "cc", "scope": "function", "symbol": "func_name", "line": 10, "value": 5.0, "severity": "ok" }, ... ],
      "errors": [ { "line": 1, "message": "SyntaxError: ..." } ]
    }
  ],
  "repo_metrics": [ ... ],
  "violations": [ ... ]
}
```

No schema version field; consumers pin a scout version for stability.

## Metric Specifications (Brief)

See full details in §6 of `docs/spec/scout-TECH-SPEC.md`. Key thresholds:

- **CC:** Warning bands [10, 20, 50]. CLI `--threshold cc=N` overrides.
- **Cognitive:** Sonar default 15.
- **Halstead:** No default threshold (reported as-is; used as input to MI).
- **MI:** Green ≥20, yellow 10–19, red <10 (Visual Studio bands). Lower MI = worse.
- **LOC:** Warning at SLOC >500 per file.
- **Duplication:** Green <3%, yellow 3–5%, red >5%.
- **CBO:** Bands [5, 14]. Higher = worse coupling.
- **LCOM:** Bands [1, 3]. 1=cohesive, 2–3=borderline, ≥4=refactor candidate.

## Build & Release

### Build System

- **Backend:** `hatchling`
- **Entrypoint:** `scout = "scout.cli:app"`
- **Package name on PyPI:** `scout-metrics`
- **Version:** Single source of truth in `src/scout/__init__.py`, read by `hatch-vcs` from git tags.

### CI/CD

- GitHub Actions: lint (ruff), typecheck (mypy), test matrix.
- Release: on tag `v*.*.*`, build wheels for Linux/macOS/Windows, publish to PyPI (trusted publishing).
- Versioning: SemVer. v0.x is pre-stable; minor versions may break JSON schema.

## Known Limitations & Open Decisions

### Documented Limitations (per spec §17)

1. **Anonymous function CBO/LCOM:** Arrow functions inside class bodies are closures, not methods (not scored).
2. **TS type-only constructs:** `type`, `interface`, type-only `import type` excluded from CC, Cognitive, logical LOC (but count as physical lines).
3. **No recursion penalty in Cognitive Complexity:** Would require call-graph resolution (deferred to v0.2+).
4. **No type-aware CBO in TypeScript:** Uses tree-sitter (not TS Compiler API) to avoid Node.js dependency. Type aliases aren't resolved.
5. **No call-graph resolution:** LCOM method-call matching is textual; dynamic dispatch is invisible.
6. **No `from foo import *` resolution:** Star imports don't contribute to CBO (conservative undercount).

### Explicit Out-of-Scope for v0.1 (§18)

- Other output formats (SARIF, JUnit XML, HTML, CSV, GitLab Code Quality).
- Incremental analysis, baseline/diff, caching, watch mode.
- Plugin API.
- Other languages (Go, Java, C#, Ruby).
- Web dashboard or daemon.
- Source-comment suppression (`# scout: ignore`).
- Per-directory config inheritance.

## References

- **Full specification:** `docs/spec/scout-TECH-SPEC.md` (19 sections, ~1500 lines).
- **Key sections:**
  - §2: Design goals and trade-offs.
  - §3: High-level architecture.
  - §4: Data model (ParsedFile, MetricValue, etc.).
  - §5: Parser layer (Python/JS/TS implementations).
  - §6: Metric specifications (CC, Cognitive, Halstead, MI, LOC, Duplication, CBO, LCOM).
  - §9: Configuration system.
  - §10: CLI layer.
  - §11: Output formats.
  - §13: Performance targets.
  - §14: Testing strategy.
  - §15: Dependencies.
