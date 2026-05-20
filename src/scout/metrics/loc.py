from __future__ import annotations

from scout.metrics.base import MetricConfig, MetricValue, Severity, severity_band
from scout.parsers.base import ParsedFile

id = "loc"


def compute(parsed: ParsedFile, config: MetricConfig) -> list[MetricValue]:
    rel = str(parsed.path)
    threshold = config.thresholds.get("loc")
    sloc_severity = (
        Severity.WARN
        if threshold is not None and parsed.sloc > threshold
        else severity_band(parsed.sloc, [500, 1000])
    )
    return [
        MetricValue(
            metric_id="loc.physical",
            file=rel,
            scope="file",
            symbol=None,
            line=None,
            value=float(parsed.physical_loc),
            threshold=None,
            severity=Severity.OK,
        ),
        MetricValue(
            metric_id="loc.sloc",
            file=rel,
            scope="file",
            symbol=None,
            line=None,
            value=float(parsed.sloc),
            threshold=threshold,
            severity=sloc_severity,
        ),
        MetricValue(
            metric_id="loc.logical",
            file=rel,
            scope="file",
            symbol=None,
            line=None,
            value=float(parsed.logical_loc),
            threshold=None,
            severity=Severity.OK,
        ),
    ]
