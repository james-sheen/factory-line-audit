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
  IT IS NOT -- authentication, a vendor's address-space layout, a PLC's actual
             update semantics, or anything about load. Calling this a rehearsal
             for a plant would be the lie this rung exists to avoid.
  SINCE 0.1.8, ALSO IS -- a SIGNED AND ENCRYPTED channel with a server
             certificate, under `serve --certificate`. Narrowly, and the
             narrowness is the point: it is a self-signed certificate this
             script generates, so it proves that `--server-cert-pin-sha256`
             reaches `asyncua`'s `certificate_validator` hook, that a matching
             digest passes and a wrong one refuses by name. It proves nothing
             about a plant's PKI. Before it existed, the pin was exercised only
             by tests that called `_Pin` directly and by a grep of `_walk` for
             the hook's name -- so whether the LIBRARY ever called it was
             unmeasured, and a hook the library never calls would pass a wrong
             digest and record the walk as pinned.

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
from typing import Optional

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


def make_certificate(directory: str):
    """A self-signed server certificate, and its SHA-256 over the DER.

    Generated rather than committed: a private key in a public repository is a
    private key in a public repository, whatever it is for. The digest is
    returned so the caller can pass the RIGHT pin without parsing anything --
    the test is whether the client checks it, not whether a shell can extract
    it.
    """
    import datetime as dt

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,
                                         "factory-line-audit rung 3")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([
                x509.UniformResourceIdentifier("urn:factory-line-audit:rung3"),
                x509.DNSName("127.0.0.1")]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None),
                           critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=False,
                key_encipherment=True, data_encipherment=True,
                key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))

    cert_path = os.path.join(directory, "server-cert.der")
    key_path = os.path.join(directory, "server-key.pem")
    with open(cert_path, "wb") as handle:
        handle.write(cert.public_bytes(serialization.Encoding.DER))
    with open(key_path, "wb") as handle:
        handle.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()))
    import hashlib
    digest = hashlib.sha256(
        cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    return cert_path, key_path, digest


async def serve(port: int, walk_path: str, ready: str,
                no_source: bool = False,
                certificate: Optional[str] = None,
                repeat: bool = False) -> None:
    from asyncua import Server, ua

    with open(walk_path, encoding="utf-8") as handle:
        walk = json.load(handle)
    samples = walk["samples"]

    server = Server()
    await server.init()
    server.set_endpoint(f"opc.tcp://127.0.0.1:{port}/factory-line-audit/")
    server.set_server_name("factory-line-audit rung 3")
    digest = None
    if certificate:
        # SIGNED AND ENCRYPTED, with the server holding a certificate. The
        # policy list is set EXPLICITLY: left at the default this server also
        # offers `NoSecurity`, and a client that quietly fell back to it would
        # produce a walk recording `pinned: true` over a channel where no
        # certificate was ever exchanged -- the precise claim the pin exists to
        # make impossible, arrived at by the back door.
        os.makedirs(certificate, exist_ok=True)
        cert_path, key_path, digest = make_certificate(certificate)
        await server.load_certificate(cert_path)
        await server.load_private_key(key_path)
        server.set_security_policy([
            ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt])
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
        # THE SEED'S TYPE, all three of them. A string seed used to fall to
        # `0.0`, so `state_running` was created as a Double and every write of a
        # state WORD was refused for the rest of the run -- `asyncua` logs
        # `Write refused` and carries on, so the server stayed up, the node
        # served its initial `0.0` forever, and the leg stayed green. The write
        # side of this had already been fixed when the corpus moved to real state
        # words; the creation side had not, and the two sides are four lines
        # apart under a comment that says a node's datatype is fixed when it is
        # created. Found by running a walk against this server and reading what
        # came back, which is the only thing that could have found it.
        if isinstance(seed, bool):
            initial = seed
        elif isinstance(seed, str):
            initial = seed
        else:
            initial = 0.0
        variables[node] = await folder.add_variable(
            ua.NodeId(node.split(";s=", 1)[1], idx), node.split(";s=", 1)[1],
            initial)

    async with server:
        announced = False
        # REPEAT, for a caller that needs the surface to outlive one pass. One
        # pass is fifty samples at 0.12 s plus three: about nine seconds, which
        # is enough for one `collect` started the moment the readiness marker
        # appears, and not enough for a leg that runs TWO clients against one
        # server -- which the pin leg does, by construction, because a right pin
        # and a wrong one are two connections.
        while True:
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
                        # A machine state is an enumeration WORD on a real
                        # server. This branch did not exist while the corpus fed
                        # booleans for `state_running`, and `float("Running")`
                        # raises -- so the corpus change to real state words
                        # would have taken the live leg down, which is the leg's
                        # whole purpose. The node's CREATION type is the other
                        # half of it, and was missed: see above.
                        variant = ua.Variant(value, ua.VariantType.String)
                    else:
                        variant = ua.Variant(float(value), ua.VariantType.Double)
                    await server.write_attribute_value(
                        variable.nodeid,
                        ua.DataValue(variant, StatusCode=status,
                                     SourceTimestamp=None if no_source else when,
                                     ServerTimestamp=when if no_source else None))
                if not announced:
                    # After the first full pass, not before it. A readiness
                    # marker written at startup says the process began, and a
                    # collector that trusts it races a server about to raise.
                    with open(ready, "w", encoding="utf-8") as handle:
                        handle.write(json.dumps({
                            "port": port,
                            "served": len(variables),
                            "samples": len(samples),
                            # The digest of the certificate THIS process holds,
                            # so a caller can pass the right pin without
                            # extracting it. What is under test is whether the
                            # client checks the certificate, not whether a shell
                            # can read one.
                            "server_cert_sha256": digest,
                            "security": ("Basic256Sha256/SignAndEncrypt"
                                         if digest else "None/None")}))
                    announced = True
                await asyncio.sleep(0.12)
            if not repeat:
                break
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
    # A SERVER THAT HOLDS A CERTIFICATE, so the pin has something to check. The
    # directory is where the generated certificate and key are written; nothing
    # is committed, because a private key in a public repository is a private
    # key in a public repository whatever it is for.
    p.add_argument("--certificate", metavar="DIR",
                   help="serve Basic256Sha256/SignAndEncrypt with a "
                        "self-signed certificate generated into DIR")
    p.add_argument("--repeat", action="store_true",
                   help="cycle the corpus until terminated. One pass is about "
                        "nine seconds, which is enough for one collector "
                        "started at the readiness marker and not enough for a "
                        "caller that runs two clients against one server")
    p = subs.add_parser("collect")
    p.add_argument("--port", type=int, default=48401)
    p.add_argument("--out", required=True)
    p.add_argument("--want", type=int, default=50)
    p.add_argument("--budget", type=float, default=45.0)
    args = parser.parse_args()
    if args.mode == "serve":
        asyncio.run(serve(args.port, args.walk, args.ready,
                          no_source=args.no_source_timestamp,
                          certificate=args.certificate,
                          repeat=args.repeat))
        return 0
    return asyncio.run(collect(args.port, args.out, args.want, args.budget))


if __name__ == "__main__":
    raise SystemExit(main())
