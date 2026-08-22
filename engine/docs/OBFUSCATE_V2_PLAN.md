# Obfuscation v2 — planning document

This plan follows the long design debate summarized in
[docs/DESIGN.md](DESIGN.md#reversible-obfuscation-keyed-by-personal-state).
Its purpose is to separate what survived that debate from what didn't, and
to lay out only the part worth actually building.

**Ground rule carried over from that debate:** nothing in this plan may be
described in docs, README, or CLI help text as "unbreakable," "impossible
to analyze," or "cannot be reversed." Every claim must state which threat
tier it addresses (casual read / automated scraping-training / community
reverse engineer / dedicated RE team / nation-state) and which one it
explicitly does not. This is the same rule that stopped v1 from overselling
itself, and it stays in force for v2.

## 1. What already works and does not change

- `fingerprint_store()` → `derive_key()` → AES-256-GCM encryption of the
  identifier-rename mapping. Given proper key custody, this part is
  already resistant to essentially any adversary, including nation-state —
  because its strength comes from a certified, standard primitive
  (AES-256-GCM) and *your* private data, not from algorithm secrecy. This
  is not being touched by v2.
- AST-exact identifier renaming (`_Renamer`, `_CollectSpans`) — correctness
  fixes already shipped, stays as-is.

v2 is only about the layer above this: making the **renamed source code
itself** more expensive for a casual/community-level reader (human or LLM)
to make sense of, beyond "the names are now meaningless." That's a
different, weaker goal than key secrecy, and it needs its own honest
threat-tier label: **raises cost against casual/automated/community-level
static reading. Does not, and cannot, resist a dedicated reverse engineer
with a debugger and unlimited time** — per Barak et al. 2001, no fixed
program can be made to resist that class of attacker via obfuscation
alone.

## 2. Ideas from the debate that are being carried forward

### 2a. Fingerprint-selected transform variant ("diversified compilation")

Real, precedented technique (software diversity / N-version obfuscation).
Concretely: define a small, fixed menu of legitimate, semantics-preserving
transform choices — e.g. which of 3–4 dispatch-table layouts to use for a
generated VM (see 2b), how densely to insert dead/opaque-predicate
branches, which of several equivalent control-flow-flattening shapes to
apply. Use the **same store fingerprint that already derives the AES key**
to also deterministically pick a point in that small combinatorial space.

What this buys: two people's obfuscated output of the *same* source is not
byte-for-byte identical, so an attacker can't write one static
de-obfuscation script and run it against every distributed copy — they
have to re-derive the transform per copy. What this does **not** buy: it
does not make any single copy harder to defeat once someone is looking at
that specific copy. It raises the cost of *scaling* an attack across many
users, not the cost of attacking one user.

### 2b. Custom bytecode VM for a restricted function subset

Real, precedented technique (this is what VMProtect/Themida/Denuvo
actually do, not what the debate's later "self-generating executor"
proposals described). Translate a restricted subset of a function's AST
(no dynamic `eval`/`exec`, no unbounded recursion, no reflection) into a
small custom opcode set, interpreted by a per-user-generated dispatch
table (the specific opcode-to-handler mapping varies per the fingerprint
from 2a). A trace of this VM shows opcode dispatch, not the original
Python — genuinely more work to read than renamed-but-still-Python source.

Honest limit: this is still an ordinary program running on ordinary
hardware. Anyone willing to single-step the interpreter recovers the
original control flow; this has happened to every commercial VM-obfuscator
to date. It's in scope because it's a real, bounded cost increase for
casual/community analysis — not because it approaches "unbreakable."

### 2c. Split public/private distribution (structure vs. data)

This is already what `vera obfuscate` produces (`.obf` + `.obfmap`), just
formalized as its own step: the `.obf` file (renamed/VM'd structure, no
private data) is the only thing that's ever public; full reconstruction
requires the `.obfmap` plus either the original store or the exported
recovery key. No new mechanism needed — v2 just documents this split
explicitly as "public form" vs. "recoverable form" so it's a named concept
instead of an implementation detail.

### 2d. Call-history bookkeeping (anti-replay convenience, not a defense claim)

Recording previously-seen call values as store facets (already how
CrossStore works generally) so that a rebuilt/re-run instance doesn't
produce byte-identical diagnostic output to a prior run. This is a minor,
genuinely useful anti-fingerprinting convenience for whoever is comparing
two dumps side by side. It is **not** described as preventing analysis —
it only means "diff this log against that log" stops being a free win.

## 3. Ideas from the debate that are explicitly rejected, and why

| Proposal | Why it's out |
|---|---|
| Detect attacker/debugger and silently rebuild | Defeated by hypervisor-level, guest-invisible snapshotting (real technique, decades old). Also has a false-positive cost: legitimate users occasionally trip debugger heuristics too. Not worth the complexity for the protection it doesn't actually provide. |
| "Memory noise" / path-traversal-through-the-executor as a defense layer | A full register/memory trace defeats this regardless of how convoluted the path was to get there — the defeated state is still sitting in memory when execution stops. This is not a real barrier, just more steps before the same endpoint. |
| Model-weight fragmentation relying on "hard to see the whole picture" | Security-by-scattering fails the moment an attacker just concatenates the fragments back together — it's a packaging inconvenience, not a protection. |
| Self-generating, non-fixed executor bootstrapped from the obfuscated code itself | Once running, it's a concrete program in memory like any other — folds into 2b (ordinary VM obfuscation) with no additional protection beyond what 2b already claims. |
| "Absolutely unbreakable via the model's own structure" | Contradicts Barak et al. 2001 (general virtual-black-box obfuscation is provably impossible). Not implementable as stated; no version of this claim goes in docs or code comments. |

These stay rejected regardless of how they're rephrased later — the
underlying objections (snapshotting, trace-defeats-noise,
concatenation-defeats-scattering, the impossibility theorem) don't change
with rewording.

## 4. Phased implementation order

1. **2a (fingerprint-selected variant)** — smallest, most self-contained;
   extends `obfuscate.py`'s existing fingerprint→key path to also select a
   transform-space index. Ship with an `OBF_VARIANT_DETERMINISM` /
   `OBF_VARIANT_DIVERSITY` fork pair (same store → same variant every time;
   different store → provably different variant, mirroring the existing
   `OBF_KEY_DETERMINISM`/`OBF_KEY_UNIQUENESS` pattern).
2. **2b (restricted-subset VM)** — larger; needs an explicit
   "VM-eligible subset" checker that refuses (falls back to plain renaming)
   for code using `eval`/`exec`/reflection/unbounded recursion, so it never
   silently produces wrong behavior on code it can't safely translate.
3. **2c (naming/documentation only)** — no code, just makes the existing
   `.obf`/`.obfmap` split an explicitly named concept in `docs/OBFUSCATE.md`.
4. **2d (call-history bookkeeping)** — smallest, optional, lowest priority.

## 5. Documentation requirement

`docs/OBFUSCATE.md`'s "Honest limits" section gets a new v2 subsection
stating plainly: variant-selection and VM translation raise cost against
casual/automated/community-level reading; they do not resist a dedicated
reverse engineer, and the only nation-state-resistant component in the
whole feature remains the AES-256-GCM key-secrecy layer from v1, unchanged.

## 6. Reframed use cases (implemented)

Section 2a's mechanism (fingerprint → deterministic point in a small
transform space) turned out to be a poor fit for its original pitch
("harder to read") but a good fit for several other, more honest goals.
Status: **implemented and shipped**, see `verantyx/watermark.py`,
`verantyx/obfuscate.py` (`VariantSignature`, `variant_from_fingerprint`),
CLI `vera watermark register|identify`, forks in `watermark_forks.py`,
full writeup in [docs/WATERMARK.md](WATERMARK.md).

- **Software watermarking / leak attribution** — the actual thing built.
  `obfuscate_file()` now derives a `VariantSignature` from the store
  fingerprint (8 prefixes × 3 hex-lengths × 2 cases × 2 separators = 96
  points) and uses it for identifier naming. A registry maps
  `owner_id → signature_id` (never the raw fingerprint — that would leak
  AES-key material). `identify_candidates()` matches a suspect obfuscated
  file's detected variant against the registry and returns a **candidate
  list**, explicitly labeled as evidence, not proof, with the honest
  birthday-bound collision note (~10 owners before coincidental overlap
  is expected). Reframing win: this doesn't need to survive a skilled
  reader at all — it only needs to survive ordinary redistribution, which
  is a claim that's actually true, unlike the original "raises reading
  cost" pitch.
- **N-version self-check** — not yet implemented. Idea stands as future
  work: generate two variants of the same transform, run both, compare
  outputs, treat disagreement as a transform-pipeline bug signal. Natural
  fit with Vera's existing multi-frontier consensus philosophy, but no
  code was written for this in this pass — flagging it here rather than
  claiming it's done.
- **Canary/tenant build assignment** — not yet implemented. The same
  `variant_from_fingerprint()` primitive could deterministically assign a
  build variant per tenant without a separate flagging system. Left as a
  documented possibility, not built — it wasn't the concrete ask.
- **Normalized diff representation** — not yet implemented, contingent on
  the 2b VM/IR work landing first (needs an intermediate representation to
  normalize against). Documented as a follow-on, not started.

Only the first bullet (watermarking) was carried through to working code
in this pass, since it was the one with a genuinely solid value
proposition (see the "reframed use cases" discussion). The other three
remain real, undismissed ideas for later — not rejected like section 3,
just not yet built.

---

Step 1 (2a) is done, retargeted as watermarking rather than obfuscation
strength (section 6). Steps 2b–2d from section 4 remain open; next up
would be 2b (restricted-subset VM) if the project wants to pursue actual
casual-reading-cost increase separately from attribution.
