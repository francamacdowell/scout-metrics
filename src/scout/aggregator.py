from __future__ import annotations

import datetime

from scout import __version__
from scout.config import ScoutConfig
from scout.discovery import SourceFile
from scout.metrics.base import FileReport, MetricConfig, MetricValue, RunReport, Severity
from scout.parsers.base import ParsedFile


def aggregate(
    config: ScoutConfig,
    source_files: list[SourceFile],
    worker_results: list[tuple[ParsedFile, list[MetricValue]]],
    duration_ms: int,
) -> RunReport:
    """Build a RunReport from per-file worker results."""
    parsed_files: list[ParsedFile] = []
    file_reports: list[FileReport] = []

    for sf, (parsed, values) in zip(source_files, worker_results, strict=False):
        rel = str(sf.rel_path)
        # Sort MetricValues within file by (metric_id, line, symbol) for determinism
        values_sorted = sorted(
            values,
            key=lambda mv: (mv.metric_id, mv.line or 0, mv.symbol or ""),
        )
        # Override file path to use relative path
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
    parsed_files = [p[1] for p in pairs]

    # Repo-level metrics (duplication)
    repo_metrics: list[MetricValue] = []
    if "duplication" in config.metrics:
        from scout.metrics.duplication import compute as dup_compute

        metric_cfg = MetricConfig(
            thresholds=config.thresholds,
            duplication_min_tokens=config.duplication_min_tokens,
        )
        dup_values = dup_compute(parsed_files, metric_cfg)
        repo_metrics.extend(dup_values)

    # Violations: MetricValues where threshold was actually exceeded
    all_metrics: list[MetricValue] = [mv for fr in file_reports for mv in fr.metrics] + repo_metrics
    violations = [mv for mv in all_metrics if _is_violation(mv)]
    # Sort violations by (severity desc, metric_id, file, line)
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
        repo_metrics=repo_metrics,
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
