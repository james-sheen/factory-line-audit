#!/usr/bin/env python3
"""The verification battery. A re-runnable script, not a transcript.

BRIDGES's verification battery. The twelve legs in its table are all here. Two
more are here as well, marked ADDED, each with the argument written down.

`pin` was an addition and is no longer one: it was proposed from here and the
guide's table now carries it. Kept in this file with its reasoning, because the
argument for the leg is the same whoever owns the row.

  corpus -- several axiom arms count inside a window measured backwards from
            now (probes M3, H2). A corpus on disk therefore expires, and a
            battery that runs against a stale one goes green having tested
            nothing. The document's fault-injection rules do not cover this,
            because rule 7 sizes the corpus and says nothing about when it was
            taken.
  pin    -- C8 says a range is a claim about every release inside it and the
            floor must be exercised. Every other capability in the list had a leg
            in the table; the one that is a claim about software the bridge does
            not control had none. It does now.
  conformance -- the core ships a kit that drives a vertical through the protocol
            using stand-ins that implement it and nothing else. It exists because
            the core once called a member the protocol did not declare, every
            test passed because the only vertical happened to have that member,
            and a second vertical found it months later. This package is that
            second vertical. Every other leg here asks whether this bridge
            satisfies itself; this one asks whether it still satisfies the core
            it pins. It costs two imports.

A leg that could not run reports 2 and is NAMED. Never skipped: an absent leg
that leaves no trace reads as a leg that passed.

Usage:
    python3 run_battery.py [--python PY] [--live-python PY] [--no-ship]
"""
from __future__ import annotations

import argparse
import hashlib
import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
CORPUS = os.path.join(HERE, "corpus")
EXAMPLES = os.path.join(ROOT, "examples")
REGISTER = os.path.join(EXAMPLES, "asset_register.json")
FIXTURE = os.path.join(EXAMPLES, "declarations", "line1.fixture.json")
FLOORS = os.path.join(HERE, "engine_floors.json")
PIN = os.path.join(HERE, "pin_evidence.json")

CLEAN, FINDINGS, INCOMPLETE = 0, 1, 2

#: Every leg this battery runs, by the name it reports under. `--only` is
#: validated against this: a mistyped leg name would otherwise select nothing,
#: and a battery that ran nothing exits 0.
SELECTABLE = ("engine", "corpus", "live", "draft", "gate", "clean", "fault",
              "absent", "attest", "pipe", "tool", "suite", "conformance",
              "regression", "capture", "pin", "ship")

RESULTS = []


def leg(name, code, note, added=False):
    RESULTS.append({"leg": name, "code": code, "note": note, "added": added})
    mark = "ADDED " if added else ""
    print(f"  {mark}{name:<8} {code}  {note}")
    return code


def cli(python, argv, cwd=None, env=None, timeout=900):
    environment = dict(os.environ, PYTHONPATH=SRC)
    environment.update(env or {})
    return subprocess.run([python, "-m", "factory_line_audit.cli"] + argv,
                          capture_output=True, text=True, cwd=cwd or ROOT,
                          env=environment, timeout=timeout)


def detect_argv(walk, *extra):
    return (["detect", "--register", REGISTER, "--walk", walk,
             "--declarations", FIXTURE] + list(extra))


# --------------------------------------------------------------------- engine
def leg_engine(python, workdir):
    """C3's own probe, RUN rather than mentioned.

    `probe_engine.py` writes `engine_floors.json`, and every sample floor, every
    window and the corpus size derive from it. Nothing ran it: its clock sat
    frozen at the day it last ran, so six days later it could not complete at
    all, and the file every number in this package rests on was a snapshot
    nobody could reproduce. It was found by accident, reaching for one of its
    numbers.

    Two files NAME the probe -- a sentence in `pin.yml` and the message just
    below in `leg_corpus` -- so a search for the filename reports it as covered.
    Naming is not running, and that is the whole reason this leg exists.

    Output is redirected: a check must not rewrite the record it is checking.
    """
    probe = os.path.join(HERE, "probe_engine.py")
    fresh = os.path.join(workdir, "engine_floors.fresh.json")
    proc = subprocess.run([python, probe], capture_output=True, text=True,
                          cwd=ROOT, timeout=900,
                          env=dict(os.environ, PYTHONPATH=SRC,
                                   FLA_ENGINE_FLOORS_OUT=fresh))
    if proc.returncode or not os.path.exists(fresh):
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:]
        return leg("engine", 2, f"probe_engine.py could not complete (exit "
                                f"{proc.returncode}): {tail}", added=True)
    with open(fresh, encoding="utf-8") as handle:
        measured = json.load(handle)
    with open(FLOORS, encoding="utf-8") as handle:
        recorded = json.load(handle)

    # NON-VACUITY. The comparison below is over keys, and two empty objects
    # agree about everything. This is also the shape a probe that wrote a stub
    # would produce.
    substance = ("probes", "floors", "vocabulary", "reachability",
                 "corpus_samples", "engine_version")
    missing = [k for k in substance if k not in measured]
    if missing:
        return leg("engine", 2, f"the probe wrote a file with no {missing}; "
                                f"there is nothing to compare", added=True)

    # Environment rather than measurement: where the engine is installed, which
    # interpreter ran, and when. Comparing those reports a difference on every
    # machine and says nothing about the engine.
    where = ("measured_on", "engine_file", "python")
    drift = sorted(k for k in set(measured) | set(recorded)
                   if k not in where and measured.get(k) != recorded.get(k))
    if drift:
        return leg("engine", 1, f"the committed engine_floors.json no longer "
                                f"describes the engine that resolves here: "
                                f"{drift} differ. Every sample floor, every "
                                f"window and the corpus size derive from it, so "
                                f"re-run probe_engine.py and commit what it "
                                f"measures", added=True)
    return leg("engine", 0, f"the probe completes against arbiter-engine "
                            f"{measured['engine_version']}, and the committed "
                            f"floors are exactly what it measures", added=True)


# --------------------------------------------------------------------- corpus
def leg_corpus():
    if not os.path.exists(FLOORS):
        return leg("corpus", 2, "engine_floors.json absent; run probe_engine.py",
                   added=True)
    with open(FLOORS, encoding="utf-8") as handle:
        floors = json.load(handle)
    windows = [spec.get("reversal_window_s") for spec in floors["floors"].values()
               if spec.get("reversal_window_s")]
    narrowest = min(windows) if windows else None
    path = os.path.join(CORPUS, "clean.json")
    if not os.path.exists(path):
        return leg("corpus", 2, "corpus absent; run make_corpus.py", added=True)
    with open(path, encoding="utf-8") as handle:
        walk = json.load(handle)
    built = walk["source"].get("built_at")
    if not built:
        return leg("corpus", 2, "the corpus does not say when it was built",
                   added=True)
    age = (_dt.datetime.now(_dt.timezone.utc)
           - _dt.datetime.fromisoformat(built.replace("Z", "+00:00"))).total_seconds()
    if narrowest and age > narrowest:
        return leg("corpus", 2,
                   f"the corpus is {int(age)}s old and the narrowest measured "
                   f"window is {narrowest}s; every arm that counts inside it "
                   f"would go quiet. Re-run make_corpus.py", added=True)
    return leg("corpus", 0, f"built {int(age)}s ago, inside the narrowest "
                            f"measured window ({narrowest}s)", added=True)


# ----------------------------------------------------------------------- live
def leg_live(live_python):
    surface = os.path.join(HERE, "opcua_surface.py")
    try:
        check = subprocess.run([live_python, "-c", "import asyncua"],
                               capture_output=True, timeout=120)
    except Exception as exc:
        return leg("live", 2, f"could not start the live interpreter: {exc}")
    if check.returncode:
        return leg("live", 2, "asyncua is not installed in the live "
                              "interpreter; install the [live] extra")
    ready = os.path.join(tempfile.gettempdir(), "fla-battery-ready.json")
    walk_out = os.path.join(tempfile.gettempdir(), "fla-battery-live-walk.json")
    for path in (ready, walk_out):
        if os.path.exists(path):
            os.unlink(path)
    server = subprocess.Popen(
        [live_python, surface, "serve", "--port", "48411", "--ready", ready],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        for _ in range(120):
            if os.path.exists(ready):
                break
            time.sleep(0.5)
        else:
            return leg("live", 2, "the server never announced a working pass")
        collect = subprocess.run(
            [live_python, surface, "collect", "--port", "48411",
             "--out", walk_out, "--want", "40", "--budget", "40"],
            capture_output=True, text=True, timeout=180)
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
    if collect.returncode or not os.path.exists(walk_out):
        return leg("live", 2, f"collection failed: {collect.stderr.strip()[-160:]}")
    with open(walk_out, encoding="utf-8") as handle:
        walk = json.load(handle)
    source = walk["source"]
    served, requested = source["nodes_served"], source["nodes_requested"]
    absent = len(source["nodes_not_in_address_space"])
    unreadable = len(source["nodes_present_but_unreadable"])
    if not walk["samples"]:
        return leg("live", 2, "the surface was reachable and served nothing")
    return leg("live", 0,
               f"a real OPC UA server read by a real client: "
               f"{len(walk['samples'])} samples, {served}/{requested} nodes "
               f"({absent} absent, {unreadable} present but unreadable). "
               f"Rung 2; nothing here is evidence about security or a plant")


# -------------------------------------------------------------- draft and gate
def leg_draft(python, workdir):
    out = os.path.join(workdir, "draft.json")
    proc = cli(python, ["draft", "--register", REGISTER, "--out", out])
    if proc.returncode != 0:
        return leg("draft", 2, f"draft exited {proc.returncode}"), None
    if not os.path.exists(out):
        return leg("draft", 2, "draft exited clean and wrote nothing"), None
    with open(out, encoding="utf-8") as handle:
        body = json.load(handle)
    if not body.get("statements"):
        return leg("draft", 2, "draft emitted no statements"), None
    return leg("draft", 0, f"emitted {len(body['statements'])} unreviewed "
                           f"statements and exited clean"), out


def leg_gate(python, drafted):
    if drafted is None:
        return leg("gate", 2, "there is no drafted file to refuse")
    proc = cli(python, ["gate", "--register", REGISTER, drafted])
    if proc.returncode != 2:
        return leg("gate", 2, f"the gate accepted an unreviewed file "
                              f"(exit {proc.returncode})")
    if drafted not in proc.stderr:
        return leg("gate", 2, "the gate refused without naming the file")
    good = cli(python, ["gate", "--register", REGISTER, FIXTURE])
    if good.returncode != 0:
        return leg("gate", 2, "the gate refused the disclosed fixture too")
    return leg("gate", 0, "refused that exact file by name, and let the "
                          "self-disclosed fixture through")


# ---------------------------------------------------------------------- clean
def leg_clean(python):
    proc = cli(python, detect_argv(os.path.join(CORPUS, "clean.json")))
    outcome = [line for line in proc.stdout.splitlines()
               if line.startswith("OUTCOME")]
    if proc.returncode == 2:
        return leg("clean", 2, f"could not complete: {proc.stderr.strip()[-160:]}")
    if proc.returncode != 0:
        return leg("clean", 1, f"the uncontaminated corpus is not quiet: "
                               f"{outcome[0] if outcome else proc.stdout[-160:]}")
    return leg("clean", 0, outcome[0] if outcome else "exit 0")


# ---------------------------------------------------------- fault and absent
def leg_faults(python):
    expect_path = os.path.join(CORPUS, "EXPECT.json")
    if not os.path.exists(expect_path):
        leg("fault", 2, "EXPECT.json absent; run make_corpus.py")
        return leg("absent", 2, "EXPECT.json absent; run make_corpus.py")
    with open(expect_path, encoding="utf-8") as handle:
        expect = json.load(handle)
    worst, checked, absent_code = 0, [], None
    for name, spec in expect["faults"].items():
        walk = os.path.join(CORPUS, f"{name}.json")
        attest = os.path.join(tempfile.gettempdir(), f"fla-{name}.json")
        proc = cli(python, detect_argv(walk, "--attest-out", attest))
        note = _fault_verdict(name, spec, proc, attest)
        checked.append((name, note))
        if note is not None:
            worst = 2
            print(f"    {name}: {note}")
        if name == "asset_absent":
            absent_code = 0 if note is None else 2
    good = sum(1 for _, note in checked if note is None)
    leg("fault", worst, f"{good}/{len(checked)} fault classes found for the "
                        f"injected reason, not just with the right exit code")
    leg("absent", absent_code if absent_code is not None else 2,
        "a declared-but-absent source is a finding, not an incompleteness"
        if absent_code == 0 else "asset_absent did not behave as declared")
    return worst


def _fault_verdict(name, spec, proc, attest_path):
    """None when the leg passed. Asserts on the FINDING, never the exit code."""
    if proc.returncode != spec["exit"]:
        return (f"exit {proc.returncode}, expected {spec['exit']} "
                f"({proc.stderr.strip()[-120:]})")
    if not os.path.exists(attest_path):
        return "no attestation was written"
    with open(attest_path, encoding="utf-8") as handle:
        att = json.load(handle)
    if spec["stage1_only"]:
        rows = att["not_established"]["stage1"]["rows"] + \
            att["not_established"]["stage1"]["substituted"]
        if not any(row["asset"] == spec["entity"] for row in rows):
            return f"Stage 1 reported nothing about {spec['entity']}"
        return None
    hits = [f for f in att["checked"]["findings_verbatim"]
            if f.get("axiom") == spec["axiom"]
            and f.get("entity_id") == spec["entity"]]
    if not hits:
        seen = [(f.get("axiom"), f.get("entity_id"))
                for f in att["checked"]["findings_verbatim"]]
        return (f"exit matched, but no {spec['axiom']} finding on "
                f"{spec['entity']}; the run reported {seen}")
    return None


# ------------------------------------------------------------ attest and pipe
def leg_attest(python, workdir):
    attest = os.path.join(workdir, "attest.json")
    first = cli(python, detect_argv(os.path.join(CORPUS, "clean.json"),
                                    "--attest-out", attest))
    if not os.path.exists(attest):
        return leg("attest", 2, "detect wrote no attestation")
    second = cli(python, ["attest", attest])
    if second.returncode != first.returncode:
        return leg("attest", 2, f"the stored verdict re-reports as "
                                f"{second.returncode}, the run said "
                                f"{first.returncode}")
    if "OUTCOME" not in second.stdout:
        return leg("attest", 2, "the attestation re-report has no OUTCOME line")
    return leg("attest", 0, "the artifact re-reports its own verdict through "
                            "the same front door")


def leg_pipe(python):
    """A reader walking away must not change the verdict or print anything."""
    argv = " ".join([python, "-m", "factory_line_audit.cli"]
                    + detect_argv(os.path.join(CORPUS, "counter_reversal.json")))
    # bash explicitly. `set -o pipefail` is a bashism, /bin/sh here is dash,
    # and dash exits 2 on it -- which this leg then read as the CLI failing on a
    # closed pipe. A red from the harness, indistinguishable in the output from
    # a red from the thing under test.
    piped = subprocess.run(
        f"set -o pipefail; {argv} | head -c 1", shell=True, executable="/bin/bash",
        capture_output=True, text=True, cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=SRC), timeout=900)
    full = cli(python, detect_argv(os.path.join(CORPUS, "counter_reversal.json")))
    if piped.returncode != full.returncode:
        return leg("pipe", 2, f"piped exit {piped.returncode}, full exit "
                              f"{full.returncode}")
    noise = [line for line in piped.stderr.splitlines()
             if "BrokenPipe" in line or "Traceback" in line or "Exception" in line]
    if noise:
        return leg("pipe", 2, f"a closed pipe printed: {noise[:2]}")
    return leg("pipe", 0, f"same exit ({full.returncode}) and nothing printed "
                          f"when the reader walked away")


# ----------------------------------------------------------------------- tool
def leg_tool(python, workdir):
    """Walk the whole table, through a subprocess, so the dispatcher under test
    is the one the protocol would advertise.

    ALL of it. The first version skipped `read_attestation` because it needed an
    artifact the others produce, and reported 5 of 6 as a pass -- which is the
    exact shape the tool-surface section names: an entry that was added and
    never wired sits there
    returning nothing while the leg is green.
    """
    stored = os.path.join(workdir, "tool-attest.json")
    made = cli(python, detect_argv(os.path.join(CORPUS, "clean.json"),
                                   "--attest-out", stored))
    if not os.path.exists(stored):
        return leg("tool", 2, "could not produce an attestation to walk the "
                              "read_attestation entry with")
    script = (
        "import contextlib, io, json, sys, tempfile, os\n"
        "from factory_line_audit.tools import SPEC, WITHHELD, dispatch\n"
        "d = tempfile.mkdtemp()\n"
        f"ATTEST = {stored!r}\n"
        f"args = dict(register={REGISTER!r}, "
        f"walk=os.path.join({CORPUS!r}, 'clean.json'), "
        f"declarations=[{FIXTURE!r}], attestation=ATTEST, "
        "out=os.path.join(d, 'a.json'), model_out=os.path.join(d, 'm.yaml'), "
        "manifest_out=os.path.join(d, 'mf.json'))\n"
        "answers = {}\n"
        "for name in SPEC:\n"
        "    with contextlib.redirect_stdout(io.StringIO()):\n"
        "        answers[name] = dispatch(name, args)\n"
        "for name in WITHHELD:\n"
        "    answers[name] = dispatch(name, {})\n"
        "answers['not_a_tool'] = dispatch('not_a_tool', {})\n"
        "print(json.dumps(answers))\n")
    proc = subprocess.run([python, "-c", script], capture_output=True, text=True,
                          cwd=ROOT, env=dict(os.environ, PYTHONPATH=SRC),
                          timeout=900)
    if proc.returncode:
        return leg("tool", 2, f"the dispatcher raised: {proc.stderr.strip()[-160:]}")
    answers = json.loads(proc.stdout)
    for name, answer in answers.items():
        if "exit" not in answer or "verdict" not in answer:
            return leg("tool", 2, f"{name} answered without an explicit verdict")
    withheld = [n for n in ("connect_to_plc", "review_declarations", "not_a_tool")
                if answers.get(n, {}).get("exit") != 2]
    if withheld:
        return leg("tool", 2, f"these did not answer 2: {withheld}")
    ran = [n for n, a in answers.items()
           if n not in ("connect_to_plc", "review_declarations", "not_a_tool")]
    missing = set(json.loads(_spec_names(python))) - set(ran)
    if missing:
        return leg("tool", 2, f"the walk skipped {sorted(missing)}; a closure "
                              f"test that skips an entry is the gap it exists "
                              f"to close")
    failed = [n for n in ran if answers[n]["exit"] == 2]
    if failed:
        return leg("tool", 2, f"these entries could not complete: "
                              f"{[(n, answers[n].get('error')) for n in failed]}")
    return leg("tool", 0, f"all {len(ran)} table entries constructed and ran; "
                          f"first contact and review stayed refused")


def _spec_names(python):
    proc = subprocess.run(
        [python, "-c", "import json; from factory_line_audit.tools import SPEC; "
                       "print(json.dumps(sorted(SPEC)))"],
        capture_output=True, text=True, cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=SRC), timeout=300)
    return proc.stdout.strip()


# ---------------------------------------------------------------------- suite
def leg_suite(python):
    check = subprocess.run([python, "-c", "import pytest"], capture_output=True)
    if check.returncode:
        return leg("suite", 2, "pytest is not installed in this interpreter")
    elsewhere = tempfile.mkdtemp(prefix="fla-suite-")
    try:
        proc = subprocess.run(
            [python, "-m", "pytest", os.path.join(ROOT, "tests"), "-q"],
            capture_output=True, text=True, cwd=elsewhere, timeout=900,
            env=dict(os.environ, PYTHONPATH=SRC))
    finally:
        shutil.rmtree(elsewhere, ignore_errors=True)
    tail = [line for line in proc.stdout.strip().splitlines() if line][-1:]
    if proc.returncode:
        return leg("suite", 1, f"from {elsewhere}: {tail}")
    return leg("suite", 0, f"passed from a directory that is not the "
                           f"repository: {tail[0] if tail else ''}")


# ---------------------------------------------------------------- conformance
def leg_conformance(python):
    """Thin on purpose: the decision lives in `probe_conformance.py`, which CI
    runs directly. Two copies of a verdict is two things to keep in step."""
    probe = os.path.join(HERE, "probe_conformance.py")
    proc = subprocess.run([python, probe], capture_output=True, text=True,
                          cwd=ROOT, timeout=300,
                          env=dict(os.environ, PYTHONPATH=SRC))
    if not proc.stdout.strip():
        return leg("conformance", 2, f"the probe printed nothing: "
                                     f"{(proc.stderr or '')[-200:]}", added=True)
    answer = json.loads(proc.stdout)
    if answer["code"] != proc.returncode:
        return leg("conformance", 2, f"the probe reported {answer['code']} and "
                                     f"exited {proc.returncode}; they are one "
                                     f"verdict and disagree", added=True)
    return leg("conformance", answer["code"], answer["note"], added=True)

# ----------------------------------------------------------------- regression
def leg_regression(python, workdir):
    """The verb through the CLI, which the suite does not reach: argparse's
    two-argument `--rename`, the OUTCOME line and the exit code.

    Both halves in one leg, because either alone passes for the wrong reason. A
    declared move that paired proves nothing if an undeclared one pairs too --
    that would be the guess the review gate exists to refuse, reported as a
    clean run.
    """
    before = os.path.join(CORPUS, "clean.json")
    absent = os.path.join(CORPUS, "asset_absent.json")
    if not os.path.exists(before) or not os.path.exists(absent):
        return leg("regression", 2, "the corpus is absent; run make_corpus.py",
                   added=True)
    with open(before, encoding="utf-8") as handle:
        walk = json.load(handle)
    moved = json.loads(json.dumps(walk))
    for sample in moved["samples"]:
        sample["nodes"] = {f"L1.{node}": reading
                           for node, reading in sample["nodes"].items()}
    shifted = os.path.join(workdir, "moved.json")
    with open(shifted, "w", encoding="utf-8") as handle:
        json.dump(moved, handle)

    dropped = cli(python, ["regression", "--before", before, "--after", absent])
    if dropped.returncode != FINDINGS:
        return leg("regression", 2, f"a walk missing an asset exited "
                                    f"{dropped.returncode}, not {FINDINGS}",
                   added=True)
    declared = cli(python, ["regression", "--before", before, "--after", shifted,
                            "--rename", "ns=2;s=", "L1.ns=2;s="])
    if declared.returncode != CLEAN:
        return leg("regression", 1, f"a DECLARED prefix move exited "
                                    f"{declared.returncode}: {declared.stdout.strip()[-160:]}",
                   added=True)
    undeclared = cli(python, ["regression", "--before", before, "--after", shifted])
    if undeclared.returncode != FINDINGS:
        return leg("regression", 1, "an UNDECLARED prefix move did not report; "
                                    "a rename this package inferred is the "
                                    "guess the review gate refuses", added=True)
    return leg("regression", 0, "a removal reports, a declared prefix move "
                                "pairs, and the same move undeclared is "
                                "reported and not applied", added=True)


# -------------------------------------------------------------------- capture
def leg_capture(live_python, workdir):
    """The shipped verb against a real server: the OUTCOME line, the content
    handle, and the membership cache.

    `live` already proves the client reads a server. This proves the CLI
    contract around it, which is the part a consumer actually depends on: one
    OUTCOME line, a handle `sha256sum` agrees with, and a second run that says
    `unchanged` without reading a value.
    """
    surface = os.path.join(HERE, "opcua_surface.py")
    check = subprocess.run([live_python, "-c", "import asyncua"],
                           capture_output=True)
    if check.returncode:
        return leg("capture", 2, "asyncua is not installed in the live "
                                 "interpreter; nothing was captured",
                   added=True)
    walk_out = os.path.join(workdir, "captured.json")
    cache = os.path.join(workdir, "membership.json")
    endpoint = "opc.tcp://127.0.0.1:48419/factory-line-audit/"

    def against_a_fresh_surface(argv):
        """One server per command: the surface plays the corpus once and stops."""
        ready = os.path.join(workdir, "ready.json")
        if os.path.exists(ready):
            os.unlink(ready)
        server = subprocess.Popen(
            [live_python, surface, "serve", "--port", "48419", "--ready", ready],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(120):
                if os.path.exists(ready):
                    break
                time.sleep(0.25)
            else:
                return None
            return cli(live_python, argv, timeout=180)
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()

    first = against_a_fresh_surface(
        ["capture", "--register", REGISTER, "--target", endpoint,
         "--out", walk_out, "--samples", "2", "--budget", "15",
         "--print-digest", "--membership-cache", cache])
    if first is None:
        return leg("capture", 2, "the surface never announced a working pass",
                   added=True)
    outcomes = [line for line in first.stdout.splitlines()
                if line.startswith("OUTCOME")]
    if len(outcomes) != 1 or outcomes[0] != "OUTCOME walked":
        return leg("capture", 1, f"the OUTCOME line is the contract and this "
                                 f"run printed {outcomes}", added=True)
    if not os.path.exists(walk_out):
        return leg("capture", 1, "OUTCOME walked and no walk was written",
                   added=True)

    printed = [line.strip() for line in first.stdout.splitlines()
               if line.strip().startswith("sha256:")]
    with open(walk_out, "rb") as handle:
        actual = "sha256:" + hashlib.sha256(handle.read()).hexdigest()
    if printed[:1] != [actual]:
        return leg("capture", 1, f"the handle printed is not the one sha256sum "
                                 f"computes, so a recipient cannot check it "
                                 f"without this tool: {printed} vs {actual}",
                   added=True)

    with open(cache, encoding="utf-8") as handle:
        cached = handle.read()
    if '"v"' in cached or '"q"' in cached:
        return leg("capture", 1, "the membership cache holds a reading; it is "
                                 "membership only and says so in the file",
                   added=True)

    second = against_a_fresh_surface(
        ["capture", "--register", REGISTER, "--target", endpoint,
         "--out", walk_out + ".2", "--samples", "2", "--budget", "15",
         "--membership-cache", cache])
    if second is None:
        return leg("capture", 2, "the surface never came back for the second "
                                 "pass", added=True)
    if "OUTCOME unchanged" not in second.stdout:
        return leg("capture", 1, f"an unchanged address space did not report "
                                 f"unchanged: "
                                 f"{second.stdout.strip().splitlines()[-1:]}",
                   added=True)
    if os.path.exists(walk_out + ".2"):
        return leg("capture", 1, "it reported unchanged and wrote a walk "
                                 "anyway", added=True)
    return leg("capture", 0, "one OUTCOME line, a handle sha256sum agrees "
                             "with, a cache holding no reading, and a second "
                             "pass that read no value", added=True)


# ------------------------------------------------------------------------ pin
def leg_pin():
    """Every declared range, not the one that happened to be measured first.

    This read a single range until 2026-09-09. The package declared two, and the
    unmeasured one was where a floor went wrong: it named the release that first
    carries the member an inventory asked about, and not the release where the
    thing that uses it actually runs.
    """
    if not os.path.exists(PIN):
        return leg("pin", 2, "pin_evidence.json absent; run probe_pin.py")
    with open(PIN, encoding="utf-8") as handle:
        evidence = json.load(handle)
    if "distributions" not in evidence:
        return leg("pin", 2, "pin_evidence.json predates the two-subject sweep "
                             "and covers one range; re-run probe_pin.py")
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as handle:
        pyproject = handle.read()
    found = evidence["distributions"]
    if not found:
        return leg("pin", 2, "the evidence names no distribution, so it is an "
                             "absence reported as a pass")
    stale, red, notes = [], [], []
    for dist, body in sorted(found.items()):
        if body["declared_range"] not in pyproject:
            stale.append(f"{dist} was measured against {body['declared_range']}, "
                         f"which pyproject.toml no longer declares")
            continue
        if not body["results"]:
            stale.append(f"{dist} has no results; nothing was installed or run")
            continue
        if not body["every_release_in_range_runs_clean"]:
            red.append(dist)
        notes.append(f"{body['declared_range']} ({len(body['inside_range'])} "
                     f"inside, floor forced by "
                     f"{sorted(body['floor_is_forced_by'])})")
    if stale:
        return leg("pin", 2, "; ".join(stale))
    if red:
        return leg("pin", 1, f"a release inside the declared range does not run "
                             f"clean for {red}; the range is a claim that is "
                             f"not true")
    return leg("pin", 0, "; ".join(notes))


# ----------------------------------------------------------------------- ship
def leg_ship(python):
    check = subprocess.run([python, "-c", "import build"], capture_output=True)
    if check.returncode:
        return leg("ship", 2, "the `build` module is not installed; cannot make "
                              "a wheel, so nothing has been installed clean")
    workdir = tempfile.mkdtemp(prefix="fla-ship-")
    try:
        made = subprocess.run([python, "-m", "build", "--wheel", "--outdir",
                               workdir, ROOT], capture_output=True, text=True,
                              timeout=900)
        if made.returncode:
            return leg("ship", 2, f"build failed: {made.stdout[-200:]}")
        wheels = [f for f in os.listdir(workdir) if f.endswith(".whl")]
        if not wheels:
            return leg("ship", 2, "build succeeded and produced no wheel")
        wheel = os.path.join(workdir, wheels[0])
        env = os.path.join(workdir, "v")
        subprocess.run([python, "-m", "virtualenv", "-q", env], check=True,
                       timeout=900)
        pip = os.path.join(env, "bin", "pip")
        installed = subprocess.run(
            [pip, "install", "-q", f"{wheel}[detect]", "pytest", "pyyaml"],
            capture_output=True, text=True, timeout=1800)
        if installed.returncode:
            return leg("ship", 2, f"install failed: {installed.stderr[-200:]}")
        shipped_python = os.path.join(env, "bin", "python")
        # The installed package, NOT the source tree: PYTHONPATH is cleared so
        # an import can only resolve to what the wheel put there.
        clean_env = dict(os.environ)
        clean_env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [shipped_python, "-m", "factory_line_audit.cli"]
            + detect_argv(os.path.join(CORPUS, "clean.json")),
            capture_output=True, text=True, cwd=workdir, env=clean_env,
            timeout=900)
        where = subprocess.run(
            [shipped_python, "-c",
             "import factory_line_audit as m; print(m.__file__)"],
            capture_output=True, text=True, env=clean_env, timeout=120)
        if SRC in where.stdout:
            return leg("ship", 2, "the installed interpreter resolved the "
                                  "source tree; this leg tested nothing")
        if proc.returncode != 0:
            return leg("ship", 1 if proc.returncode == 1 else 2,
                       f"the built artifact exits {proc.returncode}: "
                       f"{proc.stderr.strip()[-160:]}")
        suite = subprocess.run(
            [shipped_python, "-m", "pytest", os.path.join(ROOT, "tests"), "-q"],
            capture_output=True, text=True, cwd=workdir, env=clean_env,
            timeout=900)
        tail = [line for line in suite.stdout.strip().splitlines() if line][-1:]
        if suite.returncode:
            return leg("ship", 1, f"the suite fails against the installed "
                                  f"artifact: {tail}")
        return leg("ship", 0, f"wheel built, installed into an empty "
                              f"environment, detect clean and suite green "
                              f"there: {tail[0] if tail else ''}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable,
                        help="interpreter with the engine installed")
    parser.add_argument("--live-python", default=sys.executable,
                        help="interpreter with asyncua installed. Separate on "
                             "purpose: an extra installed to make one leg run "
                             "can pull a transitive major into the others")
    parser.add_argument("--no-ship", action="store_true")
    parser.add_argument("--only", action="append", metavar="LEG",
                        help="run only these legs, by name. Repeatable. A name "
                             "no leg carries is REFUSED rather than answered "
                             "with an empty run, because a battery that ran "
                             "nothing still exits 0 and reads like one that "
                             "passed")
    args = parser.parse_args()

    selected = None
    if args.only:
        unknown = [name for name in args.only if name not in SELECTABLE]
        if unknown:
            print(f"no leg named {unknown}; this battery runs "
                  f"{sorted(SELECTABLE)}")
            return INCOMPLETE
        selected = set(args.only)
        # `gate` refuses the file `draft` writes, so it cannot be asked for on
        # its own. Running its predecessor is honest -- both get reported.
        if "gate" in selected:
            selected.add("draft")

    def wanted(name):
        return selected is None or name in selected

    print(f"factory-line-audit verification battery")
    print(f"  engine interpreter: {args.python}")
    print(f"  live interpreter:   {args.live_python}\n")

    workdir = tempfile.mkdtemp(prefix="fla-battery-")
    try:
        drafted = None
        # First: `corpus` reads the window out of `engine_floors.json`, so
        # whether that file still describes the engine comes before anything
        # derived from it.
        if wanted("engine"):
            leg_engine(args.python, workdir)
        if wanted("corpus"):
            leg_corpus()
        if wanted("live"):
            leg_live(args.live_python)
        if wanted("draft"):
            _, drafted = leg_draft(args.python, workdir)
        if wanted("gate"):
            leg_gate(args.python, drafted)
        if wanted("clean"):
            leg_clean(args.python)
        if wanted("fault") or wanted("absent"):
            leg_faults(args.python)
        if wanted("attest"):
            leg_attest(args.python, workdir)
        if wanted("pipe"):
            leg_pipe(args.python)
        if wanted("tool"):
            leg_tool(args.python, workdir)
        if wanted("suite"):
            leg_suite(args.python)
        if wanted("conformance"):
            leg_conformance(args.python)
        if wanted("regression"):
            leg_regression(args.python, workdir)
        if wanted("capture"):
            leg_capture(args.live_python, workdir)
        if wanted("pin"):
            leg_pin()
        if wanted("ship"):
            if args.no_ship:
                leg("ship", 2, "NOT RUN: --no-ship. Every other leg ran against "
                               "a source tree no consumer will ever have")
            else:
                leg_ship(args.python)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    worst = max(row["code"] for row in RESULTS)
    unrun = [row["leg"] for row in RESULTS if row["code"] == 2]
    print(f"\n  {'-' * 68}")
    print(f"  {len(RESULTS)} legs, worst {worst}"
          + (f"; could not complete: {unrun}" if unrun else ""))
    print(f"  OUTCOME battery_exit={worst} legs={len(RESULTS)} "
          f"green={sum(1 for r in RESULTS if r['code'] == 0)} "
          f"findings={sum(1 for r in RESULTS if r['code'] == 1)} "
          f"incomplete={len(unrun)}")
    with open(os.path.join(HERE, "battery_result.json"), "w", encoding="utf-8") as h:
        # `only` is recorded even when it is null. A partial run whose result
        # file looked like a full one would be a green nobody could question.
        json.dump({"legs": RESULTS, "exit": worst,
                   "only": sorted(selected) if selected else None}, h, indent=2)
        h.write("\n")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
