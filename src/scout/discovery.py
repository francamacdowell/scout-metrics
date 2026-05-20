from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pathspec

from scout.config import ScoutConfig
from scout.errors import DiscoveryError
from scout.parsers.base import Language

log = logging.getLogger("scout")

_EXT_LANGUAGE: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".mjs": Language.JAVASCRIPT,
    ".cjs": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".mts": Language.TYPESCRIPT,
    ".cts": Language.TYPESCRIPT,
}

_BUILTIN_EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "coverage",
        ".tox",
        ".hatch",
        "site-packages",
    }
)

_BUILTIN_EXCLUDE_PATTERNS: list[str] = [
    "*.min.js",
    "*.map",
]


@dataclass(slots=True, frozen=True)
class SourceFile:
    abs_path: Path
    rel_path: Path  # relative to project root
    language: Language
    size_bytes: int


def scan(config: ScoutConfig) -> list[SourceFile]:
    """Walk the project root and return a sorted, filtered list of source files."""
    root = config.root
    if not root.exists():
        raise DiscoveryError(f"Project root does not exist: {root}")
    if not root.is_dir():
        raise DiscoveryError(f"Project root is not a directory: {root}")

    gitignore_spec = _load_gitignore(root) if config.respect_gitignore else None
    user_exclude = pathspec.PathSpec.from_lines("gitwildmatch", list(config.exclude))
    user_include = (
        pathspec.PathSpec.from_lines("gitwildmatch", list(config.include))
        if config.include
        else None
    )
    builtin_exclude = pathspec.PathSpec.from_lines("gitwildmatch", _BUILTIN_EXCLUDE_PATTERNS)

    active_languages = _resolve_languages(config.language)

    files: list[SourceFile] = []
    for abs_path, rel_path in _walk(root):
        # Check dir-level excludes (already done in _walk via pruning)
        rel_str = str(rel_path)

        # Gitignore
        if gitignore_spec and gitignore_spec.match_file(rel_str):
            continue

        # Built-in file-pattern excludes
        if builtin_exclude.match_file(rel_str):
            continue

        # User excludes
        if user_exclude.match_file(rel_str):
            continue

        # Language filter
        lang = _EXT_LANGUAGE.get(abs_path.suffix.lower())
        if lang is None:
            continue
        if active_languages and lang not in active_languages:
            continue

        # Include filter (if specified, file must match)
        if user_include and not user_include.match_file(rel_str):
            continue

        # Size cap
        try:
            size = abs_path.stat().st_size
        except OSError:
            log.warning("Cannot stat %s, skipping", abs_path)
            continue
        if size > config.max_file_bytes:
            log.warning(
                "Skipping %s: size %d bytes exceeds limit %d", rel_path, size, config.max_file_bytes
            )
            continue

        files.append(
            SourceFile(abs_path=abs_path, rel_path=rel_path, language=lang, size_bytes=size)
        )

    # Deterministic sort by relative path
    files.sort(key=lambda f: str(f.rel_path))
    return files


def _walk(root: Path) -> Iterator[tuple[Path, Path]]:
    """Yield (abs_path, rel_path) for all files under root, pruning built-in exclude dirs."""
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune built-in excluded directories in-place to prevent descent
        dirnames[:] = [
            d for d in dirnames if d not in _BUILTIN_EXCLUDE_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            abs_path = Path(dirpath) / fname
            rel_path = abs_path.relative_to(root)
            yield abs_path, rel_path


def _load_gitignore(root: Path) -> pathspec.PathSpec | None:
    patterns: list[str] = []
    gitignore = root / ".gitignore"
    if gitignore.exists():
        try:
            patterns.extend(gitignore.read_text(encoding="utf-8").splitlines())
        except OSError:
            log.warning("Could not read .gitignore")
    git_exclude = root / ".git" / "info" / "exclude"
    if git_exclude.exists():
        with contextlib.suppress(OSError):
            patterns.extend(git_exclude.read_text(encoding="utf-8").splitlines())
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns) if patterns else None


def _resolve_languages(language: str) -> set[Language] | None:
    """Return the active language set, or None meaning 'auto-detect'."""
    if language == "auto":
        return None  # caller (scan) should detect from files found
    mapping = {
        "python": Language.PYTHON,
        "javascript": Language.JAVASCRIPT,
        "typescript": Language.TYPESCRIPT,
    }
    lang = mapping.get(language)
    if lang is None:
        return None
    return {lang}
