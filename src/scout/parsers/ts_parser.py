from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from scout.parsers.base import (
    ClassUnit,
    FunctionUnit,
    Language,
    ParsedFile,
    ParseError,
)
from scout.parsers.js_parser import (
    _CLASS_KINDS,
    _FN_KINDS,
    _STATEMENT_KINDS,
    _build_class,
    _build_function,
    _extract_imports,
    _extract_tokens,
    _halstead_from_tokens,
    _mi,
    _walk_all,
)

log = logging.getLogger("scout.parser")

# TS-only node types to exclude from logical LOC, CC, Cognitive
_TS_TYPE_ONLY_KINDS = frozenset(
    {
        "interface_declaration",
        "type_alias_declaration",
        "ambient_declaration",
        "abstract_class_declaration",
    }
)

_ts_parser_ts: Any = None
_ts_parser_tsx: Any = None
_ts_language_ts: Any = None
_ts_language_tsx: Any = None


def _init_ts_parser() -> None:
    global _ts_parser_ts, _ts_parser_tsx, _ts_language_ts, _ts_language_tsx
    if _ts_parser_ts is not None:
        return
    try:
        import tree_sitter_typescript as tsts
        from tree_sitter import Language as TSLanguage
        from tree_sitter import Parser as TSParser

        _ts_language_ts = TSLanguage(tsts.language_typescript())
        _ts_parser_ts = TSParser(_ts_language_ts)

        _ts_language_tsx = TSLanguage(tsts.language_tsx())
        _ts_parser_tsx = TSParser(_ts_language_tsx)
    except Exception as exc:
        log.warning("tree-sitter TS unavailable: %s", exc)
        _ts_parser_ts = None


def parse(path: Path, source: str) -> ParsedFile:
    _init_ts_parser()

    is_tsx = path.suffix.lower() == ".tsx"
    ts_parser = _ts_parser_tsx if is_tsx else _ts_parser_ts

    if ts_parser is None:
        return _ts_empty(path, [ParseError(line=0, message="tree-sitter TS not available")])

    try:
        import lizard

        liz = lizard.analyze_file.analyze_source_code(str(path), source)
    except Exception as exc:
        return _ts_empty(path, [ParseError(line=0, message=f"lizard error: {exc}")])

    try:
        tree = ts_parser.parse(source.encode("utf-8"))
    except Exception as exc:
        return _ts_empty(path, [ParseError(line=0, message=f"tree-sitter parse error: {exc}")])

    root = tree.root_node

    # LOC — TS type-only declarations count for physical/sloc but not logical
    physical_loc = len(source.split("\n"))
    sloc = liz.nloc
    logical_loc = sum(
        1
        for node in _walk_all(root)
        if node.type in _STATEMENT_KINDS and node.type not in _TS_TYPE_ONLY_KINDS
    )

    tokens = _extract_tokens(root)
    imports = _extract_imports(root, source)

    cc_map: dict[str, int] = {fn.name: fn.cyclomatic_complexity for fn in liz.function_list}
    nloc_map: dict[str, int] = {fn.name: fn.nloc for fn in liz.function_list}

    functions: list[FunctionUnit] = []
    classes: list[ClassUnit] = []
    _walk_ts_declarations(root, source, tokens, cc_map, nloc_map, imports, functions, classes, [])

    errors = [
        ParseError(
            line=node.start_point[0] + 1,
            message=f"Syntax error near {source[node.start_byte : node.end_byte][:40]!r}",
        )
        for node in _walk_all(root)
        if node.type == "ERROR"
    ]

    file_halstead = _halstead_from_tokens(tokens)
    total_vol = sum(fn.halstead.volume for fn in functions if fn.halstead) or file_halstead.volume
    total_cc = sum(fn.cyclomatic_complexity for fn in functions) or 1
    mi_value = _mi(sloc, total_vol, total_cc)

    return ParsedFile(
        path=path,
        language=Language.TYPESCRIPT,
        physical_loc=physical_loc,
        sloc=sloc,
        logical_loc=logical_loc,
        functions=functions,
        classes=classes,
        tokens=tokens,
        imports=imports,
        file_halstead=file_halstead,
        maintainability_index=mi_value,
        errors=errors,
    )


def _ts_empty(path: Path, errors: list[ParseError]) -> ParsedFile:
    return ParsedFile(
        path=path,
        language=Language.TYPESCRIPT,
        physical_loc=0,
        sloc=0,
        logical_loc=0,
        functions=[],
        classes=[],
        tokens=[],
        imports={},
        file_halstead=None,
        maintainability_index=0.0,
        errors=errors,
    )


def _walk_ts_declarations(
    node: Any,
    source: str,
    all_tokens: list[Any],
    cc_map: dict[str, int],
    nloc_map: dict[str, int],
    imports: dict[str, str],
    fns: list[Any],
    classes: list[Any],
    class_stack: list[str],
) -> None:
    for child in node.children:
        if child.type in _TS_TYPE_ONLY_KINDS:
            continue  # skip type-only declarations
        if child.type in _FN_KINDS:
            fn = _build_function(child, source, all_tokens, cc_map, nloc_map, class_stack)
            if fn:
                fns.append(fn)
                _walk_ts_declarations(
                    child, source, all_tokens, cc_map, nloc_map, imports, fns, classes, class_stack
                )
        elif child.type in _CLASS_KINDS:
            cls = _build_class(child, source, imports, class_stack)
            classes.append(cls)
            _walk_ts_declarations(
                child,
                source,
                all_tokens,
                cc_map,
                nloc_map,
                imports,
                fns,
                classes,
                [*class_stack, cls.name],
            )
        else:
            _walk_ts_declarations(
                child, source, all_tokens, cc_map, nloc_map, imports, fns, classes, class_stack
            )
