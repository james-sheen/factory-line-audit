"""The exit contract, and the decline classes that feed it.

BRIDGES.md's exit contract says to adopt the three codes verbatim, so that
results from different bridges are comparable. This module is that adoption,
plus the one
thing the document insists is decided at design time rather than at runtime:
which class every engine decline lands in, and what floor that class carries.

The classes are in this file and not in the feeder deliberately. A floor chosen
while looking at a failing run is a floor chosen to make the run pass.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple

CLEAN = 0
FINDINGS = 1
INCOMPLETE = 2

MEANING = {CLEAN: "clean", FINDINGS: "findings", INCOMPLETE: "could-not-complete"}


def normalise(code: Any) -> Tuple[int, Any]:
    """Map anything to {0,1,2}, keeping the raw value beside it.

    BRIDGES: *a code outside {0,1,2} reads as 2, with the raw value kept beside
    it*. Both halves matter -- a bridge that clamps and forgets has destroyed
    the evidence that something returned 137.
    """
    if isinstance(code, bool) or not isinstance(code, int):
        return INCOMPLETE, code
    if code in (CLEAN, FINDINGS, INCOMPLETE):
        return code, code
    return INCOMPLETE, code


def compose(*codes: Any) -> int:
    """Maximum over the legs. An empty composition is 2, not 0.

    Composing nothing is the shape of a battery whose legs all failed to be
    collected, and reading that as clean is the exact error the contract exists
    to prevent.
    """
    normalised = [normalise(c)[0] for c in codes]
    if not normalised:
        return INCOMPLETE
    return max(normalised)


#: Every class this bridge routes an engine decline into, with the floor decided
#: here and the reason the floor is what it is. The engine reasons are the
#: closed vocabulary BRIDGES calls the requirements document; `_extra` records
#: the distinctions this
#: bridge draws that the reason string alone does not carry.
DECLINE_CLASSES: Dict[str, Dict[str, Any]] = {
    "warmup": {
        "floor": CLEAN,
        "reasons": ("insufficient_samples",),
        "why": "A fresh line that declines everything is making a true "
               "statement. Reported, never suppressed.",
    },
    "warmup_unreachable": {
        "floor": FINDINGS,
        "reasons": ("insufficient_samples",),
        "why": "The collector's cadence cannot reach the floor this check "
               "needs inside its window. A promise that can never be kept is "
               "a finding, not a warm-up.",
    },
    "undefined": {
        "floor": CLEAN,
        "reasons": ("undefined_for_values",),
        "why": "Nobody owes anything. Counted, and on no one's list.",
    },
    "gate_fired": {
        "floor": CLEAN,
        "reasons": ("precondition_unmet",),
        "why": "Routed to whoever owns the model, never to whoever owns the "
               "data. The engine will not say which way to read it.",
    },
    "stage1_known": {
        "floor": CLEAN,
        "reasons": ("missing_property", "no_current_value"),
        "why": "The engine agreeing with Stage 1, which already floored the "
               "run at 1 for the same source. Not counted twice.",
    },
    "bridge_defect": {
        "floor": INCOMPLETE,
        "reasons": ("missing_property", "no_current_value"),
        "why": "Stage 1 said this source WAS reading and the value still did "
               "not reach the model. A mapping bug in this package.",
    },
    "model_defect": {
        "floor": INCOMPLETE,
        "reasons": ("missing_role", "missing_config", "no_threshold",
                    "wrong_indicator_type", "missing_entity_type",
                    "no_rule_for_role"),
        "why": "This package generated the model. Nothing else will notice. "
               "`no_rule_for_role` is classed here BEFORE any release emits "
               "it. The engine splits it out of `missing_role` to say the "
               "model is right and the axiom simply has no rule for that kind "
               "of quantity -- for a hand-written model, nobody's fault. This "
               "package generates its model from a closed set of pairs: "
               "`latency` with RESPONSIVENESS, `percentage` and `count` with "
               "CONSISTENCY, `counter` with MONOTONICITY, BOUNDEDNESS wherever "
               "a reviewed declaration supplies a number. A pair the engine "
               "has no rule for is a pair this package should never have "
               "written, so the generator asked a question it did not mean. "
               "Two-sided for the reason A2 gave for `missing_entity_type`. "
               "WHAT THIS CHANGES IS THE REPORT, NOT THE VERDICT: an "
               "unclassified reason already floors at 2, so the exit code was "
               "right by accident. What was wrong was the sentence beside it "
               "-- `unclassified` says the engine is newer than its reader, "
               "which is false about a reason this package has considered.",
    },
    "declared_gap": {
        "floor": CLEAN,
        "reasons": ("no_threshold",),
        "why": "The engine declining a check this package ALREADY excluded and "
               "named in the manifest with a reason. Not a defect -- the two "
               "records agreeing. MONOTONICITY's rate arm is the case: it "
               "cannot be excluded separately from the reversal arm, so the "
               "model declares the axiom, the manifest records that no rate "
               "was declared, and the engine declines the arm.",
    },
    "stage1_known_absent": {
        "floor": CLEAN,
        "reasons": ("missing_entity_type",),
        "why": "The model pointed at an asset the walk did not serve, and "
               "Stage 1 already said so and already floored the run at 1. In a "
               "bridge that GENERATES its model from a register, an absent "
               "asset is a collection fact rather than a modelling error -- "
               "the register IS what the model believes exists. BRIDGES said "
               "to read it as a modelling error unconditionally until this "
               "package reported the case; it now states both sides.",
    },
    "engine_fault": {
        "floor": INCOMPLETE,
        "reasons": ("not_applicable", "checker_error"),
        "why": "Never a clean result. Anything inferred from this run is "
               "inferred from an unknown.",
    },
    "unclassified": {
        "floor": INCOMPLETE,
        "reasons": (),
        "why": "A reason this bridge has no class for. The engine is newer "
               "than its reader, and unmeasured never reads as clean.",
    },
}

#: The decline vocabulary this bridge was written against. Not a copy of the
#: engine's enum for use at runtime -- `feeder` reads the live enum -- but the
#: set the classes above were decided over. `probe_engine.py` compares the two
#: and the battery fails on a difference, which is how a vocabulary that grew
#: after this file was written becomes visible instead of falling into
#: `unclassified` quietly.
#:
#: `no_rule_for_role` is DELIBERATELY NOT HERE, though `model_defect` above
#: already classes it. This tuple records what was measured from a running
#: engine, and no released engine emits it: 0.1.13 is the newest on the index
#: and carries twelve reasons. Adding it here by hand would make this file
#: claim a measurement nobody took, and the live-vocabulary comparison would
#: refuse it anyway. It goes in the day a release emits it and a probe records
#: it, with that version written beside it.
VOCABULARY_AT_DESIGN_TIME = (
    "checker_error", "insufficient_samples", "missing_config",
    "missing_entity_type", "missing_property", "missing_role",
    "no_current_value", "no_threshold", "not_applicable",
    "precondition_unmet", "undefined_for_values", "wrong_indicator_type",
)


#: Finding classes, with the same design-time floors the decline classes carry.
#:
#: BRIDGES's exit contract now asks for this in as many words -- classify
#: findings the way
#: you classify declines, and give those classes floors too. It did not when this
#: package was written: the section covered declines only, and the implied rule
#: for findings was that any finding is a 1. That holds for a threshold breach,
#: which is a statement about a number somebody published. It does not hold for
#: an arm whose output is a tail probability. This class is the finding that
#: produced the guidance, kept here as the worked instance of it.
#:
#: MEASURED, probe H3/H4/H6 on 0.1.10: learned HOMEOSTASIS fires at 2 sigma
#: from the rolling baseline at `warning` and at 3 sigma at `critical`. Over
#: twelve independent stationary Gaussian series with nothing injected, the
#: warning arm fired on one of them -- about the tail mass beyond 2 sigma, which
#: is what it is by construction rather than by defect. A line with fifteen such
#: series therefore produces a warning on most healthy runs.
#:
#: So the warning arm of a LEARNED baseline is reported and floored at 0, and
#: the critical arm is floored at 1. The same axiom with a DECLARED setpoint is
#: floored at 1 in both arms: probe H6 put the same twelve series through a
#: declared setpoint and none fired, because a setpoint is a statement about the
#: plant rather than about the last thirty samples.
#:
#: This is the decision the corpus must not be allowed to make. Widening the
#: synthetic noise until the clean leg passes would be choosing the corpus.
FINDING_CLASSES: Dict[str, Dict[str, Any]] = {
    "baseline_deviation_warning": {
        "floor": CLEAN,
        "why": "learned HOMEOSTASIS at warning severity is a 2-sigma tail "
               "event on a rolling baseline nobody declared. Measured at "
               "roughly one series in twelve on stationary noise (probe H4). "
               "Reported in full; not a verdict.",
    },
    "declared": {
        "floor": FINDINGS,
        "why": "everything else. A number somebody published was crossed, a "
               "structure somebody declared did not hold, or a baseline "
               "deviation reached the critical arm.",
    },
}


def classify_finding(axiom: str, severity: str, *, learned_baseline: bool) -> str:
    """Which finding class, given what the model declared.

    `learned_baseline` is the bridge's own fact -- whether this indicator got a
    setpoint from a declaration -- and the engine does not carry it in the
    finding. Passing it in rather than inferring it from the finding string is
    the same discipline `classify` uses for Stage 1.
    """
    if (axiom == "HOMEOSTASIS" and learned_baseline
            and str(severity).lower() in ("warning", "low", "medium")):
        return "baseline_deviation_warning"
    return "declared"


def classify(reason: str, *, stage1_said_reading: Optional[bool] = None,
             floor_unreachable: bool = False,
             target_absent: Optional[bool] = None,
             recorded_gap: bool = False) -> str:
    """Reason plus this bridge's own knowledge -> class name.

    Two reasons are ambiguous on their own and the disambiguator is a fact only
    this bridge holds: whether Stage 1 saw the source reading. That is why the
    signature takes it rather than inferring it.
    """
    if reason == "insufficient_samples":
        return "warmup_unreachable" if floor_unreachable else "warmup"
    if reason == "no_threshold" and recorded_gap:
        # The manifest already named this exclusion, with a reason. An engine
        # that then declines it is agreeing, not reporting a defect -- and
        # reading agreement as a defect is how a bridge fails on a healthy line.
        # Measured: without this, a released engine carrying the rate
        # decline turns this package's clean corpus from exit 0 into exit 2.
        return "declared_gap"
    if reason == "missing_entity_type":
        if target_absent is None:
            return "unclassified"
        return "stage1_known_absent" if target_absent else "model_defect"
    if reason in ("missing_property", "no_current_value"):
        if stage1_said_reading is None:
            return "unclassified"
        return "bridge_defect" if stage1_said_reading else "stage1_known"
    for name, spec in DECLINE_CLASSES.items():
        if name in ("warmup", "warmup_unreachable", "stage1_known",
                    "stage1_known_absent", "declared_gap", "bridge_defect",
                    "unclassified"):
            continue
        if reason in spec["reasons"]:
            return name
    return "unclassified"


def floor_of(class_name: str) -> int:
    return DECLINE_CLASSES.get(class_name, DECLINE_CLASSES["unclassified"])["floor"]


def floors_over(class_names: Iterable[str]) -> int:
    """Compose the floors of a set of classes. No classes is clean here.

    Different from `compose()` on purpose: an empty *decline* set means the run
    declined nothing, which is a real and good outcome. An empty *leg* set
    means nothing ran.
    """
    return max([floor_of(c) for c in class_names] or [CLEAN])
