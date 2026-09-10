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


class TestAGateOnAnIntegerStateCode:
    """R3 from the 0.1.7 review, and a regression the S5 fix introduced.

    A PLC that serves its running flag as Int16 or Byte `0/1` is the common
    case, and after 0.1.7 it had no legal declaration at all. Measured, all
    three shapes:

      * no `open_when`        -> HardStop `gate_undecidable`
      * `open_when: [1]`      -> refused here as malformed, because every
                                 member had to be a `str`
      * `open_when: ["1"]`    -> accepted, and then `1 in ["1"]` is false, so
                                 every sample was withheld, nothing was fed,
                                 and the engine declined `missing_property` --
                                 which this package classes as its OWN defect
                                 and reports against the wrong subject

    Three ways to lose, and the only one the gate called wrong was the one that
    would have worked. `open_when` now takes `str | int | bool`, and the silent
    shape is a hard stop naming both types.

    Not a subclass of the string-gate class: inheriting re-ran that class's
    cases under this name, which reports eight passes about a subject this
    class is not testing.
    """

    STATE = TestTheGateReadsAStateWordAndNotItsTruthiness.STATE
    GATED = TestTheGateReadsAStateWordAndNotItsTruthiness.GATED

    def _ints(self, clean_walk, value, over=None):
        rows = clean_walk["samples"] if over is None else clean_walk["samples"][:over]
        for sample in rows:
            sample["nodes"][self.STATE]["v"] = value
        return clean_walk

    def _declared(self, register, tmp_path, words):
        import copy
        import json

        from factory_line_audit.declarations import gate
        body = copy.deepcopy(json.load(open(FIXTURE, encoding="utf-8")))
        for stmt in body["statements"]:
            if stmt["kind"] == "gate_on":
                if words is None:
                    stmt.pop("open_when", None)
                else:
                    stmt["open_when"] = words
        path = os.path.join(str(tmp_path), "ints.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(body, handle)
        return gate([path], register)

    def test_an_integer_state_code_is_a_legal_declaration(self, register,
                                                          clean_walk, tmp_path):
        gates = self._declared(register, tmp_path, [1])
        walk = self._ints(clean_walk, 1)
        from factory_line_audit.feeder import series_for
        series, withheld, _ = series_for(register, classify(register, walk),
                                         walk, gates)
        assert self.GATED not in withheld
        assert len(series[self.GATED]) == len(walk["samples"])

    def test_the_other_code_withholds_quietly(self, register, clean_walk,
                                              tmp_path):
        """`0` is not `1`, and that is a stopped station, not a bad
        declaration. It must not hard-stop."""
        gates = self._declared(register, tmp_path, [1])
        walk = self._ints(clean_walk, 0)
        from factory_line_audit.feeder import series_for
        _, withheld, _ = series_for(register, classify(register, walk), walk,
                                    gates)
        assert withheld[self.GATED] == len(walk["samples"])

    def test_a_string_declaration_against_an_integer_server_stops(
            self, register, clean_walk, tmp_path):
        """The silent case. Nothing here can ever be equal, so every sample
        would be withheld and the engine blamed for a missing property."""
        from factory_line_audit.feeder import HardStop, series_for
        gates = self._declared(register, tmp_path, ["1"])
        walk = self._ints(clean_walk, 1)
        with pytest.raises(HardStop) as caught:
            series_for(register, classify(register, walk), walk, gates)
        assert caught.value.name == "gate_type_mismatch"
        assert "'1' (str)" in caught.value.detail
        assert "(int)" in caught.value.detail

    def test_the_stop_is_a_claim_about_the_walk_not_one_sample(
            self, register, clean_walk, tmp_path):
        """A single odd reading is not a declaration that cannot apply. Held
        because the first version of this check fired per sample and broke the
        mixed-type case that the boolean gate test has always covered."""
        from factory_line_audit.feeder import series_for
        gates = self._declared(register, tmp_path, ["Running"])
        walk = self._ints(clean_walk, False, over=20)
        _, withheld, _ = series_for(register, classify(register, walk), walk,
                                    gates)
        assert withheld[self.GATED] == 20

    def test_a_boolean_server_may_be_declared_as_one(self, register, clean_walk,
                                                     tmp_path):
        """A PLC `BOOL` arrives as `True`, and `open_when: [1]` for it is a
        legitimate thing to write."""
        from factory_line_audit.feeder import series_for
        gates = self._declared(register, tmp_path, [1])
        walk = self._ints(clean_walk, True)
        series, withheld, _ = series_for(register, classify(register, walk),
                                         walk, gates)
        assert self.GATED not in withheld
        assert len(series[self.GATED]) == len(walk["samples"])

    def test_a_float_is_still_refused_by_the_declaration_gate(self, register,
                                                              tmp_path):
        """Equality on a float is a question about the PLC's scaling, not about
        the state machine, so the widening stops short of it."""
        import copy
        import json

        from factory_line_audit import formats
        from factory_line_audit.declarations import gate
        body = copy.deepcopy(json.load(open(FIXTURE, encoding="utf-8")))
        for stmt in body["statements"]:
            if stmt["kind"] == "gate_on":
                stmt["open_when"] = [1.5]
        path = os.path.join(str(tmp_path), "float.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(body, handle)
        with pytest.raises(formats.Refusal) as caught:
            gate([path], register)
        assert "open_when" in caught.value.message


class TestAGateTagThatNeverReads:
    """N4 from the 0.1.8 review, and the residual the R3 fix left.

    `gate_type_mismatch` asks whether any declared word could ever have equalled
    any value the server served. It is judged from a record written only when a
    gate reading arrived with a usable quality -- so a gate tag that is
    `Bad_*`/`Uncertain_*` for the WHOLE walk never reaches it. Every sample was
    withheld, the gated tag was never fed, the engine declined
    `missing_property`, and `classify()` returned `bridge_defect`: "a mapping bug
    in this package", at floor 2, about a state tag the server could not read.

    MEASURED before it was fixed (0.1.8 review, Sec. 6 run 4): a `clean.json`
    whose gate node carries `BadNoCommunication` on all fifty samples reported
    `bridge_defect: 1` and exit 2.
    """

    STATE = TestTheGateReadsAStateWordAndNotItsTruthiness.STATE
    GATED = TestTheGateReadsAStateWordAndNotItsTruthiness.GATED

    def _quality(self, clean_walk, word, over=None):
        rows = (clean_walk["samples"] if over is None
                else clean_walk["samples"][:over])
        for sample in rows:
            sample["nodes"][self.STATE]["q"] = word
        return clean_walk

    def test_a_gate_unreadable_all_walk_stops_and_names_the_gate(
            self, register, clean_walk, gated):
        walk = self._quality(clean_walk, "BadNoCommunication")
        with pytest.raises(HardStop) as caught:
            series_for(register, classify(register, walk), walk, gated)
        assert caught.value.name == "gate_unreadable"
        assert "state_running" in caught.value.detail
        assert "BadNoCommunication x50" in caught.value.detail
        assert "read usably in 50 sample(s)" in caught.value.detail

    def test_the_stop_says_it_is_not_this_package_s_defect(self, register,
                                                           clean_walk, gated):
        """The whole point: the old path reported the wrong subject, so the new
        message has to name the right one."""
        walk = self._quality(clean_walk, "BadNoCommunication")
        with pytest.raises(HardStop) as caught:
            series_for(register, classify(register, walk), walk, gated)
        assert "is what could not be read" in caught.value.detail

    def test_a_gate_readable_once_does_not_stop(self, register, clean_walk,
                                               gated):
        """The control, and the reason the claim is about the WALK. A gate that
        read usably in a single sample was consulted; the rest is a station that
        was stopped, or a patchy sensor, and both withhold quietly."""
        walk = self._quality(clean_walk, "BadNoCommunication",
                             over=len(clean_walk["samples"]) - 1)
        _, withheld, _ = series_for(register, classify(register, walk), walk,
                                    gated)
        assert withheld[self.GATED] == len(walk["samples"]) - 1

    def test_a_walk_whose_gate_reads_throughout_is_untouched(self, register,
                                                            clean_walk, gated):
        """The second control: the shipped corpus must be unaffected, or this
        stop fires on every healthy line."""
        _, withheld, _ = series_for(register, classify(register, clean_walk),
                                    clean_walk, gated)
        assert self.GATED not in withheld

    def test_an_unreadable_gate_is_not_reported_as_a_type_mismatch(
            self, register, clean_walk, gated):
        """The two stops are disjoint and the more basic one wins. A mismatch
        message here would name types nobody served."""
        walk = self._quality(clean_walk, "BadNoCommunication")
        with pytest.raises(HardStop) as caught:
            series_for(register, classify(register, walk), walk, gated)
        assert caught.value.name != "gate_type_mismatch"

    def test_the_engine_no_longer_blames_this_package(self, register, tmp_path):
        """End to end, through `run`, because the defect was in what the REPORT
        said and not in what the feeder returned. Needs the engine: skipped with
        a reason rather than silently, since a missing leg that leaves no trace
        reads as a leg that passed."""
        import json

        pytest.importorskip("arbiter_engine",
                            reason="the [detect] extra is not installed, so no "
                                   "decline can be classified here")
        from factory_line_audit.declarations import gate
        with open(os.path.join(CORPUS, "clean.json"), encoding="utf-8") as handle:
            walk = json.load(handle)
        for sample in walk["samples"]:
            sample["nodes"][self.STATE]["q"] = "BadNoCommunication"
        gated = gate([FIXTURE], register)
        model_text, manifest = build(register, gated)
        with pytest.raises(HardStop) as caught:
            run(model_text, register, classify(register, walk), walk, gated,
                manifest)
        assert caught.value.name == "gate_unreadable"

    def test_an_absent_gate_tag_reaches_the_same_stop(self, register,
                                                      clean_walk, gated):
        """O2 from the 0.1.9 review: the two states Stage 1 keeps apart both land
        here, and they are distinguishable only by the quality words the message
        carries. A gate node the address space does not hold is *not served in
        this sample*, fifty times."""
        for sample in clean_walk["samples"]:
            sample["nodes"].pop(self.STATE, None)
        presence = classify(register, clean_walk)
        graded = [row["state"] for row in presence["tags"]
                  if row["node"] == self.STATE]
        assert graded == ["absent"], (
            f"Stage 1 does not call this absent, so the comparison this test "
            f"makes is not the one it claims: {graded}")
        with pytest.raises(HardStop) as caught:
            series_for(register, presence, clean_walk, gated)
        assert caught.value.name == "gate_unreadable"
        assert "not served in this sample x50" in caught.value.detail, (
            f"an absent gate tag is reported with the same words as an "
            f"unreadable one, so a reader cannot tell which happened: "
            f"{caught.value.detail}")

    def test_an_absent_gate_tag_could_not_complete_rather_than_found(
            self, register, clean_walk, gated, tmp_path):
        """The exit code, which is the half O2 is actually about. Stage 1 floors
        the same tag at 1 -- a finding about the line -- and the run is 2, because
        no verdict about the gated tag was established. Asserted through `main`,
        since the mapping from a stop to an exit code lives there and nowhere
        else."""
        import json

        from factory_line_audit.cli import main
        presence_floor = classify(register, clean_walk)["exit"]
        for sample in clean_walk["samples"]:
            sample["nodes"].pop(self.STATE, None)
        absent_floor = classify(register, clean_walk)["exit"]
        assert absent_floor >= 1, (
            f"Stage 1 does not report the absence at all, so there is no second "
            f"reading to prefer between: {presence_floor} -> {absent_floor}")
        path = os.path.join(str(tmp_path), "walk.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(clean_walk, handle)
        code = main(["detect", "--register", REGISTER, "--walk", path,
                     "--declarations", FIXTURE])
        assert code == 2, (
            f"the stop reported {code}; the README says this exits 2 rather "
            f"than 1 and a reader counting findings would be told the line has "
            f"one")

    def test_the_message_claims_only_what_the_record_measures(self, register,
                                                             clean_walk, gated):
        """The asymmetric case, and the reason the sentence is narrow.

        The record is kept only for samples in which the GATED tag read. So a
        gate that reads usably somewhere the gated tag does not would make
        *never anywhere in this walk* false while the stop was still right to
        fire. Here the gated tag is unreadable for the first forty samples and
        the gate is unreadable for the last ten: the gate reads in forty of
        fifty, and the ten that mattered still got nothing.
        """
        gated_node = None
        for asset in register["assets"]:
            if asset["id"] == self.GATED[0]:
                gated_node = asset["tags"][self.GATED[1]]["node"]
        assert gated_node, "the gated tag is not in the register any more"
        for n, sample in enumerate(clean_walk["samples"]):
            if n < 40:
                sample["nodes"][gated_node]["q"] = "BadNoCommunication"
            else:
                sample["nodes"][self.STATE]["q"] = "BadNoCommunication"
        with pytest.raises(HardStop) as caught:
            series_for(register, classify(register, clean_walk), clean_walk,
                       gated)
        assert caught.value.name == "gate_unreadable"
        assert "read usably in 10 sample(s)" in caught.value.detail
        assert "anywhere in this walk" not in caught.value.detail
