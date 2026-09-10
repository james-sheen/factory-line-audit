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


class TestADeclaredResetChangesTheFaultTheOperatorIsHanded:
    """Plan-2 C.2, measured where it matters: at the far end, on one engine.

    Two counters on ONE station, fed BYTE-IDENTICAL series -- three resets to
    zero, packed inside the measured window. Everything else is held: same
    entity, same cadence, same axioms, same corpus. The only difference left in
    the world is that one is declared to reset in normal operation and the other
    is declared never to.

    `parts_out` is a shift counter; `parts_out_mes` is the MES record for the
    order, which is cumulative. Declaring that difference is the whole of C.2,
    and this is the evidence that declaring it reaches the engine rather than
    sitting in a JSON file nobody reads.
    """

    #: The drop floor is ZERO, and it has to be. Measured while writing this:
    #: the arm is chosen by the post-drop value against the STEP, not against
    #: the counter's magnitude -- a drop to 0.5 beside a step of 4 is a reset,
    #: the same 0.5 beside a step of 1 is a reversal, and 0.0 is a reset at
    #: every step tried. A real PLC counter resets to zero; a fixture that
    #: stops one short measures the other arm and reads as this test passing
    #: for its own reason. See probe A7.
    FLOOR = 0.0
    STEP = 1.0
    NODES = ("ns=2;s=ST02.PartsOut", "ns=2;s=ST02.PartsOutMES")

    @pytest.fixture
    def fed(self, register, clean_walk, gated):
        import datetime as dt
        walk = clean_walk
        samples = walk["samples"]
        # RESTAMPED to end now. Several arms count inside a window measured
        # backwards from the present, so a corpus built yesterday presents none
        # of them -- eleven declines reading *fewer points than can exhibit a
        # reversal* over fifty samples. The battery refuses a stale corpus; a
        # test cannot, so it stops depending on when the corpus was built.
        end = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        current = 8800.0
        drops = {len(samples) - 1 - 3 * i for i in range(3)}
        for n, sample in enumerate(samples):
            when = (end - dt.timedelta(seconds=60 * (len(samples) - 1 - n))
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
            sample["t"] = when
            current = self.FLOOR if n in drops else current + self.STEP
            for node in self.NODES:
                sample["nodes"][node] = {"v": current, "q": "Good", "t": when}
        model_text, manifest = build(register, gated)
        presence = classify(register, walk)
        result = run(model_text, register, presence, walk, gated, manifest)
        return {f["finding"]["problem_type"]: f["finding"]
                for f in result["findings_classified"]
                if f["finding"].get("entity_id") == "ST-02"
                and f["finding"].get("axiom") == "MONOTONICITY"}

    def test_the_series_reached_the_arm_at_all(self, fed):
        """The non-vacuity leg. If the window has moved or the shape is wrong,
        both rules below are true of an empty set."""
        assert fed, ("no MONOTONICITY finding on either counter, so neither "
                     "rule below is evidence of anything")

    def test_the_counter_that_resets_is_reported_as_resetting(self, fed):
        assert "monotonicity_reset_storm:parts_out" in fed

    def test_the_record_that_must_not_reset_is_reported_as_going_backwards(
            self, fed):
        """The same three drops, named as what they are for this tag. Before
        C.2 both counters inherited the engine's default and a cumulative MES
        record going backwards was reported as a routine reset."""
        assert "monotonicity_reversal:parts_out_mes" in fed

    def test_the_two_are_not_the_same_finding(self, fed):
        """Stated separately because it is the claim: one declaration, two
        different faults out of identical data."""
        assert {"monotonicity_reset_storm:parts_out",
                "monotonicity_reversal:parts_out_mes"} <= set(fed)
        assert "monotonicity_reset_storm:parts_out_mes" not in fed
        assert "monotonicity_reversal:parts_out" not in fed


class TestTheGateReadsAStateWordAndNotItsTruthiness:
    """S5 from the 0.1.6 review, and it was right.

    The gate was `bool(gate_row.get("v"))`. A PLC state is usually an
    enumeration word, and every non-empty word is true in Python -- so a station
    reporting `Stopped` opened the gate, the samples were fed, and the package
    reported a verdict about a takt the station was not running to. The corpus
    fed the boolean `True`, so the one test covering the gate covered the one
    case that worked.

    `open_when` lists the words that mean the check applies. Where a declaration
    does not list them and the value is not a boolean, this package stops rather
    than guesses: which word means running is a fact about the state machine.
    """

    STATE = "ns=2;s=ST02.Running"
    GATED = ("ST-02", "cycle_time_s")

    def _walk_with(self, clean_walk, word, over=20):
        for sample in clean_walk["samples"][-over:]:
            sample["nodes"][self.STATE]["v"] = word
        return clean_walk

    def _gated(self, register, walk, gated):
        from factory_line_audit.feeder import series_for
        presence = classify(register, walk)
        _, withheld, _ = series_for(register, presence, walk, gated)
        return withheld

    def test_the_corpus_now_carries_a_word_a_plc_would_produce(self, clean_walk):
        """Non-vacuity. With a boolean here, every rule below is about a case
        the shipped corpus cannot reach."""
        value = clean_walk["samples"][0]["nodes"][self.STATE]["v"]
        assert isinstance(value, str), value

    def test_a_running_station_is_not_withheld(self, register, clean_walk, gated):
        assert self.GATED not in self._gated(register, clean_walk, gated)

    def test_a_stopped_station_is_withheld_sample_by_sample(self, register,
                                                            clean_walk, gated):
        walk = self._walk_with(clean_walk, "Stopped")
        assert self._gated(register, walk, gated).get(self.GATED) == 20

    def test_any_other_word_is_withheld_too(self, register, clean_walk, gated):
        """Not a list of bad words -- a list of the one good one. `Changeover`
        is not in `open_when`, and nobody had to think of it."""
        walk = self._walk_with(clean_walk, "Changeover", over=7)
        assert self._gated(register, walk, gated).get(self.GATED) == 7

    def test_an_undeclared_word_gate_stops_rather_than_guessing(
            self, register, clean_walk, tmp_path):
        """The same declaration with `open_when` removed, against the same
        walk. Python truthiness would have opened the gate for every sample."""
        import copy
        import json

        from factory_line_audit.declarations import gate
        from factory_line_audit.feeder import HardStop
        with open(FIXTURE, encoding="utf-8") as handle:
            body = json.load(handle)
        body = copy.deepcopy(body)
        for stmt in body["statements"]:
            if stmt["kind"] == "gate_on":
                stmt.pop("open_when")
        path = os.path.join(str(tmp_path), "d.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(body, handle)
        without = gate([path], register)
        with pytest.raises(HardStop) as caught:
            self._gated(register, clean_walk, without)
        assert caught.value.name == "gate_undecidable"
        assert "open_when" in caught.value.detail

    def test_a_boolean_state_still_reads_as_a_boolean(self, register, clean_walk,
                                                      tmp_path):
        """The case that used to be the only one. A register whose state tag
        really is a boolean must keep working with no `open_when` at all."""
        import copy
        import json

        from factory_line_audit.declarations import gate
        with open(FIXTURE, encoding="utf-8") as handle:
            body = copy.deepcopy(json.load(handle))
        for stmt in body["statements"]:
            if stmt["kind"] == "gate_on":
                stmt.pop("open_when")
        path = os.path.join(str(tmp_path), "d.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(body, handle)
        without = gate([path], register)
        for n, sample in enumerate(clean_walk["samples"]):
            sample["nodes"][self.STATE]["v"] = n < 30
        assert self._gated(register, clean_walk, without).get(self.GATED) == 20
