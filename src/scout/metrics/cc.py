from __future__ import annotations

from scout.metrics.base import MetricConfig, MetricValue, severity_band
from scout.parsers.base import ParsedFile

id = "cc"


def compute(parsed: ParsedFile, config: MetricConfig) -> list[MetricValue]:
    rel = str(parsed.path)
    threshold = config.thresholds.get("cc")
    out: list[MetricValue] = []
    for fn in parsed.functions:
        cc = fn.cyclomatic_complexity
        severity = severity_band(cc, [10, 20, 50])
        out.append(
            MetricValue(
                metric_id="cc",
                file=rel,
                scope="function",
                symbol=fn.qualified_name,
                line=fn.location.line_start,
                value=float(cc),
                threshold=threshold,
                severity=severity,
            )
        )
    return out
