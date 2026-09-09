#!/usr/bin/env python3
"""C8: exercise the pin, including its floor.

BRIDGES C8: *pin a range, and verify the version a consumer actually resolves.
A range is a claim about every release inside it, so exercise the floor too.*

The verification battery's table has no leg for this. Every other capability in
the list has one -- C1 is `clean`, C4 is `draft`, C5 is `gate`, C7 is `attest`,
C9 is the ladder -- and the one capability that is a claim about software this
package does not control has none. So this file is the leg, and `run_battery.py`
reads what it writes.

What it does: for every release the declared range admits, build a throwaway
environment, install that exact version, and RUN something. Not an API
inventory -- the run, because an import that succeeds is not evidence that a
verdict is right.

TWO SUBJECTS since 2026-09-09, because this package declares two ranges and only
one of them was ever exercised. Each is run by the thing that actually uses it:
the engine by `detect` against the clean corpus, the neutral core by
`probe_conformance.py`, which is what asks the core whether it still accepts this
vertical.

The second subject was added the day an inventory got a floor wrong. The core's
floor was written `>=0.1.5` from an install sweep that asked which release first
carries `conformance.check_a_vocabulary` -- correct, and not the floor. Running
the leg at 0.1.5 refused it: the kit is there and `vocabulary.using`, which the
leg also needs, is not. Both numbers came off one sweep and only one of them had
been run. That is the whole argument for this file, and it had just been made
against it.

It writes `pin_evidence.json` and refuses to overwrite it with a partial result.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "pin_evidence.json")
CORPUS = os.path.join(HERE, "corpus", "clean.json")


def declared_range(dist: str) -> str:
    """Read the range out of pyproject rather than repeating it here.

    Two records of one number drift, and the one that drifts is always the copy
    in the file nobody edits when the pin changes.
    """
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as handle:
        for line in handle:
            if dist in line and ">=" in line and not line.lstrip().startswith("#"):
                return line.split('"')[1]
    raise SystemExit(f"no {dist} pin found in pyproject.toml")


def parse(spec: str):
    lower = spec.split(">=")[1].split(",")[0].strip()
    upper = spec.split("<")[-1].strip()
    return lower, upper


def as_tuple(version: str):
    return tuple(int(part) for part in version.split(".") if part.isdigit())


def published(dist: str):
    with urllib.request.urlopen(
            f"https://pypi.org/pypi/{dist}/json", timeout=30) as response:
        return sorted(json.load(response)["releases"], key=as_tuple)


def run_detect(python: str) -> dict:
    proc = subprocess.run(
        [python, "-m", "factory_line_audit.cli", "detect",
         "--register", os.path.join(ROOT, "examples", "asset_register.json"),
         "--walk", CORPUS,
         "--declarations", os.path.join(ROOT, "examples", "declarations",
                                        "line1.fixture.json")],
        capture_output=True, text=True, timeout=600,
        env=dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src")))
    outcome = [line for line in proc.stdout.splitlines()
               if line.startswith("OUTCOME")]
    return {"exit": proc.returncode, "outcome": outcome[0] if outcome else None,
            "stderr": proc.stderr.strip().splitlines()[-3:]}


def run_conformance(python: str) -> dict:
    """The core's subject is whether it still accepts this vertical, so the run
    is the same probe the `conformance` leg runs -- not a second opinion about
    it. A release where the probe cannot even start reports 2 and says why,
    which is what forces a floor rather than a preference."""
    proc = subprocess.run(
        [python, os.path.join(HERE, "probe_conformance.py")],
        capture_output=True, text=True, timeout=600,
        env=dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src")))
    note = None
    try:
        note = json.loads(proc.stdout).get("note")
    except Exception:                                        # pragma: no cover
        pass
    # The probe's note when there is one, and never the traceback beside it.
    # What goes in here is COMMITTED, and a traceback carries the absolute path
    # of whatever machine ran the sweep. That reached this file once and the
    # repository's own hygiene gate refused the commit.
    fallback = [line for line in proc.stderr.strip().splitlines()
                if line.strip() and not line.lstrip().startswith("File ")]
    return {"exit": proc.returncode,
            "outcome": f"OUTCOME conformance={proc.returncode} {note}" if note
                       else None,
            "stderr": [] if note else fallback[-1:]}


#: What each declared range is exercised BY. A range with no runner here is a
#: claim this file cannot make, so adding a pin means adding its run.
SUBJECTS = {"arbiter-engine": run_detect, "presence-audit": run_conformance}


def sweep(dist: str, run) -> dict:
    spec = declared_range(dist)
    lower, upper = parse(spec)
    everything = published(dist)
    inside = [v for v in everything
              if as_tuple(lower) <= as_tuple(v) < as_tuple(upper)]
    below = [v for v in everything if as_tuple(v) < as_tuple(lower)]
    print(f"\ndeclared range: {spec}")
    print(f"  published:  {everything}")
    print(f"  inside:     {inside}")
    print(f"  below (checked too, to show the floor is where it is because it "
          f"has to be): {below[-3:]}")

    results = {}
    for version in below[-3:] + inside:
        workdir = tempfile.mkdtemp(prefix=f"pin-{version}-")
        python = os.path.join(workdir, "v", "bin", "python")
        try:
            subprocess.run([sys.executable, "-m", "virtualenv", "-q",
                            os.path.join(workdir, "v")], check=True, timeout=600)
            install = subprocess.run(
                [os.path.join(workdir, "v", "bin", "pip"), "install", "-q",
                 f"{dist}=={version}"], capture_output=True, text=True,
                timeout=900)
            if install.returncode:
                results[version] = {"installed": False,
                                    "why": install.stderr.strip()[-200:]}
                print(f"  {version}: install failed")
                continue
            outcome = run(python)
            results[version] = dict(outcome, installed=True,
                                    inside_range=version in inside)
            print(f"  {version}: exit {outcome['exit']}  "
                  f"{outcome['outcome'] or outcome['stderr']}")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    inside_ok = all(results[v].get("exit") == 0 for v in inside if v in results)
    return {
        "declared_range": spec, "lower": lower, "upper": upper,
        "published": everything, "inside_range": inside,
        "results": results,
        "every_release_in_range_runs_clean": inside_ok,
        "floor_is_forced_by": {
            v: results[v].get("stderr") or results[v].get("outcome")
            for v in below[-3:] if v in results},
    }


def main() -> int:
    body = {"distributions": {}}
    for dist, run in SUBJECTS.items():
        body["distributions"][dist] = sweep(dist, run)

    # Refuse a partial write: a range with no result is a range this file would
    # then be silent about, and silence here reads as a pin that was exercised.
    thin = [dist for dist, found in body["distributions"].items()
            if not found["results"]]
    if thin:
        print(f"\nnothing ran for {thin}; refusing to overwrite {OUT}")
        return 2

    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(body, handle, indent=2)
        handle.write("\n")
    every = all(found["every_release_in_range_runs_clean"]
                for found in body["distributions"].values())
    print(f"\nwrote {OUT}")
    for dist, found in body["distributions"].items():
        print(f"  {dist}: every release inside {found['declared_range']} runs "
              f"clean: {found['every_release_in_range_runs_clean']}")
    return 0 if every else 1

if __name__ == "__main__":
    raise SystemExit(main())
