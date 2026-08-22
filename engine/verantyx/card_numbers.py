"""Every number on the published card, measured against the published file.

A model card that quotes figures from an earlier build is a card describing
a model nobody can download. So this measures the artifact itself — the
`vera.db` that gets uploaded — and prints exactly what the card claims, with
the query beside it, so a reader holding the same file can re-run it and get
the same rows.

    python3 -m verantyx.card_numbers --db build/vera.db

Nothing here is a target. `closure` reporting less than 100% would be a real
finding about the engine, not a threshold to tune until it passes.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

#: Questions the corpus should answer, questions it should refuse, and
#: questions whose refusal must be a SPECIFIC type. Mixed on purpose: a
#: bank of answerable questions measures nothing about a system whose claim
#: is that it refuses well.
ANSWERABLE = ("正当防衛とは", "殺人罪の刑は", "契約の成立要件は", "時効とは",
              "過失相殺とは", "超伝導とは", "民法とは", "所有権とは",
              "negligence", "consideration", "jurisdiction", "estoppel")
REFUSABLE = ("今日の天気は", "明日の株価は", "こんにちは",
             "ヴォルフガング粒子とは", "ズミルノフ環礁の面積は")


def closure(v: Any, queries: List[str]) -> Dict[str, Any]:
    """Can the store emit a symbol it does not hold?

    The whole no-fabrication claim in one measurement: every token of every
    answered path must be something the sovereign actually holds, as a core
    or as somebody's facet. This is the property that also forbids
    generalisation, so it is not a free win — it is the price, stated.
    """
    emitted = held = 0
    misses: List[str] = []
    for q in queries:
        r = v.ask(q)
        if not r.get("text"):
            continue
        store = v.stores[r.get("language", "ja")]
        vocab = set(store.crosses)
        for cross in store.crosses.values():
            vocab |= set(cross)
        for tok in str(r["text"]).split():
            emitted += 1
            if tok in vocab:
                held += 1
            else:
                misses.append(f"{q} -> {tok}")
    return {"emitted": emitted, "held": held,
            "share": round(100.0 * held / emitted, 1) if emitted else 0.0,
            "misses": misses[:5]}


def determinism(v: Any, queries: List[str], *, rounds: int = 3) -> Dict[str, Any]:
    """The same question, several times, in a shuffled order."""
    first: Dict[str, Any] = {}
    stable = total = 0
    for i in range(rounds):
        qs = list(queries)
        random.Random(i).shuffle(qs)
        for q in qs:
            r = v.ask(q)
            sig = (r.get("verdict"), r.get("core"), r.get("text"))
            if q not in first:
                first[q] = sig
            else:
                total += 1
                stable += sig == first[q]
    return {"repeats": total, "identical": stable,
            "share": round(100.0 * stable / total, 1) if total else 100.0}


def refusals(v: Any, queries: List[str]) -> Dict[str, Any]:
    """Which refusal each unanswerable question earns, and whether it closes."""
    rows = []
    for q in queries:
        r = v.ask(q)
        rem = r.get("remedy") or {}
        rows.append({
            "q": q, "verdict": r.get("verdict"),
            "typed": bool(r.get("verdict", "").startswith("UNKNOWN")),
            "closes_by_registration": rem.get("needs_registration"),
            "has_remedy": bool(rem.get("register")),
        })
    return {"rows": rows,
            "typed": f"{sum(r['typed'] for r in rows)}/{len(rows)}",
            "with_remedy": f"{sum(r['has_remedy'] for r in rows)}/{len(rows)}"}


#: Heads that no Japanese corpus of statutes and encyclopedia articles has a
#: compound for. Attached to a REAL held core, they make a term that cannot
#: exist while looking exactly like one that could.
_INVENTED_HEADS = ("ヴォルフガング", "ズミルノフ", "カルタヘナ", "ブリュッセル",
                   "メゾン", "テオドール", "ラヴィニア", "オストロフ",
                   "ヒュペリオン", "ザルツ")


def invented(v: Any, *, n: int = 200, seed: int = 7) -> Dict[str, Any]:
    """Does an invented subject get refused, or answered about a substring?

    Closure guarantees the store never emits a symbol it does not hold. It
    guarantees nothing about the SUBJECT: the staircase seeds on whatever
    part of the term it recognises, so ヒュペリオン数人 lands on 数人 and the
    unknown element is dropped without a word. The reader is then told about
    a different thing than the one they asked about, in the same shape as a
    real answer.

    This is the honest counterweight to `closure` and belongs beside it on
    the card. It is measured, not asserted.
    """
    store = v.stores.get("ja")
    if store is None:
        return {}
    cores = set(store.crosses)
    rnd = random.Random(seed)
    tails = [c for c in cores if 2 <= len(c) <= 3][:6000]
    probes: List[str] = []
    while len(probes) < n and tails:
        w = rnd.choice(_INVENTED_HEADS) + rnd.choice(tails)
        if w not in cores:
            probes.append(w)

    counts: Dict[str, int] = {}
    dropped = 0
    examples: List[str] = []
    for w in probes:
        r = v.ask(w + "とは")
        verdict = r.get("verdict", "?")
        counts[verdict] = counts.get(verdict, 0) + 1
        core = r.get("core")
        if r.get("text") and core and core != w:
            dropped += 1
            if len(examples) < 5:
                examples.append(f"{w} -> {core}")
    answered = sum(n_ for verdict, n_ in counts.items()
                   if not verdict.startswith("UNKNOWN"))
    return {"probes": len(probes), "verdicts": counts,
            "answered_not_refused": answered,
            "share_answered": round(100.0 * answered / len(probes), 1),
            "seeded_onto_substring": dropped, "examples": examples}


def latency(v: Any, queries: List[str]) -> Dict[str, Any]:
    ms: List[float] = []
    for q in queries:
        t = time.time()
        v.ask(q)
        ms.append((time.time() - t) * 1000)
    ms.sort()
    return {"median_ms": round(ms[len(ms) // 2], 1),
            "max_ms": round(ms[-1], 1), "n": len(ms)}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(corpus_root() / "build" / "vera.db"))
    a = ap.parse_args(argv)
    db = Path(a.db)

    from .export_sqlite import vera

    t0 = time.time()
    v = vera(db)
    load_s = round(time.time() - t0, 1)

    every = list(ANSWERABLE) + list(REFUSABLE)
    out = {
        "artifact": {"path": str(db),
                     "mb": round(db.stat().st_size / 1048576, 1),
                     "load_seconds": load_s,
                     "sovereigns": {k: {"cores": len(s.crosses),
                                        "facets": sum(len(c) for c in
                                                      s.crosses.values())}
                                    for k, s in sorted(v.stores.items())}},
        "closure": closure(v, list(ANSWERABLE)),
        "determinism": determinism(v, every),
        "refusals": refusals(v, list(REFUSABLE)),
        "invented_subjects": invented(v),
        "latency": latency(v, every),
    }
    out["verdict"] = ("ANSWER"
                      if out["closure"]["share"] == 100.0
                      and out["determinism"]["share"] == 100.0
                      else "DRIFTED")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["verdict"] == "ANSWER" else 1


if __name__ == "__main__":
    sys.exit(main())
