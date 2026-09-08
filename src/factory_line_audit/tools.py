"""The tool surface: a spec table and a dispatcher, and nothing else.

BRIDGES on the tool surface. Two rules shape this file and both are about what
is NOT here.

**No protocol import.** Not `mcp`, not a server SDK, not a transport. The table
and the dispatcher are plain data and a plain function, so the closure test runs
where no SDK is installed -- and the dispatcher the protocol advertises is
literally the one the test walks.

**No second code path.** Every tool routes through `cli.main`. A parallel
implementation gets a parallel suite, and on the day the two disagree both are
still green.

**First contact is deliberately absent.** There is no tool that reaches a live
OPC UA server. It takes credentials, it touches something real, and a surface
that simply does not offer it is a better boundary than a paragraph asking an
assistant not to. That absence is asserted by the closure test, so removing it
is a visible change rather than a quiet one.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .exit_contract import MEANING, normalise

#: name -> what it does, which CLI verb it becomes, and which arguments it takes.
#: `argv` is a template: each entry is either a literal flag or a parameter name
#: in braces. The dispatcher fills them, and refuses a parameter it was not given.
SPEC: Dict[str, Dict[str, Any]] = {
    "presence": {
        "summary": "Stage 1. Classify every declared tag as reading, present "
                   "but not reading, or absent. Runs with no engine installed.",
        "verb": "presence",
        "argv": ["presence", "--register", "{register}", "--walk", "{walk}"],
        "required": ["register", "walk"],
    },
    "draft_declarations": {
        "summary": "Propose the operator statements this register needs. The "
                   "output is UNREVIEWED and the gate will refuse it.",
        "verb": "draft",
        "argv": ["draft", "--register", "{register}", "--out", "{out}"],
        "required": ["register", "out"],
    },
    "gate_declarations": {
        "summary": "Refuse an unreviewed or malformed declaration file, by name.",
        "verb": "gate",
        "argv": ["gate", "--register", "{register}", "{declarations}"],
        "required": ["register", "declarations"],
    },
    "generate_model": {
        "summary": "Emit the domain model and the manifest of everything "
                   "excluded from it, as a pair.",
        "verb": "generate",
        "argv": ["generate", "--register", "{register}", "--declarations",
                 "{declarations}", "--model-out", "{model_out}",
                 "--manifest-out", "{manifest_out}"],
        "required": ["register", "declarations", "model_out", "manifest_out"],
    },
    "detect": {
        "summary": "Stage 2. Feed the engine and return the verdict, the "
                   "declines by class, and what was never established.",
        "verb": "detect",
        "argv": ["detect", "--register", "{register}", "--walk", "{walk}",
                 "--declarations", "{declarations}"],
        "required": ["register", "walk", "declarations"],
    },
    "read_attestation": {
        "summary": "Re-report a stored attestation through the same front door.",
        "verb": "attest",
        "argv": ["attest", "{attestation}"],
        "required": ["attestation"],
    },
}

#: Tools this surface deliberately does not offer, and why. Enumerated so that
#: the closure test can assert the absence rather than the absence being an
#: omission nobody wrote down.
WITHHELD = {
    "connect_to_plc": "First contact. A credentialed reach into a live PLC or "
                      "OPC UA server is an act, not a call. It stays with a "
                      "person, and a refusal is a better boundary than a "
                      "paragraph asking nicely.",
    "review_declarations": "A rule cannot know an operator-knowledge fact. "
                           "Marking a declaration reviewed is the one thing "
                           "this package must never automate.",
}


def dispatch(name: str, arguments: Optional[Dict[str, Any]] = None,
             runner: Optional[Callable[[List[str]], int]] = None) -> Dict[str, Any]:
    """Route one tool call through the CLI and answer with the exit code.

    Every result carries `exit` and `verdict` explicitly. A transport that
    successfully delivered a message about a run that could not complete has
    succeeded at being a transport and done nothing else -- left implicit, 2 is
    read as clean by whoever is reading.
    """
    arguments = dict(arguments or {})
    if name in WITHHELD:
        return _answer(2, name, argv=None,
                       error=f"{name} is deliberately not offered: "
                             f"{WITHHELD[name]}")
    spec = SPEC.get(name)
    if spec is None:
        return _answer(2, name, argv=None,
                       error=f"unknown tool {name!r}; this surface offers "
                             f"{sorted(SPEC)}")
    missing = [key for key in spec["required"] if arguments.get(key) is None]
    if missing:
        return _answer(2, name, argv=None,
                       error=f"{name} needs {missing}")
    argv: List[str] = []
    for token in spec["argv"]:
        if token.startswith("{") and token.endswith("}"):
            value = arguments[token[1:-1]]
            argv.extend(value if isinstance(value, list) else [str(value)])
        else:
            argv.append(token)
    if runner is None:
        from .cli import main as runner  # imported here: the table stays plain data
    code, raw = normalise(runner(argv))
    return _answer(code, name, argv=argv, raw=raw)


def _answer(code: int, name: str, argv, error: str = "", raw=None) -> Dict[str, Any]:
    body = {"tool": name, "exit": code, "verdict": MEANING[code], "argv": argv}
    if error:
        body["error"] = error
    if raw is not None and raw != code:
        body["raw_exit"] = raw
    return body
