"""The attestation artifact and the human report.

BRIDGES C7: report three ways -- checked, declined, not-established -- so that
silence is impossible, and quote the engine's boundary strings verbatim.

The third leg is the one that is easy to drop, and it is the one that makes the
first two mean anything. *Forty-nine invariants held* is a different sentence
depending on whether thirty-five more were excluded on purpose.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List

from . import formats
from .exit_contract import DECLINE_CLASSES, FINDING_CLASSES, MEANING


def attestation(*, register, presence, manifest, result, model_text,
                declaration_paths: List[str], walk_path: str,
                register_path: str) -> Dict[str, Any]:
    envelope = result["envelope"]
    by_class: Dict[str, int] = {}
    for row in result["declines"]:
        by_class[row["class"]] = by_class.get(row["class"], 0) + 1
    reviews = manifest.get("declaration_reviews", [])
    return {
        "format": formats.ATTEST,
        "generated": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "line": register.get("line"),
        "inputs": {
            "register": register_path,
            "walk": walk_path,
            "walk_source": presence.get("source", {}),
            "declarations": declaration_paths,
            "review": [r["status"] for r in reviews],
        },
        "engine": {
            "version": result["engine_version"],
            "schema_version": (envelope.get("meta") or {}).get("schema_version"),
            "source": (envelope.get("meta") or {}).get("source"),
            "decline_vocabulary": result["vocabulary_live"],
            "vocabulary_matches_design_time":
                sorted(result["vocabulary_live"]) ==
                sorted(result["vocabulary_at_design_time"]),
            "dropped_declarations_on_check": result["dropped_declarations_on_check"],
        },
        "checked": {
            "invariants_attempted": (envelope.get("checked") or {}).get("invariants"),
            "entities": (envelope.get("checked") or {}).get("entities"),
            "findings": len(envelope.get("findings") or []),
            "held": max(0, (envelope.get("checked") or {}).get("invariants", 0)
                        - len(envelope.get("findings") or [])
                        - len(envelope.get("not_checked") or [])),
            "findings_verbatim": envelope.get("findings") or [],
            "findings_by_class": {
                name: [f["finding"] for f in result["findings_classified"]
                       if f["class"] == name]
                for name in {f["class"] for f in result["findings_classified"]}},
            "finding_class_floors": {k: v["floor"] for k, v in FINDING_CLASSES.items()},
        },
        "declined": {
            "total": len(result["declines"]),
            "by_class": by_class,
            "class_floors": {k: v["floor"] for k, v in DECLINE_CLASSES.items()},
            "rows": result["declines"],
        },
        "not_established": {
            "stage1": {
                "counts": presence.get("counts", {}),
                "rows": [t for t in presence.get("tags", [])
                         if t["state"] != "reading"],
                "substituted": [t for t in presence.get("tags", [])
                                if t.get("substituted_samples")],
            },
            "excluded_from_model": manifest.get("exclusions", []),
            "withheld_by_gate": result["withheld_by_gate"],
            "floors_this_cadence_cannot_reach": result["unreachable_floors"],
            "unread_properties": result["unread_properties"],
        },
        "model_sha_free_copy": model_text,
        "exit": result["exit"],
        "verdict": MEANING[result["exit"]],
    }


def human(att: Dict[str, Any]) -> str:
    """The prose. One OUTCOME line is contract; the rest is prose.

    Copied deliberately from the reference bridge's `capture`: a caller that
    greps needs one stable line, and a person reading needs the rest.
    """
    lines: List[str] = []
    add = lines.append
    add(f"factory-line-audit -- line {att['line']}")
    add(f"  engine {att['engine']['version']}, envelope schema "
        f"{att['engine']['schema_version']}, source {att['engine']['source']}")
    checked = att["checked"]
    add("")
    add(f"CHECKED       {checked['invariants_attempted']} invariants attempted "
        f"over {checked['entities']} assets; {checked['findings']} findings, "
        f"{checked['held']} held")
    for name, rows in sorted(checked.get("findings_by_class", {}).items()):
        floor = checked["finding_class_floors"].get(name)
        add(f"  [{name}, floor {floor}] {FINDING_CLASSES.get(name, {}).get('why', '')}")
        for finding in rows:
            add(f"    - {finding.get('entity_id')}  {finding.get('axiom')}  "
                f"{finding.get('severity')}  {finding.get('problem_type')}")
            if finding.get("reason"):
                add(f"        {finding['reason']}")
    declined = att["declined"]
    add("")
    add(f"DECLINED      {declined['total']} cells the engine would not judge")
    for name, count in sorted(declined["by_class"].items()):
        floor = declined["class_floors"].get(name)
        add(f"  - {name:<20} {count:>3}   floor {floor}   "
            f"{DECLINE_CLASSES.get(name, {}).get('why', '')}")
    not_est = att["not_established"]
    stage1 = not_est["stage1"]["counts"]
    add("")
    add(f"NOT ESTABLISHED")
    add(f"  - Stage 1: {stage1.get('reading', 0)} reading, "
        f"{stage1.get('present_not_reading', 0)} present but not reading, "
        f"{stage1.get('absent', 0)} absent, "
        f"{stage1.get('substituted', 0)} substituted at an HMI")
    for row in not_est["stage1"]["rows"]:
        add(f"      {row['asset']}.{row['tag']}  {row['state']}  "
            f"{row.get('detail', '')}")
    for row in not_est["stage1"]["substituted"]:
        add(f"      {row['asset']}.{row['tag']}  substituted in "
            f"{row['substituted_samples']}/{row['samples']} samples")
    add(f"  - excluded from the model: {len(not_est['excluded_from_model'])} "
        f"(every one with a reason; see the manifest)")
    if not_est["withheld_by_gate"]:
        add(f"  - withheld by a declared gate: {not_est['withheld_by_gate']}")
    if not_est["floors_this_cadence_cannot_reach"]:
        add("  - floors this collector's cadence can never reach:")
        for axiom, why in not_est["floors_this_cadence_cannot_reach"].items():
            add(f"      {axiom}: {why}")
    add("")
    add(f"OUTCOME exit={att['exit']} verdict={att['verdict']} "
        f"findings={checked['findings']} declined={declined['total']} "
        f"attempted={checked['invariants_attempted']}")
    return "\n".join(lines)
