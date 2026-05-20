from __future__ import annotations

from scout.metrics.base import MetricConfig, MetricValue, Severity
from scout.parsers.base import ParsedFile

id = "mi"

# Visual Studio MI bands: lower MI = worse quality
_BAND_RED = 10.0
_BAND_YELLOW = 20.0


def compute(parsed: ParsedFile, config: MetricConfig) -> list[MetricValue]:
    mi = parsed.maintainability_index
    threshold = config.thresholds.get("mi")

    # MI is reversed: lower is worse.
    # Threshold is the *minimum* acceptable value (flag if BELOW threshold).
    severity: Severity
    if mi < _BAND_RED:
        severity = Severity.ERROR
    elif mi < _BAND_YELLOW:
        severity = Severity.WARN
    else:
        severity = Severity.OK

    return [
        MetricValue(
            metric_id="mi",
            file=str(parsed.path),
            scope="file",
            symbol=None,
            line=None,
            value=mi,
            threshold=threshold,
            severity=severity,
        )
    ]
