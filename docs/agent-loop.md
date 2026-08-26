# The agent loop, and why it stops

An agent that redesigns a garment until the user is happy does not terminate
on its own. Left to itself it will keep producing plausible revisions
forever, because "good enough" is not a property it can evaluate.

Termination here is **structural**, not a retry budget.

## The loop

```
photo
  ↓
per-part retrieval          →  PROPOSED, quarantined
  ↓
construction                →  parts → graph → pattern
  ↓
3D                          →  shown beside the source frame
  ↓
a named human approves      →  one structural claim at a time
  ↓
sewing-method search        →  unreachable before this point
  ↓
"loosen 30 to 35"           →  a stable address, not a description
  ↓
re-draft
  ↓
back to 3D
```

## What makes it finite

Every revision writes to addresses in the store. There are four outcomes, and
only one of them continues the loop:

| what the revision does | store state | loop |
|---|---|---|
| lands at a new address | a new claim | continues — **but addresses are finite** |
| agrees with what is there | no change | **fixed point: converged** |
| contradicts what is there | **CONTESTED** | **terminal.** Neither is chosen; a person is asked |
| answers differ by ingest order | `UNKNOWN_ORDER_DEPENDENT` | **stops** |
| reopens an adopted address | needs re-adoption | costs a **human signature** — a finite resource |

So the loop ends when the set of adopted addresses stops changing. It cannot
run forever because the address space of a composition is finite, contradiction
is terminal rather than a retry, and reopening settled ground requires a person
to sign again.

**This is a claim, not a theorem.** It has not been proved. `convergence.py`
carries the stagnation counter and the escalation, and the falsifiers for it
are written; the general argument above is the design intent that those
falsifiers are meant to hold to account.

## Stagnation is not the same as progress

Three rounds each rejecting a *different* claim is a loop making progress.
Three rounds rejecting the *same* claim is a loop stuck, and it escalates to
a human as `ESCALATE_HUMAN`.

The falsifier for this is deliberately blunt: remove the check that looks at
*which* claim was rejected, and the escalation stops firing. That mutation is
in the sweep and it goes red.

## Why the numbering has to be stable

The user's instruction is an address: *loosen 30 to 35*. If the numbering
shifts when the pattern is revised, then 35 means something different next
round and the loop is chasing a target it moved itself. That is not slow
convergence; it is a loop with no fixed point.

So numbers are derived from the address rather than allocated by walking a
list, and the base registry is append-only. See
[architecture.md](architecture.md#two-address-spaces).

A span whose two ends sit on different edges is refused rather than
interpreted — nobody can say what "loosen it" means across the gap between
two edges.

## What the loop is not allowed to do

- **Decide the back of a garment.** A front photo does not contain the back.
  Candidates are produced, quarantined as `PROPOSED`, and a named person
  chooses. Adoption records who.
- **Reach the sewing corpus before approval.** The gate is the argument
  surface: `methods_for(approval_id, corpus)` has no parameter into which an
  unapproved shape could be passed.
- **Keep an approval after the shape moves.** The approval carries a digest.
  A 0.1 cm zone adjustment recomposes to a different digest and the old
  approval stops opening the search — `UNKNOWN_APPROVAL_STALE`.
- **Silently build the part it can draft and skip the rest.** A retrieved
  family with no procedure refuses the *whole* construction, naming every
  offender. A garment quietly missing its cape would collect approval for a
  different garment.
