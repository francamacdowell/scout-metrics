from __future__ import annotations

import ast
import keyword
import tokenize as tokenize_mod
from io import StringIO
from pathlib import Path

from cognitive_complexity.api import get_cognitive_complexity
from radon.complexity import cc_visit
from radon.metrics import h_visit, mi_visit
from radon.raw import analyze

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

_KEYWORDS = frozenset(keyword.kwlist)


def parse(path: Path, source: str) -> ParsedFile:
    """Parse a Python source file into a ParsedFile. Never raises on syntax errors."""
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        return _empty(path, [ParseError(line=e.lineno or 0, message=str(e))])

    # Raw LOC metrics
    try:
        raw = analyze(source)
        physical_loc = raw.loc
        sloc = raw.sloc
        logical_loc = raw.lloc
    except Exception:
        lines = source.splitlines()
        physical_loc = len(lines)
        sloc = sum(1 for ln in lines if ln.strip() and not ln.strip().startswith("#"))
        logical_loc = sloc

    # MI
    try:
        mi_value = float(mi_visit(source, multi=True))
    except Exception:
        mi_value = 0.0

    # CC map: qualified_name → complexity
    cc_map: dict[str, int] = {}
    try:
        for r in cc_visit(source):
            qn = f"{r.classname}.{r.name}" if r.classname else r.name
            cc_map[qn] = r.complexity
    except Exception:
        pass

    # Halstead: file-level + per-function
    file_halstead: HalsteadReport | None = None
    h_map: dict[str, HalsteadReport] = {}
    try:
        h_result = h_visit(source)
        tot = h_result.total
        file_halstead = HalsteadReport(
            h1=int(tot.h1),
            h2=int(tot.h2),
            N1=int(tot.N1),
            N2=int(tot.N2),
            volume=float(tot.volume),
            difficulty=float(tot.difficulty),
            effort=float(tot.effort),
        )
        for name, hdata in h_result.functions:
            h_map[name] = HalsteadReport(
                h1=int(hdata.h1),
                h2=int(hdata.h2),
                N1=int(hdata.N1),
                N2=int(hdata.N2),
                volume=float(hdata.volume),
                difficulty=float(hdata.difficulty),
                effort=float(hdata.effort),
            )
    except Exception:
        pass

    # Tokens (whole-file, for duplication)
    tokens = _tokenize(source)

    # Imports map
    imports = _build_imports(tree)

    # Functions + classes from AST
    functions, classes = _build_structure(tree, source, tokens, cc_map, h_map, imports)

    return ParsedFile(
        path=path,
        language=Language.PYTHON,
        physical_loc=physical_loc,
        sloc=sloc,
        logical_loc=logical_loc,
        functions=functions,
        classes=classes,
        tokens=tokens,
        imports=imports,
        file_halstead=file_halstead,
        maintainability_index=mi_value,
        errors=[],
    )


def _empty(path: Path, errors: list[ParseError]) -> ParsedFile:
    return ParsedFile(
        path=path,
        language=Language.PYTHON,
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


def _tokenize(source: str) -> list[Token]:
    """Produce a normalized Token list from Python source."""
    tokens: list[Token] = []
    try:
        gen = tokenize_mod.generate_tokens(StringIO(source).readline)
        for tok_type, tok_string, (start_row, _), _, _ in gen:
            kind: str | None = None
            if tok_type == tokenize_mod.NAME:
                kind = "keyword" if tok_string in _KEYWORDS else "identifier"
            elif tok_type == tokenize_mod.OP:
                kind = "op"
            elif tok_type == tokenize_mod.NUMBER:
                kind = "number"
            elif tok_type == tokenize_mod.STRING:
                kind = "string"
            if kind is not None:
                tokens.append(Token(kind=kind, value=tok_string, line=start_row))
    except tokenize_mod.TokenError:
        pass
    return tokens


def _build_imports(tree: ast.Module) -> dict[str, str]:
    imports: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                imports[local] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue  # star imports excluded (§6.7)
                local = alias.asname or alias.name
                imports[local] = f"{module}.{alias.name}" if module else alias.name
    return imports


def _build_structure(
    tree: ast.Module,
    source: str,
    tokens: list[Token],
    cc_map: dict[str, int],
    h_map: dict[str, HalsteadReport],
    imports: dict[str, str],
) -> tuple[list[FunctionUnit], list[ClassUnit]]:
    source_lines = source.splitlines()
    functions: list[FunctionUnit] = []
    classes: list[ClassUnit] = []

    _collect_functions(tree, source_lines, tokens, cc_map, h_map, [], functions)
    _collect_classes(tree, source_lines, imports, classes)
    return functions, classes


def _collect_functions(
    node: ast.AST,
    source_lines: list[str],
    tokens: list[Token],
    cc_map: dict[str, int],
    h_map: dict[str, HalsteadReport],
    class_stack: list[str],
    out: list[FunctionUnit],
) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            _collect_functions(
                child, source_lines, tokens, cc_map, h_map, [*class_stack, child.name], out
            )
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _add_function(child, source_lines, tokens, cc_map, h_map, class_stack, out)
            # Recurse into nested functions (not into class bodies inside them - those are handled above)
            _collect_functions(child, source_lines, tokens, cc_map, h_map, class_stack, out)
        else:
            _collect_functions(child, source_lines, tokens, cc_map, h_map, class_stack, out)


def _add_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    source_lines: list[str],
    tokens: list[Token],
    cc_map: dict[str, int],
    h_map: dict[str, HalsteadReport],
    class_stack: list[str],
    out: list[FunctionUnit],
) -> None:
    name = node.name
    qn = ".".join([*class_stack, name]) if class_stack else name
    loc = SourceLocation(
        line_start=node.lineno,
        line_end=getattr(node, "end_lineno", node.lineno),
    )
    params = tuple(a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs)
    fn_tokens = [t for t in tokens if loc.line_start <= t.line <= loc.line_end]
    fn_lines = source_lines[node.lineno - 1 : getattr(node, "end_lineno", node.lineno)]
    sloc = sum(1 for ln in fn_lines if ln.strip() and not ln.strip().startswith("#"))

    cc = cc_map.get(qn) or cc_map.get(name) or 1
    try:
        cog = int(get_cognitive_complexity(node))
    except Exception:
        cog = 0

    halstead = h_map.get(qn) or h_map.get(name)
    branches = _collect_branches(node)

    out.append(
        FunctionUnit(
            name=name,
            qualified_name=qn,
            location=loc,
            params=params,
            branches=branches,
            tokens=fn_tokens,
            sloc=sloc,
            cyclomatic_complexity=cc,
            cognitive_score=cog,
            halstead=halstead,
        )
    )


def _collect_branches(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BranchNode]:
    branches: list[BranchNode] = []
    _walk_branches(func_node, 0, branches)
    return branches


def _walk_branches(node: ast.AST, depth: int, out: list[BranchNode]) -> None:
    """Recursive branch walker. depth tracks nesting level."""
    NESTING = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.If):
            loc = SourceLocation(
                line_start=child.lineno, line_end=getattr(child, "end_lineno", child.lineno)
            )
            out.append(BranchNode("if", depth, loc))
            _walk_branches(child.body[0] if child.body else child, depth + 1, out)
            if child.orelse:
                if len(child.orelse) == 1 and isinstance(child.orelse[0], ast.If):
                    # elif chain - don't add nesting
                    out.append(
                        BranchNode(
                            "elif",
                            depth,
                            SourceLocation(child.orelse[0].lineno, child.orelse[0].lineno),
                        )
                    )
                    _walk_branches(child.orelse[0], depth, out)
                else:
                    elif_loc = SourceLocation(
                        child.orelse[0].lineno if child.orelse else child.lineno, child.lineno
                    )
                    out.append(BranchNode("else", depth, elif_loc))
                    for n in child.orelse:
                        _walk_branches(n, depth + 1, out)
        elif isinstance(child, (ast.For, ast.AsyncFor)):
            loc = SourceLocation(
                line_start=child.lineno, line_end=getattr(child, "end_lineno", child.lineno)
            )
            out.append(BranchNode("for", depth, loc))
            for n in child.body:
                _walk_branches(n, depth + 1, out)
        elif isinstance(child, ast.While):
            loc = SourceLocation(
                line_start=child.lineno, line_end=getattr(child, "end_lineno", child.lineno)
            )
            out.append(BranchNode("while", depth, loc))
            for n in child.body:
                _walk_branches(n, depth + 1, out)
        elif isinstance(child, ast.ExceptHandler):
            loc = SourceLocation(
                line_start=child.lineno, line_end=getattr(child, "end_lineno", child.lineno)
            )
            out.append(BranchNode("catch", depth, loc))
            for n in child.body:
                _walk_branches(n, depth + 1, out)
        elif isinstance(child, ast.IfExp):
            loc = SourceLocation(line_start=child.lineno, line_end=child.lineno)
            out.append(BranchNode("ternary", depth, loc))
            _walk_branches(child, depth, out)
        elif isinstance(child, ast.BoolOp):
            loc = SourceLocation(line_start=child.lineno, line_end=child.lineno)
            kind = "boolop_and" if isinstance(child.op, ast.And) else "boolop_or"
            # Add one entry per extra operand beyond first
            for _ in range(len(child.values) - 1):
                out.append(BranchNode(kind, depth, loc))
            _walk_branches(child, depth, out)
        elif isinstance(child, ast.Match):
            for case in child.cases:
                line = case.body[0].lineno if case.body else child.lineno
                loc = SourceLocation(line_start=line, line_end=line)
                out.append(BranchNode("case", depth, loc))
                for n in case.body:
                    _walk_branches(n, depth + 1, out)
        elif isinstance(child, NESTING):
            _walk_branches(child, depth + 1, out)
        else:
            _walk_branches(child, depth, out)


# Python primitive/typing type allowlist for CBO
_PY_ALLOWLIST = frozenset(
    {
        "int",
        "float",
        "complex",
        "bool",
        "str",
        "bytes",
        "bytearray",
        "memoryview",
        "list",
        "tuple",
        "set",
        "frozenset",
        "dict",
        "range",
        "slice",
        "None",
        "NoneType",
        "Ellipsis",
        "NotImplemented",
        "object",
        "type",
        "Any",
        "Optional",
        "Union",
        "Tuple",
        "List",
        "Dict",
        "Set",
        "Callable",
        "Iterator",
        "Iterable",
        "Sequence",
        "Mapping",
        "ClassVar",
        "Final",
        "Literal",
        "TypeVar",
        "Generic",
        "Protocol",
        "overload",
        "cast",
        "TYPE_CHECKING",
        "NamedTuple",
        "TypedDict",
    }
)


def _collect_classes(
    tree: ast.Module,
    source_lines: list[str],
    imports: dict[str, str],
    out: list[ClassUnit],
    class_stack: list[str] | None = None,
) -> None:
    if class_stack is None:
        class_stack = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            qn = ".".join([*class_stack, node.name])
            loc = SourceLocation(
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", node.lineno),
            )
            fields = _collect_fields(node)
            methods = _collect_methods(node)
            imported_refs = _collect_cbo_refs(node, imports, node.name)
            out.append(
                ClassUnit(
                    name=node.name,
                    qualified_name=qn,
                    location=loc,
                    fields=fields,
                    methods=tuple(methods),
                    imported_class_refs=imported_refs,
                )
            )
            # Recurse for inner classes
            _collect_classes(node, source_lines, imports, out, [*class_stack, node.name])  # type: ignore[arg-type]


def _collect_fields(class_node: ast.ClassDef) -> frozenset[str]:
    """Collect field names from class-scope assignments and __init__ self.NAME assignments."""
    fields: set[str] = set()
    for node in ast.iter_child_nodes(class_node):
        # Class-scope: NAME = ...
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    fields.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            fields.add(node.target.id)
        # __init__ self.NAME = ...
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__init__":
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                        ):
                            fields.add(target.attr)
                elif (
                    isinstance(stmt, ast.AnnAssign)
                    and isinstance(stmt.target, ast.Attribute)
                    and isinstance(stmt.target.value, ast.Name)
                    and stmt.target.value.id == "self"
                ):
                    fields.add(stmt.target.attr)
    return frozenset(fields)


def _collect_methods(class_node: ast.ClassDef) -> list[MethodInfo]:
    methods: list[MethodInfo] = []
    for node in ast.iter_child_nodes(class_node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            loc = SourceLocation(
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", node.lineno),
            )
            # Determine self/cls parameter name
            self_names: set[str] = set()
            if node.args.args:
                self_names.add(node.args.args[0].arg)
            # Check for classmethod
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Name)
                    and dec.id == "classmethod"
                    and len(node.args.args) > 0
                ):
                    self_names.add(node.args.args[0].arg)

            refs: set[str] = set()
            calls: set[str] = set()
            for stmt in ast.walk(node):
                # self.NAME access (read or write)
                if (
                    isinstance(stmt, ast.Attribute)
                    and isinstance(stmt.value, ast.Name)
                    and stmt.value.id in self_names
                    and isinstance(stmt.ctx, (ast.Load, ast.Store))
                ):
                    refs.add(stmt.attr)
                # self.METHOD(...) call
                if isinstance(stmt, ast.Call):
                    func = stmt.func
                    if (
                        isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Name)
                        and func.value.id in self_names
                    ):
                        calls.add(func.attr)

            methods.append(
                MethodInfo(
                    name=node.name,
                    location=loc,
                    referenced_fields=frozenset(refs),
                    called_methods=frozenset(calls),
                )
            )
    return methods


def _collect_cbo_refs(
    class_node: ast.ClassDef,
    imports: dict[str, str],
    class_name: str,
) -> frozenset[str]:
    """Collect imported identifiers referenced inside the class body (for CBO)."""
    refs: set[str] = set()
    for node in ast.walk(class_node):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            name = node.id
            if name in imports and name not in _PY_ALLOWLIST and name != class_name:
                refs.add(name)
    return frozenset(refs)
