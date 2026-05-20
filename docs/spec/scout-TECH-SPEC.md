# scout — Technical Specification

| Field | Value |
|---|---|
| **Status** | Draft v0.1 |
| **Target version** | v0.1.0 (MVP) |
| **Owner** | TBD |
| **Audience** | Engineers and coding agents implementing scout |
| **Last updated** | 2026-05-17 |

This document specifies the internal design of `scout`, a Python CLI that computes static code-quality metrics for Python, JavaScript, and TypeScript codebases. It is the implementation contract: a competent engineer (or agent) should be able to build v0.1 from this document without re-deriving design decisions.

---

## 1. Purpose and Scope

### 1.1 Purpose

Build a single-binary-feel CLI that:
- Accepts a project root directory.
- Auto-detects which of {Python, JavaScript, TypeScript} are present.
- Computes seven static metrics (CC, Cognitive, Halstead, MI, LOC, Duplication, CBO/LCOM) per file/function/class as applicable.
- Emits a clear default report (text) and a machine-readable output (JSON).
- Returns meaningful exit codes for CI gating.

### 1.2 In scope (v0.1)

- Languages: Python (3.x source), JavaScript (ES2015+), TypeScript (including `.tsx`).
- Metrics: `cc`, `cognitive`, `halstead`, `mi`, `loc`, `duplication`, `cbo`, `lcom`.
- Output: `text` (default, rich-formatted) and `json`. **Only two formats.** SARIF, JUnit XML, and any other CI-integration formats are explicitly out of scope (§18).
- Configuration: CLI flags, `scout.toml`, `[tool.scout]` in `pyproject.toml`.
- Parallelism via `ProcessPoolExecutor`.
- Git-ignore honoring.

### 1.3 Out of scope (v0.1)

- Style linting, formatting, security scanning.
- Daemon/server mode, web UI, REST API.
- Incremental analysis (only-changed-files mode) — deferred to v0.3.
- Baseline/diff mode (regression detection) — deferred to v0.4.
- Plugin API — deferred to v0.5.
- Languages other than Python/JS/TS — deferred.
- Type-aware analysis for TypeScript (no TS Compiler API integration in v0.1).

### 1.4 Non-goals

- Producing per-developer scores. The tool aggregates at file/module/class/function levels only. Per-author attribution is explicitly excluded to avoid misuse as a performance metric.
- Replacing language-native linters (Pylint, ESLint). scout focuses on numeric quality metrics, not rule-based style enforcement.

---

## 2. Design Goals and Trade-offs

### 2.0 Hard constraints — simplicity is non-negotiable

This is a CLI that runs static metrics. It is not a platform, not a framework, not a foundation for future products. **Simplicity overrides every other design value listed below.** Concretely, this means:

1. **One process model, one entrypoint, one config format.** No daemon, no plugin system in v0.1, no alternative invocation modes. The CLI is a single command that scans and prints.
2. **Two output formats only.** `text` for humans, `json` for machines. SARIF, JUnit, HTML reports, CSV — all rejected. A user who needs another format can shell-pipe the JSON through `jq` or a 20-line script.
3. **Directories must earn their place.** A module is in its own file only if it is non-trivial. A subdirectory exists only if it contains more than one non-trivial module. There is no `output/` subdirectory because there are two output functions, and they live in `output.py`.
4. **No premature abstraction.** Three target languages and seven metrics. We do not pre-build for ten of each. Every abstraction in this spec earns its place by paying off within v0.1; reviewers should be able to delete any class or interface and explain what breaks.
5. **No stateful features.** Caches, watchers, incremental modes, baselines, history, dashboards — all deferred (§18). Each scout invocation reads source files, computes metrics, prints results, exits.
6. **Reuse before reinvention.** `radon` and `lizard` exist; we call them. `tree-sitter` exists; we call it. We do not rewrite anything that already works.
7. **Reject features that compound complexity.** Custom rule engines, suppression directives in source comments, severity overrides per file, per-directory config inheritance, multi-tenant runs — none of it in v0.1.

A reviewer reading this spec should be able to point at any module and say "this earns its place because [...]." Anything that fails that test gets cut.

### 2.1 Secondary goals (these may be sacrificed to keep §2.0 true)

| Goal | Implication |
|---|---|
| Fast time-to-MVP | Reuse existing libraries where defensible (`radon`, `lizard`, `cognitive_complexity`). See §2.2. |
| Predictable across machines | Pin parser grammars; no shelling out to external binaries; pure Python + bundled tree-sitter grammars. |
| Defensible numbers | Cite the canonical source for every metric formula; document deviations explicitly. |
| Trivial CI installation | Single `pip install scout-metrics`; no external runtimes (no Node, no Go, no system libs beyond a C compiler for tree-sitter wheels). |
| Survive bad input | Per-file parse errors are recorded but never abort the run. |

### 2.2 Decisions and rationale

**Decision:** Hybrid implementation. Use existing Python libraries where they exist with confidence; reimplement only what they don't cover.

| Metric | Python target | JS/TS target |
|---|---|---|
| CC | **`radon`** (`radon.complexity.cc_visit`) | **`lizard`** |
| Cognitive Complexity | **`cognitive_complexity`** | scout (in-house, tree-sitter) |
| Halstead V/D/E | **`radon`** (`radon.metrics.h_visit`) | scout (in-house, tree-sitter) |
| Maintainability Index | **`radon`** (`radon.metrics.mi_visit`) | scout (in-house, composes our Halstead + CC + LOC) |
| LOC (physical/SLOC/logical) | **`radon`** (`radon.raw.analyze`) | **`lizard`** (NLOC) + scout for logical LOC |
| Duplication | scout (in-house, Rabin–Karp on normalized tokens) | scout |
| CBO | scout (in-house, stdlib `ast`) | scout (in-house, tree-sitter) |
| LCOM (LCOM4) | scout (in-house, stdlib `ast`) | scout (in-house, tree-sitter) |

**Rationale:** `radon` is the de facto Python metrics library and has been numerically stable for a decade; reusing it avoids re-deriving its (well-defended) edge-case decisions for Python tokenization, operator classification, and MI variant computation. `lizard` is the only mature multi-language CC implementation in Python; for JS/TS, its CC numbers are what the JS community recognizes. `cognitive_complexity` is a small, focused PyPI package that implements Sonar's spec for Python (no equivalent for JS/TS, so we reimplement those). Reimplementing what `radon` and `lizard` already do correctly would be Not-Invented-Here with a stopwatch.

**Trade-off:** Multiple parsing passes per file — `radon`'s `ast` walk, `lizard`'s state-machine walk, and our own `ast`/tree-sitter walks for in-house metrics. Each pass is fast individually; cumulative cost is acceptable for v0.1 and can be optimized later by extracting a shared parse-tree-once layer. Practical impact on a 100k-SLOC repo is in the seconds-not-minutes range, well within §13's targets.

**Alternative considered:** Reimplement everything on a unified `ParsedFile` model. Rejected because the velocity gain and numeric defensibility of `radon` and `lizard` outweigh the architectural cleanliness of one-parser-per-file.

**Decision:** Use Python's stdlib `ast` + `tokenize` for Python parsing, and `tree-sitter` for JS/TS.
**Rationale:** stdlib is best-in-class for Python and adds zero dependencies. tree-sitter is the dominant cross-language parser ecosystem with maintained Python bindings.
**Alternative considered:** Use tree-sitter for all three for uniformity. Rejected because stdlib `ast` is more ergonomic for Python and we lose nothing by mixing.

**Decision:** Use `ProcessPoolExecutor`, not threads or asyncio.
**Rationale:** Metric computation is CPU-bound and AST-bound. The GIL would serialize threads; asyncio doesn't help with CPU work.
**Alternative considered:** Free-threaded Python (3.13+). Rejected for v0.1 because not all target environments have GIL-free builds yet.

**Decision:** Default metric set excludes `cbo` and `lcom`.
**Rationale:** OO-graph metrics are noisier and slower, and modern JS code is often non-OO. They run only on `--metrics all` or when explicitly requested.

**Decision:** TypeScript parsing via tree-sitter, not the TypeScript Compiler API.
**Rationale:** TS Compiler API requires Node. Bringing Node into a Python tool's install path makes the install story unpredictable. Trade-off: CBO/LCOM in TS cannot resolve type-aliased references; documented as a known limitation in the README.

**Decision:** Configuration uses TOML; `scout.toml` is the canonical filename; `pyproject.toml [tool.scout]` is also supported.
**Rationale:** TOML is the Python ecosystem's standard since PEP 518. Supporting both gives users a choice without parsing two formats.

---

## 3. High-Level Architecture

```
                                ┌─────────────────────┐
   argv ──────► CLI (Typer) ───►│ Config (toml+flags) │
                                └─────────────────────┘
                                            │
                                            ▼
                                ┌─────────────────────┐
                                │ Discovery           │  walks fs, applies gitignore + globs,
                                │ (pathspec + os.walk)│  returns Iterable[SourceFile]
                                └─────────────────────┘
                                            │
                                            ▼
                                ┌─────────────────────┐
                                │ Runner              │  fans out via ProcessPoolExecutor
                                │                     │
                                │  ┌───────────────┐  │
                                │  │ Worker (per   │  │
                                │  │ file):        │  │
                                │  │  parse → AST  │  │
                                │  │  compute      │  │
                                │  │  per-file     │  │
                                │  │  metrics      │  │
                                │  └───────────────┘  │
                                └──────────┬──────────┘
                                           │
                       ┌───────────────────┴──────────────────┐
                       ▼                                      ▼
              ┌─────────────────┐                  ┌─────────────────┐
              │ Aggregator      │                  │ Duplication     │
              │ (repo totals,   │                  │ (cross-file     │
              │  threshold      │                  │  Rabin–Karp)    │
              │  evaluation)    │                  │                 │
              └────────┬────────┘                  └────────┬────────┘
                       │                                    │
                       └───────────────┬────────────────────┘
                                       ▼
                            ┌─────────────────────┐
                            │ Output (text or     │
                            │  json — one module) │
                            └─────────────────────┘
```

### 3.1 Module layout

```
src/scout/
├── __init__.py           # package version
├── __main__.py           # `python -m scout` entrypoint → cli:app()
├── cli.py                # Typer app, argv parsing, dispatch
├── config.py             # ScoutConfig dataclass, loader, validation
├── discovery.py          # File walk, gitignore, glob filtering
├── runner.py             # ProcessPoolExecutor orchestration
├── parsers/
│   ├── __init__.py       # parse(path, source, language) -> ParsedFile
│   ├── base.py           # ParsedFile, FunctionUnit, ClassUnit, Token, ParseError types
│   ├── python_parser.py  # radon (CC/MI/Halstead/LOC), cognitive_complexity, stdlib ast (CBO/LCOM)
│   ├── js_parser.py      # lizard (CC/NLOC) + tree-sitter-javascript (Cognitive/Halstead/MI/CBO/LCOM/dup tokens)
│   └── ts_parser.py      # lizard (CC/NLOC) + tree-sitter-typescript (same as JS)
├── metrics/
│   ├── __init__.py       # registry: id -> metric module
│   ├── base.py           # MetricResult, Severity, metric protocol
│   ├── cc.py
│   ├── cognitive.py
│   ├── halstead.py
│   ├── mi.py
│   ├── loc.py
│   ├── duplication.py    # cross-file, runs in aggregator
│   ├── cbo.py
│   └── lcom.py
├── aggregator.py         # combines per-file results into a RunReport
├── output.py             # text + JSON in one module (the only two formats — §2.0)
└── errors.py             # exception classes, exit code mapping
```

---

## 4. Data Model

All shared types live in `parsers/base.py` and `metrics/base.py`. v0.1 uses `dataclasses` with `slots=True`. Type aliases use `typing` where relevant.

### 4.1 Core parser types

```python
# parsers/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

class Language(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"

@dataclass(slots=True, frozen=True)
class SourceLocation:
    line_start: int      # 1-indexed
    line_end: int        # inclusive
    col_start: int = 0
    col_end: int = 0

@dataclass(slots=True, frozen=True)
class Token:
    kind: str            # normalized kind, see §5.4
    value: str           # raw text
    line: int

@dataclass(slots=True)
class BranchNode:
    """One control-flow branching point inside a function. Used by CC and Cognitive."""
    kind: str            # one of: "if", "elif", "else", "for", "while", "case",
                         # "catch", "ternary", "boolop_and", "boolop_or",
                         # "boolop_nullish", "optional_chain"
    nesting_depth: int   # 0 at top of function; +1 inside each containing branch
    location: SourceLocation

@dataclass(slots=True)
class HalsteadReport:
    h1: int                         # distinct operators (n1)
    h2: int                         # distinct operands (n2)
    N1: int                         # total operators
    N2: int                         # total operands
    volume: float
    difficulty: float
    effort: float

@dataclass(slots=True)
class FunctionUnit:
    name: str                       # "" for anonymous lambdas/arrow functions
    qualified_name: str             # e.g. "ClassName.method" or "module.func"
    location: SourceLocation
    params: tuple[str, ...]
    branches: list[BranchNode]
    tokens: list[Token]             # tokens *inside* the function body
    sloc: int                       # source lines of code inside the function
    # Pre-computed by parser via radon/lizard/cognitive_complexity; metric
    # modules consume these directly rather than recomputing.
    cyclomatic_complexity: int      # from radon (Python) or lizard (JS/TS)
    cognitive_score: int            # from cognitive_complexity (Python) or in-house (JS/TS)
    halstead: HalsteadReport | None # from radon (Python) or in-house (JS/TS); None if empty body

@dataclass(slots=True)
class MethodInfo:
    name: str
    location: SourceLocation
    referenced_fields: frozenset[str]  # self.foo / this.foo references inside body
    called_methods: frozenset[str]     # self.bar() / this.bar() references inside body

@dataclass(slots=True)
class ClassUnit:
    name: str
    qualified_name: str
    location: SourceLocation
    fields: frozenset[str]             # statically declared field names
    methods: tuple[MethodInfo, ...]
    imported_class_refs: frozenset[str]  # external class names referenced anywhere in the class

@dataclass(slots=True)
class ParseError:
    line: int
    message: str

@dataclass(slots=True)
class ParsedFile:
    path: Path
    language: Language
    physical_loc: int
    sloc: int
    logical_loc: int
    functions: list[FunctionUnit]
    classes: list[ClassUnit]
    tokens: list[Token]                # full file token stream, used for duplication
    imports: dict[str, str]            # local_name -> source_module (best-effort)
    # File-level pre-computed values from radon (Python) or computed by the
    # parser by aggregating function-level data (JS/TS).
    file_halstead: HalsteadReport | None
    maintainability_index: float       # 0-100 (Microsoft variant)
    errors: list[ParseError]
```

### 4.2 Metric result types

```python
# metrics/base.py
from dataclasses import dataclass
from enum import Enum

class Severity(str, Enum):
    OK = "ok"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"

@dataclass(slots=True, frozen=True)
class MetricValue:
    metric_id: str                 # e.g. "cc", "cognitive"
    file: str                      # relative path from project root
    scope: str                     # "file" | "function" | "class" | "module" | "repo"
    symbol: str | None             # function or class qualified_name, if applicable
    line: int | None               # 1-indexed
    value: float                   # all metrics are numeric; floats keep MI etc. precise
    threshold: float | None
    severity: Severity

@dataclass(slots=True)
class FileReport:
    path: str
    language: Language
    physical_loc: int
    sloc: int
    logical_loc: int
    metrics: list[MetricValue]
    errors: list[ParseError]

@dataclass(slots=True)
class RunReport:
    version: str
    scanned_at: str                # ISO-8601 UTC
    duration_ms: int
    files_scanned: int
    files: list[FileReport]
    repo_metrics: list[MetricValue]
    violations: list[MetricValue]   # subset of metrics with severity != OK
```

### 4.3 Metric protocol

Every metric module implements one of two protocols depending on scope.

```python
# metrics/base.py
from typing import Protocol
from parsers.base import ParsedFile

class FileMetric(Protocol):
    """Computes a metric using only per-file data. Runs in worker processes."""
    id: str
    def compute(self, parsed: ParsedFile, config: MetricConfig) -> list[MetricValue]: ...

class RepoMetric(Protocol):
    """Computes a metric across all files. Runs in the main process after aggregation."""
    id: str
    def compute(self, files: list[ParsedFile], config: MetricConfig) -> list[MetricValue]: ...
```

`cc`, `cognitive`, `halstead`, `mi`, `loc`, `cbo`, `lcom` are `FileMetric`. `duplication` is a `RepoMetric`.

---

## 5. Parser Layer

### 5.1 Common contract

```python
# parsers/__init__.py
def parse(path: Path, source: str, language: Language) -> ParsedFile: ...
```

The parser layer is the *only* place that touches a language-specific syntax. All metric code consumes `ParsedFile`. Parse errors are caught inside each parser and returned as `ParsedFile.errors`; parsers never raise on syntax errors. They may raise on I/O errors handled at the runner level.

### 5.2 Python parser

**Libraries:** `ast` (stdlib), `tokenize` (stdlib), `radon` (CC/MI/Halstead/LOC), `cognitive_complexity` (Cognitive).

**Steps:**
1. Read source.
2. Run `radon.raw.analyze(source)` once. Map to `parsed.physical_loc`, `parsed.sloc`, `parsed.logical_loc`.
3. Run `radon.complexity.cc_visit(source)` once. Build a `name → cc` map keyed by `radon.complexity.Function.fullname` (e.g. `"ClassName.method"`).
4. Run `radon.metrics.h_visit(source)` once. Build a `name → halstead` map for per-function Halstead; keep `total` for per-file Halstead.
5. Run `radon.metrics.mi_visit(source, multi=True)` once. Store as `parsed.maintainability_index` (used by the `mi` metric module verbatim).
6. Tokenize via `tokenize.generate_tokens`:
   - Skip `ENCODING`, `NEWLINE`, `NL`, `INDENT`, `DEDENT`, `ENDMARKER`.
   - Map `OP` → kind `"op"`; `NAME` → `"identifier"` (further split into `"keyword"` if in `keyword.kwlist`); `NUMBER` → `"number"`; `STRING` → `"string"`; `COMMENT` → not in token list but counted toward `physical_loc - sloc`.
   - Token stream is used only for duplication (Halstead numbers come from radon).
7. Parse: `tree = ast.parse(source, filename=str(path))`.
8. Walk `tree` to build the structural model:
   - Each `ast.FunctionDef` / `ast.AsyncFunctionDef` / `ast.Lambda` → `FunctionUnit`.
     - Attach `cyclomatic_complexity` from step 3.
     - Attach `halstead` from step 4.
     - Compute `cognitive_score = cognitive_complexity.api.get_cognitive_complexity(node)` and attach.
     - Collect `BranchNode`s by walking the function body (used downstream for verification or fallback).
   - Each `ast.ClassDef` → `ClassUnit`:
     - Fields = names assigned at class scope or in `__init__` via `self.NAME = ...`.
     - For each method, walk its body collecting `self.NAME` and `cls.NAME` reads → `referenced_fields`; `self.NAME(...)` and `cls.NAME(...)` calls → `called_methods`.
     - `imported_class_refs` = class-body identifiers ∩ `imports` keys − allowlist (§6.7).
9. Build `imports` from `Import`/`ImportFrom` nodes:
   - `import os` → `{"os": "os"}`
   - `import numpy as np` → `{"np": "numpy"}`
   - `from foo import bar` → `{"bar": "foo.bar"}`
   - `from foo import bar as b` → `{"b": "foo.bar"}`
   - `from foo import *` → not added; flagged for §6.7 conservative handling.
10. On `SyntaxError`: return `ParsedFile` with `errors=[ParseError(line=e.lineno or 0, message=str(e))]` and empty metric inputs. radon/cognitive_complexity are NOT called when parsing fails.

**Branch node mapping (Python):**

| AST node | BranchNode.kind |
|---|---|
| `If` | `"if"` |
| `If` with `orelse` containing only another `If` | `"elif"` (synthetic, by walking the elif chain) |
| `If` with non-empty `orelse` that is not another `If` | `"else"` |
| `For`, `AsyncFor` | `"for"` |
| `While` | `"while"` |
| `Try.handlers[*]` | `"catch"` (one per `ExceptHandler`) |
| `IfExp` | `"ternary"` |
| `BoolOp(op=And)` | `"boolop_and"` for each additional operand beyond the first |
| `BoolOp(op=Or)` | `"boolop_or"` for each additional operand beyond the first |
| `Match.cases[*]` (Py 3.10+) | `"case"` (one per match case) |

### 5.3 JavaScript parser

**Libraries:** `tree-sitter`, `tree-sitter-javascript`, `lizard`.

**Steps:**
1. Lazy-load the tree-sitter parser at module import (compile grammar once per worker process).
2. Run `lizard.analyze_source_code(filename, source)` once. Build a `name → cc` and `name → nloc` map from `analysis.function_list`.
3. Parse: `tree = parser.parse(source.encode("utf-8"))`.
4. `physical_loc` = `source.count("\n") + (0 if source.endswith("\n") else 1)`. `sloc` = `analysis.nloc` from step 2. `logical_loc` = count of statement-class tree-sitter nodes (see §6.5).
5. Walk the tree:
   - `function_declaration`, `function_expression`, `arrow_function`, `method_definition`, `generator_function_declaration` → `FunctionUnit`.
     - Match against lizard's function list by `(name, start_line)`; attach `cyclomatic_complexity` and per-function `tokens`.
     - Compute Halstead per §6.3 over the function's token slice; attach.
     - Compute Cognitive Complexity per §6.2; attach.
     - Populate `branches: list[BranchNode]` per §5.3 branch mapping for any metric that needs them later.
   - `class_declaration`, `class_expression` → `ClassUnit`. Walk methods; build `referenced_fields` (`this.NAME`), `called_methods` (`this.NAME()`), `imported_class_refs`.
6. Token extraction: walk leaf nodes; map node types to kinds per §5.5 normalization table. Tokens used for Halstead (per-function and per-file) and duplication.
7. Imports: extract from `import_statement` nodes; also handle top-level `require()` calls as a best-effort `CallExpression(callee=Identifier("require"), args=[StringLiteral(M)])`.
8. On parse errors (tree contains `ERROR` nodes): record `ParseError` per error region; continue extracting from the non-error parts of the tree.

**Branch node mapping (JS):**

| tree-sitter node type | BranchNode.kind |
|---|---|
| `if_statement` (consequence) | `"if"` |
| `if_statement` (alternative is another `if_statement`) | `"elif"` |
| `if_statement` (alternative present, not nested if) | `"else"` |
| `for_statement`, `for_in_statement`, `for_of_statement` | `"for"` |
| `while_statement`, `do_statement` | `"while"` |
| `switch_case` | `"case"` |
| `catch_clause` | `"catch"` |
| `ternary_expression` | `"ternary"` |
| `binary_expression` with operator `&&` | `"boolop_and"` (one per extra operand in chain) |
| `binary_expression` with operator `\|\|` | `"boolop_or"` |
| `binary_expression` with operator `??` | `"boolop_nullish"` |
| `optional_chain` | `"optional_chain"` |

### 5.4 TypeScript parser

**Libraries:** `tree-sitter`, `tree-sitter-typescript` (exposes two grammars: `typescript` for `.ts`/`.mts`/`.cts`; `tsx` for `.tsx`), `lizard` (which supports TypeScript natively).

**Steps:** Same as JS parser (§5.3): run lizard for CC/NLOC, parse with the appropriate tree-sitter grammar, walk the tree to build `FunctionUnit`/`ClassUnit`, compute in-house Cognitive Complexity / Halstead / CBO / LCOM. Additional TS-specific concerns:
- Type-only statements (`type X = ...`, `interface I { ... }`, type-only `import type`) do NOT contribute to logical LOC, CC, or Cognitive. They DO contribute to physical_loc and SLOC (they're real source lines).
- Type annotations on expressions (`x as Foo`, `x: Foo`) are excluded from Halstead in v0.1.
- Decorators on methods: walk past them to find the wrapped method, which becomes the `FunctionUnit`. Decorator expressions themselves are excluded from function-level CC and Cognitive.
- Optional chaining (`?.`) and nullish coalescing (`??`) behave as in JS.
- `enum` declarations are treated as type-only (not classes, not functions).

Choose grammar by file extension:

| Extension | tree-sitter language |
|---|---|
| `.ts`, `.mts`, `.cts` | tree-sitter-typescript (typescript) |
| `.tsx` | tree-sitter-typescript (tsx) |

### 5.5 Token kind normalization

Across languages, tokens collapse into a small set of kinds used by Halstead and duplication:

| kind | examples |
|---|---|
| `"keyword"` | `if`, `function`, `class`, `return`, `yield`, `await`, `async` |
| `"identifier"` | user-defined names |
| `"op"` | `+`, `-`, `=`, `==`, `=>`, `?.`, `??`, `&&`, `||` |
| `"number"` | `1`, `3.14`, `0xff`, `1n` |
| `"string"` | string literals (including template strings as one token) |
| `"regex"` | regex literals (JS/TS only) |
| `"punct"` | `(`, `)`, `,`, `;`, `:` |
| `"comment"` | not in token list; counted for LOC only |

---

## 6. Metric Implementations

Each metric below is specified as: **library** (existing or in-house), **inputs**, **algorithm** (pseudocode), **edge cases**, **threshold mapping**.

### 6.0 Library reuse and call patterns

scout calls external libraries from inside the parser layer, not the metric layer. The parser is responsible for:
1. Running radon/lizard/cognitive_complexity against the source.
2. Translating their output into `MetricValue`s.
3. Also building the `ParsedFile` for the in-house metrics that need an AST view.

This keeps the metric modules uniform (they all consume `ParsedFile`) and gives us one place where library numerics live, so we can swap or upgrade the libraries without touching metric code.

**radon call surface (Python only):**
```python
from radon.complexity import cc_visit
from radon.metrics import h_visit, mi_visit
from radon.raw import analyze

# CC per function (returns list of Function namedtuples with .complexity, .lineno, .name, .classname)
cc_results = cc_visit(source)

# Halstead per file + per function
h_results = h_visit(source)             # has .total and .functions

# MI per file (multi=True gives a single 0-100 float)
mi_value = mi_visit(source, multi=True)

# Raw LOC metrics
raw = analyze(source)                    # .loc, .lloc, .sloc, .comments, .multi, .blank
```

**lizard call surface (JS/TS, also works for Python):**
```python
import lizard

analysis = lizard.analyze_file.analyze_source_code(filename, source)
# analysis.function_list[i] has: cyclomatic_complexity, name, nloc, length,
#                                 token_count, parameters, start_line, end_line
# analysis.nloc, analysis.average_cyclomatic_complexity
```

For Python files we *prefer* radon over lizard because radon's CC counts boolean operators consistent with the modern McCabe interpretation; lizard's are slightly more conservative.

**cognitive_complexity call surface (Python only):**
```python
from cognitive_complexity.api import get_cognitive_complexity
import ast

tree = ast.parse(source)
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        score = get_cognitive_complexity(node)
```

**Division of responsibility.** The parser populates raw numeric values on `FunctionUnit` / `ClassUnit` / `ParsedFile` (e.g. `fn.cyclomatic_complexity`, `parsed.maintainability_index`). The metric modules read those raw values, apply threshold logic, and construct `MetricValue`s. This keeps `MetricValue` construction in exactly one place per metric (the metric module), and keeps the parser focused on extraction and library orchestration. Metric modules are language-agnostic: they read the same `ParsedFile` fields regardless of whether radon, lizard, or our own walk populated them.

---

### 6.1 Cyclomatic Complexity (`cc`)

**Library:** `radon.complexity.cc_visit` (Python) · `lizard.analyze_source_code` (JS/TS).

**Inputs:** Source code (passed to libraries). For consistency, the parser also populates `FunctionUnit.branches` from its own AST walk so the metric module has a uniform shape across languages.

**Algorithm:**

For Python:
```python
from radon.complexity import cc_visit
results = cc_visit(source)        # one entry per function/method
# entry has: name, classname, complexity, lineno, endline
```

For JS/TS:
```python
analysis = lizard.analyze_source_code(filename, source)
for fn in analysis.function_list:
    cc = fn.cyclomatic_complexity   # int
```

For both languages, the metric module then converts to `MetricValue`:
```python
def compute(parsed: ParsedFile, cfg) -> list[MetricValue]:
    out = []
    for fn in parsed.functions:
        cc = fn.cyclomatic_complexity   # populated by parser from radon/lizard
        threshold = cfg.thresholds.get("cc")
        severity = (Severity.WARN if threshold is not None and cc > threshold
                    else severity_band(cc, [10, 20, 50]))
        out.append(MetricValue(
            metric_id="cc",
            file=str(parsed.path),
            scope="function",
            symbol=fn.qualified_name,
            line=fn.location.line_start,
            value=float(cc),
            threshold=threshold,
            severity=severity,
        ))
    return out
```

**What counts as a branch (canonical reference):**

| Construct | Python (radon) | JS/TS (lizard) |
|---|---|---|
| `if` / `elif` | +1 each | +1 each |
| `else` | 0 | 0 |
| `for`, `while` | +1 each | +1 each |
| `try` | 0 | 0 |
| `except` / `catch` | +1 each | +1 each |
| `finally` | 0 | 0 |
| `with` (Python) | 0 | n/a |
| `assert` (Python) | 0 (radon convention) | n/a |
| `match`/`case` (Python 3.10+) | +1 per `case` | n/a |
| `switch`/`case` | n/a | +1 per `case` |
| ternary `a ? b : c` / `a if cond else b` | +1 | +1 |
| `and`/`or` (`&&`/`||`) | +1 per additional operand | +1 per additional operand |
| `??` (nullish) | n/a | +1 per additional operand |
| `?.` (optional chain) | n/a | 0 |

**Edge cases:**
- Empty function: CC = 1.
- Async function: same rules apply; `await` is not a branch.
- Generator: `yield` is not a branch.
- Nested functions (closures): each is a separate `FunctionUnit` with its own CC; the outer function's CC does not include the inner's branches.

**Thresholds:** Default warning boundaries `[10, 20, 50]` mapping to green/yellow/orange/red. CLI threshold `--threshold cc=N` sets the cutoff above which severity is forced to WARN.

### 6.2 Cognitive Complexity (`cognitive`)

**Library:** `cognitive_complexity.api.get_cognitive_complexity` (Python). For JS/TS, in-house implementation against the tree-sitter AST following the Sonar spec.

**Inputs:**
- Python: `ast.FunctionDef` / `ast.AsyncFunctionDef` node per function (passed to `get_cognitive_complexity`).
- JS/TS: `FunctionUnit.branches` (with `nesting_depth`), plus per-function boolean-expression metadata populated by the parser.

**Algorithm — Python:**
```python
from cognitive_complexity.api import get_cognitive_complexity
import ast

tree = ast.parse(source)
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        score = get_cognitive_complexity(node)
        # parser stores score on the matching FunctionUnit
```

**Algorithm — JS/TS (in-house):**

For each function, walk its body recursively while tracking a nesting-depth counter. Cognitive Complexity is the running sum of three rule families per the Sonar spec:

1. **Increments that add nesting depth** (entering increments `nesting`):
   `if_statement`, `for_statement`, `for_in_statement`, `for_of_statement`,
   `while_statement`, `do_statement`, `switch_statement`, `catch_clause`,
   `ternary_expression`.
2. **Increments that do NOT add nesting depth** (cost only):
   `else_clause` (the bare `else` of an `if`), `goto`/labelled `break`/`continue`.
3. **Logical operator sequences** (handled per-expression, not per-operator):
   - Within a single boolean expression, walk operators left-to-right.
   - First operator in the expression: +1.
   - Each time the operator kind changes within the expression (`&&` → `||`, `||` → `??`, etc.): +1.
   - Same-kind runs (e.g. `a && b && c && d`) cost nothing beyond the first +1.

```python
def cognitive_js(fn_node, depth=0):
    score = 0
    for child in fn_node.named_children:
        kind = child.type
        if kind in NESTING_INCREMENTS:
            score += 1 + depth
            score += cognitive_js(child, depth + 1)
        elif kind in BARE_INCREMENTS:
            score += 1
            score += cognitive_js(child, depth)
        elif kind == "binary_expression" and is_boolean(child):
            score += boolean_expression_cost(child)   # rule 3
            score += cognitive_js(child, depth)       # recurse for non-boolean parts
        else:
            score += cognitive_js(child, depth)
    return score

def boolean_expression_cost(expr_node):
    operators = collect_boolean_operators_in_order(expr_node)
    if not operators:
        return 0
    cost = 1
    for prev, curr in pairwise(operators):
        if prev != curr:
            cost += 1
    return cost
```

**Reference:** G. Ann Campbell, *Cognitive Complexity: A New Way of Measuring Understandability*, SonarSource, 2018. scout's Python implementation delegates to the `cognitive_complexity` PyPI package; the JS/TS implementation follows §3.1–§3.4 of the paper.

**Edge cases:**
- Recursion penalty: Sonar adds +1 per recursive call. v0.1 does NOT implement this (requires call-graph resolution). Documented limitation.
- Labelled `break`/`continue` (JS/TS): +1 per the spec.
- Python `match`/`case`: each `case` increments score by `1 + nesting` (treated as `case` in the nesting set).
- Nested functions: each is its own `FunctionUnit` with its own score; the outer function does NOT inherit the inner's complexity.

**Thresholds:** Default warning at 15 (Sonar's published default).

### 6.3 Halstead (`halstead`)

**Library:** `radon.metrics.h_visit` (Python). For JS/TS, in-house implementation over the tree-sitter token stream.

**Inputs:**
- Python: full source (passed to `h_visit`). radon does its own tokenization via stdlib `tokenize`.
- JS/TS: `FunctionUnit.tokens` and `ParsedFile.tokens` (populated by parser walking the tree-sitter tree).

**Algorithm — Python (radon):**
```python
from radon.metrics import h_visit
results = h_visit(source)
# results.total is a tuple-like with h1, h2, N1, N2, vocabulary, length,
#                                     calculated_length, volume, difficulty, effort, ...
# results.functions is a list of (name, HalsteadReport) pairs
```

scout uses radon's `volume`, `difficulty`, `effort` directly. radon's operator/operand classification for Python is the reference — we don't second-guess it.

**Algorithm — JS/TS (in-house):**
```python
def halstead(tokens) -> dict:
    operators = [t for t in tokens if t.kind in {"op", "keyword", "punct"}]
    operands  = [t for t in tokens if t.kind in {"identifier", "number", "string", "regex"}]
    n1 = len({(t.kind, t.value) for t in operators})
    n2 = len({(t.kind, t.value) for t in operands})
    N1, N2 = len(operators), len(operands)
    n, N = n1 + n2, N1 + N2
    V = N * log2(n) if n > 0 else 0.0
    D = (n1 / 2) * (N2 / n2) if n2 > 0 else 0.0
    E = D * V
    return {"V": V, "D": D, "E": E, "n1": n1, "n2": n2, "N1": N1, "N2": N2}
```

Compute per function and per file. Emit three `MetricValue`s per scope with the variant in the `symbol` field or in a `details` sub-key — see §11.2:
- `metric_id="halstead.volume"`, `value=V`
- `metric_id="halstead.difficulty"`, `value=D`
- `metric_id="halstead.effort"`, `value=E`

**Token classification for JS/TS (operators vs operands):**

| tree-sitter node kind | Halstead role |
|---|---|
| `if`, `else`, `for`, `while`, `return`, `function`, `class`, `extends`, `new`, `await`, `async`, `yield`, `import`, `export`, `from`, `as`, `typeof`, `instanceof`, `in`, `of`, `delete`, `void`, etc. | operator (keyword) |
| `+`, `-`, `*`, `/`, `%`, `**`, `=`, `+=`, `-=`, `*=`, `/=`, `%=`, `**=`, `==`, `===`, `!=`, `!==`, `<`, `>`, `<=`, `>=`, `&&`, `\|\|`, `??`, `!`, `?:`, `?.`, `=>`, `...`, `&`, `\|`, `^`, `~`, `<<`, `>>`, `>>>` | operator (op) |
| `(`, `)`, `{`, `}`, `[`, `]`, `,`, `;`, `:`, `.` | operator (punct) |
| user identifiers, parameter names | operand (identifier) |
| `number` (incl. `bigint`) | operand (number) |
| `string`, `template_string` | operand (string) |
| `regex` | operand (regex) |
| `true`, `false`, `null`, `undefined` | operand (identifier) |
| comments | excluded |
| type annotations (TS only) | excluded |

**Edge cases:**
- File with only comments or empty: V=D=E=0.
- Python f-strings: radon treats them as a single token; scout reports radon's number unchanged.
- JS/TS template strings: treated as a single `string` operand in v0.1 (do not descend into interpolations).
- TS type-only constructs (`interface`, `type X = ...`): excluded from Halstead in v0.1 — they're declarative, not executable code.

**Thresholds:** None. Reported as-is. (Halstead is mostly useful as an input to MI; see §6.4.)

### 6.4 Maintainability Index (`mi`)

**Library:** `radon.metrics.mi_visit` (Python). In-house composite for JS/TS, using §6.1 CC + §6.3 Halstead Volume + §6.5 SLOC.

**Inputs:**
- Python: full source (passed to `mi_visit(source, multi=True)`).
- JS/TS: per-file SLOC, per-file Halstead Volume (sum of function Volumes from §6.3), per-file CC (sum of function CCs from §6.1).

**Algorithm — Python (radon):**
```python
from radon.metrics import mi_visit
mi_value = mi_visit(source, multi=True)   # returns float in [0, 100]
```
radon uses the Microsoft 0–100 rescaling by default when `multi=True`.

**Algorithm — JS/TS (in-house):**
```python
def mi(file_sloc: int, file_volume: float, file_cc: int) -> float:
    V = max(file_volume, 1.0)         # avoid log(0)
    LOC = max(file_sloc, 1)
    raw = 171 - 5.2 * log(V) - 0.23 * file_cc - 16.2 * log(LOC)
    return max(0.0, min(100.0, raw * 100 / 171))
```

Where `file_volume = sum(fn.halstead.volume for fn in parsed.functions)` and `file_cc = sum(fn.cyclomatic_complexity for fn in parsed.functions)`.

Reported per file with `scope="file"`. Severity bands match Visual Studio: red <10, yellow 10–19, green ≥20.

**Edge cases:**
- Files with zero functions but non-zero LOC (e.g., constant declarations, config modules): CC = 0, Volume = file-level Halstead from `ParsedFile.tokens`.
- Files with zero SLOC (only comments or blank): MI = 100 (sentinel: "nothing to maintain"). This matches radon's behavior.
- Negative raw MI: clamped to 0 by the formula; documented as a known quirk of the formula on giant files.

**Thresholds:** Default warning at `mi < 20` (Visual Studio convention; configurable via `--threshold mi=N`, where files *below* the threshold are flagged — this is the only metric where lower is worse).

### 6.5 Lines of Code (`loc`)

**Library:** `radon.raw.analyze` (Python — provides `loc`, `lloc`, `sloc`, `comments`, `multi`, `blank`). `lizard.analyze_source_code` (JS/TS — provides `nloc` per function and per file). In-house computation of logical LOC for JS/TS by counting tree-sitter statement nodes.

**Inputs:**
- Python: full source.
- JS/TS: full source + tree-sitter parse tree.

**Algorithm — Python (radon):**
```python
from radon.raw import analyze
raw = analyze(source)
# raw.loc       = total physical lines
# raw.sloc      = source lines (non-blank, non-comment)
# raw.lloc      = logical lines (radon's count of statements)
# raw.comments  = comment lines
# raw.blank     = blank lines
```

scout maps: `physical_loc = raw.loc`, `sloc = raw.sloc`, `logical_loc = raw.lloc`.

**Algorithm — JS/TS:**
```python
analysis = lizard.analyze_source_code(filename, source)
physical_loc = source.count("\n") + (0 if source.endswith("\n") else 1)
sloc = analysis.nloc   # lizard's "non-blank non-comment line count"

# Logical LOC: count tree-sitter `statement`-class nodes
logical_loc = sum(1 for node in walk(tree) if is_statement(node))
```

Where `is_statement(node)` returns True for tree-sitter node kinds in the statement family:
`expression_statement`, `variable_declaration`, `lexical_declaration`,
`return_statement`, `throw_statement`, `if_statement`, `for_statement`,
`for_in_statement`, `for_of_statement`, `while_statement`, `do_statement`,
`switch_statement`, `try_statement`, `break_statement`, `continue_statement`,
`labeled_statement`, `import_statement`, `export_statement`,
`function_declaration`, `class_declaration`. (TS-only: `interface_declaration`, `type_alias_declaration` are NOT counted as logical LOC — they're type-only.)

**Outputs:** Emit three `MetricValue`s per file (`loc.physical`, `loc.sloc`, `loc.logical`) plus a repo-level aggregate computed by the aggregator (sum across files).

**Thresholds:** Soft warning at `sloc > 500` for a single file (configurable via `--threshold loc=N`).

**Edge cases:**
- Mixed line endings (`\r\n`, `\n`): normalized to `\n` before counting; final-line-without-newline counts as one line.
- Generated files (heuristic: first 5 lines contain `// Code generated by`, `# Generated by`, `/* eslint-disable */`, or matches user `--exclude` glob): excluded by discovery, never reach this metric.
- Files of only comments: `sloc = 0`, `physical_loc > 0`. Reported as-is.

### 6.6 Duplication (`duplication`)

**Library:** None suitable in the Python ecosystem (`pylint`'s similarity checker is Python-only; `jscpd` is Node-only). In-house Rabin–Karp implementation.

**Scope:** Repo-level (`RepoMetric`).

**Inputs:** `ParsedFile.tokens` for every parsed file (already normalized to scout's `Token` type by the parser).

**Algorithm (Rabin–Karp rolling hash over normalized token stream):**

```python
def compute(files: list[ParsedFile], cfg) -> list[MetricValue]:
    window = cfg.duplication_min_tokens          # default 50
    base, mod = 1_000_003, (1 << 61) - 1

    # 1. Normalize each file's token stream into a hashable sequence.
    streams = {f.path: normalize(f.tokens) for f in files}

    # 2. Rolling hash: for each file, hash each window of length `window`.
    hashes = defaultdict(list)
    for path, stream in streams.items():
        for h, idx in rolling_hash(stream, window, base, mod):
            hashes[h].append((path, idx))

    # 3. Collect collisions; verify token-by-token (avoid hash false positives);
    #    greedily extend each match in both directions while tokens still match.
    matches = []
    for h, locs in hashes.items():
        if len(locs) < 2:
            continue
        for (a, ai), (b, bi) in pairs(locs):
            if streams[a][ai:ai+window] == streams[b][bi:bi+window]:
                matches.append(extend_match(streams[a], ai, streams[b], bi, window))

    # 4. Deduplicate overlapping matches (keep longest, drop subsumed).
    matches = dedupe_overlapping(matches)

    # 5. duplicated_lines = unique line spans across files covered by matches.
    dup_lines = unique_lines_covered(matches, files)
    total_lines = sum(f.sloc for f in files)
    pct = (dup_lines / total_lines) * 100 if total_lines else 0.0
    return [MetricValue(metric_id="duplication", scope="repo", value=pct, ...)]
```

**Normalization rules (`normalize`):**

| Token kind | Treatment |
|---|---|
| `keyword` | Kept verbatim (`if` matches `if`, never `while`). |
| `op`, `punct` | Kept verbatim. |
| `identifier` | Replaced with sentinel `<ID>`. This is what lets `def add(a, b)` match `def somme(x, y)`. |
| `number` | Kept verbatim. Two functions differing only in numeric constants are NOT duplicates. |
| `string`, `regex` | Kept verbatim. Same reasoning. |
| `comment` | Excluded (already not in `tokens`). |

**Configuration:**
- `duplication_min_tokens` (default 50, ~5 lines): minimum window size to consider.
- `--threshold duplication=N`: percentage above which to flag.

**Edge cases:**
- Generated code: excluded upstream by discovery.
- Test fixtures often duplicate legitimately; users can `--exclude tests/**` if desired (not default).
- Files with `len(tokens) < window`: skipped from hashing; still contribute to denominator (`sloc`).
- Identical files: treated as one large match; reported once.
- Cross-language duplication: hashes are computed per-language so a Python function and a TS function with the same shape don't falsely match. Two TS files with identical content do match.

**Thresholds:** Sonar-aligned defaults — green <3%, yellow 3–5%, red >5%.

### 6.7 Coupling Between Objects (`cbo`)

**Library:** None. In-house implementation against stdlib `ast` (Python) and tree-sitter (JS/TS).

**Inputs:** `ClassUnit.imported_class_refs`, populated by the parser per the rules below.

**Algorithm:**
```python
def compute(parsed, cfg) -> list[MetricValue]:
    return [
        MetricValue(
            metric_id="cbo",
            file=str(parsed.path),
            scope="class",
            symbol=c.qualified_name,
            line=c.location.line_start,
            value=float(len(c.imported_class_refs)),
            threshold=cfg.thresholds.get("cbo"),
            severity=severity_band(len(c.imported_class_refs), [5, 14]),
        )
        for c in parsed.classes
    ]
```

**Parser rules for building `imported_class_refs`:**

1. Build the file's import map `imports: dict[str, str]` (see §5.2 / §5.3).
2. For each class:
   - Walk the class body, collect every `Name` (Python) / `identifier` (JS/TS) that is read (not assigned-to as a fresh name).
   - Filter to names present as keys in `imports`.
   - Filter out names in the **language primitive/stdlib type allowlist** (these don't count as coupling).
   - Filter out the class's own name (self-reference is not coupling).
3. The result is the `imported_class_refs` frozenset.

**Primitive/stdlib type allowlist (excluded from CBO):**

| Language | Names |
|---|---|
| Python | `int, float, complex, bool, str, bytes, bytearray, memoryview, list, tuple, set, frozenset, dict, range, slice, None, NoneType, Ellipsis, NotImplemented, object, type, Any, Optional, Union, Tuple, List, Dict, Set, Callable, Iterator, Iterable, Sequence, Mapping, ClassVar, Final, Literal, TypeVar, Generic, Protocol` (typing module names) |
| JavaScript | `Array, Object, String, Number, Boolean, Symbol, BigInt, Date, RegExp, Error, TypeError, RangeError, SyntaxError, Promise, Map, Set, WeakMap, WeakSet, Proxy, Reflect, JSON, Math, console, undefined, null, NaN, Infinity` |
| TypeScript | All JS names plus: `any, unknown, never, void, string, number, boolean, bigint, symbol, object, Record, Partial, Required, Readonly, Pick, Omit, Exclude, Extract, NonNullable, Parameters, ReturnType, InstanceType, ThisType, Awaited, Promise` |

Note: scout counts imported names regardless of whether they're classes or functions, because we cannot reliably distinguish without type resolution. The metric remains called CBO for industry recognition; the semantic is "imported external identifiers referenced from the class body."

**Edge cases:**
- Python `from foo import *`: cannot resolve names statically. Imports from star-imports do NOT count toward CBO (under-counts; conservative).
- TS class extending another class from an import: the parent class counts toward CBO.
- TS class implementing interfaces: in v0.1, implemented interfaces DO count toward CBO (documented open decision §17).
- Anonymous classes (`const X = class {...}`): emit with `symbol="<anonymous>:LINE"`.
- Classes that use no imports: CBO = 0 (emitted).
- Inner classes: each is a separate `ClassUnit`; the outer class's CBO does not include the inner's references.

**Thresholds:** Default bands ≤5 low, 6–14 moderate, ≥15 high. CLI `--threshold cbo=N` forces WARN above N.

### 6.8 Lack of Cohesion of Methods (`lcom`) — LCOM4 variant

**Library:** None. In-house implementation against stdlib `ast` (Python) and tree-sitter (JS/TS).

**Inputs:** `ClassUnit.methods` (each carrying `referenced_fields` and `called_methods`), `ClassUnit.fields`.

**Parser rules for `MethodInfo.referenced_fields` and `MethodInfo.called_methods`:**

| Language | `referenced_fields` includes | `called_methods` includes |
|---|---|---|
| Python | `self.NAME` attribute reads/writes; also `cls.NAME` in `@classmethod`s | `self.METHOD()` calls; also `cls.METHOD()` in `@classmethod`s |
| JS/TS | `this.NAME` reads/writes (incl. shorthand property) | `this.METHOD()` calls |

Properties (`@property` in Python; `get`/`set` in JS/TS) are treated as methods.
Static methods participate in the graph but only contribute edges through their own `self`/`this` references (typically none).

**Algorithm (LCOM4):**
```python
def compute(parsed, cfg) -> list[MetricValue]:
    out = []
    for c in parsed.classes:
        methods = list(c.methods)
        n = len(methods)
        if n == 0:
            continue                              # do not emit for empty classes
        if n == 1:
            out.append(_value(c, 1))
            continue

        # Build undirected graph; edge iff methods share a field reference
        # OR one method calls the other (by name match within the class).
        uf = UnionFind(range(n))
        name_to_idx = {m.name: i for i, m in enumerate(methods)}
        for i in range(n):
            for j in range(i + 1, n):
                shared_field = methods[i].referenced_fields & methods[j].referenced_fields
                calls = (methods[j].name in methods[i].called_methods
                         or methods[i].name in methods[j].called_methods)
                if shared_field or calls:
                    uf.union(i, j)
        components = len({uf.find(i) for i in range(n)})
        out.append(_value(c, components))
    return out

def _value(c: ClassUnit, components: int) -> MetricValue:
    return MetricValue(
        metric_id="lcom",
        scope="class",
        symbol=c.qualified_name,
        line=c.location.line_start,
        value=float(components),
        severity=severity_band(components, [1, 3]),  # 1 ok, 2-3 warn, >=4 error
    )
```

**Reference:** Hitz & Montazeri, *Measuring Coupling and Cohesion in Object-Oriented Systems*, 1995. We pick LCOM4 over the original Chidamber & Kemerer LCOM (1991) because the original can produce 0 for almost any class with shared field access, making it useless on real codebases. LCOM4 has clean connected-component semantics: a class with LCOM = N is "N classes wearing a trenchcoat."

**Edge cases:**
- Class with 0 methods: not emitted (degenerate).
- Class with 1 method: LCOM = 1.
- Utility classes with only static methods that don't share state: legitimately high LCOM; documented as expected behavior.
- Dunder/lifecycle methods (`__init__`, `constructor`): participate in the graph normally. `__init__`/`constructor` typically writes most fields, so it tends to anchor the largest component.
- Private methods (Python `_foo`, JS `#foo`): treated identically to public methods.
- Inherited methods (not defined in this class): not in `c.methods`, so they don't participate. v0.1 does not resolve inheritance for LCOM.
- Method-call resolution is textual: `self.bar()` matches a method named `bar` in the same class. Dynamic dispatch (`getattr(self, name)()` in Python, `this[name]()` in JS) is invisible — under-connects the graph; documented limitation.

**Thresholds:** Default bands — 1 cohesive (OK), 2–3 borderline (WARN), ≥4 refactor candidate (ERROR). CLI `--threshold lcom=N`.

---

## 7. File Discovery Pipeline

### 7.1 Order of operations

```
1. Resolve project root (absolute path).
2. If --respect-gitignore (default), load .gitignore + .git/info/exclude via pathspec.
3. Apply built-in excludes: node_modules/, .venv/, venv/, __pycache__/, .git/, dist/, build/, .next/, .nuxt/, coverage/, *.min.js, *.map.
4. Apply user --exclude globs (additive to built-ins).
5. Walk file tree (os.scandir, depth-first).
6. Per file: classify by extension. Skip if not in the active language set.
7. If --include globs were provided, keep only matches.
8. Yield SourceFile(path, language, size_bytes).
```

### 7.2 SourceFile type

```python
@dataclass(slots=True, frozen=True)
class SourceFile:
    abs_path: Path
    rel_path: Path        # relative to project root
    language: Language
    size_bytes: int
```

### 7.3 Active language set

If `--language auto` (default): start empty; add Python if any `.py` files encountered, add JavaScript on `.js`/`.jsx`/`.mjs`/`.cjs`, add TypeScript on `.ts`/`.tsx`/`.mts`/`.cts`. Discovery makes a first pass to determine the language set, then a second pass to enumerate.

(Alternative: collect everything in one pass and let metric layer skip empty languages. The two-pass approach is chosen for predictable progress reporting.)

### 7.4 File size cap

Default: skip files larger than 1 MiB with a warning. Configurable via `--max-file-bytes`. Rationale: machine-generated files (minified bundles, vendored payloads) blow up parser memory.

---

## 8. Concurrency Model

### 8.1 Worker pool

- One `ProcessPoolExecutor(max_workers=cfg.jobs or os.cpu_count())`.
- Each worker is initialized via an `initializer` function that:
  - Loads tree-sitter grammars once per process.
  - Imports metric modules once per process.
- Workers receive `SourceFile`, return `(ParsedFile, list[MetricValue])` for `FileMetric`s.
- The main process collects results via `executor.map` with `chunksize=8` (tunable).

### 8.2 Cross-file phase

After per-file results return, the main process:
1. Aggregates per-file `MetricValue`s into a `RunReport`.
2. Runs `RepoMetric`s (currently just `duplication`) on the collected `ParsedFile`s.
3. Computes repo-level aggregates (sum SLOC, average MI, etc.).
4. Applies threshold evaluation: marks `MetricValue.severity` per `cfg.thresholds`.

### 8.3 Memory bound

`ParsedFile.tokens` is kept in memory through the duplication phase. For very large repos this is the dominant memory cost. Mitigation: tokens are stored as `Token(kind: str, value: str, line: int)` with `slots=True`; identifiers are deduplicated via `sys.intern`. Empirical target: ≤500 MB resident for a 200k-SLOC repo.

### 8.4 Determinism

Output ordering must be deterministic for diff-able CI artifacts:
- Files sorted by `rel_path`.
- `MetricValue`s within a file sorted by `(metric_id, line, symbol)`.
- `violations` list sorted by `(severity desc, metric_id, file, line)`.

---

## 9. Configuration System

### 9.1 Config dataclass

```python
@dataclass(slots=True)
class ScoutConfig:
    root: Path
    language: Language | Literal["auto"]
    metrics: tuple[str, ...]                  # metric IDs to run
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    respect_gitignore: bool
    max_file_bytes: int
    jobs: int
    thresholds: dict[str, float]              # {"cc": 15, "cognitive": 15, ...}
    output_format: Literal["text", "json"]
    output_path: Path | None
    quiet: bool
    no_color: bool
    strict: bool                              # parse errors → non-zero exit
    duplication_min_tokens: int

@dataclass(slots=True)
class MetricConfig:
    """Slice of ScoutConfig passed to metric workers."""
    thresholds: dict[str, float]
    duplication_min_tokens: int
```

### 9.2 Precedence

```
defaults < pyproject.toml [tool.scout] < scout.toml < CLI flags
```

The loader merges in that order. CLI flags wins. `scout.toml` wins over `pyproject.toml` when both exist (with a warning).

### 9.3 Defaults

```toml
language = "auto"
metrics = ["cc", "cognitive", "loc", "duplication", "mi"]   # not cbo/lcom
respect_gitignore = true
max_file_bytes = 1_048_576
jobs = 0                  # 0 means os.cpu_count()
output_format = "text"
strict = false
duplication_min_tokens = 50

[thresholds]
cc = 15
cognitive = 15
duplication = 5.0
mi = 20
loc = 500
cbo = 15
lcom = 4
```

### 9.4 Validation

After merging, the config is validated:
- `metrics` ⊆ registered metric IDs (else `ConfigError`).
- `language` ∈ {"auto", "python", "javascript", "typescript"} or a list of those.
- `thresholds` keys ⊆ metric IDs.
- `jobs ≥ 0`.

Validation errors exit with code 2 and a message naming the offending field.

---

## 10. CLI Layer

### 10.1 Framework: Typer

```python
# cli.py
import typer
from pathlib import Path
from typing import Optional, List

app = typer.Typer(add_completion=False, no_args_is_help=False)

@app.command()
def main(
    path: Path = typer.Argument(Path("."), exists=True, file_okay=False, resolve_path=True),
    language: str = typer.Option("auto", "--language", "-l"),
    metrics: Optional[str] = typer.Option(None, "--metrics", "-m"),
    fmt: str = typer.Option("text", "--format", "-f"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    threshold: List[str] = typer.Option([], "--threshold"),
    include: List[str] = typer.Option([], "--include"),
    exclude: List[str] = typer.Option([], "--exclude"),
    respect_gitignore: bool = typer.Option(True, "--respect-gitignore/--no-respect-gitignore"),
    config_path: Optional[Path] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
    no_color: bool = typer.Option(False, "--no-color"),
    jobs: int = typer.Option(0, "--jobs", "-j"),
    version: bool = typer.Option(False, "--version"),
):
    ...
```

### 10.2 Dispatch

```
1. If --version: print version, exit 0.
2. Load config via ScoutConfig.load(path, cli_overrides, config_path).
3. Discover files (Discovery.scan(config)).
4. Run (Runner.run(config, files)) -> RunReport.
5. Output (output.format(report, cfg.output_format, cfg.output_path)).
6. Determine exit code from RunReport.violations and strict mode.
```

### 10.3 `--threshold` parsing

`--threshold` accepts `METRIC=VALUE`. Multiple instances allowed. Invalid format → exit 2.

```python
def parse_thresholds(items: list[str]) -> dict[str, float]:
    result = {}
    for it in items:
        if "=" not in it: raise ConfigError(f"bad --threshold {it!r}")
        k, v = it.split("=", 1)
        result[k.strip()] = float(v)
    return result
```

### 10.4 Help text style

- One-line description per option (Typer auto-formats).
- Example invocations under `--help` examples section.
- Group related options in the help via Typer's `rich_help_panel`.

---

## 11. Output Formats

### 11.1 Text (default)

Renderer: `rich`. Layout:

```
scout v{version} — scanned {N} files in {duration}s

Summary
  Files:         {files}
  Total SLOC:    {sloc}
  Duplication:   {pct:.1f}%   {check}
  Avg MI:        {mi:.0f}     {check}

{per-metric section, only if there are violations or warnings:}
{Metric name} ({comparator})
  {file}:{line}  {symbol}    {value}  {icon}
  ...

Exit code: {n} ({m} threshold violations)
```

Color rules:
- Severity OK: green.
- WARN: yellow.
- ERROR: red.
- INFO: cyan.

If stdout is not a TTY or `--no-color`, ANSI codes are stripped.

### 11.2 JSON

Single document, written to stdout (or `--output PATH`). The shape is documented inline below; no separate schema file ships in v0.1 (per §2.0 — no premature abstraction).

```json
{
  "version": "string (semver of scout)",
  "scanned_at": "ISO-8601 UTC",
  "duration_ms": "integer",
  "summary": {
    "files": "integer",
    "sloc": "integer",
    "physical_loc": "integer",
    "logical_loc": "integer",
    "duplication_pct": "number",
    "avg_mi": "number"
  },
  "files": [
    {
      "path": "string (rel)",
      "language": "python|javascript|typescript",
      "physical_loc": "integer",
      "sloc": "integer",
      "logical_loc": "integer",
      "metrics": [ /* MetricValue */ ],
      "errors": [ /* ParseError */ ]
    }
  ],
  "repo_metrics": [ /* MetricValue */ ],
  "violations": [ /* MetricValue with severity != ok */ ]
}
```

If the schema needs to break in a future minor version, we bump the package version and document the change in the changelog. No `schema_version` field; a consumer that needs to detect changes can pin a scout version.

> Per §2.0, only `text` and `json` are supported. SARIF, JUnit XML, HTML, CSV, GitLab Code Quality, and any other CI-integration formats are explicitly **out of scope** and will not be added in v0.x. Users that need those formats can transform the JSON output downstream.

---

## 12. Error Handling

### 12.1 Exception hierarchy

```python
# errors.py
class ScoutError(Exception): ...
class ConfigError(ScoutError): ...           # bad CLI flag, bad config file
class IOError(ScoutError): ...               # cannot read/write files
class DiscoveryError(ScoutError): ...        # cannot resolve project root
# Per-file parse failures are NOT exceptions; they become ParseError records.
```

### 12.2 Exit code mapping

| Exit | Cause |
|---|---|
| 0 | Success, no threshold violations |
| 1 | Success, threshold violations |
| 2 | `ConfigError` |
| 3 | `IOError`, `DiscoveryError` |
| 4 | One or more parse errors AND `--strict` |
| 130 | KeyboardInterrupt |

### 12.3 Logging

Use the `logging` module with two loggers: `scout` (default INFO) and `scout.parser` (default WARNING). `--quiet` raises both to ERROR. Log target is stderr; stdout is reserved for the report unless `--output` is set.

---

## 13. Performance Targets and Budget

Reference machine: 8-core CPU, NVMe SSD, Python 3.12.

| Repo size | Target wall time | Memory |
|---|---|---|
| 10k SLOC | < 2 s | < 200 MB |
| 100k SLOC | < 15 s | < 500 MB |
| 500k SLOC | < 60 s | < 2 GB |

If we miss these on representative repos (cpython, react, vscode subset), we profile before adding features. Profiling target: `py-spy` flame graphs in CI.

---

## 14. Testing Strategy

### 14.1 Layers

- **Unit tests** per metric module using hand-crafted `ParsedFile` fixtures. Each metric has at least 3 fixtures: trivial, threshold-edge, threshold-exceeding.
- **Parser tests**: small source files in each language, expected `ParsedFile` snapshot.
- **Integration tests**: a few real-world fixture repos under `tests/fixtures/repos/`. Golden-file outputs in JSON and text.
- **Property tests** (where reasonable): for CC, `cc(empty_function) == 1`; for LCOM, `lcom(single_method_class) == 1`.

### 14.2 Coverage target

- Lines: ≥ 85% on `src/scout/` (excluding `cli.py` glue).
- Branches: enforced on `metrics/` (≥ 90%) because metric algorithms are the value proposition.

### 14.3 Snapshot strategy

Golden JSON outputs are stored under `tests/fixtures/golden/`. CI fails on diff. Updating a golden file requires `--update-snapshots` and shows up in PR review.

### 14.4 Cross-version

Test matrix: Python 3.10, 3.11, 3.12, 3.13. tree-sitter wheels availability per Python version is the gating constraint.

---

## 15. Dependencies and Versions

Pinned in `pyproject.toml`:

```toml
[project]
requires-python = ">=3.10"
dependencies = [
    # CLI framework + presentation
    "typer>=0.12,<1.0",
    "rich>=13.7,<14.0",

    # Python metric libraries (used by parsers/python_parser.py)
    "radon>=6.0,<7.0",                  # CC, MI, Halstead, raw LOC
    "cognitive_complexity>=1.3,<2.0",   # Cognitive Complexity (Python)

    # Multi-language metric library (used by parsers/{js,ts}_parser.py)
    "lizard>=1.17,<2.0",                # CC, NLOC for JS/TS

    # JS/TS parsing for in-house metrics (Cognitive, Halstead, MI, CBO, LCOM, dup)
    "tree-sitter>=0.21,<0.22",
    "tree-sitter-python>=0.21,<0.22",
    "tree-sitter-javascript>=0.21,<0.22",
    "tree-sitter-typescript>=0.21,<0.22",

    # Utilities
    "pathspec>=0.12,<1.0",
    "tomli>=2.0,<3.0; python_version<'3.11'",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.1",
    "pytest-xdist>=3.5",
    "mypy>=1.10",
    "ruff>=0.5",
    "py-spy>=0.3",
]
```

| Dependency | Why |
|---|---|
| `typer` | Type-hint-driven CLI; built on Click, modern API. |
| `rich` | Terminal formatting, color, tables. |
| `radon` | Canonical Python implementation of CC, MI, Halstead, and raw LOC. Used by Pylama, Wily, and countless internal tools. Stable since 2014. |
| `cognitive_complexity` | Small focused PyPI package implementing Sonar's Cognitive Complexity spec for Python AST. |
| `lizard` | The de facto multi-language CC and NLOC tool in Python. Used by `code-climate` plugins and many CI integrations. |
| `tree-sitter` + grammars | Robust JS/TS parsing for our in-house metrics. Used by GitHub, Atom, and Neovim. |
| `pathspec` | `.gitignore`-compatible glob matching. |
| `tomli` | TOML parsing on Python 3.10 (stdlib `tomllib` on 3.11+). |
| `pytest` family | Testing. |
| `mypy`, `ruff` | Type and lint enforcement. |

We do *not* depend on:
- `astroid` — too heavyweight; stdlib `ast` is sufficient for our CBO/LCOM walks.
- `pylint` — we don't run style rules.
- Node-based tools (`jscpd`, `escomplex`, ESLint plugins) — would require Node in our install path. Rejected per §2.2.

---

## 16. Build, Packaging, Release

### 16.1 Build

- Backend: `hatchling`.
- Wheel + sdist published to PyPI.
- Package name: `scout-metrics`. CLI entrypoint:

```toml
[project.scripts]
scout = "scout.cli:app"
```

### 16.2 Version source

Single source of truth: `src/scout/__init__.py::__version__`. Read via `hatch-vcs` from git tags.

### 16.3 CI

- GitHub Actions: lint (ruff), typecheck (mypy), test matrix (Python × OS).
- Release workflow on tag `v*.*.*`: build wheels for Linux/macOS/Windows, publish to PyPI with trusted publishing.

### 16.4 Versioning

SemVer. v0.x is pre-stable; minor versions may break the JSON schema. Consumers that need stability pin a scout version range.

---

## 17. Open Decisions

Things explicitly *not* decided in this spec; mark these in tickets before v0.1 ships.

1. **Anonymous function handling for CBO/LCOM.** Should arrow functions inside class bodies count as methods? Probably no (they're closures, not methods). Confirm with a fixture.
2. **TypeScript decorators and CC.** Decorators are expressions; do they count toward function CC? Sonar excludes them; we follow Sonar by default but document.
3. **Match statements (Python 3.10+) and cognitive complexity.** Sonar's spec was written before match; we treat each `case` as `+1 + nesting`. Validate against community expectations.
4. **JSX expressions and Halstead.** Should JSX expression containers count as operators? v0.1 says yes (they're real syntactic operators). Revisit if false positives spike.
5. **CBO inheritance counting in TS interfaces.** A class implementing 3 interfaces — does each interface count toward CBO? v0.1 says yes for classes; interfaces themselves are not scored.
6. **Re-export resolution.** Should `import { Foo } from "./re-export"` resolve through the re-export to find the original symbol for CBO? v0.1: no (shallow, textual). v0.2 might revisit if users complain.

---

## 18. Out of Scope for v0.1 (explicit)

These are deliberately excluded per the simplicity constraint in §2.0. They are not on the roadmap unless and until a concrete user need overrides the constraint.

- **Output formats other than `text` and `json`** — no SARIF, no JUnit XML, no HTML, no CSV, no GitLab Code Quality JSON. Users with a need for another format pipe the JSON through their own tool.
- Incremental analysis (changed-files only).
- Baseline / diff mode.
- Plugin API.
- Watch mode.
- Result caching across runs.
- Cross-file call-graph (would enable recursion penalty in Cognitive Complexity, deeper CBO).
- Other target languages (Go, Java, C#, Ruby).
- A web dashboard, daemon, or persistent server.
- Source-comment suppression directives (`# scout: ignore`, `// scout-disable-next-line`).
- Severity overrides per file or per directory beyond a single `[thresholds]` table.

---

## 19. Glossary

- **AST** — Abstract Syntax Tree. Tree representation of source code structure.
- **SLOC** — Source Lines of Code. Non-blank, non-comment lines.
- **CC** — Cyclomatic Complexity. McCabe's count of branching paths.
- **Cognitive Complexity** — Sonar's readability-oriented per-function score.
- **Halstead Volume/Difficulty/Effort** — Token-count-derived complexity scores.
- **MI** — Maintainability Index. Composite 0–100 score.
- **CBO** — Coupling Between Objects. Per-class count of external class references.
- **LCOM** — Lack of Cohesion of Methods. Per-class graph-component count; we use the LCOM4 variant.
- **Rabin–Karp** — Rolling-hash string-matching algorithm. Used for duplication detection over normalized token streams.
- **`ParsedFile`** — scout's internal uniform AST representation; parser layer output; metric layer input.
