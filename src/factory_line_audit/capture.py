"""`capture`: read a live OPC UA server and write `factory-line-audit/walk/1`.

**This is the client a user gets.** Until now the only OPC UA client in the
repository was `battery/opcua_surface.py`, which imports nothing from this
package -- so the evidence ladder's rung 3 read a real server with a client
nobody installs, and `pip install factory-line-audit[live]` gave you no way to
capture anything. The battery drives this module now, which makes rung 3
evidence about the shipped code and leaves one copy of the rule below.

## The rule that has to be made here

FINDINGS A7. `asyncua` raises the same way for `BadNodeIdUnknown` -- the address
space has no such node -- as for every other `Bad_*`, which says the node is
there and the server will not vouch for its value. Those are the two states
Stage 1 exists to keep apart, and the distinction has to be made HERE: catch
both into an absent list and Stage 1 cannot recover it, because by then the node
is simply not in the walk.

## What the walk records about how it was taken

`security_policy`, `security_mode`, `pinned`, `insecure`, `client_cert`,
`server_cert_sha256` and `timestamps_from`, so a certificate can refuse a walk
taken over an unverified connection. A walk that does not say how it was taken is
one a downstream reader has to assume about.

This paragraph said *they are always `None`, `None` and `false`: this verb offers
no security flags yet* until 0.1.7, by which time six flags had been added and the
pin had been implemented. Prose about an absence outlives the absence.

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


class _Pin:
    """A server-certificate pin, applied where the client library applies it.

    The flag existed since 0.1.0 and did nothing. `security_from_flags` refused
    the combinations that contradict a pin, recorded `pinned: true` in the walk's
    provenance, and then never passed the value anywhere: `cmd_capture` did not
    hand it to `capture`, `_walk` had no parameter for it, and no code compared a
    certificate. A walk could therefore say it was taken over a pinned channel
    when nothing checked who answered -- the failure this module's own docstring
    names, shipped by the module that names it.

    `asyncua` calls `Client.certificate_validator(cert, application)` with the
    server's certificate during the secure-channel setup. That is the hook, so
    this is the pin.

    `checked` is the reason this is a class. If the hook never fires -- no
    certificate was offered, or the library changed where it calls from -- then a
    WRONG pin would also not refuse, and the walk would record `pinned: true` on
    the strength of nothing. The caller asserts this ran.
    """

    def __init__(self, expected: str, endpoint: str):
        self.expected = expected.replace(":", "").replace(" ", "").lower()
        self.endpoint = endpoint
        self.checked = False
        self.digest: Optional[str] = None

    async def __call__(self, certificate, application=None) -> None:
        import hashlib

        from cryptography.hazmat.primitives.serialization import Encoding

        self.digest = hashlib.sha256(
            certificate.public_bytes(Encoding.DER)).hexdigest()
        self.checked = True
        if self.digest != self.expected:
            raise formats.Refusal(
                self.endpoint,
                f"the server's certificate does not match the pin: it presented "
                f"sha256 {self.digest}, --server-cert-pin-sha256 said "
                f"{self.expected}. Nothing was read")


def _node_id(node: str, index: Optional[int]):
    """A node id of ANY of the four OPC UA identifier types.

    This was `node.split(";s=", 1)[1]` with the namespace hard-coded to 2, and an
    `IndexError` counted as ABSENT. So `ns=2;i=1001`, a GUID and an opaque id
    were all reported as nodes the address space does not hold -- a limitation of
    this parser, reported as a fact about the plant, which is the misattribution
    A7 exists to prevent. `ns=3;s=X` was looked up at index 2: the `ns=` a
    register writes was read and discarded.

    `index` overrides the namespace when `--namespace <uri>` resolved one, which
    is what that flag is for: a register written against a namespace URI, served
    at whatever index this server happens to use.
    """
    from asyncua import ua

    try:
        parsed = ua.NodeId.from_string(node)
    except Exception as unparseable:
        raise formats.Refusal(node, f"not a node id this package can address "
                                    f"({type(unparseable).__name__}). Reporting "
                                    f"it absent would be a claim about the "
                                    f"server") from None
    if index is not None:
        parsed.NamespaceIndex = index
    return parsed


async def _membership(endpoint: str, wanted: Sequence[str], *,
                      security_string: Optional[str] = None,
                      user: Optional[str] = None,
                      password: Optional[str] = None,
                      namespace: Optional[str] = None) -> Dict[str, Any]:
    """Namespaces, and which declared nodes the address space still holds.

    No value is read. This is the only question OPC UA can answer cheaply, and
    answering a different one would be worse than answering none.
    """
    from asyncua import Client

    present, absent = [], []
    # The same channel the walk dials. This pass connected anonymously and
    # unencrypted however `capture` was invoked: `security_from_flags` guarded
    # the walk only, so `--membership-cache` with a policy and credentials sent
    # neither.
    connection = Client(url=endpoint)
    if security_string:
        await connection.set_security_string(security_string)
    if user:
        connection.set_user(user)
        if password:
            connection.set_password(password)
    async with connection as client:
        namespaces = list(await client.get_namespace_array())
        index = (await client.get_namespace_index(namespace)) if namespace else None
        for node in wanted:
            handle = client.get_node(_node_id(node, index))
            try:
                await handle.read_browse_name()
                present.append(node)
            except Exception:
                absent.append(node)
    return {"format": formats.MEMBERSHIP,
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
                password: Optional[str] = None,
                pin: Optional[str] = None) -> Dict[str, Any]:
    import asyncio

    from asyncua import Client, ua

    seen: Dict[str, Any] = {}
    absent: List[str] = []
    unreadable: Dict[str, str] = {}
    handles: Dict[str, Any] = {}
    clocks: set = set()

    connection = Client(url=endpoint)
    if security_string:
        await connection.set_security_string(security_string)
    if user:
        connection.set_user(user)
        if password:
            connection.set_password(password)
    pinned = _Pin(pin, endpoint) if pin else None
    if pinned is not None:
        connection.certificate_validator = pinned
    async with connection as client:
        if pinned is not None and not pinned.checked:
            raise formats.Refusal(
                endpoint, "a certificate pin was given and no certificate was "
                          "checked: this server offered none on the negotiated "
                          "channel, so the pin verified nothing. A walk must not "
                          "record a pin it did not apply")
        index = (await client.get_namespace_index(namespace)) if namespace else None
        for node in wanted:
            handle = client.get_node(_node_id(node, index))
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
                # NOT absent. A7 again, and this branch said both at once: the
                # node went into `nodes_not_in_address_space` AND into
                # `nodes_present_but_unreadable`, which are the two states Stage 1
                # exists to keep apart. A timeout is not a missing node.
                handles[node] = handle
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
                # A server that sets only ServerTimestamp used to yield NO
                # samples at all: every node was skipped here, the walk was
                # written with an empty `samples`, and Stage 1 then reported
                # every declared tag absent while the same artifact's
                # `nodes_served` said they had been read. Two halves of one file
                # disagreeing. Which clock answered is recorded, because a
                # server timestamp is a weaker claim than a source timestamp and
                # the reader is entitled to know which it got.
                when, clock = value.SourceTimestamp, "source"
                if when is None:
                    when, clock = value.ServerTimestamp, "server"
                if when is None:
                    when, clock = _dt.datetime.now(_dt.timezone.utc), "client"
                clocks.add(clock)
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
            # `source` is the server's own stamp; `server` is when the server
            # processed the read; `client` is this machine's clock, which is the
            # weakest and is recorded as such rather than presented as the
            # server's.
            "timestamps_from": sorted(clocks),
            # The digest that was actually compared, so a certificate reading
            # this walk can check the pin rather than read the word `pinned`.
            **({"server_cert_sha256": pinned.digest} if pinned else {}),
        },
        "samples": [seen[key] for key in sorted(seen)],
    }


def capture(register: Dict[str, Any], endpoint: str, *, samples: int = 5,
            budget_s: float = 30.0, namespace: Optional[str] = None,
            security: Optional[Dict[str, Any]] = None,
            security_string: Optional[str] = None,
            user: Optional[str] = None,
            password: Optional[str] = None,
            pin: Optional[str] = None) -> Dict[str, Any]:
    """A walk, read from a live server. Raises nothing the CLI cannot describe."""
    import asyncio
    wanted = declared_nodes(register)
    if not wanted:
        raise formats.Refusal("register", "declares no node ids to capture")
    return asyncio.run(_walk(endpoint, wanted, samples=samples,
                             budget_s=budget_s, namespace=namespace,
                             security=security,
                             security_string=security_string,
                             user=user, password=password, pin=pin))


def security_string(security: Dict[str, Any], cert: Optional[str],
                    key: Optional[str]) -> Optional[str]:
    """`asyncua`'s own form, built only once the flags have been accepted."""
    if security["security_policy"] == "None":
        return None
    return (f"{security['security_policy']},{security['security_mode']},"
            f"{cert},{key}")


def membership(register: Dict[str, Any], endpoint: str, *,
               security_string: Optional[str] = None,
               user: Optional[str] = None, password: Optional[str] = None,
               namespace: Optional[str] = None) -> Dict[str, Any]:
    """The same channel and the same namespace resolution as the walk.

    This took the endpoint and nothing else, so `--membership-cache` with a
    security policy and credentials dialled the server anonymously and in clear
    -- and compared membership at namespace index 2 whatever `--namespace` said.
    """
    import asyncio
    return asyncio.run(_membership(
        endpoint, declared_nodes(register), security_string=security_string,
        user=user, password=password, namespace=namespace))


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
