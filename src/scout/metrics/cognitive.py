from __future__ import annotations

from scout.metrics.base import MetricConfig, MetricValue, Severity, severity_band
from scout.parsers.base import ParsedFile

id = "cognitive"


def compute(parsed: ParsedFile, config: MetricConfig) -> list[MetricValue]:
    rel = str(parsed.path)
    threshold = config.thresholds.get("cognitive")
    out: list[MetricValue] = []
    for fn in parsed.functions:
        score = fn.cognitive_score
        severity = (
            Severity.WARN
            if threshold is not None and score > threshold
            else severity_band(score, [15, 25])
        )
        out.append(
            MetricValue(
                metric_id="cognitive",
                file=rel,
                scope="function",
                symbol=fn.qualified_name,
                line=fn.location.line_start,
                value=float(score),
                threshold=threshold,
                severity=severity,
            )
        )
    return out
