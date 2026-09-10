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

## Releasing

By hand, and in this order:

1. Bump the version literal in the package; `pyproject.toml` reads it from there.
2. Add the `CHANGELOG.md` entry. A test holds the declared version to an entry,
   so a release with nothing to say about itself will not pass.
3. Run the battery.
4. **Push the tag, then upload the wheel.** In that order. Done the other way
   round there is a window where a public artifact exists and nothing on the
   remote binds it to a commit, and `README.md` claims a tag that no fresh clone
   can resolve. An outside review of 0.1.7 landed inside that window and reported
   the missing tag as a defect; the tag was pushed minutes later, so the report
   was right about the window and wrong by the time it was read. The window is
   the problem, not the report.
5. Confirm from the simple index rather than the checkout — the JSON API and the
   index disagree after an upload, in both directions, and which one is ahead is
   not predictable.

## What this project is

An exam of a method as much as a tool, and **the engine it bridges to shares an
author with it**, so `FINDINGS.md` is a self-exam rather than the independent
adoption that document asks for. A finding that contradicts something written
here is welcome and is the point; several already have.
