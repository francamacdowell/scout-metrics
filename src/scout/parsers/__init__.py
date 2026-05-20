from __future__ import annotations

from pathlib import Path

from scout.parsers.base import Language, ParsedFile


def parse(path: Path, source: str, language: Language) -> ParsedFile:
    """Dispatch to the appropriate language parser."""
    if language == Language.PYTHON:
        from scout.parsers.python_parser import parse as py_parse

        return py_parse(path, source)
    if language == Language.JAVASCRIPT:
        from scout.parsers.js_parser import parse as js_parse

        return js_parse(path, source)
    if language == Language.TYPESCRIPT:
        from scout.parsers.ts_parser import parse as ts_parse

        return ts_parse(path, source)
    raise NotImplementedError(f"No parser for language: {language}")
