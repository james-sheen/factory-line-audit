"""`capture`'s decisions that do not need a server.

What DOES need one -- the client, the status-word rule, the OUTCOME line and
the digest of a real file -- is the `capture` battery leg, against the rung-2
surface. Faking a server here would test the fake.
"""
from __future__ import annotations

import hashlib
import json
import os

from conftest import CORPUS
from factory_line_audit.capture import (declared_nodes, digest,
                                        membership_unchanged, walk_recorded)

REGISTER = {"assets": [
    {"id": "PR-01", "tags": {
        "die_temp_c": {"node": "ns=2;s=PR01.DieTemp", "class": "measurement"},
        "tonnage_kn": {"node": "ns=2;s=PR01.Tonnage", "class": "measurement"}}},
    {"id": "ST-01", "tags": {
        "cycle_time_s": {"node": "ns=2;s=ST01.CycleTime", "class": "measurement"}}},
]}


class TestReadingTheRegister:
    def test_tags_are_an_object_not_a_list(self):
        """Written as a list first, which iterated the KEYS and asked a string
        for `.get("node")`. The verb then reported could-not-complete against a
        server that was answering perfectly, which is the worst shape of wrong:
        it blamed the far end."""
        assert declared_nodes(REGISTER) == ["ns=2;s=PR01.DieTemp",
                                            "ns=2;s=PR01.Tonnage",
                                            "ns=2;s=ST01.CycleTime"]

    def test_a_register_with_no_tags_asks_for_nothing(self):
        assert declared_nodes({"assets": [{"id": "A", "tags": {}}]}) == []

    def test_a_node_declared_twice_is_asked_for_once(self):
        twice = {"assets": [{"id": "A", "tags": {
            "one": {"node": "ns=2;s=X"}, "two": {"node": "ns=2;s=X"}}}]}
        assert declared_nodes(twice) == ["ns=2;s=X"]


class TestTheContentHandle:
    def test_it_is_sha256_over_the_bytes(self):
        """So `sha256sum` computes the same value and a recipient can check the
        handle without installing this tool -- which is the whole reason it is
        over the file rather than over a re-serialisation of it."""
        raw = b'{"format": "factory-line-audit/walk/1"}\n'
        assert digest(raw) == "sha256:" + hashlib.sha256(raw).hexdigest()

    def test_text_and_bytes_agree(self):
        raw = '{"a": 1}\n'
        assert digest(raw) == digest(raw.encode("utf-8"))

    def test_a_different_file_is_a_different_handle(self):
        assert digest("a") != digest("b")


class TestTheMembershipCache:
    FRESH = {"endpoint": "opc.tcp://127.0.0.1:4840/x",
             "namespaces": ["urn:a", "urn:b"],
             "present": ["ns=2;s=A"], "absent": []}

    def test_the_same_answer_from_the_same_server_is_unchanged(self):
        assert membership_unchanged(dict(self.FRESH), self.FRESH)

    def test_a_different_endpoint_is_not_unchanged(self):
        """Found by getting it wrong: two runs against two different servers on
        two different ports reported `unchanged`, because their address spaces
        matched. A skipped walk justified by another machine's address space is
        worse than no cache at all."""
        other = dict(self.FRESH, endpoint="opc.tcp://127.0.0.1:4841/x")
        assert not membership_unchanged(other, self.FRESH)

    def test_a_node_that_appeared_is_not_unchanged(self):
        assert not membership_unchanged(
            dict(self.FRESH, present=["ns=2;s=A", "ns=2;s=B"]), self.FRESH)

    def test_a_node_that_went_absent_is_not_unchanged(self):
        assert not membership_unchanged(
            dict(self.FRESH, absent=["ns=2;s=Z"]), self.FRESH)

    def test_a_new_namespace_is_not_unchanged(self):
        assert not membership_unchanged(
            dict(self.FRESH, namespaces=["urn:a"]), self.FRESH)

    def test_no_cache_at_all_is_not_unchanged(self):
        """The first run must walk, not report a comparison it never made."""
        assert not membership_unchanged(None, self.FRESH)
        assert not membership_unchanged("", self.FRESH)


class TestACachedPassThatNeverWalked:
    """O1 from the 0.1.9 review. `walk_recorded` is the second question.

    The cache is written before the walk is attempted, on purpose: the dial has
    already happened and what it learned must be recorded whatever the verdict.
    So a pass whose walk then failed leaves a cache asserting the address space
    holds exactly these nodes and nothing saying no walk was taken -- and the
    next run found the membership unchanged, exited 0 and read nothing.

    MEASURED end to end against the rung-3 surface before it was fixed, with the
    channel cut between the two dials: pass one exited 2 with the cache on disk
    and no walk; pass two printed `OUTCOME unchanged` and exited 0. The review
    also proposed `--budget 0` for this, which does not reproduce it: that exits
    0 with `OUTCOME walked` and a walk holding zero samples.
    """

    def test_a_cache_with_no_such_field_records_no_walk(self):
        """Every cache written before this rule, INCLUDING the ones written by
        the failing passes it is about. Reading an absent field as *a walk was
        taken* would leave the gap open for precisely those."""
        assert walk_recorded(dict(TestTheMembershipCache.FRESH)) is None

    def test_a_cache_naming_a_walk_records_one(self):
        assert walk_recorded(dict(TestTheMembershipCache.FRESH,
                                  walk_written="/w/walk.json")) == "/w/walk.json"

    def test_an_explicit_null_records_no_walk(self):
        """What this version writes on a pass whose walk has not happened yet."""
        assert walk_recorded(dict(TestTheMembershipCache.FRESH,
                                  walk_written=None)) is None

    def test_nothing_that_is_not_a_path_counts_as_one(self):
        """An empty string is falsey and would read as no walk anyway; `True` is
        not, and would have stood in for a path nobody can name."""
        for value in ("", True, 1, [], {"path": "/w.json"}):
            assert walk_recorded(dict(TestTheMembershipCache.FRESH,
                                      walk_written=value)) is None, value

    def test_no_cache_at_all_records_no_walk(self):
        for absent in (None, "", [], 0):
            assert walk_recorded(absent) is None, absent


class TestItStaysOutOfStageOne:
    def test_asyncua_is_imported_lazily(self):
        """Stage 1 declares no dependency and a test asserts it. Importing the
        client library at module scope would make `presence` need the [live]
        extra to run at all."""
        import ast
        import pathlib
        source = pathlib.Path(__file__).resolve().parents[1] / "src" \
            / "factory_line_audit" / "capture.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        top = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                top.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top.add(node.module.split(".")[0])
        assert "asyncua" not in top, top


class TestAWalkSaysHowManyTimesTheServerWasAsked:
    """R10, carried from M6 in the 0.1.6 review.

    Samples are keyed on the first node's timestamp, so a server whose values
    and stamps do not advance yields exactly ONE sample however long `--budget`
    runs. The walk then looked identical to a server that had been asked once:
    the engine declines `insufficient_samples` either way, and nothing in the
    artifact said which of the two had happened. A reader sent to a plant on
    that evidence is being sent on a guess.

    `polls` is not `len(samples)`. That is the whole point of recording it.
    """

    def test_the_source_block_records_the_poll_count(self):
        import inspect

        from factory_line_audit import capture as module
        source = inspect.getsource(module._walk)
        assert '"polls": polls' in source
        assert "polls += 1" in source

    def test_the_budget_is_recorded_beside_it(self):
        """A poll count without the budget it ran against is a number nobody can
        read: four polls in 0.2 s and four in 30 s are different facts."""
        import inspect

        from factory_line_audit import capture as module
        assert '"samples_budget_s"' in inspect.getsource(module._walk)

    def test_a_walk_carrying_the_field_still_validates(self):
        """The walk format did not move, so every existing reader must accept
        the new key. Held through the loader rather than assumed."""
        from factory_line_audit import formats
        from factory_line_audit.walkcheck import validate_walk
        with open(os.path.join(CORPUS, "clean.json"), encoding="utf-8") as handle:
            walk = json.load(handle)
        walk["source"]["polls"] = 412
        walk["source"]["samples_budget_s"] = 30.0
        assert validate_walk(walk) == []
        assert formats.split(walk["format"])[1] == formats.split(formats.WALK)[1]
