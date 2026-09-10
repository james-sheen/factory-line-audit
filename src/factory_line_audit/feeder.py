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
    for (asset_id, tag), statements in by_key.items():
        for stmt in statements:
            if stmt["kind"] == "gate_on":
                gate_of[(asset_id, tag)] = stmt["required_property"]

    out: Dict[Tuple[str, str], List[Tuple]] = {}
    withheld: Dict[Tuple[str, str], int] = {}
    from .presence import grade
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
                gate_ok = bool(gate_row and grade(gate_row.get("q"))[1]["usable"]
                               and gate_row.get("v"))
                if not gate_ok:
                    withheld[key] = withheld.get(key, 0) + 1
                    continue
            when_row = _parse(reading_row.get("t")) or when
            out.setdefault(key, []).append((when_row, reading_row["v"]))
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
