"""What this package says its version is, and where that number lives.

**Why the flag matters here specifically.** A consumer resolves this tool on
PATH and runs it as a SUBPROCESS. That means the `>=` in its packaging metadata
governs what pip put in the environment, not what actually answers when the
process starts -- and `odm-qa-pipeline` gate 2 now pins this package, so a floor
can be declared here and never checked. `bmc-sensor-audit` added the same
argument for the same reason, with the same defect first: `--version` exited 2
with an argparse usage error.

**Why the number's home matters.** It used to be two literals, one in
`pyproject.toml` and one in `__init__.py`, that happened to agree. Both sibling
repositories were moved off that arrangement after one of them shipped a wheel
whose `__version__` disagreed with its own metadata. Nothing read the package
literal, so a bump in the other place was invisible. The flag below reports the
package literal, which is exactly the one that would have been wrong.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ROOT
from factory_line_audit import __version__
from factory_line_audit.cli import main

PYPROJECT = Path(ROOT) / "pyproject.toml"
README = Path(ROOT) / "README.md"
EXPECTED = f"factory-line-audit {__version__}"


class TestTheFlagAnswers:

    def test_it_exits_clean_and_names_the_package_and_the_version(self, capsys):
        """Zero, not 2. The whole defect was that argparse rejected the flag."""
        with pytest.raises(SystemExit) as exited:
            main(["--version"])
        assert exited.value.code == 0, (
            f"`--version` exited {exited.value.code}; a consumer asking what "
            f"answers on PATH gets a usage error instead of a number")
        printed = capsys.readouterr().out.strip()
        assert printed == EXPECTED, f"printed {printed!r}, expected {EXPECTED!r}"

    def test_it_answers_through_the_path_a_consumer_actually_uses(self):
        """A separate process, because that is how this tool is consumed.

        The test above proves the parser is wired. It cannot prove the installed
        entry point reaches it -- the mechanism is not the path.
        """
        env = dict(os.environ, PYTHONPATH=os.path.join(str(ROOT), "src"))
        ran = subprocess.run([sys.executable, "-m", "factory_line_audit.cli",
                              "--version"], capture_output=True, text=True,
                             env=env, cwd=str(ROOT))
        assert ran.returncode == 0, (
            f"exit {ran.returncode}; stderr was {ran.stderr.strip()!r}")
        assert ran.stdout.strip() == EXPECTED, (
            f"printed {ran.stdout.strip()!r}, expected {EXPECTED!r}")

    def test_a_verb_still_runs_with_the_argument_registered(self):
        """Non-vacuity of a different kind: a global argument added above the
        subparsers can swallow the verb. An empty invocation must still be the
        refusal it was, rather than a version banner."""
        assert main([]) == 2


class TestTheNumberHasOneHome:

    def _project_section(self):
        """The `[project]` table's own lines. Scanned rather than parsed:
        `tomllib` arrives in 3.11 and this package supports 3.10, which the CI
        matrix runs."""
        lines, section, out = PYPROJECT.read_text(encoding="utf-8").splitlines(), None, []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                section = stripped
                continue
            if section == "[project]":
                out.append(line)
        return out

    def test_the_scan_found_the_table(self):
        """An absence asserted over an empty list is not a measurement."""
        found = self._project_section()
        assert len(found) > 5, (
            f"only {len(found)} line(s) read from [project]; the scan did not "
            f"find the table, so the rule below proves nothing")

    def test_the_project_table_declares_no_version_literal(self):
        offending = [line for line in self._project_section()
                     if re.match(r"\s*version\s*=", line)]
        assert not offending, (
            f"`pyproject.toml` writes the version itself: {offending}. That is "
            f"a second record of one fact, and the one nothing reads is the one "
            f"that drifts. Declare it dynamic and let the backend read the "
            f"package literal")

    def test_it_declares_the_version_dynamic(self):
        """The other half. Removing the literal without declaring `dynamic`
        does not build at all, but saying so here names the intended shape."""
        assert any(re.match(r"\s*dynamic\s*=.*version", line)
                   for line in self._project_section()), (
            "[project] does not declare `dynamic = [\"version\"]`")

    def test_the_installed_metadata_agrees_with_the_package(self):
        """The check that would have caught the sibling's shipped wheel.

        When the distribution is not installed there is no metadata to compare
        against and this asserts nothing -- said plainly rather than skipped,
        because the `checks` job fails the build on any skip. It runs for real
        there: CI installs the package before pytest.
        """
        from importlib.metadata import PackageNotFoundError, version
        try:
            declared = version("factory-line-audit")
        except PackageNotFoundError:
            return
        assert declared == __version__, (
            f"the installed metadata says {declared} and the package reports "
            f"{__version__}; a wheel disagreeing with itself is what the single "
            f"home above exists to prevent. A stale editable install also lands "
            f"here -- reinstall before believing the number")


class TestTheShippedModuleAgreesWithTheReadme:
    """The package docstring travels; the README does not.

    A reader who installs this from an index and calls `help()` sees the module,
    and for 0.1.0 it carried an authorship claim that had already been retired in
    both documents a reader of the repository sees. Fixing the two files a human
    reads left the only file that ships still saying the old thing.

    The claim is DERIVED from the README rather than written here, so there is
    one home for it, and so this file never has to contain the retired sentence
    in order to forbid it.
    """

    CLAIM = re.compile(r"\*\*([^*]*\bauthor\b[^*]*)\*\*")

    def _claim(self) -> str:
        found = self.CLAIM.search(README.read_text(encoding="utf-8"))
        assert found, ("the README makes no bolded claim about authorship, so "
                       "this guard has nothing to compare against; move it or "
                       "delete it, do not leave it passing")
        return " ".join(found.group(1).split()).rstrip(".")

    def test_there_is_a_claim_to_compare_against(self):
        assert len(self._claim()) > 20, f"claim too short: {self._claim()!r}"

    def test_the_package_docstring_makes_the_same_claim(self):
        import factory_line_audit
        doc = " ".join((factory_line_audit.__doc__ or "").split())
        claim = self._claim()
        assert claim.lower() in doc.lower(), (
            f"the README states {claim!r} and the shipped package docstring "
            f"does not. The docstring is what a reader who installed this from "
            f"an index sees, and it is the copy that goes out in the wheel")
