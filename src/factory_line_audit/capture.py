"""`capture`: read a live OPC UA server and write `factory-line-audit/walk/1`.

**This is the client a user gets.** Until now the only OPC UA client in the
repository was `battery/opcua_surface.py`, which imports nothing from this
package -- so the evidence ladder's rung 2 read a real server with a client
nobody installs, and `pip install factory-line-audit[live]` gave you no way to
capture anything. The battery drives this module now, which makes rung 2
evidence about the shipped code and leaves one copy of the rule below.

## The rule that has to be made here

FINDINGS A7. `asyncua` raises the same way for `BadNodeIdUnknown` -- the address
space has no such node -- as for every other `Bad_*`, which says the node is
there and the server will not vouch for its value. Those are the two states
Stage 1 exists to keep apart, and the distinction has to be made HERE: catch
both into an absent list and Stage 1 cannot recover it, because by then the node
is simply not in the walk.

## What the walk records about how it was taken

`security_policy`, `security_mode` and `pinned`, so a certificate can refuse a
walk taken over an unverified connection. Today they are always `None`, `None`
and `false`: this verb offers no security flags yet, and recording that
truthfully is the point. A walk that does not say how it was taken is one a
downstream reader has to assume about.

## `--membership-cache`

OPC UA has no per-node ETag, so there is no honest way to ask a server *has any
value changed*. What can be asked cheaply is whether the ADDRESS SPACE still
holds the same declared nodes, which is the question a PLC program release
changes the answer to. The cache holds node ids and namespace URIs and **never a
value** -- a test asserts that over a walk that had values.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import formats

#: `sha256:` and sixty-four hex characters, over the FILE. A digest over a
#: re-serialisation would survive re-indentation and would make every consumer
#: reproduce one language's float formatting before it could agree. `sha256sum`
#: computes this in any language, and a recipient can check it without
#: installing this tool.
def digest(raw: bytes | str) -> str:
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _quality_word(status: Any) -> str:
    """The server's status word, as a word. Never a bool.

    A boolean here would collapse `Good_LocalOverride` -- a value somebody
    forced at the HMI -- into `Good`, and the whole substituted-sample count
    rests on telling them apart.
    """
    name = getattr(status, "name", None)
    if name:
        return str(name)
    try:
        from asyncua import ua
        return str(ua.StatusCode(status).name)
    except Exception:                                        # pragma: no cover
        return str(status)


def declared_nodes(register: Dict[str, Any]) -> List[str]:
    """Every node id the register declares, in register order.

    `tags` is an object keyed by tag name, not a list. Written as a list first,
    which iterated the KEYS and asked a string for `.get("node")`; the verb
    reported could-not-complete against a server that was answering perfectly.
    """
    nodes: List[str] = []
    for asset in register.get("assets") or []:
        for tag in (asset.get("tags") or {}).values():
            node = tag.get("node") if isinstance(tag, dict) else None
            if node and node not in nodes:
                nodes.append(node)
    return nodes


async def _connect(client_url: str):
    from asyncua import Client
    return Client(url=client_url)


async def _membership(endpoint: str, wanted: Sequence[str]) -> Dict[str, Any]:
    """Namespaces, and which declared nodes the address space still holds.

    No value is read. This is the only question OPC UA can answer cheaply, and
    answering a different one would be worse than answering none.
    """
    from asyncua import Client, ua

    present, absent = [], []
    async with Client(url=endpoint) as client:
        namespaces = list(await client.get_namespace_array())
        for node in wanted:
            try:
                identifier = node.split(";s=", 1)[1]
            except IndexError:
                absent.append(node)
                continue
            handle = client.get_node(ua.NodeId(identifier, 2))
            try:
                await handle.read_browse_name()
                present.append(node)
            except Exception:
                absent.append(node)
    return {"format": f"{formats.PACKAGE}/membership/1",
            "endpoint": endpoint, "checked_at": _now(),
            "namespaces": namespaces,
            "present": sorted(present), "absent": sorted(absent),
            "note": "membership only. No value was read and none is stored: "
                    "OPC UA has no per-node ETag, so this cannot say whether a "
                    "reading changed and does not pretend to."}


async def _walk(endpoint: str, wanted: Sequence[str], *, samples: int,
                budget_s: float, namespace: Optional[str],
                security: Optional[Dict[str, Any]] = None,
                security_string: Optional[str] = None,
                user: Optional[str] = None,
                password: Optional[str] = None) -> Dict[str, Any]:
    import asyncio

    from asyncua import Client, ua

    seen: Dict[str, Any] = {}
    absent: List[str] = []
    unreadable: Dict[str, str] = {}
    handles: Dict[str, Any] = {}

    connection = Client(url=endpoint)
    if security_string:
        await connection.set_security_string(security_string)
    if user:
        connection.set_user(user)
        if password:
            connection.set_password(password)
    async with connection as client:
        index = (await client.get_namespace_index(namespace)) if namespace else 2
        for node in wanted:
            try:
                identifier = node.split(";s=", 1)[1]
            except IndexError:
                absent.append(node)
                continue
            handle = client.get_node(ua.NodeId(identifier, index))
            try:
                await handle.read_data_value()
                handles[node] = handle
            except ua.UaStatusCodeError as refused:
                # A7, and the reason this module exists rather than a copy of it
                # in the battery. A read that raises is not evidence the node is
                # missing.
                word = _quality_word(getattr(refused, "code", None))
                if "NodeIdUnknown" in word or "NodeIdUnknown" in str(refused):
                    absent.append(node)
                else:
                    handles[node] = handle
                    unreadable[node] = word
            except Exception as broke:
                absent.append(node)
                unreadable[node] = f"{type(broke).__name__}: {broke}"

        deadline = asyncio.get_event_loop().time() + budget_s
        while len(seen) < samples and asyncio.get_event_loop().time() < deadline:
            nodes: Dict[str, Any] = {}
            stamp = None
            for node, handle in handles.items():
                try:
                    value = await handle.read_data_value()
                except ua.UaStatusCodeError as refused:
                    nodes[node] = {"v": None,
                                   "q": _quality_word(getattr(refused, "code", None)),
                                   "t": stamp or _now()}
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
                               "q": _quality_word(value.StatusCode), "t": text}
            if stamp and stamp not in seen and nodes:
                seen[stamp] = {"t": stamp, "nodes": nodes}
            await asyncio.sleep(0.03)

    return {
        "format": formats.WALK,
        "line": "captured",
        "source": {
            "kind": "opcua",
            "endpoint": endpoint,
            "collected_by": "factory-line-audit capture (asyncua)",
            "captured_at": _now(),
            # How it was taken, so a certificate can refuse a walk taken over
            # an unverified connection. Refused at construction rather than
            # reported afterwards: see `security_from_flags`.
            **(security or {"security_policy": "None", "security_mode": "None",
                            "pinned": False, "insecure": False,
                            "client_cert": False}),
            "nodes_requested": len(wanted),
            "nodes_served": len(handles),
            # The battery already used these names and they are the better
            # ones: each says which of the two states Stage 1 keeps apart.
            "nodes_not_in_address_space": sorted(absent),
            "nodes_present_but_unreadable": dict(sorted(unreadable.items())),
        },
        "samples": [seen[key] for key in sorted(seen)],
    }


def capture(register: Dict[str, Any], endpoint: str, *, samples: int = 5,
            budget_s: float = 30.0, namespace: Optional[str] = None,
            security: Optional[Dict[str, Any]] = None,
            security_string: Optional[str] = None,
            user: Optional[str] = None,
            password: Optional[str] = None) -> Dict[str, Any]:
    """A walk, read from a live server. Raises nothing the CLI cannot describe."""
    import asyncio
    wanted = declared_nodes(register)
    if not wanted:
        raise formats.Refusal("register", "declares no node ids to capture")
    return asyncio.run(_walk(endpoint, wanted, samples=samples,
                             budget_s=budget_s, namespace=namespace,
                             security=security,
                             security_string=security_string,
                             user=user, password=password))


def security_string(security: Dict[str, Any], cert: Optional[str],
                    key: Optional[str]) -> Optional[str]:
    """`asyncua`'s own form, built only once the flags have been accepted."""
    if security["security_policy"] == "None":
        return None
    return (f"{security['security_policy']},{security['security_mode']},"
            f"{cert},{key}")


def membership(register: Dict[str, Any], endpoint: str) -> Dict[str, Any]:
    import asyncio
    return asyncio.run(_membership(endpoint, declared_nodes(register)))


def membership_unchanged(cached: Any, fresh: Dict[str, Any]) -> bool:
    """Same server, same declared nodes present, same namespaces.

    THE ENDPOINT IS PART OF IT, and that was found by getting it wrong. Written
    without it, two runs against two different servers on two different ports
    reported `unchanged` -- because their address spaces happened to match. A
    cache keyed on nothing answers for whatever it is pointed at, and a skipped
    walk justified by another machine's address space is worse than no cache.

    Nothing here is about values. It cannot be: OPC UA has no per-node ETag.
    """
    if not isinstance(cached, dict):
        return False
    return (cached.get("endpoint") == fresh["endpoint"]
            and cached.get("present") == fresh["present"]
            and cached.get("absent") == fresh["absent"]
            and cached.get("namespaces") == fresh["namespaces"])


# --------------------------------------------------------------- security
#: Policies this verb offers, DERIVED from what the client library accepts and
#: then narrowed, with the narrowing stated. `asyncua` also accepts
#: `Basic128Rsa15` and `Basic256`; both are withdrawn in the OPC UA spec -- one
#: for RSA-15 padding, the other for SHA-1 -- and offering a flag that looks
#: like security and is not is the failure this whole family refuses. A server
#: that offers only those is a finding about the server, not a mode to meet it
#: in.
WITHDRAWN_POLICIES = ("Basic128Rsa15", "Basic256")


def offered_policies() -> List[str]:
    """`None` plus every current policy the installed library can speak."""
    from asyncua.crypto.security_policies import SecurityPolicyType
    names = []
    for member in SecurityPolicyType:
        if member.name == "NoSecurity":
            continue
        policy = member.name.split("_")[0]
        if policy in WITHDRAWN_POLICIES or policy in names:
            continue
        names.append(policy)
    return ["None"] + names


def security_from_flags(*, policy: str, mode: str, cert: Optional[str],
                        key: Optional[str], pin: Optional[str],
                        insecure: bool, endpoint: str) -> Dict[str, Any]:
    """What to connect with, or a `Refusal` naming what cannot both be true.

    REFUSED AT CONSTRUCTION, before anything is dialled. A flag that is accepted
    and then ignored is worse than one that does not exist: the run reports
    having been taken with a protection nothing applied.
    """
    policy = policy or "None"
    mode = mode or ("None" if policy == "None" else "SignAndEncrypt")

    if policy in WITHDRAWN_POLICIES:
        raise formats.Refusal(endpoint, f"{policy} is withdrawn from the OPC UA "
                                        f"spec and this verb does not offer it; "
                                        f"a server that speaks only {policy} is "
                                        f"a finding about the server")
    if insecure and pin:
        raise formats.Refusal(endpoint, "--insecure and --server-cert-pin-sha256 "
                                        "ask for opposite things: one says do "
                                        "not check the server, the other says "
                                        "check it against this")
    if insecure and policy != "None":
        raise formats.Refusal(endpoint, f"--insecure beside --security-policy "
                                        f"{policy} would negotiate a policy and "
                                        f"then not verify who it negotiated it "
                                        f"with, which is the shape of protection "
                                        f"rather than the thing")
    if pin and policy == "None":
        raise formats.Refusal(endpoint, "a certificate pin on --security-policy "
                                        "None has nothing to check: no "
                                        "certificate is exchanged, so the pin "
                                        "would be carried into the walk's "
                                        "provenance having verified nothing")
    if policy != "None" and not (cert and key):
        raise formats.Refusal(endpoint, f"--security-policy {policy} needs a "
                                        f"client --cert and --key; the server "
                                        f"has to be able to identify what it is "
                                        f"signing to")
    if mode != "None" and policy == "None":
        raise formats.Refusal(endpoint, f"--security-mode {mode} on "
                                        f"--security-policy None cannot be "
                                        f"honoured; there is no channel to sign")
    if policy == "None" and not insecure and not _is_loopback(endpoint):
        raise formats.Refusal(endpoint, "an unencrypted anonymous connection is "
                                        "accepted on loopback, which is what the "
                                        "evidence ladder's rung 3 is. Off "
                                        "loopback it has to be asked for by "
                                        "name with --insecure, so the walk can "
                                        "record that somebody did")
    return {"security_policy": policy, "security_mode": mode,
            "pinned": bool(pin), "insecure": bool(insecure),
            "client_cert": bool(cert)}


def _is_loopback(endpoint: str) -> bool:
    """Loopback by ADDRESS, never by name. `localhost` is whatever a resolver
    says it is, and a walk taken over a resolved name is not evidence about the
    machine somebody meant."""
    import re
    match = re.search(r"//([^:/]+)", endpoint or "")
    host = match.group(1) if match else ""
    return host in ("127.0.0.1", "::1", "[::1]")
