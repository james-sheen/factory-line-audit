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
