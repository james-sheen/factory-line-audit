"""The operator-knowledge channel, and the gate that refuses it unreviewed.

BRIDGES C4 and the review gate. Some facts are physics, contract or law; no
schema holds
them and no rule derives them. This module carries them, requires a `basis` on
every one, and refuses -- mechanically, naming the file -- to let an unreviewed
statement reach evaluation.

The drafter and the gate live in the same module on purpose. A package that
emits the unreviewed artifact and then refuses its own output is a boundary
proving itself; a package that only describes the boundary is a paragraph.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import formats
from .presence import load_register, looks_templated

#: kind -> the fields a statement of that kind must carry beyond `basis`,
#: `asset` and (where applicable) `tag`. Every kind maps onto exactly one thing
#: the engine will otherwise decline, which is the point of the requirements
#: document: the decline
#: vocabulary read backwards is this table.
KINDS: Dict[str, Dict[str, Any]] = {
    "bound": {
        "requires_tag": True, "any_of": ("warning", "critical",
                                         "lower_warning", "lower_critical"),
        "answers": "no_threshold",
        "note": "a published limit. BOUNDEDNESS and RESPONSIVENESS need one, "
                "and MODELING.md refuses an invented floor.",
    },
    "setpoint": {
        "requires_tag": True, "all_of": ("setpoint", "tolerance"),
        "answers": "insufficient_samples",
        "note": "where a quantity is supposed to sit. Removes HOMEOSTASIS's "
                "dependence on history entirely.",
    },
    "rate": {
        "requires_tag": True, "any_of": ("rate_warning", "rate_critical"),
        "answers": "(nothing -- see probe R1)",
        "note": "how fast a counter is allowed to climb. The engine answers "
                "this from a default when nobody declares it.",
    },
    "reset": {
        "requires_tag": True, "all_of": (), "requires_keys": ("allow_reset",),
        "answers": "(nothing -- the engine routes from a default instead, "
                   "probe A6)",
        "note": "whether this counter is zeroed in normal operation. The only "
                "statement whose absence the engine cannot complain about: a "
                "drop to near zero is routed to the RESET arm by default, so a "
                "counter nobody asked about is judged as though resetting were "
                "normal for it. `null` is legal and means the question was "
                "asked and nobody could answer -- which is not the same as "
                "never asking, and the manifest records the two separately.",
    },
    "redundant": {
        "requires_tag": True, "all_of": ("agrees_with", "tolerance"),
        "answers": "missing_config",
        "note": "two readings of one quantity. A claim about the plant; if a "
                "rule can generate the pairs it does not know the pairs.",
    },
    "conservation": {
        "requires_tag": False, "all_of": ("input_tag", "output_tags"),
        "answers": "missing_config",
        "note": "both halves of a balance, named. The engine will not work "
                "either one out.",
    },
    "expect_variation": {
        "requires_tag": True, "all_of": (),
        "answers": "(opt-in) a flat series is a dead probe, not a steady one",
        "note": "opt-in, because a genuinely constant quantity exists.",
    },
    "slow_oscillation": {
        "requires_tag": True, "all_of": ("min_amplitude", "min_crossings"),
        "answers": "(arm selection)",
        "note": "the default STABILITY arm is period-2 by construction; "
                "hunting on a longer period needs this block.",
    },
    "gate_on": {
        "requires_tag": True, "all_of": ("required_property",),
        "answers": "precondition_unmet",
        "note": "the check means nothing unless the machine is in a state. "
                "The engine will not say which way to read the gate.",
    },
    "bad_state": {
        "requires_tag": True,               # a `state`-class tag
        "all_of": ("states",),
        "answers": "(a finding the engine can make only if told which words "
                   "mean broken)",
        "note": "which words of this machine's state enumeration mean it is "
                "broken. From the PLC alarm list or the SCADA state-machine "
                "document, never from the spelling: `Fault` is a state on one "
                "vendor and a menu on another. MEASURED across the declared "
                "engine range: a STATE indicator listing STABILITY fires "
                "`declared_bad_state` from 0.1.12, and is SILENT at 0.1.10 and "
                "0.1.11 -- accepted, no finding, and not reported by "
                "`unread_fields` either, which does report a key nobody reads. "
                "So the manifest says so; nothing else can.",
    },
    "exclusion": {
        "requires_tag": False, "all_of": ("reason",),
        "answers": "(pre-engine)",
        "note": "this asset or tag is deliberately not watched. Named in the "
                "manifest so it reads as a choice, not an oversight.",
    },
}


def _fixture(body: Dict[str, Any]) -> bool:
    return bool(body.get("fixture")) and body.get("reviewed_by") == "fixture"


def review_status(body: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """(status, why-not) for a declaration file.

    `fixture` passes only by disclosing itself on its face. Simulating a review
    -- a plausible human name and a date on a file nobody read -- teaches a
    suite that impersonation works, and the suite was the thing that was
    supposed to notice.
    """
    if _fixture(body):
        return "fixture", None
    if body.get("fixture"):
        return "unreviewed", ("declares fixture: true without "
                              'reviewed_by: "fixture" -- a fixture passes by '
                              "disclosing itself, not by naming a reviewer")
    by, on = body.get("reviewed_by"), body.get("reviewed_on")
    if by and on:
        return "reviewed", None
    if by and not on:
        return "unreviewed", (f"reviewed_by {by!r} with no reviewed_on. A name "
                              "with no date is the shape of somebody clearing "
                              "the gate rather than passing it")
    if on and not by:
        return "unreviewed", f"reviewed_on {on!r} with no reviewed_by"
    return "unreviewed", "no reviewed_by and no reviewed_on"


def check_statements(body: Dict[str, Any], register: Dict[str, Any],
                     path: str) -> List[str]:
    """Every mechanical complaint about the statements themselves."""
    problems: List[str] = []
    assets = {a["id"]: a for a in register["assets"]}
    for n, stmt in enumerate(body.get("statements") or []):
        where = f"statement {n}"
        kind = stmt.get("kind")
        if kind not in KINDS:
            problems.append(f"{where}: kind {kind!r} is not one of {sorted(KINDS)}")
            continue
        where = f"{where} ({kind}"
        asset_id = stmt.get("asset")
        where += f" on {asset_id}"
        if not stmt.get("basis"):
            problems.append(f"{where}): no basis. Every statement must say what "
                            f"the declarer actually looked at")
        if asset_id not in assets:
            problems.append(f"{where}): no such asset in the register")
            continue
        spec = KINDS[kind]
        tag = stmt.get("tag")
        if spec["requires_tag"]:
            if not tag:
                problems.append(f"{where}): no tag")
            elif tag not in assets[asset_id]["tags"]:
                problems.append(f"{where}.{tag}): the register declares no such "
                                f"tag on this asset (or it was excluded at load)")
        for field in spec.get("all_of", ()):
            if stmt.get(field) is None:
                problems.append(f"{where}.{tag}): missing {field}")
        any_of = spec.get("any_of")
        if any_of and not any(stmt.get(f) is not None for f in any_of):
            problems.append(f"{where}.{tag}): needs at least one of {list(any_of)}")
        for field in spec.get("requires_keys", ()):
            if field not in stmt:
                problems.append(f"{where}.{tag}): no {field} key. This kind "
                                f"requires it; null is the legal way to say the "
                                f"question was asked and nobody could answer")
        if kind == "rate" and "allow_reset" in stmt:
            # Read off `rate` until 0.1.6, by a generator nothing validated --
            # so a typo in the name was silently dropped and a file could look
            # declared while the engine routed from its default. Refused by
            # name rather than ignored, because ignoring it is the defect.
            problems.append(f"{where}.{tag}): carries allow_reset, which is not "
                            f"read here. Declare it as a `reset` statement, "
                            f"where it is required and checked")
        if kind == "redundant":
            for other in stmt.get("agrees_with") or []:
                if other not in assets[asset_id]["tags"]:
                    problems.append(f"{where}.{tag}): agrees_with names {other!r}, "
                                    f"not a tag on this asset")
        if kind == "conservation":
            for field in ("input_tag",):
                if stmt.get(field) and stmt[field] not in assets[asset_id]["tags"]:
                    problems.append(f"{where}): {field} {stmt[field]!r} is not a "
                                    f"tag on this asset")
            for other in stmt.get("output_tags") or []:
                if other not in assets[asset_id]["tags"]:
                    problems.append(f"{where}): output_tags names {other!r}, not "
                                    f"a tag on this asset")
    return problems


def gate(paths: List[str], register: Dict[str, Any]) -> Dict[str, Any]:
    """The mechanical refusal. Returns the accepted bodies, or raises Refusal.

    Refuses by naming the file. A gate that reports *some declaration was not
    reviewed* has told the operator to go and look at all of them.
    """
    accepted: List[Dict[str, Any]] = []
    reviews: List[Dict[str, Any]] = []
    for path in paths:
        body = formats.load(path, formats.DECLARATION)
        status, why = review_status(body)
        problems = check_statements(body, register, path)
        reviews.append({"path": path, "status": status,
                        "reviewed_by": body.get("reviewed_by"),
                        "reviewed_on": body.get("reviewed_on"),
                        "statements": len(body.get("statements") or [])})
        if status == "unreviewed":
            raise formats.Refusal(path, f"declaration is unreviewed: {why}")
        if problems:
            raise formats.Refusal(path, "declaration is malformed:\n  - "
                                        + "\n  - ".join(problems))
        body["_path"] = path
        body["_review"] = status
        accepted.append(body)
    return {"accepted": accepted, "reviews": reviews}


def draft(register: Dict[str, Any]) -> Dict[str, Any]:
    """Emit an unreviewed declaration file, and exit clean doing it.

    Drafting is legal. What this emits is a proposal shaped like the statements
    a person would have to make -- with `basis` left empty, because the one
    thing a rule cannot do is know why. It will not pass `gate`.
    """
    statements: List[Dict[str, Any]] = []
    for asset in register["assets"]:
        for tag, spec in (asset.get("tags") or {}).items():
            if looks_templated(tag):
                statements.append({
                    "kind": "exclusion", "asset": asset["id"], "tag": tag,
                    "reason": "", "basis": "",
                    "_proposed_because": "the name looks like an unfilled "
                                         "template slot. A guess about a name, "
                                         "which is why it is proposed here "
                                         "rather than acted on",
                })
                continue
            cls = spec["class"]
            if cls in ("measurement", "latency"):
                statements.append({
                    "kind": "bound", "asset": asset["id"], "tag": tag,
                    "warning": None, "critical": None, "basis": "",
                    "_proposed_because": f"tag class {cls} takes a published "
                                         f"limit; nothing in this register "
                                         f"supplies one",
                })
            elif cls == "counter":
                statements.append({
                    "kind": "rate", "asset": asset["id"], "tag": tag,
                    "rate_warning": None, "rate_critical": None, "basis": "",
                    "_proposed_because": "a counter climbs at a rate somebody "
                                         "knows; the engine will otherwise "
                                         "answer from a default",
                })
                statements.append({
                    "kind": "reset", "asset": asset["id"], "tag": tag,
                    "allow_reset": None, "basis": "",
                    "_proposed_because": "whether this counter is zeroed in "
                                         "normal operation is a fact about the "
                                         "plant. Proposed for every counter "
                                         "because the engine answers it from a "
                                         "default and says nothing about having "
                                         "done so",
                })
    return {
        "format": formats.DECLARATION,
        "line": register.get("line"),
        "reviewed_by": None,
        "reviewed_on": None,
        "_warning": "UNREVIEWED DRAFT. Every basis is empty and every number "
                    "is null. This file is refused by `gate` by design; a "
                    "person must supply the facts and sign for them.",
        "statements": statements,
    }


def collect(accepted: List[Dict[str, Any]]) -> Dict[Tuple[str, Optional[str]], List[Dict]]:
    """(asset, tag) -> statements, across every accepted file."""
    out: Dict[Tuple[str, Optional[str]], List[Dict]] = {}
    for body in accepted:
        for stmt in body.get("statements") or []:
            stmt = dict(stmt)
            stmt["_from"] = body["_path"]
            stmt["_review"] = body["_review"]
            out.setdefault((stmt.get("asset"), stmt.get("tag")), []).append(stmt)
    return out
