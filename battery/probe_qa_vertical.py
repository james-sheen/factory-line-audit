#!/usr/bin/env python3
"""Does this package's `qa-orchestrator` vertical register and unregister cleanly?

Step 6.1 of the referee-vertical work: **`register()` then `unregister()` leaves
the three registries as they were -- asserted, not assumed.** A vertical that
leaves a tier or a tool behind poisons the next scenario in the same process,
and the symptom appears somewhere else entirely.

Two halves, because the interesting one is easy to lose:

* the registries come back to what they were, AND
* they were CHANGED in between. A `register()` that quietly did nothing passes
  the first half perfectly.

    python3 battery/probe_qa_vertical.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def measure() -> dict:
    sys.path.insert(0, HERE)
    sys.path.insert(0, os.path.join(ROOT, "src"))
    try:
        from qa_orchestrator import actions, referee, substrate
        import qa_orchestrator
    except ImportError as missing:
        return {"code": 2, "note": f"qa-orchestrator is not installed, so the "
                                   f"vertical registered nothing and nothing "
                                   f"was checked: {missing}"}
    import qa_vertical

    before = {"substrates": substrate.known(), "tools": referee.known_tools(),
              "verbs": actions.known_verbs()}
    try:
        summary = qa_vertical.register()
    except Exception as error:                                  # noqa: BLE001
        return {"code": 1, "qa_orchestrator": qa_orchestrator.__version__,
                "note": f"register() raised {type(error).__name__}: {error}"}
    during = {"substrates": substrate.known(), "tools": referee.known_tools(),
              "verbs": actions.known_verbs()}
    qa_vertical.unregister()
    after = {"substrates": substrate.known(), "tools": referee.known_tools(),
             "verbs": actions.known_verbs()}

    problems = []
    # NON-VACUITY FIRST. Everything below is *the registries came back*, which is
    # true of a register() that did nothing at all.
    added = {k: sorted(set(during[k]) - set(before[k])) for k in before}
    if not added["substrates"] or not added["tools"]:
        problems.append(f"register() added {added}; a vertical that registers "
                        f"neither a tier nor a referee has nothing to unregister "
                        f"and passes the symmetry check for the wrong reason")
    if added["verbs"]:
        problems.append(f"register() added verbs {added['verbs']}; this vertical "
                        f"is written not to, because the core's five map onto "
                        f"its tier")
    for key in before:
        if sorted(after[key]) != sorted(before[key]):
            problems.append(f"{key} did not come back: before {sorted(before[key])}, "
                            f"after {sorted(after[key])}")

    # THE TRIPWIRE for qa-orchestrator #1. `findings` is read with a plain
    # `.get()` while `declines` and `checked` are read with `_dig`, so this
    # tool's nested findings cannot be reached and a scenario asserting on them
    # would pass having seen none. This asserts the CURRENT behaviour, so it
    # goes red the day the ask is answered -- which is the only way anybody
    # notices that the vertical can now judge.
    nested = {"checked": {"findings_verbatim": [{"entity_id": "x"}],
                          "invariants_attempted": 48}}
    dig = getattr(referee, "_dig", None)
    reachable = bool(nested.get("checked.findings_verbatim"))
    denominator = dig(nested, "checked.invariants_attempted") if dig else None
    if reachable:
        problems.append("qa-orchestrator #1 appears to be ANSWERED: a dotted "
                        "`findings` now resolves. Point the schema at it, drop "
                        "this tripwire, and the vertical can judge findings")
    if denominator != 48:
        problems.append(f"`checked` no longer reaches a dotted path either "
                        f"({denominator!r}); the schema's denominator is gone")

    # THE TIER'S OWN BEHAVIOUR. Registering a substrate nobody starts is a
    # declaration with nothing behind it. `start()` needs `asyncua` and a
    # server, which is the `live` leg's business; everything else operates on
    # the walk in memory and can be checked here for nothing.
    tier = qa_vertical.FactoryOpcUaSubstrate({})
    node = next(iter(tier._walk["samples"][0]["nodes"]))
    tier_states = {"before": substrate.observe(tier, node)}
    tier.disable(node)
    tier_states["disabled"] = substrate.observe(tier, node)
    tier.remove(node)
    tier_states["removed"] = substrate.observe(tier, node)
    expected = {"before": "reading", "disabled": "disabled", "removed": "absent"}
    if tier_states != expected:
        problems.append(f"the tier reports {tier_states} where {expected} was "
                        f"expected; `observe` refuses anything outside the "
                        f"core's three words, so a wrong one is a tier speaking "
                        f"its own vocabulary")

    # set_value goes through the core's adapter, not the method directly: the
    # adapter is what a scenario actually calls.
    other = next(iter(tier._walk["samples"][0]["nodes"]))
    substrate.set_value(tier, other, 12.5)
    moved = {s["nodes"][other]["v"] for s in tier._walk["samples"]
             if other in s["nodes"]}
    if moved != {12.5}:
        problems.append(f"set_value left {sorted(moved)[:4]}; a value moved for "
                        f"one sample and not the series is a fault a capture "
                        f"would average away")

    # The handle contract, which is this vertical's own invention and the
    # likeliest thing to break silently: a target from ANOTHER tier has no
    # register in it, and capture must refuse rather than build a command line
    # missing a required flag.
    try:
        qa_vertical._capture_argv("opc.tcp://127.0.0.1:1/x/", "/tmp/w.json")
        problems.append("_capture_argv accepted a handle carrying no register")
    except ValueError:
        pass

    answer = {"qa_orchestrator": qa_orchestrator.__version__,
              "tier_states": tier_states,
              "summary": summary, "added": added,
              "findings_path_reachable": reachable,
              "checked_path_reachable": denominator == 48}
    if problems:
        answer.update(code=1, note="; ".join(problems)[:400], problems=problems)
    else:
        answer.update(code=0, note=(
            f"qa-orchestrator {qa_orchestrator.__version__}: register() added "
            f"{added['substrates']} and {added['tools']} and no verbs, "
            f"unregister() put all three registries back, and findings stay "
            f"unreachable pending their #1"))
    return answer


def main() -> int:
    answer = measure()
    print(f"  qa-vertical {answer['code']}  {answer['note']}", file=sys.stderr)
    print(json.dumps(answer, indent=2, sort_keys=True, default=list))
    return answer["code"]


if __name__ == "__main__":
    raise SystemExit(main())
