from __future__ import annotations

from collections import defaultdict
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

from scout.metrics.base import MetricConfig, MetricValue, Severity, severity_band
from scout.parsers.base import ParsedFile, Token

id = "duplication"

_BASE = 1_000_003
_MOD = (1 << 61) - 1


@dataclass
class _Match:
    a_path: Path
    a_start: int  # token index, inclusive
    a_end: int  # exclusive
    b_path: Path
    b_start: int
    b_end: int


def compute(files: list[ParsedFile], config: MetricConfig) -> list[MetricValue]:
    window = config.duplication_min_tokens
    file_lang = {f.path: f.language for f in files}

    # Normalize each file's token stream
    streams: dict[Path, list[tuple[str, str]]] = {f.path: _normalize(f.tokens) for f in files}
    # Original tokens kept for line mapping
    raw_tokens: dict[Path, list[Token]] = {f.path: f.tokens for f in files}

    # Build hash → [(path, start_idx)] map
    hashes: dict[int, list[tuple[Path, int]]] = defaultdict(list)
    for path, stream in streams.items():
        if len(stream) < window:
            continue
        for h, idx in _rolling_hash(stream, window):
            hashes[h].append((path, idx))

    # Find and extend matches
    matches: list[_Match] = []
    seen: set[tuple[Path, int, Path, int]] = set()

    for locs in hashes.values():
        if len(locs) < 2:
            continue
        for i in range(len(locs)):
            for j in range(i + 1, len(locs)):
                pa, ai = locs[i]
                pb, bj = locs[j]
                if pa == pb and abs(ai - bj) < window:
                    continue  # overlapping region in same file
                if file_lang.get(pa) != file_lang.get(pb):
                    continue  # cross-language: never match
                key = (pa, ai, pb, bj)
                if key in seen:
                    continue
                seen.add(key)
                sa, sb = streams[pa], streams[pb]
                if sa[ai : ai + window] != sb[bj : bj + window]:
                    continue  # hash collision: verify token-by-token
                m = _extend(sa, ai, sb, bj, window, pa, pb)
                matches.append(m)

    matches = _dedupe(matches)

    # Count unique duplicated lines per file
    dup_lines: dict[Path, set[int]] = defaultdict(set)
    for m in matches:
        for t in raw_tokens[m.a_path][m.a_start : m.a_end]:
            dup_lines[m.a_path].add(t.line)
        for t in raw_tokens[m.b_path][m.b_start : m.b_end]:
            dup_lines[m.b_path].add(t.line)

    total_sloc = sum(f.sloc for f in files)
    dup_count = sum(len(lines) for lines in dup_lines.values())
    pct = (dup_count / total_sloc * 100) if total_sloc > 0 else 0.0
    threshold = config.thresholds.get("duplication")
    severity = (
        Severity.WARN if threshold is not None and pct > threshold else severity_band(pct, [3, 5])
    )
    return [
        MetricValue(
            metric_id="duplication",
            file="",
            scope="repo",
            symbol=None,
            line=None,
            value=pct,
            threshold=threshold,
            severity=severity,
        )
    ]


def _normalize(tokens: list[Token]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for t in tokens:
        if t.kind == "identifier":
            out.append(("identifier", "<ID>"))
        else:
            out.append((t.kind, t.value))
    return out


def _rolling_hash(
    stream: list[tuple[str, str]], window: int
) -> Generator[tuple[int, int], None, None]:
    n = len(stream)
    if n < window:
        return
    pow_w = pow(_BASE, window, _MOD)

    def _h(item: tuple[str, str]) -> int:
        return hash(item) & 0x7FFFFFFFFFFFFFFF  # keep positive

    h = 0
    for i in range(window):
        h = (h * _BASE + _h(stream[i])) % _MOD
    yield h, 0

    for i in range(1, n - window + 1):
        h = (h * _BASE - _h(stream[i - 1]) * pow_w + _h(stream[i + window - 1])) % _MOD
        yield h, i


def _extend(
    sa: list[tuple[str, str]],
    ai: int,
    sb: list[tuple[str, str]],
    bj: int,
    window: int,
    pa: Path,
    pb: Path,
) -> _Match:
    # Extend left
    la, lb = ai, bj
    while la > 0 and lb > 0 and sa[la - 1] == sb[lb - 1]:
        la -= 1
        lb -= 1
    # Extend right (already at window; keep going)
    ra, rb = ai + window, bj + window
    while ra < len(sa) and rb < len(sb) and sa[ra] == sb[rb]:
        ra += 1
        rb += 1
    return _Match(a_path=pa, a_start=la, a_end=ra, b_path=pb, b_start=lb, b_end=rb)


def _dedupe(matches: list[_Match]) -> list[_Match]:
    """Drop matches fully subsumed by a longer match on the same file pair."""
    matches.sort(key=lambda m: (m.a_path, m.b_path, -(m.a_end - m.a_start)))
    kept: list[_Match] = []
    for m in matches:
        subsumed = False
        for k in kept:
            if (
                k.a_path == m.a_path
                and k.b_path == m.b_path
                and k.a_start <= m.a_start
                and k.a_end >= m.a_end
                and k.b_start <= m.b_start
                and k.b_end >= m.b_end
            ):
                subsumed = True
                break
        if not subsumed:
            kept.append(m)
    return kept
