"""The README is the one surface that can promise what no index can deliver.

**Ported from `cert-generator`, and deliberately not verbatim.** That file opens
by explaining that its own ancestor in `bmc-sensor-audit` anchored this check on
a version sentinel, `__version__ == "0.0.0"`, and that the sentinel did not
transplant: a package declaring a real version while sitting on no index reads
*released* to it, the check passes, and the README goes on sending readers to a
name PyPI answers 404 for.

That is this package, one level out. It declares `0.1.0`, it is on no index, and
it has no tags -- so porting the sentinel would reproduce the exact defect the
source file was written to describe. Copying the mechanism without its premise is
how a check comes to run correctly and ask the wrong question.

**So the anchor is different here, and the difference is the point.** The version
literal carries no information about release state: `0.1.0` is a real number that
says nothing about whether anything was published. Two records do carry it:

* the README's own marker, which is the DECLARATION, and
* the repository's TAGS, which are the independent record able to contradict it.

A declaration guarded only by itself is a declaration with nothing behind it, so
the marker is checked against the tags wherever git can answer -- and where git
cannot, this says so rather than converting *cannot tell* into *no tags*.

What the README is held to is agreeing with itself and with the tree: a page that
says this is unreleased must not also hand a reader an install command or a tag
that only work once it is not.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

#: The distribution name an index would be asked for. Here it is also the console
#: script's name, so `cert-generator`'s second guard -- the one separating the
#: two -- has no premise in this repository and was not ported.
DIST = "factory-line-audit"

# One vocabulary for one fact across this family: both spellings are reused
# verbatim from `cert-generator`, which took them from `bmc-sensor-audit`. A
# release here needs no new wording invented for it.
UNRELEASED = "Not yet released"
RELEASED = re.compile(r"\*\*Released[^*]*?(\d+\.\d+\.\d+)\*\*")

#: `pip install factory-line-audit`, quoted or not, with or without an extra --
#: the form that only works once an index carries the name. The lookahead keeps
#: it usable while unreleased: `pip install "factory-line-audit @ git+https://..."`
#: is a direct reference rather than an index lookup and must not trip this.
#: Spelled strictly on purpose -- a guard with false positives is a guard the next
#: person loosens, and a loosened guard stops catching the real thing.
INDEX_INSTALL = re.compile(
    r"pip install\s+(?:-[^\s]+\s+)*['\"]?"
    + re.escape(DIST)
    + r"(?:\[[A-Za-z0-9,_\-]+\])?['\"]?(?!\s*@)")

#: The tag the README names, so the two can be compared without asking git.
TAGGED = re.compile(r"tagged `([^`]+)`")

#: The tag namespace this project would release in: `v` and a dotted version.
_TOOL_TAG = re.compile(r"^v(\d+(?:\.\d+)*)$")


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _version() -> str:
    from factory_line_audit import __version__
    return __version__


def _named_tag():
    """The tag string the README names, or None."""
    found = TAGGED.search(_readme())
    return found.group(1) if found else None


def _tags():
    """Repository tags, or None when git cannot answer -- caveat carried over
    from `cert-generator` intact. A checkout with no `.git` exits non-zero and an
    image with no git binary raises; answering `[]` for either would turn *cannot
    tell* into *there are no tags*. A shallow clone fetched without tags answers
    successfully and is still not an answer.
    """
    try:
        listed = subprocess.run(["git", "tag"], cwd=str(ROOT),
                                capture_output=True, text=True)
    except OSError:
        return None
    if listed.returncode != 0:
        return None
    return [line for line in listed.stdout.split() if line]


def _released_versions(tags):
    """Every tag naming a version of this package, as comparable tuples."""
    return [tuple(int(part) for part in match.group(1).split("."))
            for match in (_TOOL_TAG.match(tag) for tag in tags) if match]


class TestTheReadmeStatesWhereItStands:

    def test_the_readme_states_a_release_state_at_all(self):
        """Non-vacuity, and the reason this file is not a single test.

        Every rule below is conditional on one of the two markers being present.
        Without this, DELETING the marker is a way to pass: each prohibition
        would find nothing and report success, which is the failure shape this
        suite refuses everywhere else. It is also the state this README was
        actually in -- it said neither -- so this test is the one that would
        have been red before the sentence it guards existed.
        """
        readme = _readme()
        unreleased = UNRELEASED in readme
        released = RELEASED.search(readme)
        assert unreleased or released, (
            f"the README states neither that this is unreleased nor which "
            f"version was released; one of `{UNRELEASED}` or "
            f"`**Released -- X.Y.Z**` has to be there for the rest of this file "
            f"to mean anything")
        assert not (unreleased and released), (
            "the README says both that this is unreleased and that a version "
            "was released; that is two answers to one question")

    def test_an_index_install_is_not_offered_while_unreleased(self):
        readme = _readme()
        if UNRELEASED not in readme:
            return
        found = INDEX_INSTALL.search(readme)
        assert not found, (
            f"the README says {UNRELEASED.lower()} and still tells a reader "
            f"{found.group(0)!r}; that command resolves against an index which "
            f"does not carry this name. Offer a checkout or a direct reference, "
            f"or release it")

    def test_no_tag_is_offered_while_unreleased(self):
        """The same rule as the install line, for the other thing a reader can
        be sent to fetch. A tag named in prose is a tag somebody will try to
        check out."""
        if UNRELEASED not in _readme():
            return
        named = _named_tag()
        assert named is None, (
            f"the README says {UNRELEASED.lower()} and names the tag {named!r}; "
            f"an unreleased tree must not hand a reader a tag to check out")


class TestAReleasedReadmeAgreesWithThePackage:
    """The other branch, so this file keeps working after publication rather
    than becoming a check that only ever meant something once."""

    def test_it_names_the_version_the_package_reports(self):
        released = RELEASED.search(_readme())
        if not released:
            return
        version = _version()
        assert released.group(1) == version, (
            f"the README announces {released.group(1)} and the package reports "
            f"{version}; both are published records of one fact")

    def test_it_names_the_tag_that_version_carries(self):
        """The version literal is the anchor: it is what the package reports
        about itself, what `pyproject.toml` reads for packaging, and the only
        record that answers in an sdist and in a shallow checkout with no tags.
        The tag string is compared against it, never against another derivation
        of it -- a `v0.2.0` left behind by a bump to 0.2.1 sends a reader to a
        tag describing different code, and both strings look right alone.
        """
        if not RELEASED.search(_readme()):
            return
        version = _version()
        named = _named_tag()
        assert named, (
            f"the README announces a release and names no tag. The line should "
            f"read: tagged `v{version}`")
        assert named == f"v{version}", (
            f"the README names the tag {named!r} and the package reports "
            f"{version}; it must be `v{version}`. A leading v dropped from one, "
            f"or a tag string left behind by a bump, is how these part company")

    def test_a_release_claim_and_the_tree_do_not_disagree(self):
        """The independent record. Everything above compares the README with
        itself or with a literal in the same tree, all of which one edit can
        satisfy at once. A tag is the part of the claim the working tree cannot
        write about itself.

        **The window is carved to the rule rather than widened.** Only the
        announced version may be untagged, and only while no LATER version is
        tagged: a release in flight is always the newest one. A reverted bump
        that left its tag behind, or a tag made from the wrong commit, both
        leave a later tag and still fail here.

        Whether a tag was ever PUSHED is a fact about the remote, and no
        assertion from a working tree can reach it. Saying so is the honest
        version; asserting it would be a check that is right by luck.
        """
        released = RELEASED.search(_readme())
        if not released:
            return
        tags = _tags()
        if not tags:
            # *Cannot tell* is not *no tags*: a checkout without `.git`, an image
            # with no git binary, and a shallow clone fetched without tags all
            # land here, and none of them is evidence about the remote.
            #
            # `cert-generator` says this with `pytest.skip`. That spelling cannot
            # be used here: the `checks` job fails the build on ANY skip, so the
            # honest report would turn the release commit's own CI run red in
            # exactly the window where it is least welcome. It runs for real in
            # that job regardless -- `checks` checks out with `fetch-depth: 0`,
            # so tags are visible there and the assertions below do fire.
            return
        announced = tuple(int(part) for part in released.group(1).split("."))
        if announced in _released_versions(tags):
            return
        ahead = sorted(t for t in _released_versions(tags) if t > announced)
        assert not ahead, (
            f"the README announces {released.group(1)}, no tag names it, and "
            f"{['v' + '.'.join(map(str, t)) for t in ahead]} name later "
            f"versions. A release in flight is the only reason the announced "
            f"version should be untagged, and a release in flight is always the "
            f"newest one")
        # The one legitimate window: the tag is made OF the commit that sets the
        # version literal, so between that commit and `git tag` there is no tag
        # to find, and CI runs in that gap on every release. The wrong shapes
        # were all rejected above, so this is a pass rather than a skip -- the
        # `checks` job fails the build on any skip, which would turn every
        # release commit red at the moment somebody reaches for `--no-verify`.
        return


class TestTheMatchersCanProduceAPositive:
    """Both prohibitions above assert an ABSENCE. An absence found by a pattern
    that matches nothing is not a measurement, so each pattern is shown here
    catching the thing it exists to catch and letting past the things it must."""

    def test_the_install_matcher_separates_the_two_forms(self):
        assert INDEX_INSTALL.search(f"pip install {DIST}")
        assert INDEX_INSTALL.search(f"pip install '{DIST}[detect]'")
        assert INDEX_INSTALL.search(f"pip install --quiet {DIST}")
        assert not INDEX_INSTALL.search(
            f'pip install "{DIST} @ git+https://example.invalid/x@master"')
        assert not INDEX_INSTALL.search("pip install -r requirements.txt")
        assert not INDEX_INSTALL.search("pip install -e '.[detect,live]'")

    def test_the_tag_matcher_reads_a_tag_string(self):
        assert TAGGED.search("tagged `v0.2.0`, Apache-2.0").group(1) == "v0.2.0"
        assert TAGGED.search("**Released -- 0.2.0**, tagged `v0.2.0`")
        assert TAGGED.search("nothing tagged here") is None

    def test_the_release_matcher_reads_a_version(self):
        assert RELEASED.search("**Released -- 0.2.0**, tagged").group(1) == "0.2.0"
        assert RELEASED.search("**Released 1.10.3**").group(1) == "1.10.3"
        assert RELEASED.search(f"**{UNRELEASED}**") is None


class TestTheStatusParagraphCountsWhatExists:
    """A count written into prose has no red.

    The Status paragraph claimed *thirteen battery legs* while sixteen existed,
    and *`arbiter-engine 0.1.10`* while the range this package declares resolves
    to something later. Neither was wrong when written. Both expired when the
    next leg and the next engine release landed, and prose is where that happens
    silently -- there is no assertion to fail, so the sentence just quietly stops
    being true.

    So the numbers that stay in that paragraph are held against the tracked files
    that define them. `battery_result.json` would be the natural subject for a
    claim about a RUN, and it is gitignored, so it cannot be one: a guard reading
    it would find nothing in CI and pass. These read the battery's own leg tuple
    and the package's own dependency range instead, both of which are always
    present.
    """

    RUNNER = ROOT / "battery" / "run_battery.py"
    PYPROJECT = ROOT / "pyproject.toml"

    NUMBER = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
              "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
              "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
              "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
              "twenty": 20}

    FINDINGS = ROOT / "FINDINGS.md"

    #: The three shapes a TOTAL claim takes in these documents. Deliberately not
    #: a general `<number> legs`: *three legs also run a second time* is a true
    #: sentence about a SUBSET, and a guard that forbade it would be one the next
    #: person deletes. Written narrow, and held to that by the non-vacuity test
    #: below -- the risk of a narrow pattern is that it silently matches nothing,
    #: which is how the first version of this guard missed `Sixteen legs:` in the
    #: same file it was checking.
    TOTALS = (re.compile(r"\ball\s+([A-Za-z]+|\d+)\s+legs\b", re.IGNORECASE),
              re.compile(r"\b([A-Za-z]+|\d+)\s+battery legs\b", re.IGNORECASE),
              re.compile(r"\b([A-Za-z]+|\d+)\s+legs:", re.IGNORECASE))

    def _selectable(self) -> int:
        """The battery's own leg names, read rather than imported -- importing a
        script for a constant runs whatever else it does at module level."""
        found = re.search(r"SELECTABLE\s*=\s*\((.*?)\)",
                          self.RUNNER.read_text(encoding="utf-8"), re.S)
        assert found, "no SELECTABLE tuple in the battery runner"
        return len(re.findall(r'"[^"]+"', found.group(1)))

    def _claims(self, text: str):
        """Every total-shaped leg count in one document, as integers."""
        out = []
        for pattern in self.TOTALS:
            for word in pattern.findall(text):
                word = word.lower()
                value = self.NUMBER.get(word,
                                        int(word) if word.isdigit() else None)
                if value is not None:
                    out.append(value)
        return out

    def _documents(self):
        return {"README.md": _readme(),
                "FINDINGS.md": self.FINDINGS.read_text(encoding="utf-8")}

    def test_the_battery_has_legs_to_count(self):
        """Non-vacuity: an empty tuple would satisfy any comparison below."""
        assert self._selectable() >= 10, (
            f"only {self._selectable()} leg(s) parsed from the runner; the "
            f"pattern is not finding the tuple, so the check below proves "
            f"nothing")

    def test_every_document_states_a_total_this_guard_can_read(self):
        """Non-vacuity, and it is the failure this guard has already had.

        The first version matched only `N battery legs`. `README.md` also says
        `Sixteen legs:` and `FINDINGS.md` says `green on all thirteen legs`, and
        both went unchecked in the same change that was written to check them --
        the pattern was narrower than the claim. So each document must yield at
        least one reading, or this says so rather than passing.
        """
        for name, text in self._documents().items():
            assert self._claims(text), (
                f"{name} states no leg total this guard can read. Either the "
                f"sentence was reworded out of the three shapes in TOTALS, or "
                f"it was removed; both leave the count unheld")

    def test_every_stated_leg_total_is_the_number_that_exists(self):
        exists = self._selectable()
        wrong = {name: [c for c in self._claims(text) if c != exists]
                 for name, text in self._documents().items()}
        wrong = {k: v for k, v in wrong.items() if v}
        assert not wrong, (
            f"these state a leg total the battery does not have ({exists}): "
            f"{wrong}. This is the shape that expired twice already -- the "
            f"number was right when written, and nothing could notice the next "
            f"leg landing")

    #: Names whose version is a fact about somebody else's software, and
    #: therefore expires. `engine` is in here as a bare word on purpose: the
    #: sentence that went stale said *the engine measured is `0.1.10`* and never
    #: wrote the distribution's name at all.
    UPSTREAM = ("arbiter-engine", "presence-audit", "asyncua", "engine")

    ANY_VERSION = re.compile(r"\b\d+\.\d+(?:\.\d+)?(?:\.dev\d+)?\b")

    def test_the_readme_names_no_resolved_upstream_version(self):
        """A resolved version is a fact about one run and expires at the next
        release of someone else's package. The declared RANGE is a fact about
        this package; `engine_floors.json` and `pin_evidence.json` are where
        versions actually exercised are recorded, by probes that re-run.

        **This guard was twice as narrow as its own claim when written.** It read
        only the header, and it required the literal `arbiter-engine` beside the
        number. The stale sentence was in the last section and said *the engine*
        — so it sat outside both halves of the predicate while this test passed.
        Now: the whole page, and the bare word too.
        """
        offences = []
        for number, line in enumerate(_readme().splitlines(), start=1):
            if not any(name in line.lower() for name in self.UPSTREAM):
                continue
            if self.ANY_VERSION.search(line):
                offences.append(f"line {number}: {line.strip()[:88]}")
        assert not offences, (
            "these name a resolved upstream version, which is a fact about one "
            "run:\n  " + "\n  ".join(offences)
            + "\nName the declared range, or point at the evidence file.")

    def test_that_guard_would_catch_the_sentence_that_went_stale(self):
        """The exact shape, so a narrowed pattern cannot pass quietly again."""
        line = "- The engine measured is `0.1.10` from PyPI, and `0.1.11.dev0`"
        assert any(n in line.lower() for n in self.UPSTREAM)
        assert self.ANY_VERSION.search(line)
        assert not self.ANY_VERSION.search("the range this package declares")


class TestTheLegTableListsEveryLeg:
    """The table of legs, held to the legs that exist.

    It listed sixteen while the battery ran eighteen: `engine` and
    `orchestrator` were both added without a row, and the paragraph above the
    table already named `orchestrator` as an addition. **The count guard could
    not see this** -- the total said eighteen and was right; it was the
    enumeration underneath that was short. A number and a list are two claims,
    and checking the number does not check the list.
    """

    RUNNER = ROOT / "battery" / "run_battery.py"

    def _legs(self) -> set[str]:
        found = re.search(r"SELECTABLE\s*=\s*\((.*?)\)",
                          self.RUNNER.read_text(encoding="utf-8"), re.S)
        assert found, "no SELECTABLE tuple in the battery runner"
        return set(re.findall(r'"([^"]+)"', found.group(1)))

    def _tabled(self) -> set[str]:
        """Leg names in the README's own table, read out of the first column."""
        return set(re.findall(r"^\|\s*`([a-z-]+)`", _readme(), re.MULTILINE))

    def test_there_is_a_table_to_read(self):
        assert len(self._tabled()) >= 10, (
            f"only {sorted(self._tabled())} parsed out of the README's table; "
            f"the pattern is not finding it, so the rules below hold nothing")

    def test_every_leg_has_a_row(self):
        missing = sorted(self._legs() - self._tabled())
        assert not missing, (
            f"these legs run and the README's table does not list them: "
            f"{missing}. A reader counting the table gets a different number "
            f"from the one the paragraph above it states")

    def test_no_row_names_a_leg_that_does_not_run(self):
        """The other direction, and the cheaper mistake: a row for a leg that
        was renamed or removed reads as coverage that is not there."""
        extra = sorted(self._tabled() - self._legs())
        assert not extra, f"the table lists legs the battery does not run: {extra}"


class TestTheKindsParagraphNamesEveryKind:
    """The declaration kinds, held to the module that defines them.

    Found while adding an eleventh: the page listed nine of ten. `bad_state`
    landed as a kind, the sentence was not touched, and nothing could go red --
    the same shape as the leg table above, in prose instead of a table. A
    reader counting the kinds got one answer and `gate` another.
    """

    def _named(self) -> set[str]:
        """Kinds named in the README, in backticks, inside the kinds sentence.

        Scoped to that paragraph: `rate` and `exclusion` are ordinary words
        elsewhere on the page, and a document-wide grep would call the list
        complete on the strength of prose that is not the list.
        """
        page = _readme()
        start = page.index("Kinds: `")
        return set(re.findall(r"`([a-z_]+)`", page[start:page.index("\n\n", start)]))

    def test_there_is_a_sentence_to_read(self):
        assert len(self._named()) >= 5, (
            f"only {sorted(self._named())} parsed; the rules below hold nothing")

    def test_every_kind_is_named(self):
        from factory_line_audit.declarations import KINDS
        missing = sorted(set(KINDS) - self._named())
        assert not missing, (f"`gate` accepts these kinds and the README does "
                             f"not name them: {missing}")

    def test_no_kind_is_named_that_the_gate_would_refuse(self):
        from factory_line_audit.declarations import KINDS
        extra = sorted(self._named() - set(KINDS))
        assert not extra, (f"the README names these kinds and `gate` refuses "
                           f"them: {extra}")
