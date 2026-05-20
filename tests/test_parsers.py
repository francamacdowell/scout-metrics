from __future__ import annotations

import textwrap
from pathlib import Path

from scout.parsers.base import Language
from scout.parsers.python_parser import parse


def _parse(source: str, filename: str = "test.py") -> object:
    return parse(Path(filename), textwrap.dedent(source))


def test_empty_file():
    pf = _parse("")
    assert pf.language == Language.PYTHON
    assert pf.functions == []
    assert pf.classes == []
    assert pf.errors == []
    assert pf.sloc == 0


def test_single_trivial_function():
    pf = _parse("""\
        def greet(name):
            return f"Hello, {name}"
    """)
    assert len(pf.functions) == 1
    fn = pf.functions[0]
    assert fn.name == "greet"
    assert fn.cyclomatic_complexity == 1
    assert fn.sloc >= 1


def test_function_with_branches():
    pf = _parse("""\
        def classify(x):
            if x > 0:
                return "positive"
            elif x < 0:
                return "negative"
            else:
                return "zero"
    """)
    fn = pf.functions[0]
    assert fn.cyclomatic_complexity >= 3  # if + elif + else


def test_class_with_methods():
    pf = _parse("""\
        class Counter:
            def __init__(self):
                self.count = 0

            def increment(self):
                self.count += 1

            def reset(self):
                self.count = 0
    """)
    assert len(pf.classes) == 1
    cls = pf.classes[0]
    assert cls.name == "Counter"
    method_names = {m.name for m in cls.methods}
    assert "__init__" in method_names
    assert "increment" in method_names
    assert "reset" in method_names


def test_syntax_error_captured():
    pf = _parse("def broken(\n    pass\n")
    assert len(pf.errors) >= 1
    assert pf.functions == []


def test_async_function():
    pf = _parse("""\
        async def fetch(url):
            return await get(url)
    """)
    assert len(pf.functions) == 1
    assert pf.functions[0].name == "fetch"


def test_nested_function_qualified_name():
    pf = _parse("""\
        def outer():
            def inner():
                pass
    """)
    names = {f.qualified_name for f in pf.functions}
    assert any("outer" in n for n in names)
    assert any("inner" in n for n in names)


def test_imports_captured():
    pf = _parse("""\
        import os
        from pathlib import Path
        from typing import List
    """)
    assert "os" in pf.imports
    assert "Path" in pf.imports  # imported name, not module name


def test_halstead_volume_positive():
    pf = _parse("""\
        def add(a, b):
            return a + b
    """)
    assert pf.file_halstead.volume > 0


def test_maintainability_index_range():
    pf = _parse("""\
        def simple():
            x = 1
            return x
    """)
    # MI is unbounded above 100 in radon but should be positive for simple code
    assert pf.maintainability_index > 0


def test_loc_counts():
    pf = _parse("""\
        # a comment
        def foo():
            x = 1  # inline comment

            return x
    """)
    assert pf.physical_loc >= 5
    assert pf.sloc >= 2


def test_class_fields_detected():
    pf = _parse("""\
        class Box:
            def __init__(self):
                self.width = 0
                self.height = 0
    """)
    cls = pf.classes[0]
    assert "width" in cls.fields or "self.width" in cls.fields


def test_match_statement_parses():
    pf = _parse(
        """\
        def handle(cmd):
            match cmd:
                case "quit":
                    return False
                case "go":
                    return True
                case _:
                    return None
    """,
        filename="test_match.py",
    )
    # Should parse without errors on Python 3.10+
    assert len(pf.functions) >= 1
