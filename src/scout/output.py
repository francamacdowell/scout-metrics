from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from scout.metrics.base import FileReport, MetricValue, RunReport, Severity

_SEVERITY_COLOR = {
    Severity.OK: "green",
    Severity.INFO: "cyan",
    Severity.WARN: "yellow",
    Severity.ERROR: "red",
}
_SEVERITY_ICON = {
    Severity.OK: "✓",
    Severity.INFO: "i",
    Severity.WARN: "⚠",
    Severity.ERROR: "✗",
}


def write(report: RunReport, fmt: str, path: Path | None, no_color: bool = False) -> None:
    """Render the report and write to stdout or a file."""
    content = render_json(report) if fmt == "json" else render_text(report, no_color=no_color)

    if path is not None:
        path.write_text(content, encoding="utf-8")
    else:
        sys.stdout.write(content)
        if not content.endswith("\n"):
            sys.stdout.write("\n")


def render_json(report: RunReport) -> str:
    total_sloc = sum(f.sloc for f in report.files)
    total_physical = sum(f.physical_loc for f in report.files)
    total_logical = sum(f.logical_loc for f in report.files)
    dup_pct = _find_dup_pct(report.repo_metrics)
    mi_values = [mv.value for fr in report.files for mv in fr.metrics if mv.metric_id == "mi"]
    avg_mi = sum(mi_values) / len(mi_values) if mi_values else 0.0

    doc: dict[str, Any] = {
        "version": report.version,
        "scanned_at": report.scanned_at,
        "duration_ms": report.duration_ms,
        "summary": {
            "files": report.files_scanned,
            "sloc": total_sloc,
            "physical_loc": total_physical,
            "logical_loc": total_logical,
            "duplication_pct": round(dup_pct, 3),
            "avg_mi": round(avg_mi, 2),
        },
        "files": [_file_report_to_dict(fr) for fr in report.files],
        "repo_metrics": [_metric_value_to_dict(mv) for mv in report.repo_metrics],
        "violations": [_metric_value_to_dict(mv) for mv in report.violations],
    }
    return json.dumps(doc, indent=2, ensure_ascii=False)


def render_text(report: RunReport, no_color: bool = False) -> str:
    force_terminal = not no_color and sys.stdout.isatty()
    console = Console(
        highlight=False,
        force_terminal=force_terminal,
        no_color=no_color,
    )

    with console.capture() as capture:
        duration_s = report.duration_ms / 1000
        console.print(
            f"[bold]scout[/bold] v{report.version} — scanned [bold]{report.files_scanned}[/bold] files in {duration_s:.2f}s"
        )
        console.print()

        # Summary
        total_sloc = sum(f.sloc for f in report.files)
        dup_pct = _find_dup_pct(report.repo_metrics)
        mi_values = [mv.value for fr in report.files for mv in fr.metrics if mv.metric_id == "mi"]
        avg_mi = sum(mi_values) / len(mi_values) if mi_values else None

        console.print("[bold]Summary[/bold]")
        console.print(f"  Files:       {report.files_scanned}")
        console.print(f"  Total SLOC:  {total_sloc}")
        if dup_pct >= 0:
            dup_color = "green" if dup_pct < 3 else ("yellow" if dup_pct < 5 else "red")
            console.print(f"  Duplication: [{dup_color}]{dup_pct:.1f}%[/{dup_color}]")
        if avg_mi is not None:
            mi_color = "green" if avg_mi >= 20 else ("yellow" if avg_mi >= 10 else "red")
            console.print(f"  Avg MI:      [{mi_color}]{avg_mi:.0f}[/{mi_color}]")

        # Violation sections — group by metric_id
        if report.violations:
            console.print()
            by_metric: dict[str, list[MetricValue]] = {}
            for mv in report.violations:
                by_metric.setdefault(mv.metric_id, []).append(mv)

            for metric_id, mvs in by_metric.items():
                comparator = "< threshold" if metric_id == "mi" else "> threshold"
                console.print(f"\n[bold]{metric_id}[/bold] ({comparator})")
                tbl = Table(show_header=False, box=None, pad_edge=False)
                tbl.add_column("location", style="dim")
                tbl.add_column("symbol")
                tbl.add_column("value", justify="right")
                tbl.add_column("icon")
                for mv in mvs:
                    color = _SEVERITY_COLOR.get(mv.severity, "white")
                    icon = _SEVERITY_ICON.get(mv.severity, "?")
                    loc_str = f"{mv.file}:{mv.line}" if mv.line else mv.file
                    value_str = f"{mv.value:.1f}{'%' if mv.metric_id == 'duplication' else ''}"
                    tbl.add_row(
                        loc_str,
                        mv.symbol or "",
                        f"[{color}]{value_str}[/{color}]",
                        f"[{color}]{icon}[/{color}]",
                    )
                console.print(tbl)

        # Parse errors
        parse_errors = [(fr.path, e) for fr in report.files for e in fr.errors]
        if parse_errors:
            console.print()
            console.print("[bold red]Parse errors[/bold red]")
            for path, err in parse_errors:
                console.print(f"  [dim]{path}:{err.line}[/dim] {err.message}")

        n = len(report.violations)
        console.print()
        code = 1 if n > 0 else 0
        console.print(
            f"Exit code: [bold]{code}[/bold] ({n} threshold violation{'s' if n != 1 else ''})"
        )

    return capture.get()


def _find_dup_pct(repo_metrics: list[MetricValue]) -> float:
    for mv in repo_metrics:
        if mv.metric_id == "duplication":
            return mv.value
    return -1.0


def _metric_value_to_dict(mv: MetricValue) -> dict[str, Any]:
    return {
        "metric_id": mv.metric_id,
        "file": mv.file,
        "scope": mv.scope,
        "symbol": mv.symbol,
        "line": mv.line,
        "value": mv.value,
        "threshold": mv.threshold,
        "severity": mv.severity.value,
    }


def _file_report_to_dict(fr: FileReport) -> dict[str, Any]:
    return {
        "path": fr.path,
        "language": fr.language.value,
        "physical_loc": fr.physical_loc,
        "sloc": fr.sloc,
        "logical_loc": fr.logical_loc,
        "metrics": [_metric_value_to_dict(mv) for mv in fr.metrics],
        "errors": [{"line": e.line, "message": e.message} for e in fr.errors],
    }
