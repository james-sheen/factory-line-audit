"""The pin sweep records WHAT each release declined, not only how many.

A loaded sweep recorded `declined=7` for its last eight engine releases, where
every earlier release and every later re-run read 6. The evidence kept the
count alone, the re-run overwrote it, and nothing measured since reproduces
it, so which decline the seventh was is lost. Each release now records its
declines -- reason, axiom, entity, indicator -- from the attestation the same
run writes, and a release whose declines differ from the rest is named, with
what it added and what it lacked.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "battery"))

import probe_pin  # noqa: E402

EVIDENCE = ROOT / "battery" / "pin_evidence.json"


def _row(entity, reason="partially_checked", axiom="MONOTONICITY", indicator="parts_out"):
    return {"reason": reason, "axiom": axiom, "entity": entity, "indicator": indicator}


class TestTheRowsAreTheAttestations:

    def test_each_decline_is_named_by_four_fields_and_sorted(self):
        attestation = {"declined": {"rows": [
            dict(_row("ST-02"), engine_detail="prose", engine_remedy=None),
            dict(_row("ST-01"), floor=0, **{"class": "declared_gap"})]}}
        assert probe_pin.decline_rows(attestation) == [_row("ST-01"), _row("ST-02")]

    def test_an_attestation_with_no_declines_has_no_rows(self):
        assert probe_pin.decline_rows({"declined": {"total": 0, "rows": []}}) == []
        assert probe_pin.decline_rows({}) == []


class TestADisagreementNamesItself:

    def test_releases_that_agree_name_nothing(self):
        same = [_row("ST-01"), _row("ST-02")]
        results = {v: {"declined_rows": same} for v in ("0.2.1", "0.2.2", "0.2.3")}
        assert probe_pin.declined_differently(results) == {}

    def test_a_release_with_one_more_decline_is_named_with_it(self):
        same = [_row("ST-01")]
        extra = _row("CNV-01", reason="insufficient_samples", axiom="STABILITY",
                     indicator="mode")
        results = {"0.2.1": {"declined_rows": same}, "0.2.2": {"declined_rows": same},
                   "0.2.3": {"declined_rows": same + [extra]}}
        assert probe_pin.declined_differently(results) == {
            "0.2.3": {"added": [extra], "lacked": []}}

    def test_a_release_lacking_one_is_named_with_what_it_lacked(self):
        same = [_row("ST-01"), _row("ST-02")]
        results = {"0.2.1": {"declined_rows": same}, "0.2.2": {"declined_rows": same},
                   "0.2.3": {"declined_rows": same[:1]}}
        assert probe_pin.declined_differently(results) == {
            "0.2.3": {"added": [], "lacked": [_row("ST-02")]}}

    def test_a_release_that_recorded_nothing_is_left_out(self):
        same = [_row("ST-01")]
        results = {"0.1.7": {"declined_rows": None, "exit": 1},
                   "0.2.1": {"declined_rows": same}, "0.2.2": {"declined_rows": same}}
        assert probe_pin.declined_differently(results) == {}


class TestTheCommittedEvidenceCarriesThem:

    def test_every_engine_release_that_ran_names_as_many_declines_as_it_counted(self):
        body = json.loads(EVIDENCE.read_text())["distributions"]["arbiter-engine"]
        ran = {v: r for v, r in body["results"].items() if r.get("exit") == 0}
        assert ran, "no engine release ran, so this would pass over nothing"
        for version, result in ran.items():
            counted = int(result["outcome"].split("declined=")[1].split()[0])
            assert len(result["declined_rows"]) == counted, version

    def test_the_evidence_says_which_releases_declined_differently(self):
        body = json.loads(EVIDENCE.read_text())["distributions"]["arbiter-engine"]
        assert isinstance(body["declined_differently"], dict)
