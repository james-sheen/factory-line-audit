#!/usr/bin/env python3
"""P4: every status word the client library can report, graded.

BRIDGES C3: derive what it will judge by RUNNING it against the exact version
you pin, and write the probe as code that re-runs rather than a table in a
document. A status-word table is a written vocabulary, and this one rotted
before anybody read it twice.

## What this found the day it was written

OPC UA names these codes without separators -- `GoodLocalOverride`,
`BadDeviceFailure`, `GoodSubNormal` -- and that is what `asyncua` reports.
`presence.grade` matched on `good_`, `bad_` and `uncertain_`, which are the
spellings the SYNTHETIC corpus uses. So every compound word a real server
returns fell through to the unknown-word branch and graded `uncertain`:

* `GoodSubNormal` graded unusable, so a tag that was reading would be reported
  `present_not_reading` -- the three-state answer inverted for that tag.
* `GoodLocalOverride` graded not-substituted, so the substituted count could
  never fire against a live server. That count is the whole reason this package
  distinguishes a value a person typed at an HMI from one the process produced.

It survived because the battery's collector translated every code it read into
one of three corpus spellings before Stage 1 ever saw it. The fixture agreed
with the grader because a layer in between was making them agree, and the live
rung passed throughout: `bad` and `uncertain` both grade unusable, so the counts
matched while the reason silently did not.

## Why the whole library and not the surface's three words

The rung-3 surface serves what the corpus tells it to, so a probe driven by the
surface measures the corpus. The population that matters is every word the
client library can hand this package, which is what a real PLC can produce.

    python3 battery/probe_status_words.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "status_words.json")

#: Good codes that say a PERSON put the value there. An axiom evaluated on one
#: of these is measuring the operator, not the process.
SUBSTITUTING = ("override", "edited")


def measure() -> dict:
    sys.path.insert(0, os.path.join(ROOT, "src"))
    try:
        import asyncua
        from asyncua import ua
    except ImportError as missing:
        return {"code": 2, "note": f"asyncua is not installed, so no status "
                                   f"word was graded: {missing}"}
    from factory_line_audit.presence import QUALITY_GRADES, grade

    names = [n for n in dir(ua.StatusCodes) if not n.startswith("_")]
    graded, problems = {}, []
    for name in sorted(names):
        word = ua.StatusCode(getattr(ua.StatusCodes, name)).name or name
        grade_name, props = grade(word)
        graded[word] = {"grade": grade_name, "usable": props["usable"],
                        "substituted": props["substituted"]}
        if name.startswith("Good") and not props["usable"]:
            problems.append(f"{word} is a Good code and grades {grade_name}, "
                            f"which is not usable: a tag that IS reading would "
                            f"be reported as not reading")
        if name.startswith(("Bad", "Uncertain")) and props["usable"]:
            problems.append(f"{word} grades {grade_name}, which is usable: an "
                            f"invariant would be judged on a value the server "
                            f"does not stand behind")
        if (name.startswith("Good") and any(s in name.lower() for s in SUBSTITUTING)
                and not props["substituted"]):
            problems.append(f"{word} says a person put the value there and "
                            f"grades {grade_name}, which is not substituted")

    # NON-VACUITY. Every claim above is over `names`, and an empty enumeration
    # satisfies all of them. It is also the shape that would follow from
    # `asyncua` moving where it keeps these.
    if len(names) < 50:
        return {"code": 2, "asyncua": asyncua.__version__,
                "note": f"only {len(names)} status code(s) were enumerated; "
                        f"the library keeps hundreds, so this probe is looking "
                        f"in the wrong place and proves nothing"}

    counts = {}
    for row in graded.values():
        counts[row["grade"]] = counts.get(row["grade"], 0) + 1
    answer = {"asyncua": asyncua.__version__, "codes": len(names),
              "grades": counts, "graded": graded,
              "grades_declared": sorted(QUALITY_GRADES)}
    if problems:
        answer.update(code=1, note=f"{len(problems)} status word(s) grade in a "
                                   f"way that would misreport a real server: "
                                   f"{problems[:3]}", problems=problems)
    else:
        answer.update(code=0, note=f"asyncua {asyncua.__version__}: all "
                                   f"{len(names)} status codes grade into "
                                   f"{sorted(counts)}, every Good usable, every "
                                   f"Bad and Uncertain not, and every code that "
                                   f"names a substitution marked as one")
    return answer


def main() -> int:
    answer = measure()
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(answer, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"  status-words {answer['code']}  {answer['note']}", file=sys.stderr)
    print(json.dumps({k: v for k, v in answer.items() if k != "graded"},
                     indent=2, sort_keys=True))
    return answer["code"]


if __name__ == "__main__":
    raise SystemExit(main())
