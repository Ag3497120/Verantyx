# Software watermarking (leak attribution, not obfuscation strength)

This reuses the same fingerprint-derivation mechanism as
[obfuscation](OBFUSCATE.md), but for a different, more modest goal. See
[docs/OBFUSCATE_V2_PLAN.md](OBFUSCATE_V2_PLAN.md) for why "make the naming
scheme itself vary per person" doesn't make a single obfuscated file
harder to *read* — it doesn't. What it's good for instead is a much older,
well-established technique: **software watermarking** (Collberg &
Thomborson) — embedding a durable signal that lets you attribute a leaked
copy back to whoever it was distributed to, after the fact.

This is a fundamentally easier problem than "prevent reading." It doesn't
need to win an arms race against a skilled reader — it only needs to
survive ordinary copy/paste/rename, which a naming pattern does.

## How it works

`vera obfuscate` already derives a fingerprint from your store and a key
from that fingerprint (see [OBFUSCATE.md](OBFUSCATE.md)). v2 adds one more
derived value: a **variant signature** — which of 96 equivalent naming
schemes (identifier prefix × hex length × case × separator) got used for
this file's renamed identifiers. Two different stores very likely produce
two different variants; the same store always produces the same one.

```bash
vera obfuscate billing.py                      # now also picks a variant
vera watermark register registry.json --owner-id acme_corp   # store the signature
vera watermark identify registry.json --file billing.py.obf   # later: who does this match?
```

The registry file stores only the small `signature_id` string (e.g.
`_k|10|0|`) per owner — **never the raw fingerprint**. This matters: the
fingerprint feeds `derive_key()` directly, so it's as sensitive as the AES
key itself. The signature_id is safe to put in a shared registry, a legal
record, or a support ticket; the fingerprint/store is not.

## Honest limits

- **96 points total, not 2^256.** With that few, unrelated owners will
  occasionally land on the same variant by pure coincidence — expect this
  once a registry holds roughly √96 ≈ 10 owners (birthday bound).
  `identify_candidates()` returns a **candidate list**, not a single name,
  and says so in its own output. Treat a match as evidence to combine with
  other information (who had access, when), not as proof by itself.
- **Detection requires an intact, unedited naming pattern.** If someone
  strips/renames identifiers again before redistributing, the watermark is
  gone. This resists careless copy/paste, not a deliberate attempt to
  scrub it — same honesty rule as everywhere else in this project: no
  "can't be removed" claim is made here.
- **This is not the obfuscation-strength feature.** If your goal is
  raising the cost of casual reading, that's the VM-transform work
  described in `docs/OBFUSCATE_V2_PLAN.md` §2b, tracked separately. This
  document is only about after-the-fact attribution.
