# Package name: `scout-metrics` on PyPI, `scout` for module and CLI

The PyPI name `scout` was taken (2014), so the distribution is published as **`scout-metrics`**. The importable module and the CLI command both remain **`scout`** — that's what users type and write in code 100× a day. The three names are wired up in `pyproject.toml`:

```toml
[project]
name = "scout-metrics"

[project.scripts]
scout = "scout.cli:app"
```

Considered renaming everything to `scout_metrics` for internal consistency, or picking a fresh distribution name like `scoutpy`/`scout-cli`. Rejected: the short CLI name is the higher-traffic surface; the distribution name only shows up in install commands and `pyproject.toml`. Renaming after publication is expensive (discoverability loss, every install snippet on the internet breaks), so this needs to be a deliberate up-front decision.
