# Pre-registration — the engine suspends and asks for language

**Registered 2026-08-16, before the mechanism is written or measured.**

## What is proposed, and what is deliberately not

MCP puts the model in charge: it decides which of the 99 doors to call,
and the ones it does not know about never run. Measured today — the IDE
knows 60 doors and its answering path uses three, so 17 organs and ~6,000
lines are outside every question anyone asks.

The inversion is right. The implementation is not "the engine calls a
model API": that would put a non-deterministic call inside the
deterministic core, and the same question could return different answers.
Determinism is the only property this engine sells that an LLM cannot,
and it is not being traded for reach.

So the engine **suspends**:

```
ask(query)               → NEEDS_LANGUAGE + a typed request + a token
   host fulfils it       (MCP sampling, a provider API, or a person typing)
resume(token, text)      → the engine continues, deterministically
```

Given the same fulfilment, the same answer. The model is outside, and what
it said is data the engine received — recorded, attributable, and
replayable. `ask_back.py` already has this exact shape for humans; this
adds one more kind of receiver.

## Frozen pass lines

- **S1 — no fabrication.** WRONG on the frozen 50-item commonsense bank
  (`tools/commonsense_bank_2026-08-14.json`) must stay at **0**. The
  post-repair baseline is 9 correct / 41 typed refusal / 0 wrong.
  **This is the line that can actually fail, and it is the whole point:**
  an inversion that converts refusals into answers by asking a model is
  worth nothing if some of those answers are invented. A refusal that
  becomes a wrong answer is strictly worse than the refusal.
- **S2 — determinism holds.** The same query with the same fulfilment
  produces a byte-identical verdict on three runs. If the model's text is
  fixed, the engine's answer is fixed.
- **S3 — the model never writes.** Nothing the model returns enters the
  store, the census, or any facet. It may only re-form a QUERY. Checked by
  comparing store facet counts before and after.
- **S4 — refusals stay typed.** A query the engine could not answer and
  the model could not re-form still returns its original typed refusal,
  not a new one invented for the occasion.

## Quantities to be measured (not predicted)

1. Of the bank's 41 typed refusals, how many become ANSWER/SEEDED.
2. How many become WRONG (gated by S1 at zero).
3. How many stay refused.
4. The re-formed queries the model produced, listed verbatim.

## Stop conditions

- **S1 fails** → the inversion is an entry point for fabrication. Stop;
  do not tune the prompt to reduce it. A mechanism that needs a careful
  prompt to avoid inventing is a mechanism that will invent.
- **S3 fails** → the model has written to the store. Stop and ledger every
  facet involved, the same way the 103,599-claim repair was ledgered.
- **S2 fails** → the engine has become non-deterministic. Stop; the
  suspension is leaking state.

## Recorded before measuring

The expected gain is small. The 41 refusals are mostly
`UNKNOWN_NO_EVIDENCE` on commonsense — 「氷は冷たい」 is absent because
nobody wrote it, and no re-phrasing reaches a sentence that does not
exist. Re-forming a query helps when the store HAS the fact under another
name, which is the 表記ゆれ case, not the missing-knowledge case.

Written down so that a small number is read as the honest outcome rather
than as a failure of the mechanism, and so that a large number is
inspected for fabrication before it is celebrated.

## Not in scope

The model is not given the store, the doors, or any ability to act. It is
handed one string and asked for another. Everything else this session
built — the chain, the progress witness, the procedure replay — stays on
the engine's side, where the loop belongs. The measured reason is on
record: a 27B model given the loop produced forty paragraphs and no tool
call.
