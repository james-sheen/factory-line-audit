"""The channel, and the gate. The review gate in BRIDGES, in assertions."""
from __future__ import annotations

import json
import os

import pytest

from conftest import FIXTURE, write
from factory_line_audit import formats
from factory_line_audit.declarations import (
    KINDS, check_statements, collect, draft, gate, review_status)


class TestTheGate:
    def test_a_reviewed_file_passes(self, register, tmp_path):
        with open(FIXTURE, encoding="utf-8") as handle:
            body = json.load(handle)
        body.pop("fixture")
        body["reviewed_by"] = "J. Engineer"
        body["reviewed_on"] = "2026-09-03"
        path = write(tmp_path, "d.json", body)
        assert gate([path], register)["reviews"][0]["status"] == "reviewed"

    def test_a_name_with_no_date_is_refused(self):
        status, why = review_status({"reviewed_by": "J. Engineer"})
        assert status == "unreviewed"
        assert "clearing the gate rather than passing it" in why

    def test_a_date_with_no_name_is_refused(self):
        assert review_status({"reviewed_on": "2026-09-03"})[0] == "unreviewed"

    def test_a_fixture_passes_only_by_disclosing_itself(self):
        assert review_status({"fixture": True, "reviewed_by": "fixture"})[0] == "fixture"
        assert review_status({"fixture": True, "reviewed_by": "J. Real"})[0] == "unreviewed"

    def test_the_fixture_in_this_repository_is_marked_as_one(self):
        """A fixture that impersonated a reviewer would teach this suite that
        impersonation works, and the suite was the thing meant to notice."""
        body = formats.load(FIXTURE, formats.DECLARATION)
        assert review_status(body)[0] == "fixture"


class TestDraftingIsLegalAndFeedingItIsNot:
    def test_draft_emits_unreviewed_statements_and_exits_clean(self, register):
        body = draft(register)
        assert body["statements"], "a draft with nothing in it proves nothing"
        assert review_status(body)[0] == "unreviewed"

    def test_every_drafted_statement_has_an_empty_basis(self, register):
        """The one thing a rule cannot do is know WHY. Filling in a plausible
        basis would be the derivation wearing a costume."""
        for statement in draft(register)["statements"]:
            assert statement["basis"] == ""

    def test_the_same_package_refuses_its_own_draft(self, register, tmp_path):
        path = write(tmp_path, "draft.json", draft(register))
        with pytest.raises(formats.Refusal) as caught:
            gate([path], register)
        assert caught.value.path == path

    def test_no_drafted_statement_invents_a_number(self, register):
        for statement in draft(register)["statements"]:
            numbers = [v for k, v in statement.items()
                       if k not in ("kind", "asset", "tag", "basis")
                       and not k.startswith("_")]
            assert all(v is None for v in numbers), statement


class TestStatementsAreCheckedMechanically:
    def test_every_kind_maps_onto_something_the_engine_would_decline(self):
        """BRIDGES: the decline vocabulary read backwards IS the requirements
        table. Every kind must say which refusal it answers."""
        for name, spec in KINDS.items():
            assert spec["answers"], name
            assert spec["note"], name

    def test_a_statement_about_a_tag_that_does_not_exist_is_caught(
            self, register, tmp_path):
        body = {"format": formats.DECLARATION, "fixture": True,
                "reviewed_by": "fixture",
                "statements": [{"kind": "bound", "asset": "PR-01",
                                "tag": "nope", "warning": 1, "basis": "x"}]}
        problems = check_statements(body, register, "x")
        assert any("register declares no such tag" in p for p in problems)

    def test_a_statement_about_a_templated_tag_is_caught(self, register):
        """SpareAnalog3 was removed at register load. A declaration about it is
        a declaration about something that will never be modelled."""
        body = {"statements": [{"kind": "bound", "asset": "PR-01",
                                "tag": "SpareAnalog3", "warning": 1,
                                "basis": "x"}]}
        assert check_statements(body, register, "x")

    def test_redundancy_must_name_a_real_sibling(self, register):
        body = {"statements": [{"kind": "redundant", "asset": "ST-02",
                                "tag": "parts_out", "agrees_with": ["ghost"],
                                "tolerance": 0.01, "basis": "x"}]}
        assert any("agrees_with" in p for p in check_statements(body, register, "x"))

    def test_the_shipped_fixture_is_mechanically_clean(self, register):
        body = formats.load(FIXTURE, formats.DECLARATION)
        assert check_statements(body, register, FIXTURE) == []

    def test_collect_keeps_the_provenance_of_each_statement(self, gated):
        for statements in collect(gated["accepted"]).values():
            for statement in statements:
                assert statement["_from"].endswith(".json")
                assert statement["_review"] == "fixture"


class TestWhatCountsAsTheSameStatementTwice:
    """R4 from the 0.1.7 review, and a regression the M3 fix introduced.

    The duplicate rule keyed on `(asset, tag, kind)` and said, in its own
    refusal message, that *the generator reads the first and ignores the rest*.
    That is true of the kinds read at `[0]` and false of `conservation`, which
    `generator.build` ITERATES, emitting one derived balance per statement.
    `conservation` is asset-scoped and carries `tag: None`, so two balances on
    one station collided on one key: a declaration that was legal in 0.1.6, and
    that the generator still supports, refused by the 0.1.7 gate with a message
    asserting the opposite. Measured both ways -- the refusal, and two
    CONSERVATION axioms out of the generator for two statements.
    """

    SECOND_BALANCE = {"kind": "conservation", "asset": "ST-02",
                      "input_tag": "parts_in", "output_tags": ["parts_out_mes"],
                      "basis": "TEST -- a second, independent balance on one "
                               "station: the MES count is the other side of the "
                               "same input"}

    @staticmethod
    def _fixture():
        with open(FIXTURE, encoding="utf-8") as handle:
            return json.load(handle)

    def _with(self, tmp_path, *extra):
        body = self._fixture()
        body["statements"] = list(body["statements"]) + list(extra)
        return write(tmp_path, "dup.json", body)

    def test_two_different_balances_on_one_asset_are_accepted(self, register,
                                                              tmp_path):
        gate([self._with(tmp_path, self.SECOND_BALANCE)], register)

    def test_the_generator_really_does_emit_both(self, register, tmp_path):
        """The non-vacuity control for the rule above. If the generator read
        `[0]` after all, allowing two would be allowing one to be ignored --
        exactly what the rule exists to prevent."""
        from factory_line_audit.generator import build

        def axioms_for(*extra):
            path = self._with(tmp_path, *extra)
            with open(path, encoding="utf-8") as handle:
                body = json.load(handle)
            body["_path"] = path
            body["_review"] = {"reviewer": "test", "date": "2026-09-10"}
            text, _ = build(register, {"accepted": [body], "reviews": []})
            return text.count("CONSERVATION")

        one = axioms_for()
        two = axioms_for(self.SECOND_BALANCE)
        assert two == one + 1, (one, two)

    def test_the_same_balance_restated_is_still_a_duplicate(self, register,
                                                           tmp_path):
        same = next(s for s in self._fixture()["statements"]
                    if s["kind"] == "conservation")
        with pytest.raises(formats.Refusal) as caught:
            gate([self._with(tmp_path, dict(same, basis="TEST -- restated"))],
                 register)
        assert "declared 2 times" in caught.value.message
        assert "two DIFFERENT ones on this asset are legal" in caught.value.message

    def test_the_order_of_output_tags_does_not_make_a_new_balance(self, register,
                                                                 tmp_path):
        same = next(s for s in self._fixture()["statements"]
                    if s["kind"] == "conservation")
        flipped = dict(same, output_tags=list(reversed(same["output_tags"])),
                       basis="TEST -- the same balance, outputs reordered")
        with pytest.raises(formats.Refusal):
            gate([self._with(tmp_path, flipped)], register)

    def test_a_single_valued_kind_is_still_refused_twice(self, register,
                                                         tmp_path):
        """No strictness was traded away. A second `setpoint` on one tag is the
        contradiction the rule was written for."""
        first = next(s for s in self._fixture()["statements"]
                     if s["kind"] == "setpoint" and s["asset"] == "ST-02")
        second = dict(first, setpoint=first["setpoint"] + 1,
                      basis="TEST -- a second setpoint on one tag")
        with pytest.raises(formats.Refusal) as caught:
            gate([self._with(tmp_path, second)], register)
        assert "reads the first and ignores the rest" in caught.value.message

    def test_two_exclusions_differ_by_reason(self, register, tmp_path):
        excl = next(s for s in self._fixture()["statements"]
                    if s["kind"] == "exclusion")
        gate([self._with(tmp_path, dict(excl, reason="TEST -- a different "
                                                     "scope decision"))],
             register)
        with pytest.raises(formats.Refusal):
            gate([self._with(tmp_path, dict(excl, basis="TEST -- restated"))],
                 register)

    def test_every_iterated_kind_really_is_iterated(self, register, tmp_path):
        """`ITERATED_KINDS` is a claim about `generator.build`, so it is held
        against the generator's OUTPUT, one member at a time.

        The first version of this test regexed the generator source for a
        `for ... in _statements(...)` loop. That form finds `conservation` and
        not `exclusion` -- which is iterated through a different construct -- so
        it asserted `{conservation} <= {conservation, exclusion}` and passed
        while measuring half of what it claimed. The predicate was cheaper than
        the claim.
        """
        from factory_line_audit.declarations import ITERATED_KINDS
        from factory_line_audit.generator import build

        def manifest_for(*extra):
            path = self._with(tmp_path, *extra)
            with open(path, encoding="utf-8") as handle:
                body = json.load(handle)
            body["_path"] = path
            body["_review"] = {"reviewer": "test", "date": "2026-09-10"}
            return build(register, {"accepted": [body], "reviews": []})

        base_text, base_manifest = manifest_for()
        base_exclusions = len(base_manifest["exclusions"])

        exercised = set()

        # conservation: a second balance must add a second CONSERVATION axiom.
        text, _ = manifest_for(self.SECOND_BALANCE)
        assert text.count("CONSERVATION") == base_text.count("CONSERVATION") + 1
        exercised.add("conservation")

        # exclusion: a second asset-scope exclusion, with its own reason, must
        # reach the manifest as its own row rather than replacing the first.
        excl = next(s for s in self._fixture()["statements"]
                    if s["kind"] == "exclusion")
        _, second = manifest_for(dict(excl, reason="TEST -- a second, different "
                                                  "scope decision"))
        assert len(second["exclusions"]) == base_exclusions + 1
        exercised.add("exclusion")

        assert exercised == set(ITERATED_KINDS), (
            f"{sorted(set(ITERATED_KINDS) - exercised)} is declared iterated and "
            f"no case here shows it; a kind in this set that is really read at "
            f"[0] lets a second statement be silently ignored")
