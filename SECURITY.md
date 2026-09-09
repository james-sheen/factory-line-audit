# Security

## Report privately

**Use GitHub's private vulnerability reporting** — the *Security* tab on this
repository, *Report a vulnerability*. That opens a channel visible only to the
maintainer.

**Do not open a public issue for anything in the list below.** The failure modes
here are ones where *the report itself is the disclosure*: an issue saying
*walking my line produced this* has, by being filed, published what runs on that
line.

If private reporting is unavailable to you, open a public issue saying only
**that** you have something to report and nothing about what it is.

## What counts as a security issue here

This package reads a live OPC UA server on a production line. Three consequences
shape the list.

**1. A walk is a description of a plant.** Node identifiers, tag names, values
and their timing together give away what machines are on the line, what they are
named, how fast they run and what they are making. That is commercially
sensitive whether or not anything in it is a secret.

- **Any path by which a walk, or a fragment of one, reaches a file, a log line,
  an error message or a traceback the caller did not ask for** is a security
  issue.
- **Any value from a real line appearing in this repository** is a security
  issue, including in an example or a test fixture. Every number in `examples/`
  is invented, and that is the rule rather than an accident.
- **A gap in `tools/hygiene_check.py`** — a rule that does not fire on a hazard
  it claims to cover — is a security issue even with nothing currently leaking.
  Its coverage is pattern-based, so it finds the shapes it knows and nothing
  else.

**2. It authenticates, and it negotiates a channel.** Credentials are supplied by
the caller and never stored.

- **Credentials appearing in output**, including in an endpoint URL echoed to a
  log or an exception, are a security issue.
- `capture` **refuses an unencrypted channel off loopback unless it is asked for
  by name**, refuses the withdrawn policies outright, and refuses flag
  combinations that cannot both be true. **If any of those refusals can be
  reached when it was not requested, that is a security issue** — the refusal is
  the feature.

**3. The walk records how it was taken, and something downstream refuses on that
record.** A certificate can decline a walk taken over an unprotected channel, and
it decides using the provenance this package writes into the walk.

- **A walk that records a stronger channel than it actually used is a security
  issue**, and a more serious one than a failed capture. It does not merely get
  something wrong; it defeats a refusal somewhere else, in a way that looks
  clean at both ends.

## What does not need private handling

Ordinary defects, wrong presence counts, parse failures, crashes on malformed
input, and refusals working as designed. **Also: a defect in a server's own OPC
UA implementation.** If this tool surfaces one, the flaw is the server's — report
it to that vendor, and by all means say the tool helped.

## What to expect

A single maintainer, no service-level commitment, and no bounty. You will get an
acknowledgement and an honest answer about whether and when it will be fixed —
including *not soon*, when that is true.

**The supported version is the latest release on PyPI**, and nothing older. A fix
lands on the default branch and ships in the next release; the reply will say
which.

**No version number appears in this file on purpose.** A sibling project's
security policy told reporters there was no released version to upgrade to — true
the day it was written, false from its first release onwards, and a security
policy is the worst place in a repository for a sentence that has quietly stopped
being true. A test enforces the absence.

## Scope

This repository only. It speaks OPC UA through `asyncua` and is not affiliated
with the OPC Foundation, with `asyncua`, or with any controller or machine
vendor. A vulnerability in a server, in a PLC, or in the client library belongs
to that project or vendor rather than here.
