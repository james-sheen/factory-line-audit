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
from . import __version__
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


def _password(args) -> Optional[str]:
    """From the environment or a file, never from argv.

    On a shared host any user can read the process table, and a collector walks
    continuously, so the window is not brief. This is the same refusal
    `bmc-sensor-audit` accepted for the same reason.
    """
    if args.password_env and args.password_file:
        raise formats.Refusal(args.target, "--password-env and --password-file "
                                           "both name a password; one of them "
                                           "would be silently ignored")
    if args.password_env:
        value = os.environ.get(args.password_env)
        if value is None:
            raise formats.Refusal(args.target, f"${args.password_env} is not "
                                               f"set, so no password was read")
        return value
    if args.password_file:
        try:
            with open(args.password_file, encoding="utf-8") as handle:
                return handle.readline().rstrip("\n")
        except OSError as unreadable:
            raise formats.Refusal(args.target, f"cannot read the password file: "
                                               f"{unreadable}") from None
    if args.user:
        raise formats.Refusal(args.target, "--user needs --password-env or "
                                           "--password-file; this verb does not "
                                           "take a password on the command line")
    return None


def cmd_capture(args) -> int:
    """One OUTCOME line is the contract; the rest of stdout is prose.

    `walked` means a walk was written. `unchanged` means the address space still
    holds exactly the declared nodes it held when the cache was written, so no
    value was read -- which is a different claim from *nothing changed*, and the
    cache says so in as many words.
    """
    from . import capture as capture_module
    from .presence import load_register
    try:
        register = load_register(args.register)
    except formats.Refusal as refused:
        _out(f"  COULD NOT COMPLETE: {refused}")
        _out(f"OUTCOME exit={INCOMPLETE} verdict={MEANING[INCOMPLETE]}")
        return INCOMPLETE

    # REFUSED BEFORE ANYTHING IS DIALLED. A flag accepted and then ignored is
    # worse than one that does not exist: the walk would record a protection
    # nothing applied, and a certificate downstream would read that record.
    try:
        security = capture_module.security_from_flags(
            policy=args.security_policy, mode=args.security_mode,
            cert=args.cert, key=args.key, pin=args.server_cert_pin_sha256,
            insecure=args.insecure, endpoint=args.target)
        password = _password(args)
    except formats.Refusal as refused:
        _out(f"  REFUSED: {refused.message}")
        _out(f"OUTCOME exit={INCOMPLETE} verdict={MEANING[INCOMPLETE]}")
        return INCOMPLETE

    try:
        import asyncua  # noqa: F401
    except ImportError:
        _out("  COULD NOT COMPLETE: the [live] extra is not installed, so "
             "nothing was read from any server")
        _out(f"OUTCOME exit={INCOMPLETE} verdict={MEANING[INCOMPLETE]}")
        return INCOMPLETE

    try:
        if args.membership_cache:
            fresh = capture_module.membership(
                register, args.target,
                security_string=capture_module.security_string(
                    security, args.cert, args.key),
                user=args.user, password=password, namespace=args.namespace)
            cached = None
            if os.path.exists(args.membership_cache):
                with open(args.membership_cache, encoding="utf-8") as handle:
                    cached = json.load(handle)
            if capture_module.membership_unchanged(cached, fresh):
                _out(f"  {len(fresh['present'])} declared node(s) still in the "
                     f"address space, {len(fresh['absent'])} not. No value was "
                     f"read and none is cached: this says the membership is "
                     f"unchanged, not that a reading is")
                _out("OUTCOME unchanged")
                return CLEAN
            with open(args.membership_cache, "w", encoding="utf-8") as handle:
                json.dump(fresh, handle, indent=2)
                handle.write("\n")

        walk = capture_module.capture(
            register, args.target, samples=args.samples,
            budget_s=args.budget, namespace=args.namespace,
            security=security,
            security_string=capture_module.security_string(
                security, args.cert, args.key),
            user=args.user, password=password,
            pin=args.server_cert_pin_sha256)
    except formats.Refusal as refused:
        _out(f"  COULD NOT COMPLETE: {refused}")
        _out(f"OUTCOME exit={INCOMPLETE} verdict={MEANING[INCOMPLETE]}")
        return INCOMPLETE
    except Exception as unreachable:
        _out(f"  COULD NOT COMPLETE: {args.target}: "
             f"{type(unreachable).__name__}: {unreachable}")
        _out(f"OUTCOME exit={INCOMPLETE} verdict={MEANING[INCOMPLETE]}")
        return INCOMPLETE

    raw = json.dumps(walk, indent=2) + "\n"
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(raw)
    source = walk["source"]
    _out(f"  {source['nodes_served']}/{source['nodes_requested']} declared "
         f"node(s) served, "
         f"{len(source['nodes_not_in_address_space'])} absent, "
         f"{len(source['nodes_present_but_unreadable'])} present and not "
         f"reading; "
         f"{len(walk['samples'])} sample(s) -> {args.out}")
    _out(f"  taken with security_policy={source['security_policy']} "
         f"security_mode={source['security_mode']} pinned={source['pinned']}")
    if args.print_digest:
        _out(capture_module.digest(raw))
    _out("OUTCOME walked")
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
    """The measured floors, from the package unless a caller names a file.

    This looked in `battery/`, which no wheel carries, and returned `{}` when it
    found nothing -- including when `--floors` named a file that does not exist.
    So an installed deployment lost `warmup_unreachable` silently: a collector
    too slow to ever present a floor had its `insufficient_samples` declines
    classed `warmup`, floor 0, which reads as *give it time*. The floors now ship
    beside the code, and a named file that is missing is a refusal rather than an
    empty dict, because *the file you asked for is not there* and *this engine has
    no measured floors* are different facts.
    """
    if path:
        if not os.path.exists(path):
            raise formats.Refusal(path, "--floors names a file that does not "
                                        "exist. Continuing without it would "
                                        "class every unreachable floor as a "
                                        "warm-up")
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    beside = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "engine_floors.json")
    if os.path.exists(beside):
        with open(beside, "r", encoding="utf-8") as handle:
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
    # A consumer resolves this tool on PATH and runs it as a SUBPROCESS, so the
    # `>=` in its packaging metadata governs what pip put in the environment and
    # not what actually answers. Until this existed there was no way to ask:
    # the flag exited 2 with an argparse usage error, so a downstream floor
    # could be declared and never checked. `bmc-sensor-audit` carries the same
    # argument for the same reason.
    parser.add_argument("--version", action="version",
                        version=f"factory-line-audit {__version__}")
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

    p = subs.add_parser("capture", help="read a live OPC UA server, write a walk")
    register_arg(p)
    p.add_argument("--target", required=True, metavar="opc.tcp://HOST:PORT/PATH")
    p.add_argument("--out", required=True)
    p.add_argument("--samples", type=int, default=5)
    p.add_argument("--budget", type=float, default=30.0,
                   help="seconds to spend collecting, whatever --samples asks")
    p.add_argument("--namespace", help="namespace URI; index 2 is assumed without it")
    p.add_argument("--print-digest", action="store_true",
                   help="print the content handle of the file written")
    p.add_argument("--membership-cache", metavar="PATH",
                   help="ask only whether the address space still holds the "
                        "declared nodes. No value is read or stored")
    p.add_argument("--security-policy", default="None",
                   help="None, or a current OPC UA policy. Withdrawn policies "
                        "are refused by name rather than offered")
    p.add_argument("--security-mode", default="",
                   help="None, Sign or SignAndEncrypt. Defaults to "
                        "SignAndEncrypt whenever a policy is chosen")
    p.add_argument("--cert", help="client certificate, required by any policy")
    p.add_argument("--key", help="client private key, required by any policy")
    p.add_argument("--server-cert-pin-sha256", metavar="HEX",
                   help="refuse a server whose certificate is not this one")
    p.add_argument("--insecure", action="store_true",
                   help="connect unencrypted and anonymous off loopback. "
                        "Recorded in the walk, because somebody chose it")
    p.add_argument("--user", help="username; the password never crosses argv")
    p.add_argument("--password-env", metavar="NAME",
                   help="environment variable holding the password")
    p.add_argument("--password-file", metavar="PATH",
                   help="file holding the password, first line")
    p.set_defaults(fn=cmd_capture)

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
