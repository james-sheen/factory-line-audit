# factory-line-audit

A bridge from a discrete-manufacturing line to
[`arbiter-engine`](https://github.com/james-sheen/arbiter), built to the method
in that repository's `BRIDGES.md` against nothing but its published surfaces.

**The engine and this bridge share an author.** So the exam below is a
deliberate self-exam, not the independent adoption `BRIDGES.md` asks for, and
this sentence used to say otherwise. What the findings rest on is the method
rather than the distance: the bridge was written from the published document and
the released package, and every claim names the probe that produced it. Read
them as a first pass by someone holding every advantage.

The engine judges series and properties it is handed and refuses to invent a fact
to fill a gap. Everything it refuses to own -- what exists on the line, what each
tag is, what is deliberately not watched, what only an operator can know, what
gets fed and when, and how a verdict becomes an exit code -- is here.

**Its purpose is twofold.** It is a working audit tool for a cell of stations,
presses, robots and controllers read over OPC UA. It is also an exam of the
method: `BRIDGES.md` invites the first vertical that shares no vocabulary with
its worked examples to report the parts that do not survive contact.
[FINDINGS.md](FINDINGS.md) is that report: findings against the method, findings
against the engine and its modelling guide, and **both** of the findings the
previous attempt at this bridge left to be filed upstream, withdrawn because
re-measurement did not reproduce them.

**Status: a live-but-safe surface read for real -- the third of the four rungs
named below.** Thirteen battery legs green against
`arbiter-engine 0.1.10` from PyPI, including a real OPC UA server read by a real
client and the built wheel installed into an empty environment. Nothing here has
touched a plant. Every number in `examples/` is invented.

---

## The two stages

**Stage 1 -- presence.** Given a register of what should exist and a walk of what
the server served, classify every declared tag three ways: reading, present but
not reading, absent. This has **no dependencies at all**, and asserting that is
a test rather than a promise.

**Stage 2 -- detection.** Generate a model and a manifest from the register plus
reviewed operator declarations, feed only what Stage 1 saw reading, and turn the
engine's envelope into an exit code, an attestation and a human report.

```
register.json ─┬─> presence ──> presence/1
               │       │
declarations ──┤       └────────┐  (only reading tags are fed)
   (gated)     │                v
               └─> generate ──> model.yaml + manifest/1 ──> detect ──> attest/1
                                                                        exit {0,1,2}
```

## Exit codes

`0` clean, `1` findings, `2` could-not-complete. `2` never reads as clean and `2`
beats `1`. Composed as the maximum over every leg, with each floor decided at
design time in `exit_contract.py` -- including, unusually, floors for **findings**
as well as declines. The reason is measured and is in
[FINDINGS.md A3](FINDINGS.md).

## Quick start

```bash
git clone https://github.com/james-sheen/factory-line-audit
cd factory-line-audit
python3 -m virtualenv /tmp/v && /tmp/v/bin/pip install -e '.[detect,live]'
export PYTHONPATH=src

# C3 -- measure the engine you pinned. Everything else derives from this.
/tmp/v/bin/python battery/probe_engine.py

# the corpus, sized from those floors and stamped at build time
python3 battery/make_corpus.py

# Stage 1, with the engine uninstalled if you like
python3 -m factory_line_audit.cli presence \
    --register examples/asset_register.json --walk battery/corpus/clean.json

# the channel and its gate
python3 -m factory_line_audit.cli draft --register examples/asset_register.json --out /tmp/d.json   # 0
python3 -m factory_line_audit.cli gate  --register examples/asset_register.json /tmp/d.json         # 2, names it
python3 -m factory_line_audit.cli gate  --register examples/asset_register.json \
    examples/declarations/line1.fixture.json                                                        # 0

# Stage 2
/tmp/v/bin/python -m factory_line_audit.cli detect \
    --register examples/asset_register.json --walk battery/corpus/clean.json \
    --declarations examples/declarations/line1.fixture.json --attest-out /tmp/attest.json

# C8 -- exercise both declared ranges, floors included (installs each release; slow)
python3 battery/probe_pin.py

# does the core still accept this vertical? two imports, and CI runs it too
/tmp/v/bin/python battery/probe_conformance.py

# the whole battery
/tmp/v/bin/python battery/run_battery.py --python /tmp/v/bin/python --live-python /tmp/v/bin/python
```

## The verification battery

Sixteen legs: the twelve in `BRIDGES.md`'s verification battery, plus four added
with the argument written down.

All five additions started here. `pin` was proposed by this package and is now a
row in the guide's own table, so it is no longer an addition and is unmarked
below. `corpus`, `conformance`, `regression` and `capture` still are.

| Leg | Question |
|---|---|
| `corpus` **added** | Is the corpus still inside the narrowest measured window? |
| `live` | Can a live OPC UA surface be read at all, and how many nodes did it serve? |
| `capture` **added** | Does the shipped verb print one OUTCOME line, a handle `sha256sum` agrees with, and a membership cache holding no reading? |
| `draft` | Does draft tooling emit an unreviewed statement and exit clean? |
| `gate` | Does the gate then refuse that exact file, by name? |
| `clean` | Over an uncontaminated corpus, does the pipeline stay quiet? |
| `fault` | For each of thirteen fault classes, is the injected thing found? |
| `absent` | Is a declared-but-absent source a finding, not an incompleteness? |
| `attest` | Does attestation work through the same front door? |
| `pipe` | Does a reader walking away change the verdict, or print anything? |
| `tool` | Is the tool surface closed, and does every entry construct? |
| `suite` | Does the suite pass from a directory that is not the repository? |
| `conformance` **added** | Does the core's own kit still accept this vertical, and does its noun reach the core? |
| `regression` **added** | Does a declared prefix move pair, and the same move undeclared get reported and not applied? |
| `pin` | Does every release inside each declared range actually run? |
| `ship` | Does the built artifact, installed clean, still do all of that? |

A leg that could not run reports `2` and is **named**, never skipped.
`--only NAME` runs a subset; a name no leg carries is refused rather than
answered with an empty run, and the result file records the selection so a
partial run cannot read as a full one.

Most of the battery is run by hand, because it builds a wheel and installs
every release in two ranges. Three legs are the exception and run in CI:
`conformance` on every interpreter, because it costs two imports and is the
only leg whose question is about software this package does not control; and
`live` and `capture` on one, because the OPC UA surface is anonymous,
localhost and over in seconds, and `capture` is the only verb here that talks
to anything. `probe_status_words.py` runs beside them: it grades every status
word `asyncua` can report, which is the population a real PLC draws from
rather than the three the corpus happens to carry. A leg nothing triggers is a leg nobody reads, which is the same
argument the legs themselves are written from.

## Formats

All JSON, all carrying a `format` string, all refusing an unknown major by name.

| Format | What it is |
|---|---|
| `factory-line-audit/register/1` | What should exist: assets, tags with a declared `class` and node id, typed relations |
| `factory-line-audit/walk/1` | What the server served, with per-reading status word and source timestamp |
| `factory-line-audit/presence/1` | Stage 1's three-way classification |
| `factory-line-audit/declaration/1` | Operator statements, each with a `basis`, and a review marker |
| `factory-line-audit/manifest/1` | Everything excluded from the model with a reason, the entity-type map, and every indicator this package derived |
| `factory-line-audit/attest/1` | Per-run record: checked, declined, not-established, engine strings verbatim, exit |

## Declarations

A rule can propose an operator-knowledge fact. It cannot know one. Every
statement carries a `basis` -- what the declarer actually looked at -- and
`draft` emits them unreviewed with every basis empty and every number null,
because the one thing a rule cannot supply is why.

Kinds: `bound`, `setpoint`, `rate`, `redundant`, `conservation`,
`expect_variation`, `slow_oscillation`, `gate_on`, `exclusion`. Each maps onto
exactly one thing the engine would otherwise decline, which is the decline
vocabulary read backwards.

A file becomes usable when a person adds their name **and** the date. A test
fixture passes only by disclosing itself on its face, never by naming a reviewer.

## The evidence ladder

| Rung | What it is | Here |
|---|---|---|
| 1 | Synthetic corpus | `battery/corpus/clean.json`, sized from measured floors |
| 2 | Mutated copies | thirteen one-fault copies with expectations declared before the run |
| 3 | A live-but-safe surface | `battery/opcua_surface.py` -- a real server, a real client, localhost |
| 4 | First contact | **not climbed.** A person, a plant, a register exported from that plant's MES, declarations signed by that plant's engineers |

Rung 3 is evidence that the walk format survives a real client, that node ids
resolve, that a status word comes back as a status word, and that a node which is
not there fails the way Stage 1 says it does. It is **not** evidence about
security, certificates, a vendor's address space, or load.

First contact is deliberately absent from the tool surface as well, and the
closure test asserts that absence.

## What this package does not claim

- No number in `examples/` is a fact about a real machine. The declaration file
  says so on its face and every `basis` string begins `FIXTURE`.
- The engine measured is `0.1.10` from PyPI, and `0.1.11.dev0` from `master` was
  run too. Any other pin needs `probe_engine.py` re-run, not re-read.
- Ten of the twelve decline reasons are reachable from a model this package could
  generate. `not_applicable` and `checker_error` are engine-side.
- The learned-baseline warning arm has a measured false-positive rate of roughly
  one series in twelve. It is reported in full and floored at 0, and that is a
  judgement, written down in `exit_contract.py` with the measurement behind it.
