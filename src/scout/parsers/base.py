from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Language(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"


@dataclass(slots=True, frozen=True)
class SourceLocation:
    line_start: int  # 1-indexed
    line_end: int  # inclusive
    col_start: int = 0
    col_end: int = 0


@dataclass(slots=True, frozen=True)
class Token:
    kind: str  # normalized kind: keyword, identifier, op, number, string, regex, punct
    value: str  # raw text (identifiers are sys.intern'd)
    line: int

    def __post_init__(self) -> None:
        if self.kind == "identifier":
            object.__setattr__(self, "value", sys.intern(self.value))


@dataclass(slots=True)
class BranchNode:
    """One control-flow branching point inside a function."""

    kind: str  # if, elif, else, for, while, case, catch, ternary,
    # boolop_and, boolop_or, boolop_nullish, optional_chain
    nesting_depth: int  # 0 at top of function; +1 per containing branch
    location: SourceLocation


@dataclass(slots=True)
class HalsteadReport:
    h1: int  # distinct operators
    h2: int  # distinct operands
    N1: int  # total operators
    N2: int  # total operands
    volume: float
    difficulty: float
    effort: float


@dataclass(slots=True)
class FunctionUnit:
    name: str  # "" for anonymous lambdas/arrow functions
    qualified_name: str  # e.g. "ClassName.method" or "module.func"
    location: SourceLocation
    params: tuple[str, ...]
    branches: list[BranchNode]
    tokens: list[Token]  # tokens inside the function body
    sloc: int
    cyclomatic_complexity: int
    cognitive_score: int
    halstead: HalsteadReport | None  # None if empty body


@dataclass(slots=True)
class MethodInfo:
    name: str
    location: SourceLocation
    referenced_fields: frozenset[str]  # self.foo / this.foo references
    called_methods: frozenset[str]  # self.bar() / this.bar() references


@dataclass(slots=True)
class ClassUnit:
    name: str
    qualified_name: str
    location: SourceLocation
    fields: frozenset[str]  # statically declared field names
    methods: tuple[MethodInfo, ...]
    imported_class_refs: frozenset[str]  # external class names referenced in the class


@dataclass(slots=True)
class ParseError:
    line: int
    message: str


@dataclass(slots=True)
class ParsedFile:
    path: Path
    language: Language
    physical_loc: int
    sloc: int
    logical_loc: int
    functions: list[FunctionUnit]
    classes: list[ClassUnit]
    tokens: list[Token]  # full file token stream (for duplication)
    imports: dict[str, str]  # local_name -> source_module
    file_halstead: HalsteadReport | None
    maintainability_index: float  # 0-100 (Microsoft variant)
    errors: list[ParseError]
