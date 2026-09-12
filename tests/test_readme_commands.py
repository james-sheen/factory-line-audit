"""Run the commands the README prints, exactly as it prints them.

**Borrowed from `bmc-sensor-audit`, whose docstring says why it exists**: its
README was wrong the moment it was written and stayed wrong through a full green
suite. It printed a bare `python3 -m bmc_sensor_audit.cli`, the package lives
under `src/`, and every run during development already had `PYTHONPATH` set --
so the documented command was never the command being tested.

The shape is the one this package exists to catch in other systems: **a check
written from the author's vocabulary inherits the author's blind spot.** A test
that restates the quickstart in its own words passes forever while the printed
quickstart is broken. So this READS the lines out of the page. Change the block
and this runs whatever you changed it to.

**Two things this README does that the sibling's does not.** Its commands are
wrapped over several lines with a trailing backslash, so they are joined before
anything runs -- half a command is a different command, and it would fail for a
reason that has nothing to do with the documentation. And its `draft` and `gate`
lines CHAIN through a file, so they run in order in one scratch directory rather
than independently; run alone, `gate` would be refused for the wrong reason and
the test would pass on a coincidence.

**What is substituted, and why that is still faithful.** The page tells a reader
to build a virtualenv at `/tmp/v` and `export PYTHONPATH=src`. This runs the same
commands with the interpreter that has the package, from the directory the page
says to `cd` into, with `/tmp/` pointed at a scratch dir so one run cannot
inherit another's leftovers. Nothing about the command's own shape is rewritten.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ROOT

README = Path(ROOT) / "README.md"

#: The module a documented command invokes.
CLI = "factory_line_audit.cli"

#: A trailing `# 0` or `# 2, names it`: the exit code the page promises.
DOCUMENTED_EXIT = re.compile(r"#\s*(\d)\b")

#: The interpreter the page builds WITH the extras. Which of the two a line
#: names is not incidental: the page runs Stage 1 under a bare `python3` to show
#: it needs nothing installed, and Stage 2 under the virtualenv because it needs
#: the engine. Collapsing them ran `detect` on an interpreter with no engine,
#: and this file then reported that the README was wrong -- a check firing
#: precisely, against the wrong subject. The classification below is DERIVED
#: from the page rather than from a list of which verbs need what.
WITH_EXTRAS = ".venv/bin/python"

#: An interpreter the page names but a test environment does not have.
INTERPRETER = re.compile(r"^(?:\.venv/bin/python|python3)\b")

#: argparse refusing the command line, which is NOT the same as this package
#: refusing the work. Both exit 2 -- `2` means *could not complete* here -- so
#: the exit code alone cannot tell a documented command that does not parse from
#: one that parsed and honestly declined. Found by mutation: adding an unknown
#: flag to a documented command left this file green, because argparse exits with
#: a code the exit contract calls legitimate. A real decline says `REFUSED` and
#: names the file; argparse prints a usage banner.
ARGPARSE_REJECTED = re.compile(r"^usage: ", re.MULTILINE)


def _lines():
    """Every command the README prints, with continuations joined."""
    out = []
    for block in re.findall(r"```[a-z]*\n(.*?)```", README.read_text("utf-8"),
                            re.S):
        joined, pending = [], ""
        for raw in block.splitlines():
            line = raw.strip()
            if not line:
                continue
            if pending:
                line = pending + " " + line
                pending = ""
            if line.endswith("\\"):
                pending = line[:-1].strip()
                continue
            joined.append(line)
        if pending:                      # a continuation with nothing after it
            joined.append(pending)
        out += joined
    return out


def _cli_commands():
    """The documented invocations, paired with the exit code the page promises."""
    found = []
    for line in _lines():
        if CLI not in line and not line.startswith("factory-line-audit"):
            continue
        exit_code = DOCUMENTED_EXIT.search(line)
        command = line.split("#", 1)[0].strip()
        found.append((command, int(exit_code.group(1)) if exit_code else None,
                      command.startswith(WITH_EXTRAS)))
    return found


class TestTheReadmePrintsCommandsAtAll:

    def test_there_are_commands_to_run(self):
        """Every claim below is over this list, and a renamed fence or a
        reformatted block empties it silently -- which is this whole file
        passing while documenting nothing."""
        found = _cli_commands()
        assert len(found) >= 4, (
            f"only {len(found)} documented command(s) parsed out of the README: "
            f"{[c for c, _, _ in found]}. The block was renamed or reformatted, "
            f"and nothing below is running anything")

    def test_the_continuations_were_joined(self):
        """A half-command fails for a reason that has nothing to do with the
        documentation, and reads as a real defect."""
        broken = [c for c, _, _ in _cli_commands() if c.endswith("\\")]
        assert not broken, f"these were never joined: {broken}"

    def test_the_page_promises_some_exit_codes(self):
        """The strongest assertion here reads a number off the page. If the
        annotations go, this quietly becomes a smoke test."""
        promised = [c for c, code, _ in _cli_commands() if code is not None]
        assert len(promised) >= 2, (
            f"the README annotates {len(promised)} command(s) with an exit "
            f"code; this file's sharpest check has nothing to read")


def _runnable(command: str, scratch: str) -> str:
    """The page's command, with the interpreter it names swapped for this one
    and its scratch paths pointed somewhere private.

    **The order matters and getting it wrong is silent.** `sys.executable` in a
    virtualenv is itself under `/tmp/`, so rewriting `/tmp/` across the whole
    line rewrote the interpreter's own path too. Every command then returned
    127 and this file reported that the README printed commands that do not
    work -- a check firing precisely, at high confidence, against the wrong
    subject. Substitute the head, then the remainder; never the whole line.
    """
    head, _, tail = command.partition(" ")
    if INTERPRETER.match(head):
        head = sys.executable
    return head + " " + tail.replace("/tmp/", scratch + "/")


class TestEveryDocumentedCommandRuns:

    def _run(self, commands, tmp_path):
        """Run them in order and in one scratch directory, because they chain.

        `draft` writes a file `gate` is then documented to refuse by name. Run
        independently, `gate` would be refused for a missing file -- the right
        exit code for the wrong reason, which is a pass this suite does not want.
        """
        environment = dict(os.environ, PYTHONPATH=os.path.join(str(ROOT), "src"))
        failures = []
        for command, promised, _ in commands:
            runnable = _runnable(command, str(tmp_path))
            proc = subprocess.run(runnable, shell=True, capture_output=True,
                                  text=True, cwd=str(ROOT), env=environment,
                                  timeout=300)
            if "Traceback" in proc.stderr:
                failures.append(f"{command}\n    raised: "
                                f"{proc.stderr.strip().splitlines()[-1]}")
                continue
            if ARGPARSE_REJECTED.search(proc.stderr):
                failures.append(f"{command}\n    argparse refused it: "
                                f"{proc.stderr.strip().splitlines()[-1]}")
                continue
            # An UNANNOTATED command is a promise that it works. The page
            # annotates exactly the two it expects to refuse, which is why the
            # annotation exists at all -- so silence means zero.
            #
            # Accepting any of 0/1/2 here was too weak, and mutation showed it:
            # pointing a documented command at a file that does not exist left
            # this green, because *could not complete* is a legitimate code.
            expected = 0 if promised is None else promised
            if proc.returncode != expected:
                failures.append(
                    f"{command}\n    "
                    + (f"the page promises exit {promised} and it returned "
                       f"{proc.returncode}" if promised is not None else
                       f"returned {proc.returncode}; the page prints it "
                       f"unqualified, which promises it works")
                    + (f"\n    it said: {proc.stderr.strip().splitlines()[-1]}"
                       if proc.stderr.strip() else ""))
        return failures

    def test_the_page_runs_stage_one_on_a_bare_interpreter(self, tmp_path):
        """The page's own claim, exercised: these are printed under a plain
        `python3`, and Stage 1 declares no dependency at all."""
        bare = [c for c in _cli_commands() if not c[2]]
        assert len(bare) >= 3, f"only {len(bare)} bare command(s) found"
        failures = self._run(bare, tmp_path)
        assert not failures, ("the README prints commands that do not do what "
                              "it says:\n  " + "\n  ".join(failures))

    def test_the_page_runs_stage_two_in_the_environment_it_builds(self, tmp_path):
        """The other interpreter. The page installs the extras before printing
        these, so judging them without the engine would test the environment
        rather than the page -- and it did, until this was split."""
        pytest.importorskip("arbiter_engine",
                            reason="the page installs the [detect] extra before "
                                   "printing these; without it this would judge "
                                   "the environment rather than the README")
        staged = [c for c in _cli_commands() if c[2]]
        assert staged, "no command is printed under the page's own virtualenv"
        failures = self._run(staged, tmp_path)
        assert not failures, ("the README prints commands that do not do what "
                              "it says:\n  " + "\n  ".join(failures))


    def test_the_argparse_check_can_tell_the_two_refusals_apart(self):
        """Non-vacuity for the rule above, in both directions: it must see a
        usage banner and must not see this package declining honestly."""
        assert ARGPARSE_REJECTED.search(
            "usage: factory-line-audit [-h]\nerror: unrecognized arguments")
        assert not ARGPARSE_REJECTED.search(
            "REFUSED /tmp/d.json: declaration is unreviewed")


class TestEveryScriptTheReadmeNamesExists:
    """The lines this cannot run -- the battery scripts and the pin sweep, which
    install releases and take minutes -- are still claims about paths. A page
    naming a script that was renamed sends a reader to a `No such file`."""

    def _scripts(self):
        found = set()
        for line in _lines():
            for token in line.split():
                if token.endswith(".py") and "/" in token:
                    found.add(token)
        return sorted(found)

    def test_it_found_scripts_to_check(self):
        assert len(self._scripts()) >= 3, (
            f"only {self._scripts()} parsed; the README names several battery "
            f"scripts, so this is reading the wrong thing")

    def test_every_named_script_is_there(self):
        missing = [s for s in self._scripts() if not (Path(ROOT) / s).exists()]
        assert not missing, f"the README names scripts that do not exist: {missing}"


#: Top-level directories this repository actually has. A backticked token whose
#: first segment is one of these is a claim ABOUT THIS REPOSITORY; `out/walk.json`
#: and `~/line1/` are not, and are left alone.
TRACKED_ROOTS = ("battery", "src", "tests", "examples", "tools", ".github")
_SUFFIXES = (".py", ".json", ".md", ".yml", ".yaml", ".toml", ".cfg", ".txt")


class TestEveryRepositoryPathTheDocumentsNameExists:
    """R5 from the 0.1.7 review: `engine_floars.json` moved into the package and
    two documents went on naming the old place.

    The sibling class above parses RUNNABLE lines for `.py` tokens, so neither
    stale line was reachable by it: one was prose, and both named a `.json`. A
    rule is only as wide as the surfaces it is run against.

    Both documents, because the two stale lines were one in each.
    """

    DOCS = ("README.md", "FINDINGS.md")

    def _named(self, doc):
        body = (Path(ROOT) / doc).read_text(encoding="utf-8")
        found = set()
        for token in re.findall(r"`([^`\n]+)`", body):
            token = token.strip().rstrip(".,;:)")
            if "/" not in token or token.startswith(("http", "~", "/")):
                continue
            if not token.startswith(TRACKED_ROOTS):
                continue
            if token.endswith("/") or token.endswith(_SUFFIXES):
                found.add(token)
        return sorted(found)

    @pytest.mark.parametrize("doc", DOCS)
    def test_it_found_paths_to_check(self, doc):
        """Non-vacuity, per document. An empty set satisfies the rule below."""
        assert len(self._named(doc)) >= 2, (
            f"{doc}: only {self._named(doc)} parsed as repository paths")

    @pytest.mark.parametrize("doc", DOCS)
    def test_every_named_path_is_there(self, doc):
        missing = [p for p in self._named(doc)
                   if not (Path(ROOT) / p.rstrip("/")).exists()]
        assert not missing, f"{doc} names paths that do not exist: {missing}"

    def test_the_floors_file_is_named_where_it_lives(self):
        """The instance, held by behaviour rather than by the absence of a
        string: the file the battery reads and the file the documents name have
        to be one file."""
        from factory_line_audit.cli import _floors
        for doc in self.DOCS:
            body = (Path(ROOT) / doc).read_text(encoding="utf-8")
            if "engine_floors.json" not in body:
                continue
            named = {p for p in self._named(doc) if p.endswith("engine_floors.json")}
            assert named, f"{doc} names engine_floors.json by an untracked path"
            for path in named:
                assert (Path(ROOT) / path).exists(), path
        assert _floors(None)["floors"], "the package copy carries no floors"
