#!/usr/bin/env python3
"""Evidence-ladder rung 2: a live-but-safe OPC UA surface, read for real.

BRIDGES C9: *name every rung -- synthetic corpus, mutated copies, a live-but-safe
surface, first contact. Every rung below the top must be climbable in a box.*

Rung 1 is `corpus/`. Rung 2 is this: a real OPC UA server, on localhost, serving
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
NAMESPACE = "urn:factory-line-audit:rung2"

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


async def serve(port: int, walk_path: str, ready: str) -> None:
    from asyncua import Server, ua

    with open(walk_path, encoding="utf-8") as handle:
        walk = json.load(handle)
    samples = walk["samples"]

    server = Server()
    await server.init()
    server.set_endpoint(f"opc.tcp://127.0.0.1:{port}/factory-line-audit/")
    server.set_server_name("factory-line-audit rung 2")
    idx = await server.register_namespace(NAMESPACE)
    folder = await server.nodes.objects.add_folder(idx, "Line1")

    # A node's datatype is fixed when it is created, and a server refuses a
    # write of the wrong one. This is the first thing rung 2 found that rung 1
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
                    quality, value = "Bad_DeviceFailure", None
                status = (ua.StatusCode(ua.StatusCodes.Good)
                          if quality.lower().startswith("good")
                          else ua.StatusCode(ua.StatusCodes.BadDeviceFailure))
                if value is None:
                    variant = ua.Variant(None, ua.VariantType.Null)
                elif isinstance(value, bool):
                    variant = ua.Variant(value, ua.VariantType.Boolean)
                else:
                    variant = ua.Variant(float(value), ua.VariantType.Double)
                await server.write_attribute_value(
                    variable.nodeid,
                    ua.DataValue(variant, StatusCode=status,
                                 SourceTimestamp=when))
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


def _quality_word(status) -> str:
    """An OPC UA StatusCode -> the word this package's Stage 1 grades.

    Collapsing this to a bool here would move the decision Stage 1 exists to
    make into the collector, where nothing can see it.
    """
    name = getattr(status, "name", None) or str(status)
    if "Good" in name:
        return "Good_LocalOverride" if "Override" in name else "Good"
    if "Uncertain" in name:
        return "Uncertain"
    return "Bad_DeviceFailure"


async def collect(port: int, out: str, want: int, budget_s: float) -> int:
    from asyncua import Client, ua

    wanted = node_ids()
    seen = {}
    served = 0
    absent = []
    unreadable = {}
    refused = {}
    async with Client(url=f"opc.tcp://127.0.0.1:{port}/factory-line-audit/") as client:
        idx = await client.get_namespace_index(NAMESPACE)
        handles = {}
        for node in wanted:
            handle = client.get_node(ua.NodeId(node.split(";s=", 1)[1], idx))
            try:
                await handle.read_data_value()
                handles[node] = handle
                served += 1
            except ua.UaStatusCodeError as exc:
                # THE DISTINCTION STAGE 1 IS FOR, MADE WHERE IT HAS TO BE MADE.
                #
                # A read that raises is not evidence the node is missing.
                # `BadNodeIdUnknown` says the address space has no such node;
                # every other Bad status says the node is there and the server
                # will not vouch for its value. asyncua raises on both, and the
                # first version of this collector caught the exception and put
                # the node on the absent list -- which collapsed
                # present-but-not-reading into absent one layer ABOVE the stage
                # whose whole job is to keep them apart. Stage 1 could not have
                # recovered it: by then the node simply was not in the walk.
                code = getattr(exc, "code", None)
                try:
                    name = ua.StatusCode(code).name
                except Exception:
                    name = str(exc)
                if "NodeIdUnknown" in str(name) or "NodeIdUnknown" in str(exc):
                    absent.append(node)
                else:
                    handles[node] = handle
                    served += 1
                    unreadable[node] = str(name)
            except Exception as exc:
                absent.append(node)
                refused[node] = f"{type(exc).__name__}: {exc}"
        deadline = asyncio.get_event_loop().time() + budget_s
        while len(seen) < want and asyncio.get_event_loop().time() < deadline:
            nodes = {}
            stamp = None
            for node, handle in handles.items():
                try:
                    value = await handle.read_data_value()
                except ua.UaStatusCodeError as exc:
                    # Present, and the server will not vouch for it. Carried
                    # into the walk with a Bad word and a null value, which is
                    # what Stage 1 reads as present-but-not-reading.
                    nodes[node] = {"v": None, "q": "Bad_DeviceFailure",
                                   "t": stamp or _dt.datetime.now(
                                       _dt.timezone.utc).isoformat().replace(
                                           "+00:00", "Z")}
                    continue
                except Exception:
                    continue
                when = value.SourceTimestamp
                if when is None:
                    continue
                if when.tzinfo is None:
                    when = when.replace(tzinfo=_dt.timezone.utc)
                text = when.isoformat().replace("+00:00", "Z")
                stamp = stamp or text
                nodes[node] = {"v": value.Value.Value,
                               "q": _quality_word(value.StatusCode),
                               "t": text}
            if stamp and stamp not in seen and nodes:
                seen[stamp] = {"t": stamp, "nodes": nodes}
            await asyncio.sleep(0.03)

    body = {
        "format": "factory-line-audit/walk/1",
        "line": "line1",
        "source": {
            "kind": "opcua",
            "endpoint": f"opc.tcp://127.0.0.1:{port}/factory-line-audit/",
            "collected_by": "battery/opcua_surface.py collect (asyncua)",
            "cadence_s": 60,
            "provenance": "EVIDENCE LADDER RUNG 2. A real OPC UA client read a "
                          "real OPC UA server on localhost. The server was fed "
                          "the rung-1 corpus and served each value with its "
                          "source timestamp, so the cadence above is the one "
                          "the timestamps carry, not the polling interval. "
                          "Anonymous, unencrypted, localhost: nothing here is "
                          "evidence about security or about a plant.",
            "nodes_requested": len(wanted),
            "nodes_served": served,
            "nodes_not_in_address_space": absent,
            "nodes_present_but_unreadable": unreadable,
            "nodes_refused_for_another_reason": refused,
        },
        "samples": [seen[k] for k in sorted(seen)],
    }
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(body, handle, indent=1)
        handle.write("\n")
    print(f"collected {len(body['samples'])} distinct samples from "
          f"{served}/{len(wanted)} nodes; {len(absent)} not in the address "
          f"space, {len(unreadable)} present but unreadable")
    return 0 if body["samples"] else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="mode", required=True)
    p = subs.add_parser("serve")
    p.add_argument("--port", type=int, default=48401)
    p.add_argument("--walk", default=os.path.join(HERE, "corpus", "clean.json"))
    p.add_argument("--ready", default="/tmp/fla-rung2-ready.json")
    p = subs.add_parser("collect")
    p.add_argument("--port", type=int, default=48401)
    p.add_argument("--out", required=True)
    p.add_argument("--want", type=int, default=50)
    p.add_argument("--budget", type=float, default=45.0)
    args = parser.parse_args()
    if args.mode == "serve":
        asyncio.run(serve(args.port, args.walk, args.ready))
        return 0
    return asyncio.run(collect(args.port, args.out, args.want, args.budget))


if __name__ == "__main__":
    raise SystemExit(main())
