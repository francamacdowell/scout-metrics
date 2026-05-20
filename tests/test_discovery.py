from __future__ import annotations

from pathlib import Path

from scout.config import ScoutConfig
from scout.discovery import scan
from scout.parsers.base import Language


def _cfg(tmp_path: Path, overrides: dict | None = None) -> ScoutConfig:
    return ScoutConfig.load(tmp_path, overrides or {})


def test_finds_python_files(tmp_path: Path):
    (tmp_path / "app.py").write_text("x = 1\n")
    files = scan(_cfg(tmp_path))
    assert len(files) == 1
    assert files[0].language == Language.PYTHON


def test_finds_js_files(tmp_path: Path):
    (tmp_path / "app.js").write_text("const x = 1;\n")
    files = scan(_cfg(tmp_path))
    assert len(files) == 1
    assert files[0].language == Language.JAVASCRIPT


def test_finds_ts_files(tmp_path: Path):
    (tmp_path / "app.ts").write_text("const x: number = 1;\n")
    files = scan(_cfg(tmp_path))
    assert len(files) == 1
    assert files[0].language == Language.TYPESCRIPT


def test_excludes_venv_directory(tmp_path: Path):
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "site.py").write_text("x = 1\n")
    (tmp_path / "app.py").write_text("y = 2\n")
    files = scan(_cfg(tmp_path))
    assert len(files) == 1
    assert files[0].rel_path == Path("app.py")


def test_excludes_node_modules(tmp_path: Path):
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("module.exports = {};\n")
    (tmp_path / "src.js").write_text("const x = 1;\n")
    files = scan(_cfg(tmp_path))
    assert len(files) == 1


def test_respects_gitignore(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".gitignore").write_text("secret.py\n")
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "secret.py").write_text("password = 'hunter2'\n")
    files = scan(_cfg(tmp_path))
    assert all(f.rel_path != Path("secret.py") for f in files)


def test_no_gitignore_flag(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("secret.py\n")
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "secret.py").write_text("x = 1\n")
    files = scan(_cfg(tmp_path, {"respect_gitignore": False}))
    paths = {f.rel_path for f in files}
    assert Path("secret.py") in paths


def test_size_cap_skips_large_files(tmp_path: Path):
    big = tmp_path / "big.py"
    big.write_bytes(b"x = 1\n" * 200_000)  # ~1.2 MB
    (tmp_path / "small.py").write_text("y = 2\n")
    files = scan(_cfg(tmp_path, {"max_file_bytes": 1_048_576}))
    assert all(f.rel_path == Path("small.py") for f in files)


def test_language_filter_python_only(tmp_path: Path):
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "app.js").write_text("const x = 1;\n")
    files = scan(_cfg(tmp_path, {"language": "python"}))
    assert all(f.language == Language.PYTHON for f in files)


def test_sorted_output(tmp_path: Path):
    for name in ("z.py", "a.py", "m.py"):
        (tmp_path / name).write_text("x = 1\n")
    files = scan(_cfg(tmp_path))
    paths = [str(f.rel_path) for f in files]
    assert paths == sorted(paths)


def test_include_glob(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test(): pass\n")
    files = scan(_cfg(tmp_path, {"include": ["src/**"]}))
    assert all("src" in str(f.rel_path) for f in files)
