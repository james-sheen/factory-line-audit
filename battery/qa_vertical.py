#!/usr/bin/env python3
"""`factory-line-audit` as a `qa-orchestrator` vertical: a tier and a referee.

**Why this is in `battery/` and not in `src/`.** The tier serves OPC UA by
running `opcua_surface.py`, which is part of the verification apparatus and is
not in the wheel. A shipped module that shells out to a file no install carries
would be broken for every consumer. The core's plugin loader takes
`--plugin path/to/file.py`, so this needs no entry point and no new
distribution:

    qa-orchestrator check SCENARIO --plugin battery/qa_vertical.py

**Everything below was measured against the installed wheel before it was
written**, because the brief that proposed this vertical had never run any of
it. Its three constructor calls all raise on 0.3.2: `Verb` is missing the
required `describe`, `ReportSchema` has no `names` field (it is `subject`), and
`Tool` is missing `install_hint`, `capture_argv` and `judge_argv`. Its `modes`
was a dict of argv templates; the field is a tuple of mode NAMES and argv comes
from two callables.

**No verbs are registered, and that is measured rather than saved effort.** The
core ships `disable`, `drive`, `fail`, `remove` and `set`, and each maps onto a
method of the `Substrate` protocol this tier implements. The brief proposed five
more; four are expressible as `drive` over a series, and the fifth is named
`drift`, which is already an alias of `set` -- `register_verb` refuses it:
*verb 'drift' is already defined*.

**What is NOT yet judgeable, and why nothing here pretends otherwise.** This
tool keeps its findings at `checked.findings_verbatim`. `ReportSchema.checked`
is read with a dotted path and reaches its neighbour `checked.invariants_attempted`
fine; `findings` is read with a plain `.get()` and cannot. So a scenario
asserting on findings would see none and pass. Filed upstream as
`qa-orchestrator` #1. `test_qa_vertical.py` carries a tripwire that goes red the
day it is answered, so this comment cannot outlive its own fix.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SURFACE = os.path.join(HERE, "opcua_surface.py")
REGISTER = os.path.join(ROOT, "examples", "asset_register.json")
CORPUS = os.path.join(HERE, "corpus", "clean.json")

#: The tier's handle carries two things, because `capture_argv` is handed
#: `(target, out)` and nothing else -- and this tool's `capture` REQUIRES a
#: `--register`. The protocol says the handle is "a URL, a path, a DSN --
#: whatever the referee is pointed at. The harness does not interpret it", and
#: both ends of it live in this file, so carrying the register in it is within
#: the contract rather than around it.
HANDLE_SEPARATOR = "#register="

#: A quality word a real server sends for a node that is present and unreadable.
UNREADABLE = "BadDeviceFailure"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class FactoryOpcUaSubstrate:
    """A real OPC UA server, serving a walk this class mutates.

    The fault verbs edit the walk the surface replays rather than reaching into
    a running server: a tag that was removed is one no sample carries, and a
    disabled one is a node the server answers for with a Bad status. That is
    what those two look like on a line, and it is what Stage 1 has to tell
    apart.
    """

    NAME = "factory-opcua"
    name = NAME

    def __init__(self, setup: dict | None = None) -> None:
        setup = setup or {}
        self.register = str(setup.get("register", REGISTER))
        with open(setup.get("walk", CORPUS), encoding="utf-8") as handle:
            self._walk = json.load(handle)
        self._workdir = tempfile.mkdtemp(prefix="fla-qa-tier-")
        self._server: subprocess.Popen | None = None
        self._port: int | None = None

    # ---------------------------------------------------------- the protocol
    def start(self) -> str:
        """Serve the current walk and return the handle the referee reads.

        Called before EVERY capture, so an injection between captures is
        actually served. The previous server is taken down first: leaving it up
        would answer from the walk as it was before the fault.
        """
        self.stop()
        walk_path = os.path.join(self._workdir, "walk.json")
        with open(walk_path, "w", encoding="utf-8") as handle:
            json.dump(self._walk, handle)
        ready = os.path.join(self._workdir, "ready.json")
        if os.path.exists(ready):
            os.unlink(ready)
        self._port = _free_port()
        self._server = subprocess.Popen(
            [sys.executable, SURFACE, "serve", "--port", str(self._port),
             "--walk", walk_path, "--ready", ready],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        for _ in range(120):
            if os.path.exists(ready):
                break
            if self._server.poll() is not None:
                raise RuntimeError(
                    f"the surface exited {self._server.returncode} before "
                    f"serving: {(self._server.stderr.read() or '')[-300:]}")
            time.sleep(0.5)
        else:
            self.stop()
            raise RuntimeError("the surface never announced a working pass")
        endpoint = f"opc.tcp://127.0.0.1:{self._port}/factory-line-audit/"
        return f"{endpoint}{HANDLE_SEPARATOR}{self.register}"

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.terminate()
        try:
            self._server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self._server.kill()
        self._server = None

    def remove(self, entity: str) -> None:
        for sample in self._walk["samples"]:
            sample["nodes"].pop(entity, None)

    def disable(self, entity: str) -> None:
        for sample in self._walk["samples"]:
            cell = sample["nodes"].get(entity)
            if cell is not None:
                cell["q"], cell["v"] = UNREADABLE, None

    def fail(self, region: str, status: Any) -> None:
        """A region here is a node-id prefix, and the status is the word the
        server answers with. Both are this tier's own terms, which is what the
        protocol says they are."""
        word = str(status or UNREADABLE)
        for sample in self._walk["samples"]:
            for node, cell in sample["nodes"].items():
                if node.startswith(region):
                    cell["q"], cell["v"] = word, None

    def set_value(self, entity: str, value: Any) -> None:
        for sample in self._walk["samples"]:
            cell = sample["nodes"].get(entity)
            if cell is not None:
                cell["v"] = value

    def state(self, entity: str) -> str:
        """What the substrate looks like NOW, in the core's three words.

        Graded with the tool's OWN grader rather than by matching quality
        strings here. A second opinion about what counts as readable is a second
        thing to keep in step, and the one that drifts is the copy nobody runs.
        """
        sys.path.insert(0, os.path.join(ROOT, "src"))
        from factory_line_audit.presence import grade

        seen = [sample["nodes"][entity] for sample in self._walk["samples"]
                if entity in sample["nodes"]]
        if not seen:
            return "absent"
        if any(grade(cell.get("q"))[1]["usable"] for cell in seen):
            return "reading"
        return "disabled"


# ------------------------------------------------------------------ referee
def _capture_argv(target: str, out: Path) -> tuple[str, ...]:
    """`capture --register R --target E --out W --print-digest`.

    The register comes out of the handle because the signature has no other
    channel for it, and this tool cannot capture without one.
    """
    endpoint, _, register = target.partition(HANDLE_SEPARATOR)
    if not register:
        raise ValueError(
            f"the handle {target!r} carries no register. This tier writes one "
            f"into every handle it returns, so this target came from somewhere "
            f"else -- probably another vertical's tier")
    return ("capture", "--register", register, "--target", endpoint,
            "--out", str(out), "--print-digest")


def _judge_argv(mode: str, configs: Sequence[str],
                captures: Sequence[Path]) -> tuple[str, ...]:
    """`<mode> --register R --walk W [--declarations D...]`.

    The FIRST config is the register and the rest are declarations, which is
    the order this tool's own quick start prints them in.
    """
    if not configs:
        raise ValueError(f"{mode} needs a register as its first config")
    argv = [mode, "--register", str(configs[0])]
    for capture in captures:
        argv += ["--walk", str(capture)]
    if mode == "detect" and len(configs) > 1:
        argv.append("--declarations")
        argv += [str(c) for c in configs[1:]]
    return tuple(argv)


FACTORY_LINE_AUDIT_REPORT = None       # filled in below, after referee imports


def _schema(referee):
    """DERIVED from reports this tool wrote, never from plausible names.

    Run `presence` and `detect --json` and read the keys off the output. The
    reference vertical in this core guessed `("finding", "message")` for its
    text field, the tool emits `detail`, and every text expectation in three
    shipped scenarios failed silently against it.

    * `checked` -- `checked.invariants_attempted` exists and a dotted path
      reaches it.
    * `findings` -- `checked.findings_verbatim` is where they are. A dotted path
      does NOT reach it today; `qa-orchestrator` #1.
    * `subject` -- an attestation finding names `entity_id`; a presence row
      names `asset` and `tag`.
    * `text` -- an attestation finding carries `reason` and `problem_type`.
    * `declines` -- deliberately None. This tool reports declines as COUNTS
      (`declined.total`, `declined.by_class`) and not as a list, and pointing a
      list-shaped field at a dict would read as *no declines* forever.
    """
    return referee.ReportSchema(
        findings="checked.findings_verbatim",
        subject=("entity_id", "asset", "tag"),
        text=("reason", "problem_type"),
        checked="checked.invariants_attempted",
        declines=None)


def _tool(referee):
    return referee.Tool(
        name="factory-line-audit",
        executable="factory-line-audit",
        install_hint="pip install 'factory-line-audit[detect,live]'",
        modes=("presence", "detect"),
        capture_argv=_capture_argv,
        validate_argv=lambda path: ("validate-walk", str(path)),
        judge_argv=_judge_argv,
        json_argv=lambda mode: ("--json",) if mode == "detect" else None,
        report=_schema(referee),
        digest_pattern=r"\bsha256:[0-9a-f]{64}\b",
        configs_are_paths=True)


def register() -> str:
    from qa_orchestrator import referee, substrate

    substrate.register(FactoryOpcUaSubstrate.NAME, FactoryOpcUaSubstrate)
    referee.register_tool(_tool(referee))
    return (f"referee factory-line-audit (modes presence, detect); "
            f"tier {FactoryOpcUaSubstrate.NAME}; no verbs added -- the five the "
            f"core ships map onto this tier")


def unregister() -> None:
    from qa_orchestrator import referee, substrate

    substrate.unregister(FactoryOpcUaSubstrate.NAME)
    referee.unregister_tool("factory-line-audit")
