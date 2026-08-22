# Reversible code obfuscation, keyed by your store's personal state

Renames identifiers deterministically and encrypts the reversal mapping
with a key derived from **your own CrossStore's accumulated state** — not
from a password you have to remember, and not from hiding the algorithm
(which stays fully public, same as everything else in this repo).

## Why this design (and not the alternatives we rejected)

Earlier drafts of this feature tried to make the *obfuscation process
itself* hard to reverse — a "6-axis isolation" scheme, or "requires the
same multi-frontier search Vera uses" scheme. Both are security theater:
Vera's algorithm is public (MIT, on GitHub), so any sufficiently motivated
party — human or AI — can just run the same public code. Kerckhoffs's
principle: security must live in a **secret**, never in an algorithm's
unusualness. See [docs/DESIGN.md](DESIGN.md#reversible-obfuscation-keyed-by-personal-state)
for the full reasoning trail, including why "make the AI solve a puzzle to
decode it" doesn't work either.

What actually differs between two people running the identical public
code is **what they poured, in what order** — the path-dependent residue
in their CrossStore (facet counts, insertion order, adaptation history).
That accumulated state is real, personal, and hard for an outsider to
reconstruct — so it's used as **key material**, feeding a standard,
vetted primitive (PBKDF2 → AES-256-GCM via the `cryptography` library),
not a home-grown cipher.

```text
your CrossStore's accumulated state (counts, order, history)
        │  fingerprint_store()  — SHA-256, order-sensitive
        ▼
   fingerprint (bytes)
        │  derive_key()  — PBKDF2-HMAC-SHA256, 200k iterations
        ▼
   32-byte key  ──────────────►  AES-256-GCM  ──►  encrypted mapping
```

## Install

```bash
pip install -e ".[obfuscate]"   # adds `cryptography`
```

## Use

```bash
vera obfuscate path/to/billing.py --export-key recovery.key
# → billing.py.obf      (renamed source, safe to share/publish)
# → billing.py.obfmap   (AES-256-GCM encrypted mapping)
# → recovery.key        (back this up — see below)

vera deobfuscate billing.py.obf billing.py.obfmap            # via your store
vera deobfuscate billing.py.obf billing.py.obfmap --key-file recovery.key  # via the key alone
```

## What actually gets renamed, and what doesn't

Renaming uses exact AST source positions (`ast.Name`, `ast.arg`,
`FunctionDef`/`ClassDef` names) — **never** a whole-file text regex. This
matters for correctness, not just cosmetics: a naive regex would also
rewrite a string literal like `{"price": price}["price"]` wherever the
text "price" appears, silently changing runtime behavior (e.g. dict keys
used for dispatch) whenever an identifier name coincides with a string a
program depends on. String literals, comments, and docstrings are never
touched; type annotations are preserved (`ast.arg`'s span includes the
annotation, so the renamer trims it to the bare parameter name — a real
bug caught and fixed by the `OBF_*` forks during development).

## Recovery — read this before relying on it

The derived key is **not** portable by default: it's regenerated from your
store's exact state. If you lose that store (corruption, wrong machine,
data pruned), you lose the ability to decrypt existing mappings — same
trade-off as any personal-secret-derived key.

`--export-key` writes the *already-derived* 32-byte key to its own file
(`chmod 600`). That file — not the store — becomes the portable secret.
Treat it like a password: back it up somewhere the store itself doesn't
live (a password manager, offline media). `vera deobfuscate --key-file`
uses it directly, with no dependency on the original store surviving.

## Honest limits

- **Only as unique as your private data.** The public base store
  (`kofdai/Verantyx-Vera-base-store`, 889k cores) gives zero uniqueness by
  itself — anyone can download it. Real key strength comes from what you
  poured *beyond* that: personal documents, your own pour order, usage
  history.
- **Renaming, not semantic protection.** This does not hide business logic
  inferable from numeric literals or code shape (`round(x*1.21, 2)` still
  reads as "≈21% markup" regardless of identifier names) — no obfuscation
  scheme, per current market research, reliably defeats that. See
  [docs/DESIGN.md](DESIGN.md#reversible-obfuscation-keyed-by-personal-state).
- **AES-GCM refuses on a wrong key** (authentication failure, not silently
  wrong output) — verified by `OBF_WRONG_KEY_REFUSES`.
- Python only, identifier-level renaming (functions, classes, params,
  locals) — no control-flow obfuscation, no literal encryption (that would
  require additional cryptographic tooling, and this module deliberately
  keeps to the one already-vetted primitive it needs).
