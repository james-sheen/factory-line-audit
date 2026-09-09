"""Which files this repository carries for a reader, and which it refuses to.

This is a decision written down where it is enforced, because the reasons are the
part that rots. A file added later by habit, or deleted later by tidying, should
have to argue with something.

**Carried.**

* `SECURITY.md` — this package authenticates to a controller, negotiates a
  channel, and writes a walk that describes a working production line. It also
  records *how* the walk was taken, and something downstream refuses on that
  record. There are real failure modes here where the report is itself the
  disclosure, so there has to be a private channel and a page saying so.
* `CONTRIBUTING.md` — it carries one fact a contributor cannot get anywhere else:
  the hooks are `core.hooksPath` and therefore **per-clone and off by default**,
  so a fresh clone has none. Everything else in it is a pointer.

**Refused, and this is the argument.**

* `CITATION.cff` — it would invite citation of a document whose own `FINDINGS.md`
  says it is a self-exam by the engine's author, not the independent adoption the
  method asks for. A citation file is a claim to standing this deliberately does
  not have. Revisit if somebody else adopts the method and reports back.
* `CODE_OF_CONDUCT.md` — it is a commitment to enforce a standard, made to a
  community. There is one maintainer and no issue traffic. Publishing an
  enforcement promise nobody is positioned to keep is worse than not making it.
  Revisit the day issues open to anyone.

Both refusals are cheap to reverse. Changing the decision means changing this
docstring and the test below, in that order.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import ROOT

CARRIED = ("SECURITY.md", "CONTRIBUTING.md")
REFUSED = ("CITATION.cff", "CODE_OF_CONDUCT.md")

#: Anything a reader could take for a released version.
VERSION_LITERAL = re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b")


class TestTheFilesThisRepositoryCarries:

    @pytest.mark.parametrize("name", CARRIED)
    def test_it_is_there_and_says_something(self, name):
        path = Path(ROOT) / name
        assert path.exists(), (
            f"{name} is missing. It is carried on purpose; the reason is in this "
            f"file's docstring, and removing it means changing that first")
        assert len(path.read_text(encoding="utf-8").split()) > 80, (
            f"{name} exists and is a stub, which is worse than absent: it "
            f"answers the question without telling anybody anything")

    @pytest.mark.parametrize("name", REFUSED)
    def test_it_is_absent_on_purpose(self, name):
        assert not (Path(ROOT) / name).exists(), (
            f"{name} was added. It is refused on purpose and the argument is in "
            f"this file's docstring -- if the argument is now wrong, change it "
            f"and this test, rather than deleting the test")


class TestTheSecurityPolicyCarriesNoVersion:
    """A number here is a number that goes stale, and this is the worst place in
    a repository for a sentence that has quietly stopped being true.

    Not hypothetical: a sibling project's security policy told reporters there was
    no released version to upgrade to. That was true the day it was written and
    false from its first release onwards -- and this package was itself
    unreleased in the morning and on an index by the afternoon. `SECURITY.md`
    says a test enforces this, so here it is; a page claiming a guard that does
    not exist is its own defect.
    """

    def _text(self) -> str:
        return (Path(ROOT) / "SECURITY.md").read_text(encoding="utf-8")

    def test_there_is_a_policy_to_read(self):
        assert self._text().strip(), "SECURITY.md is empty"

    def test_it_names_no_version(self):
        found = VERSION_LITERAL.findall(self._text())
        assert not found, (
            f"SECURITY.md names {found}. Say *the latest release* and let the "
            f"index be the record; a number here cannot be re-read by anything "
            f"when it stops being true")

    def test_the_matcher_would_find_one(self):
        """The claim above is an absence. Show the pattern can produce a yes."""
        assert VERSION_LITERAL.findall("supported: 0.1.3 and later")
        assert VERSION_LITERAL.findall("upgrade to v1.2")
        assert not VERSION_LITERAL.findall("the latest release on PyPI")

    def test_it_points_at_a_private_channel(self):
        """The one thing the page must actually do. A security policy that
        explains the failure modes and never says where to send them has
        published a map and no address."""
        text = self._text().lower()
        assert "private" in text and "report" in text, (
            "SECURITY.md does not tell a reporter where to send anything")
