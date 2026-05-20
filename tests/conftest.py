from __future__ import annotations

from pathlib import Path

from scout.parsers.base import (
    ClassUnit,
    FunctionUnit,
    HalsteadReport,
    Language,
    MethodInfo,
    ParsedFile,
    SourceLocation,
    Token,
)


def make_halstead(v: float = 10.0, d: float = 2.0) -> HalsteadReport:
    return HalsteadReport(h1=3, h2=3, N1=10, N2=10, volume=v, difficulty=d, effort=v * d)


def make_function(
    name: str = "func",
    qn: str | None = None,
    cc: int = 1,
    cog: int = 0,
    sloc: int = 5,
    line: int = 1,
    halstead: HalsteadReport | None = None,
) -> FunctionUnit:
    loc = SourceLocation(line_start=line, line_end=line + sloc)
    return FunctionUnit(
        name=name,
        qualified_name=qn or name,
        location=loc,
        params=(),
        branches=[],
        tokens=[],
        sloc=sloc,
        cyclomatic_complexity=cc,
        cognitive_score=cog,
        halstead=halstead or make_halstead(),
    )


def make_class(
    name: str = "MyClass",
    qn: str | None = None,
    methods: list[MethodInfo] | None = None,
    fields: frozenset[str] | None = None,
    line: int = 1,
) -> ClassUnit:
    loc = SourceLocation(line_start=line, line_end=line + 10)
    return ClassUnit(
        name=name,
        qualified_name=qn or name,
        location=loc,
        fields=fields or frozenset(),
        methods=tuple(methods or []),
        imported_class_refs=frozenset(),
    )


def make_method(
    name: str,
    refs: frozenset[str] | None = None,
    calls: frozenset[str] | None = None,
) -> MethodInfo:
    return MethodInfo(
        name=name,
        location=SourceLocation(1, 5),
        referenced_fields=refs or frozenset(),
        called_methods=calls or frozenset(),
    )


def make_parsed_file(
    path: str = "test.py",
    language: Language = Language.PYTHON,
    sloc: int = 10,
    physical_loc: int = 12,
    logical_loc: int = 8,
    functions: list[FunctionUnit] | None = None,
    classes: list[ClassUnit] | None = None,
    tokens: list[Token] | None = None,
    mi: float = 80.0,
    file_halstead: HalsteadReport | None = None,
) -> ParsedFile:
    return ParsedFile(
        path=Path(path),
        language=language,
        physical_loc=physical_loc,
        sloc=sloc,
        logical_loc=logical_loc,
        functions=functions or [],
        classes=classes or [],
        tokens=tokens or [],
        imports={},
        file_halstead=file_halstead or make_halstead(),
        maintainability_index=mi,
        errors=[],
    )
