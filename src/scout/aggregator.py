from __future__ import annotations

import datetime

from scout import __version__
from scout.discovery import SourceFile
from scout.metrics.base import FileReport, MetricValue, RunReport, Severity
from scout.parsers.base import ParsedFile


def aggregate(
    worker_results: list[tuple[SourceFile, ParsedFile, list[MetricValue]]],
    duration_ms: int,
    repo_metrics: list[MetricValue] | None = None,
) -> RunReport:
    """Build a RunReport from per-file worker results."""
    parsed_files: list[ParsedFile] = []
    file_reports: list[FileReport] = []

    for sf, parsed, values in worker_results:
        rel = str(sf.rel_path)
        values_sorted = sorted(
            values,
            key=lambda mv: (mv.metric_id, mv.line or 0, mv.symbol or ""),
        )
        values_rel = [
            MetricValue(
                metric_id=mv.metric_id,
                file=rel,
                scope=mv.scope,
                symbol=mv.symbol,
                line=mv.line,
                value=mv.value,
                threshold=mv.threshold,
                severity=mv.severity,
            )
            for mv in values_sorted
        ]
        file_reports.append(
            FileReport(
                path=rel,
                language=parsed.language,
                physical_loc=parsed.physical_loc,
                sloc=parsed.sloc,
                logical_loc=parsed.logical_loc,
                metrics=values_rel,
                errors=parsed.errors,
            )
        )
        parsed_files.append(parsed)

    # Sort files by relative path for determinism
    pairs = sorted(zip(file_reports, parsed_files, strict=False), key=lambda p: p[0].path)
    file_reports = [p[0] for p in pairs]

    effective_repo_metrics = repo_metrics if repo_metrics is not None else []
    all_metrics: list[MetricValue] = [mv for fr in file_reports for mv in fr.metrics] + effective_repo_metrics
    violations = [mv for mv in all_metrics if _is_violation(mv)]
    violations.sort(
        key=lambda mv: (
            _severity_order(mv.severity),
            mv.metric_id,
            mv.file,
            mv.line or 0,
        )
    )

    return RunReport(
        version=__version__,
        scanned_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        duration_ms=duration_ms,
        files_scanned=len(file_reports),
        files=file_reports,
        repo_metrics=effective_repo_metrics,
        violations=violations,
    )


def _is_violation(mv: MetricValue) -> bool:
    if mv.threshold is None:
        return False
    if mv.metric_id == "mi":
        return mv.value < mv.threshold  # MI: lower is worse
    return mv.value > mv.threshold


def _severity_order(s: Severity) -> int:
    return {Severity.ERROR: 0, Severity.WARN: 1, Severity.INFO: 2, Severity.OK: 3}.get(s, 4)
