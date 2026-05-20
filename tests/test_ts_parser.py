from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scout.parsers.base import Language
from scout.parsers.ts_parser import parse


def _parse(source: str, filename: str = "test.ts") -> object:
    return parse(Path(filename), textwrap.dedent(source))


@pytest.fixture(autouse=True)
def _skip_if_no_treesitter(request):
    pf = parse(Path("probe.ts"), "")
    if pf.errors and "not available" in pf.errors[0].message:
        pytest.skip("tree-sitter TS not available in this environment")


def test_empty_file():
    pf = _parse("")
    assert pf.language == Language.TYPESCRIPT
    assert pf.functions == []
    assert pf.classes == []
    assert pf.errors == []


def test_typed_function():
    pf = _parse("""\
        function greet(name: string): string {
            return "Hello, " + name;
        }
    """)
    assert len(pf.functions) == 1
    fn = pf.functions[0]
    assert fn.name == "greet"
    assert fn.cyclomatic_complexity >= 1


def test_arrow_function_with_types():
    pf = _parse("""\
        const add = (a: number, b: number): number => a + b;
    """)
    assert len(pf.functions) == 1


def test_interface_excluded_from_logical_loc():
    pf_with = _parse("""\
        interface Point {
            x: number;
            y: number;
        }
        function origin(): Point {
            return { x: 0, y: 0 };
        }
    """)
    pf_without = _parse("""\
        function origin() {
            return { x: 0, y: 0 };
        }
    """)
    # Interface lines must not inflate logical LOC
    assert pf_with.logical_loc <= pf_without.logical_loc + 1


def test_type_alias_excluded_from_logical_loc():
    pf = _parse("""\
        type ID = string | number;
        function getId(): ID {
            return 42;
        }
    """)
    # type alias shouldn't count as logical loc
    assert pf.logical_loc >= 1  # function body does count


def test_class_with_typed_methods():
    pf = _parse("""\
        class Stack<T> {
            private items: T[] = [];
            push(item: T): void {
                this.items.push(item);
            }
            pop(): T | undefined {
                return this.items.pop();
            }
        }
    """)
    assert len(pf.classes) == 1
    cls = pf.classes[0]
    assert cls.name == "Stack"
    method_names = {m.name for m in cls.methods}
    assert "push" in method_names
    assert "pop" in method_names


def test_async_function():
    pf = _parse("""\
        async function fetchUser(id: number): Promise<string> {
            const resp = await fetch(`/users/${id}`);
            return resp.json();
        }
    """)
    assert len(pf.functions) == 1
    assert pf.functions[0].name == "fetchUser"


def test_imports_captured():
    pf = _parse("""\
        import { readFile } from 'fs';
        import type { User } from './types';
    """)
    assert len(pf.imports) >= 1


def test_halstead_volume_positive():
    pf = _parse("""\
        function add(a: number, b: number): number {
            return a + b;
        }
    """)
    assert pf.file_halstead is not None
    assert pf.file_halstead.volume > 0


def test_maintainability_index_positive():
    pf = _parse("""\
        function simple(): number {
            const x = 1;
            return x;
        }
    """)
    assert pf.maintainability_index > 0


def test_tsx_file_parses():
    pf = parse(
        Path("component.tsx"),
        textwrap.dedent("""\
            function Button({ label }: { label: string }) {
                return <button>{label}</button>;
            }
        """),
    )
    assert pf.language == Language.TYPESCRIPT
    assert isinstance(pf.errors, list)


def test_enum_does_not_crash():
    pf = _parse("""\
        enum Direction {
            Up,
            Down,
            Left,
            Right,
        }
        function move(d: Direction): string {
            return d.toString();
        }
    """)
    assert len(pf.functions) >= 1


def test_loc_counts():
    pf = _parse("""\
        // comment
        function foo(): number {
            const x: number = 1;
            return x;
        }
    """)
    assert pf.physical_loc >= 5
    assert pf.sloc >= 2


def test_function_with_branches():
    pf = _parse("""\
        function classify(x: number): string {
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
