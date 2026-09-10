#!/usr/bin/env python3
"""Evidence-ladder rung 3: a live-but-safe OPC UA surface, read for real.

BRIDGES C9: *name every rung -- synthetic corpus, mutated copies, a live-but-safe
surface, first contact. Every rung below the top must be climbable in a box.*

Rung 1 is `corpus/` and rung 2 its mutated copies. Rung 3 is this: a real OPC UA
server, on localhost, serving
the rung-1 corpus, read by a real OPC UA client that has never seen the JSON.
Nothing here reaches a plant, and the walk it produces goes through exactly the
same Stage 1 and Stage 2 as the synthetic one.

What it is genuinely evidence for, and what it is not:

  IT IS   -- the walk format survives contact with a real client library; node
             ids resolve; a status word comes back as a status word rather than
             as the bool this package might have assumed; source timestamps are
             what the engine's windows get fed; a node that is not there fails
             the way Stage 1 says it does.
  IT IS NOT -- security, certificates, authentication, a vendor's address-space
             layout, a PLC's actual update semantics, or anything about load. An
             anonymous unencrypted localhost server is the safe surface, and
             calling it a rehearsal for a plant would be the lie this rung
             exists to avoid.

Two entry points, run as separate processes:
    python3 opcua_surface.py serve   --port N --walk clean.json
    python3 opcua_surface.py collect --port N --out live_walk.json
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REGISTER = os.path.join(ROOT, "examples", "asset_register.json")
NAMESPACE = "urn:factory-line-audit:rung3"

#: Deliberately not served, so the live walk exercises all three Stage 1 states
#: against a real server rather than against a JSON file this package wrote.
#: `absent` is a node the server never creates; `bad` is a node it creates and
#: then marks Bad. A rung that only ever proves the happy path is a rung.
WITHHOLD_ABSENT = "ns=2;s=ROB01.Torque"
WITHHOLD_BAD = "ns=2;s=PLC01.CpuLoad"


def node_ids():
    with open(REGISTER, encoding="utf-8") as handle:
        register = json.load(handle)
    return [spec["node"] for asset in register["assets"]
            for spec in asset["tags"].values()]


async def serve(port: int, walk_path: str, ready: str,
                no_source: bool = False) -> None:
    from asyncua import Server, ua

    with open(walk_path, encoding="utf-8") as handle:
        walk = json.load(handle)
    samples = walk["samples"]

    server = Server()
    await server.init()
    server.set_endpoint(f"opc.tcp://127.0.0.1:{port}/factory-line-audit/")
    server.set_server_name("factory-line-audit rung 3")
    idx = await server.register_namespace(NAMESPACE)
    folder = await server.nodes.objects.add_folder(idx, "Line1")

    # A node's datatype is fixed when it is created, and a server refuses a
    # write of the wrong one. This is the first thing rung 3 found that rung 1
    # could not: the register declares a tag CLASS but no datatype, and
    # `state_running` is the tag where that difference is not academic. The
    # initial value is taken from the corpus so that a bool node is a bool node.
    # A register exported from a real MES would carry the datatype; this one
    # infers it, and the inference is named here rather than hidden.
    first = (samples[0].get("nodes") if samples else {}) or {}
    variables = {}
    for node in node_ids():
        if node == WITHHOLD_ABSENT:
            continue
        seed = (first.get(node) or {}).get("v")
        initial = bool(seed) if isinstance(seed, bool) else 0.0
        variables[node] = await folder.add_variable(
            ua.NodeId(node.split(";s=", 1)[1], idx), node.split(";s=", 1)[1],
            initial)

    async with server:
        announced = False
        for sample in samples:
            for node, variable in variables.items():
                reading = (sample.get("nodes") or {}).get(node)
                if reading is None:
                    continue
                value = reading.get("v")
                quality = str(reading.get("q") or "Good")
                when = _dt.datetime.fromisoformat(
                    str(reading.get("t") or sample["t"]).replace("Z", "+00:00"))
                if node == WITHHOLD_BAD:
                    quality, value = "BadDeviceFailure", None
                # THE WORD THE CORPUS ASKED FOR, not a two-way collapse. This
                # served `Good` or `BadDeviceFailure` and nothing else, so the
                # rung could not produce a substituted value at all -- and
                # `Good_LocalOverride`, the case the substituted count exists
                # for, lived only in the synthetic corpus.
                status = ua.StatusCode(_status_code(quality))
                if value is None:
                    variant = ua.Variant(None, ua.VariantType.Null)
                elif isinstance(value, bool):
                    variant = ua.Variant(value, ua.VariantType.Boolean)
                elif isinstance(value, str):
                    # A machine state is an enumeration WORD on a real server.
                    # This branch did not exist while the corpus fed booleans for
                    # `state_running`, and `float("Running")` raises -- so the
                    # corpus change to real state words would have taken the live
                    # leg down, which is the leg's whole purpose.
                    variant = ua.Variant(value, ua.VariantType.String)
                else:
                    variant = ua.Variant(float(value), ua.VariantType.Double)
                await server.write_attribute_value(
                    variable.nodeid,
                    ua.DataValue(variant, StatusCode=status,
                                 SourceTimestamp=None if no_source else when,
                                 ServerTimestamp=when if no_source else None))
            if not announced:
                # After the first full pass, not before it. A readiness marker
                # written at startup says the process began, and a collector
                # that trusts it races a server that is about to raise.
                with open(ready, "w", encoding="utf-8") as handle:
                    handle.write(json.dumps({"port": port,
                                             "served": len(variables),
                                             "samples": len(samples)}))
                announced = True
            await asyncio.sleep(0.12)
        await asyncio.sleep(3.0)


def _status_code(word: str):
    """A corpus status word -> the OPC UA code a real server would report.

    Nothing normalises on the way back any more. This file used to carry a
    `_quality_word` that turned every code the client read into one of three
    corpus spellings -- `Good`, `Good_LocalOverride`, `Bad_DeviceFailure` --
    which meant Stage 1 never saw what `asyncua` actually reports and its
    grader was never exercised against it. The grader now reads the real
    spelling, so this serves the real code and the walk carries it through.
    """
    from asyncua import ua
    flat = str(word or "Good").replace("_", "").replace("-", "").lower()
    for name in dir(ua.StatusCodes):
        if not name.startswith(("Good", "Bad", "Uncertain")):
            continue
        if name.lower() == flat:
            return getattr(ua.StatusCodes, name)
    if flat.startswith("good"):
        return ua.StatusCodes.Good
    if flat.startswith("uncertain"):
        return ua.StatusCodes.Uncertain
    return ua.StatusCodes.BadDeviceFailure


async def collect(port: int, out: str, want: int, budget_s: float) -> int:
    """Rung 3, driven through the SHIPPED client.

    This held its own OPC UA client until 2026-09-09, which made rung 3 evidence
    about a client nobody installs -- and kept a second copy of FINDINGS A7, the
    rule that tells `BadNodeIdUnknown` apart from every other `Bad_*`. The
    package now ships `capture`, so the ladder reads the code a user gets and
    the rule has one home.

    The provenance below is still this file's: what makes a walk rung-2 evidence
    is how it was OBTAINED, and only this script knows the server on the other
    end was fed the rung-1 corpus.

    `node_ids()` and not the register: this asks the surface for every node it
    was told to serve, INCLUDING the templated one the register loader drops, so
    the rung keeps exercising a node the shipped path filters out.
    """
    import sys as _sys
    _sys.path.insert(0, os.path.join(ROOT, "src"))
    from factory_line_audit.capture import _walk

    endpoint = f"opc.tcp://127.0.0.1:{port}/factory-line-audit/"
    body = await _walk(endpoint, node_ids(), samples=want, budget_s=budget_s,
                       namespace=None)
    body["line"] = "line1"
    body["source"].update({
        "collected_by": "battery/opcua_surface.py collect, through "
                        "factory_line_audit.capture (asyncua)",
        "cadence_s": 60,
        "provenance": "EVIDENCE LADDER RUNG 2. A real OPC UA client read a "
                      "real OPC UA server on localhost. The server was fed "
                      "the rung-1 corpus and served each value with its "
                      "source timestamp, so the cadence above is the one "
                      "the timestamps carry, not the polling interval. "
                      "Anonymous, unencrypted, localhost: nothing here is "
                      "evidence about security or about a plant.",
    })
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(body, handle, indent=2)
        handle.write("\n")
    source = body["source"]
    print(f"collected {len(body['samples'])} distinct samples from "
          f"{source['nodes_served']}/{source['nodes_requested']} nodes; "
          f"{len(source['nodes_not_in_address_space'])} not in the address "
          f"space, {len(source['nodes_present_but_unreadable'])} present but "
          f"unreadable")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="mode", required=True)
    p = subs.add_parser("serve")
    p.add_argument("--port", type=int, default=48401)
    p.add_argument("--walk", default=os.path.join(HERE, "corpus", "clean.json"))
    p.add_argument("--ready", default="/tmp/fla-rung3-ready.json")
    # A server that stamps only ServerTimestamp. `capture` skipped any reading
    # whose SourceTimestamp was None, which against such a server produced a
    # walk with ZERO samples -- and Stage 1 then called every declared tag absent
    # while the same file's `nodes_served` said they had been read. The fallback
    # is in `capture`; this is what can exercise it.
    p.add_argument("--no-source-timestamp", action="store_true")
    p = subs.add_parser("collect")
    p.add_argument("--port", type=int, default=48401)
    p.add_argument("--out", required=True)
    p.add_argument("--want", type=int, default=50)
    p.add_argument("--budget", type=float, default=45.0)
    args = parser.parse_args()
    if args.mode == "serve":
        asyncio.run(serve(args.port, args.walk, args.ready,
                          no_source=args.no_source_timestamp))
        return 0
    return asyncio.run(collect(args.port, args.out, args.want, args.budget))


if __name__ == "__main__":
    raise SystemExit(main())
