<div align="center">
  <h1>🛡️ Verantyx</h1>
  <p><b>An engine that refuses to guess — and a macOS IDE built around it</b></p>
  <p>
    <a href="#what-this-is">What it is</a> ·
    <a href="#the-guarantee">The guarantee</a> ·
    <a href="#run-it">Run it</a> ·
    <a href="#repository-map">Map</a> ·
    <a href="#where-to-start-contributing">Contribute</a>
  </p>
</div>

---

## What this is

**Vera-a** is a deterministic knowledge engine. You pour documents in, you ask
it things, and it answers **only from what it holds** — or says, in a typed
verdict, that it does not know. No embeddings, no sampling, no network. The
same question returns the same answer, and the order you loaded the documents
in does not change it.

On top of that sits the **covenant guard**: a ledger of what you told an
assistant to do and not do, checked against every reply, with the promises
whose compliance is *dropping* named by number. It runs as Claude Code hooks in
0.04 s per check, or as a panel in the IDE.

Everything claimed here is backed by a pre-registered measurement in this
repository. You can re-run all of it in 45 seconds:

```bash
python3.11 engine/experiments/guard/verify_all.py
# forks 89/89 / 測定 50/50 — 全て緑
```

## The guarantee

These eight properties are re-run **on your machine, at the moment you ask**,
by `vera doctor`. If one fails, the command exits non-zero.

| | The guard | The standalone device |
|---|---|---|
| 1 | A covenant you registered catches a reply that breaks it | What you poured in gets answered, with its source |
| 2 | Nothing you did **not** register can ever block a reply | What was never poured in is **refused**, typed, with a reason |
| 3 | Deterministic; registration order cannot change a verdict | The same question survives every ingestion order |
| 4 | Retiring a covenant is an entry in the ledger, never a deletion | The answer is built only from words the store holds |

Row 2 is the one an embedding+LLM stack cannot promise: nearest-neighbour
search always returns *something*, and generation always mixes in outside
words. Here, absence is an answer.

### What it is honestly not

Named, measured, and deliberately **not** on the roadmap — see
[`engine/experiments/guard/PREREG5_FREEZE.md`](engine/experiments/guard/PREREG5_FREEZE.md):

* It does not read natural-language instructions reliably. Measured: of 20
  realistic instructions, 3 were read correctly, 13 produced nothing, 4 picked
  the wrong term. Anything a rule reads therefore lands in **quarantine** and
  can never block; only what a person registers is enforceable.
* It does not catch literal evasion (TODO → FIXME) unless the corpus already
  puts the two side by side.
* It does not generate prose. It returns the words it holds.
* Widening the rules does not fix any of this — measured three ways
  (645/661 negations outside a 39-word vocabulary; no frequency threshold
  separates content words from function words; a corpus buys inventory, not
  reading).

## Run it

```bash
python3.11 -m verantyx.cli --store ~/vera_store.json documents ~/your-docs/
```

```bash
python3.11 -m verantyx.cli --store ~/vera_store.json ask "交際費"
```

Ask for something that was never loaded and it answers
`UNKNOWN_NO_EVIDENCE` with a reason, instead of the nearest paragraph.

```bash
python3.11 -m verantyx.cli doctor          # prove the eight properties here, now
python3.11 -m verantyx.cli index search "約束 破棄"   # does this already exist?
```

The guard as Claude Code hooks: point `~/.claude/settings.json` at
[`engine/tools/guard/settings.snippet.json`](engine/tools/guard/settings.snippet.json),
then run `doctor` — it checks the wiring, not just the engine, because a guard
that fails open looks exactly like a quiet day.

## Repository map

```
engine/     Vera-a — the deterministic engine (Python). Everything above lives here.
  verantyx/            the package; mcp_server.py is the ONLY interface the IDE uses
  experiments/         pre-registrations and measurements (74 preregs, 37 results)
  tools/guard/         the Claude Code hooks
ide/        the macOS app (Swift) + packaging. Talks to the engine over MCP only.
  VerantyxIDE/Sources/Verantyx/Views/   screens, incl. CovenantGuardView
docs/       architecture and archives
attic/      old debug scripts, kept rather than deleted
```

**The seam is MCP.** The IDE calls 130 named doors by name and never imports
Python; the engine never imports Swift. If you are changing a screen you only
touch `ide/`; if you are changing what a door answers you only touch
`engine/verantyx/`. `capability_index` will tell you which door already does
what you are about to build.

## Where to start contributing

Read [`engine/CLAUDE.md`](engine/CLAUDE.md) first — it is short, and it names
the measured lines that a change must not cross (pre-register before measuring;
ties abstain; absence is not denial; nothing is deleted, only archived).

Then run the index before writing code:

```bash
python3.11 -m verantyx.cli index search "<what you are about to build>"
```

It exists because this repository is larger than any working memory — 67k
lines, 130 doors, 89 forks, 75 pre-registrations — and capabilities were
genuinely being built twice.

Issues tagged as good starting points are scoped so that "done" means *a
measurement passes*, not *the code looks right*.

## The other engines

The IDE also ships **Gatekeeper** (local small models convert code to an
intermediate form so a cloud model never sees proprietary semantics) and
**JGEN** (quantized GGUF inference on Metal/NEON, two-Mac layer split over
Thunderbolt). They work, and they are not what this project claims to be
different at — that space has strong, well-funded competitors. Vera-a is the
part with a property nobody else offers: **a typed refusal you can trust, and
a promise ledger that notices when a model drifts.** Judge the project on that.

## Licence

See [LICENSE](LICENSE).
