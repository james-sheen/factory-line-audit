"""`validate-walk`: what a receiver can refuse, and what it must not.

Synthetic walks throughout. The corpus is derived and not committed, and it is
also written by this package -- so a rule checked only against it is a rule
checked against its own author. That is not hypothetical here: the first cut of
`_is_scalar` said *a number or null* and refused the corpus outright, because a
state tag carries a boolean. Widening it to match the corpus would still have
refused a real line, where a machine state is usually an enumeration string.
The reader is the oracle, and `Node.reading` passes the value through uncoerced.
"""
from __future__ import annotations

import json

import pytest

from factory_line_audit import formats
from factory_line_audit.cli import main
from factory_line_audit.exit_contract import CLEAN, INCOMPLETE
from factory_line_audit.walkcheck import observations, validate_walk


def reading(value, quality="Good"):
    return {"v": value, "q": quality, "t": "2026-09-09T08:00:00Z"}


def walk(nodes):
    return {"format": formats.WALK, "line": "L1",
            "source": {"kind": "synthetic"},
            "samples": [{"t": "2026-09-09T08:00:00Z", "nodes": nodes}]}


class TestWhatAReadingMayBe:
    """Every scalar the reader passes through, in one walk."""

    def test_all_four_kinds_are_well_formed(self):
        subject = walk({
            "ns=2;s=PR01.DieTemp": reading(198.4),          # a measurement
            "ns=2;s=ST01.Running": reading(True),           # a running flag
            "ns=2;s=ST01.Mode": reading("Auto"),            # an enumeration
            "ns=2;s=ROB01.Ax1Temp": reading(None, "Bad_DeviceFailure"),
        })
        assert validate_walk(subject) == []

    def test_an_object_is_not_a_reading(self):
        """The non-vacuity control for the class above: the check CAN fire."""
        problems = validate_walk(walk({"ns=2;s=A": reading({"nested": 1})}))
        assert len(problems) == 1
        assert "dict" in problems[0]

    def test_a_list_is_not_a_reading_either(self):
        assert validate_walk(walk({"ns=2;s=A": reading([1, 2])}))


class TestWhatItRefuses:
    @pytest.mark.parametrize("payload, expected", [
        ("not a walk at all", "not an object"),
        ({"samples": []}, "no `format`"),
        ({"format": 7, "samples": []}, "not a string"),
        ({"format": "factory-line-audit/walk/9", "samples": []}, "major 9"),
        ({"format": "somebody-else/walk/1", "samples": []}, "not a"),
        ({"format": formats.WALK}, "no `samples`"),
        ({"format": formats.WALK, "samples": {}}, "not a list"),
    ])
    def test_each_is_named(self, payload, expected):
        problems = validate_walk(payload)
        assert problems, payload
        assert any(expected in problem for problem in problems), problems

    def test_a_sample_that_is_not_an_object(self):
        assert validate_walk({"format": formats.WALK, "samples": ["nope"]})

    def test_a_reading_with_no_status_word(self):
        """The status word is how a node the server will not vouch for is told
        apart from one it never had -- the three-state answer rests on it."""
        problems = validate_walk(walk({"ns=2;s=A": {"v": 1.0}}))
        assert any("carries no `q`" in p for p in problems), problems

    def test_it_reports_every_problem_at_once(self):
        """One per run would make a caller fix them one at a time."""
        problems = validate_walk({"format": formats.WALK, "samples": [
            {"t": 7, "nodes": {"ns=2;s=A": {"v": 1.0}}}]})
        assert len(problems) >= 2, problems


class TestWhatItMustNotRefuse:
    """A validator that rejects valid input is one people learn to route
    around, and they take the malformed cases with them."""

    def test_a_walk_that_served_nothing_is_legal(self):
        empty = {"format": formats.WALK, "samples": []}
        assert validate_walk(empty) == []
        assert observations(empty), "and it is worth SAYING that it served none"

    def test_an_absent_timestamp_is_legal(self):
        assert validate_walk(walk({"ns=2;s=A": {"q": "Good"}})) == []

    def test_an_absent_value_is_legal(self):
        """Absent and null are both `the server would not vouch for it`."""
        assert validate_walk(walk({"ns=2;s=A": {"q": "Bad_DeviceFailure"}})) == []

    def test_extra_fields_are_ignored(self):
        subject = walk({"ns=2;s=A": dict(reading(1.0), units="degC")})
        subject["collected_by"] = "somebody"
        assert validate_walk(subject) == []


class TestObservationsAreNotProblems:
    def test_out_of_order_samples_are_noted_not_refused(self):
        subject = {"format": formats.WALK, "samples": [
            {"t": "2026-09-09T09:00:00Z", "nodes": {}},
            {"t": "2026-09-09T08:00:00Z", "nodes": {}}]}
        assert validate_walk(subject) == []
        assert any("time order" in note for note in observations(subject))


class TestThroughTheCli:
    def test_a_well_formed_walk_is_clean(self, tmp_path, capsys):
        path = tmp_path / "w.json"
        path.write_text(json.dumps(walk({"ns=2;s=A": reading(1.0)})))
        assert main(["validate-walk", str(path)]) == CLEAN

    def test_a_malformed_walk_is_two_and_never_one(self, tmp_path):
        """A file that could not be read is not a finding about the line."""
        path = tmp_path / "w.json"
        path.write_text(json.dumps({"format": formats.WALK, "samples": {}}))
        assert main(["validate-walk", str(path)]) == INCOMPLETE

    def test_a_truncated_file_is_two(self, tmp_path):
        path = tmp_path / "w.json"
        path.write_text('{"format": "factory-line-audit/walk/1", "sam')
        assert main(["validate-walk", str(path)]) == INCOMPLETE

    def test_a_missing_file_is_two(self, tmp_path):
        assert main(["validate-walk", str(tmp_path / "nope.json")]) == INCOMPLETE


class TestItStaysInStageOne:
    def test_it_imports_nothing_outside_the_standard_library(self):
        """A receiver checking a file should not have to install an axiom
        engine, and this package's whole shape rests on Stage 1 being bare."""
        import ast
        import pathlib
        source = pathlib.Path(
            __file__).resolve().parents[1] / "src" / "factory_line_audit" / "walkcheck.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
        assert not (imported & {"presence_audit", "arbiter_engine", "asyncua"}), imported
