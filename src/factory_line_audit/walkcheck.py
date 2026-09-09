"""`validate-walk`: everything wrong with a walk file, or an empty list.

**The person who RECEIVES the file is the one who needs to check it.** A line
that ships walks to a customer, an archive, or a certificate has to be able to
refuse a malformed one using the format's own words rather than a shape inferred
from whichever files happened to arrive first. That is why this ships rather
than living in a test.

**Stage 1, and it stays there.** No engine, no core, no server, nothing outside
the standard library. Checking a walk is reading JSON, and a receiver should not
have to install an axiom engine to do it.

**Malformation only.** A walk with no samples is a legal capture of a line that
served nothing -- `Walk.complete` already reports that, and refusing it here
would refuse a file this package writes. Absent optional fields are accepted for
the same reason the reader accepts them; present-and-the-wrong-type is not,
because that is the case where the reader takes a value it cannot use.

**Problems, not an exception.** A caller reports all of them at once rather than
one per run. The CLI turns a non-empty list into exit 2 and never 1: a file that
could not be read is not a finding about the line.

## What `factory-line-audit/walk/1` guarantees

Written down so a downstream pin has something to pin TO, rather than a shape
read off whichever file it was handed first.

* `format` is `factory-line-audit/walk/1`; a different MAJOR is refused.
* `samples` is a list, oldest first. It may be empty.
* each sample carries `t`, an ISO-8601 string, and `nodes`, an object.
* each entry in `nodes` is keyed by the node id as the server reports it, and
  carries `q`, the OPC UA status word as a string. `v` may be absent or null --
  that is a node the server would not vouch for, and it is the whole subject of
  the three-state answer. When present it is a SCALAR of any JSON type: a
  measurement is a number, a running flag is a boolean, and a machine state is
  usually an enumeration string. Nothing here coerces it.
* anything else in the file is permitted and ignored. Nothing here is a claim
  that a walk carries ONLY these.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from . import formats

#: The one this reader was written against. Anything with the same major is
#: read; a different major is refused rather than guessed at.
FORMAT = formats.WALK


def _is_scalar(value: Any) -> bool:
    """What a reading may be. THE READER IS THE ORACLE, not the corpus.

    This began as *a number or null* and refused the corpus this package writes:
    a `state`-class tag carries a boolean. Widening to numbers, booleans and
    null would have refused a real line too, because a state word on most
    servers is an enumeration STRING and the feeder feeds it as a property. The
    corpus is generated here and could not have said so.

    So the rule is what `vertical.Node.reading` and `feeder` actually do, which
    is check for `None` and pass the value through uncoerced. Anything scalar is
    usable; an object or a list is not a reading under any reading of it.
    """
    return value is None or isinstance(value, (int, float, bool, str))


def validate_walk(payload: Any) -> List[str]:
    """Everything wrong with this walk, or `[]`. Never raises."""
    problems: List[str] = []
    if not isinstance(payload, dict):
        return [f"the walk is {type(payload).__name__}, not an object"]

    declared = payload.get("format")
    if not declared:
        problems.append("no `format`, so a reader cannot tell what this is")
    elif not isinstance(declared, str):
        problems.append(f"`format` is {type(declared).__name__}, not a string")
    else:
        try:
            name, major = formats.split(declared)
            _, mine = formats.split(FORMAT)
        except Exception:
            problems.append(f"`format` {declared!r} is not <package>/<artifact>/<n>")
        else:
            if name != formats.split(FORMAT)[0]:
                problems.append(f"`format` {declared!r} is not a {FORMAT} walk")
            elif major != mine:
                problems.append(f"`format` {declared!r} is major {major}; this "
                                f"reader was written against {mine} and will "
                                f"not guess at another")

    samples = payload.get("samples")
    if samples is None:
        problems.append("no `samples`; a walk with none is written as an empty "
                        "list, and absent means the field was never written")
        return problems
    if not isinstance(samples, list):
        problems.append(f"`samples` is {type(samples).__name__}, not a list")
        return problems

    for index, sample in enumerate(samples):
        where = f"samples[{index}]"
        if not isinstance(sample, dict):
            problems.append(f"{where} is {type(sample).__name__}, not an object")
            continue
        stamp = sample.get("t")
        if stamp is not None and not isinstance(stamp, str):
            problems.append(f"{where}.t is {type(stamp).__name__}, not a string")
        nodes = sample.get("nodes")
        if nodes is None:
            problems.append(f"{where} carries no `nodes`")
            continue
        if not isinstance(nodes, dict):
            problems.append(f"{where}.nodes is {type(nodes).__name__}, "
                            f"not an object")
            continue
        for node, reading in nodes.items():
            spot = f"{where}.nodes[{node!r}]"
            if not isinstance(node, str) or not node:
                problems.append(f"{spot} is not a node id")
                continue
            if not isinstance(reading, dict):
                problems.append(f"{spot} is {type(reading).__name__}, "
                                f"not an object")
                continue
            quality = reading.get("q")
            if quality is None:
                problems.append(f"{spot} carries no `q`; the status word is how "
                                f"a node the server will not vouch for is told "
                                f"apart from one it never had")
            elif not isinstance(quality, str):
                problems.append(f"{spot}.q is {type(quality).__name__}, "
                                f"not a string")
            if "v" in reading and not _is_scalar(reading["v"]):
                problems.append(f"{spot}.v is {type(reading['v']).__name__}; a "
                                f"reading is a scalar or null, and nothing here "
                                f"can take an object or a list as one")
    return problems


def observations(payload: Dict[str, Any]) -> List[str]:
    """True of the walk, wrong of nothing. Printed, never scored.

    Kept apart from `validate_walk` on purpose: a validator that refuses a valid
    file is one people learn to route around, and they take the malformed cases
    with them.
    """
    notes: List[str] = []
    samples = payload.get("samples") or []
    if not samples:
        notes.append("no samples: a legal capture of a line that served "
                     "nothing, and nothing here can be judged from it")
        return notes
    widths = {len(s.get("nodes") or {}) for s in samples if isinstance(s, dict)}
    if len(widths) > 1:
        notes.append(f"samples do not all carry the same number of nodes "
                     f"({min(widths)}-{max(widths)}); a node that appeared or "
                     f"vanished mid-walk is a real thing and not an error")
    stamps = [s.get("t") for s in samples
              if isinstance(s, dict) and isinstance(s.get("t"), str)]
    if stamps != sorted(stamps):
        notes.append("samples are not in time order; the readers here take the "
                     "LAST as current, so the order is load-bearing")
    return notes
