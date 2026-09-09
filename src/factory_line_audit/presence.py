"""Stage 1: what exists, and what is reading. No engine, standard library only.

BRIDGES C1: the first stage answers the question the engine cannot ask -- does
the thing exist at all -- and it must run with the engine uninstalled. Nothing
in this module imports anything the engine ships.

The classification is three-way and never a boolean. *Absent* and *present but
not reading* send a person to two different places: one is a walk that could
not find a node the register promised, the other is a node the server served
with a quality word that says do not believe this.
"""
from __future__ import annotations

import fnmatch
from typing import Any, Dict, List, Optional, Tuple

from . import formats
from .exit_contract import CLEAN, FINDINGS

#: Names that LOOK like a slot in a template nobody filled in.
#:
#: These do not exclude anything. `draft` uses them to PROPOSE an exclusion a
#: person then reviews; the only thing that actually excludes a tag is
#: `"templated": true` in the register or a reviewed `exclusion` statement.
#:
#: It was a silent exclusion rule until the suite caught `Spare*` swallowing
#: `spared_capacity`. Widening the glob or special-casing the word would have
#: hidden the real problem, which is that BRIDGES's review gate already answers
#: this:
#: a rule may propose an operator-knowledge fact and may not know one, and
#: "this tag is an unfilled template slot" is exactly such a fact. `SpareAnalog3`
#: and `spared_capacity` are not separable by any predicate over their letters,
#: and a bridge that excluded the second would have removed a real measurement
#: from an audit and named it in the manifest as if that were a decision.
LOOKS_TEMPLATED = ("spare*", "reserved*", "template*", "unused*", "dummy*")

#: Tag classes a register may declare. Never inferred from a name: BRIDGES
#: the review gate and MODELING.md both refuse a rule that reads meaning out of
#: naming.
TAG_CLASSES = ("measurement", "counter", "latency", "percentage", "count", "state")

#: How an OPC UA status word is read, and what each reading costs.
#:
#: Collapsing this to Good / not-Good was the first thing Stage 1 did, and it
#: throws away the two distinctions a plant actually acts on. `Uncertain` is the
#: server saying it does not stand behind the number -- judging an invariant on
#: it manufactures a verdict out of a value nobody vouched for. And
#: `Good_LocalOverride` is a value a person typed at an HMI: the tag reads, the
#: process behind it does not, and every axiom evaluated on it is being asked
#: about the operator rather than the machine.
QUALITY_GRADES = {
    "good": {"usable": True, "substituted": False, "floor": CLEAN,
             "note": "the server vouches for this value"},
    "good_subnormal": {"usable": True, "substituted": False, "floor": CLEAN,
                       "note": "good, from fewer sources than normal"},
    "good_localoverride": {"usable": True, "substituted": True, "floor": FINDINGS,
                           "note": "substituted at an HMI; this measures the "
                                   "operator, not the process"},
    "uncertain": {"usable": False, "substituted": False, "floor": FINDINGS,
                  "note": "the server does not stand behind this value"},
    "bad": {"usable": False, "substituted": False, "floor": FINDINGS,
            "note": "the server reports the source as failed"},
}

READING = "reading"
NOT_READING = "present_not_reading"
ABSENT = "absent"

#: Stage 1 floors, decided here rather than where a run is failing.
STATE_FLOOR = {READING: CLEAN, NOT_READING: FINDINGS, ABSENT: FINDINGS}


def grade(quality: Any) -> Tuple[str, Dict[str, Any]]:
    """An OPC UA status word -> a grade name and its properties.

    Unknown words grade as `uncertain` rather than `bad` or `good`: a status
    this reader has never seen is one it cannot interpret, and interpreting it
    optimistically is how a substituted value gets judged as a measurement.
    """
    word = str(quality or "").strip().lower().replace("-", "_").replace(" ", "_")
    if word in QUALITY_GRADES:
        return word, QUALITY_GRADES[word]

    # SEPARATORS REMOVED, because the two spellings are two populations. OPC UA
    # names these codes `GoodLocalOverride` and `BadDeviceFailure`, and that is
    # what `asyncua` reports; the synthetic corpus writes `Good_LocalOverride`
    # and `Bad_DeviceFailure`. Matching on `good_` saw only the second, so every
    # compound word a real server returns fell through to the unknown-word
    # branch: `GoodSubNormal` graded unusable and a reading tag read as
    # `present_not_reading`, and `GoodLocalOverride` graded not-substituted, so
    # the substituted count -- the whole point of telling an HMI override apart
    # from a measurement -- could never fire against a live server.
    #
    # It survived because the battery's collector TRANSLATED into the corpus
    # spelling before Stage 1 saw it. The fixture agreed with the grader
    # because something in between made it agree.
    flat = word.replace("_", "")
    if flat in ("good", "uncertain", "bad"):
        return flat, QUALITY_GRADES[flat]
    if flat.startswith("good"):
        # A qualified Good is still a reading the server vouches for. Two of
        # them say a PERSON put the value there, which is a different claim
        # about what an axiom would then be measuring.
        if "override" in flat or "edited" in flat:
            return "good_localoverride", QUALITY_GRADES["good_localoverride"]
        return "good_subnormal", QUALITY_GRADES["good_subnormal"]
    if flat.startswith("uncertain"):
        return "uncertain", QUALITY_GRADES["uncertain"]
    if flat.startswith("bad"):
        return "bad", QUALITY_GRADES["bad"]
    return "uncertain", QUALITY_GRADES["uncertain"]


def looks_templated(tag_name: str) -> bool:
    """A PROPOSAL, never a decision. See LOOKS_TEMPLATED."""
    low = tag_name.lower()
    return any(fnmatch.fnmatch(low, pattern) for pattern in LOOKS_TEMPLATED)


def load_register(path: str) -> Dict[str, Any]:
    """Load a register, excluding templated tags before anything else sees it.

    The exclusions are returned on the register itself, under `_excluded_tags`,
    so the manifest can name them. An exclusion that leaves no trace is
    indistinguishable from having forgotten the tag existed, and BRIDGES's
    requirements-document section
    says that difference is the whole value of an audit.
    """
    body = formats.load(path, formats.REGISTER)
    assets = body.get("assets")
    if not isinstance(assets, list) or not assets:
        raise formats.Refusal(path, "register declares no assets")
    excluded: List[Dict[str, str]] = []
    seen_ids = set()
    for asset in assets:
        asset_id = asset.get("id")
        if not asset_id:
            raise formats.Refusal(path, "an asset has no id")
        if asset_id in seen_ids:
            raise formats.Refusal(path, f"asset {asset_id} declared twice")
        seen_ids.add(asset_id)
        if not asset.get("type"):
            raise formats.Refusal(path, f"asset {asset_id} has no type")
        tags = asset.get("tags") or {}
        keep = {}
        for name, spec in tags.items():
            if spec.get("templated") is True:
                excluded.append({"asset": asset_id, "tag": name,
                                 "reason": "declared_templated",
                                 "detail": "the register declares this tag an "
                                           "unfilled template slot; excluded "
                                           "before generation"})
                continue
            cls = spec.get("class")
            if cls not in TAG_CLASSES:
                raise formats.Refusal(
                    path, f"{asset_id}.{name} declares class {cls!r}; "
                          f"this package knows {list(TAG_CLASSES)}. A tag class "
                          f"is declared, never inferred from the name")
            if not spec.get("node"):
                raise formats.Refusal(path, f"{asset_id}.{name} has no node id")
            keep[name] = spec
        asset["tags"] = keep
    body["_excluded_tags"] = excluded
    body["_path"] = path
    return body


def walk_index(walk: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """nodeId -> the samples that carried it, in walk order."""
    index: Dict[str, List[Dict[str, Any]]] = {}
    for sample in walk.get("samples") or []:
        stamp = sample.get("t")
        for node, reading in (sample.get("nodes") or {}).items():
            entry = dict(reading)
            entry.setdefault("t", stamp)
            entry["_sample_t"] = stamp
            index.setdefault(node, []).append(entry)
    return index


def classify(register: Dict[str, Any], walk: Dict[str, Any]) -> Dict[str, Any]:
    """The presence/1 artifact: every declared tag, in one of three states."""
    index = walk_index(walk)
    samples = walk.get("samples") or []
    tags: List[Dict[str, Any]] = []
    for asset in register["assets"]:
        for name, spec in (asset.get("tags") or {}).items():
            node = spec["node"]
            readings = index.get(node)
            row: Dict[str, Any] = {
                "asset": asset["id"], "asset_type": asset["type"],
                "tag": name, "node": node, "class": spec["class"],
            }
            if readings is None:
                row.update(state=ABSENT, samples=0, usable_samples=0,
                           qualities={}, substituted_samples=0,
                           detail="the walk never served this node")
                tags.append(row)
                continue
            qualities: Dict[str, int] = {}
            usable = 0
            substituted = 0
            for reading in readings:
                name_of_grade, props = grade(reading.get("q"))
                qualities[name_of_grade] = qualities.get(name_of_grade, 0) + 1
                if props["usable"] and reading.get("v") is not None:
                    usable += 1
                    if props["substituted"]:
                        substituted += 1
            state = READING if usable else NOT_READING
            row.update(state=state, samples=len(readings), usable_samples=usable,
                       qualities=qualities, substituted_samples=substituted)
            if state is NOT_READING:
                worst = sorted(qualities, key=lambda q: -qualities[q])[0]
                row["detail"] = QUALITY_GRADES.get(
                    grade(worst)[0], QUALITY_GRADES["uncertain"])["note"]
            elif substituted:
                row["detail"] = QUALITY_GRADES["good_localoverride"]["note"]
            tags.append(row)

    floors = [STATE_FLOOR[t["state"]] for t in tags]
    floors += [QUALITY_GRADES["good_localoverride"]["floor"]
               for t in tags if t.get("substituted_samples")]
    counts = {state: sum(1 for t in tags if t["state"] == state)
              for state in (READING, NOT_READING, ABSENT)}
    counts["substituted"] = sum(1 for t in tags if t.get("substituted_samples"))
    return {
        "format": formats.PRESENCE,
        "line": register.get("line"),
        "source": walk.get("source", {}),
        "samples_in_walk": len(samples),
        "counts": counts,
        "tags": tags,
        "excluded_tags": register.get("_excluded_tags", []),
        "exit": max(floors) if floors else CLEAN,
    }


def reading_map(presence: Dict[str, Any]) -> Dict[Tuple[str, str], bool]:
    """(asset, tag) -> did Stage 1 see it reading.

    This is the fact the engine does not have, and the one that tells
    `missing_property` on a dead sensor apart from `missing_property` on a
    mapping bug in this package. `feeder` may not classify those two without it.
    """
    return {(t["asset"], t["tag"]): t["state"] == READING
            for t in presence.get("tags", [])}
