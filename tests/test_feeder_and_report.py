"""Stage 2: the hard stops, and the three ways of reporting. C5, C6, C7."""
from __future__ import annotations

import os

import pytest

from conftest import CORPUS, FIXTURE, REGISTER
from factory_line_audit import formats
from factory_line_audit.feeder import HardStop, run, series_for, unreachable_floors
from factory_line_audit.generator import build
from factory_line_audit.presence import classify
from factory_line_audit.report import attestation, human

pytest.importorskip("arbiter_engine", reason="Stage 2 needs the engine; Stage 1 "
                                             "does not, and that is the point")


@pytest.fixture
def ran(register, clean_walk, gated):
    model_text, manifest = build(register, gated)
    presence = classify(register, clean_walk)
    result = run(model_text, register, presence, clean_walk, gated, manifest)
    return model_text, manifest, presence, result


class TestOnlyWhatStageOneSawIsFed:
    def test_a_tag_that_never_read_is_not_fed(self, register, clean_walk, gated):
        press = next(a for a in register["assets"] if a["id"] == "PR-01")
        node = press["tags"]["die_temp_c"]["node"]
        for sample in clean_walk["samples"]:
            sample["nodes"][node] = {"v": None, "q": "Bad_SensorFailure"}
        presence = classify(register, clean_walk)
        series, _, _ = series_for(register, presence, clean_walk, gated)
        assert ("PR-01", "die_temp_c") not in series

    def test_a_state_word_is_never_fed_as_a_series(self, register, clean_walk, gated):
        """It becomes a property. Fed as a series it is an observation no
        declared indicator reads, which is a hard stop."""
        series, _, _ = series_for(register, presence_of(register, clean_walk), clean_walk, gated)
        assert not any(tag == "state_running" for _, tag in series)

    def test_every_point_carries_its_own_timestamp(self, register, clean_walk, gated):
        """Never the synthetic uniform ladder. Several axiom arms count inside
        a window measured backwards from now, so a reconstructed cadence moves
        the answer."""
        series, _, _ = series_for(register, presence_of(register, clean_walk),
                                  clean_walk, gated)
        for points in series.values():
            assert all(len(p) == 2 and p[0] is not None for p in points)


def presence_of(register, walk):
    return classify(register, walk)


class TestTheGateThisBridgeAppliesItself:
    def test_samples_outside_the_declared_state_are_withheld(
            self, register, clean_walk, gated):
        """The engine's `required_property` is read by CONNECTIVITY alone
        (probe G2), so a machine-state gate on a HOMEOSTASIS check cannot be
        expressed in the model. This bridge applies it at feed time."""
        station = next(a for a in register["assets"] if a["id"] == "ST-02")
        node = station["tags"]["state_running"]["node"]
        for sample in clean_walk["samples"][:20]:
            sample["nodes"][node]["v"] = False
        _, withheld, gates = series_for(register, presence_of(register, clean_walk),
                                        clean_walk, gated)
        assert gates[("ST-02", "cycle_time_s")] == "state_running"
        assert withheld[("ST-02", "cycle_time_s")] == 20

    def test_the_withholding_is_reported_because_the_engine_cannot_see_it(self, ran):
        _, _, _, result = ran
        assert "withheld_by_gate" in result


class TestHardStops:
    def test_a_value_the_engine_did_not_understand_stops_the_run(
            self, register, clean_walk, gated):
        """`check` grew a `dropped_declarations` leg only after 0.1.10, so this
        reads the same fact from `model_describe`, which has it on both."""
        model_text, manifest = build(register, gated)
        broken = model_text.replace("BOUNDEDNESS", "BOUNDEDNES", 1)
        with pytest.raises(HardStop) as caught:
            run(broken, register, classify(register, clean_walk), clean_walk,
                gated, manifest)
        assert caught.value.name == "dropped_declarations"
        assert "BOUNDEDNES" in caught.value.detail

    def test_a_model_that_attempts_nothing_stops_the_run(
            self, register, clean_walk, gated):
        model_text, manifest = build(register, gated)
        empty = "\n".join(model_text.split("\n")[:8]) + "\n  indicators: {}\n"
        with pytest.raises(HardStop) as caught:
            run(empty, register, classify(register, clean_walk), clean_walk,
                gated, manifest)
        assert caught.value.name in ("zero_invariants", "dropped_declarations")

    def test_every_hard_stop_names_itself_and_says_why(self):
        stop = HardStop("schema_version", "envelope said 2")
        assert stop.name and stop.detail and stop.name in str(stop)


class TestTheCadenceCanKeepItsPromises:
    def test_a_collector_too_slow_for_a_measured_floor_is_a_finding(self):
        floors = {"floors": {"HOMEOSTASIS": {"samples": 30, "max_cadence_s": 21240}}}
        assert unreachable_floors({"source": {"cadence_s": 60}}, floors) == {}
        slow = unreachable_floors({"source": {"cadence_s": 86400}}, floors)
        assert "HOMEOSTASIS" in slow and "21240" in slow["HOMEOSTASIS"]

    def test_no_cadence_declared_means_no_claim_either_way(self):
        assert unreachable_floors({"source": {}}, {"floors": {}}) == {}


class TestThreeWaysOfReporting:
    def test_the_attestation_says_all_three(self, ran):
        model_text, manifest, presence, result = ran
        att = attestation(register=None or {"line": "line1"}, presence=presence,
                          manifest=manifest, result=result, model_text=model_text,
                          declaration_paths=[FIXTURE], walk_path="w",
                          register_path=REGISTER)
        assert att["checked"]["invariants_attempted"] > 0
        assert "by_class" in att["declined"]
        assert att["not_established"]["excluded_from_model"]

    def test_the_engine_strings_are_quoted_verbatim(self, ran):
        """Paraphrasing machine output is how two copies of a remedy drift."""
        _, _, _, result = ran
        for row in result["declines"]:
            assert "engine_detail" in row and "engine_remedy" in row

    def test_one_outcome_line_is_contract_and_the_rest_is_prose(self, ran):
        model_text, manifest, presence, result = ran
        att = attestation(register={"line": "line1"}, presence=presence,
                          manifest=manifest, result=result, model_text=model_text,
                          declaration_paths=[FIXTURE], walk_path="w",
                          register_path=REGISTER)
        lines = [line for line in human(att).splitlines()
                 if line.startswith("OUTCOME")]
        assert len(lines) == 1
        assert f"exit={att['exit']}" in lines[0]

    def test_the_attestation_records_which_engine_answered(self, ran):
        _, _, _, result = ran
        assert result["engine_version"]
        assert result["vocabulary_live"]

    def test_a_vocabulary_wider_than_this_reader_knows_floors_the_run(self, ran):
        """An engine newer than its reader. Not a decline this package can
        classify -- a statement that it cannot classify them all."""
        from factory_line_audit.exit_contract import VOCABULARY_AT_DESIGN_TIME
        _, _, _, result = ran
        assert sorted(result["vocabulary_live"]) == sorted(VOCABULARY_AT_DESIGN_TIME)
