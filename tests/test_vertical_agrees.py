"""The port's whole justification: the two paths must agree.

`presence.classify()` is this package's own code and has no dependencies.
`vertical` adapts the same register and the same walk onto
`presence-audit`'s neutral core and lets `diff.compare()` do the pairing.

If those two disagree about which tags are reading, the port changed a verdict,
and a changed verdict is a worse outcome than no port at all. So the assertion
is agreement on the SAME corpus, tag by tag -- not merely that both produce a
number.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pa = pytest.importorskip("presence_audit",
                         reason="the vertical needs the [vertical] extra")

from presence_audit import vocabulary as V
from presence_audit.diff import compare

from factory_line_audit import presence, vertical


def _core_reads_points() -> bool:
    """Does the installed core read `.points`, or iterate the object?

    Probed by BEHAVIOUR, not by a version string. The requirement is that the
    core touches only what `presence_audit.protocols` declares; a version number is a
    proxy for that and goes stale the moment a backport or a local checkout is
    in play. This asks the actual question by handing `compare()` a declaration
    that has `points` and refuses everything else.

    Published `bmc-sensor-audit` 0.2.5 fails this: `diff.compare` does
    `list(declaration)`, so an adapter written to the published protocol raises
    `TypeError` before any comparison runs. MEASURED, not assumed -- the whole
    suite below was run against the 0.2.5 wheel and three tests failed there.
    """
    class _OnlyPoints:
        points = ()
        sources = ()
        anomalies = ()
        unreadable = ()

    class _EmptyWalk(_OnlyPoints):
        captured_at = None
        complete = True
        errors = ()

    previous = V._REGISTERED
    V.reset()
    V.register(vertical.FactoryLineVocabulary())
    try:
        compare(_OnlyPoints(), _EmptyWalk())
        return True
    except TypeError:
        return False
    finally:
        V._REGISTERED = previous


NEEDS_POINTS = pytest.mark.skipif(
    not _core_reads_points(),
    reason="the installed presence-audit iterates the capture and the "
           "declaration instead of reading `.points`, so an adapter written to "
           "its own published protocol cannot run. Fixed after 0.2.5; this is a "
           "floor that is not met, not a defect in this package")

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "examples" / "asset_register.json"


@pytest.fixture
def registered():
    previous = V._REGISTERED
    V.reset()
    V.register(vertical.FactoryLineVocabulary())
    try:
        yield
    finally:
        V._REGISTERED = previous


@pytest.fixture(scope="module")
def corpus():
    register = presence.load_register(str(REGISTER))
    walk = _a_walk(register)
    return register, walk


def _a_walk(register):
    """A walk over the register, with one node absent and one substituted.

    Built here rather than loaded so the three states are all present by
    construction -- a corpus in which nothing is absent cannot tell an agreeing
    pair of implementations from two that both say everything is fine.
    """
    nodes = [spec["node"] for a in register["assets"]
             for spec in (a.get("tags") or {}).values()]
    assert len(nodes) >= 3, "the register is too small to exercise three states"
    absent, substituted = nodes[0], nodes[1]
    sample = {}
    for node in nodes:
        if node == absent:
            continue
        q = "GoodLocalOverride" if node == substituted else "Good"
        sample[node] = {"v": 1.0, "q": q}
    bad = nodes[2]
    sample[bad] = {"v": None, "q": "Bad"}
    return {"source": {"endpoint": "opc.tcp://test"},
            "samples": [{"t": "2026-09-08T00:00:00Z", "nodes": sample}]}


def _stage1_states(register, walk):
    out = {}
    for row in presence.classify(register, walk)["tags"]:
        out[row["node"]] = row["state"]
    return out


def _core_states(register, walk):
    report = compare(vertical.Register(register), vertical.Walk(walk))
    out = {}
    for match in report.matches:
        out[match.declared.name] = (presence.READING if match.live.is_reading
                                    else presence.NOT_READING)
    for declared in report.unmatched_declared:
        out[declared.name] = presence.ABSENT
    return out


@NEEDS_POINTS
class TestTheTwoPathsAgree:
    def test_the_corpus_exercises_all_three_states(self, corpus):
        """Before comparing two answers, check the question is a real one."""
        states = set(_stage1_states(*corpus).values())
        assert states == {presence.READING, presence.NOT_READING, presence.ABSENT}, (
            f"the corpus produced only {sorted(states)}; two implementations "
            f"agreeing on a single state is not evidence of anything")

    def test_every_tag_lands_in_the_same_state(self, corpus, registered):
        register, walk = corpus
        stage1, core = _stage1_states(register, walk), _core_states(register, walk)
        assert core == stage1, (
            "the port changed a verdict:\n"
            + "\n".join(f"  {n}: stage1={stage1.get(n)} core={core.get(n)}"
                        for n in sorted(set(stage1) | set(core))
                        if stage1.get(n) != core.get(n)))

    def test_the_counts_agree_too(self, corpus, registered):
        register, walk = corpus
        s1 = presence.classify(register, walk)["counts"]
        report = compare(vertical.Register(register), vertical.Walk(walk))
        counts = report.counts()
        assert counts["reading"] == s1[presence.READING]
        assert counts["present_not_reading"] == s1[presence.NOT_READING]
        assert counts["declared_absent"] == s1[presence.ABSENT]


@NEEDS_POINTS
class TestWhatOnlyTheDomainKnows:
    def test_a_substituted_value_becomes_a_finding(self, corpus, registered):
        """The core pairs and counts; it cannot know an HMI override is one.

        Stage 1 reports this as a `substituted` count. Through the core it
        arrives as a finding from `capture_findings`, which is the vocabulary
        member that exists for exactly this.
        """
        register, walk = corpus
        report = compare(vertical.Register(register), vertical.Walk(walk))
        subs = [f for f in report.findings if f.kind == "substituted_value"]
        assert len(subs) == presence.classify(register, walk)["counts"]["substituted"]
        assert subs, "the fixture built no substituted reading, so this proves nothing"

    def test_the_quality_section_is_this_domains_own_report_key(self, corpus, registered):
        register, walk = corpus
        sections = V.current().report_sections()
        assert "opcua_quality" in sections
        payload = sections["opcua_quality"](vertical.Walk(walk))
        assert payload["grades"], "no quality words were counted"
        assert payload["substituted_nodes"] >= 1


class TestTheAdaptersAreOnlyTheProtocol:
    """The lesson from the core's own foreign-domain suite, applied here.

    These classes must not carry a member the protocol does not declare. If they
    do, this package stops being evidence that a vertical can be written from
    the published document.
    """

    @pytest.mark.parametrize("cls", [vertical.Walk, vertical.Register])
    @pytest.mark.parametrize("member", ["__iter__", "__len__"])
    def test_no_undeclared_dunder(self, cls, member):
        assert not hasattr(cls, member), (
            f"{cls.__name__} defines {member}, which presence_audit.protocols does not "
            f"declare -- the adapter is relying on something no reader of the "
            f"protocol could know to implement")

    def test_the_naming_convention_is_not_used_to_decide(self):
        """`LOOKS_TEMPLATED` is a proposal; `templated: true` is the decision."""
        v = vertical.FactoryLineVocabulary()
        assert v.template_pattern("SpareAnalog3") is None
        assert v.template_pattern("reserved_1") is None


class TestTheCoreCanSeeATemplateSlot:
    """Sec. 4.5 of the 0.1.6 review: two protocol members with no reachable
    true case.

    `load_register` strips templated tags before anything else sees the register,
    and the vertical built its points from what survived -- so `is_templated` and
    `disabled` always answered False, and the core's `templated_tags` count was
    zero however many slots a register declared. Nothing could go red: the count
    was correct about the points it was given.
    """

    def test_the_register_really_declares_one(self, register):
        """Non-vacuity. With no template slot in the fixture, both rules below
        are true of an empty set -- which is how this passed for a month."""
        assert any(row["reason"] == "declared_templated"
                   for row in register.get("_excluded_tags") or [])

    def test_a_template_slot_reaches_the_core_as_a_point(self, register):
        from factory_line_audit.vertical import Register
        points = list(Register(register).points)
        templated = [p for p in points if p.is_templated]
        assert len(templated) == 1, [p.display_name for p in templated]
        assert templated[0].display_name == "PR-01.SpareAnalog3"

    def test_it_is_disabled_and_still_names_its_node(self, register):
        """A point the core is told to skip still has to be addressable, or the
        count is the only thing it can report about it."""
        from factory_line_audit.vertical import Register
        slot = next(p for p in Register(register).points if p.is_templated)
        assert slot.disabled is True
        assert slot.name.startswith("ns=")
        assert slot.type == "measurement"

    def test_no_surviving_tag_claims_to_be_a_slot(self, register):
        """The inverse. If `points` grew a second copy of every tag, or flagged
        the wrong ones, the count above would still be satisfiable."""
        from factory_line_audit.vertical import Register
        points = list(Register(register).points)
        names = [p.display_name for p in points]
        assert len(names) == len(set(names)), "a tag reached the core twice"
        live = [p.display_name for p in points if not p.is_templated]
        assert "PR-01.SpareAnalog3" not in live
