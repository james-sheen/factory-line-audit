"""Every artifact format this package reads or writes, and the refusal.

BRIDGES's exit contract: *version every artifact format you emit as
`<package>/<artifact>/<n>`, and refuse unknown majors.* One function does the
refusing so that a new reader cannot forget to, and so the refusal message has
one shape: it names the file.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

PACKAGE = "factory-line-audit"

REGISTER = f"{PACKAGE}/register/1"
WALK = f"{PACKAGE}/walk/1"
PRESENCE = f"{PACKAGE}/presence/1"
DECLARATION = f"{PACKAGE}/declaration/1"
MANIFEST = f"{PACKAGE}/manifest/1"
ATTEST = f"{PACKAGE}/attest/1"
#: Written by `regression` and by `capture --membership-cache`. They were
#: emitted with a version string and listed nowhere: not here, so `load` could
#: not refuse an unknown major of either, and not in the README's table, so the
#: page's *all refusing an unknown major by name* was a claim about six of eight.
REGRESSION = f"{PACKAGE}/regression/1"
MEMBERSHIP = f"{PACKAGE}/membership/1"

ALL = (REGISTER, WALK, PRESENCE, DECLARATION, MANIFEST, ATTEST,
       REGRESSION, MEMBERSHIP)


class Refusal(Exception):
    """A refusal, which is always exit 2 and always names the file.

    Not a subclass of anything the standard library raises, because a bare
    `except Exception` in a caller must not be able to turn a refusal into a
    result. BRIDGES C6: no exception path escapes the contract.
    """

    def __init__(self, path: Any, message: str):
        self.path = str(path)
        self.message = message
        super().__init__(f"{self.path}: {message}")


def split(fmt: str) -> tuple:
    head, _, major = str(fmt).rpartition("/")
    return head, major


def load(path: str, expected: str) -> Dict[str, Any]:
    """Read a JSON artifact and refuse anything that is not the expected format.

    Refuses on: unreadable, not JSON, not an object, no `format` key, a
    different artifact, and a different major of the same artifact. The last
    two produce different messages -- *this is a walk, not a register* and
    *this is a register from a later version of this package* are different
    problems for the person holding it.
    """
    if not os.path.exists(path):
        raise Refusal(path, "no such file")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            body = json.load(handle)
    except json.JSONDecodeError as exc:
        raise Refusal(path, f"not JSON ({exc.msg} at line {exc.lineno})")
    except OSError as exc:
        raise Refusal(path, f"unreadable ({exc.strerror})")
    if not isinstance(body, dict):
        raise Refusal(path, f"expected a JSON object, found {type(body).__name__}")
    found = body.get("format")
    if found is None:
        raise Refusal(path, f"no format field; expected {expected}")
    if found == expected:
        return body
    want_head, want_major = split(expected)
    got_head, got_major = split(str(found))
    if got_head == want_head:
        raise Refusal(path, f"format {found} is major {got_major}; this reader "
                            f"understands major {want_major} only")
    raise Refusal(path, f"format {found}; expected {expected}")


def dump(path: str, body: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(body, handle, indent=2, sort_keys=False)
        handle.write("\n")
