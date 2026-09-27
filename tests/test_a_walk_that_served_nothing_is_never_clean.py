"""A walk that served nothing is never a clean result, on any verb.

A walk with NO samples was already refused where it could be compared, and it
was already worth a note where it is checked for shape. A walk WITH samples and
no node in any of them was neither: `regression` paired zero points against zero
and answered *nothing changed*, exit 0, and `validate-walk` said nothing at all.
One level further on, `detect` refused such a walk under the wrong name, and a
stored attestation of nothing attempted re-reported whatever verdict it carried.
"""
from __future__ import annotations

import json
import os

import pytest

from conftest import CORPUS, FIXTURE, REGISTER, write
from factory_line_audit import formats
from factory_line_audit.cli import main
from factory_line_audit.exit_contract import CLEAN, INCOMPLETE
from factory_line_audit.walkcheck import observations, validate_walk

NODE = "ns=2;s=PR01.DieTemp"


def walk(samples):
    return {"format": formats.WALK, "line": "L1",
            "source": {"kind": "synthetic", "endpoint": "none"},
            "samples": samples}


def served(n=3, nodes=(NODE,)):
    """A walk of `n` samples, each serving every node in `nodes`."""
    return walk([{"t": f"2026-09-09T08:0{i}:00Z",
                  "nodes": {node: {"v": 10.0 + i, "q": "Good"} for node in nodes}}
                 for i in range(n)])


def nodeless(n=3):
    return served(n, nodes=())


class TestRegressionRefusesAWalkThatServedNothing:

    @pytest.fixture(autouse=True)
    def _core(self):
        pytest.importorskip("presence_audit",
                            reason="the [vertical] extra is not installed")

    def test_two_nodeless_walks_are_two_not_nothing_changed(self, tmp_path):
        from factory_line_audit.regression import compare
        one = write(tmp_path, "a.json", nodeless())
        two = write(tmp_path, "b.json", nodeless())
        code, body = compare(one, two)
        assert code == INCOMPLETE, body
        said = " ".join(body["could_not_complete"])
        assert "no node in any of them" in said and "a.json" in said and "b.json" in said

    def test_either_side_is_enough(self, tmp_path):
        from factory_line_audit.regression import compare
        good = write(tmp_path, "good.json", served())
        empty = write(tmp_path, "empty.json", nodeless())
        assert compare(good, empty)[0] == INCOMPLETE
        assert compare(empty, good)[0] == INCOMPLETE

    def test_a_walk_that_served_something_still_compares(self, tmp_path):
        """The control: the refusal keys on NO node, not on an empty sample.
        A node that vanished mid-walk is a real thing and still compared."""
        from factory_line_audit.regression import compare
        partial = served()
        partial["samples"][0]["nodes"] = {}
        one = write(tmp_path, "a.json", partial)
        assert compare(one, one)[0] == CLEAN

    def test_through_the_front_door(self, tmp_path, capsys):
        one = write(tmp_path, "a.json", nodeless())
        assert main(["regression", "--before", one, "--after", one]) == INCOMPLETE
        assert "no node in any of them" in capsys.readouterr().out


class TestValidateWalkSaysSoAndStillAccepts:
    """Malformation only, by design: a nodeless walk is well formed, like an
    empty one. What it must do is say what it is, as it does for no samples."""

    def test_it_is_legal(self):
        assert validate_walk(nodeless()) == []

    def test_and_it_is_noted(self):
        assert any("no node in any of the 3 sample(s)" in note
                   for note in observations(nodeless()))

    def test_a_walk_that_served_something_is_not_noted_as_empty(self):
        assert not any("no node in any" in note for note in observations(served()))

    def test_through_the_front_door_it_is_clean_with_the_note(self, tmp_path, capsys):
        path = write(tmp_path, "w.json", nodeless())
        assert main(["validate-walk", path]) == CLEAN
        assert "note: no node in any" in capsys.readouterr().out


def _detect(tmp_path, body, *extra):
    path = write(tmp_path, "walk.json", body)
    return main(["detect", "--register", REGISTER, "--walk", path,
                 "--declarations", FIXTURE, *extra])


class TestDetectNamesTheCause:
    """A walk that fed nothing used to stop as `engine_unavailable` -- naming
    the one component that was working."""

    @pytest.fixture(autouse=True)
    def _engine(self):
        pytest.importorskip("arbiter_engine", reason="Stage 2 needs the engine")

    @pytest.mark.parametrize("body,why", [
        (walk([]), "the walk carries no samples"),
        (nodeless(), "carry no node in any of them"),
        (served(nodes=("ns=2;s=NotOnThisLine",)),
         "no node the walk served is a tag this register models"),
    ], ids=["no samples", "no nodes", "no modelled tag"])
    def test_it_stops_as_nothing_fed(self, tmp_path, capsys, body, why):
        assert _detect(tmp_path, body) == INCOMPLETE
        err = capsys.readouterr().err
        assert "HARD STOP nothing_fed" in err and why in err, err
        assert "engine_unavailable" not in err

    def test_the_run_itself_is_unchanged(self, register, clean_walk, gated):
        """The control: the corpus walk still runs to a verdict."""
        from factory_line_audit.feeder import run
        from factory_line_audit.generator import build
        from factory_line_audit.presence import classify
        model_text, manifest = build(register, gated)
        result = run(model_text, register, classify(register, clean_walk),
                     clean_walk, gated, manifest)
        assert result["envelope"]["checked"]["invariants"] > 0


class TestAttestRefusesARecordOfNothingAttempted:

    @pytest.fixture
    def stored(self, tmp_path):
        pytest.importorskip("arbiter_engine", reason="Stage 2 needs the engine")
        out = os.path.join(str(tmp_path), "attest.json")
        main(["detect", "--register", REGISTER,
              "--walk", os.path.join(CORPUS, "clean.json"),
              "--declarations", FIXTURE, "--attest-out", out])
        with open(out, encoding="utf-8") as handle:
            return out, json.load(handle)

    def test_a_real_attestation_re_reports_its_verdict(self, stored, capsys):
        path, att = stored
        assert main(["attest", path]) == att["exit"]
        assert "OUTCOME" in capsys.readouterr().out

    def test_one_with_nothing_attempted_is_two_and_prints_no_outcome(
            self, stored, tmp_path, capsys):
        _, att = stored
        att["checked"]["invariants_attempted"] = 0
        att["checked"]["entities"] = 0
        att["exit"], att["verdict"] = CLEAN, "CLEAN"
        path = write(tmp_path, "nothing.json", att)
        capsys.readouterr()
        assert main(["attest", path]) == INCOMPLETE
        captured = capsys.readouterr()
        assert "REFUSED" in captured.err and "no invariant attempted" in captured.err
        assert "OUTCOME" not in captured.out


class TestGateNotesADeclarationOfNothing:
    """Noted, not refused: a reviewed file may honestly declare nothing, and the
    register decides what is checked. It must not read like a file that did."""

    def _declaration(self, tmp_path, statements):
        with open(FIXTURE, encoding="utf-8") as handle:
            body = json.load(handle)
        body["statements"] = statements
        return write(tmp_path, "d.json", body)

    def test_an_empty_one_passes_with_the_note(self, tmp_path, capsys):
        path = self._declaration(tmp_path, [])
        assert main(["gate", "--register", REGISTER, path]) == CLEAN
        assert "declares nothing, so it adds nothing to the model" in \
            capsys.readouterr().out

    def test_one_that_declares_something_is_not_noted(self, capsys):
        assert main(["gate", "--register", REGISTER, FIXTURE]) == CLEAN
        assert "declares nothing" not in capsys.readouterr().out
