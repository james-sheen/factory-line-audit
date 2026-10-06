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
import subprocess
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

    # FINDINGS ARE REACHABLE, asked of the harness's own reader. This was a
    # tripwire meant to go red the day qa-orchestrator #1 was answered, and it
    # could never fire: it read a dotted key off its own literal dict with a
    # plain `.get`, which is None whatever the harness does. #1 was answered in
    # qa-orchestrator 0.3.3 -- `Verdict.findings()` reads the schema's path with
    # `_dig` -- and nothing here noticed. So the question is now the positive
    # one, put to the harness with this vertical's own schema: a nested finding
    # comes back, or this vertical cannot judge findings and a scenario
    # asserting on them would pass having seen none.
    nested = {"checked": {"findings_verbatim": [{"entity_id": "x"}],
                          "invariants_attempted": 48}}
    schema = qa_vertical._schema(referee)
    try:
        verdict = referee.Verdict(exit_code=1, stdout="", stderr="",
                                  report=nested, schema=schema)
    except TypeError as error:
        verdict = None
        problems.append(f"this harness's `Verdict` would not take a report and "
                        f"a schema ({error}), so nothing can be read through it")
    reachable = (verdict is not None
                 and [f.get("entity_id") for f in verdict.findings()] == ["x"])
    denominator = verdict.checked() if verdict is not None else None
    if verdict is not None and not reachable:
        problems.append(f"qa-orchestrator {qa_orchestrator.__version__} does "
                        f"not reach the schema's `{schema.findings}` in a report "
                        f"keeping findings at `checked.findings_verbatim`; it "
                        f"reads a dotted path from 0.3.3, and without one this "
                        f"vertical cannot judge findings")
    if verdict is not None and denominator != 48:
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

    # THE CROSS-VERTICAL CONTROL. This is the part that checks the HARNESS
    # rather than the bridge: another vertical's entity must be REFUSED by name,
    # not answered. It was answered `absent` -- the same word this tier gives a
    # node a verb removed -- so a BMC scenario, or one with a typo'd node id,
    # would have had its `absent` expectation met by a tier that was never
    # serving the thing at all.
    try:
        substrate.observe(tier, "Inlet")
        problems.append("the tier answered for 'Inlet', a BMC sensor it has "
                        "never served, instead of refusing by name")
        foreign_refused = False
    except Exception as refusal:
        foreign_refused = "not one of them" in str(refusal)
        if not foreign_refused:
            problems.append(f"the tier refused a foreign entity for the wrong "
                            f"reason: {type(refusal).__name__}: {refusal}")

    # And the scenarios end to end, when the tool and the client library are
    # both here. A tier that registers and is never started is a declaration.
    def _run_scenario(name):
        environment = dict(os.environ)
        environment["PATH"] = (os.path.dirname(sys.executable) + os.pathsep
                               + environment.get("PATH", ""))
        return subprocess.run(
            [sys.executable, "-m", "qa_orchestrator.cli", "--plugin",
             os.path.join(HERE, "qa_vertical.py"), "run",
             os.path.join(HERE, "scenarios", name)],
            capture_output=True, text=True, cwd=ROOT, env=environment,
            timeout=900)

    ran = "not attempted"
    wrong_on_purpose = "not attempted"
    must_fail = os.path.join(HERE, "scenarios", "must-fail.yaml")
    if not os.path.exists(must_fail):
        problems.append("scenarios/must-fail.yaml is gone. It is the only thing "
                        "here that shows the comparator compares anything; "
                        "without it a blind referee and a working one look the "
                        "same from a suite where everything passes")
    try:
        import asyncua                                          # noqa: F401

        proc = _run_scenario("tag-removed.yaml")
        ran = f"exit {proc.returncode}"
        if proc.returncode != 0 or "every expectation held" not in proc.stdout:
            problems.append(f"the scenario did not hold: exit "
                            f"{proc.returncode}: "
                            f"{(proc.stdout or proc.stderr).strip()[-300:]}")

        # THE WRONG-ON-PURPOSE SCENARIO. It must fail, and it must fail FOR THE
        # REASONS IT WAS WRITTEN FOR. Requiring only a non-zero exit would be
        # met by a scenario broken some other way -- an unknown substrate, a
        # typo'd verb -- which says nothing about whether anything is compared.
        if os.path.exists(must_fail):
            bad = _run_scenario("must-fail.yaml")
            wrong_on_purpose = f"exit {bad.returncode}"
            output = bad.stdout + bad.stderr
            if bad.returncode == 0:
                problems.append(
                    "scenarios/must-fail.yaml PASSED. All three of its "
                    "expectations are false, so the comparator is not "
                    "comparing -- and every green scenario beside it means "
                    "nothing")
            # One tell per channel, named by subject rather than by the whole
            # sentence: the wording is the harness's to change, the subject is
            # not. The findings channel has its own subject for that reason.
            for tell, channel in (("exit code", "the referee channel"),
                                  ("ns=2;s=PR01.Strokes", "the findings channel"),
                                  ("ns=2;s=PR01.DieTemp", "the substrate channel"),
                                  ("expected reading", "the substrate channel")):
                if tell not in output:
                    problems.append(
                        f"must-fail.yaml failed without {channel} producing a "
                        f"mismatch naming {tell!r}; it failed for some other "
                        f"reason, which proves nothing")
    except ImportError:
        ran = wrong_on_purpose = "asyncua absent, so the tier could not be started"

    answer = {"qa_orchestrator": qa_orchestrator.__version__,
              "tier_states": tier_states,
              "foreign_entity_refused": foreign_refused,
              "scenario": ran,
              "wrong_on_purpose": wrong_on_purpose,
              "summary": summary, "added": added,
              "findings_path_reachable": reachable,
              "checked_path_reachable": denominator == 48}
    if problems:
        answer.update(code=1, note="; ".join(problems)[:400], problems=problems)
    else:
        answer.update(code=0, note=(
            f"qa-orchestrator {qa_orchestrator.__version__}: registries come "
            f"back ({added['substrates']} + {added['tools']}, no verbs); a "
            f"foreign entity is refused by name; findings reach the harness "
            f"through the schema; the scenario ran end to end ({ran}) and the "
            f"wrong-on-purpose one failed for each of its three reasons "
            f"({wrong_on_purpose})"))
    return answer


def main() -> int:
    answer = measure()
    print(f"  qa-vertical {answer['code']}  {answer['note']}", file=sys.stderr)
    print(json.dumps(answer, indent=2, sort_keys=True, default=list))
    return answer["code"]


if __name__ == "__main__":
    raise SystemExit(main())
