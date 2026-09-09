"""A workflow must not EXECUTE a version range this package already declares.

`checks.yml` ran `pip install 'arbiter-engine>=0.1.10,<0.2'` to prove that its
bare-install check could see a dependency arrive. The range was correct, and
that is the whole problem: it agreed with `pyproject.toml` on the day it was
written, so nothing could notice the two parting. Move the `detect` floor and
that line goes on installing the old range, reporting green about a version this
package no longer claims to support.

**Borrowed from `cert-generator`, which has this guard because the defect cost
it something.** The identical line lived in two of its workflows, was fixed in
one, and ran every morning in the other -- downgrading the referee below the
package's own floor and going red at a combination it had assembled itself. The
one instrument watching a seam it did not control had spent its whole signal on
its own pin.

**What is a breach and what is not.** An EXECUTED constraint is the breach. A
comment quoting one while explaining what went wrong is not, and must keep
working: a rule that forces prose about a removal to be deleted buys a clean
grep at the price of the history that explains it. So comment lines are dropped
before the scan, and there is a test below asserting they are.

Parametrised per file rather than over a concatenation, for the reason
`cert-generator` gives: a per-file failure names the file, and a new workflow is
picked up without anybody remembering to add it here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import ROOT

WORKFLOWS = Path(ROOT) / ".github" / "workflows"
PYPROJECT = Path(ROOT) / "pyproject.toml"


def _declared() -> set[str]:
    """Distribution names this package declares a range for.

    Read out of `pyproject.toml` rather than out of installed metadata: the
    text is present in a bare checkout, and this guard should work in one.
    """
    body = PYPROJECT.read_text(encoding="utf-8")
    names = set()
    for header in ("[project.optional-dependencies]", "[project]"):
        if header not in body:
            continue
        section = body.split(header, 1)[1]
        section = re.split(r"^\[", section, maxsplit=1, flags=re.MULTILINE)[0]
        names |= set(re.findall(r'"([A-Za-z0-9][A-Za-z0-9._-]*)\s*[<>=!~]',
                                section))
    return names


def _executed(path: Path):
    """Lines a shell would run: everything that is not a comment.

    A `#` first on a line is a comment in YAML and in the shell inside a `run:`
    block, so one rule covers both. A trailing comment after code stays in, and
    that is the safe direction to err.
    """
    return [(n, line) for n, line in
            enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
            if not line.lstrip().startswith("#")]


def _matcher(names):
    #: `name[extra]>=1.2` and `name>=1.2`, quoted or not.
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(names))
                      + r")\s*(?:\[[A-Za-z0-9,_-]+\])?\s*[<>=!~]=")


def _breaches(path: Path, names):
    matcher = _matcher(names)
    return [f"{path.name}:{n}: {line.strip()[:88]}"
            for n, line in _executed(path) if matcher.search(line)]


WORKFLOW_FILES = sorted(WORKFLOWS.glob("*.yml"))


class TestNoWorkflowExecutesARangeThisPackageDeclares:

    def test_there_are_workflows_to_scan(self):
        """Non-vacuity. Every claim below is over this glob, and an empty glob
        satisfies all of them."""
        assert len(WORKFLOW_FILES) >= 2, (
            f"only {len(WORKFLOW_FILES)} workflow(s) found in {WORKFLOWS}; the "
            f"scan is looking in the wrong place")

    def test_the_package_declares_something_to_look_for(self):
        """The other half. An empty name set builds a matcher that matches
        nothing, and every file below would pass for that reason."""
        found = _declared()
        assert len(found) >= 3, (
            f"only {sorted(found)} parsed out of pyproject.toml; this package "
            f"declares three ranges, so the parse is wrong and the scan below "
            f"would be a claim about nothing")

    @pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda p: p.name)
    def test_it_executes_no_declared_range(self, path):
        breaches = _breaches(path, _declared())
        assert not breaches, (
            "these EXECUTE a range `pyproject.toml` already declares, so the "
            "two can part without anything noticing:\n  "
            + "\n  ".join(breaches)
            + "\nRead it out of the installed metadata instead.")

    def test_the_matcher_finds_an_executed_constraint(self, tmp_path):
        """Before believing the absence above, show this can say yes -- in the
        exact shape the real defect took."""
        sample = tmp_path / "w.yml"
        sample.write_text("        run: |\n"
                          "          pip install 'arbiter-engine>=0.1.10,<0.2'\n",
                          encoding="utf-8")
        assert _breaches(sample, _declared()), "the real shape went unseen"

    def test_a_comment_quoting_a_range_is_not_a_breach(self, tmp_path):
        """The rule this guard is allowed to be wrong about in only one
        direction. `checks.yml` and this file both explain the defect by
        quoting it, and must go on being able to."""
        sample = tmp_path / "w.yml"
        sample.write_text("# this line used to read arbiter-engine>=0.1.10,<0.2\n"
                          "          # pip install 'presence-audit>=0.1.6,<0.2'\n"
                          "        run: echo fine\n", encoding="utf-8")
        assert not _breaches(sample, _declared()), (
            "a comment explaining the defect was reported as the defect")
