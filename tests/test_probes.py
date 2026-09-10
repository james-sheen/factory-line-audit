"""What the probes must not do, and what their evidence must say.

**Why `ast` and not a grep.** The obvious spelling of this check -- refuse a
date-shaped string in `battery/probe_*.py` -- is red today against two files, and
both are innocent. `probe_pin.py`'s docstring says it grew a second subject on a
date, and `probe_engine.py` carries a comment explaining the frozen clock that
was already removed. **Prose describing a defect reads exactly like the defect.**
A grep cannot tell them apart, and a guard with false positives is one the next
person deletes.

Parsing gets this right for free: comments are not in the tree at all, and a
docstring is a node this can identify and skip. What is left is a date that some
code actually evaluates, which is the only kind that can freeze anything.

**Why it matters.** `probe_engine.py` had `NOW` pinned to the day it last ran.
Every series it builds counts backwards from that instant, so six days later the
windows saw nothing, two probes measured `None`, and the script died deriving a
corpus size from one. `engine_floors.json` -- the file every sample floor, every
window and the corpus size comes out of -- was a snapshot nobody could reproduce,
and nothing went red, because nothing ran it. -> the `engine` battery leg.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from conftest import ROOT

BATTERY = Path(ROOT) / "battery"
PACKAGE = Path(ROOT) / "src" / "factory_line_audit"

#: A date somebody wrote down. Not a match for `datetime.now()`, which is the
#: whole point -- one expires and the other does not.
DATE_TEXT = re.compile(r"\b20\d\d[-/]\d\d[-/]\d\d\b")

#: Constructors that build a moment out of literals. `now` and `today` take no
#: constant arguments and are deliberately absent.
BUILDS_A_MOMENT = ("datetime", "date", "fromisoformat", "fromtimestamp",
                   "strptime")


def _docstrings(tree):
    """Every node that is a docstring, by identity.

    A docstring is prose that happens to be a string expression, and this file
    exists because prose about a pinned clock is not a pinned clock.
    """
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
    return out


def pinned_clocks(source: str, name: str):
    """Every place this source EVALUATES a date it wrote down."""
    tree = ast.parse(source)
    prose = _docstrings(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in prose or not DATE_TEXT.search(node.value):
                continue
            found.append(f"{name}:{node.lineno}: the string {node.value!r}")
        if isinstance(node, ast.Call):
            called = node.func
            label = (called.attr if isinstance(called, ast.Attribute)
                     else getattr(called, "id", ""))
            if label not in BUILDS_A_MOMENT:
                continue
            literal = [a for a in node.args if isinstance(a, ast.Constant)
                       and a.value is not None]
            if literal:
                found.append(f"{name}:{node.lineno}: {label}() built from "
                             f"{[a.value for a in literal]}")
    return found


class TestNoProbePinsItsOwnClock:

    #: `make_corpus.py` is not a probe and is scanned anyway: it stamps the
    #: corpus, the `corpus` leg refuses one older than the narrowest measured
    #: window, and a frozen clock there would be the same defect wearing a
    #: different name.
    def _sources(self):
        return sorted(BATTERY.glob("probe_*.py")) + [BATTERY / "make_corpus.py"]

    def test_the_scan_found_the_probes(self):
        """Non-vacuity, and it names the number so a shrinking glob is visible.

        The claim below is *none of these pins a clock*, which is true of an
        empty set. Four probes exist; the floor is set under that so adding one
        does not turn this red, and well over zero so losing them all does.
        """
        found = self._sources()
        assert len(found) >= 4, (
            f"only {len(found)} file(s) scanned: {[p.name for p in found]}. "
            f"The glob is not finding the battery, so the rule below is a claim "
            f"about nothing")

    def test_no_probe_evaluates_a_date_it_wrote_down(self):
        offences = []
        for path in self._sources():
            offences += pinned_clocks(path.read_text(encoding="utf-8"),
                                      path.name)
        assert not offences, (
            "these evaluate a date somebody wrote down, which is an expiry "
            "date rather than a measurement:\n  " + "\n  ".join(offences))

    def test_the_detector_finds_a_pinned_clock_when_there_is_one(self):
        """Before believing the negative above, prove this can say yes.

        Both shapes the real defect took: a constructed moment, and a written
        instant parsed back. Written as source text here rather than by naming
        the retired line, so this file never contains the thing it forbids.
        """
        built = "import datetime\nNOW = datetime.datetime(2026, 9, 3, 12, 0)\n"
        parsed = ("import datetime\n"
                  "NOW = datetime.datetime.fromisoformat('2026-09-03T12:00')\n")
        assert pinned_clocks(built, "x.py"), "a constructed moment went unseen"
        assert pinned_clocks(parsed, "x.py"), "a parsed instant went unseen"

    def test_the_detector_lets_a_real_clock_and_prose_past(self):
        """The other half. A guard that flags `now()` or a comment about a date
        is one somebody switches off, and then it guards nothing."""
        live = ("import datetime\n"
                "NOW = datetime.datetime.now(datetime.timezone.utc)\n")
        prose = '"""Grew a second subject on 2026-09-09."""\nX = 1\n'
        comment = "# frozen at 2026-09-03 until it was not\nX = 1\n"
        assert not pinned_clocks(live, "x.py"), "a real clock was flagged"
        assert not pinned_clocks(prose, "x.py"), "a docstring was flagged"
        assert not pinned_clocks(comment, "x.py"), "a comment was flagged"


class TestEveryEvidenceFileNamesWhatItMeasured:
    """A measurement without the version of its subject is a number with no
    referent. `engine_floors.json` records the engine it measured, so the
    `engine` leg can say the committed floors stopped describing the engine that
    resolves; without that field the file would just be numbers.

    The map is a REVIEWED record, and the test below refuses an evidence file
    that has no row -- so a new one cannot arrive unguarded.
    """

    #: file -> what reading its subject's version out of it looks like.
    SUBJECT = {
        "engine_floors.json": lambda d: [d["engine_version"]],
        "status_words.json": lambda d: [d["asyncua"]],
        "pin_evidence.json": lambda d: [v for body in d["distributions"].values()
                                        for v in body["results"]],
    }

    VERSION = re.compile(r"^\d+\.\d+")

    #: Where committed evidence lives. `engine_floors.json` moved INTO THE
    #: PACKAGE in 0.1.7, because the installed tool reads it at run time -- and a
    #: guard that globbed only `battery/` would have gone on passing while its
    #: subject walked out of the directory it was watching.
    WHERE = (BATTERY, PACKAGE)

    def _tracked(self):
        """Evidence committed to the repository. `battery_result.json` is
        gitignored -- it records a run rather than a measurement, and it is
        rewritten by every one."""
        return sorted(p for where in self.WHERE for p in where.glob("*.json")
                      if p.name != "battery_result.json")

    def _path(self, name):
        for where in self.WHERE:
            if (where / name).exists():
                return where / name
        return None

    def test_every_committed_evidence_file_has_a_row(self):
        missing = [p.name for p in self._tracked() if p.name not in self.SUBJECT]
        assert not missing, (
            f"{missing} are committed evidence with no row here, so nothing "
            f"asks what version they describe. Add the row rather than widening "
            f"the glob")

    def test_the_map_describes_files_that_exist(self):
        """The inverse, and the cheaper mistake: a row for a file that was
        renamed or deleted passes forever without reading anything."""
        gone = [name for name in self.SUBJECT if self._path(name) is None]
        assert not gone, f"{gone} are named here and not on disk"

    @pytest.mark.parametrize("name", sorted(SUBJECT))
    def test_it_records_the_version_of_what_it_measured(self, name):
        with open(self._path(name), encoding="utf-8") as handle:
            body = json.load(handle)
        versions = self.SUBJECT[name](body)
        assert versions, f"{name} names no version of its subject"
        bad = [v for v in versions if not self.VERSION.match(str(v))]
        assert not bad, f"{name} records {bad} where a version was expected"


class TestTheCorpusSpellsStatusWordsTheWayAServerDoes:
    """R5: the population is what the real thing can produce, not what the
    fixture contains.

    OPC UA names these codes without separators -- `GoodLocalOverride`,
    `BadDeviceFailure` -- and that is what `asyncua` reports. The synthetic
    corpus wrote `Good_LocalOverride` and `Bad_DeviceFailure`, so every leg that
    judges the corpus exercised the grader against a spelling no server sends.
    The grader reads both, so this was never a wrong answer; it was a fixture
    that could not falsify its own consumer, which is worse, because it looks
    like coverage.

    Parsed rather than grepped for the same reason as the clock sweep above:
    the comments and docstrings in these files still name the retired spellings
    ON PURPOSE, because they explain what happened. A grep would report the
    explanation as the defect.
    """

    SOURCES = ("make_corpus.py", "opcua_surface.py")

    #: A status word as OPC UA spells one, or as the corpus used to.
    STATUS = re.compile(r"^(Good|Bad|Uncertain)[A-Za-z_]*$")

    def _emitted(self, path: Path):
        """Status words this source actually evaluates, with line numbers."""
        tree = ast.parse(path.read_text(encoding="utf-8"))
        prose = _docstrings(tree)
        return [(node.lineno, node.value) for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in prose
                and self.STATUS.match(node.value)]

    def test_the_scan_found_status_words(self):
        """Non-vacuity. Nothing below can fail if this found nothing, and a
        renamed file or a reworded assignment is exactly how that happens."""
        found = {name: self._emitted(BATTERY / name) for name in self.SOURCES}
        for name, words in found.items():
            assert words, (f"no status word parsed out of {name}; this guard is "
                           f"reading the wrong file or the wrong shape")

    def test_no_emitted_status_word_carries_a_separator(self):
        offences = []
        for name in self.SOURCES:
            for line, word in self._emitted(BATTERY / name):
                if "_" in word or "-" in word:
                    offences.append(f"{name}:{line}: {word!r}")
        assert not offences, (
            "these are spellings no OPC UA server sends, written into the "
            "fixture the grader is judged against:\n  " + "\n  ".join(offences)
            + "\n`asyncua` reports GoodLocalOverride, not Good_LocalOverride.")

    def test_the_matcher_tells_the_two_spellings_apart(self):
        """The prohibition asserts an absence; show the pattern can find one."""
        assert self.STATUS.match("Good_LocalOverride")
        assert self.STATUS.match("GoodLocalOverride")
        assert not self.STATUS.match("ns=2;s=CNV01.Speed")
        assert not self.STATUS.match("q")


class TestTheLadderHasOneNumbering:
    """Sec. 4.1 of the 0.1.6 review: the live surface was rung 2 in its own
    files, rung 3 in the README, and `capture.py` said both -- rung 2 in its
    header and rung 3 in a refusal message twelve lines from the bottom.

    Held against the README's table, which is the published one. Not a pinned
    number: the rung is READ from the row whose description names the thing.
    """

    LIVE = "live-but-safe"
    MENTIONS = re.compile(r"[Rr]ung (\d)")

    def _readme_rung(self) -> str:
        page = (Path(ROOT) / "README.md").read_text(encoding="utf-8")
        rows = re.findall(r"^\|\s*(\d)\s*\|([^|]*)\|", page, re.MULTILINE)
        named = [n for n, what in rows if self.LIVE in what]
        assert len(named) == 1, (
            f"the README's ladder names {self.LIVE!r} in {named} rows; this "
            f"guard needs exactly one to hold the rest against")
        return named[0]

    def _files(self):
        return [BATTERY / "opcua_surface.py", BATTERY / "run_battery.py",
                PACKAGE / "capture.py"]

    def test_the_surface_and_the_leg_agree_with_the_page(self):
        """Every rung number in the files that ARE the live surface must be the
        README's number for it. `capture.py` mentions rung 1 nowhere, so any
        number it carries is about this one."""
        rung = self._readme_rung()
        wrong = []
        for path in self._files():
            for line in path.read_text(encoding="utf-8").splitlines():
                found = self.MENTIONS.search(line)
                if not found:
                    continue
                if found.group(1) not in (rung, "1", "2", "4"):
                    wrong.append(f"{path.name}: {line.strip()[:72]}")
                if found.group(1) in ("1", "2", "4") and "corpus" not in line \
                        and "mutated" not in line and "first contact" not in line.lower():
                    wrong.append(f"{path.name}: {line.strip()[:72]}")
        assert not wrong, ("these name a rung that is not the README's rung for "
                           f"the live surface ({rung}): {wrong}")

    def test_the_guard_reads_real_mentions(self):
        """Non-vacuity: if the pattern found nothing, the rule above is a rule
        about an empty set."""
        seen = sum(len(self.MENTIONS.findall(p.read_text(encoding="utf-8")))
                   for p in self._files())
        assert seen >= 5, f"only {seen} rung mentions found in {self._files()}"
