# scout

A Python CLI tool for computing static code-quality metrics (Cyclomatic Complexity, Cognitive Complexity, Halstead, Maintainability Index, LOC, Duplication, CBO, LCOM) for Python, JavaScript, and TypeScript codebases.

## Installation

```bash
uv sync --extra dev
```

## Usage

```bash
scout [PATH] [OPTIONS]
```

## Development

```bash
make check   # lint + typecheck + tests
make test    # tests only
make demo    # run against current directory
```
