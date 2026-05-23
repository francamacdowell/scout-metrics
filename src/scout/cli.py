from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

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

if TYPE_CHECKING:
    from scout.metrics.base import MetricValue

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

    show_progress = _should_show_progress(quiet)
    shared_console: Console | None = Console(file=sys.stderr, no_color=no_color) if show_progress else None
    _setup_logging(quiet, console=shared_console)

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

        # Phase 1: Discovering files
        if show_progress and shared_console is not None:
            with Progress(
                SpinnerColumn(),
                TextColumn("Discovering files"),
                console=shared_console,
                transient=True,
            ) as prog:
                prog.add_task("")
                source_files = scan(cfg)
        else:
            source_files = scan(cfg)

        if not source_files:
            typer.echo("No source files found.", err=True)
            raise typer.Exit(EXIT_OK)

        # Phase 2: Computing file metrics
        t0 = time.monotonic()
        if show_progress and shared_console is not None:
            with Progress(
                SpinnerColumn(),
                TextColumn("Computing file metrics"),
                BarColumn(),
                MofNCompleteColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=shared_console,
                transient=True,
            ) as prog:
                task = prog.add_task("", total=len(source_files))
                worker_results = run(
                    cfg,
                    source_files,
                    on_file_done=lambda _sf: prog.advance(task),
                )
        else:
            worker_results = run(cfg, source_files)
        duration_ms = int((time.monotonic() - t0) * 1000)

        # Phase 3: Computing duplication (hoisted from aggregator; conditional on metric selection)
        repo_metrics: list[MetricValue] = []
        if "duplication" in cfg.metrics:
            from scout.metrics.base import MetricConfig
            from scout.metrics.duplication import compute as dup_compute

            metric_cfg = MetricConfig(
                thresholds=cfg.thresholds,
                duplication_min_tokens=cfg.duplication_min_tokens,
            )
            parsed_files = [pf for _sf, pf, _vals in worker_results]
            if show_progress and shared_console is not None:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("Computing duplication"),
                    console=shared_console,
                    transient=True,
                ) as prog:
                    prog.add_task("")
                    repo_metrics = dup_compute(parsed_files, metric_cfg)
            else:
                repo_metrics = dup_compute(parsed_files, metric_cfg)

        report = aggregate(worker_results, duration_ms, repo_metrics)
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


def _should_show_progress(quiet: bool) -> bool:
    return sys.stderr.isatty() and not quiet


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


def _setup_logging(quiet: bool, console: Console | None = None) -> None:
    level = logging.ERROR if quiet else logging.WARNING
    scout_log = logging.getLogger("scout")
    scout_log.setLevel(level)
    scout_log.handlers.clear()
    if console is not None:
        handler = RichHandler(console=console, show_time=False, show_path=False, markup=False)
        handler.setLevel(level)
        scout_log.addHandler(handler)
        scout_log.propagate = False
    else:
        logging.basicConfig(
            level=level,
            format="scout: %(message)s",
            stream=sys.stderr,
            force=True,
        )
