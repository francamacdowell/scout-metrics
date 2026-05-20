from __future__ import annotations

from scout.metrics.base import MetricConfig, MetricValue, severity_band
from scout.parsers.base import ParsedFile

id = "cbo"


def compute(parsed: ParsedFile, config: MetricConfig) -> list[MetricValue]:
    rel = str(parsed.path)
    threshold = config.thresholds.get("cbo")
    out: list[MetricValue] = []
    for cls in parsed.classes:
        val = float(len(cls.imported_class_refs))
        severity = severity_band(val, [5, 14])
        out.append(
            MetricValue(
                metric_id="cbo",
                file=rel,
                scope="class",
                symbol=cls.qualified_name,
                line=cls.location.line_start,
                value=val,
                threshold=threshold,
                severity=severity,
            )
        )
    return out
