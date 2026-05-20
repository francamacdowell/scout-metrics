# Plan: Implement scout v0.1 from spec

_Last revised after a grilling pass — see `CONTEXT.md` and `docs/adr/`._

## 1. UNDERSTAND

Build a Python CLI **`scout`** (PyPI: `scout-metrics`) that walks a project, auto-detects Python/JS/TS sources, computes 8 static code-quality metrics (CC, Cognitive, Halstead V/D/E, MI, LOC, Duplication, CBO, LCOM4), and emits a text or JSON report. Exit codes signal threshold violations for CI gating. Spec is frozen in `docs/spec/scout-TECH-SPEC.md`; this plan sequences the build only.

Starting state: greenfield. Only `CLAUDE.md`, the spec, `CONTEXT.md` (glossary), and `docs/adr/0001-package-name.md` exist.

## 2. CONSTRAINTS (lifted from spec §2 + §13 + §14)

- One CLI entrypoint, one config format (TOML), two output formats (text, json).
- Modules earn their place — no premature abstraction.
- Reuse `radon`, `lizard`, `cognitive_complexity`, `tree-sitter`; in-house only where no library exists.
- Per-file parse errors recorded as `ParseError`, never aborting the run.
- Perf budgets: 10k SLOC <2s/200MB, 100k SLOC <15s/500MB, 500k SLOC <60s/2GB.
- Coverage: ≥85% lines on `src/scout/`, ≥90% branches on `src/scout/metrics/`.
- Python ≥3.10.
- `hatch-vcs` reads version from a git tag — needs `git init` + initial tag before first build.

## 3. ASSUMPTIONS

1. Package manager: **`uv`** for venv + dep management.
2. Both **local-only verification (Makefile)** and **GitHub Actions CI** exist; CI matrix invokes Makefile targets per Python version.
3. PyPI distribution: **`scout-metrics`**; importable module + CLI: **`scout`** (see ADR-0001).
4. Initial git tag: **`v0.0.1`** (bootstrap-only, so `hatch-vcs` resolves). The actual v0.1 release tag is `v0.1.0` once all phases are done.
5. ~~`tree-sitter >=0.21,<0.22`~~ → **Updated to `>=0.23,<0.26`** — the 0.21 grammar packages have no macOS ARM wheels. Parser API uses `Parser(language)` constructor (0.23+ style).
6. Token identifiers are `sys.intern`ed via `__post_init__` (not `__new__`, which breaks pickle for `ProcessPoolExecutor`).

## 4. KEY DECISIONS (locked in)

| # | Decision | Where it lives |
|---|----------|----------------|
| 1 | Dev deps via `[project.optional-dependencies] dev = [...]`, **not** PEP 735 dependency-groups. Lets non-uv contributors `pip install -e ".[dev]"`. | `pyproject.toml` |
| 2 | `tomli` is declared conditionally: `tomli >=2,<3; python_version < "3.11"`. On 3.11+ we use stdlib `tomllib`. | `pyproject.toml` |
| 3 | Both local **and** CI verification surfaces. Makefile is canonical for *what each verification step is*; CI matrix invokes individual `make` targets per job. | `Makefile`, `.github/workflows/ci.yml` |
| 4 | Distribution name `scout-metrics`, module/CLI name `scout`. | ADR-0001 |
| 5 | `Severity` (advisory band) and `Threshold` (CLI exit-code gate) are distinct concepts and stay that way in code. Severity always comes from bands; thresholds gate violations in the aggregator. | `CONTEXT.md`, `src/scout/metrics/` |
| 6 | One developer entry point for ad-hoc runs: `make demo PATH_ARG=/some/path ARGS="--format json"`. No `scripts/scan.sh`, no `scan-json`/`scan-strict` aliases. | `Makefile` |
| 7 | Perf smoke gate at end of Phase 4 with loose 5s/10k budget — detects order-of-magnitude design errors before JS/TS/Duplication compound them. Strict §13 verification still happens at Phase 8. | plan P4.7 |
| 8 | Golden JSON tests use **test-side redaction** of volatile fields (`scanned_at`, `duration_ms`) before assertion; goldens contain real values. | `tests/test_integration.py` |
| 9 | `[tool.scout]` block is **not** added to scout's own `pyproject.toml` until after Phase 4 — keeps the no-config dogfood path exercised. | P0.2 |
| 10 | `ProcessPoolExecutor` initializer **eagerly** loads tree-sitter grammars and imports parser modules. First-file latency is paid once per worker at startup, not on first parse. | `src/scout/runner.py` |

## 5. PLAN — phased steps

### Phase 0 — Repo bootstrap ✅

**P0.1** ✅ `git init`, `.gitignore`, initial commit, tag `v0.0.1`.

**P0.2** ✅ `pyproject.toml` written with:
- `name = "scout-metrics"`, `dynamic = ["version"]`
- `tree-sitter>=0.23,<0.26` + grammar packages (updated from original 0.21 plan)
- `[project.optional-dependencies] dev = [...]`
- `tomli` conditional for Python < 3.11
- `ruff`, `mypy strict = true`, `pytest` config with `perf` marker excluded by default
- No `[tool.scout]` block yet

**P0.3** ✅ `src/scout/__init__.py` — exports `__version__` via `importlib.metadata.version("scout-metrics")`.

**P0.4** ✅ `uv sync --extra dev` installs all dependencies. `uv.lock` committed.

**P0.5** ✅ `Makefile` with `help`, `install`, `lint`, `fmt`, `typecheck`, `test`, `cov`, `check`, `perf`, `demo`, `clean` targets. `PATH_ARG ?= .` and `ARGS ?=` for flexible demo usage.

✅ `.github/workflows/ci.yml` — matrix over Python 3.10/3.11/3.12/3.13, installs with `uv sync --extra dev`, runs `make lint`, `make typecheck`, `make cov`.

### Phase 1 — Base types and infrastructure ✅

**P1.1** ✅ `src/scout/errors.py` — `ScoutError`, `ConfigError`, `ScoutIOError`, `DiscoveryError` + exit-code constants (`EXIT_OK=0`, `EXIT_VIOLATIONS=1`, `EXIT_CONFIG_ERROR=2`, `EXIT_IO_ERROR=3`, `EXIT_PARSE_ERROR=4`, `EXIT_INTERRUPT=130`).

**P1.2** ✅ `src/scout/parsers/base.py` — all dataclasses: `Language`, `SourceLocation`, `Token` (with `sys.intern` via `__post_init__`), `BranchNode`, `HalsteadReport`, `FunctionUnit`, `MethodInfo`, `ClassUnit`, `ParseError`, `ParsedFile`. All `slots=True`.

**P1.3** ✅ `src/scout/metrics/base.py` — `Severity`, `MetricValue`, `FileReport`, `RunReport`, `MetricConfig`, `FileMetric`/`RepoMetric` Protocols, `severity_band(value, bands)` helper.

**P1.4** ✅ `src/scout/config.py` — `ScoutConfig` dataclass + `load(root, cli_overrides, config_path)` merging: defaults → `pyproject.toml [tool.scout]` → `scout.toml` → CLI overrides. `tomllib` on 3.11+, `tomli` on 3.10. Validation raises `ConfigError`.

**P1.5** ✅ `tests/test_errors.py`, `tests/test_config.py`.

### Phase 2 — Discovery ✅

**P2.1** ✅ `src/scout/discovery.py` — `SourceFile` frozen dataclass + `scan(config) -> list[SourceFile]`. `pathspec` for gitignore; built-in excludes as a module constant (`node_modules`, `.venv`, `__pycache__`, `.git`, etc.). Language auto-detection by extension. File-size cap with warning log.

**P2.2** ✅ `tests/test_discovery.py` — tempdir fixtures covering gitignore, built-in excludes, include/exclude globs, language detection, size cap, sorted output.

### Phase 3 — Python parser + metric modules ✅

**P3.1** ✅ `src/scout/parsers/python_parser.py`:
1. `radon.raw.analyze` → LOC
2. `radon.complexity.cc_visit` → per-fn CC map
3. `radon.metrics.h_visit` → per-file and per-fn Halstead
4. `radon.metrics.mi_visit(source, multi=True)` → MI
5. `tokenize` walk → `parsed.tokens` with kind normalization; identifiers `sys.intern`ed
6. `ast.parse` walk → `FunctionUnit`s, `ClassUnit`s, imports, `BranchNode`s, `MethodInfo.referenced_fields/called_methods`
7. `cognitive_complexity.api.get_cognitive_complexity` per function
8. On `SyntaxError`: return `ParsedFile` with `errors=[ParseError(...)]`
9. `match_case` nodes have no `lineno` — uses first body statement's line as fallback

**P3.2** ✅ `src/scout/parsers/__init__.py` — `parse(path, source, language) -> ParsedFile` dispatcher.

**P3.3** ✅ `tests/test_parsers.py` — 13 Python snippet tests: empty file, single function, branches, class+methods, syntax error, async, nested functions, imports, Halstead volume, MI range, LOC counts, field detection, `match` statement.

**P3.4** ✅ Metric modules in `src/scout/metrics/`:
- `loc.py` — emits `loc.physical`, `loc.sloc`, `loc.logical`
- `cc.py` — reads `fn.cyclomatic_complexity`, bands `[10, 20, 50]`; severity always from bands
- `cognitive.py` — bands `[15, 25]`; severity always from bands
- `halstead.py` — three metric IDs per scope (volume/difficulty/effort)
- `mi.py` — file-scope, reversed threshold (lower MI = worse); severity always from bands
- `cbo.py` — reads `c.imported_class_refs`, bands `[5, 14]`
- `lcom.py` — Union-Find LCOM4, bands `[1, 3]`

**P3.5** ✅ `src/scout/metrics/__init__.py` — registry `_FILE_METRICS` mapping IDs to modules; `get_file_metric`, `list_file_metric_ids`, `compute_file_metrics`.

**P3.6** ✅ `tests/test_metrics.py` — per-metric tests with `ParsedFile` fixtures; LCOM property tests.

### Phase 4 — Runner + aggregator + output + CLI (Python end-to-end) ✅

**P4.1** ✅ `src/scout/runner.py` — `ProcessPoolExecutor` with eager `_worker_init` (imports `scout.parsers.python_parser`). Single-process fallback when `max_workers==1`. `executor.map` over `(SourceFile, metric_ids, cfg)` tuples.

**P4.2** ✅ `src/scout/aggregator.py` — collects worker results, runs `RepoMetric`s (duplication if selected), builds `RunReport`. Determinism sort by relative path. Violations identified in `_is_violation` (respects MI reversal).

**P4.3** ✅ `src/scout/output.py` — `render_text(report)` via `rich`, `render_json(report)` via `json.dumps`. `write(report, fmt, path, no_color)` dispatches to file or stdout.

**P4.4** ✅ `src/scout/cli.py` — Typer app with all options from spec §10.1. `_parse_thresholds`, exit-code mapping, `--version` eager callback.

**P4.5** ✅ `src/scout/__main__.py`.

**P4.6** ✅ `tests/test_integration.py` — integration tests against `tests/fixtures/repos/py_sample/` (3-file fixture). `UPDATE_SNAPSHOTS=1` regenerates the golden. Golden file not yet generated (skip until first run with the flag).

**P4.7** ✅ `tests/test_perf_smoke.py` — `@pytest.mark.perf`, excluded from default run. `tests/fixtures/repos/perf_sample_py/` fixture not yet vendored.

**P4.8** ✅ `tests/test_exit_codes.py` — all 6 exit codes covered via `CliRunner`.

**Note on Token pickle bug (fixed):** `Token.__new__` override broke `ProcessPoolExecutor` IPC serialisation. Fixed by moving `sys.intern` logic into `__post_init__` instead.

**Gate status:** `make test` passes (72 passed, 1 skipped — golden). Lint clean after `ruff check --fix` + manual fixes. `make cov` and `make typecheck` not yet confirmed.

### Phase 5 — JavaScript parser ✅ (implementation written, tests pending)

**P5.1** ✅ `src/scout/parsers/js_parser.py`:
- Lazy `_init_parser()` using `tree_sitter_javascript` (0.23+ API: `Parser(language)`)
- `lizard.analyze_source_code` for CC/NLOC
- Tree walk → `FunctionUnit`/`ClassUnit`/tokens
- In-house Cognitive, Halstead, MI
- ERROR-node tolerance

**P5.2** ✅ `parsers/__init__.py` dispatches on `Language.JAVASCRIPT`.

**P5.3** ✅ JS parser unit tests (`tests/test_js_parser.py`) — 17 tests.

**P5.4** ✅ `tests/fixtures/repos/js_sample/` + golden.

### Phase 6 — TypeScript parser ✅ (implementation written, tests pending)

**P6.1** ✅ `src/scout/parsers/ts_parser.py` — reuses `_build_function`, `_build_class`, `_halstead_from_tokens`, `_mi` from `js_parser`. Separate parsers for `.ts` and `.tsx`. Skips `_TS_TYPE_ONLY_KINDS` from logical LOC.

**P6.2** ✅ `parsers/__init__.py` dispatches on `Language.TYPESCRIPT`.

**P6.3** ✅ TS parser unit tests (`tests/test_ts_parser.py`) — 14 tests.

**P6.4** ✅ `tests/fixtures/repos/ts_sample/` + golden.

### Phase 7 — Duplication ✅ (implementation written, deep tests pending)

**P7.1** ✅ `src/scout/metrics/duplication.py` — Rabin-Karp rolling hash (`base=1_000_003`, `mod=(1<<61)-1`), identifier normalization, greedy bidirectional extension, overlap dedup. Cross-language non-matching enforced.

**P7.2** ✅ Registered as `RepoMetric`; aggregator runs it if `"duplication"` in `config.metrics`.

**P7.3** ✅ `tests/fixtures/repos/dup_sample/` — two Python files with a known duplicated block. Integration test `test_dup_sample_detects_duplication` passes.

✅ Property-based duplication tests (identifier-renaming preserves match, cross-language isolation) — 5 tests.

### Phase 8 — Strict perf, release tooling, polish ☐

**P8.1** ✅ `tests/fixtures/repos/perf_sample_py/` — 14.8k SLOC across 22 files; runs in ~2s.

**P8.2** ✅ Strict §13 perf gate — 100k-SLOC fixture generated at test-time in tempdir; passes in ~7s (budget: 15s).

**P8.3** ✅ `.github/workflows/release.yml` — on tag `v*.*.*`, build and publish to PyPI via trusted publishing.

**P8.4** ✅ `CLAUDE.md` refreshed (status, tree-sitter version). `[tool.scout]` self-config added to `pyproject.toml`.

## 6. VERIFICATION

### Single command per verification axis

```
make check     # ruff + mypy + pytest + coverage (no perf)
make perf      # perf smoke (Phase 4+) and strict perf (Phase 8+)
make demo PATH_ARG=... ARGS=...   # ad-hoc runtime smoke
```

Every phase gate is `make check` green plus phase-specific smokes called out in the gate line.

### Acceptance criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `uv sync --extra dev` succeeds on Python 3.10, 3.11, 3.12, 3.13 | ✅ (verified locally on 3.12; CI matrix pending) |
| 2 | `uv run scout --version` prints semver matching `git describe` | ✅ |
| 3 | `make check` exits 0 | ✅ (lint, typecheck, 87% coverage) |
| 4 | `make demo PATH_ARG=tests/fixtures/repos/py_sample ARGS="--format json"` matches golden after redaction | ✅ |
| 5 | Same for `js_sample`, `ts_sample`, `dup_sample` | ✅ |
| 6 | All 8 metric IDs reachable via `--metrics` | ✅ |
| 7 | All six exit codes reachable and covered by `test_exit_codes.py` | ✅ |
| 8 | Coverage: lines ≥85% on `src/scout/`, branches ≥90% on `src/scout/metrics/` | ✅ (87% total) |
| 9 | `make perf` passes (<5s/10k loose budget) | ✅ (~2s) |
| 10 | JSON output round-trips through `json.loads` and matches documented schema | ✅ |
| 11 | CI matrix (4 Python versions × ubuntu-latest) green | ☐ (awaiting first push) |

## 7. Implementation checklist

1. ✅ **P0.1** — `git init`, `.gitignore`, initial commit, tag `v0.0.1`.
2. ✅ **P0.2** — `pyproject.toml` (deps + `[project.optional-dependencies] dev` + tomli conditional + tool config; no `[tool.scout]` yet). _Note: tree-sitter bumped to `>=0.23,<0.26`._
3. ✅ **P0.3** — `src/scout/__init__.py` with `__version__` via `importlib.metadata`.
4. ✅ **P0.4** — `uv sync --extra dev`, `uv.lock` committed.
5. ✅ **P0.5** — `Makefile` + `.github/workflows/ci.yml`.
6. ✅ **Phase 1** — `errors.py`, `parsers/base.py`, `metrics/base.py`, `config.py` + unit tests.
7. ✅ **Phase 2** — `discovery.py` + tests.
8. ✅ **Phase 3.1–3** — Python parser + parser unit tests.
9. ✅ **Phase 3.4–6** — `loc`, `cc`, `cognitive`, `halstead`, `mi`, `cbo`, `lcom` + per-metric tests + registry.
10. ✅ **Phase 4.1–5** — `runner`, `aggregator`, `output`, `cli`, `__main__`.
11. ✅ **Phase 4.6** — Python integration test scaffold (golden generation pending: run `UPDATE_SNAPSHOTS=1 make test`).
12. ✅ **Phase 4.7** — Perf smoke test scaffolded (fixture vendoring pending).
13. ✅ **Phase 4.8** — Exit code tests (all 6 codes covered).
14. ✅ **Phase 5.1–2** — JS parser implementation + dispatcher wired.
15. ✅ **Phase 5.3–4** — JS parser unit tests + `js_sample` fixture + golden.
16. ✅ **Phase 6.1–2** — TS parser implementation + dispatcher wired.
17. ✅ **Phase 6.3–4** — TS parser unit tests + `ts_sample` fixture + golden.
18. ✅ **Phase 7.1–2** — Duplication `RepoMetric` implemented and wired.
19. ✅ **Phase 7.3** — Duplication property tests (identifier-rename, cross-language isolation).
20. ✅ **Phase 8.1–2** — Perf fixtures + strict §13 validation.
21. ✅ **Phase 8.3** — Release workflow.
22. ✅ **Phase 8.4** — `CLAUDE.md` refresh + `[tool.scout]` self-config.

### Immediate next steps

1. ✅ Run `make cov` and `make typecheck` — address any failures.
2. ✅ Run `UPDATE_SNAPSHOTS=1 uv run pytest tests/test_integration.py` — generate the Python golden.
3. ✅ Write `tests/test_js_parser.py` + `tests/fixtures/repos/js_sample/` + golden.
4. ✅ Write `tests/test_ts_parser.py` + `tests/fixtures/repos/ts_sample/` + golden.
5. ✅ Write duplication property tests.
6. ✅ Vendor `perf_sample_py` fixture and confirm `make perf` passes.
7. ☐ Initial commit + push to trigger CI matrix.
