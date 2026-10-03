"""The pin sweep builds the corpus again before each engine release.

One corpus fed every release in version order, and it aged through the sweep.
On 0.2.31, CONSERVATION on `ST-02` `parts_in_per_interval` answers at 241 s and
declines `insufficient_samples` by 331 s, while the guard compared the corpus's
age with MONOTONICITY's 900 s window. So a sweep slowed by other work asked its
later releases a question its earlier ones were not asked, and recorded one
decline more for them. That was read twice as a boundary between engine
versions.

Each engine release is now asked a corpus built for it, after its install, and
the result keeps that corpus's stamp and its age at the run. The slow sweep
below runs on a simulated clock: every install takes a hundred seconds, and the
stand-in for `detect` adds that decline on a corpus older than three hundred,
inside the bracket the engine was measured in.
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "battery"))

import probe_pin  # noqa: E402

EVIDENCE = ROOT / "battery" / "pin_evidence.json"

INSTALL_S = 100
QUIET_AFTER_S = 300
SIX = [{"reason": "partially_checked", "axiom": "MONOTONICITY", "entity": f"C-{n}",
        "indicator": "count"} for n in range(6)]
QUIET = {"reason": "insufficient_samples", "axiom": "CONSERVATION", "entity": "ST-02",
         "indicator": "parts_in_per_interval"}
PUBLISHED = ["0.2.28", "0.2.29", "0.2.30", "0.2.31", "0.2.32"]


def _stamp(moment):
    return moment.isoformat().replace("+00:00", "Z")


def _moment(stamp):
    return _dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _done(code=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)


class SlowSweep:
    """`subprocess.run` for a sweep whose installs take INSTALL_S seconds each,
    on a clock this object owns."""

    def __init__(self):
        self.clock = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
        self.started = self.clock
        self.builds = True
        self.build_exit = 0
        self.calls = []

    def now(self):
        return self.clock

    def build(self):
        Path(probe_pin.CORPUS).write_text(
            json.dumps({"source": {"built_at": _stamp(self.clock)}}), encoding="utf-8")

    def __call__(self, argv, **_kwargs):
        if argv[1:2] == [probe_pin.MAKE_CORPUS]:
            self.calls.append("corpus")
            if self.build_exit:
                return _done(self.build_exit, stderr="REFUSED: the floors are absent")
            if self.builds:
                self.build()
            return _done()
        if "virtualenv" in argv:
            self.calls.append("environment")
            return _done()
        if argv[1:2] == ["install"]:
            self.calls.append("install")
            self.clock += _dt.timedelta(seconds=INSTALL_S)
            return _done()
        if "detect" in argv:
            self.calls.append("detect")
            walk = json.loads(Path(argv[argv.index("--walk") + 1]).read_text())
            age = (self.clock - _moment(walk["source"]["built_at"])).total_seconds()
            rows = SIX + ([QUIET] if age > QUIET_AFTER_S else [])
            Path(argv[argv.index("--attest-out") + 1]).write_text(
                json.dumps({"declined": {"rows": rows}}), encoding="utf-8")
            return _done(stdout=f"OUTCOME exit=0 verdict=clean declined={len(rows)}\n")
        raise AssertionError(f"the sweep ran something this stand-in does not know: {argv}")


@pytest.fixture()
def slow(tmp_path, monkeypatch):
    sweep = SlowSweep()
    monkeypatch.setattr(probe_pin, "CORPUS", str(tmp_path / "clean.json"))
    monkeypatch.setattr(probe_pin, "_now", sweep.now)
    monkeypatch.setattr(probe_pin.subprocess, "run", sweep)
    monkeypatch.setattr(probe_pin, "published", lambda dist: list(PUBLISHED))
    monkeypatch.setattr(probe_pin, "declared_range", lambda dist: f"{dist}>=0.2.29,<0.3")
    return sweep


class TestASlowSweep:

    def test_one_corpus_ageing_through_it_names_its_later_releases(self, slow, monkeypatch):
        """NON-VACUITY. Fed one corpus, as before, the stand-in reproduces what the
        sweep recorded: the releases reached after the corpus passed the age the
        arm goes quiet at decline one row more, and are named for it."""
        slow.build()

        def as_before():
            built = probe_pin.corpus_built_at()
            return (slow.clock - _moment(built)).total_seconds(), built

        monkeypatch.setattr(probe_pin, "rebuild_corpus", as_before)
        found = probe_pin.sweep("arbiter-engine", probe_pin.run_detect)
        assert found["declined_differently"] == {
            "0.2.31": {"added": [QUIET], "lacked": []},
            "0.2.32": {"added": [QUIET], "lacked": []}}

    def test_a_corpus_built_for_each_release_asks_every_one_at_one_age(self, slow):
        found = probe_pin.sweep("arbiter-engine", probe_pin.run_detect)
        results = list(found["results"].values())
        assert (slow.clock - slow.started).total_seconds() == INSTALL_S * len(PUBLISHED)
        assert [r["corpus_age_s"] for r in results] == [0] * len(PUBLISHED)
        assert found["declined_differently"] == {}
        assert all(r["declined_rows"] == SIX for r in results)

    def test_each_release_gets_its_own_corpus_after_its_install(self, slow):
        found = probe_pin.sweep("arbiter-engine", probe_pin.run_detect)
        stamps = [r["corpus_built_at"] for r in found["results"].values()]
        assert stamps == sorted(set(stamps)) and len(stamps) == len(PUBLISHED)
        assert slow.calls == ["environment", "install", "corpus", "detect"] * len(PUBLISHED)

    def test_the_sweep_needs_no_corpus_built_before_it(self, slow, tmp_path, monkeypatch):
        """The workflow built one before the sweep, and the sweep refused to start
        without a young one. Neither is needed now: nothing is on disk here."""
        monkeypatch.setattr(probe_pin, "OUT", str(tmp_path / "pin_evidence.json"))
        monkeypatch.setattr(probe_pin, "SUBJECTS", {"arbiter-engine": probe_pin.run_detect})
        monkeypatch.setattr(probe_pin, "reap_abandoned", lambda: [])
        assert not Path(probe_pin.CORPUS).exists()
        assert probe_pin.main() == 0
        written = json.loads((tmp_path / "pin_evidence.json").read_text())
        results = written["distributions"]["arbiter-engine"]["results"]
        assert [r["corpus_age_s"] for r in results.values()] == [0] * len(PUBLISHED)


class TestARebuildThatDidNotHappenIsRefused:

    def test_a_rebuild_that_failed(self, slow, capsys):
        slow.build_exit = 2
        with pytest.raises(SystemExit) as raised:
            probe_pin.rebuild_corpus()
        assert raised.value.code == 2
        assert "make_corpus.py exited 2" in capsys.readouterr().err

    def test_a_rebuild_that_left_the_old_corpus_in_place(self, slow, capsys):
        """Exit 0 and nothing written: the corpus on disk is the one before, and
        it may still be young enough to pass any window."""
        slow.build()
        slow.builds = False
        slow.clock += _dt.timedelta(seconds=5)
        with pytest.raises(SystemExit) as raised:
            probe_pin.rebuild_corpus()
        assert raised.value.code == 2
        assert "is still stamped" in capsys.readouterr().err


def _battery():
    spec = importlib.util.spec_from_file_location(
        "fla_run_battery_corpus_per_release", ROOT / "battery" / "run_battery.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def pin(tmp_path, monkeypatch, capsys):
    """`leg_pin` over a copy of the committed evidence, edited by the test."""
    battery = _battery()

    def run(mutate=None):
        evidence = json.loads(EVIDENCE.read_text())
        if mutate:
            mutate(evidence["distributions"]["arbiter-engine"]["results"])
        path = tmp_path / "pin_evidence.json"
        path.write_text(json.dumps(evidence), encoding="utf-8")
        monkeypatch.setattr(battery, "PIN", str(path))
        monkeypatch.setattr(battery, "_installed_version", lambda dist: None)
        code = battery.leg_pin()
        capsys.readouterr()
        return code, battery.RESULTS[-1]["note"]

    run.floor = battery.FAULT_AGE_FLOOR_S
    return run


class TestTheEvidence:

    def test_every_engine_release_records_a_corpus_built_for_it(self, pin):
        body = json.loads(EVIDENCE.read_text())["distributions"]["arbiter-engine"]
        ran = [r for r in body["results"].values() if r.get("installed")]
        assert ran, "no engine release was installed, so this would pass over nothing"
        stamps = [r["corpus_built_at"] for r in ran]
        assert stamps == sorted(set(stamps)) and len(stamps) == len(ran)
        assert max(r["corpus_age_s"] for r in ran) <= pin.floor

    def test_the_leg_reads_the_committed_evidence_and_says_so(self, pin):
        code, note = pin()
        assert code == 0, note
        assert "each engine release asked a corpus built for it, at most" in note

    def test_the_leg_refuses_evidence_from_one_ageing_corpus(self, pin):
        def as_before(results):
            for result in results.values():
                result.pop("corpus_built_at", None)
                result.pop("corpus_age_s", None)

        code, note = pin(as_before)
        assert code == 2, note
        assert "predates the corpus built per release" in note

    def test_the_leg_refuses_a_release_asked_an_old_corpus(self, pin):
        def one_old(results):
            last = [v for v, r in results.items() if r.get("installed")][-1]
            results[last]["corpus_age_s"] = pin.floor + 1

        code, note = pin(one_old)
        assert code == 2, note
        assert f"past the measured {pin.floor}s floor" in note
