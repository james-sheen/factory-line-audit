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
the engine by `detect` against a clean corpus built for each run, the neutral
core by `probe_conformance.py`, which is what asks the core whether it still
accepts this vertical.

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

import datetime as _dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "pin_evidence.json")
CORPUS = os.path.join(HERE, "corpus", "clean.json")
MAKE_CORPUS = os.path.join(HERE, "make_corpus.py")


#: One definition of the work-directory prefix, because the reaper and the
#: `mkdtemp` that creates them have to agree. Written twice, the two drift and
#: the reaper quietly stops matching anything -- which reads exactly like a
#: machine that never leaks. Namespaced to this tool: the prefix used to be a
#: bare `pin-`, which is a wide net to sweep a shared /tmp with.
WORK_PREFIX = "fla-pin-"

#: How old an abandoned directory must be before it is reaped. Anything younger
#: could belong to a probe running right now.
REAP_AFTER_SECONDS = 6 * 3600


def reap_abandoned(prefix: str = WORK_PREFIX,
                   older_than: int = REAP_AFTER_SECONDS) -> list[str]:
    """Remove work directories a previous run was killed before cleaning up.

    The `finally` below covers exceptions. It does not cover SIGKILL, a
    timed-out CI step or a reboot, and a run that dies that way leaves one
    virtualenv per release tried -- gigabytes, with nothing left alive to
    remove them. So this reaps on the way IN: the run that leaked is by
    definition not around to clean up on the way out.

    Conservative on purpose. A directory is reaped only when it carries this
    tool's own prefix, is older than the threshold -- so a probe running
    concurrently is never touched -- and either holds an environment or is the
    empty shell of a run that died before building one. Anything else wearing
    the prefix belongs to somebody else and is left alone.
    """
    reaped = []
    cutoff = time.time() - older_than
    for path in sorted(pathlib.Path(tempfile.gettempdir()).glob(f"{prefix}*")):
        if path.is_symlink() or not path.is_dir():
            continue
        try:
            if path.stat().st_mtime >= cutoff:
                continue
            occupied = any(path.iterdir())
        except OSError:
            continue
        if occupied and not any(path.glob("*/pyvenv.cfg")):
            continue
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            reaped.append(path.name)
    return reaped


def _now() -> _dt.datetime:
    """The clock every stamp and age in the evidence is read from, in one
    place so a test can run a slow sweep on a clock of its own."""
    return _dt.datetime.now(_dt.timezone.utc)


def corpus_built_at() -> str:
    """When the walk the engine subject reads was built, from the walk itself."""
    with open(CORPUS, encoding="utf-8") as handle:
        walk = json.load(handle)
    built = (walk.get("source") or {}).get("built_at")
    if not built:
        print(f"REFUSED: {CORPUS} does not say when it was built, so this sweep "
              f"cannot know whether the engines or the clock answered it.",
              file=sys.stderr)
        raise SystemExit(2)
    return built


def rebuild_corpus() -> tuple:
    """`(age_seconds, built_at)` of a corpus built for the run about to read it.

    WHY ITS AGE MATTERS. Four engine versions were recorded with the
    byte-identical line `declined=11`, which cannot be right: B6 measured that
    from 0.1.11 an undeclared MONOTONICITY rate arm declines where 0.1.10
    answered from a default, and this fixture leaves six of eight counters
    undeclared. Measured on a fresh corpus the two differ by exactly six -- 1
    against 7. Measured on a three-hour-old one they are both 11, because every
    windowed arm has gone quiet with `insufficient_samples` and that decline
    arrives before the threshold question is ever reached. So four identical
    lines were recorded as evidence about four engines.

    WHY BEFORE EACH RELEASE, AND NOT ONCE PER SWEEP. One corpus then fed every
    release, refused if older than MONOTONICITY's 900 s window -- at the start,
    and again before writing. An arm goes quiet long before that: on 0.2.31,
    CONSERVATION on `ST-02` `parts_in_per_interval` answers at 241 s and
    declines `insufficient_samples` by 331 s, and 0.2.24, asked the same corpus
    beside it, adds the same decline. The sweep runs releases in version order,
    so a sweep slowed by other work crossed that age part-way, and its later
    releases recorded one decline more than its earlier ones. That was read
    twice as a boundary between engine versions, at 0.2.20 and at 0.2.25.
    Built here, every release is asked at the same age however long the
    installs between them take, and nothing has to know which arm quiets
    first.

    A rebuild that failed would leave the previous corpus in place, perhaps
    still young enough to pass any window, so the stamp is checked against the
    moment this rebuild started.
    """
    started = _now().replace(microsecond=0)
    proc = subprocess.run([sys.executable, MAKE_CORPUS], capture_output=True,
                          text=True, cwd=ROOT, timeout=900)
    if proc.returncode:
        print(f"REFUSED: make_corpus.py exited {proc.returncode} rebuilding the "
              f"corpus: {' '.join(proc.stderr.strip().splitlines()[-1:])}",
              file=sys.stderr)
        raise SystemExit(2)
    built = corpus_built_at()
    stamp = _dt.datetime.fromisoformat(built.replace("Z", "+00:00"))
    if stamp < started:
        print(f"REFUSED: make_corpus.py exited 0 and {CORPUS} is still stamped "
              f"{built}, before this rebuild started at "
              f"{started.isoformat().replace('+00:00', 'Z')}, so this release "
              f"would be asked whatever was left on disk, at whatever age it "
              f"has reached.",
              file=sys.stderr)
        raise SystemExit(2)
    return (_now() - stamp).total_seconds(), built


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


def decline_rows(attestation: dict) -> list:
    """What each decline WAS, from the attestation the same run wrote: reason,
    axiom, entity and indicator, sorted. The engine's prose is left out --
    it is written for a person, and it moves between releases on its own."""
    rows = ((attestation.get("declined") or {}).get("rows")) or []
    return sorted(({key: row.get(key) for key in ("reason", "axiom", "entity",
                                                   "indicator")}
                   for row in rows if isinstance(row, dict)),
                  key=lambda row: tuple(str(row[key]) for key in sorted(row)))


def run_detect(python: str, workdir: str) -> dict:
    """The OUTCOME line, and the declines behind its count, from ONE run, on a
    corpus built for it -- whose stamp and age the result keeps.

    THE ROWS, BECAUSE A COUNT CANNOT SAY WHICH. A loaded sweep on 2026-10-01
    recorded `declined=7` for its last eight releases where every earlier one
    and every later re-run read 6. The file kept the count alone and the re-run
    overwrote it. The attestation the same run writes names each decline, so a
    count that moves now says what moved -- and the next time, the rows named
    the arm `rebuild_corpus` explains.
    """
    age, built = rebuild_corpus()
    attestation = os.path.join(workdir, "attestation.json")
    proc = subprocess.run(
        [python, "-m", "factory_line_audit.cli", "detect",
         "--register", os.path.join(ROOT, "examples", "asset_register.json"),
         "--walk", CORPUS,
         "--declarations", os.path.join(ROOT, "examples", "declarations",
                                        "line1.fixture.json"),
         "--attest-out", attestation],
        capture_output=True, text=True, timeout=600,
        env=dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src")))
    outcome = [line for line in proc.stdout.splitlines()
               if line.startswith("OUTCOME")]
    rows = None
    if os.path.exists(attestation):
        with open(attestation, encoding="utf-8") as handle:
            rows = decline_rows(json.load(handle))
    return {"exit": proc.returncode, "outcome": outcome[0] if outcome else None,
            "declined_rows": rows,
            # STAMPED, so the evidence says what each release was measured
            # against. The file once recorded four engine versions with one
            # identical OUTCOME line, and nothing in it could say why.
            "corpus_built_at": built, "corpus_age_s": int(age),
            "stderr": proc.stderr.strip().splitlines()[-3:]}


def declined_differently(results: dict) -> dict:
    """Each release whose declines differ from the commonest set among the
    releases that recorded any, with what it added and what it lacked. Empty
    when they all agree -- which is the expected answer, and the point is
    that a disagreement names itself."""
    recorded = {version: result["declined_rows"] for version, result in results.items()
                if result.get("declined_rows") is not None}
    if not recorded:
        return {}
    keyed = {version: json.dumps(rows, sort_keys=True)
             for version, rows in recorded.items()}
    tally: dict = {}
    for key in keyed.values():
        tally[key] = tally.get(key, 0) + 1
    common = max(tally, key=lambda key: (tally[key], key))
    baseline = {json.dumps(row, sort_keys=True) for row in json.loads(common)}
    odd = {}
    for version, key in keyed.items():
        if key == common:
            continue
        mine = {json.dumps(row, sort_keys=True) for row in recorded[version]}
        odd[version] = {"added": [json.loads(row) for row in sorted(mine - baseline)],
                        "lacked": [json.loads(row) for row in sorted(baseline - mine)]}
    return odd


def run_conformance(python: str, workdir: str) -> dict:
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
        workdir = tempfile.mkdtemp(prefix=f"{WORK_PREFIX}{version}-")
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
            outcome = run(python, workdir)
            results[version] = dict(outcome, installed=True,
                                    inside_range=version in inside)
            print(f"  {version}: exit {outcome['exit']}  "
                  f"{outcome['outcome'] or outcome['stderr']}"
                  + (f"  (corpus {outcome['corpus_age_s']}s old)"
                     if "corpus_age_s" in outcome else ""))
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    inside_ok = all(results[v].get("exit") == 0 for v in inside if v in results)
    odd = declined_differently(results)
    for version, moved in sorted(odd.items(), key=lambda item: as_tuple(item[0])):
        print(f"  NOTE: {version} declined differently from the rest -- "
              f"added {moved['added']}, lacked {moved['lacked']}")
    return {
        "declared_range": spec, "lower": lower, "upper": upper,
        "published": everything, "inside_range": inside,
        "results": results,
        "every_release_in_range_runs_clean": inside_ok,
        # Named, not counted: an empty map is every release declining alike.
        "declined_differently": odd,
        # TWO FIELDS, BECAUSE THEY WERE ONE AND IT WAS A CLAIM THE DATA DID NOT
        # CARRY. `floor_is_forced_by` held every control checked below the
        # floor, whether it failed or not, and the battery printed *floor
        # forced by* over the list. That was true only while the controls
        # failed -- which they did, until a floor was raised to a release the
        # ones below it also satisfy. Then the sentence named three releases
        # as forcing a floor they do not force, and nothing could tell.
        #
        # A passing control is evidence the floor is HIGHER than anything here
        # measured. It is not evidence the floor is wrong, and it is not
        # evidence the floor is needed. Keeping both sets lets the reader be
        # told which of those it is looking at.
        "checked_below": {
            v: results[v].get("stderr") or results[v].get("outcome")
            for v in below[-3:] if v in results},
        "floor_is_forced_by": {
            v: results[v].get("stderr") or results[v].get("outcome")
            for v in below[-3:]
            if v in results and results[v].get("exit") != 0},
    }


def main() -> int:
    abandoned = reap_abandoned()
    if abandoned:
        print(f"reaped {len(abandoned)} work director"
              f"{'y' if len(abandoned) == 1 else 'ies'} left by a killed run: "
              f"{', '.join(abandoned)}")
    body = {"measured_on": _now().replace(microsecond=0).isoformat()
            .replace("+00:00", "Z"),
            "distributions": {}}
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
