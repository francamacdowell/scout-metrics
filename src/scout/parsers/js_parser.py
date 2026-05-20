from __future__ import annotations

import logging
from collections.abc import Generator
from math import log2
from pathlib import Path
from typing import Any

from scout.parsers.base import (
    BranchNode,
    ClassUnit,
    FunctionUnit,
    HalsteadReport,
    Language,
    MethodInfo,
    ParsedFile,
    ParseError,
    SourceLocation,
    Token,
)

log = logging.getLogger("scout.parser")

# Lazy module-level state — initialised once per process
_parser: Any = None
_language: Any = None

_JS_KEYWORDS = frozenset(
    {
        "if",
        "else",
        "for",
        "while",
        "do",
        "switch",
        "case",
        "break",
        "continue",
        "return",
        "function",
        "class",
        "extends",
        "new",
        "this",
        "typeof",
        "instanceof",
        "in",
        "of",
        "delete",
        "void",
        "throw",
        "try",
        "catch",
        "finally",
        "import",
        "export",
        "from",
        "as",
        "async",
        "await",
        "yield",
        "let",
        "const",
        "var",
        "null",
        "undefined",
        "true",
        "false",
        "default",
        "static",
        "get",
        "set",
        "super",
        "with",
        "debugger",
    }
)
_JS_OPS = frozenset(
    {
        "+",
        "-",
        "*",
        "/",
        "%",
        "**",
        "=",
        "+=",
        "-=",
        "*=",
        "/=",
        "%=",
        "**=",
        "==",
        "===",
        "!=",
        "!==",
        "<",
        ">",
        "<=",
        ">=",
        "&&",
        "||",
        "??",
        "!",
        "~",
        "&",
        "|",
        "^",
        "<<",
        ">>",
        ">>>",
        "++",
        "--",
        "=>",
        "...",
        "?.",
        "?:",
    }
)
_JS_PUNCT = frozenset({"(", ")", "{", "}", "[", "]", ",", ";", ":", "."})

_NESTING_INCREMENTS = frozenset(
    {
        "if_statement",
        "for_statement",
        "for_in_statement",
        "for_of_statement",
        "while_statement",
        "do_statement",
        "switch_statement",
        "catch_clause",
        "ternary_expression",
    }
)
_BARE_INCREMENTS = frozenset({"else_clause"})

_STATEMENT_KINDS = frozenset(
    {
        "expression_statement",
        "variable_declaration",
        "lexical_declaration",
        "return_statement",
        "throw_statement",
        "if_statement",
        "for_statement",
        "for_in_statement",
        "for_of_statement",
        "while_statement",
        "do_statement",
        "switch_statement",
        "try_statement",
        "break_statement",
        "continue_statement",
        "labeled_statement",
        "import_statement",
        "export_statement",
        "function_declaration",
        "class_declaration",
    }
)


def _init_parser() -> None:
    global _parser, _language
    if _parser is not None:
        return
    try:
        import tree_sitter_javascript as tsjava
        from tree_sitter import Language as TSLanguage
        from tree_sitter import Parser as TSParser

        _language = TSLanguage(tsjava.language())
        _parser = TSParser(_language)
    except Exception as exc:
        log.warning("tree-sitter JS unavailable: %s", exc)
        _parser = None


def parse(path: Path, source: str) -> ParsedFile:
    _init_parser()
    if _parser is None:
        return _empty(path, [ParseError(line=0, message="tree-sitter JS not available")])

    try:
        import lizard

        liz = lizard.analyze_file.analyze_source_code(str(path), source)
    except Exception as exc:
        return _empty(path, [ParseError(line=0, message=f"lizard error: {exc}")])

    try:
        tree = _parser.parse(source.encode("utf-8"))
    except Exception as exc:
        return _empty(path, [ParseError(line=0, message=f"tree-sitter parse error: {exc}")])

    root = tree.root_node

    # LOC
    lines = source.split("\n")
    physical_loc = len(lines)
    sloc = liz.nloc
    logical_loc = sum(
        1
        for node in _walk_all(root)
        if (node.type in _STATEMENT_KINDS and not node.children) or node.type in _STATEMENT_KINDS
    )
    # Simpler logical LOC: count statement-class nodes
    logical_loc = sum(1 for node in _walk_all(root) if node.type in _STATEMENT_KINDS)

    # Tokens
    tokens = _extract_tokens(root)

    # Build CC map from lizard
    cc_map: dict[str, int] = {}
    nloc_map: dict[str, int] = {}
    for fn in liz.function_list:
        cc_map[fn.name] = fn.cyclomatic_complexity
        nloc_map[fn.name] = fn.nloc

    # Imports
    imports = _extract_imports(root, source)

    # Functions + classes
    functions: list[FunctionUnit] = []
    classes: list[ClassUnit] = []
    _walk_declarations(root, source, tokens, cc_map, nloc_map, imports, functions, classes, [])

    # Parse errors from ERROR nodes
    errors: list[ParseError] = [
        ParseError(
            line=node.start_point[0] + 1,
            message=f"Syntax error near {_node_text(node, source)!r}",
        )
        for node in _walk_all(root)
        if node.type == "ERROR"
    ]

    # File-level Halstead
    file_halstead = _halstead_from_tokens(tokens)

    # MI
    total_vol = sum(fn.halstead.volume for fn in functions if fn.halstead) or file_halstead.volume
    total_cc = sum(fn.cyclomatic_complexity for fn in functions) or 1
    mi_value = _mi(sloc, total_vol, total_cc)

    return ParsedFile(
        path=path,
        language=Language.JAVASCRIPT,
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


def _empty(path: Path, errors: list[ParseError]) -> ParsedFile:
    return ParsedFile(
        path=path,
        language=Language.JAVASCRIPT,
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


def _walk_all(node: Any) -> Generator[Any, None, None]:
    yield node
    for child in node.children:
        yield from _walk_all(child)


def _node_text(node: Any, source: str) -> str:
    try:
        return source[node.start_byte : node.end_byte][:40]
    except Exception:
        return ""


def _extract_tokens(root: Any) -> list[Token]:
    tokens: list[Token] = []
    for node in _walk_all(root):
        if node.child_count > 0:
            continue  # skip non-leaf nodes
        text = node.text.decode("utf-8", errors="replace") if node.text else ""
        kind = _token_kind(node.type, text)
        if kind:
            tokens.append(Token(kind=kind, value=text, line=node.start_point[0] + 1))
    return tokens


def _token_kind(node_type: str, text: str) -> str | None:
    if node_type == "identifier":
        if text in _JS_KEYWORDS:
            return "keyword"
        return "identifier"
    if node_type in {"string", "template_string", "template_literal"}:
        return "string"
    if node_type in {"number", "decimal_integer_literal"}:
        return "number"
    if node_type == "regex":
        return "regex"
    if text in _JS_KEYWORDS:
        return "keyword"
    if text in _JS_OPS:
        return "op"
    if text in _JS_PUNCT:
        return "punct"
    if node_type == "comment":
        return None  # excluded
    return None


def _extract_imports(root: Any, source: str) -> dict[str, str]:
    imports: dict[str, str] = {}
    for node in _walk_all(root):
        if node.type == "import_statement":
            src = _find_string_source(node, source)
            if src:
                for child in _walk_all(node):
                    if (
                        child.type == "identifier"
                        and child.parent
                        and child.parent.type != "import_statement"
                    ):
                        imports[_node_text(child, source)] = src
    return imports


def _find_string_source(node: Any, source: str) -> str:
    for child in _walk_all(node):
        if child.type == "string":
            raw = _node_text(child, source)
            return raw.strip("'\"")
    return ""


_FN_KINDS = frozenset(
    {
        "function_declaration",
        "function_expression",
        "arrow_function",
        "method_definition",
        "generator_function_declaration",
        "generator_function",
    }
)
_CLASS_KINDS = frozenset({"class_declaration", "class_expression"})


def _walk_declarations(
    node: Any,
    source: str,
    all_tokens: list[Token],
    cc_map: dict[str, int],
    nloc_map: dict[str, int],
    imports: dict[str, str],
    fns: list[FunctionUnit],
    classes: list[ClassUnit],
    class_stack: list[str],
) -> None:
    for child in node.children:
        if child.type in _FN_KINDS:
            fn = _build_function(child, source, all_tokens, cc_map, nloc_map, class_stack)
            if fn:
                fns.append(fn)
                _walk_declarations(
                    child, source, all_tokens, cc_map, nloc_map, imports, fns, classes, class_stack
                )
        elif child.type in _CLASS_KINDS:
            cls = _build_class(child, source, imports, class_stack)
            classes.append(cls)
            _walk_declarations(
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
            _walk_declarations(
                child, source, all_tokens, cc_map, nloc_map, imports, fns, classes, class_stack
            )


def _build_function(
    node: Any,
    source: str,
    all_tokens: list[Token],
    cc_map: dict[str, int],
    nloc_map: dict[str, int],
    class_stack: list[str],
) -> FunctionUnit | None:
    name = ""
    # Find name
    for child in node.children:
        if child.type in {"identifier", "property_identifier"}:
            name = _node_text(child, source)
            break
    qn = ".".join([*class_stack, name]) if (class_stack and name) else name

    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    loc = SourceLocation(line_start=start_line, line_end=end_line)

    fn_tokens = [t for t in all_tokens if start_line <= t.line <= end_line]
    fn_sloc = nloc_map.get(name) or nloc_map.get(qn) or max(end_line - start_line, 1)
    cc = cc_map.get(name) or cc_map.get(qn) or 1
    cog = _cognitive_score(node)
    halstead = _halstead_from_tokens(fn_tokens)
    branches = _collect_branches(node)

    params: list[str] = []
    for child in node.children:
        if child.type == "formal_parameters":
            for p in child.children:
                if p.type in {"identifier", "rest_pattern"}:
                    params.append(_node_text(p, source))

    return FunctionUnit(
        name=name,
        qualified_name=qn,
        location=loc,
        params=tuple(params),
        branches=branches,
        tokens=fn_tokens,
        sloc=fn_sloc,
        cyclomatic_complexity=cc,
        cognitive_score=cog,
        halstead=halstead if (halstead.N1 + halstead.N2 > 0) else None,
    )


def _build_class(
    node: Any, source: str, imports: dict[str, str], class_stack: list[str]
) -> ClassUnit:
    name = ""
    for child in node.children:
        if child.type in {"identifier", "type_identifier"}:
            name = _node_text(child, source)
            break
    qn = ".".join([*class_stack, name]) if (class_stack and name) else name
    loc = SourceLocation(line_start=node.start_point[0] + 1, line_end=node.end_point[0] + 1)

    methods: list[MethodInfo] = []
    fields: set[str] = set()
    for child in _walk_all(node):
        if child.type == "method_definition":
            m = _build_method_info(child, source)
            if m:
                methods.append(m)
        elif child.type == "field_definition":
            for fc in child.children:
                if fc.type == "property_identifier":
                    fields.add(_node_text(fc, source))

    imported_refs = _collect_cbo_refs(node, source, imports, name)

    return ClassUnit(
        name=name,
        qualified_name=qn,
        location=loc,
        fields=frozenset(fields),
        methods=tuple(methods),
        imported_class_refs=imported_refs,
    )


def _build_method_info(node: Any, source: str) -> MethodInfo | None:
    name = ""
    for child in node.children:
        if child.type == "property_identifier":
            name = _node_text(child, source)
            break
    if not name:
        return None
    loc = SourceLocation(line_start=node.start_point[0] + 1, line_end=node.end_point[0] + 1)

    refs: set[str] = set()
    calls: set[str] = set()
    for child in _walk_all(node):
        if child.type == "member_expression":
            obj = child.children[0] if child.children else None
            prop = child.children[-1] if len(child.children) > 1 else None
            if obj and _node_text(obj, source) == "this" and prop:
                prop_name = _node_text(prop, source)
                # Check if it's a call
                parent = child.parent
                if parent and parent.type == "call_expression":
                    calls.add(prop_name)
                else:
                    refs.add(prop_name)
    return MethodInfo(
        name=name, location=loc, referenced_fields=frozenset(refs), called_methods=frozenset(calls)
    )


_JS_ALLOWLIST = frozenset(
    {
        "Array",
        "Object",
        "String",
        "Number",
        "Boolean",
        "Symbol",
        "BigInt",
        "Date",
        "RegExp",
        "Error",
        "TypeError",
        "RangeError",
        "SyntaxError",
        "Promise",
        "Map",
        "Set",
        "WeakMap",
        "WeakSet",
        "Proxy",
        "Reflect",
        "JSON",
        "Math",
        "console",
        "undefined",
        "null",
        "NaN",
        "Infinity",
    }
)


def _collect_cbo_refs(
    node: Any, source: str, imports: dict[str, str], class_name: str
) -> frozenset[str]:
    refs: set[str] = set()
    for child in _walk_all(node):
        if child.type == "identifier":
            name = _node_text(child, source)
            if name in imports and name not in _JS_ALLOWLIST and name != class_name:
                refs.add(name)
    return frozenset(refs)


def _collect_branches(node: Any) -> list[BranchNode]:
    branches: list[BranchNode] = []
    _walk_branches(node, 0, branches)
    return branches


def _walk_branches(node: Any, depth: int, out: list[BranchNode]) -> None:
    for child in node.children:
        kind = child.type
        if kind in _NESTING_INCREMENTS:
            loc = SourceLocation(child.start_point[0] + 1, child.end_point[0] + 1)
            out.append(BranchNode(kind, depth, loc))
            _walk_branches(child, depth + 1, out)
        elif kind in _BARE_INCREMENTS:
            loc = SourceLocation(child.start_point[0] + 1, child.end_point[0] + 1)
            out.append(BranchNode(kind, depth, loc))
            _walk_branches(child, depth, out)
        else:
            _walk_branches(child, depth, out)


def _cognitive_score(fn_node: Any, depth: int = 0) -> int:
    score = 0
    for child in fn_node.children:
        kind = child.type
        if kind in _NESTING_INCREMENTS:
            score += 1 + depth
            score += _cognitive_score(child, depth + 1)
        elif kind in _BARE_INCREMENTS:
            score += 1
            score += _cognitive_score(child, depth)
        elif kind == "binary_expression" and _is_boolean_expr(child):
            score += _boolean_expr_cost(child)
            score += _cognitive_score(child, depth)
        else:
            score += _cognitive_score(child, depth)
    return score


def _is_boolean_expr(node: Any) -> bool:
    return any(child.type in {"&&", "||", "??"} for child in node.children)


def _boolean_expr_cost(node: Any) -> int:
    import itertools

    ops = [child.type for child in node.children if child.type in {"&&", "||", "??"}]
    if not ops:
        return 0
    cost = 1
    for prev, curr in itertools.pairwise(ops):
        if prev != curr:
            cost += 1
    return cost


def _halstead_from_tokens(tokens: list[Token]) -> HalsteadReport:
    operators = [t for t in tokens if t.kind in {"op", "keyword", "punct"}]
    operands = [t for t in tokens if t.kind in {"identifier", "number", "string", "regex"}]
    n1 = len({(t.kind, t.value) for t in operators})
    n2 = len({(t.kind, t.value) for t in operands})
    N1, N2 = len(operators), len(operands)
    n, N = n1 + n2, N1 + N2
    V = N * log2(n) if n > 0 else 0.0
    D = (n1 / 2) * (N2 / n2) if n2 > 0 else 0.0
    E = D * V
    return HalsteadReport(h1=n1, h2=n2, N1=N1, N2=N2, volume=V, difficulty=D, effort=E)


def _mi(sloc: int, volume: float, cc: int) -> float:
    from math import log

    V = max(volume, 1.0)
    LOC = max(sloc, 1)
    raw = 171 - 5.2 * log(V) - 0.23 * cc - 16.2 * log(LOC)
    return max(0.0, min(100.0, raw * 100 / 171))
