"""The tool surface: closure, and the absences that are deliberate."""
from __future__ import annotations

import ast
import inspect
import os

import pytest

from conftest import CORPUS, FIXTURE, REGISTER
from factory_line_audit import tools
from factory_line_audit.tools import SPEC, WITHHELD, dispatch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "src", "factory_line_audit")


def _declared_extras():
    """extra -> the distributions `pyproject.toml` puts behind it.

    Read from the packaging metadata rather than from anything in the package,
    because the question the callers ask is whether this package's own map of
    extras agrees with what an install of those extras would actually provide.
    """
    import re
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as handle:
        body = handle.read()
    section = body.split("[project.optional-dependencies]")[1].split("\n[")[0]
    out = {}
    for extra, raw in re.findall(r"^(\w+)\s*=\s*\[(.*?)\]", section,
                                 re.MULTILINE | re.DOTALL):
        out[extra] = [re.split(r"[<>=!~\[;]", piece.strip().strip("\"'"))[0].strip()
                      for piece in raw.split(",") if piece.strip().strip("\"'")]
    return {extra: [d for d in dists if d] for extra, dists in out.items()}


def _module_imports(name):
    """(sibling modules, third-party roots) one package module imports."""
    path = os.path.join(PACKAGE, name + ".py")
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    siblings, third = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                if node.module:
                    siblings.add(node.module.split(".")[0])
                else:
                    siblings.update(alias.name for alias in node.names)
            elif node.module:
                third.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            third.update(alias.name.split(".")[0] for alias in node.names)
    return siblings, third


def _reach_of_verb(verb):
    """Every third-party root a CLI verb can reach, transitively.

    Two closures, because the reach lives in both: the call graph INSIDE `cli`
    starting at the verb's handler -- `cmd_presence` imports nothing itself and
    calls a helper that does -- and then the sibling-module import closure from
    whatever those functions import. Following only the handler's own body
    measured an empty set and called it proof.
    """
    import textwrap

    from factory_line_audit import cli
    siblings, third, walked = set(), set(), set()
    pending = [_handler_of(verb).__name__]
    while pending:
        name = pending.pop()
        if name in walked:
            continue
        function = getattr(cli, name, None)
        if function is None or not callable(function):
            continue
        walked.add(name)
        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    if node.module:
                        siblings.add(node.module.split(".")[0])
                    else:
                        siblings.update(alias.name for alias in node.names)
                elif node.module:
                    third.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                third.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                pending.append(node.func.id)
    seen = set()
    queue = list(siblings)
    while queue:
        module = queue.pop()
        if module in seen or not os.path.exists(
                os.path.join(PACKAGE, module + ".py")):
            continue
        seen.add(module)
        more, roots = _module_imports(module)
        third |= roots
        queue.extend(more - seen)
    assert seen, (f"{verb} reaches no module in this package; the walk found "
                  f"nothing and an empty reach agrees with every map")
    return third


class _Withheld:
    """A loader that refuses, so the refusal happens where a real one would.

    `find_spec` could raise `ImportError` directly and this file once did it that
    way; a spec whose loader fails during execution is the documented shape and
    is what a broken third-party package actually does, so it is the one less
    likely to behave differently on an interpreter this machine cannot run.
    """

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        raise ImportError(f"{module.__name__} is withheld for this measurement")


class _Withhold:
    """Refuse every extra's root module, and record which ones were asked for."""

    def __init__(self, roots):
        self.roots, self.attempted = set(roots), set()

    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root not in self.roots:
            return None
        self.attempted.add(root)
        import importlib.util
        return importlib.util.spec_from_loader(fullname, _Withheld())


#: Parsed once per session. The measurement is a subprocess, so four tests
#: asking for it would be four interpreters otherwise.
_MEASURED_REACH = {}


def _reach_by_running():
    """verb -> the extras it actually tried to import, measured by running it.

    IN A FRESH INTERPRETER, and that is not a detail. Withholding a module works
    by refusing its import, and an import already satisfied never reaches a
    finder -- so asked inside the suite, after some other test has imported the
    engine, every verb measures an empty set and the whole instrument reads as
    *nothing needs anything*. MEASURED: run alone this passed, run with the file
    it lives in it tripped its own control. The child is this very file, so there
    is one implementation of the measurement and the parent exercises it rather
    than holding a second copy of it.
    """
    import json
    import subprocess
    import sys
    if not _MEASURED_REACH:
        proc = subprocess.run([sys.executable, os.path.abspath(__file__),
                               "--measure-reach"],
                              capture_output=True, text=True, timeout=600)
        assert proc.returncode == 0, (
            f"the reach measurement did not complete: "
            f"{proc.stderr.strip()[-400:]}")
        _MEASURED_REACH.update(
            {verb: set(extras)
             for verb, extras in json.loads(proc.stdout).items()})
    return dict(_MEASURED_REACH)


def _measure_reach_here():
    """The measurement itself, run in a child with nothing imported yet.

    THE ORACLE THE AST WALK CANNOT MOVE. `_reach_of_verb` approximates
    reachability by reading source, and an approximation's blind spots are
    invisible from inside it: a call whose callee is a subscript or an attribute
    is not followed, so a verb reaching the engine that way measures as reaching
    nothing -- and the map could then go stale with every guard green. MEASURED:
    with a reach of that shape planted in `cli`, both guards above passed while
    the verb needed an extra nobody declared.

    Every root is refused here rather than uninstalled, so the answer does not
    depend on what this interpreter has: a failed import is not cached, so one
    process can ask once per verb. The arguments are real, because a verb that
    exits before its own body measures an empty set that reads as *needs
    nothing* -- which is why `_ARGV_FOR` hands each verb inputs it will act on,
    and why the controls below assert the refusal applied at all.
    """
    import contextlib
    import importlib
    import io
    import json
    import sys
    import tempfile

    roots = {root: extra for extra, dists in _declared_extras().items()
             for root in (d.replace("-", "_") for d in dists)}
    assert roots, "no distribution roots derived; nothing would be withheld"
    withhold = _Withhold(roots)
    sys.meta_path.insert(0, withhold)
    try:
        for root in sorted(roots):
            try:
                importlib.import_module(root)
            except ImportError:
                continue
            raise AssertionError(
                f"{root} imported while it was supposed to be withheld; every "
                f"measurement below would be an empty set reading as *needs "
                f"nothing*")
        assert withhold.attempted == set(roots), (
            f"the control asked for {sorted(roots)} and the finder saw "
            f"{sorted(withhold.attempted)}")
        from factory_line_audit import cli
        work = tempfile.mkdtemp()
        attest = os.path.join(work, "attest.json")
        with open(attest, "w", encoding="utf-8") as handle:
            # Enough of one for `attest` to reach its own body and refuse: the
            # engine is withheld here, so a real attestation cannot be produced.
            json.dump({"format": "factory-line-audit/attest/0"}, handle)
        measured = {}
        for verb, argv in sorted(_ARGV_FOR(work, attest).items()):
            withhold.attempted.clear()
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                cli.main(list(argv))
            measured[verb] = sorted(roots[root]
                                    for root in withhold.attempted)
        return measured
    finally:
        sys.meta_path.remove(withhold)


def _ARGV_FOR(work, attest):
    """Real arguments for every CLI verb, so each one reaches its own body."""
    clean = os.path.join(CORPUS, "clean.json")
    return {
        "presence": ["presence", "--register", REGISTER, "--walk", clean],
        "draft": ["draft", "--register", REGISTER,
                  "--out", os.path.join(work, "draft.json")],
        "gate": ["gate", "--register", REGISTER, FIXTURE],
        "generate": ["generate", "--register", REGISTER, "--declarations",
                     FIXTURE, "--model-out", os.path.join(work, "m.yaml"),
                     "--manifest-out", os.path.join(work, "mf.json")],
        "detect": ["detect", "--register", REGISTER, "--walk", clean,
                   "--declarations", FIXTURE],
        "validate-walk": ["validate-walk", clean],
        "regression": ["regression", "--before", clean, "--after",
                       os.path.join(CORPUS, "asset_absent.json")],
        "attest": ["attest", attest],
        "capture": ["capture", "--register", REGISTER, "--target",
                    "opc.tcp://127.0.0.1:1/unreachable-on-purpose",
                    "--out", os.path.join(work, "w.json")],
    }


def _handler_of(verb):
    """The function the CLI routes `verb` to, read off the real parser.

    Through the parser rather than by spelling `cmd_` + the verb: the routing is
    what a caller gets, and a verb rerouted to a different handler would leave a
    name-based lookup measuring a function nothing calls.
    """
    from factory_line_audit import cli
    for action in cli.build_parser()._actions:
        choices = getattr(action, "choices", None) or {}
        if verb in choices:
            handler = choices[verb].get_default("fn")
            assert handler is not None, f"{verb} is parsed and routed nowhere"
            return handler
    raise AssertionError(f"the CLI has no verb {verb!r}")


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
        probe agrees with a real import.

        THIS TEST WAS GREEN AGAINST A WRONG MAP, and that is why the one below
        exists. It imported the same module names the probe imports, so
        `import arbiter` -- a module no distribution provides -- failed on both
        sides, `detect` was reported absent, the assertion held, and
        `missing_extras()` reported the engine missing in every interpreter ever
        shipped. Shared implementation proves consistency, never truth. Kept,
        because the agreement it asserts is still worth asserting; no longer
        alone.
        """
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

    def test_the_probe_agrees_with_the_installed_distributions(self):
        """The independent oracle: `importlib.metadata`, not this package's map.

        For every extra `pyproject.toml` declares, ask the metadata whether the
        distribution it names is installed, and require `missing_extras()` to
        say the same. Nothing here reads `EXTRA_PROBE`, so an import name that
        does not belong to the distribution reddens -- which `arbiter` did, in
        every environment, for as long as the map carried it.
        """
        from importlib.metadata import PackageNotFoundError, distribution

        from factory_line_audit.tools import missing_extras
        absent, declared = missing_extras(), _declared_extras()
        assert declared, "pyproject declares no extras; this test measures nothing"
        for extra, dists in sorted(declared.items()):
            assert dists, f"[{extra}] declares no distribution"
            installed = True
            for dist in dists:
                try:
                    distribution(dist)
                except PackageNotFoundError:
                    installed = False
            if installed:
                assert extra not in absent, (
                    f"every distribution behind [{extra}] ({dists}) is "
                    f"installed and the probe reports the extra absent: it is "
                    f"importing the wrong module name")
            else:
                assert extra in absent, (
                    f"[{extra}] is not installed ({dists}) and the probe does "
                    f"not report it")

    def test_every_entry_that_reaches_an_extra_declares_it(self):
        """`REQUIRES_EXTRA`, derived from the import graph rather than recalled.

        `detect` was missing from the map. The rule 0.1.8 introduced -- an
        absent extra is not a broken entry -- did not cover the one entry that
        needs the engine, and no test could notice, because every test about the
        map read the map. The reach is computed here from the verb's own imports:
        an entry that starts importing the core or the engine reddens until the
        map says so.
        """
        from factory_line_audit.tools import REQUIRES_EXTRA, SPEC
        by_root = {root: extra
                   for extra, dists in _declared_extras().items()
                   for root in (d.replace("-", "_") for d in dists)}
        assert by_root, "no distribution roots derived; the reach cannot be read"
        reached = {}
        # A SET, NOT THE LAST ONE SEEN. This assigned `reached[name]` inside the
        # loop, so an entry reaching two extras kept whichever root came out of
        # a SET last -- which is hash order, so the verdict flipped with
        # PYTHONHASHSEED. MEASURED across six seeds: three said one extra and
        # three the other. A wrong answer is bad; a wrong answer that is only
        # sometimes wrong costs the next reader the afternoon.
        for name, spec in SPEC.items():
            for root in _reach_of_verb(spec["verb"]):
                if root in by_root:
                    reached.setdefault(name, set()).add(by_root[root])
        for name, extras in sorted(reached.items()):
            assert len(extras) == 1, (
                f"{name} reaches {sorted(extras)} and REQUIRES_EXTRA holds one "
                f"extra per entry, so it cannot say this. Widen the map's value "
                f"to a set before widening the dependency")
        reached = {name: sorted(extras)[0] for name, extras in reached.items()}
        assert reached, (
            "no SPEC entry reaches any extra's distribution; either the import "
            "walk broke or the table stopped needing an engine")
        for name, extra in sorted(reached.items()):
            assert REQUIRES_EXTRA.get(name) == extra, (
                f"{name} reaches [{extra}] through its own imports and "
                f"REQUIRES_EXTRA says {REQUIRES_EXTRA.get(name)!r}; a caller "
                f"cannot tell a missing install from a broken entry")
        for name in REQUIRES_EXTRA:
            assert name in reached, (
                f"{name} declares an extra its imports do not reach; the map "
                f"has outlived the dependency")

    def test_the_reach_measured_by_running_agrees_with_the_map(self):
        """O3 from the 0.1.9 review, closed by adding an instrument rather than
        by patching the one that was wrong.

        The review named two blind spots in `_reach_of_verb` and called both
        latent. They are -- today. What is not latent is that a static walk
        cannot know its own blind spots: planted a reach through a subscripted
        callee and both guards above stayed green while the verb needed an extra
        nobody declared. So the map is held to the RUN, and the walk is held to
        the run below.
        """
        from factory_line_audit.tools import REQUIRES_EXTRA, SPEC
        measured = _reach_by_running()
        for name, spec in sorted(SPEC.items()):
            reached = measured[spec["verb"]]
            declared = REQUIRES_EXTRA.get(name)
            assert reached == ({declared} if declared else set()), (
                f"running {spec['verb']} tried to import {sorted(reached)} and "
                f"REQUIRES_EXTRA says {declared!r}; a caller cannot tell a "
                f"missing install from a broken entry")

    def test_the_run_reaches_something_or_it_is_measuring_nothing(self):
        """Non-vacuity, and it is the whole protection here: an empty set is what
        a verb that never reached its own body also measures."""
        measured = _reach_by_running()
        reaching = {verb: sorted(extras) for verb, extras in measured.items()
                    if extras}
        assert len(reaching) >= 2, (
            f"only {reaching} reached any extra; either the withholding stopped "
            f"applying or the arguments stop the verbs before their own bodies")

    def test_the_verb_this_surface_refuses_is_the_one_that_dials(self):
        """`capture` is accounted for by `NOT_OFFERED` rather than offered, and
        the measurement says why in the same breath: it is the verb that needs
        the OPC UA client. Held here because the table's own walk cannot see it
        -- `capture` is not in `SPEC`, which is the point of it."""
        from factory_line_audit.tools import NOT_OFFERED
        measured = _reach_by_running()
        assert measured["capture"] == {"live"}, (
            f"capture reached {sorted(measured['capture'])}; the refusal is "
            f"about first contact and this is what makes it first contact")
        assert "capture" in NOT_OFFERED

    def test_the_static_walk_never_claims_more_than_the_run(self):
        """The walk may measure LESS -- that is O3, and it is why the run is the
        oracle. It must never measure more: a reach it invents would put an
        extra in the map that nothing needs, and the other direction of the
        agreement test would then demand a dependency this package does not
        have."""
        from factory_line_audit.tools import SPEC
        by_root = {root: extra
                   for extra, dists in _declared_extras().items()
                   for root in (d.replace("-", "_") for d in dists)}
        measured = _reach_by_running()
        for name, spec in sorted(SPEC.items()):
            walked = {by_root[root] for root in _reach_of_verb(spec["verb"])
                      if root in by_root}
            invented = walked - measured[spec["verb"]]
            assert not invented, (
                f"the import walk says {spec['verb']} reaches {sorted(invented)} "
                f"and running it does not touch them")

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
        behavioural cases above, not instead of them.

        EVERY declared extra, not the one that was current when this was
        written. It named `vertical` alone, so when the leg grew a second branch
        for the prerequisite half -- the `detect` run that produces the
        attestation -- a literal there would have passed. The list is derived
        from `pyproject.toml`; the QUOTED form is what is forbidden, because
        `detect_argv` legitimately carries the bare word.
        """
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "battery", "run_battery.py"),
                  encoding="utf-8") as handle:
            source = handle.read()
        leg = source.split("def leg_tool(")[1].split("\ndef ")[0]
        assert "REQUIRES_EXTRA" in leg or "_extra_for_verb" in leg
        extras = sorted(_declared_extras())
        assert extras, "no extras derived; this test forbids nothing"
        for extra in extras:
            assert f'"{extra}"' not in leg and f"'{extra}'" not in leg, (
                f"the leg names [{extra}] literally; it must read the map")


if __name__ == "__main__":
    # `python tests/test_tools.py --measure-reach` -- the child half of
    # `_reach_by_running`. Not a second entry point for anything else: the
    # measurement needs an interpreter in which nothing has been imported yet,
    # and that is the only thing this block provides.
    import json as _json
    import sys as _sys
    if _sys.argv[1:] != ["--measure-reach"]:
        _sys.stderr.write(f"usage: {_sys.argv[0]} --measure-reach\n")
        raise SystemExit(2)
    _sys.stdout.write(_json.dumps(_measure_reach_here()))
