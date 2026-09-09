# Contributing

The most useful thing you can send is **a register and a walk where Stage 1 said
a tag was reading and it was not**, or where the gate accepted a declaration it
should have refused. Those are the two failures this package exists to prevent,
and a real line will find shapes a synthetic corpus never will.

The second-most useful is a status word, a node layout or a server behaviour the
reader mishandles quietly. `battery/probe_status_words.py` grades every code the
client library defines, and that population has already been wrong once — every
compound `Good…` word from a real server was graded unusable, because the grader
had been matched against the corpus spelling rather than the one OPC UA uses.

## Before you commit: enable the hooks

```bash
git config core.hooksPath .githooks     # once, per clone
```

**This is per-clone and off by default**, so a fresh clone has no hooks until
somebody remembers. They run the hygiene sweep over what you staged and check the
commit message with the same rules — because **a commit message is the one
published surface that can never be corrected**. CI repeats both, but only after
the message is already permanent.

Two things the hooks will refuse: staging part of a file while the rest of it is
edited (the commit would record something you have not looked at), and a message
or a file carrying something that should not be published.

Subjects are 72 characters or fewer. **Imperative mood is the convention and is
deliberately not enforced** — the clearest violation this project produced began
with the word `declare`, which any first-word check reads as a perfect
imperative, and a hook that refuses honest messages is one people learn to pass
`--no-verify`, which turns off the leak rules too.

## Running it

`README.md`'s quick start is the whole thing, and a test runs those commands out
of the page, so they work as printed. Beyond that:

```bash
python3 battery/run_battery.py          # every leg; CI runs this on each push
python3 battery/run_battery.py --only live --only capture
```

A leg that could not run reports `2` and says so by name — it is never skipped.
`--only` refuses a leg name that does not exist rather than running nothing, and
the result file records the selection, so a partial run cannot be mistaken for a
full one.

## What this project is

An exam of a method as much as a tool, and **the engine it bridges to shares an
author with it**, so `FINDINGS.md` is a self-exam rather than the independent
adoption that document asks for. A finding that contradicts something written
here is welcome and is the point; several already have.
