"""`regression`: two walks of one line, oldest first, judged by the core.

**An adapter call, not a port.** `vertical.Walk` already implements the core's
`Capture` protocol and `FactoryLineVocabulary` already implements all fifteen
members of its `Vocabulary` -- the core's own conformance kit accepts it with no
problems. So the whole of this module is: load two walks, hand them over, and
decide what the answer means here.

**The vocabulary is passed explicitly rather than registered.** Two registered
verticals are refused rather than ranked, and a pipeline may legitimately have
this one and a BMC installed side by side. Passing it means this verb works with
the `[vertical]` extra present and no entry point in force at all.

**An undeclared prefix shift is a FINDING, never applied.** The core reports a
subtree that may have moved behind a new prefix and does not pair across it
unless a map declares it. A rename this package inferred would be exactly the
guess the review gate exists to refuse, so the shift is reported and the
operator declares it or does not.

**What this verb is for on a line**: a PLC program release renames or drops
tags, and the walk taken after it should differ from the walk before it in
exactly the ways somebody signed for. `--rename OLD NEW` is that signature --
two arguments rather than one `OLD=NEW` string, because every OPC UA node id
already contains an equals sign.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence, Tuple

from . import formats
from .exit_contract import CLEAN, FINDINGS, INCOMPLETE

#: What this verb writes. Its own format, because the counts below are this
#: package's reading of the core's report and not the core's report itself.
FORMAT = formats.REGRESSION


def _walk(path: str) -> Tuple[Any, str]:
    """Through `formats.load`, which is what refuses an unknown major.

    This read raw JSON until 0.1.7 and accepted any object with a `samples` key
    -- including a `walk/2` written by a reader this one does not understand.
    Every other verb went through the loader; the README's claim that all of
    them do was true of seven of nine.

    `validate_walk` IS called, and the reason it was not is worth recording
    because it was false. 0.1.7 said a receiver-side shape check would refuse
    the declared-rename leg's prefixed walk, so the verb exists to accept the
    one input the check rejects. Measured: `validate_walk` requires node keys to
    be non-empty strings and `L1.ns=2;s=...` is one, so the prefixed walk passes
    with no problems at all -- as do all fifteen corpus walks. The decision was
    harmless and its stated reason was wrong, which is the worse half: a reader
    who believed it would not have tried.
    """
    try:
        payload = formats.load(path, formats.WALK)
    except formats.Refusal as refused:
        # The message alone does not carry the file. Every other branch here
        # names it, and a refusal that does not tells the caller to go and look
        # at both walks.
        return None, f"{refused.path}: {refused.message}"
    except OSError as unreadable:
        return None, f"cannot read {path}: {unreadable}"
    except json.JSONDecodeError as malformed:
        return None, f"{path} is not JSON: {malformed}"
    if not isinstance(payload, dict) or not payload.get("samples"):
        return None, (f"{path} carries no samples, so it is not a walk this "
                      f"can compare; a capture that served nothing is not a "
                      f"capture that found nothing")
    from .walkcheck import validate_walk
    problems = validate_walk(payload)
    if problems:
        return None, (f"{path} is not a well-formed walk: "
                      + "; ".join(problems[:3])
                      + (f" (and {len(problems) - 3} more)"
                         if len(problems) > 3 else ""))
    return payload, ""


def compare(before_path: str, after_path: str,
            renames: Sequence[Sequence[str]] = ()) -> Tuple[int, Dict[str, Any]]:
    """`(exit code, report)`. Never raises for an input it can describe."""
    from .vertical import FactoryLineVocabulary, Walk

    problems: List[str] = []
    before_raw, why = _walk(before_path)
    if why:
        problems.append(why)
    after_raw, why = _walk(after_path)
    if why:
        problems.append(why)
    if problems:
        return INCOMPLETE, {"format": FORMAT, "could_not_complete": problems}

    try:
        # Lazy on purpose: Stage 1 declares no dependency and a test asserts it.
        from presence_audit.regression import compare_walks
    except ImportError as missing:
        return INCOMPLETE, {"format": FORMAT, "could_not_complete": [
            f"the [vertical] extra is not installed, so the core could not "
            f"judge these walks: {missing}"]}

    # PAIRS, not the core's `parse_prefix_map`. That helper splits `OLD=NEW` on
    # the first `=` and every OPC UA node id contains one, so the old prefix
    # `ns=2;s=` is read as `ns` and the declaration silently matches nothing --
    # producing the mass-removal report the flag exists to prevent. Measured:
    # the same move pairs all 27 points when the names carry no `=`, and
    # `compare_walks(prefix_map=[("ns=2;s=", "ns=2;s=L1.")])` pairs them here
    # too. The helper is the only unusable part; filed as presence-audit #5.
    prefix_map = [(str(old), str(new)) for old, new in renames]

    report = compare_walks(Walk(before_raw), Walk(after_raw),
                           prefix_map=prefix_map,
                           vocabulary=FactoryLineVocabulary())
    changes = report.regressions
    changes = list(changes() if callable(changes) else changes)

    counts = dict(report.counts())
    shifted = counts.get("aggregation_prefix_shift", 0)
    body: Dict[str, Any] = {
        "format": FORMAT,
        "before": before_path, "after": after_path,
        "declared_renames": list(renames),
        "counts": counts,
        "regressions": [str(change) for change in changes],
        "undeclared_prefix_shifts": shifted,
    }
    if shifted:
        body["note"] = ("a subtree may have moved behind a prefix nobody "
                        "declared. It is reported and NOT applied: a rename "
                        "this package inferred is the guess the review gate "
                        "refuses. Declare it with --rename OLD NEW or leave "
                        "it reported.")
    return (FINDINGS if changes or shifted else CLEAN), body


def render(body: Dict[str, Any]) -> str:
    """One line per thing, and the counts last so a reader ends on the total."""
    if body.get("could_not_complete"):
        return "\n".join(f"  COULD NOT COMPLETE: {why}"
                         for why in body["could_not_complete"])
    lines = [f"  {change}" for change in body["regressions"]]
    if body.get("note"):
        lines.append(f"  {body['note']}")
    counted = ", ".join(f"{key} {value}"
                        for key, value in sorted(body["counts"].items()) if value)
    lines.append(f"  {counted or 'nothing changed'}")
    return "\n".join(lines)
