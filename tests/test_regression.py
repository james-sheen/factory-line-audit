"""`regression`: two walks of one line, through the core's gate.

Synthetic walks rather than the corpus: the corpus is derived, expires, and is
not committed, so a test that read it would be green or absent depending on
whether somebody had run `make_corpus.py`.

Two of these are regression tests for defects filed upstream and fixed here
first. Both were found by USING the seam end to end, and neither is visible to
the core's conformance kit -- which accepts this vertical with no problems.
"""
from __future__ import annotations

import json
import os

import pytest

from conftest import CORPUS
from factory_line_audit.exit_contract import CLEAN, FINDINGS, INCOMPLETE

core = pytest.importorskip("presence_audit",
                           reason="the [vertical] extra is not installed")

NODES = ("ns=2;s=PR01.DieTemp", "ns=2;s=PR01.Tonnage", "ns=2;s=ST01.CycleTime")


def walk(nodes, *, samples=3, prefix=""):
    """A `factory-line-audit/walk/1` with one reading per node per sample."""
    return {
        "format": "factory-line-audit/walk/1",
        "line": "L1",
        "source": {"kind": "synthetic", "endpoint": "none"},
        "samples": [
            {"t": f"2026-09-09T08:0{n}:00Z",
             "nodes": {f"{prefix}{node}": {"v": 10.0 + n, "q": "Good",
                                           "t": f"2026-09-09T08:0{n}:00Z"}
                       for node in nodes}}
            for n in range(samples)
        ],
    }


def written(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


class TestAWalkComparedWithItself:
    """The control. Everything else here is a claim about a DIFFERENCE, and a
    comparison that reported differences against identical input would satisfy
    several of them for the wrong reason."""

    def test_nothing_changed(self, tmp_path):
        from factory_line_audit.regression import compare
        one = written(tmp_path, "a.json", walk(NODES))
        code, body = compare(one, one)
        assert code == CLEAN, body
        assert not body["regressions"]

    def test_points_are_the_same_objects_on_every_read(self, tmp_path):
        """The core's `compare_walks` claims points into a set keyed on `id()`
        and then re-reads `.points` to see what it did not claim. Built fresh on
        read, this walk handed it new objects the second time, nothing was ever
        claimed, and two walks sharing 24 of 27 points came back as 27 removed
        and 24 added.

        The protocol asks for `Iterable[CapturedPoint]` and says nothing about
        identity, so this is a requirement no reader of it can find. Filed as
        presence-audit #4; pinned here because the fix is a property of this
        class and a refactor would quietly undo it.
        """
        from factory_line_audit.vertical import Walk
        subject = Walk(walk(NODES))
        assert [id(p) for p in subject.points] == [id(p) for p in subject.points]


class TestARemoval:
    def test_a_dropped_tag_is_a_finding_and_is_named(self, tmp_path):
        from factory_line_audit.regression import compare
        before = written(tmp_path, "before.json", walk(NODES))
        after = written(tmp_path, "after.json", walk(NODES[:-1]))
        code, body = compare(before, after)
        assert code == FINDINGS
        assert body["counts"].get("sensor_removed") == 1
        assert any(NODES[-1] in line for line in body["regressions"]), body


class TestADeclaredRename:
    """A PLC program release moves a subtree; somebody signs for it."""

    def test_a_declared_prefix_move_pairs_and_is_clean(self, tmp_path):
        from factory_line_audit.regression import compare
        before = written(tmp_path, "before.json", walk(NODES))
        after = written(tmp_path, "after.json", walk(NODES, prefix="L1."))
        code, body = compare(before, after, [("ns=2;s=", "L1.ns=2;s=")])
        assert code == CLEAN, body
        assert body["counts"].get("aggregation_prefix_paired") == len(NODES)

    def test_the_old_prefix_may_contain_an_equals_sign(self, tmp_path):
        """The core's `parse_prefix_map` splits `OLD=NEW` on the first `=`, so
        an OPC UA node id -- which always carries one -- cannot be declared
        through it, and the declaration silently matches nothing. This verb
        takes the pair as two arguments and hands `compare_walks` a tuple,
        which it accepts. Filed as presence-audit #5.

        The assertion is that the declaration WORKED, because the failure mode
        is a rename that reads as a mass removal rather than an error.
        """
        from factory_line_audit.regression import compare
        before = written(tmp_path, "before.json", walk(NODES))
        after = written(tmp_path, "after.json", walk(NODES, prefix="L1."))
        _, body = compare(before, after, [("ns=2;s=", "L1.ns=2;s=")])
        assert not body["counts"].get("sensor_removed")
        assert not body["counts"].get("sensor_added")


class TestAnUndeclaredShift:
    def test_it_is_reported_and_not_applied(self, tmp_path):
        """The other half of the one above, and the reason the flag exists. A
        rename this package inferred would be the guess the review gate
        refuses, so the shift is named and the points stay unpaired."""
        from factory_line_audit.regression import compare
        before = written(tmp_path, "before.json", walk(NODES))
        after = written(tmp_path, "after.json", walk(NODES, prefix="L1."))
        code, body = compare(before, after)
        assert code == FINDINGS
        assert body["undeclared_prefix_shifts"] >= 1
        assert body["counts"].get("sensor_removed") == len(NODES)
        assert not body["counts"].get("aggregation_prefix_paired")
        assert "NOT applied" in body["note"]


class TestWhatItCannotDo:
    """Could-not-complete is 2, never 1: a comparison that did not happen must
    not be reported as a comparison that found nothing."""

    def test_an_unreadable_walk_is_two(self, tmp_path):
        from factory_line_audit.regression import compare
        one = written(tmp_path, "a.json", walk(NODES))
        code, body = compare(one, str(tmp_path / "nope.json"))
        assert code == INCOMPLETE
        assert body["could_not_complete"]

    def test_a_walk_with_no_samples_is_two_and_says_why(self, tmp_path):
        """The fixture carries the REAL format.

        It used to say `format: x`, which since 0.1.7 is refused by the loader
        one step earlier -- so the test passed on a message about the format
        while claiming to be about the samples. Two reasons, one assertion, and
        the one it named was not the one that fired.
        """
        from factory_line_audit.regression import compare
        one = written(tmp_path, "a.json", walk(NODES))
        body_of = dict(walk(NODES), samples=[])
        empty = written(tmp_path, "empty.json", body_of)
        code, body = compare(one, empty)
        assert code == INCOMPLETE
        assert "no samples" in " ".join(body["could_not_complete"])

    def test_an_unknown_major_is_refused_by_this_verb_too(self, tmp_path):
        """M1 from the 0.1.6 review. This verb read raw JSON and compared any
        object with a `samples` key, including a `walk/2` written by a reader it
        does not understand, while the README said every verb refuses an unknown
        major by name."""
        from factory_line_audit.regression import compare
        one = written(tmp_path, "a.json", walk(NODES))
        ahead = written(tmp_path, "ahead.json",
                        dict(walk(NODES), format="factory-line-audit/walk/2"))
        code, body = compare(one, ahead)
        assert code == INCOMPLETE
        said = " ".join(body["could_not_complete"])
        assert "walk/2" in said and "ahead.json" in said, said

    def test_both_bad_walks_are_reported_together(self, tmp_path):
        """One per run would make a caller fix them one at a time."""
        from factory_line_audit.regression import compare
        code, body = compare(str(tmp_path / "no.json"), str(tmp_path / "nor.json"))
        assert code == INCOMPLETE
        assert len(body["could_not_complete"]) == 2


class TestItNeedsNoRegistration:
    def test_no_vertical_is_registered_and_it_still_works(self, tmp_path):
        """Two registered verticals are refused rather than ranked, so a
        pipeline may have this one and a BMC installed together. Passing the
        vocabulary explicitly is what makes the verb usable there."""
        import presence_audit.vocabulary as vocabulary
        from factory_line_audit.regression import compare
        assert not vocabulary.in_force(), (
            "a vertical is registered in this interpreter, so this test cannot "
            "tell whether the verb works without one")
        before = written(tmp_path, "before.json", walk(NODES))
        after = written(tmp_path, "after.json", walk(NODES[:-1]))
        assert compare(before, after)[0] == FINDINGS


class TestTheReceiverSideShapeCheckIsActuallyCalled:
    """R6 from the 0.1.7 review: a decision whose stated reason was false.

    0.1.7's docstring said `validate_walk` was not called because the
    declared-rename leg compares a walk whose node ids carry a prefix this
    package did not write, and a shape check on that copy *would refuse the one
    input the verb exists to accept*. Measured: `validate_walk` requires node
    keys to be non-empty strings, `L1.ns=2;s=...` is one, and the prefixed walk
    produces no problems at all -- nor do any of the corpus walks. The decision
    cost nothing and the reason was wrong, which is the worse half: a reader who
    believed it would not have tried.
    """

    def test_a_prefixed_walk_is_not_refused(self, tmp_path):
        """The claim the old reason rested on, held directly."""
        from factory_line_audit.walkcheck import validate_walk
        with open(os.path.join(CORPUS, "clean.json"), encoding="utf-8") as handle:
            walk = json.load(handle)
        for sample in walk["samples"]:
            sample["nodes"] = {f"L1.{node}": row
                               for node, row in sample["nodes"].items()}
        assert validate_walk(walk) == []

    def test_the_declared_rename_still_pairs_end_to_end(self, tmp_path):
        """The behaviour the old reason was protecting. Held through `compare`,
        so the shape check being in the path is exercised rather than read."""
        from factory_line_audit.regression import compare
        before = os.path.join(CORPUS, "clean.json")
        with open(before, encoding="utf-8") as handle:
            walk = json.load(handle)
        for sample in walk["samples"]:
            sample["nodes"] = {f"L1.{node}": row
                               for node, row in sample["nodes"].items()}
        after = os.path.join(str(tmp_path), "moved.json")
        with open(after, "w", encoding="utf-8") as handle:
            json.dump(walk, handle)
        code, _ = compare(before, after, [("ns=2;s=", "L1.ns=2;s=")])
        assert code == CLEAN

    def test_a_malformed_walk_is_now_refused_rather_than_compared(self, tmp_path):
        """What calling it buys. A walk that loads and is not a walk used to be
        compared anyway."""
        from factory_line_audit.regression import compare
        with open(os.path.join(CORPUS, "clean.json"), encoding="utf-8") as handle:
            walk = json.load(handle)
        walk["samples"][3]["nodes"] = "not an object"
        broken = os.path.join(str(tmp_path), "broken.json")
        with open(broken, "w", encoding="utf-8") as handle:
            json.dump(walk, handle)
        code, body = compare(os.path.join(CORPUS, "clean.json"), broken, [])
        assert code == INCOMPLETE
        assert any("well-formed walk" in p
                   for p in body["could_not_complete"]), body

    def test_the_false_reason_is_gone_from_the_source(self):
        """Pinned to the ARTIFACT, not the diff: prose describing a decision
        outlives the decision."""
        import inspect

        from factory_line_audit import regression
        source = inspect.getsource(regression._walk)
        assert "would refuse the one input" not in source
        assert "validate_walk" in source
