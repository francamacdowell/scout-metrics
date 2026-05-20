from __future__ import annotations

import itertools
import logging
import os
from concurrent.futures import ProcessPoolExecutor

from scout.config import ScoutConfig
from scout.discovery import SourceFile
from scout.metrics import compute_file_metrics
from scout.metrics.base import MetricConfig, MetricValue
from scout.parsers import parse
from scout.parsers.base import ParsedFile

log = logging.getLogger("scout")


def _worker_init() -> None:
    """Eagerly import parser modules so grammar loading happens once per worker."""
    import scout.parsers.python_parser  # noqa: F401


def _worker_task(
    sf: SourceFile,
    metric_ids: tuple[str, ...],
    cfg: MetricConfig,
) -> tuple[ParsedFile, list[MetricValue]]:
    try:
        source = sf.abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        from scout.parsers.base import ParsedFile as PF
        from scout.parsers.base import ParseError

        empty = PF(
            path=sf.abs_path,
            language=sf.language,
            physical_loc=0,
            sloc=0,
            logical_loc=0,
            functions=[],
            classes=[],
            tokens=[],
            imports={},
            file_halstead=None,
            maintainability_index=0.0,
            errors=[ParseError(line=0, message=str(e))],
        )
        return empty, []

    parsed = parse(sf.abs_path, source, sf.language)
    values = compute_file_metrics(parsed, metric_ids, cfg)
    return parsed, values


def run(
    config: ScoutConfig,
    files: list[SourceFile],
) -> list[tuple[ParsedFile, list[MetricValue]]]:
    """Fan out per-file parsing and metric computation across workers."""
    if not files:
        return []

    metric_cfg = MetricConfig(
        thresholds=config.thresholds,
        duplication_min_tokens=config.duplication_min_tokens,
    )
    # Filter to file-scope metric IDs (duplication is a RepoMetric, runs later)
    from scout.metrics import list_file_metric_ids

    file_metric_ids = tuple(mid for mid in config.metrics if mid in list_file_metric_ids())
    metric_ids = file_metric_ids

    max_workers = config.jobs if config.jobs > 0 else os.cpu_count() or 1

    if max_workers == 1 or len(files) == 1:
        # Single-process path — avoids pickling overhead, useful for tests and --jobs 1
        return [_worker_task(sf, metric_ids, metric_cfg) for sf in files]

    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=_worker_init,
    ) as executor:
        results = list(
            executor.map(
                _worker_task,
                files,
                itertools.repeat(metric_ids),
                itertools.repeat(metric_cfg),
                chunksize=8,
            )
        )
    return results
