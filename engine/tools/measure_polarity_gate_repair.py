"""Gate B measured as a proposal. `polarity.py` is not modified.

The repair pre-registration
(`docs/PREREGISTERED_2026-08-16_polarity_gate_repair.md`) names a bank
conflict in advance — 「問題ない。」 → `¬ある` is expected to stop firing —
and forbids resolving it inside the measurement. So Gate B lives here,
applied as a filter over what the unmodified reader returns, and the
changed bank items are listed for a person to decide. Editing the gate
inside `polarity.py` first would have resolved the conflict silently by
making one of the two frozen banks simply wrong.

    python3.11 tools/measure_polarity_gate_repair.py [N]
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BANK = Path(__file__).resolve().parent / "polarity_bank_2026-08-14.json"

#: pos1 values that carry no testimony however real the word is.
_BLOCKED_POS1 = frozenset({"助動詞", "接続詞", "名詞", "助詞", "副詞"})
#: 非自立可能 is deliberately NOT blocked. It is a property of the
#: lexeme ("〜てくる exists"), not of the usage, so blocking on it cut
#: 彼は来ない / 我は行かぬ / 今はできません. See the third
#: pre-registration; B'3 below asks the adjacency instead.
_BLOCKED_POS2 = frozenset()

_tagger = None


def _pos(lemma: str):
    """(pos1, pos2) for a lemma tagged standalone, or None."""
    global _tagger
    if _tagger is None:
        import fugashi
        _tagger = fugashi.Tagger()
    toks = list(_tagger(lemma))
    if len(toks) != 1:
        return None
    f = toks[0].feature
    return (f.pos1, f.pos2)


def _conjugated_surface(lemma: str, left: str) -> str:
    """The negated verb's own text at the end of `left`, or "".

    Tried longest-first from the lemma's stem so 捨てる contributes 捨て
    rather than 捨. Only the verb's own spelling is removed; nothing is
    guessed about what lies further left.
    """
    stem = lemma[:-1] if len(lemma) > 1 else lemma
    for cand in (lemma, stem, lemma[:-2] if len(lemma) > 2 else ""):
        if cand and left.endswith(cand):
            return cand
    return ""


def _after_te_joint(sentence: str, span, lemma: str) -> bool:
    """B″3 — is this verb an auxiliary hanging off a て-form?

    The third attempt scanned raw characters and matched the で of
    できる itself (「今はでき」 read as で+き). The verb's own surface is
    already known, so it is subtracted BEFORE anything is looked for.
    No verb's spelling can then be mistaken for the joint, which removes
    the class of error rather than narrowing it.
    """
    if not span:
        return False
    left = sentence[:max(int(span[0]), 0)]
    own = _conjugated_surface(lemma, left)
    remainder = left[:len(left) - len(own)] if own else left
    return remainder.endswith("て") or remainder.endswith("で")


def gate_b(lemma: str, sentence: str = "", span=None) -> bool:
    """Content verb/adjective, not serving as an auxiliary here.

    B'1 part of speech, B'2 single token, B'3 not after a て-form. The
    dictionary and the grammar decide; there is no exclusion list and no
    frequency threshold.
    """
    p = _pos(lemma)
    if p is None:                                   # B'2
        return False
    pos1, pos2 = p
    if pos1 in _BLOCKED_POS1:                       # B'1
        return False
    if pos1 not in ("動詞", "形容詞"):
        return False
    if sentence and _after_te_joint(sentence, span, lemma):  # B″3
        return False
    return True


def main(n: int = 10000) -> int:
    try:
        import fugashi  # noqa: F401
        import unidic_lite  # noqa: F401
    except Exception as exc:
        raise SystemExit("G0 UNMET: %s — run is VOID, not a null result" % exc)

    from verantyx.lang import ja_chosen_core
    from verantyx.meaning_index import connection
    from verantyx.polarity import ObservedNegation, observe_negation

    conn = connection()
    rows = conn.execute("SELECT k, v FROM defs LIMIT ?", (n,)).fetchall()

    before, after = Counter(), Counter()
    cores_after, blocked_pos = set(), Counter()
    n_before = n_after = 0

    for _t, text in rows:
        sent = (text or "").strip()
        if not sent:
            continue
        reading = observe_negation(sent)
        if not reading.observed:
            continue
        core = ja_chosen_core(sent)
        if not core:
            continue
        for obs in reading.observed:
            if not isinstance(obs, ObservedNegation):
                continue
            before[obs.lemma] += 1
            n_before += 1
            if gate_b(obs.lemma, sent, obs.span):
                after[obs.lemma] += 1
                cores_after.add(core)
                n_after += 1
            else:
                p = _pos(obs.lemma)
                blocked_pos["%s/%s" % p if p else "untaggable"] += 1

    # P5 — re-check independently rather than trusting the filter.
    p5_violations = sorted({lm for lm in after if not gate_b(lm)})

    # P6 — the frozen W1a banks, re-run with Gate B applied.
    changed = []
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    for item in bank.get("sentences", []):
        s = item.get("text") or item.get("sentence") or ""
        if not s:
            continue
        r = observe_negation(s)
        kept = [o for o in r.observed
                if isinstance(o, ObservedNegation) and gate_b(o.lemma, s, o.span)]
        if len(kept) != len(r.observed):
            changed.append({
                "id": item.get("id"),
                "text": s,
                "was": [o.lemma for o in r.observed],
                "now": [o.lemma for o in kept],
                "expected": item.get("expected"),
            })

    out = {
        "Q1_facets": {"before_gate_b": n_before, "after_gate_b": n_after,
                      "removed": n_before - n_after,
                      "kept_share": round(n_after / max(n_before, 1), 4)},
        "Q2_top_surviving_lemmas": after.most_common(20),
        "Q3_cores_after": len(cores_after),
        "blocked_by_pos": blocked_pos.most_common(8),
        "P5": "PASS" if not p5_violations else "FAIL",
        "P5_violations": p5_violations,
        "P6_bank_items_changed": len(changed),
        "P6_changes": changed[:12],
        "polarity_py_modified": False,
        "store_written": False,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 10000))
