"""`bad_state`: which words of a machine's state enumeration mean broken.

Measured across the declared engine range before this was written. A STATE
indicator listing STABILITY fires `declared_bad_state` from 0.1.12 and is
SILENT at 0.1.10 and 0.1.11 -- accepted, no finding, and not reported by
`unread_fields`, which does report a key nobody reads. So the manifest has to
carry the pin-dependence; nothing the engine offers will. Filed as arbiter #10.
"""
from __future__ import annotations

import json

import pytest

from factory_line_audit import formats
from factory_line_audit.declarations import KINDS, gate
from factory_line_audit.generator import build
from factory_line_audit.presence import load_register

REGISTER = "examples/asset_register.json"


def reviewed(tmp_path, asset, tag, states, **extra):
    body = {"format": "factory-line-audit/declaration/1",
            "reviewed_by": "commissioning engineer", "reviewed_on": "2026-09-09",
            "statements": [dict({"kind": "bad_state", "asset": asset, "tag": tag,
                                 "states": states,
                                 "basis": "PLC alarm list L1_MAIN v3.4"},
                                **extra)]}
    path = tmp_path / "declaration.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return str(path)


@pytest.fixture
def register():
    return load_register(REGISTER)


@pytest.fixture
def a_state_tag(register):
    for asset in register["assets"]:
        for name, tag in (asset.get("tags") or {}).items():
            if tag.get("class") == "state":
                return asset["id"], name
    pytest.fail("the example register carries no state-class tag")


class TestTheKind:
    def test_it_is_declared(self):
        assert "bad_state" in KINDS
        assert KINDS["bad_state"]["all_of"] == ("states",)

    def test_it_needs_a_tag(self):
        assert KINDS["bad_state"]["requires_tag"] is True

    def test_the_note_records_where_it_was_measured(self):
        """A pin-dependence nobody can re-derive is a claim, not a measurement."""
        note = KINDS["bad_state"]["note"]
        assert "0.1.12" in note and "0.1.10" in note


class TestWhatTheGateRefuses:
    def test_a_statement_with_no_states(self, tmp_path, register):
        body = {"format": "factory-line-audit/declaration/1",
                "reviewed_by": "x", "reviewed_on": "2026-09-09",
                "statements": [{"kind": "bad_state", "asset": "ST-01",
                                "tag": "state_running", "basis": "b"}]}
        path = tmp_path / "d.json"
        path.write_text(json.dumps(body), encoding="utf-8")
        with pytest.raises(formats.Refusal):
            gate([str(path)], register)

    def test_a_statement_with_no_basis(self, tmp_path, register, a_state_tag):
        """Every statement says what the declarer actually looked at. `Fault` is
        a state on one vendor and a menu on another; the spelling is not a
        source."""
        asset, tag = a_state_tag
        body = json.loads(open(reviewed(tmp_path, asset, tag, ["Faulted"])).read())
        del body["statements"][0]["basis"]
        path = tmp_path / "nobasis.json"
        path.write_text(json.dumps(body), encoding="utf-8")
        with pytest.raises(formats.Refusal):
            gate([str(path)], register)


class TestWhatTheGeneratorEmits:
    def test_a_reviewed_declaration_becomes_a_state_indicator(
            self, tmp_path, register, a_state_tag):
        asset, tag = a_state_tag
        gated = gate([reviewed(tmp_path, asset, tag, ["Faulted", "EStop"])],
                     register)
        model, _ = build(register, gated)
        assert "type: STATE" in model
        assert "bad: [Faulted, EStop]" in model
        assert "STABILITY" in model

    def test_no_normal_is_invented(self, tmp_path, register, a_state_tag):
        """Measured: `bad:` alone fires, and a word in neither list produces
        nothing either way. A `normal:` this package wrote would be a claim
        nobody reviewed."""
        asset, tag = a_state_tag
        gated = gate([reviewed(tmp_path, asset, tag, ["Faulted"])], register)
        model, _ = build(register, gated)
        assert "normal:" not in model

    def test_the_manifest_records_that_it_is_silent_below_0_1_12(
            self, tmp_path, register, a_state_tag):
        asset, tag = a_state_tag
        gated = gate([reviewed(tmp_path, asset, tag, ["Faulted"])], register)
        _, manifest = build(register, gated)
        rows = [r for r in manifest["exclusions"]
                if r.get("reason") == "bad_state_is_pinned"]
        assert rows, manifest["exclusions"]
        assert "0.1.12" in rows[0]["detail"]

    def test_a_state_tag_with_no_declaration_is_still_not_an_indicator(
            self, register):
        """Unchanged, and the reason had to be corrected: the note said the
        engine has no axiom for a machine state word, which stopped being true
        at 0.1.12. It is not that the engine cannot judge one -- it is that
        nobody has said which words are bad."""
        _, manifest = build(register, gate([], register))
        rows = [r for r in manifest["exclusions"]
                if r.get("reason") == "state_tag_is_not_an_indicator"]
        assert rows
        assert "no axiom" not in rows[0]["detail"]
        assert "0.1.12" in rows[0]["detail"]
