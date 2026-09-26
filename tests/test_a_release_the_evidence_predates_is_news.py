"""A release upstream is news, not a defect in this repository.

The battery's `pin` and `engine` legs read committed evidence -- the pin sweep
and the engine floors -- and both went red on the next push after any release
of arbiter-engine or presence-audit inside this package's ranges, whoever made
that push and whatever it changed: twice on 2026-09-26, a push that changed only
a workflow among them. The live question is asked where it belongs -- `pin.yml`
sweeps the index every Monday and whenever a range or a probe changes -- so a
release the evidence predates is a notice now.

What still fails is evidence that is WRONG rather than behind: a release the
sweep should have seen and did not, a release that does not run, a measured
floor that moved. Each of those is asserted below beside the case that became a
notice, because a leg that stopped failing altogether would pass the notice
tests too.
"""

from __future__ import annotations

import importlib.util
import json
import os

import pytest

from conftest import ROOT

EVIDENCE = os.path.join(ROOT, "battery", "pin_evidence.json")
FLOORS = os.path.join(ROOT, "src", "factory_line_audit", "engine_floors.json")


def _battery():
    """The runner, by path: the battery is scripts, not a package."""
    spec = importlib.util.spec_from_file_location(
        "fla_run_battery_news", os.path.join(ROOT, "battery", "run_battery.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _after(version):
    """The next patch release after `version`: one nobody has swept."""
    parts = version.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def _newest(dist):
    order = _battery()._release_order()
    return max(_load(EVIDENCE)["distributions"][dist]["published"], key=order)


@pytest.fixture()
def pin(tmp_path, monkeypatch, capsys):
    """Run `leg_pin` over a copy of the committed evidence, with the installed
    versions chosen by the test rather than by this interpreter."""
    battery = _battery()

    def run(installed, mutate=None):
        evidence = _load(EVIDENCE)
        if mutate:
            mutate(evidence)
        path = tmp_path / "pin_evidence.json"
        path.write_text(json.dumps(evidence), encoding="utf-8")
        monkeypatch.setattr(battery, "PIN", str(path))
        monkeypatch.setattr(battery, "_installed_version",
                            lambda dist: installed.get(dist))
        code = battery.leg_pin()
        return code, battery.RESULTS[-1]["note"], capsys.readouterr().out

    return run


class TestThePinLeg:

    def test_the_committed_evidence_holds_for_the_releases_it_swept(self, pin):
        """NON-VACUITY. Every case below edits this evidence, so it has to pass
        the leg's structural checks as committed; otherwise the notice cases
        would be reading a leg that had already failed for another reason."""
        code, note, _ = pin({dist: _newest(dist) for dist in
                             ("arbiter-engine", "presence-audit")})
        assert code == 0, note
        assert "NOTICE" not in note

    @pytest.mark.parametrize("dist", ["arbiter-engine", "presence-audit"])
    def test_a_release_newer_than_the_sweep_is_a_notice(self, pin, dist):
        newer = _after(_newest(dist))
        code, note, out = pin({dist: newer})
        assert code == 0, (
            f"{dist} {newer} is newer than every release the sweep saw, and "
            f"the leg failed on it: {note}")
        assert f"NOTICE: {dist} {newer}" in note
        assert f"::notice::{dist} {newer}" in out, (
            "the notice reached the leg's note and not the CI annotation")

    def test_a_release_the_sweep_should_have_seen_still_fails(self, pin):
        """Older than the newest release recorded, and missing from the sweep:
        the evidence is incomplete, which is a different fact from behind."""
        published = _load(EVIDENCE)["distributions"]["arbiter-engine"]["published"]
        order = _battery()._release_order()
        inside = sorted(published, key=order)
        missing = inside[-2]

        def drop(evidence):
            body = evidence["distributions"]["arbiter-engine"]
            body["published"] = [v for v in body["published"] if v != missing]

        code, note, _ = pin({"arbiter-engine": missing}, drop)
        assert code == 2, note
        assert "never saw this release" in note

    def test_a_release_that_does_not_run_is_red_beside_a_notice(self, pin):
        """The notice must not mask a range that is not true."""
        def broken(evidence):
            evidence["distributions"]["arbiter-engine"][
                "every_release_in_range_runs_clean"] = False

        code, note, _ = pin({"arbiter-engine": _after(_newest("arbiter-engine"))},
                            broken)
        assert code == 1, note

    def test_nothing_installed_is_still_an_answer(self, pin):
        """The leg reads a committed file and must answer where neither pinned
        distribution is installed; `None` was never a failure and is not one."""
        code, note, _ = pin({})
        assert code == 0, note
        assert "NOTICE" not in note


class TestTheEngineLeg:

    @staticmethod
    def _relabelled(record, version):
        """The same record, naming another engine wherever it names its own."""
        text = json.dumps(record).replace(f'"{record["engine_version"]}"',
                                          f'"{version}"')
        return json.loads(text)

    def test_a_version_label_alone_is_news(self):
        recorded = _load(FLOORS)
        measured = self._relabelled(recorded, _after(recorded["engine_version"]))
        assert measured["engine_version"] != recorded["engine_version"]
        assert _battery()._version_moved_alone(measured, recorded)

    def test_the_environment_keys_do_not_count_against_it(self):
        recorded = _load(FLOORS)
        measured = self._relabelled(recorded, _after(recorded["engine_version"]))
        measured["measured_on"] = "2099-01-01T00:00:00+00:00"
        measured["python"] = "3.99.0"
        assert _battery()._version_moved_alone(measured, recorded)

    def test_a_moved_floor_is_not_news(self):
        """The case the engine leg exists for, and it must still fail."""
        recorded = _load(FLOORS)
        measured = self._relabelled(recorded, _after(recorded["engine_version"]))
        name = next(k for k, v in measured["floors"].items()
                    if isinstance(v.get("samples"), int))
        measured["floors"][name]["samples"] += 1
        assert not _battery()._version_moved_alone(measured, recorded)

    def test_the_same_record_is_not_a_version_move(self):
        """Nothing moved, so there is nothing to call news: the leg's own
        equality answers that case, and this function must not claim it."""
        recorded = _load(FLOORS)
        assert not _battery()._version_moved_alone(recorded, dict(recorded))
