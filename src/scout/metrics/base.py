from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from scout.parsers.base import Language, ParsedFile, ParseError


class Severity(str, Enum):
    OK = "ok"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


@dataclass(slots=True, frozen=True)
class MetricValue:
    metric_id: str  # e.g. "cc", "cognitive", "halstead.volume"
    file: str  # relative path from project root
    scope: str  # function | class | file | repo
    symbol: str | None  # qualified function/class name, if applicable
    line: int | None  # 1-indexed
    value: float
    threshold: float | None
    severity: Severity


@dataclass(slots=True)
class FileReport:
    path: str
    language: Language
    physical_loc: int
    sloc: int
    logical_loc: int
    metrics: list[MetricValue]
    errors: list[ParseError]


@dataclass(slots=True)
class RunReport:
    version: str
    scanned_at: str  # ISO-8601 UTC
    duration_ms: int
    files_scanned: int
    files: list[FileReport]
    repo_metrics: list[MetricValue]
    violations: list[MetricValue]


@dataclass(slots=True)
class MetricConfig:
    """Slice of ScoutConfig passed to metric workers."""

    thresholds: dict[str, float]
    duplication_min_tokens: int


def severity_band(value: float, bands: list[int]) -> Severity:
    """Map a value to a Severity using ascending threshold bands.

    bands = [warn_at, error_at] or [warn_at, high_warn_at, error_at].
    Values below bands[0] → OK, at or above last band → ERROR.
    """
    if not bands:
        return Severity.OK
    if value <= bands[0]:
        return Severity.OK
    if len(bands) == 1 or value <= bands[1]:
        return Severity.WARN
    if len(bands) == 2 or value <= bands[2]:
        return Severity.ERROR
    return Severity.ERROR


class FileMetric(Protocol):
    """Computes a metric using only per-file data. Runs in worker processes."""

    id: str

    def compute(self, parsed: ParsedFile, config: MetricConfig) -> list[MetricValue]: ...


class RepoMetric(Protocol):
    """Computes a metric across all files. Runs in the main process after aggregation."""

    id: str

    def compute(self, files: list[ParsedFile], config: MetricConfig) -> list[MetricValue]: ...
