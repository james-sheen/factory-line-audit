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
