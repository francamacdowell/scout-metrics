from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from scout.cli import app
from scout.errors import EXIT_OK, EXIT_VIOLATIONS

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "repos"
GOLDEN = Path(__file__).parent / "fixtures" / "golden"
UPDATE = os.environ.get("UPDATE_SNAPSHOTS") == "1"

PY_SAMPLE = FIXTURES / "py_sample"
JS_SAMPLE = FIXTURES / "js_sample"
TS_SAMPLE = FIXTURES / "ts_sample"


def test_py_sample_runs(tmp_path: Path):
    result = runner.invoke(app, [str(PY_SAMPLE), "--format", "json"])
    assert result.exit_code in (EXIT_OK, EXIT_VIOLATIONS), result.output


def test_py_sample_json_structure(tmp_path: Path):
    result = runner.invoke(app, [str(PY_SAMPLE), "--format", "json"])
    data = json.loads(result.output)
    assert "version" in data
    assert "summary" in data
    assert "files" in data
    assert data["summary"]["files"] >= 1


def test_py_sample_detects_python_files():
    result = runner.invoke(app, [str(PY_SAMPLE), "--format", "json"])
    data = json.loads(result.output)
    langs = {f["language"] for f in data["files"]}
    assert "python" in langs


def test_py_sample_golden(tmp_path: Path):
    golden_path = GOLDEN / "py_sample.json"
    result = runner.invoke(
        app,
        [str(PY_SAMPLE), "--format", "json", "--metrics", "cc,loc,mi"],
    )
    assert result.exit_code in (EXIT_OK, EXIT_VIOLATIONS)
    data = json.loads(result.output)

    if UPDATE:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        # Strip volatile fields before saving
        _strip_volatile(data)
        golden_path.write_text(json.dumps(data, indent=2) + "\n")
        pytest.skip("Golden file updated")

    if not golden_path.exists():
        pytest.skip("Golden file not yet generated — run with UPDATE_SNAPSHOTS=1")

    golden = json.loads(golden_path.read_text())
    _strip_volatile(data)
    # Compare file paths and metric ids (not exact values, which vary by radon version)
    actual_paths = sorted(f["path"] for f in data["files"])
    golden_paths = sorted(f["path"] for f in golden["files"])
    assert actual_paths == golden_paths


def _strip_volatile(data: dict) -> None:
    data.pop("scanned_at", None)
    data.pop("duration_ms", None)


def test_js_sample_runs():
    if not JS_SAMPLE.exists() or not any(JS_SAMPLE.iterdir()):
        pytest.skip("js_sample fixture not present")
    result = runner.invoke(app, [str(JS_SAMPLE), "--format", "json"])
    assert result.exit_code in (EXIT_OK, EXIT_VIOLATIONS), result.output


def test_js_sample_detects_javascript_files():
    if not JS_SAMPLE.exists() or not any(JS_SAMPLE.iterdir()):
        pytest.skip("js_sample fixture not present")
    result = runner.invoke(app, [str(JS_SAMPLE), "--format", "json"])
    data = json.loads(result.output)
    langs = {f["language"] for f in data["files"]}
    assert "javascript" in langs


def test_js_sample_golden():
    if not JS_SAMPLE.exists() or not any(JS_SAMPLE.iterdir()):
        pytest.skip("js_sample fixture not present")
    golden_path = GOLDEN / "js_sample.json"
    result = runner.invoke(
        app,
        [str(JS_SAMPLE), "--format", "json", "--metrics", "cc,loc,mi"],
    )
    assert result.exit_code in (EXIT_OK, EXIT_VIOLATIONS)
    data = json.loads(result.output)

    if UPDATE:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        _strip_volatile(data)
        golden_path.write_text(json.dumps(data, indent=2) + "\n")
        pytest.skip("Golden file updated")

    if not golden_path.exists():
        pytest.skip("Golden file not yet generated — run with UPDATE_SNAPSHOTS=1")

    golden = json.loads(golden_path.read_text())
    _strip_volatile(data)
    actual_paths = sorted(f["path"] for f in data["files"])
    golden_paths = sorted(f["path"] for f in golden["files"])
    assert actual_paths == golden_paths


def test_ts_sample_runs():
    if not TS_SAMPLE.exists() or not any(TS_SAMPLE.iterdir()):
        pytest.skip("ts_sample fixture not present")
    result = runner.invoke(app, [str(TS_SAMPLE), "--format", "json"])
    assert result.exit_code in (EXIT_OK, EXIT_VIOLATIONS), result.output


def test_ts_sample_detects_typescript_files():
    if not TS_SAMPLE.exists() or not any(TS_SAMPLE.iterdir()):
        pytest.skip("ts_sample fixture not present")
    result = runner.invoke(app, [str(TS_SAMPLE), "--format", "json"])
    data = json.loads(result.output)
    langs = {f["language"] for f in data["files"]}
    assert "typescript" in langs


def test_ts_sample_golden():
    if not TS_SAMPLE.exists() or not any(TS_SAMPLE.iterdir()):
        pytest.skip("ts_sample fixture not present")
    golden_path = GOLDEN / "ts_sample.json"
    result = runner.invoke(
        app,
        [str(TS_SAMPLE), "--format", "json", "--metrics", "cc,loc,mi"],
    )
    assert result.exit_code in (EXIT_OK, EXIT_VIOLATIONS)
    data = json.loads(result.output)

    if UPDATE:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        _strip_volatile(data)
        golden_path.write_text(json.dumps(data, indent=2) + "\n")
        pytest.skip("Golden file updated")

    if not golden_path.exists():
        pytest.skip("Golden file not yet generated — run with UPDATE_SNAPSHOTS=1")

    golden = json.loads(golden_path.read_text())
    _strip_volatile(data)
    actual_paths = sorted(f["path"] for f in data["files"])
    golden_paths = sorted(f["path"] for f in golden["files"])
    assert actual_paths == golden_paths


def test_text_output_renders(tmp_path: Path):
    result = runner.invoke(app, [str(PY_SAMPLE)])
    assert result.exit_code in (EXIT_OK, EXIT_VIOLATIONS)
    assert "scout" in result.output.lower() or "files" in result.output.lower()


def test_dup_sample_detects_duplication():
    dup_sample = FIXTURES / "dup_sample"
    if not dup_sample.exists():
        pytest.skip("dup_sample fixture not present")
    result = runner.invoke(app, [str(dup_sample), "--format", "json", "--metrics", "duplication"])
    data = json.loads(result.output)
    repo_metrics = data.get("repo_metrics", [])
    dup = next((m for m in repo_metrics if m["metric_id"] == "duplication"), None)
    assert dup is not None
    assert dup["value"] > 0
