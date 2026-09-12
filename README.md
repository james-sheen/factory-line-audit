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

**Released -- 0.1.10**, tagged `v0.1.10`, Apache-2.0, on PyPI as
[`factory-line-audit`](https://pypi.org/project/factory-line-audit/).

**Status: a live-but-safe surface read for real -- the third of the four rungs
named below.** Nineteen battery legs green, including a real OPC UA server read
by a real client, the built wheel installed into an empty environment, and a
sweep of the whole `arbiter-engine` range this package declares. Nothing here has
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

## The verbs

Nine, and the page names all nine because a verb nobody documents is a verb
nobody runs.

* **`presence`** -- Stage 1: what the register declares against what the walk
  served, classified three ways. No dependencies.
* **`validate-walk`** -- everything wrong with a walk file, or nothing. A
  receiver checking a file: no engine, no core, no server. A malformed walk is
  *could not complete*, never a finding, because a file that would not read is
  not a finding about the line.
* **`draft`** -- propose the declarations a person would have to make, every
  basis empty and every number null. Exits clean; `gate` refuses what it wrote.
* **`gate`** -- refuse unreviewed declarations, naming the file.
* **`generate`** -- the model and the manifest, as a pair.
* **`detect`** -- Stage 2: feed the engine what Stage 1 saw reading, report, and
  exit on the contract above.
* **`attest`** -- re-report a stored attestation through the same front door,
  and reach the same verdict.
* **`capture`** -- read a live OPC UA server and write a walk.
* **`regression`** -- two walks of one line, oldest first. An undeclared prefix
  shift is reported, never applied.

## Exit codes

`0` clean, `1` findings, `2` could-not-complete. `2` never reads as clean and `2`
beats `1`. Composed as the maximum over every leg, with each floor decided at
design time in `exit_contract.py` -- including, unusually, floors for **findings**
as well as declines. The reason is measured and is in
[FINDINGS.md A3](FINDINGS.md).

## Quick start

To use it: `pip install 'factory-line-audit[detect,live]'`. To work on it, or to
run the verification battery below, take a checkout instead:

```bash
git clone https://github.com/james-sheen/factory-line-audit
cd factory-line-audit
python3 -m virtualenv .venv && .venv/bin/pip install -e '.[detect,live]'
export PYTHONPATH=src

# C3 -- measure the engine you pinned. Everything else derives from this.
.venv/bin/python battery/probe_engine.py

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
.venv/bin/python -m factory_line_audit.cli detect \
    --register examples/asset_register.json --walk battery/corpus/clean.json \
    --declarations examples/declarations/line1.fixture.json --attest-out /tmp/attest.json

# C8 -- exercise both declared ranges, floors included (installs each release; slow)
python3 battery/probe_pin.py

# does the core still accept this vertical? two imports, and CI runs it too
.venv/bin/python battery/probe_conformance.py

# the whole battery
.venv/bin/python battery/run_battery.py --python .venv/bin/python --live-python .venv/bin/python
```

## The verification battery

Nineteen legs: the twelve in `BRIDGES.md`'s verification battery, plus the ones
this package added, each with the argument written down.

Every addition started here. `pin` was proposed by this package and is now a
row in the guide's own table, so it is no longer an addition and is unmarked
below. `corpus`, `conformance`, `regression`, `capture`, `engine`,
`pin_channel` and `orchestrator` still are.

| Leg | Question |
|---|---|
| `engine` **added** | Does `probe_engine.py` still complete, and do the committed floors still describe the engine that resolves? |
| `corpus` **added** | Is the corpus still inside the narrowest measured window? |
| `live` | Can a live OPC UA surface be read at all, and how many nodes did it serve? |
| `capture` **added** | Does the shipped verb print one OUTCOME line, a handle `sha256sum` agrees with, and a membership cache holding no reading? |
| `draft` | Does draft tooling emit an unreviewed statement and exit clean? |
| `gate` | Does the gate then refuse that exact file, by name? |
| `clean` | Over an uncontaminated corpus, does the pipeline stay quiet? |
| `fault` | For each of fourteen fault classes, is the injected thing found? |
| `absent` | Is a declared-but-absent source a finding, not an incompleteness? |
| `attest` | Does attestation work through the same front door? |
| `pipe` | Does a reader walking away change the verdict, or print anything? |
| `tool` | Is the tool surface closed, and does every entry construct? |
| `suite` | Does the suite pass from a directory that is not the repository? |
| `conformance` **added** | Does the core's own kit still accept this vertical, and does its noun reach the core? |
| `regression` **added** | Does a declared prefix move pair, and the same move undeclared get reported and not applied? |
| `orchestrator` **added** | Does this package register as a `qa-orchestrator` vertical, hand back all three registries, refuse another vertical's entity, and does the wrong-on-purpose scenario still fail? |
| `pin_channel` **added** | Over a channel that has a certificate, does the client library actually call the pin -- does a right digest walk and a wrong one refuse, naming both? |
| `pin` | Does every release inside each declared range actually run? |
| `ship` | Does the built artifact, installed clean, still do all of that? |

A leg that could not run reports `2` and is **named**, never skipped.
`--only NAME` runs a subset; a name no leg carries is refused rather than
answered with an empty run, and the result file records the selection so a
partial run cannot read as a full one.

The whole battery runs in CI, on every push, in under a minute. It is that
cheap because `pin` reads the evidence `probe_pin.py` wrote rather than
sweeping: the sweep installs every release in two ranges and runs weekly in its
own workflow. Three legs also run a second time on their own terms, and the
duplication is the point: `conformance` on every interpreter, because it costs
two imports and is the only leg whose question is about software this package
does not control; and `live` and `capture` in a job that installs the OPC UA
client and nothing else, which is the only way either can say `capture` needs no
axiom engine to read a server. `probe_status_words.py` runs beside them: it grades every status
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
| `factory-line-audit/regression/1` | Two walks of one line compared: pairs, removals, additions, and any undeclared prefix move |
| `factory-line-audit/membership/1` | Which declared nodes the address space still holds, and the namespaces; no value read |

## Declarations

A rule can propose an operator-knowledge fact. It cannot know one. Every
statement carries a `basis` -- what the declarer actually looked at -- and
`draft` emits them unreviewed with every basis empty and every number null,
because the one thing a rule cannot supply is why.

Kinds: `bound`, `setpoint`, `rate`, `reset`, `redundant`, `conservation`,
`expect_variation`, `slow_oscillation`, `gate_on`, `bad_state`, `exclusion`.
Each maps onto exactly one thing the engine would otherwise decline, which is
the decline vocabulary read backwards -- except `reset`, which answers something
the engine never declines: it routes a counter that drops to zero from its own
default and says nothing about having done so.

A file becomes usable when a person adds their name **and** the date. A test
fixture passes only by disclosing itself on its face, never by naming a reviewer.

**Upgrading, if you keep declaration files.** Three refusals arrived in 0.1.6 and
0.1.7, each replacing something that was accepted and then ignored; 0.1.8 then
narrowed one of them back, because it refused a file the generator supports.
0.1.9 refuses nothing new about a FILE and adds one stop about a WALK. 0.1.10
refuses nothing new at all and changes one thing a reader can feel: a
`--membership-cache` written by any earlier version no longer justifies skipping
a walk, so the first pass after upgrading takes one. The full history is in
[CHANGELOG.md](CHANGELOG.md).

* `allow_reset` is a `reset` statement of its own (0.1.6). It used to be read off
  a `rate` statement and validated by nothing, so a misspelling read as a
  declaration while the engine routed from its own default. A `rate` statement
  still carrying it is refused by name, pointing at where it moved. A counter with
  no `reset` statement is recorded in the manifest as running on the engine's
  routing -- a line in a report, not an error.
* `gate_on` takes `open_when`, a list of the state WORDS that mean the check
  applies (0.1.7). The gate read `bool(value)`, and every non-empty word a PLC
  produces is true in Python -- so a station reporting `Stopped` opened the gate
  and the run judged a takt the station was not running to. Where the state is
  not a boolean and no `open_when` is declared, `detect` stops rather than
  guesses. `required_property` must also name a `state`-class tag on the same
  asset.
* A statement declared twice is refused (0.1.7), across every accepted file. The
  generator reads the first of MOST kinds, so the second was accepted and ignored
  -- and across two files the earlier file won, an ordering nobody declared.
  An `exclusion` naming a tag the register does not have is refused for the same
  reason: it excluded nothing and was recorded as an exclusion.
* **0.1.8 narrows that rule back.** `conservation` and `exclusion` are ITERATED
  by the generator, not read at `[0]`, so two balances on one asset are legal and
  both take effect -- and 0.1.7 refused them, telling you the generator would
  ignore one. Two statements of those kinds now collide only when they are the
  same statement: the same balance over the same tags, or the same exclusion for
  the same reason.
* **0.1.8 widens `open_when`** to accept integer state codes. A PLC serving its
  running flag as Int16 or Byte `0/1` had no legal declaration in 0.1.7: no
  `open_when` hard stopped, `[1]` was refused as malformed, and `["1"]` was
  accepted and then withheld every sample, because `1 in ["1"]` is false. Where
  the declared values could never equal what the server serves, `detect` now
  stops and says so instead of withholding everything and letting the engine
  report a missing property.
* **0.1.9 adds a third gate stop, `gate_unreadable`.** The two above are about
  the DECLARATION. This one is about the gate tag. Across the samples in which
  the GATED tag itself read usably -- the samples that should have been fed --
  the gate read usably **in none of them**, so every one was withheld because
  the gate could not be consulted, nothing was fed, and the engine's
  `missing_property` was classed `bridge_defect` -- a mapping bug in this
  package -- at exit 2, for a tag the server could not read. A gate that read
  usably in even one of those samples is untouched: one patchy sample is a
  stopped station, not a broken declaration.
* **0.1.10 narrows the paragraph above, which described a stop this package does
  not have.** It stated the condition over the whole walk, twice, and the stop is
  judged only over the samples the gated tag read in -- a gate that reads where
  the gated tag does not has told this package nothing about the readings it has.
  Measured: a walk whose gate reads usably in forty of fifty samples still stops,
  because the ten that mattered got nothing. The stop's own message was narrowed
  in 0.1.9 and this page was not, so the page went on describing a wider stop
  than the one that ships. The retired wording is not quoted here: a guard
  holding this page to the narrow condition would find it and fire on the
  sentence explaining the change.
* **An absent gate tag reaches the same stop, and the run exits 2 rather than
  1.** A `required_property` the address space does not hold is graded `absent`
  by Stage 1 -- a finding about the line, floor 1 -- and arrives here as *not
  served in this sample*, which is a hard stop: could-not-complete. Both
  readings of that state are defensible; the exit code is the second one,
  because no verdict about the gated tag was established. Stage 1's report is
  where the absence is reported as a finding.
* **0.1.10: the cache also records whether a walk followed.** It is written
  before the walk is attempted, which is deliberate -- the server has already
  been dialled and what that learned is recorded whatever happens next -- so a
  pass that read the membership and then lost the server left a cache saying the
  address space holds exactly these nodes and nothing saying no walk was taken.
  The next run found the membership unchanged, reported `unchanged`, exited 0 and
  read nothing. `--membership-cache` now shortcuts only when a walk stands behind
  the cache, and says which one. Nothing to do: a cache from an earlier version
  carries no such record and is not reused, and the next pass writes one.
* **0.1.9: a membership cache now records the channel of every pass**, not only
  of passes where the membership changed. A `--membership-cache` written by 0.1.7
  carries no `pinned` field, and until 0.1.9 a pinned run against an unchanged
  address space did not add one -- so a later run that dropped the pin found
  nothing to refuse and exited 0 off the same cache. Nothing to do: the upgrade
  happens on the next pinned run.

## The evidence ladder

| Rung | What it is | Here |
|---|---|---|
| 1 | Synthetic corpus | `battery/corpus/clean.json`, sized from measured floors |
| 2 | Mutated copies | fourteen one-fault copies with expectations declared before the run |
| 3 | A live-but-safe surface | `battery/opcua_surface.py` -- a real server, a real client, localhost |
| 4 | First contact | **not climbed.** A person, a plant, a register exported from that plant's MES, declarations signed by that plant's engineers |

Rung 3 is evidence that the walk format survives a real client, that node ids
resolve, that a status word comes back as a status word, and that a node which is
not there fails the way Stage 1 says it does. Since 0.1.8 it also serves
Basic256Sha256/SignAndEncrypt with a self-signed certificate, so it is evidence
that `--server-cert-pin-sha256` reaches the client library's validator hook: a
matching digest walks and records the certificate the server presented, and a
wrong one refuses naming both. That line was previously *not evidence about
security, certificates, ...*, and the half about this package's own pin was the
half that stopped being true.

It is still **not** evidence about a plant's PKI, a certificate anybody else
signed, authentication, a vendor's address space, or load.

First contact is deliberately absent from the tool surface as well, and the
closure test asserts that absence.

## What this package does not claim

- No number in `examples/` is a fact about a real machine. The declaration file
  says so on its face and every `basis` string begins `FIXTURE`.
- The engine measured is whichever one `src/factory_line_audit/engine_floors.json`
  records, and
  the `engine` battery leg goes red when that file stops describing the engine
  that resolves here. Any other pin needs `probe_engine.py` re-run, not re-read.
  This line named a version until 2026-09-09, by which time the file recorded a
  later one.
- Ten of the twelve decline reasons are reachable from a model this package could
  generate. `not_applicable` and `checker_error` are engine-side.
- The learned-baseline warning arm has a measured false-positive rate of roughly
  one series in twelve. It is reported in full and floored at 0, and that is a
  judgement, written down in `exit_contract.py` with the measurement behind it.

---

Security reports go through [SECURITY.md](SECURITY.md), privately -- for the
failure modes listed there, filing the report in public *is* the disclosure.
[CONTRIBUTING.md](CONTRIBUTING.md) has the one thing a fresh clone will not tell
you: the hooks are per-clone and off until you enable them.
