"""Stage 2: feed the engine, and turn what comes back into an exit code.

BRIDGES C5 and C6. The engine is imported inside `run` and nowhere else in this
package, which is what lets Stage 1 run with it uninstalled.

Two things here are load-bearing and neither is obvious.

**Only what Stage 1 saw reading is fed.** The engine's `missing_property`
decline stays as the belt to that brace -- if it fires on a tag Stage 1 called
reading, the value did not survive this module, and that is a defect here rather
than in the plant.

**The model is checked for values this engine did not understand, through
`model_describe`.** `check` grew a `dropped_declarations` leg after 0.1.10, so a
bridge that reads it there has a hard stop that silently does not exist on the
version its own range floor resolves. `model_describe` reports the same fact on
both, so that is where this reads it from.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional, Tuple

from . import formats
from .exit_contract import (CLEAN, FINDINGS, FINDING_CLASSES, INCOMPLETE,
                            classify, classify_finding, compose, floor_of,
                            VOCABULARY_AT_DESIGN_TIME)
from .generator import PER_INTERVAL_SUFFIX, entity_type_for
from .presence import READING, reading_map

SCHEMA_VERSION = 1


class HardStop(Exception):
    """A condition under which no verdict may be reported. Always exit 2."""

    def __init__(self, name: str, detail: str):
        self.name, self.detail = name, detail
        super().__init__(f"{name}: {detail}")


def _parse(stamp: Any) -> Optional[_dt.datetime]:
    if not stamp:
        return None
    text = str(stamp).replace("Z", "+00:00")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


#: The manifest reasons a DECLINE can agree with. `no_declared_reset` is not one
#: and must not become one: the engine declines nothing when a counter says
#: nothing about resetting -- it routes from its own default and is silent about
#: having done so, which is why that gap is recorded in the manifest at all.
RECORDED_GAPS: Tuple[str, ...] = ("no_declared_rate", "no_declared_bound")


def series_for(register, presence, walk, gated) -> Dict[Tuple[str, str], List[Tuple]]:
    """(asset, tag) -> [(when, value)], for reading tags only, gate applied.

    The gate is applied HERE rather than in the model. The engine's
    `required_property` is read by CONNECTIVITY alone, so a machine-state gate
    on a BOUNDEDNESS check is not expressible there; feeding only the samples
    taken while the machine was in the declared state is the same statement made
    where this bridge can make it. What it costs is visibility: the engine sees
    a shorter series, not a gated one, and cannot report the gate firing. That
    is why the count of withheld samples is recorded in the attestation.
    """
    from .declarations import collect
    by_key = collect(gated["accepted"])
    reading = reading_map(presence)
    node_of: Dict[Tuple[str, str], str] = {}
    gate_of: Dict[Tuple[str, str], str] = {}
    state_nodes: Dict[str, Dict[str, str]] = {}
    for asset in register["assets"]:
        for tag, spec in (asset.get("tags") or {}).items():
            if spec["class"] == "state":
                # A state word is fed as a PROPERTY and never as a series. The
                # generator emits no indicator for it, so a series would be an
                # observation no declared indicator reads -- which the engine
                # reports through `unconsumed_observations`, and which this
                # package treats as a hard stop because it means the model and
                # the feed disagree about what is being checked.
                state_nodes.setdefault(asset["id"], {})[tag] = spec["node"]
                continue
            node_of[(asset["id"], tag)] = spec["node"]
    open_when: Dict[Tuple[str, str], List[str]] = {}
    for (asset_id, tag), statements in by_key.items():
        for stmt in statements:
            if stmt["kind"] == "gate_on":
                gate_of[(asset_id, tag)] = stmt["required_property"]
                if stmt.get("open_when") is not None:
                    open_when[(asset_id, tag)] = list(stmt["open_when"])

    out: Dict[Tuple[str, str], List[Tuple]] = {}
    withheld: Dict[Tuple[str, str], int] = {}
    #: Per gated tag: did ANY sample serve a state that a declared word could
    #: have equalled, and what types were actually served. Both are whole-walk
    #: facts, so both are settled after the loop.
    comparable: Dict[Tuple[str, str], bool] = {}
    observed: Dict[Tuple[str, str], Dict[str, Any]] = {}
    #: Per gated tag: was the gate's own node ever READABLE, and what quality
    #: the server reported when it was not. A gate unreadable for the whole walk
    #: withholds every sample without ever reaching the comparison above, so
    #: `comparable` has no entry for it and the mismatch stop cannot fire --
    #: the tag was simply never fed, the engine declined `missing_property`, and
    #: this package classed its own report as a mapping bug in itself.
    gate_readable: Dict[Tuple[str, str], bool] = {}
    gate_quality: Dict[Tuple[str, str], Dict[str, int]] = {}
    from .presence import grade

    def _comparable(state: Any, word: Any) -> bool:
        """Could `state == word` ever be true, on type alone?

        Strings compare with strings; numbers and booleans compare with each
        other, because a PLC `BOOL` arrives as `True` and a declaration may
        legitimately write `1` for it. Nothing else is asserted: whether the
        word is the RIGHT one is the declaration's claim, not this function's.
        """
        if isinstance(state, str) or isinstance(word, str):
            return isinstance(state, str) and isinstance(word, str)
        return isinstance(state, (int, float, bool)) and \
            isinstance(word, (int, float, bool))

    for sample in walk.get("samples") or []:
        when = _parse(sample.get("t"))
        nodes = sample.get("nodes") or {}
        for key, node in node_of.items():
            if not reading.get(key):
                continue
            reading_row = nodes.get(node)
            if not reading_row:
                continue
            _, props = grade(reading_row.get("q"))
            if not props["usable"] or reading_row.get("v") is None:
                continue
            gate_prop = gate_of.get(key)
            if gate_prop:
                gate_node = state_nodes.get(key[0], {}).get(gate_prop)
                gate_row = nodes.get(gate_node) if gate_node else None
                usable_gate = bool(gate_row
                                   and grade(gate_row.get("q"))[1]["usable"])
                # Recorded for every sample in which this gate MATTERED: the
                # reading above is usable, so the only reason to withhold is the
                # gate. Settled after the walk, like the mismatch below.
                gate_readable[key] = gate_readable.get(key, False) or usable_gate
                if not usable_gate:
                    word = ((gate_row or {}).get("q") if gate_row
                            else "not served in this sample")
                    counts = gate_quality.setdefault(key, {})
                    counts[str(word)] = counts.get(str(word), 0) + 1
                    withheld[key] = withheld.get(key, 0) + 1
                    continue
                state = gate_row.get("v")
                words = open_when.get(key)
                if words is not None:
                    # WHETHER THIS DECLARATION COULD EVER APPLY, recorded per
                    # gated tag and judged after the walk rather than here. `1
                    # in ["1"]` is false, so a PLC serving Int16 0/1 against
                    # `open_when: ["1"]` withheld every sample, fed nothing, and
                    # the engine then declined `missing_property` -- which this
                    # package classes as its own defect, reported against the
                    # wrong subject.
                    #
                    # Per-SAMPLE is the wrong scope and that was measured: one
                    # odd reading of a different type is not a declaration that
                    # cannot apply, and a station that really is stopped serves
                    # a word of the declared type and must withhold quietly. The
                    # claim is about the WALK -- no sample in it could ever have
                    # opened this gate -- so it is settled once, below, where
                    # the whole walk has been seen.
                    comparable[key] = comparable.get(key, False) or \
                        any(_comparable(state, word) for word in words)
                    observed.setdefault(key, {})[type(state).__name__] = state
                    gate_ok = state in words
                elif isinstance(state, bool):
                    gate_ok = state
                else:
                    # NOT truthiness. `bool("Stopped")` is True, so a gate read
                    # that way opens on every state word a PLC can produce and
                    # withholds nothing -- the check runs on samples taken while
                    # the machine was stopped, and reports a verdict about them.
                    # Which words mean running is a fact about the state machine,
                    # so the package stops rather than guesses.
                    raise HardStop(
                        "gate_undecidable",
                        f"{key[0]}.{key[1]} is gated on {gate_prop}, whose value "
                        f"is {state!r} ({type(state).__name__}) rather than a "
                        f"boolean, and the declaration lists no open_when. "
                        f"Declare the state words that mean the check applies")
                if not gate_ok:
                    withheld[key] = withheld.get(key, 0) + 1
                    continue
            when_row = _parse(reading_row.get("t")) or when
            out.setdefault(key, []).append((when_row, reading_row["v"]))

    # A gate whose OWN tag never read, across a walk in which it mattered. This
    # comes first because it is the more basic fact: there was nothing to
    # compare, so the mismatch stop below cannot speak for it, and until 0.1.9
    # nothing did -- every sample was withheld, the tag was never fed, and the
    # engine's `missing_property` was classed `bridge_defect`, which says "a
    # mapping bug in this package" about a state tag the SERVER could not read.
    # A check that fires against the wrong subject is worse than one that stays
    # quiet, and this one also floored the run at 2 for it.
    for key, readable in sorted(gate_readable.items()):
        if readable:
            continue
        counts = gate_quality.get(key) or {}
        total = sum(counts.values())
        # THE MESSAGE SAYS WHAT THE PREDICATE MEASURED, and the two are not the
        # same sentence. This is recorded only for samples in which the gated
        # tag ITSELF read -- the samples that should have been fed -- so the
        # claim is about those, not about the whole walk. A gate readable
        # somewhere the gated tag was not reading would make the wider sentence
        # false while this stop was still right to fire.
        raise HardStop(
            "gate_unreadable",
            f"{key[0]}.{key[1]} read usably in {total} sample(s) and its gate "
            f"{gate_of.get(key)} read usably in none of them: "
            f"{', '.join(f'{word} x{n}' for word, n in sorted(counts.items()))}"
            f". Every one was withheld because the gate could not be consulted, "
            f"so nothing was fed and the engine would decline for a missing "
            f"property -- which this package classes as its own mapping defect. "
            f"It is not one: the state tag is what could not be read. Stage 1 "
            f"grades {gate_of.get(key)} on the same walk; fix it at the source, "
            f"or declare a gate on a tag that reads")

    # A gate that was evaluated and could never once have opened, on type
    # alone. Settled here because it is a claim about the walk: the loop sees
    # one sample at a time and cannot tell a mixed reading from a declaration
    # written against the wrong data type.
    for key, ever in sorted(comparable.items()):
        if ever:
            continue
        words = open_when.get(key) or []
        served = observed.get(key) or {}
        raise HardStop(
            "gate_type_mismatch",
            f"{key[0]}.{key[1]} is gated on {gate_of.get(key)}, which served "
            f"only "
            f"{', '.join(f'{v!r} ({t})' for t, v in sorted(served.items()))} "
            f"across this walk, and open_when lists "
            f"{', '.join(f'{w!r} ({type(w).__name__})' for w in words)}. No "
            f"declared value can equal any value served, so every sample was "
            f"withheld and the engine would decline for a missing property "
            f"instead -- a defect this package would have reported against the "
            f"wrong subject. Declare the state in the type the server serves")
    return out, withheld, gate_of


def _per_interval(register, gated, series):
    """First differences for every tag in a declared balance.

    The engine compares levels, so a lifetime counter's balance sits against a
    lifetime total. Differencing here rather than in the model is the bridge
    owning what gets fed -- and the derived names are in the manifest, because
    a finding on an indicator no operator declared has to be traceable to
    whoever invented it.
    """
    from .declarations import collect
    out = {}
    for (asset_id, _), statements in collect(gated["accepted"]).items():
        for stmt in statements:
            if stmt["kind"] != "conservation":
                continue
            for tag in [stmt.get("input_tag")] + list(stmt.get("output_tags") or []):
                points = series.get((asset_id, tag))
                if not points or len(points) < 2:
                    continue
                out[(asset_id, tag + PER_INTERVAL_SUFFIX)] = [
                    (when, float(value) - float(points[n][1]))
                    for n, (when, value) in enumerate(points[1:])]
    return out


def unreachable_floors(walk, floors: Dict[str, Any]) -> Dict[str, str]:
    """Which measured floors this collector's cadence can never present.

    BRIDGES, `insufficient_samples`: *a floor is a count taken inside a window,
    so a corpus can hold many times the floor and still never present it*. If
    the cadence times the sample floor exceeds the window, the check was
    promised and cannot be delivered, and this bridge floors that at 1.
    """
    cadence = (walk.get("source") or {}).get("cadence_s")
    out: Dict[str, str] = {}
    if not cadence:
        return out
    for name, spec in (floors.get("floors") or {}).items():
        widest = spec.get("max_cadence_s")
        if not widest:
            continue
        if float(cadence) > float(widest):
            out[name] = (f"the {spec.get('samples')}-sample floor is reachable "
                         f"only at a cadence of {widest}s or faster (measured, "
                         f"probe H2); this walk collects every {cadence}s")
    return out


def run(model_text: str, register, presence, walk, gated, manifest,
        floors: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Feed, read the envelope, classify every decline, compose the exit."""
    try:
        from arbiter_engine.api import EngineSession, check, model_describe
        from arbiter_engine.types import NotEvaluatedReason
        import arbiter_engine
    except ImportError as exc:
        raise HardStop("engine_absent",
                       f"Stage 2 needs the engine: {exc}. Install the [detect] "
                       f"extra; Stage 1 runs without it")

    live_vocabulary = tuple(sorted(r.value for r in NotEvaluatedReason))
    session = EngineSession()
    session.load_model(model_text)

    described = model_describe(session).to_dict()
    dropped = [f for f in (described.get("model") or {}).get("unread_fields", [])
               if f.get("reason") == "unknown_value"]
    if dropped:
        raise HardStop("dropped_declarations",
                       "this engine did not understand values this package "
                       "generated, so checks that were declared did not run: "
                       + "; ".join(f"{d.get('field')}={d.get('value')!r} on "
                                   f"{d.get('entity_type')}.{d.get('indicator')}"
                                   for d in dropped))

    series, withheld, gate_of = series_for(register, presence, walk, gated)
    derived = _per_interval(register, gated, series)
    series.update(derived)
    reading = reading_map(presence)
    fed_assets: Dict[str, str] = {}
    for asset in register["assets"]:
        etype = entity_type_for(asset)
        if etype not in (manifest.get("entity_type_map") or {}):
            continue
        tags = [t for t in (asset.get("tags") or {})
                if reading.get((asset["id"], t)) and (asset["id"], t) in series]
        if not tags:
            continue
        properties = {t: series[(asset["id"], t)][-1][1] for t in tags}
        for (owner, tag), points in series.items():
            if owner == asset["id"] and tag.endswith(PER_INTERVAL_SUFFIX) and points:
                properties[tag] = points[-1][1]
        for tag, spec in (asset.get("tags") or {}).items():
            if spec["class"] == "state" and reading.get((asset["id"], tag)):
                last = [s for s in (walk.get("samples") or [])
                        if spec["node"] in (s.get("nodes") or {})]
                if last:
                    properties[tag] = last[-1]["nodes"][spec["node"]].get("v")
        session.add_entity(asset["id"], etype, properties=properties)
        fed_assets[asset["id"]] = etype

    for (asset_id, tag), points in series.items():
        if asset_id in fed_assets:
            session.add_observations(asset_id, tag, points)

    for asset in register["assets"]:
        if asset["id"] not in fed_assets:
            continue
        for relation in asset.get("relations") or []:
            if relation.get("target") in fed_assets and relation.get("required"):
                # (source, relation_type, target) -- the middle argument is the
                # EDGE, not the far end. Passing the target there produced four
                # missing_relationship findings on a clean corpus, and they read
                # exactly like a real broken conveyor.
                session.add_relationship(asset["id"], relation["type"],
                                         relation["target"])

    envelope = check(session).to_dict()
    meta = envelope.get("meta") or {}
    if meta.get("schema_version") != SCHEMA_VERSION:
        raise HardStop("schema_version",
                       f"envelope schema_version {meta.get('schema_version')!r}; "
                       f"this reader understands {SCHEMA_VERSION}")
    if meta.get("source") == "unavailable":
        raise HardStop("engine_unavailable",
                       "the engine returned an unavailable envelope; nothing "
                       "in it is a measurement")
    attempted = (envelope.get("checked") or {}).get("invariants", 0)
    if attempted == 0:
        raise HardStop("zero_invariants",
                       "the engine attempted no invariants. A clean result over "
                       "an empty denominator is not a clean result")
    unconsumed = list(session.unconsumed_observations() or [])
    if unconsumed:
        raise HardStop("unconsumed_observations",
                       "series were fed that no declared indicator reads, so "
                       "this package modelled something it then did not check: "
                       + ", ".join(str(u) for u in unconsumed[:8]))

    absent_assets = {row["asset"] for row in presence.get("tags", [])
                     if row["state"] == "absent"}
    fully_absent = {asset["id"] for asset in register["assets"]
                    if asset["id"] in absent_assets
                    and all(row["state"] == "absent"
                            for row in presence.get("tags", [])
                            if row["asset"] == asset["id"])}
    targets = manifest.get("relationship_targets") or {}
    # Every gap this package excluded ON PURPOSE and wrote into the manifest.
    # The engine declining one of these is the two records agreeing.
    recorded = {(row.get("asset"), row.get("tag"))
                for row in manifest.get("exclusions") or []
                if row.get("reason") in RECORDED_GAPS}
    unreachable = unreachable_floors(walk, floors or {})
    classes: List[Dict[str, Any]] = []
    for row in envelope.get("not_checked") or []:
        reason = row.get("reason")
        entity = row.get("entity_id")
        indicator = row.get("indicator") or row.get("property")
        stage1 = reading.get((entity, indicator))
        axiom = row.get("axiom")
        target = targets.get(f"{fed_assets.get(entity, '')}.{indicator}")
        name = classify(reason, stage1_said_reading=stage1,
                        recorded_gap=(entity, indicator) in recorded,
                        target_absent=(target in fully_absent
                                       if target is not None else None),
                        floor_unreachable=bool(unreachable) and
                        reason == "insufficient_samples" and
                        axiom in unreachable)
        classes.append({"class": name, "floor": floor_of(name), "reason": reason,
                        "axiom": axiom, "entity": entity, "indicator": indicator,
                        "engine_detail": row.get("detail"),
                        "engine_remedy": row.get("remedy")})

    learned = set(manifest.get("learned_baselines") or [])
    findings = []
    for row in envelope.get("findings") or []:
        key = f"{row.get('entity_id')}.{str(row.get('problem_type', '')).rpartition(':')[2]}"
        name = classify_finding(row.get("axiom"), row.get("severity"),
                                learned_baseline=key in learned)
        findings.append({"class": name,
                         "floor": FINDING_CLASSES[name]["floor"],
                         "learned_baseline": key in learned, "finding": row})

    legs = [CLEAN]
    legs.append(presence.get("exit", CLEAN))
    legs.extend(f["floor"] for f in findings)
    legs.extend(c["floor"] for c in classes)
    if sorted(live_vocabulary) != sorted(VOCABULARY_AT_DESIGN_TIME):
        legs.append(INCOMPLETE)

    return {
        "envelope": envelope,
        "findings_classified": findings,
        "engine_version": getattr(arbiter_engine, "__version__", "unknown"),
        "declines": classes,
        "unreachable_floors": unreachable,
        # WHICH measurement was in force. An empty `unreachable_floors` has two
        # causes -- no floor is out of reach, or no floors were loaded at all --
        # and before 0.1.7 the installed tool always had the second one and said
        # nothing. The engine the floors were measured against is recorded beside
        # the engine that answered, because they can differ inside the declared
        # range and a reader is entitled to see that.
        "floors_measured_against": {
            "engine_version": (floors or {}).get("engine_version"),
            "measured_on": (floors or {}).get("measured_on"),
            "axioms": sorted((floors or {}).get("floors") or {}),
        },
        "withheld_by_gate": {f"{a}.{t}": n for (a, t), n in withheld.items()},
        "gates_declared": {f"{a}.{t}": p for (a, t), p in gate_of.items()},
        "unread_properties": list(session.unread_properties() or []),
        "vocabulary_live": list(live_vocabulary),
        "vocabulary_at_design_time": list(VOCABULARY_AT_DESIGN_TIME),
        "dropped_declarations_on_check":
            "dropped_declarations" in envelope,
        "fed": {"entities": len(fed_assets), "series": len(series)},
        "exit": compose(*legs),
    }
