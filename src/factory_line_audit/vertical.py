"""This package's domain, offered to `presence-audit`.

Stage 1 answers *which declared tags are reading* with its own code, in
`presence.py`, and that path has no dependencies at all. This module answers the
same question through the shared core instead: the register and the walk are
adapted onto `presence_audit.protocols`, the tag classes and the OPC UA
quality words become a `Vocabulary`, and `diff.compare()` does the pairing.

**Both paths are kept, and that is the point.** Stage 1's independence is a
property this package tests rather than promises, so the core cannot become a
hard dependency of it. What this module buys is the other half: a second domain
running on the core is the only evidence that the core is shared rather than one
domain's code behind an indirection -- and `tests/test_vertical_agrees.py` asserts
the two paths give the SAME three-valued answer on the same corpus. A port that
quietly changed a verdict would be a worse outcome than not porting.

Nothing here is imported by `presence`, `feeder`, `generator` or the CLI. Install
the `[vertical]` extra to get it; without that extra this file simply does not
import, and everything else is unaffected.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import presence

# Kinds. The register's declared classes are the auditable ones; the two below
# are what a classifier must be able to say about a type it was not given.
TEMPLATED = "templated"
UNRECOGNISED = "unrecognised_class"
KINDS: Tuple[str, ...] = presence.TAG_CLASSES + (TEMPLATED, UNRECOGNISED)


# --------------------------------------------------------------------------
# The register and the walk, as the core's protocols see them.
# --------------------------------------------------------------------------

class Tag:
    """One declared tag. `protocols.DeclaredPoint`, and nothing more."""

    def __init__(self, asset: Mapping[str, Any], tag: str,
                 spec: Mapping[str, Any], source: str) -> None:
        self._asset, self._tag, self._spec, self._source = asset, tag, spec, source

    @property
    def name(self) -> str:
        # The NODE id, not the tag name: it is what the walk serves points
        # under, and the core pairs on `name`. The human name is `display_name`.
        return self._spec["node"]

    @property
    def type(self) -> Optional[str]:
        return self._spec.get("class")

    @property
    def display_name(self) -> str:
        return f"{self._asset['id']}.{self._tag}"

    @property
    def source(self) -> str:
        return self._source

    @property
    def expects_reading(self) -> Optional[bool]:
        # Declined rather than answered. Every non-templated tag in a register is
        # expected to read, so this would only restate `disabled`, and the
        # protocol documents None as *this domain has no separate opinion*.
        return None

    @property
    def disabled(self) -> bool:
        return self._spec.get("templated") is True

    @property
    def is_templated(self) -> bool:
        return self._spec.get("templated") is True

    @property
    def thresholds(self) -> Sequence[object]:
        return ()


class Register:
    """`protocols.DeclarationSource` over a loaded register."""

    def __init__(self, register: Mapping[str, Any]) -> None:
        self._r = register

    @property
    def points(self) -> Iterable[Tag]:
        src = self._r.get("_path") or "register"
        return [Tag(asset, tag, spec, src)
                for asset in self._r.get("assets") or []
                for tag, spec in (asset.get("tags") or {}).items()]

    @property
    def sources(self) -> Sequence[object]:
        return (self._r.get("_path") or "register",)

    @property
    def anomalies(self) -> Sequence[object]:
        # `load_register` REFUSES rather than records: an unknown tag class or a
        # missing node id raises before anything sees the register. So a
        # register that got this far has none, and saying so is not the same as
        # not looking.
        return ()

    @property
    def unreadable(self) -> Sequence[Tuple[str, str]]:
        return ()


class Node:
    """One walked node. `protocols.CapturedPoint`, and nothing more."""

    def __init__(self, node: str, readings: Sequence[Mapping[str, Any]]) -> None:
        self._node, self._r = node, list(readings)
        self._graded = [presence.grade(r.get("q")) for r in self._r]

    @property
    def name(self) -> str:
        return self._node

    @property
    def path(self) -> str:
        return self._node

    @property
    def reading(self) -> Optional[float]:
        for (_, props), r in zip(reversed(self._graded), reversed(self._r)):
            if props["usable"] and r.get("v") is not None:
                return r["v"]
        return None

    @property
    def is_reading(self) -> bool:
        """Usable AND carrying a value -- Stage 1's rule, unchanged.

        A node the server served with `Bad` quality is PRESENT and NOT READING,
        which is exactly the distinction the three-valued answer exists for.
        """
        return any(props["usable"] and r.get("v") is not None
                   for (_, props), r in zip(self._graded, self._r))

    @property
    def state(self) -> Optional[str]:
        return self._graded[-1][0] if self._graded else None

    @property
    def thresholds(self) -> Mapping[Tuple[str, str], float]:
        return {}                       # NO COUNTERPART: OPC UA carries none here

    @property
    def units(self) -> Optional[str]:
        return None                     # NO COUNTERPART

    @property
    def is_enabled(self) -> bool:
        return True                     # nothing in a walk can be switched off

    @property
    def substituted_samples(self) -> int:
        """How many readings were typed at an HMI. Domain-only; see the note in
        `QUALITY_GRADES`. The core never asks for this -- `capture_findings`
        does, and that is a member of this domain's vocabulary."""
        return sum(1 for name, props in self._graded if props["substituted"])


class Walk:
    """`protocols.Capture` over a recorded OPC UA walk."""

    def __init__(self, walk: Mapping[str, Any]) -> None:
        self._w = walk
        self._index = presence.walk_index(walk)

    @property
    def points(self) -> Iterable[Node]:
        return [Node(node, readings) for node, readings in self._index.items()]

    @property
    def captured_at(self) -> Optional[str]:
        stamps = [s.get("t") for s in self._w.get("samples") or [] if s.get("t")]
        return stamps[-1] if stamps else None

    @property
    def complete(self) -> bool:
        """A walk that served no sample is not a walk that found nothing."""
        return bool(self._w.get("samples"))

    @property
    def errors(self) -> Sequence[Tuple[str, str]]:
        return ()


# --------------------------------------------------------------------------
# The vocabulary.
# --------------------------------------------------------------------------

class FactoryLineVocabulary:
    """Tag classes and OPC UA quality, as the core's `Vocabulary`."""

    @property
    def kinds(self) -> Sequence[str]:
        return KINDS

    @property
    def count_keys(self) -> Mapping[str, str]:
        return {TEMPLATED: "templated_tags", UNRECOGNISED: "unrecognised_class"}

    @property
    def noun(self) -> Sequence[str]:
        """A line has tags, not sensors. Until the core asked, its report told a
        press cell about its `Sensor coverage`."""
        return ("tag", "tags")

    def count_labels(self) -> Mapping[str, Sequence[str]]:
        """These two counts existed and were INVISIBLE in the text report: the
        core printed two keys by name and they were the other vertical's, so
        anything this domain set aside was in the JSON and nowhere a person
        looked."""
        return {
            "templated_tags": (
                "templated",
                "a name carrying a substitution; not a tag on its own"),
            "unrecognised_class": (
                "class unrecognised",
                "not classified either way; NOT counted as absent"),
        }

    def classify(self, declared_type: Optional[str]) -> str:
        if declared_type in presence.TAG_CLASSES:
            return declared_type
        return UNRECOGNISED

    def is_auditable(self, kind: str) -> bool:
        return kind in presence.TAG_CLASSES

    def is_expected_live(self, declared_type: Optional[str]) -> bool:
        return declared_type in presence.TAG_CLASSES

    def template_pattern(self, declared_name: str) -> object:
        """None, always, and deliberately.

        `LOOKS_TEMPLATED` exists and is NOT used here. This package refuses to
        read meaning out of a name: a tag is a template because the register
        says `templated: true`, which reaches the core through `is_templated`.
        Returning a pattern from the name list would make a naming convention
        decide what gets audited, which the review gate exists to prevent.
        """
        return None

    def same_point(self, old: object, new: object) -> bool:
        """One node id is one node. A domain with no evidence to the contrary
        says yes, and a node id IS the evidence here."""
        return getattr(old, "path", None) == getattr(new, "path", None)

    def captures_comparable(self, before: object, after: object) -> bool:
        """Two walks compare only if both actually served samples. False means
        the per-point comparisons are SKIPPED, not that they found nothing."""
        return bool(getattr(before, "complete", False)
                    and getattr(after, "complete", False))

    def point_changes(self, old: object, new: object, *,
                      comparable: bool = False) -> Sequence[object]:
        from presence_audit.regression import Change
        if not comparable:
            return ()
        was, now = getattr(old, "state", None), getattr(new, "state", None)
        if was == now:
            return ()
        return (Change(kind="quality_changed", sensor=getattr(new, "name", "?"),
                       detail=f"OPC UA quality went {was} -> {now}",
                       before_path=getattr(old, "path", None),
                       after_path=getattr(new, "path", None)),)

    def capture_changes(self, before: object, after: object) -> Sequence[object]:
        from presence_audit.regression import Change
        a = len(list(getattr(before, "points", ())))
        b = len(list(getattr(after, "points", ())))
        if a == b:
            return ()
        return (Change(kind="node_count_changed", sensor="(walk)",
                       detail=f"the server served {a} node(s), then {b}"),)

    def capture_findings(self, capture: object) -> Sequence[object]:
        """Substituted values -- the finding only this domain can make.

        A tag reading `Good_LocalOverride` is a number a person typed at an HMI.
        It is PRESENT and READING by every structural test the core applies, and
        judging an invariant on it asks a question about the operator rather
        than the machine. The core cannot know that; the pairing it does cannot
        see it; so it belongs here, beside the diff's own findings.
        """
        from presence_audit.diff import Finding
        out: List[object] = []
        for node in getattr(capture, "points", ()):
            n = getattr(node, "substituted_samples", 0)
            if n:
                out.append(Finding(
                    kind="substituted_value", sensor=node.name,
                    detail=(f"{n} sample(s) substituted at an HMI; this measures "
                            f"the operator, not the process"),
                    live_path=node.path))
        return out

    def peer_groups(self, declaration: object) -> Sequence[Mapping[str, object]]:
        """Empty, and this is a claim rather than a gap.

        Two `measurement` tags on one press are two different measurements, not
        two readings of one thing. This domain has no declared notion of
        redundancy, and inventing one from asset-and-class would pair a die
        temperature with a tonnage.
        """
        return ()

    def report_sections(self) -> Mapping[str, object]:
        return {"opcua_quality": _quality_payload}


def _quality_payload(capture: object) -> Mapping[str, Any]:
    """Every OPC UA quality word seen, counted. The core has no key for this."""
    counts: Dict[str, int] = {}
    for node in getattr(capture, "points", ()):
        for name, _props in getattr(node, "_graded", ()):
            counts[name] = counts.get(name, 0) + 1
    return {"grades": counts,
            "substituted_nodes": sum(
                1 for n in getattr(capture, "points", ())
                if getattr(n, "substituted_samples", 0))}


def register() -> str:
    from presence_audit import vocabulary as _vocabulary
    _vocabulary.register(FactoryLineVocabulary())
    return "factory-line: tag classes and OPC UA quality"
