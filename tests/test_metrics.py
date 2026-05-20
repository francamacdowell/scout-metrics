from __future__ import annotations

from pathlib import Path

from scout.config import ScoutConfig
from scout.metrics import base as mb
from scout.metrics import cbo, cc, cognitive, duplication, halstead, lcom, loc, mi
from scout.metrics.base import MetricConfig
from scout.parsers.base import Language, Token
from tests.conftest import (
    make_class,
    make_function,
    make_halstead,
    make_method,
    make_parsed_file,
)


def _cfg(tmp_path, overrides=None):

    return ScoutConfig.load(Path(tmp_path), overrides or {})


# ---------------------------------------------------------------------------
# LOC
# ---------------------------------------------------------------------------


class TestLOC:
    def test_physical_emitted(self, tmp_path):
        pf = make_parsed_file(sloc=10, physical_loc=15, logical_loc=8)
        results = loc.compute(pf, _cfg(tmp_path))
        ids = {mv.metric_id for mv in results}
        assert "loc.physical" in ids
        assert "loc.sloc" in ids

    def test_sloc_violation(self, tmp_path):
        pf = make_parsed_file(sloc=600, physical_loc=700, logical_loc=500)
        cfg = _cfg(tmp_path, {"thresholds": {"loc": 500}})
        results = loc.compute(pf, cfg)
        sloc_mv = next(mv for mv in results if mv.metric_id == "loc.sloc")
        assert sloc_mv.value == 600
        assert sloc_mv.severity in (mb.Severity.WARN, mb.Severity.ERROR)

    def test_ok_sloc(self, tmp_path):
        pf = make_parsed_file(sloc=100)
        results = loc.compute(pf, _cfg(tmp_path))
        sloc_mv = next(mv for mv in results if mv.metric_id == "loc.sloc")
        assert sloc_mv.severity == mb.Severity.OK


# ---------------------------------------------------------------------------
# CC
# ---------------------------------------------------------------------------


class TestCC:
    def test_trivial_function_cc_one(self, tmp_path):
        fn = make_function(cc=1)
        pf = make_parsed_file(functions=[fn])
        results = cc.compute(pf, _cfg(tmp_path))
        assert len(results) == 1
        assert results[0].value == 1
        assert results[0].severity == mb.Severity.OK

    def test_high_cc_is_warn(self, tmp_path):
        fn = make_function(cc=12)
        pf = make_parsed_file(functions=[fn])
        results = cc.compute(pf, _cfg(tmp_path))
        assert results[0].severity in (mb.Severity.WARN, mb.Severity.ERROR)

    def test_very_high_cc_is_error(self, tmp_path):
        fn = make_function(cc=25)
        pf = make_parsed_file(functions=[fn])
        results = cc.compute(pf, _cfg(tmp_path))
        assert results[0].severity == mb.Severity.ERROR

    def test_empty_file_no_results(self, tmp_path):
        pf = make_parsed_file(functions=[])
        results = cc.compute(pf, _cfg(tmp_path))
        assert results == []


# ---------------------------------------------------------------------------
# Cognitive
# ---------------------------------------------------------------------------


class TestCognitive:
    def test_zero_cognitive_ok(self, tmp_path):
        fn = make_function(cog=0)
        pf = make_parsed_file(functions=[fn])
        results = cognitive.compute(pf, _cfg(tmp_path))
        assert results[0].value == 0
        assert results[0].severity == mb.Severity.OK

    def test_high_cognitive_warn(self, tmp_path):
        fn = make_function(cog=18)
        pf = make_parsed_file(functions=[fn])
        results = cognitive.compute(pf, _cfg(tmp_path))
        assert results[0].severity in (mb.Severity.WARN, mb.Severity.ERROR)

    def test_symbol_is_function_name(self, tmp_path):
        fn = make_function(name="complex_fn", cog=5)
        pf = make_parsed_file(functions=[fn])
        results = cognitive.compute(pf, _cfg(tmp_path))
        assert results[0].symbol == "complex_fn"


# ---------------------------------------------------------------------------
# Halstead
# ---------------------------------------------------------------------------


class TestHalstead:
    def test_volume_emitted(self, tmp_path):
        fn = make_function(halstead=make_halstead(v=100.0, d=5.0))
        pf = make_parsed_file(functions=[fn])
        results = halstead.compute(pf, _cfg(tmp_path))
        ids = {mv.metric_id for mv in results}
        assert "halstead.volume" in ids
        assert "halstead.difficulty" in ids

    def test_file_scope_emitted(self, tmp_path):
        pf = make_parsed_file(file_halstead=make_halstead(v=200.0, d=10.0))
        results = halstead.compute(pf, _cfg(tmp_path))
        file_results = [mv for mv in results if mv.scope == "file"]
        assert len(file_results) >= 1


# ---------------------------------------------------------------------------
# MI
# ---------------------------------------------------------------------------


class TestMI:
    def test_high_mi_is_ok(self, tmp_path):
        pf = make_parsed_file(mi=80.0)
        results = mi.compute(pf, _cfg(tmp_path))
        assert len(results) == 1
        assert results[0].value == 80.0
        assert results[0].severity == mb.Severity.OK

    def test_low_mi_is_error(self, tmp_path):
        pf = make_parsed_file(mi=5.0)
        results = mi.compute(pf, _cfg(tmp_path))
        assert results[0].severity == mb.Severity.ERROR

    def test_mi_scope_is_file(self, tmp_path):
        pf = make_parsed_file(mi=60.0)
        results = mi.compute(pf, _cfg(tmp_path))
        assert results[0].scope == "file"


# ---------------------------------------------------------------------------
# CBO
# ---------------------------------------------------------------------------


class TestCBO:
    def test_no_refs_ok(self, tmp_path):
        cls = make_class(name="Isolated")
        pf = make_parsed_file(classes=[cls])
        results = cbo.compute(pf, _cfg(tmp_path))
        assert results[0].value == 0
        assert results[0].severity == mb.Severity.OK

    def test_many_refs_warn(self, tmp_path):
        from scout.parsers.base import ClassUnit, SourceLocation

        loc_ = SourceLocation(line_start=1, line_end=20)
        cls = ClassUnit(
            name="God",
            qualified_name="God",
            location=loc_,
            fields=frozenset(),
            methods=(),
            imported_class_refs=frozenset(f"Dep{i}" for i in range(8)),
        )
        pf = make_parsed_file(classes=[cls])
        results = cbo.compute(pf, _cfg(tmp_path))
        assert results[0].severity in (mb.Severity.WARN, mb.Severity.ERROR)

    def test_empty_classes_no_results(self, tmp_path):
        pf = make_parsed_file(classes=[])
        results = cbo.compute(pf, _cfg(tmp_path))
        assert results == []


# ---------------------------------------------------------------------------
# LCOM
# ---------------------------------------------------------------------------


class TestLCOM:
    def test_single_method_lcom_one(self, tmp_path):
        m = make_method("do_it", refs=frozenset({"x"}))
        cls = make_class(methods=[m])
        pf = make_parsed_file(classes=[cls])
        results = lcom.compute(pf, _cfg(tmp_path))
        assert results[0].value == 1
        assert results[0].severity == mb.Severity.OK

    def test_disjoint_methods_high_lcom(self, tmp_path):
        m1 = make_method("m1", refs=frozenset({"a", "b"}))
        m2 = make_method("m2", refs=frozenset({"c", "d"}))
        m3 = make_method("m3", refs=frozenset({"e", "f"}))
        cls = make_class(methods=[m1, m2, m3])
        pf = make_parsed_file(classes=[cls])
        results = lcom.compute(pf, _cfg(tmp_path))
        assert results[0].value >= 2  # disjoint → multiple components

    def test_empty_class_no_results(self, tmp_path):
        cls = make_class(methods=[])
        pf = make_parsed_file(classes=[cls])
        results = lcom.compute(pf, _cfg(tmp_path))
        assert results == []

    def test_connected_methods_lcom_one(self, tmp_path):
        m1 = make_method("m1", refs=frozenset({"x"}))
        m2 = make_method("m2", refs=frozenset({"x"}))
        cls = make_class(methods=[m1, m2])
        pf = make_parsed_file(classes=[cls])
        results = lcom.compute(pf, _cfg(tmp_path))
        assert results[0].value == 1


# ---------------------------------------------------------------------------
# Duplication — property tests
# ---------------------------------------------------------------------------

_DUP_WINDOW = 8  # small window for unit tests


def _dup_cfg() -> MetricConfig:
    return MetricConfig(thresholds={"duplication": 5.0}, duplication_min_tokens=_DUP_WINDOW)


def _make_tokens(names: list[str], base_line: int = 1) -> list[Token]:
    """Build a realistic-length normalized-invariant token stream.

    Produces tokens equivalent to:
        def <n>(x): return x + 1; y = x * 2; z = y - n; return z
    repeated for each name in *names*, so that identifier renaming only
    changes the 'identifier' tokens — which are normalized away.
    """
    stream: list[Token] = []
    line = base_line
    for n in names:
        # def <n>(x):
        stream += [
            Token(kind="keyword", value="def", line=line),
            Token(kind="identifier", value=n, line=line),
            Token(kind="punct", value="(", line=line),
            Token(kind="identifier", value="x", line=line),
            Token(kind="punct", value=")", line=line),
            Token(kind="punct", value=":", line=line),
        ]
        line += 1
        # return x + 1
        stream += [
            Token(kind="keyword", value="return", line=line),
            Token(kind="identifier", value="x", line=line),
            Token(kind="op", value="+", line=line),
            Token(kind="number", value="1", line=line),
        ]
        line += 1
        # y = x * 2
        stream += [
            Token(kind="identifier", value="y", line=line),
            Token(kind="op", value="=", line=line),
            Token(kind="identifier", value="x", line=line),
            Token(kind="op", value="*", line=line),
            Token(kind="number", value="2", line=line),
        ]
        line += 1
    return stream


class TestDuplicationProperties:
    def test_identifier_rename_detected_as_duplicate(self):
        """Two blocks with different variable names but identical structure must match."""
        names_a = ["foo", "bar", "baz"]
        names_b = ["alpha", "beta", "gamma"]  # different identifiers, same structure
        tokens_a = _make_tokens(names_a)
        tokens_b = _make_tokens(names_b)

        pf_a = make_parsed_file(path="a.py", language=Language.PYTHON, tokens=tokens_a, sloc=9)
        pf_b = make_parsed_file(path="b.py", language=Language.PYTHON, tokens=tokens_b, sloc=9)

        results = duplication.compute([pf_a, pf_b], _dup_cfg())
        assert len(results) == 1
        assert results[0].value > 0, "renamed identifiers should still be flagged as duplicates"

    def test_cross_language_not_matched(self):
        """Identical token streams in different languages must not be counted as duplicates.

        Uses a single non-repeating block so each file has 0% internal duplication.
        The cross-language guard must then keep the combined result at 0%.
        """
        # Single block — no structural repetition, so no internal self-match per file.
        tokens_py = _make_tokens(["unique_py"])
        tokens_js = _make_tokens(["unique_js"])

        pf_py = make_parsed_file(path="a.py", language=Language.PYTHON, tokens=tokens_py, sloc=3)
        pf_js = make_parsed_file(
            path="b.js", language=Language.JAVASCRIPT, tokens=tokens_js, sloc=3
        )

        results = duplication.compute([pf_py, pf_js], _dup_cfg())
        assert len(results) == 1
        assert results[0].value == 0.0, "cross-language blocks must never be matched"

    def test_identical_blocks_same_language_detected(self):
        """Exact duplicate blocks in two same-language files must be detected."""
        tokens = _make_tokens(["foo", "bar", "baz"])

        pf_a = make_parsed_file(path="a.py", language=Language.PYTHON, tokens=tokens, sloc=9)
        pf_b = make_parsed_file(path="b.py", language=Language.PYTHON, tokens=list(tokens), sloc=9)

        results = duplication.compute([pf_a, pf_b], _dup_cfg())
        assert results[0].value > 0

    def test_single_file_no_duplication(self):
        """A single file with no internal repetition reports 0% duplication."""
        tokens = _make_tokens(["foo"])
        pf = make_parsed_file(path="alone.py", language=Language.PYTHON, tokens=tokens, sloc=3)

        results = duplication.compute([pf], _dup_cfg())
        assert results[0].value == 0.0

    def test_empty_files_no_crash(self):
        """Files with no tokens must not crash the deduplication engine."""
        pf_a = make_parsed_file(path="empty_a.py", language=Language.PYTHON, tokens=[], sloc=0)
        pf_b = make_parsed_file(path="empty_b.py", language=Language.PYTHON, tokens=[], sloc=0)
        results = duplication.compute([pf_a, pf_b], _dup_cfg())
        assert results[0].value == 0.0
