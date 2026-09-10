# Changelog

What changed between releases, and why. Newest first.

This file starts at 0.1.8 and back-fills 0.1.6 and 0.1.7, because the answers to
two reviews lived only in commit messages and code comments -- the two least
findable places -- and a user of 0.1.6 reading the repository had nowhere to
learn that the meaning of `pinned` in a walk had changed from *a flag was given*
to *a certificate was compared*.

Entries say what a reader has to DO, then what was wrong. A release that only
narrows an internal rule still gets a line, because somebody's declaration file
is the thing it narrows.

## 0.1.8 -- 2026-09-10

Answers the static re-verification of 0.1.7. Eleven items were raised; one was
refuted on measurement and the rest held, two of them regressions that 0.1.7
introduced. Running the fixes found three more that no review had named: the two
marked below, and a guard that could not see its own subject.

### Breaking

Nothing. Two rules were NARROWED, so files 0.1.7 refused may now be accepted:

* **Two different `conservation` balances on one asset are legal again.** 0.1.7
  refused any `(asset, tag, kind)` declared twice, and `conservation` is
  asset-scoped with `tag: null` -- so two balances on one station collided, and
  the refusal told you the generator reads the first and ignores the rest. The
  generator ITERATES conservation statements and emits a derived pair for each,
  so that sentence was false about the one kind it was refusing. Two statements
  of an iterated kind now collide only when they are the SAME statement: the
  same balance over the same tags, the same exclusion for the same reason.
* **`open_when` accepts integer state codes**, not only strings. A PLC serving
  its running flag as Int16 or Byte `0/1` had no legal declaration at all: no
  `open_when` hard stopped as undecidable, `[1]` was refused as malformed, and
  `["1"]` was accepted and then withheld every sample, because `1 in ["1"]` is
  false. Three shapes, and the only one the gate called wrong was the one that
  would have worked.

### Fixed

* **`--membership-cache` beside `--server-cert-pin-sha256` dialled an unchecked
  peer.** 0.1.7 gave the walk a real certificate check and stopped there. The
  membership pass took the security string, the credentials and the namespace,
  and not the pin -- and when it answers `unchanged` the verb exits 0 writing no
  walk, so the only artifact that records `pinned` was never written. The pin now
  applies to both passes, the cache records what it was taken over, and a cache
  taken over a pinned channel is not reused over an unpinned one.
* **A malformed pin blamed the server.** The flag was tested for truthiness only,
  and the comparison stripped `:` and spaces -- so `sha256:<hex>`, the shape this
  package's own `digest()` prints, became a 70-character string that could never
  match, and the run was refused with a message saying the server had presented
  the wrong certificate. A person reading that goes and looks at the plant. The
  pin is now validated before anything is dialled, and `openssl`-style colons and
  an optional `sha256:` prefix are accepted.
* **A gate whose declared values cannot match what the server serves now stops**
  rather than withholding every sample and letting the engine decline
  `missing_property` -- a decline this package classes as its own defect, so it
  was reporting itself against the wrong subject. Judged over the whole walk, not
  per sample: one reading of an odd type is not a declaration that cannot apply,
  and a station that really is stopped must still withhold quietly.
* **`regression` calls `validate_walk`.** It did not, and the stated reason was
  that a receiver-side shape check would refuse the declared-rename leg's
  prefixed walk. Measured: that walk passes with no problems, as do all fifteen
  corpus walks. The decision cost nothing and its reason was false, which is the
  worse half -- a reader who believed it would not have tried. A walk that loads
  and is not a walk is now refused instead of compared.
* **A walk records `polls`.** Samples are keyed on the first node's timestamp, so
  a server whose values do not advance yields exactly one sample however long
  `--budget` runs -- indistinguishable, in the artifact, from a server asked
  once. The engine declines `insufficient_samples` either way.
* **(Found here, not in the review.) The rung-3 server was not serving state
  words at all.** A string seed fell
  back to `0.0` when the node was created, and an OPC UA node's datatype is fixed
  at creation -- so every write of a state word was refused for the whole run,
  `asyncua` logged it and carried on, and the node served its initial `0.0`
  forever. Two nodes were affected. The `live` leg could not fail on this and
  was green throughout; it now checks that a value comes back as the type it
  went out as, derived from the corpus rather than named.
* Two documents named `battery/engine_floors.json` after it moved into the
  package in 0.1.7. Every repository path either document names is now held by a
  test -- the existing guard parsed only `.py` tokens on runnable lines, so
  neither stale line was reachable by it.
* `leg_tool` reported a missing `[vertical]` extra as an entry that could not
  construct, naming neither the extra nor a reason. It still goes red, because it
  could not ask its question; it now says which install would let it.
* The guard holding the README's leg table to the legs that run matched
  `[a-z-]+`, so it could not see the first leg name containing an underscore --
  and reported `pin_channel` missing from a table that carried it. A rule is only
  as wide as the surfaces it is run against.
* `leg_pin` now notices when the installed version of a pinned distribution is
  not one the committed evidence swept. By measurement, not by date: an age bound
  would redden because a week passed.
* **(Found here, not in the review.) The `fault` leg was flaky on a timescale
  shorter than the battery's own run.** `parts_vanish` stops being found once the corpus passes about two
  minutes -- measured by ageing the corpus and sweeping all fourteen classes, and
  it is not monotonic: lost at 120 s and 180 s, found at 240 s, gone from 300 s.
  Every leg before `fault` costs wall-clock, so the battery was relying on being
  fast enough, and when it was not the red leg read as a detection regression.
  The leg now builds its own corpus immediately before judging, reports the age
  it judged at, and refuses rather than reporting a miss if the rebuild did not
  take. The `corpus` leg's 900 s is the ENGINE's widest window, not the narrowest
  thing any leg needs, and it now says so. Recorded as FINDINGS A4 extended.

### Added

* **`pin_channel` battery leg, and `opcua_surface.py serve --certificate`.** The
  pin was the one protection this package offered that nothing had exercised end
  to end: five tests constructed the checker and called it directly, one grepped
  the walk function for the hook's name, and every one of those passes if the
  client library never calls the hook. The rung-3 surface was anonymous on
  loopback, where a pin is refused by policy, so there was nowhere to find out.
  It now serves Basic256Sha256/SignAndEncrypt with a self-signed certificate, and
  the leg runs `capture` against it twice: a matching digest must walk and record
  the certificate the server actually presented, and a wrong one must refuse
  naming both. **Measured: `asyncua` does call it.**
* `serve --repeat`, because two clients against one server outlive a single pass
  through the corpus.

### Not changed, and why

* The review reported `v0.1.7` as absent from the remote while the wheel was
  public. The tag is on the remote at the reviewed commit; the window the review
  saw had closed before it was read. Releases here are run by hand, so the
  ordering advice belongs in the runbook rather than in a workflow.
* The review asked for `A10` and `A11` to move out of FINDINGS section B. They
  are findings against the ENGINE, which is what section B is; the `A` in the
  label is a citation handle, not a claim about placement. The reason was already
  written above them and the reviewer read it, jumped to the heading, and
  reported the placement anyway -- so the reason is now repeated at each heading,
  where a citation lands.

## 0.1.7 -- 2026-09-10

Answers the static verification of 0.1.6: eleven findings, five of them severe.
**Breaking for declaration files.**

* `gate_on` takes `open_when`, the state WORDS that mean the check applies. The
  gate read `bool(value)`, and every non-empty word a PLC produces is true in
  Python -- so a station reporting `Stopped` opened the gate and the run judged a
  takt the station was not running to.
* A statement declared twice is refused, across every accepted file. (Narrowed in
  0.1.8 for the two kinds the generator iterates.)
* `--server-cert-pin-sha256` is compared against the server's certificate. It had
  existed since 0.1.0, was recorded in the walk as `pinned: true`, and was passed
  nowhere -- so **the meaning of that field changed in 0.1.7**, from *a flag was
  given* to *a certificate was compared*.
* `engine_floors.json` moved into the package, so an installed wheel carries it.
* Node ids of all four OPC UA identifier types; `--namespace` is honoured by the
  membership pass; an unparseable id is a refusal rather than *absent*.
* A server that stamps only `ServerTimestamp` no longer yields an empty walk.
* `regression` reads through the format loader, so an unknown major is refused.
* A register where no asset carries a surviving tag is refused.

## 0.1.6 -- 2026-09-10

* `reset` declaration kind: whether a counter is zeroed, declared rather than
  inferred. `allow_reset` on a `rate` statement is refused, naming where it moved.
* RESPONSIVENESS fault injection; fourteen fault classes.
* The tool surface is closed over the CLI: every verb is offered or withheld with
  a reason, and nothing is both.

## 0.1.0 -- 0.1.5

Initial public releases: the two stages, nine verbs, the declaration channel and
its review gate, the evidence ladder, and the verification battery. See
[FINDINGS.md](FINDINGS.md) for what the exam produced, and `git log` for the
sequence.
