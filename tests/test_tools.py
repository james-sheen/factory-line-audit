"""The tool surface: closure, and the absences that are deliberate."""
from __future__ import annotations

import ast
import inspect
import os

import pytest

from conftest import CORPUS, FIXTURE, REGISTER
from factory_line_audit import tools
from factory_line_audit.tools import SPEC, WITHHELD, dispatch


class TestTheTableIsWalkedNotSampled:
    @pytest.mark.parametrize("name", sorted(SPEC))
    def test_every_entry_dispatches(self, name, tmp_path):
        """BRIDGES on the tool surface: testing one entry at a time passes while
        an entry that was
        added and never wired sits there returning nothing."""
        arguments = {
            "register": REGISTER, "walk": os.path.join(CORPUS, "clean.json"),
            "declarations": [FIXTURE], "attestation": FIXTURE,
            "out": os.path.join(str(tmp_path), "draft.json"),
            "model_out": os.path.join(str(tmp_path), "m.yaml"),
            "manifest_out": os.path.join(str(tmp_path), "mf.json"),
        }
        seen = {}

        def runner(argv):
            seen["argv"] = argv
            return 0

        answer = dispatch(name, arguments, runner=runner)
        assert answer["exit"] == 0
        assert seen["argv"][0] == SPEC[name]["verb"]
        assert not any(token.startswith("{") for token in seen["argv"])

    def test_every_entry_has_a_summary_and_a_verb(self):
        for name, spec in SPEC.items():
            assert spec["summary"].strip(), name
            assert spec["verb"], name
            assert spec["required"], name

    def test_every_placeholder_is_a_required_argument(self):
        """A template naming a parameter the spec does not require would fail
        only when someone omitted it, with a KeyError rather than a 2."""
        for name, spec in SPEC.items():
            placeholders = {t[1:-1] for t in spec["argv"]
                            if t.startswith("{") and t.endswith("}")}
            assert placeholders <= set(spec["required"]), name


class TestEveryAnswerCarriesItsVerdict:
    def test_the_exit_code_and_the_word_are_both_explicit(self):
        answer = dispatch("presence", {"register": REGISTER, "walk": "x"},
                          runner=lambda argv: 2)
        assert answer["exit"] == 2 and answer["verdict"] == "could-not-complete"

    def test_a_code_outside_the_set_is_normalised_and_the_raw_value_kept(self):
        answer = dispatch("presence", {"register": REGISTER, "walk": "x"},
                          runner=lambda argv: 137)
        assert answer["exit"] == 2 and answer["raw_exit"] == 137

    def test_an_unknown_tool_is_two_and_not_an_empty_answer(self):
        answer = dispatch("do_the_thing", {})
        assert answer["exit"] == 2 and "unknown tool" in answer["error"]

    def test_a_missing_argument_is_two_rather_than_a_traceback(self):
        answer = dispatch("presence", {"register": REGISTER})
        assert answer["exit"] == 2 and "walk" in answer["error"]


class TestWhatIsDeliberatelyNotOffered:
    def test_first_contact_is_not_a_tool(self):
        """BRIDGES, what no mechanism absorbs: the first credentialed reach into
        a real system is an act,
        not a call. A surface that does not offer it is a better boundary than
        a paragraph asking nicely."""
        assert "connect_to_plc" in WITHHELD
        answer = dispatch("connect_to_plc", {"endpoint": "opc.tcp://plant"})
        assert answer["exit"] == 2 and "First contact" in answer["error"]

    def test_marking_a_declaration_reviewed_is_not_a_tool(self):
        answer = dispatch("review_declarations", {"path": "x"})
        assert answer["exit"] == 2

    def test_no_withheld_name_is_also_in_the_table(self):
        assert not set(WITHHELD) & set(SPEC)

    def test_nothing_in_the_table_reaches_a_network(self):
        for name, spec in SPEC.items():
            assert "opc" not in " ".join(spec["argv"]).lower(), name


class TestTheBindingStaysThin:
    def test_the_table_and_the_dispatcher_import_no_protocol(self):
        """Checked by parsing, so this docstring cannot trip it. The closure
        test then runs where no SDK is installed, which is the point."""
        tree = ast.parse(inspect.getsource(tools))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add((node.module or "").split(".")[0])
        assert not (imported & {"mcp", "fastmcp", "grpc", "flask", "fastapi",
                                "aiohttp", "asyncua", "requests"}), imported

    def test_the_dispatcher_routes_through_the_cli(self):
        source = inspect.getsource(tools.dispatch)
        assert "from .cli import main" in source
        assert "feeder" not in source and "generator" not in source
