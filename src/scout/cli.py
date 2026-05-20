from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import typer

from scout.errors import (
    EXIT_CONFIG_ERROR,
    EXIT_INTERRUPT,
    EXIT_IO_ERROR,
    EXIT_OK,
    EXIT_PARSE_ERROR,
    EXIT_VIOLATIONS,
    ConfigError,
    DiscoveryError,
    ScoutIOError,
)

app = typer.Typer(add_completion=False, no_args_is_help=False)


@app.command()
def main(
    path: Path = typer.Argument(Path("."), help="Project root to scan."),
    language: str = typer.Option(
        "auto", "--language", "-l", help="Language filter (auto|python|javascript|typescript)."
    ),
    metrics: str | None = typer.Option(
        None, "--metrics", "-m", help="Comma-separated metric IDs to run."
    ),
    fmt: str = typer.Option("text", "--format", "-f", help="Output format (text|json)."),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write report to file instead of stdout."
    ),
    threshold: list[str] = typer.Option(
        [], "--threshold", help="Threshold override, e.g. cc=15 (repeatable)."
    ),
    include: list[str] = typer.Option([], "--include", help="Include glob patterns (additive)."),
    exclude: list[str] = typer.Option(
        [], "--exclude", help="Exclude glob patterns (additive to built-ins)."
    ),
    respect_gitignore: bool = typer.Option(True, "--respect-gitignore/--no-respect-gitignore"),
    config_path: Path | None = typer.Option(None, "--config", help="Explicit config file path."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress warnings."),
    no_color: bool = typer.Option(False, "--no-color", help="Strip ANSI color codes."),
    jobs: int = typer.Option(0, "--jobs", "-j", help="Worker processes (0 = cpu_count)."),
    strict: bool = typer.Option(False, "--strict", help="Parse errors → exit 4."),
    version: bool = typer.Option(False, "--version", is_eager=True, help="Print version and exit."),
) -> None:
    if version:
        from scout import __version__

        typer.echo(__version__)
        raise typer.Exit(0)

    _setup_logging(quiet)

    try:
        from scout.config import ScoutConfig

        thresholds = _parse_thresholds(threshold)
        metrics_tuple = tuple(m.strip() for m in metrics.split(",")) if metrics else None

        cli_overrides: dict[str, object] = {
            "language": language,
            "output_format": fmt,
            "output_path": str(output) if output else None,
            "respect_gitignore": respect_gitignore,
            "quiet": quiet,
            "no_color": no_color,
            "jobs": jobs,
            "strict": strict,
        }
        if thresholds:
            cli_overrides["thresholds"] = thresholds
        if metrics_tuple:
            cli_overrides["metrics"] = list(metrics_tuple)
        if include:
            cli_overrides["include"] = include
        if exclude:
            cli_overrides["exclude"] = exclude

        root = path.resolve()
        cfg = ScoutConfig.load(root, cli_overrides, config_path)

    except ConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR) from None

    try:
        from scout.aggregator import aggregate
        from scout.discovery import scan
        from scout.output import write as write_report
        from scout.runner import run

        source_files = scan(cfg)
        if not source_files:
            typer.echo("No source files found.", err=True)
            raise typer.Exit(EXIT_OK)

        t0 = time.monotonic()
        worker_results = run(cfg, source_files)
        duration_ms = int((time.monotonic() - t0) * 1000)

        report = aggregate(cfg, source_files, worker_results, duration_ms)
        write_report(report, cfg.output_format, cfg.output_path, no_color=cfg.no_color)

    except (ScoutIOError, DiscoveryError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(EXIT_IO_ERROR) from None
    except KeyboardInterrupt:
        raise typer.Exit(EXIT_INTERRUPT) from None

    # Exit-code determination
    has_parse_errors = any(fr.errors for fr in report.files)
    if cfg.strict and has_parse_errors:
        raise typer.Exit(EXIT_PARSE_ERROR)
    if report.violations:
        raise typer.Exit(EXIT_VIOLATIONS)
    raise typer.Exit(EXIT_OK)


def _parse_thresholds(items: list[str]) -> dict[str, float]:
    result: dict[str, float] = {}
    for it in items:
        if "=" not in it:
            raise ConfigError(f"Invalid --threshold {it!r}; expected METRIC=VALUE")
        k, v = it.split("=", 1)
        try:
            result[k.strip()] = float(v.strip())
        except ValueError as exc:
            raise ConfigError(f"Invalid threshold value in {it!r}; expected a number") from exc
    return result


def _setup_logging(quiet: bool) -> None:
    level = logging.ERROR if quiet else logging.WARNING
    logging.basicConfig(
        level=level,
        format="scout: %(message)s",
        stream=sys.stderr,
        force=True,
    )
    logging.getLogger("scout").setLevel(level)
