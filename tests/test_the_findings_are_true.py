"""FINDINGS.md cites its own sections and reports measured numbers. Both resolve.

The README is already held to the package by `test_readme.py` -- the leg table,
the kinds, the verbs, the status counts. FINDINGS.md had nothing, and at seven
hundred lines it is the longer claim: twenty findings, a disposition table keyed
by finding, counts taken off real runs, and repository paths its own intro says
are held by a test.

That intro sentence is why this file exists. It says *every repository path
either of them names is now held by a test* -- written about README.md and
BRIDGES.md, and not true of FINDINGS.md itself until now. A document asserting
that its paths are checked, while nothing checks its own paths, is exactly the
failure this class is about.

**On the `C` labels.** `C1`..`C8` are BRIDGES capabilities, and `C1`/`C2` are
also the two withdrawn findings in section C. One letter, two namespaces, in one
document. Nothing here resolves a bare `C` label, because a check that cannot
tell which namespace it is in would be guessing. Recorded rather than papered
over.
"""

from __future__ import annotations

import os
import re

from conftest import ROOT

FINDINGS = open(os.path.join(ROOT, "FINDINGS.md"), encoding="utf-8").read()

#: `### A7.` opens a finding; `A7` anywhere else cites one. The `C` namespace is
#: deliberately excluded -- see the module docstring.
DEFINED = re.compile(r"^### ([AB]\d+)\.", re.MULTILINE)
CITED = re.compile(r"\b([AB]\d+)\b")


def _defined() -> list[str]:
    return DEFINED.findall(FINDINGS)


# --- the document resolves against itself ----------------------------------

def test_there_are_enough_findings_for_these_checks_to_mean_something() -> None:
    """NON-VACUITY. Every loop below passes over an empty set, and a FINDINGS.md
    that stopped matching the heading shape would take all of them green."""
    assert len(_defined()) >= 15, (
        f"only {len(_defined())} findings parsed; the heading shape probably moved")


def test_every_finding_label_the_prose_cites_is_one_the_document_defines() -> None:
    """A citation resolving nowhere is a renumbering that half landed. This document
    has renumbered once already -- A9 was appended out of order and the note above
    A10 says the labels stay put precisely because other documents cite them."""
    defined, cited = set(_defined()), set(CITED.findall(FINDINGS))
    missing = sorted(cited - defined)
    assert not missing, f"the prose cites {missing}, which it never defines"


def test_finding_labels_are_unique_and_contiguous_within_each_letter() -> None:
    """A repeat reads as one finding and a gap reads as a withdrawal. Order is NOT
    asserted: the document states plainly that A10 and A11 were appended after
    section B, and keeping the labels was the deliberate choice over sorting."""
    for letter in ("A", "B"):
        numbers = sorted(int(tag[1:]) for tag in _defined() if tag.startswith(letter))
        assert numbers, f"no {letter} findings parsed"
        assert len(numbers) == len(set(numbers)), f"a {letter} label is defined twice"
        assert numbers == list(range(1, len(numbers) + 1)), (
            f"{letter} numbering has a gap: {numbers}")


# --- the disposition table, and the four findings it does not reach --------

#: Defined findings that section E never names. This is a REAL GAP in the
#: document, pinned here so it cannot grow quietly, and NOT endorsed:
#:
#:   B7  -- dispositioned in its own body (shipped in 0.1.11, 2026-09-04) and
#:          never carried up into the table.
#:   A10 -- covered by a table row whose Finding column is `--`, naming the topic
#:          `allow_reset` instead of the label, while E's own preamble says the
#:          table is KEYED BY FINDING.
#:   B1  -- no disposition anywhere in the document.
#:   A11 -- no disposition anywhere in the document.
UNDISPOSITIONED = {"B1", "B7", "A10", "A11"}


def test_the_disposition_table_accounts_for_every_finding_but_the_known_four() -> None:
    """Section E is the document's own accounting, and it is short by four.

    The rule this asserts is the one E states about itself: a finding is a row.
    The exception set is named above with a reason for each, so adding a finding
    without a disposition fails here, and closing one of the four fails here too
    -- which is the point. A pinned gap that cannot be closed without the test
    noticing is a ratchet; a pinned gap nobody has to look at is a lie.
    """
    disposition = FINDINGS.split("## E. Disposition", 1)
    assert len(disposition) == 2, "section E is gone, and it is the accounting"
    # BOUND the section at the next `## ` heading. E is last today, so an
    # unbounded split ran to end-of-file and read anything APPENDED AFTER E as
    # having been dispositioned BY E -- a new undispositioned finding tacked on
    # the end made this test greener, not redder.
    body = re.split(r"\n## ", disposition[1], 1)[0]
    named = set(CITED.findall(body))
    unaccounted = set(_defined()) - named
    assert unaccounted == UNDISPOSITIONED, (
        f"section E accounts for a different set than recorded: "
        f"now unaccounted {sorted(unaccounted)}, recorded {sorted(UNDISPOSITIONED)}")


# --- the document resolves against the package -----------------------------

def test_the_leg_count_the_prose_states_is_the_battery_that_runs() -> None:
    """*green on all nineteen legs* is a number about the runner, not about prose.
    `test_readme.py` learned this the hard way on the README's own table: the total
    was right while the enumeration under it was two short."""
    words = {"sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
             "twenty": 20, "twenty-one": 21}
    claimed = re.search(r"green on all ([a-z-]+) legs", FINDINGS)
    assert claimed, "the prose no longer states a leg count"
    stated = words.get(claimed.group(1))
    assert stated is not None, f"leg count {claimed.group(1)!r} is not a word this test reads"

    runner = open(os.path.join(ROOT, "battery", "run_battery.py"), encoding="utf-8").read()
    found = re.search(r"SELECTABLE\s*=\s*\((.*?)\)", runner, re.S)
    assert found, "no SELECTABLE tuple in the battery runner"
    legs = re.findall(r'"([^"]+)"', found.group(1))
    assert stated == len(legs), f"the prose says {stated} legs, the runner selects {len(legs)}"


def test_every_repository_path_the_prose_names_exists() -> None:
    """The intro's own promise, applied to the intro. It moved `engine_floors.json`
    into the package in 0.1.7 and both documents went on naming the old path, which
    is the sentence this check makes true of FINDINGS.md as well."""
    paths = sorted(set(re.findall(
        r"`((?:src|battery|tests|tools|examples|docs)/[A-Za-z0-9_./-]+)`", FINDINGS)))
    assert len(paths) >= 4, f"only {len(paths)} paths found; the check is near vacuous"
    for path in paths:
        assert os.path.exists(os.path.join(ROOT, path)), (
            f"the prose names {path}, which is not in the repository")


def test_the_engine_the_exam_measured_is_still_the_declared_floor() -> None:
    """The document says the exam measured 0.1.10 and that this *is still this
    package's range floor* -- a claim about `pyproject.toml`, which moves
    independently of prose. If the floor is raised, this file is about an engine
    the package no longer accepts, and it should say so rather than be read as
    current."""
    measured = re.search(r"The exam measured `arbiter-engine ([0-9.]+)`", FINDINGS)
    assert measured, "the prose no longer names the engine version it measured"
    pyproject = open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read()
    floor = re.search(r'arbiter-engine>=([0-9.]+)', pyproject)
    assert floor, "no arbiter-engine floor in pyproject.toml"
    assert measured.group(1) == floor.group(1), (
        f"the exam measured {measured.group(1)} and the floor is now "
        f"{floor.group(1)}; the prose calls them the same")
