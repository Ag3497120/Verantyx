"""Kin-prediction test: does lateral association carry meaning?

Same 150 held-out cores as the reach/explain measurement. Ground truth =
the held core's own top-10 facets. Predictors are blind to that cross:
  A  kin (units >= 2 chars) aggregated facets, top-20
  B  kin (all units, atoms included), top-20
  C  single richest held unit's facets, top-20 (what reach/explain use)
  D  20 random vocabulary words' aggregated facets (chance floor)
Metric: recall of the true top-10 within each predictor's top-20.
"""
import json
import pickle
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.cross_store import CrossStore
from verantyx.granularity import decompose_units
from verantyx.lattice import build, predict_facets
from verantyx.reach import by_units
from verantyx.writer import Writer

ROOT = Path.home() / "Projects" / "vera-corpus"
KANJI = re.compile(r"^[㐀-䶿一-鿿]{3,5}$")

doms = pickle.loads((ROOT / "build" / "federation.pkl").read_bytes())
ja = CrossStore()
for d in doms:
    for s in doms[d].values():
        ja.source_labels |= getattr(s, "source_labels", set())
        for c, cr in s.crosses.items():
            dst = ja.crosses.setdefault(c, {})
            for f, n in cr.items():
                dst[f] = dst.get(f, 0) + n

vocab = Writer.load(ROOT / "build" / "writer.json").vocab
labels = ja.source_labels

eligible = sorted(c for c in ja.crosses if c not in labels and KANJI.match(c))
stride = max(1, len(eligible) // 150)
held_out = eligible[::stride][:150]
removed = {t: ja.crosses.pop(t) for t in held_out}

lat = build(list(vocab.attested))
print("lattice:", json.dumps(lat.report()), flush=True)
model = decompose_units([c for c in ja.crosses if c not in labels])

vocab_words = sorted(w for w in vocab.attested if w in ja.crosses)


def truth(term):
    cross = removed[term]
    fs = [f for f in sorted(cross, key=lambda f: (-cross[f], f))
          if f not in labels][:10]
    return set(fs)


def recall(pred, true):
    return len(set(pred) & true) / len(true) if true else None


def single_unit_pred(term):
    part = by_units(ja, model, term)
    if not part:
        return []
    cross = ja.crosses.get(part) or {}
    return [f for f in sorted(cross, key=lambda f: (-cross[f], f))
            if f not in labels][:20]


def random_pred(i):
    # Deterministic "random": stride through the vocab keyed on index.
    step = max(1, len(vocab_words) // 20)
    picks = vocab_words[(i * 7) % step::step][:20]
    weights = {}
    for w in picks:
        for f, n in (ja.crosses.get(w) or {}).items():
            if f in labels:
                continue
            weights[f] = weights.get(f, 0) + n
    return [f for f, _ in sorted(weights.items(),
                                 key=lambda kv: (-kv[1], kv[0]))[:20]]


rows = {"kin2": [], "kin_all": [], "unit": [], "rand": []}
covered = {"kin2": 0, "kin_all": 0, "unit": 0}
for i, term in enumerate(held_out):
    true = truth(term)
    if not true:
        continue
    a = predict_facets(lat, ja, term, min_unit=2)
    b = predict_facets(lat, ja, term, min_unit=1)
    c = single_unit_pred(term)
    d = random_pred(i)
    if a:
        covered["kin2"] += 1
        rows["kin2"].append(recall(a, true))
    if b:
        covered["kin_all"] += 1
        rows["kin_all"].append(recall(b, true))
    if c:
        covered["unit"] += 1
        rows["unit"].append(recall(c, true))
    rows["rand"].append(recall(d, true))

out = {}
for k, v in rows.items():
    vals = [x for x in v if x is not None]
    out[k] = {"n": len(vals),
              "mean_recall": round(sum(vals) / len(vals), 4) if vals else None}
out["covered"] = covered
print(json.dumps(out, ensure_ascii=False, indent=1))
