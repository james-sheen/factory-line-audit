"""Register plus gated declarations -> a model and a manifest, as one pair.

BRIDGES C2. The model declares what gets fed; the manifest names everything
excluded and why. Emitting the first without the second turns *we chose not to
watch this* into *we forgot it exists*, and those are the two halves an audit
is for.

The YAML is written by this module rather than by a serialiser, so Stage 1 --
of which generation is a part -- keeps its promise to run with nothing
installed. The writer handles exactly the shapes a model uses, refuses anything
else, and the battery parses its output back with a real parser and compares.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from . import formats
from .declarations import collect

#: Every scope an exclusion row can carry. Here rather than in the suite,
#: which held the list by transcribing it -- and a transcribed vocabulary goes
#: stale on the day a member lands, with nothing able to go red.
SCOPES: Tuple[str, ...] = ("tag", "asset", "axiom", "axiom_arm", "relation",
                           "derived", "routing")

#: Suffix for the indicators this package DERIVES rather than reads.
#:
#: CONSERVATION compares levels and fires at a RELATIVE deficit, measured
#: between 5 % and 8 % and identical at both scales tried (probe K7). A
#: discrete line counts parts with lifetime counters, so a real
#: loss of forty parts sits against a lifetime total of nine thousand and is
#: 0.45 % -- invisible, and invisible in a way that gets quieter the longer the
#: line runs. MODELING.md's worked example balances `bytes_in` against
#: `bytes_out`, which reads as an endorsement of cumulative counters; it is one
#: for a gauge that resets, and not one for a counter that never does.
#:
#: So the balance is declared on the first difference of each counter, fed under
#: a derived name. Every derived indicator is in the manifest: an indicator an
#: operator never declared, appearing in a finding, must be traceable to the
#: package that invented it.
PER_INTERVAL_SUFFIX = "_per_interval"

#: Axioms this bridge will emit only when a declaration supplies the number
#: they need. Emitting them anyway would add invariants the engine can only
#: decline `no_threshold`, inflating the denominator with questions nobody
#: asked (BRIDGES on the decline vocabulary, `no_threshold`).
NEEDS_DECLARED_NUMBER = ("BOUNDEDNESS", "RESPONSIVENESS")


def sanitise(asset_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", asset_id).strip("_")


def entity_type_for(asset: Dict[str, Any]) -> str:
    """One entity type per real-world unit.

    Declared thresholds live on entity types, and the engine's per-entity
    override path does not reach a declared BOUNDEDNESS threshold
    (`api.OVERRIDE_DECLARED_BUT_UNREACHABLE`). Two presses with different die
    limits therefore need two types. The manifest carries the map back so an
    operator never has to read `Station__ST_01`.
    """
    return f"{asset['type']}__{sanitise(asset['id'])}"


def _yaml(value: Any, indent: int = 0) -> List[str]:
    pad = "  " * indent
    lines: List[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, dict) and item:
                lines.append(f"{pad}{key}:")
                lines.extend(_yaml(item, indent + 1))
            elif isinstance(item, list):
                if not item:
                    lines.append(f"{pad}{key}: []")
                elif all(isinstance(x, (str, int, float, bool)) for x in item):
                    inner = ", ".join(_scalar(x) for x in item)
                    lines.append(f"{pad}{key}: [{inner}]")
                else:
                    lines.append(f"{pad}{key}:")
                    for element in item:
                        body = _yaml(element, indent + 2)
                        body[0] = pad + "  - " + body[0].lstrip()
                        lines.extend(body)
            else:
                lines.append(f"{pad}{key}: {_scalar(item)}")
        return lines
    raise TypeError(f"the model writer handles maps, lists and scalars; "
                    f"got {type(value).__name__}")


#: Words a YAML 1.1 parser reads as something other than a string, IN ANY CASE.
#:
#: The engine loads models with `yaml.safe_load`, and PyYAML resolves YAML 1.1:
#: `Off`, `OFF`, `No`, `Yes`, `On`, `True`, `Null` and their case variants are
#: booleans and nulls, not words. This list was lowercase-only, so a `bad_state`
#: declaring the PLC state word `Off` emitted `bad: [Off, Fault]` and the engine
#: read `[False, "Fault"]`. The fed property is the string `"Off"`, which never
#: equals `False`, so the declared bad state could not fire -- and probe D1
#: measured that `unread_fields` says nothing about `bad:`, so no surface
#: anywhere reported it. `On` and `Yes` fail the other way: they become `True`,
#: which a state tag fed a real boolean would MATCH.
#:
#: The suite derives this set from the parser rather than trusting the list.
YAML_ONE_ONE_WORDS = ("true", "false", "null", "yes", "no", "on", "off", "y", "n")


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    if (text and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]*", text)
            and text.lower() not in YAML_ONE_ONE_WORDS):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _statements(by_key, asset_id: str, tag: Optional[str], kind: str) -> List[Dict]:
    return [s for s in by_key.get((asset_id, tag), []) if s.get("kind") == kind]


def build(register: Dict[str, Any], gated: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Return (model_yaml_text, manifest)."""
    by_key = collect(gated["accepted"])
    exclusions: List[Dict[str, Any]] = []
    for row in register.get("_excluded_tags", []):
        exclusions.append(dict(row, scope="tag"))

    excluded_assets = set()
    for (asset_id, tag), statements in by_key.items():
        for stmt in statements:
            if stmt["kind"] == "exclusion":
                scope = "tag" if tag else "asset"
                if scope == "asset":
                    excluded_assets.add(asset_id)
                exclusions.append({"scope": scope, "asset": asset_id, "tag": tag,
                                   "reason": "declared_exclusion",
                                   "detail": stmt.get("reason"),
                                   "basis": stmt.get("basis"),
                                   "declared_in": stmt["_from"]})

    entity_types: List[str] = []
    learned: List[str] = []
    rel_targets: Dict[str, str] = {}
    type_map: Dict[str, str] = {}
    indicators: Dict[str, List[Dict[str, Any]]] = {}
    relationship_types: List[str] = []
    counts = {"indicators": 0, "axioms": 0}

    live_assets = [a for a in register["assets"] if a["id"] not in excluded_assets]
    live_ids = {a["id"] for a in live_assets}

    for asset in live_assets:
        etype = entity_type_for(asset)
        entity_types.append(etype)
        type_map[etype] = asset["id"]
        rows: List[Dict[str, Any]] = []
        excluded_tags = {t for (a, t) in by_key
                         if a == asset["id"] and t and
                         _statements(by_key, a, t, "exclusion")}
        for tag, spec in (asset.get("tags") or {}).items():
            if tag in excluded_tags:
                continue
            row, dropped = _indicator(asset, tag, spec, by_key)
            exclusions.extend(dropped)
            if row is None:
                continue
            rows.append(row)
            if "HOMEOSTASIS" in (row.get("axioms") or []) and "homeostasis" not in row:
                learned.append(f"{asset['id']}.{tag}")
            counts["indicators"] += 1
            counts["axioms"] += len(row.get("axioms") or [])
        for stmt in _statements(by_key, asset["id"], None, "conservation"):
            derived, note = _conservation_rate(asset, stmt, excluded_tags)
            if derived is None:
                exclusions.append(note)
                continue
            rows.extend(derived)
            counts["indicators"] += len(derived)
            counts["axioms"] += sum(len(r.get("axioms") or []) for r in derived)
            exclusions.append(note)
        for relation in asset.get("relations") or []:
            if not relation.get("required"):
                exclusions.append({"scope": "relation", "asset": asset["id"],
                                   "tag": relation.get("type"),
                                   "reason": "relation_not_required",
                                   "detail": "the register does not declare "
                                             "this edge required; CONNECTIVITY "
                                             "would assert something nobody did"})
                continue
            target = relation.get("target")
            if target not in live_ids:
                exclusions.append({"scope": "relation", "asset": asset["id"],
                                   "tag": relation.get("type"),
                                   "reason": "relation_target_excluded",
                                   "detail": f"target {target} is not in the "
                                             f"model; asserting the edge would "
                                             f"be a missing_entity_type decline"})
                continue
            target_asset = next(a for a in live_assets if a["id"] == target)
            rel_type = relation["type"]
            if rel_type not in relationship_types:
                relationship_types.append(rel_type)
            rel_targets[f"{etype}.{rel_type}__{sanitise(target)}"] = target
            rows.append({
                "name": f"{rel_type}__{sanitise(target)}",
                "type": "RELATIONSHIP",
                "axioms": ["CONNECTIVITY"],
                "target_type": entity_type_for(target_asset),
                "relation_type": rel_type,
                "min_cardinality": 1,
            })
            counts["indicators"] += 1
            counts["axioms"] += 1
            # RECORDED, because the check cannot report what it looks like it
            # reports. The feeder adds this edge exactly when the register
            # declares it required and both ends were fed, so the engine is
            # confirming an edge this package asserted from the same register it
            # read the indicator from. Measured on the shipped corpus: no
            # CONNECTIVITY finding arises from a clean walk OR from one where
            # the target is entirely absent -- that case declines
            # `missing_entity_type` instead. A `missing_relationship` here means
            # the feeder failed to add an edge it should have, which is a defect
            # in this package and not a fault on the line.
            exclusions.append({
                "scope": "relation", "asset": asset["id"], "tag": rel_type,
                "reason": "relation_asserted_from_register",
                "detail": f"the edge to {target} is asserted by this bridge "
                          f"from the register and then confirmed by the engine, "
                          f"so this invariant counts toward `attempted` and "
                          f"cannot fail on plant evidence. A finding here would "
                          f"be a feed defect in this package. No walk evidence "
                          f"contradicts a declared edge: OPC UA serves nodes, "
                          f"not topology"})
        if rows:
            indicators[etype] = rows
        else:
            exclusions.append({"scope": "asset", "asset": asset["id"], "tag": None,
                               "reason": "no_indicators",
                               "detail": "no tag on this asset produced a "
                                         "checkable indicator"})

    model = {"domain": {
        "id": register.get("line") or "factory-line",
        "name": register.get("name") or register.get("line") or "Factory line",
        "entity_types": [e for e in entity_types if e in indicators],
        "relationship_types": relationship_types,
        "indicators": indicators,
    }}
    if not relationship_types:
        model["domain"].pop("relationship_types")

    text = "\n".join(
        ["# GENERATED by factory-line-audit. Every exclusion is in the manifest",
         "# emitted beside it; the two are one artifact in two files.", ""]
        + _yaml(model)) + "\n"

    manifest = {
        "format": formats.MANIFEST,
        "line": register.get("line"),
        "entity_type_map": type_map,
        "counts": {
            "assets_in_register": len(register["assets"]),
            "assets_modelled": len(model["domain"]["entity_types"]),
            "assets_excluded": len(register["assets"]) - len(model["domain"]["entity_types"]),
            "indicators": counts["indicators"],
            "axiom_declarations": counts["axioms"],
            "exclusions": len(exclusions),
        },
        "learned_baselines": learned,
        # Which asset each CONNECTIVITY indicator points at. Without this, a
        # `missing_entity_type` decline names an entity TYPE this package
        # invented and nothing can say which real station it meant.
        "relationship_targets": rel_targets,
        "exclusions": exclusions,
        "declaration_reviews": gated["reviews"],
    }
    return text, manifest


def _conservation_rate(asset, stmt, excluded_tags):
    """The derived per-interval indicators for one conservation statement."""
    tags = [stmt.get("input_tag")] + list(stmt.get("output_tags") or [])
    missing = [t for t in tags if t not in (asset.get("tags") or {})
               or t in excluded_tags]
    if missing:
        return None, {"scope": "axiom", "asset": asset["id"], "tag": None,
                      "axiom": "CONSERVATION", "reason": "balance_incomplete",
                      "detail": f"the declared balance names {missing}, which "
                                f"this model does not carry; a balance with a "
                                f"missing half is a check the engine cannot run"}
    rows = [{
        "name": stmt["input_tag"] + PER_INTERVAL_SUFFIX,
        "type": "NUMERIC", "axioms": ["CONSERVATION"], "flow": "in",
        "conservation": {
            "input_property": stmt["input_tag"] + PER_INTERVAL_SUFFIX,
            "output_properties": [t + PER_INTERVAL_SUFFIX
                                  for t in stmt["output_tags"]]},
    }]
    for out_tag in stmt["output_tags"]:
        # No `axioms:` key at all rather than an empty list. The output half of
        # a balance is read as a property; declaring it with an empty axiom list
        # would be declaring an indicator that answers nothing.
        rows.append({"name": out_tag + PER_INTERVAL_SUFFIX,
                     "type": "NUMERIC", "flow": "out"})
    note = {"scope": "derived", "asset": asset["id"], "tag": None,
            "axiom": "CONSERVATION", "reason": "derived_per_interval_indicator",
            "detail": f"this package derived {[r['name'] for r in rows]} as the "
                      f"first difference of {tags}. No operator declared these "
                      f"names; a finding on one of them is a finding about "
                      f"{tags}",
            "basis": stmt.get("basis"), "declared_in": stmt["_from"]}
    return rows, note


def _indicator(asset, tag, spec, by_key):
    """One tag -> at most one indicator, plus the exclusions it generated."""
    asset_id = asset["id"]
    cls = spec["class"]
    dropped: List[Dict[str, Any]] = []
    axioms: List[str] = []
    row: Dict[str, Any] = {"name": tag, "type": "NUMERIC"}

    bounds = _statements(by_key, asset_id, tag, "bound")
    setpoints = _statements(by_key, asset_id, tag, "setpoint")
    rates = _statements(by_key, asset_id, tag, "rate")
    redundant = _statements(by_key, asset_id, tag, "redundant")
    conserve = _statements(by_key, asset_id, None, "conservation")
    variation = _statements(by_key, asset_id, tag, "expect_variation")
    slow = _statements(by_key, asset_id, tag, "slow_oscillation")
    gate_on = _statements(by_key, asset_id, tag, "gate_on")

    if cls == "state":
        bad_states = _statements(by_key, asset_id, tag, "bad_state")
        if not bad_states:
            dropped.append({"scope": "tag", "asset": asset_id, "tag": tag,
                            "reason": "state_tag_is_not_an_indicator",
                            "detail": "fed as a property so other checks can be "
                                      "gated on it. STABILITY judges a state "
                                      "word against a declared `bad:` from "
                                      "0.1.12, so what is missing is a review: "
                                      "no `bad_state` declaration names a word "
                                      "for this tag. Until 2026-09-09 this line "
                                      "gave the engine's capability as the "
                                      "reason, which is a different claim and "
                                      "was retired at that release."})
            return None, dropped
        words = list(bad_states[0]["states"])
        row.update({"name": tag, "type": "STATE", "axioms": ["STABILITY"],
                    "bad": words})
        dropped.append({"scope": "axiom", "asset": asset_id, "tag": tag,
                        "axiom": "STABILITY", "reason": "bad_state_is_pinned",
                        "detail": f"{len(words)} reviewed word(s) declared bad. "
                                  f"The engine fires `declared_bad_state` from "
                                  f"0.1.12 and is SILENT below it -- accepted, "
                                  f"no finding, and `unread_fields` does not "
                                  f"report it. At a resolved engine under "
                                  f"0.1.12 this declaration does nothing and "
                                  f"nothing else will say so."})
        # No `normal:` is emitted. Measured: `bad:` alone fires, and a word in
        # neither list produces nothing either way -- so a `normal:` this
        # package invented would be a claim nobody reviewed.
        return row, dropped

    if cls in ("latency",):
        row["role"] = "latency"
    elif cls == "percentage":
        row["role"] = "percentage"
    elif cls == "count":
        row["role"] = "count"
    elif cls == "counter":
        row["role"] = "count"

    if bounds:
        stmt = bounds[0]
        for field in ("warning", "critical", "lower_warning", "lower_critical"):
            if stmt.get(field) is not None:
                row[field] = stmt[field]
        axioms.append("BOUNDEDNESS")
        if cls == "latency" and stmt.get("critical") is not None:
            axioms.append("RESPONSIVENESS")
    else:
        for axiom in NEEDS_DECLARED_NUMBER:
            if axiom == "RESPONSIVENESS" and cls != "latency":
                continue
            dropped.append({
                "scope": "axiom", "asset": asset_id, "tag": tag, "axiom": axiom,
                "reason": "no_declared_bound",
                "detail": "no reviewed bound declaration supplies a number. "
                          "Declaring the axiom anyway would add an invariant "
                          "the engine can only decline no_threshold"})

    if cls in ("measurement", "latency", "percentage"):
        axioms.append("HOMEOSTASIS")
        if setpoints:
            stmt = setpoints[0]
            block = {"setpoint": stmt["setpoint"], "tolerance": stmt["tolerance"]}
            if stmt.get("tolerance_critical") is not None:
                block["tolerance_critical"] = stmt["tolerance_critical"]
            row["homeostasis"] = block
        elif cls == "percentage":
            row["direction"] = "LOWER"

    if cls == "percentage":
        axioms.append("CONSISTENCY")
    if cls in ("count", "counter"):
        axioms.append("CONSISTENCY")

    if cls == "counter":
        axioms.append("MONOTONICITY")
        block: Dict[str, Any] = {"expected_direction": "increasing"}
        if rates:
            stmt = rates[0]
            for field in ("rate_warning", "rate_critical"):
                if stmt.get(field) is not None:
                    block[field] = stmt[field]
        else:
            dropped.append({
                "scope": "axiom_arm", "asset": asset_id, "tag": tag,
                "axiom": "MONOTONICITY.rate", "reason": "no_declared_rate",
                "detail": "no reviewed rate declaration. MEASURED ACROSS THE "
                          "DECLARED RANGE, and the behaviour splits: at 0.1.10 "
                          "the engine answers this arm from its own default "
                          "rather than declining, and from 0.1.11 it declines "
                          "`no_threshold` -- six more declines on this fixture, "
                          "which is what `pin_evidence.json` now records per "
                          "release. Either way the arm runs against a number "
                          "nobody in this "
                          "plant chose -- see probe R1 and the finding titled "
                          "`The MONOTONICITY rate arm answers from a default rather than declining`"})
        # NO SEGMENTATION HERE, and that is a decision rather than an omission.
        #
        # A `reset_schedule` was specified for this package: cut the series at
        # each scheduled counter reset and feed only the last segment, so a shift
        # reset could not fire the reversal arm. Measured (probes T1, A1-A4, A6)
        # it protects against nothing that happens:
        #
        #   T1  the reversal window is bounded by a sample count AND a duration,
        #       whichever is shorter. A scheduled reset is hours old and outside
        #       the duration bound at any cadence, so it never reaches the arm.
        #   A6  with `allow_reset` absent -- which is what a declaration that
        #       says nothing produces -- a drop to near zero is routed to the
        #       RESET arm and the reversal arm never fires at all.
        #   A1  that arm needs THREE drops inside the window to say anything.
        #
        # So one reset inside the window is silent, and what does fire is three
        # resets in a quarter of an hour -- which is not a shift change, it is
        # `monotonicity_reset_storm`, and reporting it is the point.
        #
        # The alternative once written down here was `allow_reset: false` with
        # `reversal_tolerance: 1`. A2 and A4 measure what that does: `false`
        # ROUTES drops to the reversal arm, and a tolerance of 1 fires on the
        # first one. It reads as the cautious option and would turn a silent
        # non-event into a finding at every reset.
        #
        # C.2, and it is the asking rather than the answer. Three states, and
        # the model cannot tell them apart on its own: DECLARED carries a
        # basis; UNANSWERED was asked and nobody knew; absent was never asked.
        # The last two produce the same model and must not produce the same
        # record.
        resets = _statements(by_key, asset_id, tag, "reset")
        if resets and resets[0].get("allow_reset") is not None:
            block["allow_reset"] = resets[0]["allow_reset"]
        elif resets:
            dropped.append({
                "scope": "routing", "asset": asset_id, "tag": tag,
                "axiom": "MONOTONICITY", "reason": "reset_unanswered",
                "basis": resets[0].get("basis"),
                "detail": "asked and unanswered: `allow_reset` is declared null "
                          "with a basis, so the engine routes a drop to near "
                          "zero to the reset arm from its own default (probe "
                          "A6). Recorded because this reads as a choice and an "
                          "absent declaration does not"})
        else:
            dropped.append({
                "scope": "routing", "asset": asset_id, "tag": tag,
                "axiom": "MONOTONICITY", "reason": "no_declared_reset",
                "detail": "nobody declared whether this counter is zeroed in "
                          "normal operation. A drop to near zero is routed to "
                          "the reset arm by the engine's default (probe A6), so "
                          "this arm runs as though resetting were normal for "
                          "this tag -- chosen by the engine rather than by "
                          "anybody who has seen the line. The engine declines "
                          "nothing here, so no decline will ever report it"})
        row["monotonicity"] = block

    if variation:
        axioms.append("STABILITY")
        row["expect_variation"] = True
        if slow:
            stmt = slow[0]
            row["stability"] = {"detect_slow_oscillation": True,
                                "min_amplitude": stmt["min_amplitude"],
                                "min_crossings": stmt["min_crossings"]}
    elif slow:
        axioms.append("STABILITY")
        stmt = slow[0]
        row["stability"] = {"detect_slow_oscillation": True,
                            "min_amplitude": stmt["min_amplitude"],
                            "min_crossings": stmt["min_crossings"]}

    if redundant:
        stmt = redundant[0]
        if "CONSISTENCY" not in axioms:
            axioms.append("CONSISTENCY")
        row["consistency"] = {"agrees_with": list(stmt["agrees_with"]),
                              "tolerance": stmt["tolerance"]}

    if conserve and (any(s.get("input_tag") == tag for s in conserve)
                     or any(tag in (s.get("output_tags") or []) for s in conserve)):
        dropped.append({
            "scope": "axiom", "asset": asset_id, "tag": tag,
            "axiom": "CONSERVATION", "reason": "balanced_on_the_derived_rate",
            "detail": f"{tag} is a lifetime counter and CONSERVATION compares "
                      f"LEVELS at a relative threshold measured between 5 % and "
                      f"8 % (probe K7). Against a lifetime total that is "
                      f"a loss of hundreds of parts, so the balance is declared "
                      f"on the derived per-interval rate instead -- see the "
                      f"{PER_INTERVAL_SUFFIX} indicators"})

    if gate_on:
        dropped.append({
            "scope": "axiom_arm", "asset": asset_id, "tag": tag,
            "axiom": "(gate)", "reason": "gate_not_expressible_on_this_axiom",
            "detail": "a gate_on declaration was made. The engine's "
                      "required_property gate is read by CONNECTIVITY only, so "
                      "this bridge applies the gate at feed time instead -- see "
                      "probe G1 and the finding titled `required_property is "
                      "read by CONNECTIVITY only, and check will not tell you`"})

    if not axioms:
        dropped.append({"scope": "tag", "asset": asset_id, "tag": tag,
                        "reason": "no_axiom_reachable",
                        "detail": f"tag class {cls} with no declaration "
                                  f"supplies nothing checkable"})
        return None, dropped

    row["axioms"] = axioms
    ordered = {k: row[k] for k in ("name", "type", "role", "direction", "axioms")
               if k in row}
    ordered.update({k: v for k, v in row.items() if k not in ordered})
    return ordered, dropped
