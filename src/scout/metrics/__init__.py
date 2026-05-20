from __future__ import annotations

from types import ModuleType

from scout.metrics import cbo, cc, cognitive, halstead, lcom, loc, mi
from scout.metrics.base import MetricConfig, MetricValue
from scout.parsers.base import ParsedFile

# File-scoped metrics — run per-file inside worker processes
_FILE_METRICS: dict[str, ModuleType] = {
    loc.id: loc,
    cc.id: cc,
    cognitive.id: cognitive,
    halstead.id: halstead,
    mi.id: mi,
    cbo.id: cbo,
    lcom.id: lcom,
}


def get_file_metric(metric_id: str) -> ModuleType | None:
    return _FILE_METRICS.get(metric_id)


def list_file_metric_ids() -> list[str]:
    return list(_FILE_METRICS)


def compute_file_metrics(
    parsed: ParsedFile, metric_ids: tuple[str, ...], cfg: MetricConfig
) -> list[MetricValue]:
    out: list[MetricValue] = []
    for mid in metric_ids:
        module = _FILE_METRICS.get(mid)
        if module is not None:
            out.extend(module.compute(parsed, cfg))
    return out
