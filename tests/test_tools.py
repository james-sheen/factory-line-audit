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
            "before": os.path.join(CORPUS, "clean.json"),
            "after": os.path.join(CORPUS, "asset_absent.json"),
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


class TestTheSurfaceIsClosedOverTheCli:
    """M4 from the 0.1.6 review.

    `validate-walk` and `regression` were in neither the table nor the withheld
    list -- exactly the *omission nobody wrote down* this module's docstring says
    the enumeration exists to prevent. Two local Stage-1 verbs, absent from both
    sides of a surface whose whole claim is that its absences are deliberate.

    Held against the parser, not a list: a verb added to the CLI lands here.
    """

    def _verbs(self):
        import argparse

        from factory_line_audit.cli import build_parser
        subs = [a for a in build_parser()._actions
                if isinstance(a, argparse._SubParsersAction)]
        return set(subs[0].choices)

    def test_there_are_verbs_and_entries_to_compare(self):
        assert len(self._verbs()) >= 5 and len(SPEC) >= 5

    def test_every_cli_verb_is_offered_or_accounted_for(self):
        """NOT the acceptance the review proposed.

        It asked for `verbs(SPEC) | verbs(WITHHELD) == verbs(cli)`, which is
        satisfiable only by offering `capture` -- first contact, the one thing
        this surface refuses on purpose. `WITHHELD` is keyed by capability and a
        capability is not a verb, so the union it names cannot close. `NOT_OFFERED`
        is the missing half: a verb is offered, or it is accounted for there.
        """
        from factory_line_audit.tools import NOT_OFFERED
        offered = {spec["verb"] for spec in SPEC.values()}
        missing = sorted(self._verbs() - offered - set(NOT_OFFERED))
        assert not missing, (f"the CLI accepts these verbs and the tool surface "
                             f"neither offers nor accounts for them: {missing}")

    def test_nothing_is_both_offered_and_refused(self):
        from factory_line_audit.tools import NOT_OFFERED
        offered = {spec["verb"] for spec in SPEC.values()}
        assert not (offered & set(NOT_OFFERED))

    def test_every_refused_verb_names_a_reason_that_exists(self):
        """A verb pointing at a capability nobody wrote down is the same
        omission one level out."""
        from factory_line_audit.tools import NOT_OFFERED
        for verb, capability in NOT_OFFERED.items():
            assert capability in WITHHELD, (verb, capability)
            assert WITHHELD[capability]

    def test_no_entry_offers_a_verb_the_cli_does_not_have(self):
        offered = {spec["verb"] for spec in SPEC.values()}
        extra = sorted(offered - self._verbs())
        assert not extra, f"the table offers verbs the CLI refuses: {extra}"

    def test_what_is_withheld_is_not_a_verb_name(self):
        """The two lists answer different questions. A withheld name is a
        capability, not a verb: if one ever collides with a verb the surface
        would be offering and refusing the same thing."""
        assert not (set(WITHHELD) & self._verbs())


class TestAnAbsentExtraIsNotABrokenEntry:
    """R8 from the 0.1.7 review.

    `compare_walks` routes to `regression`, which asks the core to judge the two
    walks and returns 2 without `[vertical]`. `leg_tool` treats any entry
    answering 2 as an entry that could not construct, and the answer carries no
    `error` for a verb that ran -- so the leg reported `('compare_walks', None)`:
    a red naming neither the extra nor a reason, against a table that was fine.
    The leg still goes red, because it could not ask its question; what changed
    is that it can now say which install would let it.
    """

    def test_the_requirement_is_declared_beside_the_table(self):
        from factory_line_audit.tools import REQUIRES_EXTRA, SPEC
        assert REQUIRES_EXTRA, "no entry declares an extra; the map is inert"
        for name in REQUIRES_EXTRA:
            assert name in SPEC, f"{name} declares an extra and is not offered"

    def test_the_probe_measures_rather_than_declares(self):
        """`missing_extras` must answer about THIS interpreter. The suite's own
        environment has `[vertical]`, so the reachable assertion is that the
        probe agrees with a real import."""
        import importlib

        from factory_line_audit.tools import EXTRA_PROBE, missing_extras
        absent = missing_extras()
        for extra, module in EXTRA_PROBE.items():
            try:
                importlib.import_module(module)
            except ImportError:
                assert extra in absent, f"{extra} is not importable and not reported"
            else:
                assert extra not in absent, f"{extra} imports and is reported absent"

    def test_every_declared_extra_names_a_module_to_probe(self):
        from factory_line_audit.tools import EXTRA_PROBE, REQUIRES_EXTRA
        for name, extra in REQUIRES_EXTRA.items():
            assert extra in EXTRA_PROBE, (
                f"{name} needs [{extra}] and nothing says how to detect it, so "
                f"a caller cannot tell a missing install from a broken entry")

    def test_the_declared_extras_are_ones_the_package_offers(self):
        """Held against `pyproject.toml`, so a renamed extra reddens here."""
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as handle:
            body = handle.read()
        section = body.split("[project.optional-dependencies]")[1].split("\n[")[0]
        declared = set(re.findall(r"^(\w+)\s*=", section, re.MULTILINE))
        from factory_line_audit.tools import EXTRA_PROBE
        assert set(EXTRA_PROBE) <= declared, (set(EXTRA_PROBE) - declared)

    @staticmethod
    def _decide(*args):
        """`blocked_by_extras` from the battery, which is not importable as a
        package: the battery is scripts, run by path."""
        import importlib.util
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec = importlib.util.spec_from_file_location(
            "fla_run_battery", os.path.join(root, "battery", "run_battery.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.blocked_by_extras(*args)

    def test_a_failure_whose_extra_is_absent_names_the_extra(self):
        said = self._decide(["compare_walks"], {"compare_walks": "vertical"},
                            {"vertical": "presence_audit"})
        assert "compare_walks needs [vertical]" in said
        assert "not a verdict about them" in said

    def test_a_failure_with_every_extra_present_is_a_real_failure(self):
        """The control. Without this, a function that always blamed an extra
        would satisfy the rule above and hide every genuine break."""
        assert self._decide(["compare_walks"], {"compare_walks": "vertical"},
                            {}) == ""

    def test_a_failure_that_needs_no_extra_is_a_real_failure(self):
        assert self._decide(["presence"], {"compare_walks": "vertical"},
                            {"vertical": "presence_audit"}) == ""

    def test_nothing_failed_is_not_an_excuse_either(self):
        assert self._decide([], {"compare_walks": "vertical"},
                            {"vertical": "presence_audit"}) == ""

    def test_the_leg_reads_the_map_rather_than_listing_it(self):
        """The lesson `WITHHELD` already taught here: a copy in the leg is a
        copy that drifts the day the map grows an entry. Held in addition to the
        behavioural cases above, not instead of them."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "battery", "run_battery.py"),
                  encoding="utf-8") as handle:
            source = handle.read()
        leg = source.split("def leg_tool(")[1].split("\ndef ")[0]
        assert "REQUIRES_EXTRA" in leg and "missing_extras" in leg
        assert '"vertical"' not in leg and "'vertical'" not in leg, (
            "the leg names an extra literally; it must read the map")
