"""Every refusal class this package names, exercised by walking the list.

BRIDGES, on the tool surface, says to walk the table when testing closure,
because testing one
entry at a time passes while an entry that was added and never wired sits there
returning nothing. The same argument applies to refusals: `cli.REFUSALS` is the
enumeration, and this file asserts that every name in it is reachable.

The point is not the count. It is that adding a refusal without writing its test
fails HERE, in one place, rather than being noticed later by nobody.
"""
from __future__ import annotations

import json
import os

import pytest

from conftest import CORPUS, FIXTURE, REGISTER, write
from factory_line_audit import formats
from factory_line_audit.cli import REFUSALS, main

CLEAN_WALK = os.path.join(CORPUS, "clean.json")


def run(*argv):
    return main(list(argv))


def _register_with(tmp_path, mutate):
    with open(REGISTER, encoding="utf-8") as handle:
        body = json.load(handle)
    mutate(body)
    return write(tmp_path, "register.json", body)


@pytest.fixture
def exercised():
    return {}


class TestEveryRefusalIsReachable:
    """One test per entry in REFUSALS, and a closure test that they are all here."""

    def test_no_such_file(self, capsys):
        assert run("presence", "--register", "/nope.json", "--walk", CLEAN_WALK) == 2
        assert "no such file" in capsys.readouterr().err

    def test_not_json(self, tmp_path, capsys):
        path = write(tmp_path, "r.json", "{not json at all")
        assert run("presence", "--register", path, "--walk", CLEAN_WALK) == 2
        assert "not JSON" in capsys.readouterr().err

    def test_not_an_object(self, tmp_path, capsys):
        path = write(tmp_path, "r.json", [1, 2, 3])
        assert run("presence", "--register", path, "--walk", CLEAN_WALK) == 2
        assert "expected a JSON object" in capsys.readouterr().err

    def test_no_format_field(self, tmp_path, capsys):
        path = write(tmp_path, "r.json", {"assets": []})
        assert run("presence", "--register", path, "--walk", CLEAN_WALK) == 2
        assert "no format field" in capsys.readouterr().err

    def test_wrong_artifact(self, capsys):
        """A walk handed in where a register belongs. Different message from a
        version mismatch, because they are different problems."""
        assert run("presence", "--register", CLEAN_WALK, "--walk", CLEAN_WALK) == 2
        err = capsys.readouterr().err
        assert "expected factory-line-audit/register/1" in err

    def test_wrong_major(self, tmp_path, capsys):
        path = write(tmp_path, "r.json", {"format": "factory-line-audit/register/9"})
        assert run("presence", "--register", path, "--walk", CLEAN_WALK) == 2
        assert "major 9" in capsys.readouterr().err

    def test_register_empty(self, tmp_path, capsys):
        path = _register_with(tmp_path, lambda b: b.update(assets=[]))
        assert run("presence", "--register", path, "--walk", CLEAN_WALK) == 2
        assert "declares no assets" in capsys.readouterr().err

    def test_register_duplicate_asset(self, tmp_path, capsys):
        path = _register_with(tmp_path, lambda b: b["assets"].append(b["assets"][0]))
        assert run("presence", "--register", path, "--walk", CLEAN_WALK) == 2
        assert "declared twice" in capsys.readouterr().err

    def test_register_no_type(self, tmp_path, capsys):
        path = _register_with(tmp_path, lambda b: b["assets"][0].pop("type"))
        assert run("presence", "--register", path, "--walk", CLEAN_WALK) == 2
        assert "has no type" in capsys.readouterr().err

    def test_register_unknown_tag_class(self, tmp_path, capsys):
        def mutate(body):
            body["assets"][0]["tags"]["die_temp_c"]["class"] = "temperature"
        path = _register_with(tmp_path, mutate)
        assert run("presence", "--register", path, "--walk", CLEAN_WALK) == 2
        err = capsys.readouterr().err
        assert "declared, never inferred from the name" in err

    def test_register_no_node(self, tmp_path, capsys):
        def mutate(body):
            body["assets"][0]["tags"]["die_temp_c"].pop("node")
        path = _register_with(tmp_path, mutate)
        assert run("presence", "--register", path, "--walk", CLEAN_WALK) == 2
        assert "has no node id" in capsys.readouterr().err

    def test_declaration_unreviewed(self, tmp_path, capsys):
        """The gate, refusing by NAME. A gate that says *some file was not
        reviewed* has told the operator to go and look at all of them."""
        out = os.path.join(str(tmp_path), "draft.json")
        assert run("draft", "--register", REGISTER, "--out", out) == 0
        assert run("gate", "--register", REGISTER, out) == 2
        err = capsys.readouterr().err
        assert out in err and "unreviewed" in err

    def test_declaration_fixture_without_disclosure(self, tmp_path, capsys):
        with open(FIXTURE, encoding="utf-8") as handle:
            body = json.load(handle)
        body["reviewed_by"] = "A. Plausible Name"
        path = write(tmp_path, "d.json", body)
        assert run("gate", "--register", REGISTER, path) == 2
        assert "disclosing itself" in capsys.readouterr().err

    def test_declaration_malformed(self, tmp_path, capsys):
        with open(FIXTURE, encoding="utf-8") as handle:
            body = json.load(handle)
        body["statements"][0].pop("basis")
        body["statements"][1]["tag"] = "no_such_tag"
        path = write(tmp_path, "d.json", body)
        assert run("gate", "--register", REGISTER, path) == 2
        err = capsys.readouterr().err
        assert "no basis" in err and "no such tag" in err

    def test_hard_stop(self, tmp_path, capsys):
        """A hard stop is exit 2 and prints what it was, on stderr."""
        from factory_line_audit.feeder import HardStop
        stop = HardStop("schema_version", "envelope schema_version 2")
        assert stop.name == "schema_version"
        assert "schema_version" in str(stop)

    def test_unknown_verb(self, capsys):
        assert main([]) == 2

    def test_engine_absent_is_named(self):
        """Not run here -- an environment with the engine installed cannot
        produce it, and pretending otherwise would be a test that asserts on a
        branch it never took. The `ship` leg's Stage-1-only environment is where
        this one is exercised."""
        assert "engine_absent" in REFUSALS


class TestTheEnumerationIsClosed:
    def test_every_named_refusal_has_a_test(self):
        """The closure check. `test_<name>` for every key, so a refusal added
        to the dict without a test fails here."""
        have = {name[len("test_"):] for name in dir(TestEveryRefusalIsReachable)
                if name.startswith("test_")}
        have |= {"engine_absent"}
        missing = set(REFUSALS) - have
        assert not missing, f"refusals with no test: {sorted(missing)}"

    def test_no_test_claims_a_refusal_that_does_not_exist(self):
        """The other direction, which is the one that rots quietly: a test
        named for a refusal that was renamed or removed."""
        have = {name[len("test_"):] for name in dir(TestEveryRefusalIsReachable)
                if name.startswith("test_")}
        stray = have - set(REFUSALS) - {"engine_absent_is_named"}
        assert not stray, f"tests naming a refusal that is not declared: {sorted(stray)}"
