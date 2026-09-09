# What did not survive contact

`BRIDGES.md` ends by saying that its two worked implementations are both by the
engine's author, that this is a limit on what they prove, and that if you are the
first to carry the method into a vertical sharing no vocabulary with them, **the
parts that do not survive contact are worth more to the document than the parts
that do**.

This file is that, with one correction to the invitation it answers.
`factory-line-audit` was built to the method against `arbiter-engine 0.1.10`
from PyPI, using only published surfaces -- but **it shares an author with the
engine**, so it is a self-exam and not the independent adoption the invitation
asks for. This paragraph claimed independence until it was checked. Section E
already said the engine is *not somebody else's*, two hundred lines further
down, which is where the true half of this was sitting the whole time.

The verification battery is green on all eighteen legs. Everything below is a
place where following the document produced a wrong answer, or where a
measurement contradicted something the surrounding documents say.

Every claim here names the probe that produced it. `battery/probe_engine.py` is
code that re-runs; `battery/engine_floors.json` is its output.

**Which engine each claim is about.** The exam measured `arbiter-engine 0.1.10`,
which is still this package's range floor. Engine fixes recorded below as *fixed
in source* shipped in **0.1.11 (2026-09-04)**; the engine has released 0.1.12 and
0.1.13 since. Where a finding says a release does or does not have something, it
means **that release** -- not whatever the range resolves to on the day you read
this. A range resolves to its newest member, so a fresh install and the floor are
different engines, and this file is about the floor.

---

## A. Findings against the method

> **Sections of `BRIDGES.md` are cited here by TITLE, not by number.** They were
> cited by number until 2026-09-03, when closing A6 inserted a new section and
> silently repointed every reference at or above it. See A9.


### A1. A generated table says it is generated and not when

The decline-vocabulary section states one measurement, and defends it:

> 12 reasons. The set is closed, and this table is generated from the engine in
> this repository rather than transcribed -- a guide that disagreed with it would
> not have been published.

**The claim holds.** See section C1: the table and the engine agree at every
commit. The residue is small and is a suggestion rather than a defect: *generated
from the engine in this repository* is not checkable by a reader who is holding
the document and does not know which commit produced it. A version string beside
the number would make it checkable -- the same move the exit contract already
requires of
every artifact a bridge emits, applied to the one artifact the document itself
emits.

### A2. `missing_entity_type` is ambiguous in exactly the way `missing_property` is

The decline vocabulary tells you what to do with it, unconditionally:

> Not a gap in one entity's data -- a gap between what your model believes exists
> and what your walk found. Treat it as a modelling error, not a collection error.

Three other reasons in the same table get careful two-sided treatment.
`no_current_value` exists *because* collapsing it into `missing_property` hands
an operator the wrong instruction. `precondition_unmet` says outright that the
engine cannot tell you which way to read it. This one gets a rule.

For a bridge that **generates its model from a register**, the rule is wrong. The
register is what the model believes exists; when a station is powered down, every
CONNECTIVITY indicator pointing at it declines `missing_entity_type`, and that is
a collection fact Stage 1 already reported and already floored the run at 1.
Following the document verbatim floored the `absent` leg at 2 -- *could not
complete* for a run that completed and found the thing it was looking for.

**Measured**: `battery/corpus/asset_absent.json`, before and after. The fix is
`exit_contract.classify(..., target_absent=...)`: the same disambiguation
`missing_property` already gets, from the same source, Stage 1.

**Remedy**: the entry needs the two-sided treatment its neighbours have. Which
side you are on depends on whether your model was written by hand or generated,
and the engine cannot know that -- which is the argument the `precondition_unmet`
entry already makes about itself.

### A3. The exit contract gives declines a floor taxonomy and gives findings none

> **Closed 2026-09-03.** It now asks for it: classify findings
> the way you classify declines and floor those classes too, with the working
> distinction stated as **where the number came from** — a declared target is a
> claim about your system, an inferred baseline is a claim about the last N
> samples. The measurements below did NOT go into the guide: its opening rule
> forbids stating engine behaviour there, and C3 is where a reader takes them.
> That generalises past HOMEOSTASIS, which the measured wording would not have.

> Classify every decline into a small closed set of classes, each with a floor.

Nothing is said about findings, and the implied rule -- any finding is a 1 -- is
what a first implementation writes. It is right for a threshold breach, which is
a statement about a number somebody published. It is wrong for an arm whose
output is a tail probability.

**Measured** (probes H3, H4, H6):

| | |
|---|---|
| learned HOMEOSTASIS fires at | 2 sigma `warning`, 3 sigma `critical` |
| over 12 stationary Gaussian series, nothing injected | **1 fired** |
| the same 12 with a declared setpoint at 3 sigma tolerance | **0 fired** |

A line with ten learned baselines -- this one has ten -- produces a warning on
most healthy runs. Undifferentiated `findings -> 1` makes that a failing audit
every other day, which is the definition of a check people turn off.

This is also the trap the prior attempt fell into and named correctly: *do not
simply widen the noise until it passes -- that is choosing the corpus.* The
alternative it proposed, flooring warning-severity learned HOMEOSTASIS at 0, is
what this package does, and the measurement above is the argument for it, which
the proposal did not have.

**Remedy**: findings need classes and floors on the same terms declines do, and
the document should say so. `exit_contract.FINDING_CLASSES` is one shape.

### A4. A corpus expires, and rule 7 does not mention it

> **Closed 2026-09-03.** Injection rule 8, in the guide's own
> words: a corpus for a windowed engine has a shelf life, stamp it when built,
> and have the battery refuse a stale one rather than run against it.

The verification battery, rule 7: *derive the corpus from the engine's floors --
how many
samples, and over what span.* Nothing about **when it was taken**.

**Measured** (probes M3, H2): several arms count inside a window measured
backwards from now. MONOTONICITY's reversal window is about fifteen minutes at
60 s cadence. A corpus written with fixed timestamps therefore stops presenting
those arms as it ages -- silently, and every fault leg that depends on one goes
green having tested nothing.

This happened here. A corpus stamped two days earlier produced eleven
`insufficient_samples` declines reading *fewer points than can exhibit a
reversal* over fifty samples.

**Remedy**: an eighth rule -- a corpus for a windowed engine has a shelf life,
and the battery should refuse a stale one rather than run against it. This
package added a `corpus` leg that does exactly that.

### A5. The battery table has no leg for C8

> **Closed 2026-09-03.** `pin` is a row in the table now, between
> `suite` and `ship` — so this package's leg is no longer an addition, and its
> ADDED marker came off in the same change.

C8 is the one capability that is a claim about software the bridge does not
control: *a range is a claim about every release inside it, so exercise the floor
too.* Every other capability in the list has a leg in the battery table. This
one has none, so the discipline the document is most emphatic about is the one it
does not make you prove.

Added as a `pin` leg (`battery/probe_pin.py`): install every published release in
the declared range, and every release below the floor, and run this package's own
`detect` against each. It found something immediately -- the comment in
`pyproject.toml` explaining *why* the floor is 0.1.10 named the wrong reason. The
run says `unread_properties`; the comment said `add_relationship`. An API
inventory would have agreed with the comment.

### A6. The read surface a bridge needs is never named

> **Closed 2026-09-03.** `bridge-guide.md` gained a section, *The
> three verbs that are not `check`*, covering all three, with the argument that
> a bridge which GENERATES its model has nothing else to proofread it. C2 now
> points at it from the model-and-manifest capability, which is where a bridge
> author is standing when they need it. The insertion renumbered Sections 3-8
> to 4-9; every reference in this file moved with it.

The division says the engine owns "a small read surface". The decline
vocabulary's table, and
every worked example in the document, is about `check`.

Three things a bridge cannot do without, none of them mentioned anywhere:

- **`model_describe().model.unread_fields`** -- the only place the engine says a
  field you declared is read by nobody, or that a *value* you declared was not
  understood.
- **`session.unconsumed_observations()`** -- series you fed that no declared
  indicator reads. This package treats it as a hard stop; it caught a real bug
  here within minutes (state words fed as series).
- **`session.unread_properties()`** -- and this one is load-bearing enough to
  set the floor of the pin range.

A bridge built strictly to the document is blind to its own generated model.

### A7. C1's three-way rule is stated for the stage that reads the walk, not the one that writes it

> **Closed 2026-09-03.** C1 gained the paragraph: the distinction
> has to survive collection, a read that raises is not evidence the source is
> missing, and a client library raises the same way for an absent node and for
> one the server will not vouch for.

> Classify each expected source three ways -- present and reading, present but
> not reading, absent -- never as a boolean.

The collector is upstream of Stage 1, and it can destroy the distinction before
Stage 1 exists. The first version of the OPC UA collector here caught the read
exception and put the node on the absent list. `BadNodeIdUnknown` means the
address space has no such node; every other Bad status means the node is there
and the server will not vouch for its value -- and asyncua raises on both.

Stage 1 could not have recovered it: by then the node was simply not in the walk.

**Remedy**: C1 should say the walk format must be able to express *present and
unreadable*, and that the collector is where that distinction has to be made.

### A8. The review gate's rule is easy to agree with and easy to walk past

> Deriving a relationship from names ... is a guess wearing the costume of a
> derivation.

The prior attempt's design decision 5 -- exclude tags matching `Spare*`,
`Reserved*`, `Template*` at register load -- is that guess, and it was carried
into this package before its own suite caught it. `Spare*` silently excludes
`spared_capacity`, which is a real measurement, and names the exclusion in the
manifest as though it were a decision. No predicate over the letters separates
`SpareAnalog3` from `spared_capacity`.

**The handoff attributed the design to the reference bridge. It does not do
this.** `bmc-sensor-audit`'s `is_templated` matches `\$\w+` -- a literal,
unsubstituted `$variable` token in an entity-manager configuration. That is
syntax, not a guess about a word: a name carrying `$bus` cannot match a live
name, and the code says so and says why. A prefix glob over English words is a
different thing wearing the same label.

So this is not a finding against the method or against the reference bridge; the
method already forbids it and the reference bridge already obeys. It is here
because it is the shape of the mistake a **second** implementer makes: reading
"templated names are excluded" in a worked example, reaching for the nearest
mechanism, and landing on the wrong side of a line the document draws clearly two
sections later. A worked example is read for its outcome; the reason lives in its
source.

The rule now *proposes* an exclusion through `draft`, and only a declared
`"templated": true` in the register or a reviewed `exclusion` statement excludes
anything.

## B. Findings against the engine and the modelling guide

### B1. `required_property` is read by CONNECTIVITY only, and `check` will not tell you

**Probe G2.** `required_property` on a NUMERIC BOUNDEDNESS indicator is not read.
BOUNDEDNESS fires normally with the gate property absent. `model_describe`
reports it: `field: required_property, reason: axiom_not_declared, read_by:
["CONNECTIVITY"]`. `check` reports nothing.

The prior attempt proposed this field as the mechanism for machine-state gating
-- feed `state_running` and let planned stops decline `precondition_unmet`. It
does not work, and the gap is not small: cycle time, throughput and every balance
on a discrete line are meaningless during a changeover.

**What this bridge does instead**: applies the gate at feed time, withholding
samples taken outside the declared state. What that costs is visibility -- the
engine sees a shorter series rather than a gated one, and cannot report that a
gate fired. The count of withheld samples is in the attestation because nothing
else can say it.

### B2. `expect_variation` means *never moved at all*, not *has stopped moving*

> **Closed 2026-09-03.** MODELING.md now says it, and says the remedy
> this finding did not have: **the indicator's `window:` reaches this arm.** The
> same fifty samples, thirty varied then twenty flat, fire at `10m` and `15m`,
> stay quiet at `30m` and `1h`, and decline `insufficient_samples` at `5m`. So
> the window is a lever with a floor under it, and it is paired with the
> collection cadence. Pinned by `test_a_freeze_is_found_inside_its_window.py`,
> 15 tests, because a behaviour in a document with nothing running against it is
> the second copy that drifts.

**Probe S5.** Fifty samples, the last k of them flat:

| k | 5 | 10 | 20 | 30 | 40 | 45 | 49 | 50 |
|---|---|---|---|---|---|---|---|---|
| fires | no | no | no | no | no | no | **no** | **yes** |

MODELING.md: *a reading that never moves is a dead probe rather than a very
steady system.* A plant reads that as *tell me when a sensor freezes*. It will
not, until every varying sample has aged out of the fed history.

Also a fault-injection trap: flattening the tail of a corpus injects nothing, and
the leg passes for the wrong reason. Rule 4 says measure the excuse boundary
first; this is a boundary nothing in either document suggests is there.

### B3. CONSERVATION's threshold is relative, and the guide's example implies counters are fine

> **Closed 2026-09-03.** MODELING.md now states that the deficit is
> judged as a proportion of the input, and says to difference a counter that
> only climbs and balance the per-interval rate — which is what this package
> does. Flagged there as a separate concern from the naming point it sits
> beside, so it is not read as more advice about `flow:`.

**Probe K7.** The deficit that fires is a fraction of the input, identical at
both scales tried: quiet at 5 %, fires at 8 %, at input 100 and at input 8800
alike.

MODELING.md's worked example is `bytes_in` against `bytes_out`. That reads as an
endorsement of cumulative counters, and it is fine for a gauge that resets. On a
lifetime counter the threshold becomes a fraction of the lifetime total: a real
loss of forty parts against nine thousand is 0.45 %, invisible, and it gets
quieter every shift the line runs.

**What this bridge does**: derives `<tag>_per_interval` as the first difference
and balances that, naming every derived indicator in the manifest. It is the
bridge's job -- but nothing in either document points at it, and the natural
first implementation is silently inert.

### B4. The reversal tolerance is a count inside a window, and only one entry says so

> **Closed 2026-09-03.** Generalised in place under
> `insufficient_samples`: every count the engine keeps inside a window behaves
> this way, tolerances included. The measured numbers stayed out — the guide
> states no engine behaviour, and a reader takes them at C3.

**Probes M1, M3, M4.** The same engine behaviour, with the tolerance at its
default of 3:

| where the reversals sit | apparent tolerance |
|---|---|
| packed at the end, 50-sample corpus | **3** |
| spread every 3rd sample, 12-sample corpus | 3 |
| spread every 3rd sample, 30-sample corpus | 6 |
| spread every 3rd sample, 60-sample corpus | 16 |

Only the first is the tolerance. The rest is the window (about fifteen minutes at
60 s cadence) discarding reversals before they are counted.

The `insufficient_samples` entry states this trap exactly -- *a floor is a
count taken inside a window, so a corpus can hold many times the floor and still
never present it.* It is stated for one reason, and it is true of every
count-based tolerance in the format.

This probe got it wrong twice before getting it right: first by climbing a ladder
fast enough to trip the **rate** arm and reading that finding as the reversal
arm's floor, then by spreading the reversals outside the window. One axiom, two
arms, one `axiom:` field in the finding.

### B5. `no_threshold` is not reachable through RESPONSIVENESS, and the cell counts as covered

> **Filed upstream and fixed in source, 2026-09-03.** The threshold test is
> hoisted out of `_check_latency_threshold` into `check`, where a
> `not_evaluated` record survives the caller's `extend`, and the two truthiness
> threshold guards became `is not None` so a declared `critical: 0` is compared.
> Eleven tests. **Released in 0.1.11, 2026-09-04.** Everything below remains
> true of released 0.1.10 -- the version this exam measured, and this package's
> range floor -- and is false from 0.1.11 on.

**Probe X1.** A `role: latency` indicator declaring RESPONSIVENESS with no
`critical:`, fed a latency of ten million:

- findings: none
- declines: none
- `checked.invariants`: **1**

BOUNDEDNESS with no thresholds does decline `no_threshold`. RESPONSIVENESS holds
silently, and the denominator counts it as attempted. That is the shape the
decline vocabulary
warns about under `wrong_indicator_type` -- *silence that looks like health* --
arriving through a different door.

**Probe X2**, on the same theme: of the twelve reasons, **ten** are reachable
from a model a bridge could generate. `not_applicable` and `checker_error` are
engine-side, which the document says. Worth measuring, because that section's
claim
is that the vocabulary is a requirements document, and a requirements document
you can only satisfy five-sixths of is worth knowing about in advance.

### B6. The MONOTONICITY rate arm answers from a default rather than declining

> **Ruled and fixed in source, 2026-09-03.** The operator ruled the default
> unintended; the fix makes the arm decline `no_threshold` when no rate is
> declared, with the reversal arm beside it still running. Permitted in a patch
> by COMPATIBILITY.md. **Everything below remains true of released 0.1.10.**
>
> **It broke two consumers, and neither break was visible to the engine's 2,118
> green tests.** `bmc-sensor-audit --strict` goes 0 to 1 on every healthy BMC
> with a counter, because `no_threshold` is in none of its five reason sets
> (and it blocks the engine's next release). *This package* went 0 to **2** on its own
> clean corpus, because `no_threshold` read as a model defect and this package
> writes the model -- fixed here by a `declared_gap` class: a gap the manifest
> already names, which the engine is agreeing with rather than reporting.
>
> That is the finding behind the finding. A decline-vocabulary change is the
> class that reaches downstream, and the only thing that saw either break was
> running the consumers.

**Probes R1, R2.** With nothing declared, the rate arm fires at **0.1/s**
(`warning`) and **0.5/s** (`critical`). A declared `rate_warning` / `rate_critical`
displaces the default cleanly.

Every PLC heartbeat crosses this. Every fast production counter crosses it. The
finding is `monotonicity_rate`, on an entity whose model never asked the
question, from a number nobody in the plant chose.

It is the one arm in the format that behaves this way: the reversal tolerance is
declared, thresholds are declared, `agrees_with` is declared, and MODELING.md is
emphatic that the engine must not decide a domain question. Whether the default
is intended is a question for the author. Either way it is not excludable --
declaring MONOTONICITY gets both arms -- so a bridge either declares a rate with
a basis or ships an assertion it did not make. This package does the former and
records the latter in the manifest for every counter without one.

### B7. A hard stop worth having does not exist at the range floor

`check().dropped_declarations` was `[Unreleased]` in the engine's CHANGELOG when
this was written; it **shipped in 0.1.11, 2026-09-04**. Released 0.1.10 still does
not have it, and 0.1.10 is this package's range floor. A bridge that builds its
*did the engine understand my model* hard stop on that leg has a hard stop that
silently does not exist at the floor it advertises -- which
`battery/probe_pin.py` exercises alongside every other release the range admits.

`model_describe().model.unread_fields` carries the same fact with
`reason: unknown_value` on **both**, which is where this package reads it.

Found by C8's floor exercise. An API inventory would not have found it, because
the API is present -- on the wrong verb.

---

## C. Reported previously, and withdrawn on measurement

The prior attempt at this bridge left two findings to be filed upstream. Both
were re-measured before filing. **Neither survived.**

### C1. Withdrawn: BRIDGES.md and the engine disagreed on the decline count

As reported:

> BRIDGES.md as served listed 9 decline reasons and claimed generation from the
> engine; the engine at the same time had 12.

**Not reproduced.** Counting `NotEvaluatedReason` members in
`arbiter_engine/types.py` and the stated figure in `BRIDGES.md`, at every commit
on `master` where both exist:

| commit | date | engine | BRIDGES |
|---|---|---|---|
| `57e976d` | 2026-08-31 | 9 | 9 |
| `5e1fee1` (Release 0.1.9) | 2026-08-31 | 9 | 9 |
| `a397dbd` | 2026-09-02 | **12** | **12** |
| `3f6a76a` (Release 0.1.10) | 2026-09-03 | 12 | 12 |
| `5cb6d41` | 2026-09-03 | 12 | 12 |
| `d292b22` (remote head) | 2026-09-03 | 12 | 12 |

The three reasons and the table update landed in **one commit**, `a397dbd`. There
is no window in which the repository was inconsistent, so there is nothing to
report.

**What actually happened** is worth keeping, because it is a methodological trap
rather than an engine defect: the reader read the document at one time and
installed the engine at another, across a release boundary, and attributed the
difference between their two snapshots to the document. The document's own
warning -- *second copies drift* -- made that story fit, which is exactly what
makes it dangerous. A finding of the form *these two disagree* needs both halves
pinned to the same commit before it is a finding.

Filing it as written would have sent the author looking for a drift that did not
happen, in the one place the document had gone to trouble to prevent it.

### C2. Withdrawn: CONSERVATION reads a global 300 s window

As reported:

> CONSERVATION ignores the indicator's `window:` and reads a global 300 s window
> that the supported `EngineSession` surface cannot set. A station whose parts
> vanish over an hour, evenly, will be judged over the last five minutes only.

**Half true, and the consequential half is not.** Probes K5 and K6: ten samples
spread over six days, with `window:` declared `5m`, `1h` and `30d`, fire
identically; a deficit is seen across every span tried, up to six days.

The first clause holds -- the indicator's `window:` does not reach this checker,
which is why all three declarations give one answer and why a respected `5m`
would have left a single sample inside it. The second does not: there is no
five-minute horizon hiding an older deficit.

Right observation, wrong consequence, and the consequence is the part somebody
would act on. Not filed.

### The pattern in both

Two findings, both drafted from a real observation, both wrong in the half that
would have been acted on. The observation was never the weak part; the inference
from it was. Neither would have survived the run that this package's own C3 and
C8 probes make routine -- which is an argument for the method rather than against
it, and the reason both are here rather than quietly dropped.

### A9. A citation by section NUMBER is a dependency nothing type-checks

Not a finding against the method — a finding against this bridge, produced by
following it, and general enough to be worth stating.

This package cited `BRIDGES` by section number in **twenty-five** places across
`src/`, `tests/`, `battery/`, `pyproject.toml`, `README.md` and this file.
Closing A6 inserted a new section, and every citation at or above it became a
pointer to a different section than the one it meant. **All 146 tests stayed
green.** Nothing on either side can fail on it: a section number is prose in the
guide and prose in the comment, and no tool holds both.

**The instance fix was itself incomplete, and that is the sharper half.** The
first repair renumbered by matching `BRIDGES Sec. N` — and the citations are not
spelled consistently. Eleven sites written as bare `Sec. N`, `Section N of
BRIDGES`, or a number inside a sentence survived it, still pointing at the wrong
section, for a full day of work across two more closures. The sweep that found
them was an enumeration by eye, not a pattern: **a reference in prose has no
canonical form, so nothing that reads it as a pattern will find all of it.**

The same window falsified two prose claims outright — a class comment asserting
*BRIDGES says to treat this reason as a modelling error unconditionally*, and
another asserting the guide *gives findings none*. Both were true when written
and false within the day, and neither would have been noticed by anything.

**Fixed by citing titles.** *The review gate*, *the verification battery*, *the
exit contract* — they survive reordering, and they read better at the call site
than an ordinal a reader has to go and resolve. The one place a number is still
written is the sentence above describing what happened, which is history rather
than a pointer.

## E. Disposition

Filed 2026-09-03 in the engine repository's own tracker, since the engine is
not somebody else's. **Keyed by finding rather than by ticket**: the ticket
numbers are internal and a reader here cannot resolve them, so the column that
named them is gone and the finding it covers is the row.

Two of these were still open when this table was written. Both have since
closed, and the rows say what closed them rather than naming ticket numbers a
reader here cannot resolve:

| Finding | Disposition |
|---|---|
| B5 | engine fix, **released in 0.1.11**, 2026-09-04 |
| A6 | guide: name the read surface — **done** |
| A2 | guide: `missing_entity_type` is two-sided — **done** |
| A3 | guide: findings need floors too — **done** |
| A4, A5, A7, B4 | four smaller guide edits — **done** |
| B2, B3 | MODELING.md expectations — **done** |
| B6 | decision: **ruled**, the default is not intended |
| B6 | engine fix, **released in 0.1.11**, 2026-09-04, once the consumer below was ready |
| A9 | this bridge cites the guide by ordinal |
| -- | the consumer must classify `no_threshold` first — **done**: the feeder moved out in the 0.3.0 split, so it ships in `presence-audit` 0.1.2 |
| -- | `allow_reset` / `reset_tolerance` measured — **done** |

A1 was retired on measurement and is not filed. A8 is a note about a trap rather
than a defect and is not filed. C1 and C2 are the withdrawals.

**Nothing here implicates a shipped bridge.** `bmc-sensor-audit` declares no
CONNECTIVITY, no HOMEOSTASIS, and feeds no counter into CONSERVATION;
`fleet-sensor-baseline` does not touch the engine. That is also the reason these
gaps survived two worked examples: the pair exercises a narrow slice, which is
the limit the guide already states about them and which this exam measured.

### A10. `allow_reset` is routing, not excusing — and it settles the reset question

Measured (probes A1-A5) rather than argued. With `allow_reset: true` a drop to
near zero counts against the RESET tolerance and fires at three; with it false
the same drop counts against the REVERSAL tolerance and fires at three. The two
are mutually exclusive: a drop lands in one counter or the other, never both. A
declared `reset_tolerance` is the firing count exactly, and the arm carries the
same roughly-fifteen-sample window the reversal arm does.

MODELING.md is accurate — it says `allow_reset` excuses a drop *individually*
and that `reset_tolerance` counts them separately, and both hold. What the
measurement adds is that *excusing* is **routing**, and a reader who takes it as
*ignoring* will expect `allow_reset: false` to fire on the first drop. It fires
on the third.

**The consequence is bigger than the clarification.** Shift resets are hours
apart and the window is minutes, so two scheduled resets can never fall inside
one window — no declared tolerance distinguishes a scheduled reset from an
unscheduled one, because the arm never sees two at once. The engine has no arm
that answers it. That is the second question in this exam whose answer is *the
bridge does it at feed time* (the first was machine state), and both times the
engine was honest about not answering rather than answering wrongly.

## D. What survived

Recorded because a findings list with no other side is a complaint.

- **The exit contract.** Adopted verbatim, including *2 beats 1* and *compose as
  the maximum*. Nothing in it needed changing, and the discipline of deciding
  every floor at design time caught two arguments that would otherwise have been
  had while a run was failing.
- **The review gate.** *A fixture passes only by disclosing itself on its face*
  is a one-line rule that removed a whole category of decision. The
  same-package-emits-and-refuses shape is genuinely better evidence than a
  description of a boundary.
- **Model and manifest as a pair.** The manifest is where every one of the
  measurements above ended up being recorded. Without it there is nowhere to put
  *this counter's rate arm is running on an engine default* except a comment.
- **The decline vocabulary as a requirements document.** It works. Ten of the
  twelve entries turned into either a declaration kind or a reported class, and
  reading the whole list before designing anything was the single most useful
  instruction in the document.
- **C1's dependency rule.** Stage 1 here has no dependencies at all, asserted by
  parsing rather than grepping. It made the OPC UA rung cheap to add, because
  presence logic was already independent of everything.
- **The ship leg.** Green, and it is the leg that would have been skipped.
