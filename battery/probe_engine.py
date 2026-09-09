#!/usr/bin/env python3
"""C3: measure the engine we pin. Do not read it.

BRIDGES C3: *derive what it will judge, decline, or excuse by running every arm
of every relevant axiom against the exact version you pin. Behaviour no probe
covered is neither handled nor unhandled -- it is unmeasured, and unmeasured
never reads as clean. Write the probes as code that re-runs, never as a table in
a document.*

This file is that code. It measures and prints; it asserts nothing. Every number
the rest of this package uses -- corpus size, sample floors, which arm of which
axiom fires on what -- comes out of `engine_floors.json`, which this writes.

Run it again on any pin change. A probe that has not been re-run against the
resolved version is a table in a document with extra steps.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import math
import os
import contextlib
import sys

from arbiter_engine.api import EngineSession, check, model_describe
from arbiter_engine.types import NotEvaluatedReason
import arbiter_engine

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "engine_floors.json")
#: REAL now, and it has to be. Every series below is built backwards from this
#: and every arm the engine counts inside a window measures backwards from the
#: real clock -- so a frozen NOW is a probe with an expiry date.
#:
#: It was frozen at 2026-09-03T12:00Z, the day it last ran. Six days later the
#: series all ended six days in the past, every window shorter than that saw
#: nothing, S1 and K6 measured None where the committed evidence records 10 and
#: a 300 s horizon, and the script died deriving a corpus size from a None. The
#: file every number in this package comes from was a snapshot nobody could
#: reproduce, and nothing went red because no leg runs this probe.
NOW = _dt.datetime.now(_dt.timezone.utc)


def model(indicators: str, entity_types="[A]", extra="") -> str:
    return f"""
domain:
  id: probe
  name: Probe
  entity_types: {entity_types}
{extra}  indicators:
{indicators}
"""


def run(model_text, entities, series=None, relationships=None):
    """Load, feed, check. stderr is swallowed: the loader narrates, and the
    narration is not the surface a caller can query."""
    session = EngineSession()
    with contextlib.redirect_stderr(io.StringIO()) as err:
        session.load_model(model_text)
        for entity_id, entity_type, properties in entities:
            session.add_entity(entity_id, entity_type, properties=properties)
        for entity_id, prop, points in (series or []):
            session.add_observations(entity_id, prop, points)
        for src, dst, rel in (relationships or []):
            session.add_relationship(src, dst, rel)
        envelope = check(session).to_dict()
        described = model_describe(session).to_dict()
    envelope["_stderr"] = err.getvalue().strip().splitlines()
    envelope["_unread_fields"] = (described.get("model") or {}).get("unread_fields", [])
    return envelope


def stamps(n, cadence_s, end=NOW):
    return [end - _dt.timedelta(seconds=cadence_s * (n - 1 - i)) for i in range(n)]


def ts(values, cadence_s=60.0):
    return list(zip(stamps(len(values), cadence_s), values))


def fired(env, axiom=None, entity=None):
    return [f for f in env.get("findings", [])
            if (axiom is None or f.get("axiom") == axiom)
            and (entity is None or f.get("entity_id") == entity)]


def declined(env, axiom=None):
    return [d for d in env.get("not_checked", [])
            if axiom is None or d.get("axiom") == axiom]


def first_n_where(lo, hi, predicate):
    """Smallest n in [lo, hi] where predicate(n); None if never."""
    for n in range(lo, hi + 1):
        if predicate(n):
            return n
    return None


RESULT = {
    "measured_on": NOW.isoformat(),
    "engine_version": arbiter_engine.__version__,
    "engine_file": os.path.dirname(arbiter_engine.__file__),
    "python": sys.version.split()[0],
    "probes": {},
    "floors": {},
}


def record(name, question, value, note=""):
    # A DUPLICATE NAME IS REFUSED, because overwriting one is silent and its
    # consequence is not. `S1` was recorded twice: the second answer replaced
    # expect_variation's sample floor with a dict, and the derivation at the end
    # raised a TypeError several hundred lines later. Getting the same collision
    # twice in one sitting is what made this a guard rather than more care.
    if name in RESULT["probes"]:
        raise SystemExit(f"probe {name} is recorded twice; the first was "
                         f"{RESULT['probes'][name]['question']!r}")
    RESULT["probes"][name] = {"question": question, "measured": value, "note": note}
    print(f"  {name:<6} {question}")
    print(f"         -> {value}")
    if note:
        print(f"            {note}")



# ------------------------------------------------------------- state words
# P5. Named D. S is expect_variation and B is the property/history pair --
# both were already taken, and both were taken by me in turn. `record` now
# refuses a duplicate rather than overwriting one.
#  A STATE indicator listing STABILITY and a reviewed `bad:`. The engine
# fires from 0.1.12 and is SILENT below it -- accepted, no finding, and NOT
# reported by `unread_fields`, which does report a key nobody reads. A
# consumer cannot tell an inert declaration from a healthy machine, so the
# manifest has to say so and this is where the claim comes from.
print("D -- a declared bad state")
_STATE_MODEL = model("""    Station:
      - name: mode
        type: STATE
        axioms: [STABILITY]
        bad: [Faulted]
""", entity_types="[Station]")
_bad = run(_STATE_MODEL, [("ST-01", "Station", {"mode": "Faulted"})])
_ok = run(_STATE_MODEL, [("ST-01", "Station", {"mode": "Auto"})])
record("D1", "does a declared bad state fire on this engine",
       {"fires": [(f.get("axiom"), f.get("problem_type"))
                  for f in _bad.get("findings") or []],
        "quiet_when_not_bad": not (_ok.get("findings") or []),
        "unread_fields": _bad["_unread_fields"]},
       "silent at 0.1.10 and 0.1.11, fires `declared_bad_state` from 0.1.12; "
       "`unread_fields` is empty either way, so nothing but this probe "
       "distinguishes the two")

_UNKNOWN = model("""    Station:
      - name: mode
        type: STATE
        axioms: [STABILITY]
        bad: [Faulted]
        nonsense_field: 7
""", entity_types="[Station]")
record("D2", "can unread_fields report a key at all, on this engine",
       run(_UNKNOWN, [("ST-01", "Station", {"mode": "Faulted"})])["_unread_fields"],
       "the non-vacuity control for D1: an empty answer there is only evidence "
       "if this one is not empty")

# ---------------------------------------------------------------- vocabulary
print("V -- the decline vocabulary")
vocab = sorted(r.value for r in NotEvaluatedReason)
record("V1", "how many decline reasons does this engine define",
       {"count": len(vocab), "reasons": vocab})
RESULT["vocabulary"] = vocab

env = run(model("""    A:
      - name: p
        type: NUMERIC
        axioms: [BOUNDEDNES]
        warning: 1
        critical: 2
"""), [("a1", "A", {"p": 5})])
record("V2", "is a misspelled axiom visible on check, or only on model_describe",
       {"on_check": "dropped_declarations" in env,
        "on_model_describe": [f for f in env["_unread_fields"]
                              if f.get("reason") == "unknown_value"] != [],
        "invariants": env["checked"]["invariants"]},
       "the check the author wrote did not run; whether the envelope says so "
       "is the question a bridge's hard stop depends on")

# --------------------------------------------------------------- BOUNDEDNESS
print("\nB -- BOUNDEDNESS")
env = run(model("""    A:
      - name: p
        type: NUMERIC
        axioms: [BOUNDEDNESS]
        warning: 80
        critical: 95
"""), [("a1", "A", {"p": 99})])
record("B1", "property only, no history: does it judge",
       {"findings": len(fired(env, "BOUNDEDNESS")), "declined": len(declined(env))})

env = run(model("""    A:
      - name: p
        type: NUMERIC
        axioms: [BOUNDEDNESS]
        warning: 80
        critical: 95
"""), [("a1", "A", {})], [("a1", "p", ts([99.0] * 40))])
record("B2", "history but no property: what reason",
       {"declined": [d["reason"] for d in declined(env, "BOUNDEDNESS")]})

# --------------------------------------------------------------- MONOTONICITY
print("\nM -- MONOTONICITY")

MONO = """    A:
      - name: c
        type: NUMERIC
        role: count
        axioms: [MONOTONICITY]
        monotonicity:
          expected_direction: increasing
{block}"""


def mono(values, cadence=60.0, block=""):
    return run(model(MONO.format(block=block)),
               [("a1", "A", {"c": values[-1]})], [("a1", "c", ts(values, cadence))])


def arm(env, which):
    """Only the named arm. MONOTONICITY has two and they are both reported
    under one axiom, so a probe that filters on the axiom is reading whichever
    one happened to fire. The first pass of this file climbed a ladder at ten
    units a minute and read the RATE arm's finding as the REVERSAL arm's floor."""
    return [f for f in fired(env, "MONOTONICITY")
            if which in str(f.get("problem_type", ""))]


def reversals_at_end(k, n=50, step=5.0, offset=0):
    """k backward steps packed at the end of a rising series."""
    values, current = [], 0.0
    down = {n - 1 - offset - 2 * i for i in range(k)}
    for i in range(n):
        current += -step if i in down else step
        values.append(current)
    return values


record("M1", "how many recent reversals before the reversal arm fires",
       {"fires_at": first_n_where(0, 12, lambda k: bool(
            arm(mono(reversals_at_end(k)), "reversal"))),
        "per_count": {k: bool(arm(mono(reversals_at_end(k)), "reversal"))
                      for k in range(0, 6)}},
       "MODELING.md states the default reversal_tolerance is 3")

tol = {}
for t in (1, 2, 3, 5):
    tol[t] = first_n_where(0, 12, lambda k, tt=t: bool(arm(
        mono(reversals_at_end(k),
             block=f"          reversal_tolerance: {tt}\n"), "reversal")))
record("M2", "with reversal_tolerance declared, at how many reversals it fires",
       tol, "confirms the count is the declared tolerance and not an offset "
            "from it")

ages = {}
for offset in (0, 5, 10, 12, 15, 20, 30):
    ages[f"{offset} samples back"] = bool(
        arm(mono(reversals_at_end(6, offset=offset)), "reversal"))
record("M3", "THE WINDOW, WHICH IS THE ONE THAT BITES: how far back can six "
             "reversals sit at 60 s cadence and still be counted", ages,
       "BRIDGES states the count-inside-a-window trap for insufficient_samples "
       "only. It applies to every count-based tolerance, and this is one: a "
       "50-sample corpus with reversals spread through it fires at six, and "
       "with the same six at the end fires at three. Neither number is the "
       "tolerance; the window is doing the work")

spread = {}


def _spread(k, n, step=5.0):
    values, current = [], 0.0
    down = {3 + i * 3 for i in range(k)}
    for i in range(n):
        current += -step if i in down else step
        values.append(current)
    return values


for n in (12, 20, 30, 60):
    spread[n] = first_n_where(0, 20, lambda k, nn=n: bool(
        arm(mono(_spread(k, nn)), "reversal")))
record("M4", "the same tolerance measured with reversals SPREAD through the "
             "corpus rather than packed at the end", spread,
       "one engine behaviour, four different apparent tolerances, decided by "
       "where the injector put the fault")


def monotonic_rate(per_second, n=30, cadence=60.0, block=""):
    values = [float(i * per_second * cadence) for i in range(n)]
    return mono(values, cadence, block)


rates = {}
for rate in (0.01, 0.05, 0.09, 0.1, 0.11, 0.4, 0.49, 0.5, 0.51, 1.0, 50.0):
    found = arm(monotonic_rate(rate), "rate")
    rates[rate] = {"fired": bool(found),
                   "severity": found[0]["severity"] if found else None}
record("R1", "THE ARM THE FIRST PASS MISSED: at what climb rate does the rate "
             "arm fire, with no rate declared", rates,
       "a counter faster than this is a finding the model never asked for, "
       "answered from an engine default rather than declined no_threshold")

declared = {}
for rate in (0.5, 50.0, 200.0):
    found = arm(monotonic_rate(
        rate, block="          rate_warning: 100\n"
                    "          rate_critical: 500\n"), "rate")
    declared[rate] = {"fired": bool(found),
                      "severity": found[0]["severity"] if found else None}
record("R2", "does a declared rate_warning/rate_critical displace the default",
       declared, "if it does, a fast counter is declarable and the clean "
                 "corpus can be quiet without choosing the corpus")

# ------------------------------------------------ allow_reset / reset_tolerance
print("\nA -- allow_reset and reset_tolerance")

#: A counter climbing slowly enough that the RATE arm cannot fire on the pinned
#: engine (its undeclared default is 0.1/s warning, probe R1). Everything below
#: is about the reset arm, and a ladder fast enough to trip the rate arm would
#: have produced findings from the wrong one -- which is exactly the mistake the
#: M probes made and had to be rebuilt for.
RESET_STEP = 4.0          # 4 per 60 s = 0.067/s, under the 0.1/s default


def resets(count, n=50, spacing=3, floor=0.5):
    """A rising counter with `count` drops to near zero, packed at the end.

    Packed deliberately: probe M3 measured a window on the reversal arm, and a
    reset is counted by the same checker. Spreading them through the corpus
    would measure the window again rather than the tolerance.
    """
    values, current = [], 0.0
    drops = {n - 1 - spacing * i for i in range(count)}
    for i in range(n):
        current = floor if i in drops else current + RESET_STEP
        values.append(current)
    return values


def reset_run(values, allow=True, block="", cadence=60.0):
    allow_line = f"          allow_reset: {'true' if allow else 'false'}\n"
    return mono(values, cadence, allow_line + block)


record("A1", "with allow_reset TRUE, how many drops to near zero before the "
             "reset arm says anything",
       {"fires_at": first_n_where(0, 10, lambda k: bool(
            arm(reset_run(resets(k)), "reset"))),
        "per_count": {k: [f["problem_type"] for f in
                          fired(reset_run(resets(k)), "MONOTONICITY")]
                      for k in range(0, 6)},
        "note": "per_count shows EVERY arm, so the contamination is visible "
                "rather than filtered away: a drop steepens the fitted slope "
                "and the rate arm answers too. fires_at is the reset arm only"},
       "MODELING.md says allow_reset excuses a drop-to-near-zero INDIVIDUALLY "
       "and that reset_tolerance is the separate count of them; this is the "
       "count, measured")

record("A2", "with allow_reset FALSE, which arm answers and at what count",
       {"reversal_fires_at": first_n_where(0, 10, lambda k: bool(
            arm(reset_run(resets(k), allow=False), "reversal"))),
        "reset_fires_at": first_n_where(0, 10, lambda k: bool(
            arm(reset_run(resets(k), allow=False), "reset"))),
        "per_count": {k: [f["problem_type"] for f in
                          fired(reset_run(resets(k), allow=False), "MONOTONICITY")]
                      for k in range(0, 5)}},
       "if one drop is a finding here and not above, `allow_reset` is the switch "
       "the guide describes and the tolerance only applies when it is on")

tol = {}
for t in (1, 2, 5):
    tol[t] = first_n_where(0, 12, lambda k, tt=t: bool(arm(
        reset_run(resets(k), block=f"          reset_tolerance: {tt}\n"),
        "reset")))
record("A3", "with reset_tolerance declared, at how many drops it fires", tol,
       "reads whether the declared number IS the firing count, as the reversal "
       "tolerance turned out to be")

record("A4", "IS A RESET ALSO COUNTED AS A REVERSAL", {
    "allow_reset true -- reversal arm ever fires": any(
        arm(reset_run(resets(k)), "reversal") for k in range(0, 9)),
    "allow_reset true -- reset arm ever fires": any(
        arm(reset_run(resets(k)), "reset") for k in range(0, 9)),
    "allow_reset false -- reversal arm ever fires": any(
        arm(reset_run(resets(k), allow=False), "reversal") for k in range(0, 9)),
    "allow_reset false -- reset arm ever fires": any(
        arm(reset_run(resets(k), allow=False), "reset") for k in range(0, 9)),
}, "the two tolerances default to the same number and are counted separately "
   "on purpose. If a drop lands in BOTH counters, a bridge that declares one of "
   "them is silently moving the other")

ages = {}
for offset in (0, 5, 10, 15, 25):
    values, current = [], 0.0
    drops = {50 - 1 - offset - 3 * i for i in range(6)}
    for i in range(50):
        current = 0.5 if i in drops else current + RESET_STEP
        values.append(current)
    ages[f"{offset} samples back"] = bool(arm(reset_run(values), "reset"))
record("A5", "how far back can six drops sit and still be counted", ages,
       "the reversal arm's window bit this package once already; the reset arm "
       "is counted by the same checker and is not assumed to differ")

# --------------------------------------------------------------- HOMEOSTASIS
print("\nH -- HOMEOSTASIS")


def homeostasis_learned(n, cadence=60.0, sigma_shift=0.0, spread=1.0, seed=7):
    import random
    rng = random.Random(seed)
    values = [100.0 + rng.gauss(0, spread) for _ in range(n)]
    if sigma_shift:
        values[-1] = 100.0 + sigma_shift * spread
    env = run(model("""    A:
      - name: m
        type: NUMERIC
        axioms: [HOMEOSTASIS]
"""), [("a1", "A", {"m": values[-1]})], [("a1", "m", ts(values, cadence))])
    return env


record("H1", "how many samples before learned HOMEOSTASIS stops declining",
       first_n_where(2, 60, lambda k: not declined(homeostasis_learned(k), "HOMEOSTASIS")),
       "the widest sample floor in the format")

window = {}
for cadence_h in (1, 4, 5, 5.5, 5.7, 5.79, 5.9, 6, 8, 24):
    env = homeostasis_learned(30, cadence=cadence_h * 3600)
    window[f"{cadence_h}h"] = {
        "declined": [d["reason"] for d in declined(env, "HOMEOSTASIS")] or None,
        "span_days": round(29 * cadence_h / 24.0, 2)}
record("H2", "30 samples at widening cadence: where does the window cut them off",
       window,
       "a floor is a count inside a window; a collector slower than this can "
       "never present it, however long it runs")

zs = {}
for z in (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 6.0):
    env = homeostasis_learned(50, sigma_shift=z)
    found = fired(env, "HOMEOSTASIS")
    zs[z] = {"fired": bool(found),
             "severity": found[0]["severity"] if found else None}
record("H3", "at what deviation from the learned baseline does it fire, and at "
             "what severity", zs,
       "this is what decides whether a corpus of noisy stationary series can "
       "ever be quiet")

noise = {}
import random as _random
for seed in range(12):
    env = homeostasis_learned(50, seed=seed)
    found = fired(env, "HOMEOSTASIS")
    noise[seed] = bool(found)
record("H4", "over 12 independent Gaussian series with no injected shift, how "
             "often does learned HOMEOSTASIS fire",
       {"fired": sum(noise.values()), "of": len(noise), "per_seed": noise},
       "the false-positive rate a clean corpus inherits per learned series")

env = run(model("""    A:
      - name: m
        type: NUMERIC
        axioms: [HOMEOSTASIS]
        homeostasis:
          setpoint: 60
          tolerance: 3
"""), [("a1", "A", {"m": 70.0})], [("a1", "m", ts([70.0]))])
record("H5", "declared setpoint: how many samples does it need",
       {"samples": 1, "findings": len(fired(env, "HOMEOSTASIS")),
        "declined": [d["reason"] for d in declined(env, "HOMEOSTASIS")]},
       "the way past the widest floor in the format")

setpoint_noise = {}
for seed in range(12):
    import random
    rng = random.Random(seed)
    values = [60.0 + rng.gauss(0, 1.0) for _ in range(50)]
    env = run(model("""    A:
      - name: m
        type: NUMERIC
        axioms: [HOMEOSTASIS]
        homeostasis:
          setpoint: 60
          tolerance: 3
"""), [("a1", "A", {"m": values[-1]})], [("a1", "m", ts(values))])
    setpoint_noise[seed] = bool(fired(env, "HOMEOSTASIS"))
record("H6", "same 12 noisy series, but with a declared setpoint at 3 sigma "
             "tolerance", {"fired": sum(setpoint_noise.values()), "of": 12},
       "if this is 0 where H4 is not, the remedy is a declaration rather than "
       "a quieter corpus")

# ------------------------------------------------------------------ STABILITY
print("\nS -- STABILITY")


def stability_flat(n):
    return run(model("""    A:
      - name: m
        type: NUMERIC
        axioms: [STABILITY]
        expect_variation: true
"""), [("a1", "A", {"m": 5.0})], [("a1", "m", ts([5.0] * n))])


record("S1", "expect_variation on a flat series: sample floor",
       first_n_where(2, 40, lambda k: bool(fired(stability_flat(k), "STABILITY"))))


def stability_wave(period, n=60, amplitude=0.27, block=""):
    values = [100.0 * (1 + amplitude * math.sin(2 * math.pi * i / period))
              for i in range(n)]
    if period == 2:
        values = [100.0 * (1 + amplitude * (1 if i % 2 else -1)) for i in range(n)]
    return run(model(f"""    A:
      - name: m
        type: NUMERIC
        axioms: [STABILITY]
{block}"""), [("a1", "A", {"m": values[-1]})], [("a1", "m", ts(values))])


waves = {}
for period in (2, 4, 6, 8):
    env = stability_wave(period)
    waves[period] = bool(fired(env, "STABILITY"))
record("S2", "default arm: which oscillation periods fire, up to 60 samples", waves,
       "if only period 2 fires, the default detector is period-2 by construction")

slow_block = ("        stability:\n"
              "          detect_slow_oscillation: true\n"
              "          min_amplitude: 0.10\n"
              "          min_crossings: 4\n")
slow = {}
for period in (2, 4, 6, 8):
    slow[period] = bool(fired(stability_wave(period, block=slow_block), "STABILITY"))
record("S3", "with detect_slow_oscillation: which periods fire", slow)


def stability_noise(seed, block=slow_block):
    import random
    rng = random.Random(seed)
    values = [100.0 + rng.gauss(0, 1.0) for _ in range(50)]
    return run(model(f"""    A:
      - name: m
        type: NUMERIC
        axioms: [STABILITY]
{block}"""), [("a1", "A", {"m": values[-1]})], [("a1", "m", ts(values))])


def stability_partly_flat(k, n=50, seed=3):
    """A series that varied and then stopped, k samples ago."""
    import random
    rng = random.Random(seed)
    values = [8500.0 + rng.gauss(0, 380.0) for _ in range(n - k)] + [8500.0] * k
    return run(model("""    A:
      - name: m
        type: NUMERIC
        axioms: [STABILITY]
        expect_variation: true
"""), [("a1", "A", {"m": values[-1]})], [("a1", "m", ts(values))])


record("S5", "a probe that DIED PART WAY THROUGH: how many trailing flat "
             "samples of fifty before expect_variation says so",
       {k: bool(fired(stability_partly_flat(k), "STABILITY"))
        for k in (5, 10, 20, 30, 40, 45, 49, 50)},
       "MODELING.md describes this arm as *a reading that never moves is a dead "
       "probe*. If only k=50 fires, the arm means never moved in the WHOLE fed "
       "history, and a sensor that froze this morning is not reported until "
       "every varying sample has aged out. That is a much weaker check than the "
       "sentence suggests, and it decides how a fault must be injected")

record("S4", "does the slow-oscillation arm fire on Gaussian noise",
       {"fired": sum(bool(fired(stability_noise(s), "STABILITY")) for s in range(12)),
        "of": 12})

# ---------------------------------------------------------------- CONSISTENCY
print("\nC -- CONSISTENCY")
env = run(model("""    A:
      - name: pct
        type: NUMERIC
        role: percentage
        axioms: [CONSISTENCY]
"""), [("a1", "A", {"pct": 104.5})])
record("C1", "role: percentage above 100",
       {"findings": [f["problem_type"] for f in fired(env, "CONSISTENCY")]})

env = run(model("""    A:
      - name: c
        type: NUMERIC
        role: count
        axioms: [CONSISTENCY]
"""), [("a1", "A", {"c": -3})])
record("C2", "role: count below zero",
       {"findings": [f["problem_type"] for f in fired(env, "CONSISTENCY")]})

pairs = {}
for divergence in (0.0, 0.005, 0.02, 0.05):
    env = run(model("""    A:
      - name: a
        type: NUMERIC
        axioms: [CONSISTENCY]
        consistency:
          agrees_with: [b]
          tolerance: 0.01
      - name: b
        type: NUMERIC
"""), [("a1", "A", {"a": 100.0, "b": 100.0 * (1 + divergence)})])
    pairs[divergence] = [f["problem_type"] for f in fired(env, "CONSISTENCY")]
record("C3", "agrees_with at tolerance 0.01: where does it break", pairs)

# -------------------------------------------------------------- RESPONSIVENESS
print("\nP -- RESPONSIVENESS")
resp = {}
for value in (12, 34):
    env = run(model("""    A:
      - name: lat
        type: NUMERIC
        role: latency
        axioms: [RESPONSIVENESS]
        critical: 30
"""), [("a1", "A", {"lat": value})])
    resp[value] = [f["problem_type"] for f in fired(env, "RESPONSIVENESS")]
env = run(model("""    A:
      - name: lat
        type: NUMERIC
        axioms: [RESPONSIVENESS]
        critical: 30
"""), [("a1", "A", {"lat": 34})])
resp["no_role"] = [d["reason"] for d in declined(env, "RESPONSIVENESS")]
for extreme in (34, 10_000_000):
    env = run(model("""    A:
      - name: lat
        type: NUMERIC
        role: latency
        axioms: [RESPONSIVENESS]
"""), [("a1", "A", {"lat": extreme})], [("a1", "lat", ts([float(extreme)] * 40))])
    resp[f"no_threshold@{extreme}"] = {
        "declined": [d["reason"] for d in declined(env, "RESPONSIVENESS")],
        "findings": [f["problem_type"] for f in fired(env, "RESPONSIVENESS")],
        "invariants_attempted": env["checked"]["invariants"]}
record("P1", "latency role, threshold, and what each absence declines", resp,
       "the no_threshold rows are the interesting ones: an indicator counted "
       "in the denominator that neither fires nor declines has been reported "
       "as covered while being unable to produce a verdict")

# --------------------------------------------------------------- CONSERVATION
print("\nK -- CONSERVATION")


def conservation(deficit, n=10, cadence=60.0, window="1h", base=100.0):
    ins = [base] * n
    outs = [base - deficit] * n
    env = run(model(f"""    A:
      - name: parts_in
        type: NUMERIC
        axioms: [CONSERVATION]
        window: {window}
        flow: in
        conservation:
          input_property: parts_in
          output_properties: [parts_out]
      - name: parts_out
        type: NUMERIC
        flow: out
"""), [("a1", "A", {"parts_in": ins[-1], "parts_out": outs[-1]})],
        [("a1", "parts_in", ts(ins, cadence)), ("a1", "parts_out", ts(outs, cadence))])
    return env


record("K1", "deficit sizes that fire",
       {d: bool(fired(conservation(d), "CONSERVATION")) for d in (0, 1, 5, 20, 50)})

spans = {}
for cadence_min in (1, 3, 5, 10, 30):
    env = conservation(20, n=10, cadence=cadence_min * 60)
    spans[f"{cadence_min}min"] = {
        "fired": bool(fired(env, "CONSERVATION")),
        "span_min": 10 * cadence_min,
        "declined": [d["reason"] for d in declined(env, "CONSERVATION")] or None}
record("K2", "does the indicator's window: reach the checker, or is there a "
             "global one", spans,
       "if a deficit stops firing as the samples spread out while window: says "
       "1h, the checker is reading its own window and the model cannot set it")

env = run(model("""    A:
      - name: parts_in
        type: NUMERIC
        axioms: [CONSERVATION]
        flow: in
        conservation:
          input_property: parts_in
          output_properties: [parts_out]
      - name: parts_out
        type: NUMERIC
        flow: out
"""), [("a1", "A", {"parts_in": 0.0, "parts_out": 0.0})],
    [("a1", "parts_in", ts([0.0] * 10)), ("a1", "parts_out", ts([0.0] * 10))])
record("K3", "zero input",
       {"declined": [d["reason"] for d in declined(env, "CONSERVATION")],
        "findings": len(fired(env, "CONSERVATION"))})

relative = {}
for base in (100.0, 8800.0):
    for frac in (0.001, 0.005, 0.01, 0.02, 0.05, 0.08, 0.1, 0.12, 0.2):
        env = conservation(base * frac, n=10, base=base)
        relative.setdefault(base, {})[frac] = bool(fired(env, "CONSERVATION"))
record("K7", "is the threshold ABSOLUTE or RELATIVE, and where is it", relative,
       "if the same fraction fires at both scales, the threshold is relative -- "
       "which means a lifetime counter's balance is judged against a lifetime "
       "total. A real loss of forty parts against nine thousand is 0.45 %, and "
       "gets quieter every shift. The remedy is the bridge's: balance the "
       "derived per-interval rate, not the counter")

env = run(model("""    A:
      - name: parts_in
        type: NUMERIC
        axioms: [CONSERVATION]
"""), [("a1", "A", {"parts_in": 100.0})], [("a1", "parts_in", ts([100.0] * 10))])
record("K4", "CONSERVATION declared with no conservation: block",
       {"declined": [d["reason"] for d in declined(env, "CONSERVATION")],
        "findings": len(fired(env, "CONSERVATION")),
        "unread": [f.get("reason") for f in env["_unread_fields"]]})

# --------------------------------------------------------------- CONNECTIVITY
print("\nN -- CONNECTIVITY")
CONN = """    A:
      - name: feeds_b
        type: RELATIONSHIP
        axioms: [CONNECTIVITY]
        target_type: B
        relation_type: feeds
        min_cardinality: 1
    B:
      - name: p
        type: NUMERIC
        axioms: [BOUNDEDNESS]
        warning: 10
        critical: 20
"""
env = run(model(CONN, entity_types="[A, B]",
                extra="  relationship_types: [feeds]\n"),
          [("a1", "A", {}), ("b1", "B", {"p": 1})], relationships=[("a1", "b1", "feeds")])
record("N1", "edge present, min_cardinality 1",
       {"findings": len(fired(env, "CONNECTIVITY")),
        "declined": [d["reason"] for d in declined(env, "CONNECTIVITY")]})

env = run(model(CONN, entity_types="[A, B]",
                extra="  relationship_types: [feeds]\n"),
          [("a1", "A", {}), ("b1", "B", {"p": 1})])
record("N2", "edge missing",
       {"findings": [f["problem_type"] for f in fired(env, "CONNECTIVITY")],
        "declined": [d["reason"] for d in declined(env, "CONNECTIVITY")]})

env = run(model(CONN, entity_types="[A, B]",
                extra="  relationship_types: [feeds]\n"), [("a1", "A", {})])
record("N3", "target entity type never observed",
       {"findings": [f["problem_type"] for f in fired(env, "CONNECTIVITY")],
        "declined": [d["reason"] for d in declined(env)]})

# ------------------------------------------------------------ the gate arm
print("\nG -- the required_property gate")
GATE = """    A:
      - name: feeds_b
        type: RELATIONSHIP
        axioms: [CONNECTIVITY]
        target_type: B
        relation_type: feeds
        min_cardinality: 1
        required_property: state_running
    B:
      - name: p
        type: NUMERIC
        axioms: [BOUNDEDNESS]
        warning: 10
        critical: 20
"""
gate_cases = {}
for label, props in (("gate absent everywhere", {}),
                     ("gate present and true", {"state_running": True}),
                     ("gate present and false", {"state_running": False})):
    env = run(model(GATE, entity_types="[A, B]",
                    extra="  relationship_types: [feeds]\n"),
              [("a1", "A", props), ("b1", "B", {"p": 1})])
    gate_cases[label] = {
        "findings": [f["problem_type"] for f in fired(env, "CONNECTIVITY")],
        "declined": [d["reason"] for d in declined(env, "CONNECTIVITY")]}
record("G1", "required_property on a CONNECTIVITY indicator: what each state does",
       gate_cases)

env = run(model("""    A:
      - name: p
        type: NUMERIC
        axioms: [BOUNDEDNESS]
        warning: 10
        critical: 20
        required_property: state_running
"""), [("a1", "A", {"p": 99})])
record("G2", "THE QUESTION THE HANDOFF LEFT OPEN: does required_property gate a "
             "NUMERIC axiom such as BOUNDEDNESS",
       {"findings": len(fired(env, "BOUNDEDNESS")),
        "declined": [d["reason"] for d in declined(env, "BOUNDEDNESS")],
        "unread_fields": [(f.get("field"), f.get("reason"), f.get("read_by"))
                          for f in env["_unread_fields"]]},
       "if BOUNDEDNESS still fires with the gate property absent, the gate does "
       "not reach this axiom and machine-state gating is the bridge's problem")

env = run(model("""    A:
      - name: p
        type: NUMERIC
        axioms: [BOUNDEDNESS]
        warning: 10
        critical: 20
"""), [("a1", "A", {})])
record("G3", "which reason does a bare absent property produce",
       {"declined": [d["reason"] for d in declined(env)]})

# -------------------------------------------------------------- warming_up
print("\nW -- envelope source")
env = run(model("""    A:
      - name: m
        type: NUMERIC
        axioms: [HOMEOSTASIS]
"""), [("a1", "A", {"m": 1.0})], [("a1", "m", ts([1.0, 2.0]))])
record("W1", "envelope meta on a run where everything declined",
       {"meta": env.get("meta"), "invariants": env["checked"]["invariants"],
        "declined": [d["reason"] for d in declined(env)]})

# ------------------------------------------------- can each reason be reached
print("\nX -- reachability of the twelve reasons")

REACH = {}


def note_reach(reason, how, env, axiom=None):
    got = [d["reason"] for d in declined(env, axiom)]
    REACH[reason] = {"reached": reason in got, "how": how, "saw": sorted(set(got))}


note_reach("insufficient_samples", "HOMEOSTASIS learned, 3 samples",
           homeostasis_learned(3), "HOMEOSTASIS")
note_reach("missing_property", "BOUNDEDNESS, entity carries no property",
           run(model("""    A:
      - name: p
        type: NUMERIC
        axioms: [BOUNDEDNESS]
        warning: 1
        critical: 2
"""), [("a1", "A", {})]), "BOUNDEDNESS")
note_reach("no_current_value", "BOUNDEDNESS, history fed but no property",
           run(model("""    A:
      - name: p
        type: NUMERIC
        axioms: [BOUNDEDNESS]
        warning: 1
        critical: 2
"""), [("a1", "A", {})], [("a1", "p", ts([9.0] * 40))]), "BOUNDEDNESS")
note_reach("missing_entity_type", "CONNECTIVITY pointing at an unobserved type",
           run(model(CONN, entity_types="[A, B]",
                     extra="  relationship_types: [feeds]\n"), [("a1", "A", {})]))
note_reach("missing_config", "CONSERVATION with no conservation: block",
           run(model("""    A:
      - name: q
        type: NUMERIC
        axioms: [CONSERVATION]
"""), [("a1", "A", {"q": 1.0})], [("a1", "q", ts([1.0] * 10))]), "CONSERVATION")

no_threshold_attempts = {}
for label, text in (
        ("BOUNDEDNESS with no thresholds", """    A:
      - name: p
        type: NUMERIC
        axioms: [BOUNDEDNESS]
"""),
        ("RESPONSIVENESS role latency, no critical", """    A:
      - name: lat
        type: NUMERIC
        role: latency
        axioms: [RESPONSIVENESS]
"""),
        ("HOMEOSTASIS setpoint with no tolerance", """    A:
      - name: m
        type: NUMERIC
        axioms: [HOMEOSTASIS]
        homeostasis:
          setpoint: 60
""")):
    env = run(model(text), [("a1", "A", {"p": 99.0, "lat": 99.0, "m": 99.0})],
              [("a1", "p", ts([99.0] * 40)), ("a1", "lat", ts([99.0] * 40)),
               ("a1", "m", ts([99.0] * 40))])
    no_threshold_attempts[label] = {
        "declined": sorted({d["reason"] for d in declined(env)}),
        "findings": [f["problem_type"] for f in env.get("findings", [])],
        "invariants": env["checked"]["invariants"],
        "loader_said": env["_stderr"]}
record("X1", "which model shape produces no_threshold", no_threshold_attempts,
       "a reason a bridge cannot reach is a row in the requirements table with "
       "nothing behind it")
REACH["no_threshold"] = {
    "reached": any("no_threshold" in v["declined"]
                   for v in no_threshold_attempts.values()),
    "how": "three shapes tried", "saw": no_threshold_attempts}

note_reach("wrong_indicator_type", "BOUNDEDNESS on a STATE indicator",
           run(model("""    A:
      - name: s
        type: STATE
        axioms: [BOUNDEDNESS]
        warning: 1
        critical: 2
"""), [("a1", "A", {"s": "running"})]))
note_reach("missing_role", "RESPONSIVENESS with no role",
           run(model("""    A:
      - name: lat
        type: NUMERIC
        axioms: [RESPONSIVENESS]
        critical: 30
"""), [("a1", "A", {"lat": 99})]), "RESPONSIVENESS")
note_reach("undefined_for_values", "CONSERVATION with zero input",
           run(model("""    A:
      - name: i
        type: NUMERIC
        axioms: [CONSERVATION]
        flow: in
        conservation:
          input_property: i
          output_properties: [o]
      - name: o
        type: NUMERIC
        flow: out
"""), [("a1", "A", {"i": 0.0, "o": 0.0})],
               [("a1", "i", ts([0.0] * 10)), ("a1", "o", ts([0.0] * 10))]),
           "CONSERVATION")
note_reach("precondition_unmet", "CONNECTIVITY gate present and false",
           run(model(GATE, entity_types="[A, B]",
                     extra="  relationship_types: [feeds]\n"),
               [("a1", "A", {"state_running": False}), ("b1", "B", {"p": 1})]),
           "CONNECTIVITY")
REACH["not_applicable"] = {"reached": False, "how": "engine-side residue; no "
                           "model shape a bridge can write reaches it", "saw": []}
REACH["checker_error"] = {"reached": False, "how": "an engine fault; not "
                          "reachable from a model", "saw": []}
record("X2", "of the twelve reasons, which can a model this bridge could "
             "generate actually produce",
       {"reachable": sorted(k for k, v in REACH.items() if v["reached"]),
        "not_reached": sorted(k for k, v in REACH.items() if not v["reached"]),
        "detail": {k: {"reached": v["reached"], "how": v["how"]}
                   for k, v in REACH.items()}},
       "BRIDGES says the vocabulary is the requirements document; this "
       "measures how much of it a bridge can be held to")
RESULT["reachability"] = REACH

# ------------------------------------------ CONSERVATION window, more closely
print("\nK -- CONSERVATION window, second pass")
win = {}
for declared_window in ("5m", "1h", "30d"):
    env = conservation(20, n=10, cadence=60000, window=declared_window)
    win[declared_window] = {
        "fired": bool(fired(env, "CONSERVATION")),
        "declined": [d["reason"] for d in declined(env, "CONSERVATION")] or None}
record("K5", "ten samples spread over SIX DAYS, with window: declared 5m, 1h "
             "and 30d", win,
       "a respected window: of 5m would leave one sample inside it and the "
       "deficit unseeable. Identical results across all three mean the "
       "indicator's window: does not reach this checker")

age = {}
for label, cadence in (("span 9 min", 60), ("span 90 min", 600),
                       ("span 15 h", 6000), ("span 6 d", 60000)):
    env = conservation(20, n=10, cadence=cadence, window="30d")
    age[label] = {"fired": bool(fired(env, "CONSERVATION")),
                  "declined": [d["reason"] for d in declined(env, "CONSERVATION")] or None}
record("K6", "how far back can a deficit be and still be seen", age,
       "the first probe of this package reported a 300 s horizon; this is the "
       "measurement that either reproduces it or retires it")

# ------------------------------------------------------------------- floors
floors = {}
h1 = RESULT["probes"]["H1"]["measured"]
s1 = RESULT["probes"]["S1"]["measured"]
# The learned window, stated as the thing a bridge can act on: the widest
# collection cadence at which the floor is still reachable. Deriving a window
# in seconds from this would be arithmetic on top of a measurement, and the
# arithmetic is where a second copy of a fact gets born.
passed = [float(label.rstrip("h")) for label, row
          in RESULT["probes"]["H2"]["measured"].items() if not row["declined"]]
failed = [float(label.rstrip("h")) for label, row
          in RESULT["probes"]["H2"]["measured"].items() if row["declined"]]
floors["HOMEOSTASIS"] = {
    "samples": h1,
    "max_cadence_s": int(max(passed) * 3600) if passed else None,
    "first_failing_cadence_s": int(min(failed) * 3600) if failed else None,
    "note": "learned baseline. A collector slower than max_cadence_s can never "
            "present this floor, however long it runs. A declared setpoint "
            "needs one sample and no window"}
floors["STABILITY"] = {"samples": s1, "max_cadence_s": None,
                       "note": "expect_variation arm on a flat series"}
mono_window = None
for label, counted in RESULT["probes"]["M3"]["measured"].items():
    if not counted:
        mono_window = int(label.split()[0]) * 60
        break
floors["MONOTONICITY"] = {
    "samples": RESULT["probes"]["M1"]["measured"]["fires_at"],
    "max_cadence_s": None, "reversal_window_s": mono_window,
    "note": "reversals, counted inside a window; the count is a tolerance "
            "rather than a floor, so it is not a corpus-size input"}
RESULT["floors"] = floors
RESULT["corpus_samples"] = int(max(
    [floors["HOMEOSTASIS"]["samples"], floors["STABILITY"]["samples"]]) * 1.5) + 5

print("\n=== derived ===")
print(f"  floors: {json.dumps(floors)}")
print(f"  corpus size: {RESULT['corpus_samples']} samples "
      f"(max floor * 1.5 + 5, derived not chosen)")

with open(OUT, "w", encoding="utf-8") as handle:
    json.dump(RESULT, handle, indent=2)
    handle.write("\n")
print(f"\nwrote {OUT}")
