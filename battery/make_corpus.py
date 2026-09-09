#!/usr/bin/env python3
"""Build the clean walk and one mutated copy per fault class.

BRIDGES's verification battery, the seven rules for injecting a fault. Each is
enforced here
rather than described:

1. Mutate a copy -- every fault starts from `clean.json`, which is written once.
2. Absolute deltas where a baseline can be zero -- `scrap_count` starts at 0 and
   the parts-vanish injector subtracts a count, never a proportion.
3. Assert the injection took -- every injector returns the number of samples it
   changed and this script refuses to write a copy where that is zero.
4. Stay outside the engine's excuse boundaries and write down why -- each entry
   in FAULTS carries `outside`, naming the measured boundary it clears and the
   probe that measured it.
5. One fault per copy, expectation declared before the run -- EXPECT.json is
   written by this script, not by the battery.
6. Assert on the finding, not the code -- EXPECT carries the axiom and the
   entity, and `run_battery.py` checks those.
7. Derive the corpus from the engine's floors -- the sample count comes from
   `engine_floors.json` and this script refuses to run without it.

This script has no engine import. It reads the floors the probe measured.
"""
from __future__ import annotations

import copy
import datetime as _dt
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CORPUS = os.path.join(HERE, "corpus")
FLOORS = os.path.join(HERE, "engine_floors.json")
REGISTER = os.path.join(ROOT, "examples", "asset_register.json")

CADENCE_S = 60
SEED = 20260903

#: The corpus ENDS at build time, and that is not a convenience.
#:
#: Several arms count inside a window measured backwards from now: probe M3 put
#: MONOTONICITY's reversal window at about fifteen minutes at this cadence, and
#: STABILITY and CONSERVATION behave the same way. A corpus written with fixed
#: timestamps is therefore a fixture with a shelf life -- it stops presenting
#: those arms as it ages, silently, and every fault leg that depends on one goes
#: green having tested nothing.
#:
#: This bit during development: a corpus stamped two days earlier produced
#: eleven `insufficient_samples` declines reading *fewer points than can exhibit
#: a reversal* over fifty samples. `run_battery.py` refuses a corpus older than
#: the narrowest measured window rather than trusting this to stay true.
BUILT_AT = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)

if not os.path.exists(FLOORS):
    print(f"REFUSED: {FLOORS} is absent. The corpus size is derived from the "
          f"engine's measured floors, not chosen. Run probe_engine.py first.",
          file=sys.stderr)
    raise SystemExit(2)

with open(FLOORS, encoding="utf-8") as handle:
    floors = json.load(handle)
N = floors["corpus_samples"]
if floors.get("engine_version") is None:
    print("REFUSED: the floors file names no engine version", file=sys.stderr)
    raise SystemExit(2)

widest = min([spec["max_cadence_s"] for spec in floors["floors"].values()
              if spec.get("max_cadence_s")] or [None])
if widest and CADENCE_S > widest:
    print(f"REFUSED: this corpus collects every {CADENCE_S}s and the widest "
          f"cadence that still reaches a measured floor is {widest}s",
          file=sys.stderr)
    raise SystemExit(2)

START = BUILT_AT - _dt.timedelta(seconds=CADENCE_S * (N - 1))
rng = random.Random(SEED)
with open(REGISTER, encoding="utf-8") as handle:
    register = json.load(handle)
NODE = {f"{a['id']}.{t}": s["node"]
        for a in register["assets"] for t, s in a["tags"].items()}


def stamp(i):
    return (START + _dt.timedelta(seconds=CADENCE_S * i)).isoformat().replace(
        "+00:00", "Z")


def noisy(mean, spread):
    return round(mean + rng.gauss(0, spread), 3)


def clean_walk():
    """A healthy hour of Cell 1.

    Every series is stationary or monotone; nothing here is shaped to satisfy a
    check. Where a value is bounded, it sits well inside the bound, and the
    margin is stated in the comment so a reader can see it was not tuned to the
    edge of one.
    """
    samples = []
    counters = {"PR-01.stroke_count": 41200, "ST-01.parts_out": 8830,
                "ST-02.parts_in": 8830, "ST-02.parts_out": 8794,
                "ST-02.parts_out_mes": 8794, "ST-02.scrap_count": 36,
                "ST-03.parts_out": 8794, "PLC-01.heartbeat": 1_284_000}
    for i in range(N):
        counters["PR-01.stroke_count"] += 1
        counters["ST-01.parts_out"] += 1
        counters["ST-02.parts_in"] += 1
        if i % 10 == 9:                      # one part in ten is scrapped
            counters["ST-02.scrap_count"] += 1
        else:
            counters["ST-02.parts_out"] += 1
            counters["ST-02.parts_out_mes"] += 1
            counters["ST-03.parts_out"] += 1
        counters["PLC-01.heartbeat"] += 50 * CADENCE_S   # 50/s, one per 20 ms scan
        values = {
            "PR-01.die_temp_c": noisy(198, 3.0),          # warning 240
            "PR-01.tonnage_kn": noisy(1520, 22.0),        # warning 1800
            "PR-01.SpareAnalog3": 0.0,
            "ST-01.cycle_time_s": noisy(60, 1.0),         # setpoint 60 +/- 4
            "ST-01.weld_current_a": noisy(8500, 380.0),   # varies by construction
            "ST-01.state_running": True,
            "ST-02.cycle_time_s": noisy(60, 1.0),
            "ST-02.state_running": True,
            "ST-03.cycle_time_s": noisy(60, 1.0),
            "ST-03.reject_pct": max(0.0, noisy(2.4, 0.45)),
            "ROB-01.program_cycle_ms": noisy(604, 21.0),  # warning 800
            "ROB-01.axis1_temp_c": noisy(45, 1.8),        # warning 65
            "ROB-01.joint_torque_nm": noisy(121, 4.5),    # no published bound
            "CNV-01.speed_mpm": noisy(12, 0.28),          # setpoint 12 +/- 1.2
            "CNV-01.motor_current_a": noisy(11.8, 0.7),   # warning 18
            "PLC-01.scan_time_ms": noisy(14, 1.1),        # warning 20
            "PLC-01.cpu_load_pct": noisy(41, 3.0),        # warning 70
            "MES-GW.queue_depth": float(rng.randint(0, 4)),
            "MES-GW.uplink_latency_ms": noisy(30, 6.0),
        }
        values.update({k: float(v) for k, v in counters.items()})
        when = stamp(i)
        samples.append({"t": when, "nodes": {
            NODE[k]: {"v": v, "q": "Good", "t": when} for k, v in values.items()}})
    return {
        "format": "factory-line-audit/walk/1",
        "line": "line1",
        "source": {
            "kind": "synthetic", "endpoint": "none",
            "collected_by": f"make_corpus.py seed={SEED}",
            "cadence_s": CADENCE_S, "started": stamp(0),
            "built_at": BUILT_AT.isoformat().replace("+00:00", "Z"),
            "expires_because": "several axiom arms count inside a window "
                               "measured backwards from now; see BUILT_AT",
            "provenance": "SYNTHETIC. No OPC UA server was read. Evidence "
                          "ladder rung 1.",
            "derived_from": {"engine_version": floors["engine_version"],
                             "corpus_samples": N,
                             "reason": "max measured sample floor * 1.5 + 5"},
        },
        "samples": samples,
    }


def at(sample, key):
    return sample["nodes"][NODE[key]]


# ------------------------------------------------------------------ injectors

def flat_weld_current(walk):
    """STABILITY, expect_variation arm. The WHOLE series, and that is forced.

    Probe S5 measured it: a series flat for its last 45 of 50 samples does not
    fire; only a series flat throughout does. So a probe that dies mid-shift is
    not reported frozen until every varying sample has aged out of the fed
    history. Flattening only the tail would have been a fault injected inside
    the engine's excuse boundary -- a green that tested nothing, which is the
    exact failure rule 4 exists to prevent, and the first version of this
    injector did it."""
    touched = 0
    for sample in walk["samples"]:
        at(sample, "ST-01.weld_current_a")["v"] = 8500.0
        touched += 1
    return touched


def die_over_temp(walk):
    """BOUNDEDNESS. 271 against a declared critical of 265; the engine judges
    the current value and needs no history (probe B1)."""
    touched = 0
    for sample in walk["samples"][-6:]:
        at(sample, "PR-01.die_temp_c")["v"] = 271.0
        touched += 1
    return touched


def count_mismatch(walk):
    """CONSISTENCY, agrees_with. 5 % divergence against a declared tolerance of
    0.01; probe C3 measured the break between 0.005 and 0.02."""
    touched = 0
    for sample in walk["samples"][-8:]:
        cell = at(sample, "ST-02.parts_out_mes")
        cell["v"] = round(cell["v"] * 0.95, 3)
        touched += 1
    return touched


def parts_vanish(walk):
    """CONSERVATION, on the DERIVED per-interval rate.

    Half the parts stop being counted out over the last twenty-five intervals,
    which is a 40 % deficit against a threshold measured between 5 % and
    8 % (probe K7).

    The first version of this injector subtracted a constant forty from the
    cumulative counter, and it was wrong twice over: forty against a lifetime
    total of nine thousand is 0.45 %, and a CONSTANT offset has a FLAT first
    difference, so it injects nothing at all into a rate balance. A sustained
    loss has to be injected as a change in the RATE."""
    samples = walk["samples"]
    start = len(samples) - 25
    base = at(samples[start], "ST-02.parts_out")["v"]
    touched = 0
    kept = 0
    for n, sample in enumerate(samples[start + 1:], start=1):
        if n % 2 == 0:
            kept += 1
        cell = at(sample, "ST-02.parts_out")
        cell["v"] = base + float(kept)
        touched += 1
    return touched


def counter_reversal(walk):
    """MONOTONICITY, reversal arm. Three backward steps in the last five
    samples: the measured tolerance is three AND the measured window is about
    fifteen samples (probes M1, M3), so they are placed at the end."""
    touched = 0
    for offset in (1, 3, 5):
        cell = at(walk["samples"][-offset], "ST-03.parts_out")
        cell["v"] = cell["v"] - 7.0
        touched += 1
    return touched


def cycle_drift(walk):
    """HOMEOSTASIS against a DECLARED setpoint, which needs one sample rather
    than thirty (probe H5). 71 s against 60 +/- 4."""
    touched = 0
    for sample in walk["samples"][-12:]:
        at(sample, "ST-01.cycle_time_s")["v"] = 71.0
        touched += 1
    return touched


def scan_time_breach(walk):
    """BOUNDEDNESS and RESPONSIVENESS on a latency. 46 ms against a declared
    critical of 40."""
    touched = 0
    for sample in walk["samples"][-5:]:
        at(sample, "PLC-01.scan_time_ms")["v"] = 46.0
        touched += 1
    return touched


def speed_hunting(walk):
    """STABILITY, slow-oscillation arm. A period-6 wave at 15 % amplitude: the
    default arm cannot see it at all (probe S2 -- period 2 only), and the
    declared block can (probe S3)."""
    import math
    touched = 0
    for n, sample in enumerate(walk["samples"]):
        at(sample, "CNV-01.speed_mpm")["v"] = round(
            12.0 * (1 + 0.15 * math.sin(2 * math.pi * n / 6)), 3)
        touched += 1
    return touched


def sensor_bad(walk):
    """Stage 1, present but not reading. The node is served with a Bad status
    word in every sample; the engine is never asked."""
    touched = 0
    for sample in walk["samples"]:
        cell = at(sample, "ROB-01.axis1_temp_c")
        cell["q"] = "BadDeviceFailure"
        cell["v"] = None
        touched += 1
    return touched


def asset_absent(walk):
    """Stage 1, absent. Every ST-03 node is removed from every sample, which is
    what a station powered down looks like from an OPC UA walk."""
    nodes = [NODE[k] for k in NODE if k.startswith("ST-03.")]
    touched = 0
    for sample in walk["samples"]:
        for node in nodes:
            if sample["nodes"].pop(node, None) is not None:
                touched += 1
    return touched


def reject_pct_impossible(walk):
    """CONSISTENCY, role: percentage. 104.5, measured at probe C1."""
    touched = 0
    for sample in walk["samples"][-4:]:
        at(sample, "ST-03.reject_pct")["v"] = 104.5
        touched += 1
    return touched


def heartbeat_runaway(walk):
    """MONOTONICITY, rate arm, against a DECLARED rate. The heartbeat climbs at
    200/s against a declared rate_critical of 120 -- the arm the first pass of
    this package never probed, and the one that made its clean corpus noisy."""
    touched = 0
    samples = walk["samples"]
    base = at(samples[-16], "PLC-01.heartbeat")["v"]
    for n, sample in enumerate(samples[-15:], start=1):
        at(sample, "PLC-01.heartbeat")["v"] = base + 200.0 * CADENCE_S * n
        touched += 1
    return touched


def hmi_override(walk):
    """Stage 1, substituted. The conveyor speed reads GoodLocalOverride: a
    value somebody typed at a panel. The number is inside every bound, which is
    the point -- collapsing quality to Good/not-Good makes this invisible."""
    touched = 0
    for sample in walk["samples"][-30:]:
        cell = at(sample, "CNV-01.speed_mpm")
        cell["q"] = "GoodLocalOverride"
        cell["v"] = 12.0
        touched += 1
    return touched


FAULTS = [
    ("flat_weld_current", flat_weld_current, "STABILITY", "ST-01", 1,
     "flat throughout, which S5 measured as the only shape this arm sees"),
    ("die_over_temp", die_over_temp, "BOUNDEDNESS", "PR-01", 1,
     "271 against a declared critical of 265; no history needed (B1)"),
    ("count_mismatch", count_mismatch, "CONSISTENCY", "ST-02", 1,
     "5 % against a declared tolerance of 0.01; breaks between .005 and .02 (C3)"),
    ("parts_vanish", parts_vanish, "CONSERVATION", "ST-02", 1,
     "a 40 % per-interval deficit; the threshold measured 5-8 % relative (K7)"),
    ("counter_reversal", counter_reversal, "MONOTONICITY", "ST-03", 1,
     "3 reversals inside the measured ~15-sample window (M1, M3)"),
    ("cycle_drift", cycle_drift, "HOMEOSTASIS", "ST-01", 1,
     "declared setpoint, so one sample suffices (H5)"),
    ("scan_time_breach", scan_time_breach, "BOUNDEDNESS", "PLC-01", 1,
     "46 ms against a declared critical of 40"),
    ("speed_hunting", speed_hunting, "STABILITY", "CNV-01", 1,
     "period 6, invisible to the default arm (S2), seen by the declared one (S3)"),
    ("sensor_bad", sensor_bad, None, "ROB-01", 1,
     "Stage 1 only; the engine is never asked about this tag"),
    ("asset_absent", asset_absent, None, "ST-03", 1,
     "Stage 1 only; a declared source the walk did not serve"),
    ("reject_pct_impossible", reject_pct_impossible, "CONSISTENCY", "ST-03", 1,
     "104.5 on a declared percentage role (C1)"),
    ("heartbeat_runaway", heartbeat_runaway, "MONOTONICITY", "PLC-01", 1,
     "200/s against a declared rate_critical of 120 (R1, R2)"),
    ("hmi_override", hmi_override, None, "CNV-01", 1,
     "Stage 1 only; every value stays inside every bound, deliberately"),
]


def main():
    os.makedirs(CORPUS, exist_ok=True)
    clean = clean_walk()
    with open(os.path.join(CORPUS, "clean.json"), "w", encoding="utf-8") as handle:
        json.dump(clean, handle, indent=1)
        handle.write("\n")
    print(f"clean.json: {N} samples at {CADENCE_S}s, seed {SEED}")

    expect = {"format": "factory-line-audit/expect/1",
              "written_before_the_run": True,
              "clean": {"exit": 0,
                        "why": "an uncontaminated corpus; the pipeline stays "
                               "quiet or the clean leg is not clean"},
              "faults": {}}
    for name, injector, axiom, entity, code, outside in FAULTS:
        copy_of = copy.deepcopy(clean)
        touched = injector(copy_of)
        if not touched:
            print(f"REFUSED: injector {name} changed nothing. A silent no-op "
                  f"turns a fault leg into a green that tested nothing.",
                  file=sys.stderr)
            raise SystemExit(2)
        if copy_of == clean:
            print(f"REFUSED: injector {name} reported {touched} changes and "
                  f"produced a copy identical to clean.json", file=sys.stderr)
            raise SystemExit(2)
        copy_of["source"]["provenance"] = (
            f"clean.json with one fault injected: {name}. {outside}")
        copy_of["source"]["injected"] = {"fault": name, "samples_changed": touched}
        with open(os.path.join(CORPUS, f"{name}.json"), "w", encoding="utf-8") as h:
            json.dump(copy_of, h, indent=1)
            h.write("\n")
        expect["faults"][name] = {
            "exit": code, "axiom": axiom, "entity": entity,
            "samples_changed": touched, "outside_the_excuse_boundary": outside,
            "stage1_only": axiom is None}
        print(f"{name}.json: {touched} samples changed, expect exit {code}"
              + (f", {axiom} on {entity}" if axiom else f", Stage 1 on {entity}"))

    with open(os.path.join(CORPUS, "EXPECT.json"), "w", encoding="utf-8") as handle:
        json.dump(expect, handle, indent=2)
        handle.write("\n")
    print(f"\nEXPECT.json: {len(FAULTS)} fault classes, expectations declared "
          f"before any of them was run")


if __name__ == "__main__":
    main()
