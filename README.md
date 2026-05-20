# scout

A Python CLI tool for computing static code-quality metrics — Cyclomatic Complexity, Cognitive Complexity, Halstead, Maintainability Index, LOC, Duplication, CBO, LCOM — for Python, JavaScript, and TypeScript codebases.

## Installation

### As a tool

```bash
pip install scout-metrics
# or
uv tool install scout-metrics
```

### For development

```bash
git clone https://github.com/francamacdowell/scout-metrics.git
cd scout-metrics
uv sync --extra dev
```

## Usage

### Scan the current directory

```bash
scout
```

### Scan a specific path

```bash
scout ./src
```

### Output as JSON (e.g. for CI)

```bash
scout ./src --format json --output report.json
```

### Run only selected metrics

```bash
scout --metrics cc,cognitive,loc
```

### Tighten a threshold for CI gating

```bash
# Fail if any function has cyclomatic complexity > 10
scout --threshold cc=10 --threshold mi=25
```

### Scan only TypeScript files

```bash
scout --language typescript ./src
```

### Include or exclude paths

```bash
scout --exclude "tests/**" --exclude "*.min.js"
scout --include "src/**/*.ts"
```

### Ignore .gitignore rules

```bash
scout --no-respect-gitignore
```

### Use a custom config file

```bash
scout --config ./config/scout.toml
```

### Suppress warnings and strip color (useful in CI logs)

```bash
scout --quiet --no-color
```

### Control parallelism

```bash
scout --jobs 4   # use 4 worker processes
scout --jobs 0   # default: one worker per CPU core
```

### Treat parse errors as fatal

```bash
scout --strict   # exits with code 4 if any file fails to parse
```

## Configuration

Settings can be placed in `pyproject.toml` under `[tool.scout]` or in a `scout.toml` file at the project root. CLI flags override file config.

```toml
# pyproject.toml
[tool.scout]
metrics = ["cc", "cognitive", "loc", "mi"]
exclude = ["tests/fixtures"]

[tool.scout.thresholds]
cc = 10.0
mi = 25.0
loc = 300.0
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | No violations |
| 1 | Threshold violations detected |
| 2 | Configuration error |
| 3 | File I/O or discovery error |
| 4 | Parse errors (only with `--strict`) |

## Development

```bash
make check   # lint + typecheck + tests
make test    # tests only
make demo    # run scout against itself
```
