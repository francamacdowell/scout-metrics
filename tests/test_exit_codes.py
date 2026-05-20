from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from scout.cli import app
from scout.errors import (
    EXIT_CONFIG_ERROR,
    EXIT_IO_ERROR,
    EXIT_OK,
    EXIT_PARSE_ERROR,
    EXIT_VIOLATIONS,
)

runner = CliRunner()


def test_exit_ok(tmp_path: Path):
    (tmp_path / "clean.py").write_text("x = 1\n")
    result = runner.invoke(app, [str(tmp_path)])
    assert result.exit_code == EXIT_OK


def test_exit_violations(tmp_path: Path):
    # Write a function with CC high enough to violate threshold=1
    body = "def f(x):\n" + "    if x:\n" * 30 + "        return x\n"
    (tmp_path / "complex.py").write_text(body)
    result = runner.invoke(app, [str(tmp_path), "--threshold", "cc=1"])
    assert result.exit_code == EXIT_VIOLATIONS


def test_exit_config_error(tmp_path: Path):
    result = runner.invoke(app, [str(tmp_path), "--language", "cobol"])
    assert result.exit_code == EXIT_CONFIG_ERROR


def test_exit_io_error():
    result = runner.invoke(app, ["/nonexistent/path/xyz"])
    assert result.exit_code == EXIT_IO_ERROR


def test_exit_parse_error_without_strict(tmp_path: Path):
    (tmp_path / "broken.py").write_text("def broken(\n    pass\n")
    result = runner.invoke(app, [str(tmp_path)])
    # Without --strict, parse errors are tolerated → exit 0 (no violations)
    assert result.exit_code in (EXIT_OK, EXIT_VIOLATIONS)


def test_exit_parse_error_with_strict(tmp_path: Path):
    (tmp_path / "broken.py").write_text("def broken(\n    pass\n")
    result = runner.invoke(app, [str(tmp_path), "--strict"])
    assert result.exit_code == EXIT_PARSE_ERROR
