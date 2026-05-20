from __future__ import annotations

from pathlib import Path

import pytest

from scout.config import ScoutConfig
from scout.errors import ConfigError


def test_defaults(tmp_path: Path):
    cfg = ScoutConfig.load(tmp_path)
    assert cfg.language == "auto"
    assert "cc" in cfg.metrics
    assert "mi" in cfg.metrics
    assert cfg.respect_gitignore is True
    assert cfg.jobs == 0
    assert cfg.output_format == "text"
    assert cfg.strict is False
    assert cfg.duplication_min_tokens == 50


def test_default_thresholds(tmp_path: Path):
    cfg = ScoutConfig.load(tmp_path)
    assert cfg.thresholds["cc"] == 15.0
    assert cfg.thresholds["mi"] == 20.0
    assert cfg.thresholds["cognitive"] == 15.0


def test_scout_toml_overrides_defaults(tmp_path: Path):
    (tmp_path / "scout.toml").write_text("[thresholds]\ncc = 5\n")
    cfg = ScoutConfig.load(tmp_path)
    assert cfg.thresholds["cc"] == 5.0
    assert cfg.thresholds["mi"] == 20.0  # not overridden


def test_pyproject_toml_tool_scout(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[tool.scout]\nmetrics = ["cc", "loc"]\n')
    cfg = ScoutConfig.load(tmp_path)
    assert set(cfg.metrics) == {"cc", "loc"}


def test_scout_toml_wins_over_pyproject(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[tool.scout]\n[tool.scout.thresholds]\ncc = 5\n")
    (tmp_path / "scout.toml").write_text("[thresholds]\ncc = 8\n")
    cfg = ScoutConfig.load(tmp_path)
    assert cfg.thresholds["cc"] == 8.0


def test_cli_overrides_win(tmp_path: Path):
    (tmp_path / "scout.toml").write_text("[thresholds]\ncc = 5\n")
    cfg = ScoutConfig.load(tmp_path, {"thresholds": {"cc": 20.0}})
    assert cfg.thresholds["cc"] == 20.0


def test_validation_unknown_metric(tmp_path: Path):
    with pytest.raises(ConfigError, match="Unknown metric"):
        ScoutConfig.load(tmp_path, {"metrics": ["nonexistent"]})


def test_validation_invalid_language(tmp_path: Path):
    with pytest.raises(ConfigError, match="Invalid language"):
        ScoutConfig.load(tmp_path, {"language": "cobol"})


def test_validation_negative_jobs(tmp_path: Path):
    with pytest.raises(ConfigError, match="jobs"):
        ScoutConfig.load(tmp_path, {"jobs": -1})


def test_validation_invalid_output_format(tmp_path: Path):
    with pytest.raises(ConfigError, match="output_format"):
        ScoutConfig.load(tmp_path, {"output_format": "xml"})


def test_malformed_toml(tmp_path: Path):
    (tmp_path / "scout.toml").write_text("this is not valid toml ][")
    with pytest.raises(ConfigError):
        ScoutConfig.load(tmp_path)
