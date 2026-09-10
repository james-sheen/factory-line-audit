"""Whether a counter is zeroed in normal operation, and who decided.

Plan-2 C.2. The plan filed it as *the fixture rides an engine default for a
plant fact*, and described two `rate` statements that declare `allow_reset` on
neither. Measured, the population is EIGHT: `rate` is what the plan was looking
at, and `counter` is what carries MONOTONICITY. Six of the eight had no rate
statement at all -- and `allow_reset` was read only off a rate statement, so six
of the eight had no channel to declare it through. The predicate the plan
counted was cheaper than the claim it made.

So the channel is its own kind, and there are three states rather than two:

* **declared** -- `allow_reset: true` or `false`, with a basis;
* **unanswered** -- `allow_reset: null` with a basis, which says the question
  was put to somebody and nobody knew;
* **absent** -- nobody asked.

The last two produce the same model, and the engine cannot tell them apart. The
manifest can, and does, because *asked and unanswered* is a state a plant can
be in and *never asked* is a state this package would rather report than ship.
"""
from __future__ import annotations

import copy
import json

import pytest

from conftest import FIXTURE, write
from factory_line_audit import formats
from factory_line_audit.declarations import KINDS, check_statements, draft, gate
from factory_line_audit.generator import build


def counters(register) -> set:
    """(asset, tag) for every tag the generator gives MONOTONICITY.

    Derived from the register rather than listed. A list of eight would be a
    pin with an expiry date: it goes stale the day a ninth counter is added to
    the register, and it goes stale silently.
    """
    return {(asset["id"], tag)
            for asset in register["assets"]
            for tag, spec in (asset.get("tags") or {}).items()
            if spec["class"] == "counter"}


@pytest.fixture
def declared():
    with open(FIXTURE, encoding="utf-8") as handle:
        return json.load(handle)


def regated(body, register, tmp_path, name="d.json"):
    return gate([write(tmp_path, name, body)], register)


class TestEveryCounterWasAsked:
    def test_there_are_counters_to_ask_about(self, register):
        assert counters(register), ("no counter-class tag in the register, so "
                                   "every rule below holds an empty set")

    def test_every_counter_carries_monotonicity(self, register, gated):
        """The population is the axiom's, not the rate statement's."""
        import yaml
        text, manifest = build(register, gated)
        model = yaml.safe_load(text)
        carried = {(manifest["entity_type_map"][etype], row["name"])
                   for etype, rows in model["domain"]["indicators"].items()
                   for row in rows
                   if "MONOTONICITY" in (row.get("axioms") or [])}
        assert carried == counters(register)

    def test_none_is_left_to_the_engine_default(self, register, gated):
        """The acceptance, as C.2 wrote it: declared with a basis, or recorded
        as unanswerable. A counter in neither state is one nobody asked."""
        _, manifest = build(register, gated)
        unasked = {(row["asset"], row["tag"]) for row in manifest["exclusions"]
                   if row["reason"] == "no_declared_reset"}
        assert not unasked, (f"these counters inherit the engine's routing and "
                            f"nobody asked: {sorted(unasked)}")

    def test_every_reset_statement_carries_a_basis(self, declared):
        rows = [s for s in declared["statements"] if s["kind"] == "reset"]
        assert rows
        assert all(s.get("basis") for s in rows)


class TestTheDeclarationReachesTheEngine:
    """Declaring it is not the claim. The claim is that the engine sees it."""

    def test_the_model_carries_what_was_declared(self, register, gated, declared):
        import yaml
        text, manifest = build(register, gated)
        model = yaml.safe_load(text)
        etype_of = {asset: etype
                    for etype, asset in manifest["entity_type_map"].items()}
        for stmt in declared["statements"]:
            if stmt["kind"] != "reset":
                continue
            row = next(r for r in model["domain"]["indicators"][etype_of[stmt["asset"]]]
                       if r["name"] == stmt["tag"])
            assert row["monotonicity"]["allow_reset"] is stmt["allow_reset"], stmt

    def test_the_declarations_are_not_all_the_same_answer(self, declared):
        """Non-vacuity for the rule above. If every counter were declared the
        same way, a generator that hardcoded that value would pass it."""
        answers = {s["allow_reset"] for s in declared["statements"]
                   if s["kind"] == "reset"}
        assert answers == {True, False}, (
            f"the fixture declares only {answers}; the rule above cannot tell "
            f"a declaration that was read from one that was assumed")


class TestTheThreeStatesAreDistinguished:
    def test_absent_is_recorded_as_nobody_asked(self, register, declared, tmp_path):
        body = copy.deepcopy(declared)
        body["statements"] = [s for s in body["statements"]
                              if not (s["kind"] == "reset"
                                      and s["tag"] == "stroke_count")]
        _, manifest = build(register, regated(body, register, tmp_path))
        rows = [r for r in manifest["exclusions"]
                if r["reason"] == "no_declared_reset"]
        assert [(r["asset"], r["tag"]) for r in rows] == [("PR-01", "stroke_count")]
        assert "A6" in rows[0]["detail"], "the record cites no measurement"

    def test_unanswered_is_recorded_as_a_different_thing(self, register, declared,
                                                         tmp_path):
        body = copy.deepcopy(declared)
        for stmt in body["statements"]:
            if stmt["kind"] == "reset" and stmt["tag"] == "stroke_count":
                stmt["allow_reset"] = None
                stmt["basis"] = "FIXTURE -- asked; the line has no document"
        _, manifest = build(register, regated(body, register, tmp_path))
        rows = [r for r in manifest["exclusions"]
                if r["reason"] == "reset_unanswered"]
        assert [(r["asset"], r["tag"]) for r in rows] == [("PR-01", "stroke_count")]
        assert rows[0]["basis"] == "FIXTURE -- asked; the line has no document"
        assert not [r for r in manifest["exclusions"]
                    if r["reason"] == "no_declared_reset"]

    def test_unanswered_and_absent_produce_the_same_model(self, register,
                                                          declared, tmp_path):
        """Which is why they are recorded at all. The engine is handed an
        identical indicator either way; only the manifest says which happened."""
        import yaml
        absent = copy.deepcopy(declared)
        absent["statements"] = [s for s in absent["statements"]
                                if not (s["kind"] == "reset"
                                        and s["tag"] == "stroke_count")]
        unanswered = copy.deepcopy(declared)
        for stmt in unanswered["statements"]:
            if stmt["kind"] == "reset" and stmt["tag"] == "stroke_count":
                stmt["allow_reset"] = None
        one = build(register, regated(absent, register, tmp_path, "a.json"))[0]
        two = build(register, regated(unanswered, register, tmp_path, "b.json"))[0]
        block = lambda text: next(  # noqa: E731
            r for r in yaml.safe_load(text)["domain"]["indicators"]["Press__PR_01"]
            if r["name"] == "stroke_count")["monotonicity"]
        assert block(one) == block(two)
        assert "allow_reset" not in block(one)

    def test_declared_records_neither(self, register, gated):
        _, manifest = build(register, gated)
        assert not [r for r in manifest["exclusions"]
                    if r["reason"] in ("no_declared_reset", "reset_unanswered")]


class TestTheGateChecksTheChannel:
    def test_the_kind_exists_and_says_what_it_answers(self):
        assert KINDS["reset"]["requires_tag"] is True
        assert KINDS["reset"]["requires_keys"] == ("allow_reset",)
        assert KINDS["reset"]["note"]

    def test_a_reset_statement_with_no_answer_key_is_refused(self, register):
        problems = check_statements(
            {"statements": [{"kind": "reset", "asset": "PR-01",
                             "tag": "stroke_count", "basis": "x"}]},
            register, "x")
        assert any("no allow_reset key" in p for p in problems), problems

    def test_a_misspelt_answer_is_refused_rather_than_dropped(self, register):
        """An unknown KEY is not checked anywhere in this format, so before the
        key was required, `allow_resets: true` read as a file that had declared
        it while the engine routed from its default."""
        problems = check_statements(
            {"statements": [{"kind": "reset", "asset": "PR-01",
                             "tag": "stroke_count", "allow_resets": True,
                             "basis": "x"}]},
            register, "x")
        assert any("no allow_reset key" in p for p in problems), problems

    def test_null_with_a_basis_is_accepted(self, register):
        assert not check_statements(
            {"statements": [{"kind": "reset", "asset": "PR-01",
                             "tag": "stroke_count", "allow_reset": None,
                             "basis": "asked; nobody knew"}]},
            register, "x")

    def test_the_old_home_of_the_field_is_refused_by_name(self, register):
        """It was read off `rate` by the generator and validated by nothing.
        Refusing it names the remedy; ignoring it is the defect."""
        problems = check_statements(
            {"statements": [{"kind": "rate", "asset": "PR-01",
                             "tag": "stroke_count", "rate_warning": 1,
                             "allow_reset": True, "basis": "x"}]},
            register, "x")
        assert any("`reset` statement" in p for p in problems), problems

    def test_the_drafter_proposes_one_for_every_counter(self, register):
        proposed = {(s["asset"], s["tag"]) for s in draft(register)["statements"]
                    if s["kind"] == "reset"}
        assert proposed == counters(register)
        assert all(s["allow_reset"] is None and s["basis"] == ""
                   for s in draft(register)["statements"] if s["kind"] == "reset")


class TestTheChannelDoesNotSwallowTheOtherRecord:
    def test_a_reset_declaration_leaves_the_rate_gap_recorded(self, register,
                                                              gated):
        """The cheap way to carry `allow_reset` would have been a `rate`
        statement with no numbers in it. `rates` is tested for emptiness, so
        such a statement would have silenced `no_declared_rate` -- removing the
        record that says the rate arm is running on a number nobody chose,
        while supplying no number. A separate kind cannot do that."""
        _, manifest = build(register, gated)
        rate_gaps = {(r["asset"], r["tag"]) for r in manifest["exclusions"]
                     if r["reason"] == "no_declared_rate"}
        declared_reset = {("ST-02", "parts_out"), ("ST-02", "parts_out_mes")}
        assert declared_reset <= rate_gaps

    def test_the_new_reason_is_not_one_a_decline_can_agree_with(self):
        """The engine declines nothing for a missing `allow_reset`; it routes
        and is silent. A reason listed there would pair a record with a decline
        that can never arrive."""
        from factory_line_audit.feeder import RECORDED_GAPS
        assert "no_declared_reset" not in RECORDED_GAPS
        assert "reset_unanswered" not in RECORDED_GAPS
