from __future__ import annotations

from scout.metrics.base import MetricConfig, MetricValue, severity_band
from scout.parsers.base import ParsedFile

id = "lcom"


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        px, py = self.find(x), self.find(y)
        if px != py:
            self.parent[px] = py


def compute(parsed: ParsedFile, config: MetricConfig) -> list[MetricValue]:
    rel = str(parsed.path)
    threshold = config.thresholds.get("lcom")
    out: list[MetricValue] = []
    for cls in parsed.classes:
        methods = list(cls.methods)
        n = len(methods)
        if n == 0:
            continue  # do not emit for empty classes
        if n == 1:
            components = 1
        else:
            uf = _UnionFind(n)
            for i in range(n):
                for j in range(i + 1, n):
                    shared = methods[i].referenced_fields & methods[j].referenced_fields
                    calls = (
                        methods[j].name in methods[i].called_methods
                        or methods[i].name in methods[j].called_methods
                    )
                    if shared or calls:
                        uf.union(i, j)
            components = len({uf.find(i) for i in range(n)})

        severity = severity_band(float(components), [1, 3])
        out.append(
            MetricValue(
                metric_id="lcom",
                file=rel,
                scope="class",
                symbol=cls.qualified_name,
                line=cls.location.line_start,
                value=float(components),
                threshold=threshold,
                severity=severity,
            )
        )
    return out
