from __future__ import annotations

import time
from pathlib import Path

import pytest

from scout.config import ScoutConfig
from scout.discovery import scan
from scout.runner import run

FIXTURES = Path(__file__).parent / "fixtures" / "repos"


@pytest.mark.perf
def test_perf_10k_sloc_under_5s():
    """Loose gate: 10k SLOC must complete in under 5 seconds."""
    sample = FIXTURES / "perf_sample_py"
    if not sample.exists():
        pytest.skip("perf_sample_py fixture not present")

    cfg = ScoutConfig.load(sample)
    files = scan(cfg)

    start = time.perf_counter()
    run(cfg, files)
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0, f"10k SLOC run took {elapsed:.2f}s (budget: 5s)"


def _generate_py_module(
    mod_idx: int, n_classes: int, methods_per_class: int, n_functions: int
) -> str:
    """Generate a synthetic Python module with predictable structure."""
    lines = [
        "from __future__ import annotations",
        "import math",
        "from dataclasses import dataclass",
        "",
    ]
    for ci in range(n_classes):
        cname = f"Module{mod_idx:04d}Class{ci}"
        lines += [
            f"class {cname}:",
            "    def __init__(self, v: int = 0) -> None:",
            "        self.v = v",
            "        self.acc: list[int] = []",
        ]
        for mi in range(methods_per_class):
            lines += [
                f"    def method_{mi:03d}(self, x: int, y: int) -> int:",
                "        if x < 0:",
                "            x = abs(x)",
                "        if y == 0:",
                "            return self.v",
                "        total = x + y",
                "        for i in range(min(x, 10)):",
                "            total += i * y",
                "        self.acc.append(total)",
                "        return total % 1000",
            ]
        lines.append("")
    for fi in range(n_functions):
        lines += [
            f"def m{mod_idx:04d}_fn{fi:03d}(a: int, b: int, c: int = 1) -> float:",
            "    if a < 0 or b < 0:",
            "        return 0.0",
            "    result = 0.0",
            "    for i in range(a):",
            "        if i % 2 == 0:",
            "            result += b * math.log(i + 1)",
            "        elif i % 3 == 0:",
            "            result -= c * i",
            "        else:",
            "            result += i",
            "    return result / (a + 1)",
            "",
        ]
    return "\n".join(lines)


@pytest.mark.perf
def test_perf_100k_sloc_under_15s(tmp_path: Path):
    """Strict §13 gate: 100k SLOC must complete in under 15 seconds.

    Fixture is generated at test time in a tempdir — not stored in the repo.
    Target: ~100k SLOC across ~120 files (~833 SLOC/file).
    """
    # Generate ~100k SLOC: 120 files x ~850 SLOC each
    total_sloc = 0
    for i in range(120):
        src = _generate_py_module(mod_idx=i, n_classes=5, methods_per_class=10, n_functions=12)
        sloc = sum(1 for ln in src.splitlines() if ln.strip() and not ln.strip().startswith("#"))
        total_sloc += sloc
        (tmp_path / f"module_{i:04d}.py").write_text(src)

    assert total_sloc >= 80_000, f"Fixture only generated {total_sloc} SLOC — too small"

    cfg = ScoutConfig.load(tmp_path)
    files = scan(cfg)

    start = time.perf_counter()
    run(cfg, files)
    elapsed = time.perf_counter() - start

    assert elapsed < 15.0, (
        f"100k SLOC run took {elapsed:.2f}s (budget: 15s, SLOC: {total_sloc})\n"
        "Hint: profile with `py-spy record -o profile.svg -- uv run scout <path>`"
    )
