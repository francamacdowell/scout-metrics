from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from scout.config import ScoutConfig
from scout.discovery import SourceFile, scan
from scout.runner import run


def _make_cfg(tmp_path: Path, **overrides: object) -> ScoutConfig:
    return ScoutConfig.load(tmp_path, overrides or None)


def _write_files(tmp_path: Path, count: int = 3) -> list[Path]:
    paths = []
    for i in range(count):
        p = tmp_path / f"mod_{i}.py"
        p.write_text(f"x_{i} = {i}\n")
        paths.append(p)
    return paths


class TestWorkerContract:
    def test_run_returns_triples(self, tmp_path: Path) -> None:
        _write_files(tmp_path, count=2)
        cfg = _make_cfg(tmp_path, metrics=["cc"])
        files = scan(cfg)
        results = run(cfg, files)
        assert len(results) == 2
        for item in results:
            assert len(item) == 3
            sf, _parsed, _vals = item
            assert isinstance(sf, SourceFile)
            assert sf.abs_path.suffix == ".py"

    def test_sf_attribution_matches_parsed_path(self, tmp_path: Path) -> None:
        """SourceFile.abs_path must equal ParsedFile.path for every triple."""
        _write_files(tmp_path, count=4)
        cfg = _make_cfg(tmp_path, metrics=["cc"])
        files = scan(cfg)
        results = run(cfg, files)
        for sf, parsed, _vals in results:
            assert sf.abs_path == parsed.path

    def test_run_empty_files_returns_empty(self, tmp_path: Path) -> None:
        cfg = _make_cfg(tmp_path)
        results = run(cfg, [])
        assert results == []


class TestOnFileDoneCallback:
    def test_callback_called_once_per_file(self, tmp_path: Path) -> None:
        n = 5
        _write_files(tmp_path, count=n)
        cfg = _make_cfg(tmp_path, metrics=["cc"], jobs=1)
        files = scan(cfg)
        callback = MagicMock()
        run(cfg, files, on_file_done=callback)
        assert callback.call_count == n

    def test_callback_receives_source_file(self, tmp_path: Path) -> None:
        _write_files(tmp_path, count=2)
        cfg = _make_cfg(tmp_path, metrics=["cc"], jobs=1)
        files = scan(cfg)
        received: list[SourceFile] = []
        run(cfg, files, on_file_done=received.append)
        assert all(isinstance(sf, SourceFile) for sf in received)
        assert {sf.abs_path for sf in received} == {sf.abs_path for sf in files}

    def test_no_callback_still_works(self, tmp_path: Path) -> None:
        _write_files(tmp_path, count=2)
        cfg = _make_cfg(tmp_path, metrics=["cc"], jobs=1)
        files = scan(cfg)
        results = run(cfg, files)
        assert len(results) == 2

    def test_callback_called_in_parallel_path(self, tmp_path: Path) -> None:
        _write_files(tmp_path, count=6)
        cfg = _make_cfg(tmp_path, metrics=["cc"], jobs=2)
        files = scan(cfg)
        callback = MagicMock()
        run(cfg, files, on_file_done=callback)
        assert callback.call_count == len(files)
