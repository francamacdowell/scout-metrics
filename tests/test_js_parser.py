from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scout.parsers.base import Language
from scout.parsers.js_parser import parse


def _parse(source: str, filename: str = "test.js") -> object:
    return parse(Path(filename), textwrap.dedent(source))


@pytest.fixture(autouse=True)
def _skip_if_no_treesitter(request):
    pf = parse(Path("probe.js"), "")
    if pf.errors and "not available" in pf.errors[0].message:
        pytest.skip("tree-sitter JS not available in this environment")


def test_empty_file():
    pf = _parse("")
    assert pf.language == Language.JAVASCRIPT
    assert pf.functions == []
    assert pf.classes == []
    assert pf.errors == []


def test_single_function():
    pf = _parse("""\
        function greet(name) {
            return "Hello, " + name;
        }
    """)
    assert len(pf.functions) == 1
    fn = pf.functions[0]
    assert fn.name == "greet"
    assert fn.cyclomatic_complexity >= 1


def test_arrow_function():
    pf = _parse("""\
        const add = (a, b) => a + b;
    """)
    assert len(pf.functions) == 1


def test_function_with_branches():
    pf = _parse("""\
        function classify(x) {
            if (x > 0) {
                return "positive";
            } else if (x < 0) {
                return "negative";
            } else {
                return "zero";
            }
        }
    """)
    fn = pf.functions[0]
    assert fn.cyclomatic_complexity >= 2


def test_async_function():
    pf = _parse("""\
        async function fetchData(url) {
            const resp = await fetch(url);
            return resp.json();
        }
    """)
    assert len(pf.functions) == 1
    assert pf.functions[0].name == "fetchData"


def test_class_with_methods():
    pf = _parse("""\
        class Counter {
            constructor() {
                this.count = 0;
            }
            increment() {
                this.count += 1;
            }
            reset() {
                this.count = 0;
            }
        }
    """)
    assert len(pf.classes) == 1
    cls = pf.classes[0]
    assert cls.name == "Counter"
    method_names = {m.name for m in cls.methods}
    assert "increment" in method_names
    assert "reset" in method_names


def test_imports_captured():
    pf = _parse("""\
        import { readFile } from 'fs';
        import path from 'path';
    """)
    assert len(pf.imports) >= 1


def test_loc_counts():
    pf = _parse("""\
        // a comment
        function foo() {
            const x = 1;
            return x;
        }
    """)
    assert pf.physical_loc >= 5
    assert pf.sloc >= 2


def test_halstead_volume_positive():
    pf = _parse("""\
        function add(a, b) {
            return a + b;
        }
    """)
    assert pf.file_halstead is not None
    assert pf.file_halstead.volume > 0


def test_maintainability_index_positive():
    pf = _parse("""\
        function simple() {
            const x = 1;
            return x;
        }
    """)
    assert pf.maintainability_index > 0


def test_tokens_extracted():
    pf = _parse("""\
        function foo(x) {
            return x * 2;
        }
    """)
    assert len(pf.tokens) > 0
    kinds = {t.kind for t in pf.tokens}
    assert "identifier" in kinds or "keyword" in kinds


def test_error_node_tolerance():
    # Partial/broken syntax — should not crash, errors list may be non-empty
    pf = _parse("function broken( { return 1; }")
    assert isinstance(pf.errors, list)
    assert pf.language == Language.JAVASCRIPT


def test_nested_function():
    pf = _parse("""\
        function outer() {
            function inner() {
                return 1;
            }
            return inner();
        }
    """)
    names = {f.name for f in pf.functions}
    assert "outer" in names or "inner" in names


def test_logical_loc_counted():
    pf = _parse("""\
        function foo() {
            const x = 1;
            const y = 2;
            return x + y;
        }
    """)
    assert pf.logical_loc >= 1


def test_for_loop_branches():
    pf = _parse("""\
        function sumList(arr) {
            let total = 0;
            for (let i = 0; i < arr.length; i++) {
                total += arr[i];
            }
            return total;
        }
    """)
    fn = pf.functions[0]
    assert fn.cyclomatic_complexity >= 2


def test_cognitive_score_nested_control_flow():
    pf = _parse("""\
        function process(items) {
            for (const item of items) {
                if (item > 0) {
                    if (item > 10) {
                        return item;
                    }
                }
            }
        }
    """)
    fn = pf.functions[0]
    assert fn.cognitive_score >= 3
