"""The contract, including the parts that only matter when something goes wrong."""
from __future__ import annotations

import pytest

from factory_line_audit.exit_contract import (
    CLEAN, DECLINE_CLASSES, FINDINGS, FINDING_CLASSES, INCOMPLETE,
    VOCABULARY_AT_DESIGN_TIME, classify, classify_finding, compose, floor_of,
    floors_over, normalise)


class TestTheThreeCodes:
    @pytest.mark.parametrize("raw,expected", [
        (0, 0), (1, 1), (2, 2), (3, 2), (-1, 2), (137, 2), (None, 2),
        ("0", 2), (True, 2), (1.0, 2)])
    def test_anything_outside_the_set_reads_as_two(self, raw, expected):
        assert normalise(raw)[0] == expected

    def test_the_raw_value_is_kept_beside_it(self):
        """Clamping and forgetting destroys the evidence that something
        returned 137, which is the only clue to what happened."""
        assert normalise(137) == (INCOMPLETE, 137)

    def test_a_bool_is_not_an_exit_code(self):
        """`True == 1` in Python, so a verb returning True would compose as
        findings. It is not an exit code and reads as 2."""
        assert normalise(True)[0] == INCOMPLETE

    def test_two_beats_one(self):
        assert compose(FINDINGS, INCOMPLETE) == INCOMPLETE

    def test_composing_nothing_is_two(self):
        """A battery whose legs all failed to be collected must not read clean."""
        assert compose() == INCOMPLETE

    def test_declining_nothing_is_clean(self):
        """The other direction: an empty DECLINE set is a real, good outcome."""
        assert floors_over([]) == CLEAN


class TestDeclineClassesAndTheirFloors:
    def test_every_engine_reason_has_a_class(self):
        for reason in VOCABULARY_AT_DESIGN_TIME:
            name = classify(reason, stage1_said_reading=False,
                            target_absent=False)
            assert name != "unclassified", reason

    def test_missing_entity_type_is_ambiguous_the_same_way(self):
        """BRIDGES says to treat it as a modelling error unconditionally. In a
        bridge that generates its model from a register, an asset the walk did
        not serve makes it a collection fact Stage 1 already reported."""
        assert classify("missing_entity_type") == "unclassified"
        assert classify("missing_entity_type", target_absent=True) == "stage1_known_absent"
        assert classify("missing_entity_type", target_absent=False) == "model_defect"
        assert floor_of("stage1_known_absent") == CLEAN
        assert floor_of("model_defect") == INCOMPLETE

    def test_a_reason_this_package_has_never_seen_is_two(self):
        """An engine newer than its reader. Unmeasured never reads as clean."""
        assert floor_of(classify("some_future_reason")) == INCOMPLETE

    def test_missing_role_and_no_rule_for_role_share_a_class(self):
        """The engine splits `no_rule_for_role` out of `missing_role` in the
        release after 0.1.13. Both say the same thing to a package that WROTE
        its own model, so both land in `model_defect` and a consumer counting
        one of them sees the total hold when the range resolves to that release.

        The exit code would not have moved either way -- an unclassified reason
        already floors at 2 -- so this pin is about the class and the sentence
        it carries, not the verdict. `unclassified` says the engine is newer
        than its reader, and that is false about a reason considered here.
        """
        assert classify("no_rule_for_role") == classify("missing_role")
        assert classify("no_rule_for_role") == "model_defect"

    def test_no_rule_for_role_is_not_in_the_recorded_vocabulary_yet(self):
        """The classes are a DECISION and may run ahead of the engine; this
        tuple is a MEASUREMENT and may not. No released engine emits this
        reason, so recording it would be claiming a probe nobody ran.

        This goes green again by running `probe_engine.py` against a release
        that emits it, and adding it with that version beside it -- in that
        order.
        """
        assert "no_rule_for_role" not in VOCABULARY_AT_DESIGN_TIME

    def test_the_ambiguous_pair_needs_stage_one(self):
        """`missing_property` means two different things and the engine cannot
        tell them apart. Without Stage 1's answer this must not guess."""
        assert classify("missing_property") == "unclassified"
        assert classify("missing_property", stage1_said_reading=True) == "bridge_defect"
        assert classify("missing_property", stage1_said_reading=False) == "stage1_known"

    def test_a_promise_the_cadence_cannot_keep_is_a_finding(self):
        assert floor_of(classify("insufficient_samples")) == CLEAN
        assert floor_of(classify("insufficient_samples",
                                 floor_unreachable=True)) == FINDINGS

    def test_an_unreviewed_foundation_and_an_engine_fault_both_floor_at_two(self):
        assert floor_of("engine_fault") == INCOMPLETE
        assert floor_of("model_defect") == INCOMPLETE

    def test_a_gap_this_package_already_named_is_agreement_not_a_defect(self):
        """MEASURED, and it is why this class exists. An engine build carrying
        the rate decline turns this package's CLEAN corpus from exit 0
        into exit 2 without it -- `could-not-complete` on a healthy line,
        because `no_threshold` reads as a model defect and this package writes
        the model.

        It is not a defect here. MONOTONICITY's rate arm cannot be excluded
        separately from the reversal arm, so the model declares the axiom and
        the manifest records that no rate was declared. The engine then
        declining that arm is the two records agreeing."""
        assert classify("no_threshold", recorded_gap=True) == "declared_gap"
        assert floor_of("declared_gap") == CLEAN

    def test_the_same_reason_is_still_a_defect_when_nothing_recorded_it(self):
        """The other half. Without this the class above would excuse every
        `no_threshold`, including one from an axiom this package emitted with
        no bound by mistake -- which nothing else would notice."""
        assert classify("no_threshold") == "model_defect"
        assert floor_of("model_defect") == INCOMPLETE

    def test_a_gate_that_fired_is_not_a_data_quality_ticket(self):
        assert classify("precondition_unmet") == "gate_fired"
        assert floor_of("gate_fired") == CLEAN

    def test_nobody_owes_anything_for_undefined(self):
        assert floor_of(classify("undefined_for_values")) == CLEAN


class TestFindingClasses:
    """The floors that BRIDGES gives declines and does not give findings."""

    def test_a_learned_baseline_warning_is_reported_not_failed(self):
        name = classify_finding("HOMEOSTASIS", "warning", learned_baseline=True)
        assert name == "baseline_deviation_warning"
        assert FINDING_CLASSES[name]["floor"] == CLEAN

    def test_the_critical_arm_of_the_same_axiom_still_fails(self):
        name = classify_finding("HOMEOSTASIS", "critical", learned_baseline=True)
        assert FINDING_CLASSES[name]["floor"] == FINDINGS

    def test_a_declared_setpoint_makes_even_a_warning_a_finding(self):
        """H6: the same twelve noisy series fired nothing against a declared
        setpoint. A deviation from a number somebody wrote down is not a tail
        event."""
        name = classify_finding("HOMEOSTASIS", "warning", learned_baseline=False)
        assert FINDING_CLASSES[name]["floor"] == FINDINGS

    def test_every_other_axiom_is_a_finding(self):
        for axiom in ("BOUNDEDNESS", "CONSERVATION", "STABILITY", "MONOTONICITY",
                      "CONSISTENCY", "CONNECTIVITY", "RESPONSIVENESS"):
            name = classify_finding(axiom, "warning", learned_baseline=True)
            assert FINDING_CLASSES[name]["floor"] == FINDINGS, axiom

    def test_every_class_carries_its_reasoning(self):
        """A floor with no written reason is a floor somebody will move."""
        for name, spec in list(FINDING_CLASSES.items()) + list(DECLINE_CLASSES.items()):
            assert spec["why"].strip(), name
