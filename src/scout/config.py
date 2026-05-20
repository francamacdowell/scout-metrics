from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from scout.errors import ConfigError

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

_VALID_METRIC_IDS = frozenset(
    {"cc", "cognitive", "halstead", "mi", "loc", "duplication", "cbo", "lcom"}
)
_VALID_LANGUAGES = frozenset({"auto", "python", "javascript", "typescript"})

_DEFAULTS: dict[str, object] = {
    "language": "auto",
    "metrics": ["cc", "cognitive", "loc", "duplication", "mi"],
    "include": [],
    "exclude": [],
    "respect_gitignore": True,
    "max_file_bytes": 1_048_576,
    "jobs": 0,
    "output_format": "text",
    "output_path": None,
    "quiet": False,
    "no_color": False,
    "strict": False,
    "duplication_min_tokens": 50,
    "thresholds": {
        "cc": 15.0,
        "cognitive": 15.0,
        "duplication": 5.0,
        "mi": 20.0,
        "loc": 500.0,
        "cbo": 15.0,
        "lcom": 4.0,
    },
}


@dataclass(slots=True)
class ScoutConfig:
    root: Path
    language: str  # "auto" | "python" | "javascript" | "typescript"
    metrics: tuple[str, ...]
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    respect_gitignore: bool
    max_file_bytes: int
    jobs: int
    thresholds: dict[str, float]
    output_format: Literal["text", "json"]
    output_path: Path | None
    quiet: bool
    no_color: bool
    strict: bool
    duplication_min_tokens: int

    @staticmethod
    def load(
        root: Path,
        cli_overrides: dict[str, object] | None = None,
        config_path: Path | None = None,
    ) -> ScoutConfig:
        merged = dict(_DEFAULTS)
        merged["thresholds"] = dict(_DEFAULTS["thresholds"])  # type: ignore[call-overload]

        # Load from pyproject.toml [tool.scout]
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            try:
                data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
                tool_scout = data.get("tool", {}).get("scout", {})
                _merge_toml(merged, tool_scout)
            except Exception as e:
                raise ConfigError(f"Failed to read {pyproject}: {e}") from e

        # Load from scout.toml (wins over pyproject.toml if both exist)
        scout_toml = config_path or root / "scout.toml"
        if scout_toml.exists():
            if config_path is None and pyproject.exists():
                import logging

                logging.getLogger("scout").warning(
                    "Both scout.toml and pyproject.toml [tool.scout] found; scout.toml takes precedence."
                )
            try:
                data = tomllib.loads(scout_toml.read_text(encoding="utf-8"))
                _merge_toml(merged, data)
            except Exception as e:
                raise ConfigError(f"Failed to read {scout_toml}: {e}") from e

        # Apply CLI overrides
        if cli_overrides:
            for k, v in cli_overrides.items():
                if v is not None:
                    if k == "thresholds" and isinstance(v, dict):
                        merged["thresholds"].update(v)  # type: ignore[attr-defined]
                    else:
                        merged[k] = v

        cfg = ScoutConfig(
            root=root,
            language=str(merged["language"]),
            metrics=tuple(merged["metrics"]),  # type: ignore[arg-type]
            include=tuple(merged.get("include", [])),  # type: ignore[arg-type]
            exclude=tuple(merged.get("exclude", [])),  # type: ignore[arg-type]
            respect_gitignore=bool(merged["respect_gitignore"]),
            max_file_bytes=int(merged["max_file_bytes"]),  # type: ignore[call-overload]
            jobs=int(merged["jobs"]),  # type: ignore[call-overload]
            thresholds=dict(merged["thresholds"]),  # type: ignore[call-overload]
            output_format=str(merged["output_format"]),  # type: ignore[arg-type]
            output_path=Path(str(merged["output_path"])) if merged["output_path"] else None,
            quiet=bool(merged["quiet"]),
            no_color=bool(merged["no_color"]),
            strict=bool(merged["strict"]),
            duplication_min_tokens=int(merged["duplication_min_tokens"]),  # type: ignore[call-overload]
        )
        _validate(cfg)
        return cfg


def _merge_toml(base: dict[str, object], override: dict[str, object]) -> None:
    for k, v in override.items():
        if k == "thresholds" and isinstance(v, dict):
            base_thresholds = base.get("thresholds", {})
            if isinstance(base_thresholds, dict):
                base_thresholds.update(v)
                base["thresholds"] = base_thresholds
        else:
            base[k] = v


def _validate(cfg: ScoutConfig) -> None:
    if cfg.language not in _VALID_LANGUAGES:
        raise ConfigError(
            f"Invalid language {cfg.language!r}. Choose from: {sorted(_VALID_LANGUAGES)}"
        )
    unknown = set(cfg.metrics) - _VALID_METRIC_IDS
    if unknown:
        raise ConfigError(
            f"Unknown metric IDs: {sorted(unknown)}. Valid: {sorted(_VALID_METRIC_IDS)}"
        )
    unknown_thresh = set(cfg.thresholds) - _VALID_METRIC_IDS
    if unknown_thresh:
        raise ConfigError(f"Unknown threshold keys: {sorted(unknown_thresh)}")
    if cfg.jobs < 0:
        raise ConfigError(f"jobs must be >= 0, got {cfg.jobs}")
    if cfg.output_format not in ("text", "json"):
        raise ConfigError(f"output_format must be 'text' or 'json', got {cfg.output_format!r}")
    if cfg.duplication_min_tokens < 1:
        raise ConfigError(f"duplication_min_tokens must be >= 1, got {cfg.duplication_min_tokens}")
