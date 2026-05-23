# scout

A Python CLI for static code-quality metrics on Python, JavaScript, and TypeScript codebases. See [Available metrics](#available-metrics) for the full list.

## Available metrics

| ID | Metric | What it measures | Scope |
|----|--------|-----------------|-------|
| `cc` | Cyclomatic Complexity | Counts decision branches (if / for / and / or) in a function. More branches = harder to test. | function |
| `cognitive` | Cognitive Complexity | Like CC, but penalises deep nesting more heavily. Closer to how hard humans find code to read. | function |
| `halstead` | Halstead | Counts unique operators and operands to estimate the mental effort needed to read a file. | file |
| `mi` | Maintainability Index | A 0–100 score combining size, complexity, and Halstead. **Higher is better** (≥20 = healthy). | file |
| `loc` | Lines of Code | Counts total lines, blank lines, comments, and real source lines (SLOC) per file. | file |
| `duplication` | Duplication | Finds copy-pasted code chunks that appear in more than one file across the project. | repo |
| `cbo` | Coupling Between Objects | Counts how many other classes a class depends on. More dependencies = more tangled. | class |
| `lcom` | Lack of Cohesion of Methods | Measures whether a class's methods share data; high values mean unrelated code crammed together. | class |

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

Pass any combination of [metric IDs](#available-metrics) to `--metrics`.

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
