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
environment, install that exact version, and run this package's own `detect`
against the clean corpus. Not an API inventory -- the run, because an import
that succeeds is not evidence that a verdict is right.

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
DIST = "arbiter-engine"


def declared_range() -> str:
    """Read the range out of pyproject rather than repeating it here.

    Two records of one number drift, and the one that drifts is always the copy
    in the file nobody edits when the pin changes.
    """
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as handle:
        for line in handle:
            if DIST in line and ">=" in line:
                return line.split('"')[1]
    raise SystemExit(f"no {DIST} pin found in pyproject.toml")


def parse(spec: str):
    lower = spec.split(">=")[1].split(",")[0].strip()
    upper = spec.split("<")[-1].strip()
    return lower, upper


def as_tuple(version: str):
    return tuple(int(part) for part in version.split(".") if part.isdigit())


def published():
    with urllib.request.urlopen(
            f"https://pypi.org/pypi/{DIST}/json", timeout=30) as response:
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


def main() -> int:
    spec = declared_range()
    lower, upper = parse(spec)
    everything = published()
    inside = [v for v in everything
              if as_tuple(lower) <= as_tuple(v) < as_tuple(upper)]
    below = [v for v in everything if as_tuple(v) < as_tuple(lower)]
    print(f"declared range: {spec}")
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
                 f"{DIST}=={version}"], capture_output=True, text=True, timeout=900)
            if install.returncode:
                results[version] = {"installed": False,
                                    "why": install.stderr.strip()[-200:]}
                print(f"  {version}: install failed")
                continue
            outcome = run_detect(python)
            results[version] = dict(outcome, installed=True,
                                    inside_range=version in inside)
            print(f"  {version}: exit {outcome['exit']}  {outcome['outcome'] or outcome['stderr']}")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    inside_ok = all(results[v].get("exit") == 0 for v in inside if v in results)
    body = {
        "declared_range": spec, "lower": lower, "upper": upper,
        "published": everything, "inside_range": inside,
        "results": results,
        "every_release_in_range_runs_clean": inside_ok,
        "floor_is_forced_by": {
            v: results[v].get("stderr") or results[v].get("outcome")
            for v in below[-3:] if v in results},
    }
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(body, handle, indent=2)
        handle.write("\n")
    print(f"\nwrote {OUT}")
    print(f"every release inside the declared range runs clean: {inside_ok}")
    return 0 if inside_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
