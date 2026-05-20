from __future__ import annotations

from scout.metrics.base import MetricConfig, MetricValue, Severity
from scout.parsers.base import HalsteadReport, ParsedFile

id = "halstead"


def compute(parsed: ParsedFile, config: MetricConfig) -> list[MetricValue]:
    rel = str(parsed.path)
    out: list[MetricValue] = []

    for fn in parsed.functions:
        if fn.halstead is not None:
            out.extend(
                _emit(rel, "function", fn.qualified_name, fn.location.line_start, fn.halstead)
            )

    if parsed.file_halstead is not None:
        out.extend(_emit(rel, "file", None, None, parsed.file_halstead))

    return out


def _emit(
    rel: str,
    scope: str,
    symbol: str | None,
    line: int | None,
    h: HalsteadReport,
) -> list[MetricValue]:
    return [
        MetricValue(
            metric_id="halstead.volume",
            file=rel,
            scope=scope,
            symbol=symbol,
            line=line,
            value=h.volume,
            threshold=None,
            severity=Severity.OK,
        ),
        MetricValue(
            metric_id="halstead.difficulty",
            file=rel,
            scope=scope,
            symbol=symbol,
            line=line,
            value=h.difficulty,
            threshold=None,
            severity=Severity.OK,
        ),
        MetricValue(
            metric_id="halstead.effort",
            file=rel,
            scope=scope,
            symbol=symbol,
            line=line,
            value=h.effort,
            threshold=None,
            severity=Severity.OK,
        ),
    ]
