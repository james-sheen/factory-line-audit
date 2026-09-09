"""The front door. Every verb, and every refusal, arrive through here.

BRIDGES on the tool surface: it routes through the CLI rather than beside it, so
there is one implementation to test. That only works if the CLI is the single
place a verdict becomes an exit code -- which is what `main` is.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

from . import formats
from .exit_contract import CLEAN, FINDINGS, INCOMPLETE, MEANING

#: Every refusal class this package defines, named. Enumerated rather than
#: discovered so that the suite can walk the list, and so that adding a refusal
#: without considering its test is a visible omission rather than a silent one.
REFUSALS = {
    "no_such_file": "an input path does not exist",
    "not_json": "an input is not JSON",
    "not_an_object": "an input is JSON but not an object",
    "no_format_field": "an input carries no format field",
    "wrong_artifact": "an input is a different artifact of this package",
    "wrong_major": "an input is a later major of the right artifact",
    "register_empty": "the register declares no assets",
    "register_duplicate_asset": "the register declares one asset twice",
    "register_no_type": "an asset carries no type",
    "register_unknown_tag_class": "a tag declares a class this package does not know",
    "register_no_node": "a tag carries no node id",
    "declaration_unreviewed": "a declaration file has not been reviewed",
    "declaration_fixture_without_disclosure":
        "a file claims fixture status without disclosing it in reviewed_by",
    "declaration_malformed": "a declaration statement is missing a required field",
    "engine_absent": "Stage 2 was asked for and the engine is not installed",
    "hard_stop": "a condition under which no verdict may be reported",
    "unknown_verb": "a verb this front door does not implement",
}


def _out(text: str) -> None:
    """Write, and survive a reader walking away.

    BRIDGES battery, `pipe`: a reader closing the pipe must not change the
    verdict and must not print anything. Python's default is a
    BrokenPipeError traceback on stderr at interpreter shutdown, which is both.
    """
    try:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
    except BrokenPipeError:
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass


def _load_walk(path: str) -> Dict[str, Any]:
    return formats.load(path, formats.WALK)


def _presence(args) -> tuple:
    from .presence import classify, load_register
    register = load_register(args.register)
    walk = _load_walk(args.walk)
    return register, walk, classify(register, walk)


def cmd_presence(args) -> int:
    _, _, presence = _presence(args)
    if args.out:
        formats.dump(args.out, presence)
    _out(json.dumps(presence, indent=2))
    return presence["exit"]


def cmd_draft(args) -> int:
    from .declarations import draft
    from .presence import load_register
    body = draft(load_register(args.register))
    if args.out:
        formats.dump(args.out, body)
        _out(f"wrote {len(body['statements'])} unreviewed statements to {args.out}")
    else:
        _out(json.dumps(body, indent=2))
    return CLEAN


def cmd_validate_walk(args) -> int:
    """Stage 1: no engine, no core, no server. A receiver checking a file.

    A malformed walk is INCOMPLETE and never FINDINGS: a file that could not be
    read is not a finding about the line.
    """
    from .walkcheck import observations, validate_walk
    try:
        with open(args.walk, encoding="utf-8") as handle:
            payload = json.load(handle)
    except OSError as unreadable:
        _out(f"  COULD NOT COMPLETE: cannot read {args.walk}: {unreadable}")
        _out(f"OUTCOME exit={INCOMPLETE} verdict={MEANING[INCOMPLETE]}")
        return INCOMPLETE
    except json.JSONDecodeError as malformed:
        _out(f"  COULD NOT COMPLETE: {args.walk} is not JSON: {malformed}")
        _out(f"OUTCOME exit={INCOMPLETE} verdict={MEANING[INCOMPLETE]}")
        return INCOMPLETE

    problems = validate_walk(payload)
    notes = observations(payload) if isinstance(payload, dict) else []
    code = INCOMPLETE if problems else CLEAN
    if args.json:
        _out(json.dumps({"walk": args.walk, "problems": problems,
                         "observations": notes}, indent=2))
    else:
        for problem in problems:
            _out(f"  {problem}")
        for note in notes:
            _out(f"  note: {note}")
        if not problems:
            _out(f"  {args.walk} is a well-formed walk")
    _out(f"OUTCOME exit={code} verdict={MEANING[code]}")
    return code


def cmd_regression(args) -> int:
    from .regression import compare, render
    code, body = compare(args.before, args.after, args.rename)
    if args.json:
        _out(json.dumps(body, indent=2))
    else:
        _out(render(body))
    _out(f"OUTCOME exit={code} verdict={MEANING[code]}")
    return code


def cmd_gate(args) -> int:
    from .declarations import gate
    from .presence import load_register
    register = load_register(args.register)
    result = gate(args.declarations, register)
    for review in result["reviews"]:
        _out(f"{review['path']}: {review['status']} "
             f"({review['statements']} statements)")
    return CLEAN


def _generate(args):
    from .declarations import gate
    from .generator import build
    from .presence import load_register
    register = load_register(args.register)
    gated = gate(args.declarations or [], register)
    model_text, manifest = build(register, gated)
    return register, gated, model_text, manifest


def cmd_generate(args) -> int:
    _, _, model_text, manifest = _generate(args)
    if args.model_out:
        with open(args.model_out, "w", encoding="utf-8") as handle:
            handle.write(model_text)
    if args.manifest_out:
        formats.dump(args.manifest_out, manifest)
    if not args.model_out and not args.manifest_out:
        _out(model_text)
        _out(json.dumps(manifest, indent=2))
    else:
        counts = manifest["counts"]
        _out(f"{counts['indicators']} indicators over "
             f"{counts['assets_modelled']} assets; "
             f"{counts['exclusions']} exclusions named in the manifest")
    return CLEAN


def _floors(path: Optional[str]) -> Dict[str, Any]:
    candidate = path or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "battery", "engine_floors.json")
    if os.path.exists(candidate):
        with open(candidate, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return {}


def cmd_detect(args) -> int:
    from .feeder import HardStop, run
    from .presence import classify
    from .report import attestation, human
    register, gated, model_text, manifest = _generate(args)
    walk = _load_walk(args.walk)
    presence = classify(register, walk)
    result = run(model_text, register, presence, walk, gated, manifest,
                 floors=_floors(args.floors))
    att = attestation(register=register, presence=presence, manifest=manifest,
                      result=result, model_text=model_text,
                      declaration_paths=list(args.declarations or []),
                      walk_path=args.walk, register_path=args.register)
    if args.attest_out:
        formats.dump(args.attest_out, att)
    if args.json:
        _out(json.dumps(att, indent=2))
    else:
        _out(human(att))
    return att["exit"]


def cmd_attest(args) -> int:
    """Read back an attestation and re-report its verdict.

    The same front door, so the battery's `attest` leg exercises the artifact
    rather than a second reader of it.
    """
    from .report import human
    att = formats.load(args.attestation, formats.ATTEST)
    _out(human(att))
    return att["exit"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="factory-line-audit",
        description="A bridge from a discrete-manufacturing line to "
                    "arbiter-engine. Stage 1 needs nothing installed.")
    subs = parser.add_subparsers(dest="verb")

    def register_arg(sub):
        sub.add_argument("--register", required=True)

    p = subs.add_parser("presence", help="Stage 1: what exists and what reads")
    register_arg(p); p.add_argument("--walk", required=True)
    p.add_argument("--out"); p.set_defaults(fn=cmd_presence)

    p = subs.add_parser("draft", help="propose declarations, unreviewed")
    register_arg(p); p.add_argument("--out"); p.set_defaults(fn=cmd_draft)

    p = subs.add_parser("gate", help="refuse unreviewed declarations by name")
    register_arg(p); p.add_argument("declarations", nargs="+")
    p.set_defaults(fn=cmd_gate)

    p = subs.add_parser("generate", help="model and manifest, as a pair")
    register_arg(p); p.add_argument("--declarations", nargs="*")
    p.add_argument("--model-out"); p.add_argument("--manifest-out")
    p.set_defaults(fn=cmd_generate)

    p = subs.add_parser("detect", help="Stage 2: feed the engine, report, exit")
    register_arg(p); p.add_argument("--walk", required=True)
    p.add_argument("--declarations", nargs="*")
    p.add_argument("--attest-out"); p.add_argument("--floors")
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_detect)

    p = subs.add_parser("attest", help="re-report a stored attestation")
    p.add_argument("attestation"); p.set_defaults(fn=cmd_attest)

    p = subs.add_parser("validate-walk",
                        help="everything wrong with a walk file, or nothing")
    p.add_argument("walk")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_validate_walk)

    p = subs.add_parser("regression", help="two walks of one line, oldest first")
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p.add_argument("--rename", action="append", nargs=2, default=[],
                   metavar=("OLD", "NEW"),
                   help="a prefix move somebody signed for, as two arguments. "
                        "Repeatable. Two and not OLD=NEW because every OPC UA "
                        "node id contains an equals sign. A shift nobody "
                        "declared is REPORTED and never applied")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_regression)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """The only place a verdict becomes an exit code.

    Every exception path lands here. BRIDGES C6: a traceback delivered as a
    successful result is the transport reporting on itself.
    """
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not getattr(args, "fn", None):
        parser.print_help(sys.stderr)
        return INCOMPLETE
    try:
        code = args.fn(args)
    except formats.Refusal as refusal:
        sys.stderr.write(f"REFUSED {refusal.path}: {refusal.message}\n")
        return INCOMPLETE
    except Exception as exc:  # noqa: BLE001 -- deliberate: see docstring
        from .feeder import HardStop
        if isinstance(exc, HardStop):
            sys.stderr.write(f"HARD STOP {exc.name}: {exc.detail}\n")
        else:
            sys.stderr.write(f"HARD STOP unhandled: {type(exc).__name__}: {exc}\n")
        return INCOMPLETE
    # Python flushes stdout again at interpreter shutdown, and on a closed pipe
    # that raises AFTER main has returned -- which prints `Exception ignored`
    # and replaces the exit code. Detaching stdout here means the verdict this
    # function computed is the verdict the caller sees.
    try:
        sys.stdout.flush()
    except BrokenPipeError:
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass
    from .exit_contract import normalise
    normalised, raw = normalise(code)
    if normalised != raw:
        sys.stderr.write(f"a verb returned {raw!r}, which is not an exit code; "
                         f"reading it as {normalised}\n")
    return normalised


if __name__ == "__main__":
    sys.exit(main())
