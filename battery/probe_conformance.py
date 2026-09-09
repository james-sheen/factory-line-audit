#!/usr/bin/env python3
"""Ask the core's own kit whether it still accepts this vertical.

`presence-audit` ships `conformance.check_a_vocabulary`, driven by stand-ins
that implement the protocols and **nothing else**. Its docstring records why it
exists: the core once called `.points` on a capture the protocol did not
declare, every test passed because the only vertical in existence happened to
have that member, and a second vertical found it months later. This package is
that second vertical.

Every other probe and leg here asks whether this bridge satisfies itself. This
one asks whether it still satisfies the core it pins, which is the question no
test in this repository can answer, because every one of them is written by the
same author as the vertical.

Run directly, it exits 0/1/2 and prints one JSON document. `run_battery.py`'s
`conformance` leg runs this same file under whichever interpreter carries the
`[vertical]` extra and reports the code this returns -- so the decision lives
here, once, rather than in two places that would drift.

    python3 battery/probe_conformance.py
"""
from __future__ import annotations

import json
import sys

#: What this vertical calls its points. Held here rather than imported, because
#: the check below is that the core RENDERS this -- comparing the core's answer
#: against the vertical's own attribute would compare the vertical with itself
#: and pass however the member is declared.
EXPECTED_NOUN = ("tag", "tags")


def _problems(result):
    """The kit returns `(problems, observations)`; only the first is a claim."""
    return list(result[0] if isinstance(result, tuple) else result)


class _TooShort:
    """A vocabulary with four members, for the non-vacuity control below."""

    kinds = ("measurement",)
    count_keys = {}

    def classify(self, declared_type):
        return "measurement"


def measure() -> dict:
    """Always one document, always a code. A traceback escaping here would
    break both halves of that contract, and it did: run against a core older
    than `vocabulary.using`, this raised, and `probe_pin.py` recorded the
    frames -- absolute build paths and all -- into a file that ships. The
    repository's own hygiene gate refused the commit, which is the gate working.
    An older core is a fact about the range, not a crash."""
    try:
        from presence_audit.conformance import (check_a_vocabulary,
                                                check_the_core)
        import presence_audit as core
        import presence_audit.vocabulary as vocabulary
        from factory_line_audit.vertical import FactoryLineVocabulary
    except Exception as missing:
        return {"code": 2,
                "note": f"the [vertical] extra is not installed in this "
                        f"interpreter, so the core never judged this vertical: "
                        f"{type(missing).__name__}: {missing}"}
    try:
        return _measure(check_a_vocabulary, check_the_core, core, vocabulary,
                        FactoryLineVocabulary)
    except Exception as broke:
        return {"code": 2, "presence_audit": getattr(core, "__version__", "?"),
                "note": f"the core is installed and this probe could not put a "
                        f"question to it: {type(broke).__name__}: {broke}"}


def _measure(check_a_vocabulary, check_the_core, core, vocabulary,
             FactoryLineVocabulary) -> dict:

    core_problems = _problems(check_the_core())
    mine = _problems(check_a_vocabulary(FactoryLineVocabulary()))

    # NON-VACUITY. Everything above is a negative claim, and a kit that had
    # stopped checking would satisfy all of them by saying nothing. A stand-in
    # that is deliberately short has to come back with something, or a clean
    # answer above means nothing at all.
    control = _problems(check_a_vocabulary(_TooShort()))

    # The noun the core will actually RENDER, which is not among the members the
    # kit checks. `noun` is read as an attribute and falls back to the core's own
    # default on any malformed answer -- a bare string, or a method where a
    # property is read -- so a refactor reinstates the defect this vertical
    # already had once, its reports naming a press cell's tags as sensors, and
    # a clean conformance run says nothing. Filed upstream as presence-audit #1;
    # until it is answered this leg is the only thing that would notice.
    with vocabulary.using(FactoryLineVocabulary()):
        rendered = tuple(vocabulary.noun())

    answer = {"presence_audit": core.__version__, "core": core_problems,
              "vocabulary": mine, "control": len(control),
              "noun_rendered_by_the_core": list(rendered)}

    if not control:
        answer.update(code=2, note="the kit reported nothing against a "
                                   "deliberately short vocabulary, so it is not "
                                   "checking; the clean answers beside this "
                                   "would mean nothing")
    elif core_problems:
        answer.update(code=1, note=f"the core does not satisfy its own kit: "
                                   f"{core_problems}")
    elif mine:
        answer.update(code=1, note=f"this vertical does not satisfy the core's "
                                   f"kit: {mine}")
    elif rendered != EXPECTED_NOUN:
        answer.update(code=1, note=f"the core renders {rendered}, not "
                                   f"{EXPECTED_NOUN}; `noun` is read as an "
                                   f"ATTRIBUTE and falls back silently, and the "
                                   f"kit does not check it")
    else:
        answer.update(code=0, note=f"presence-audit {core.__version__}: core "
                                   f"clean, this vertical clean, the kit named "
                                   f"{len(control)} problem(s) against a short "
                                   f"stand-in, and the core renders {rendered}")
    return answer


def main() -> int:
    answer = measure()
    print(json.dumps(answer, indent=2))
    print(f"  conformance {answer['code']}  {answer['note']}", file=sys.stderr)
    return answer["code"]


if __name__ == "__main__":
    raise SystemExit(main())
