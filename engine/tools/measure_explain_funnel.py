"""The explain funnel over 150 held-out cores, with the lattice wired.

Same protocol as tools/measure_lattice.py (kanji-only cores 3-5 chars,
deterministic stride, popped before model/ladder are built). Reports the
verdict tally before/after the kin hand-over: the KIN_NEIGHBOURHOOD rows
are exactly the former UNKNOWN_NO_REACH rows the lattice can family.
"""
import json
import pickle
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.cross_store import CrossStore
from verantyx.explain import explain
from verantyx.graded import GradedJudge, settings_for
from verantyx.lattice import build
from verantyx.reach import build_model
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
for t in held_out:
    ja.crosses.pop(t)

model = build_model(ja)
judge = GradedJudge(settings_for("これは日本語です。")).build(ja)
lat = build(list(vocab.attested))

tally = {}
examples = {}
for term in held_out:
    ex = explain(ja, term, model=model, vocab=vocab, judge=judge, lat=lat)
    v = ex["verdict"]
    tally[v] = tally.get(v, 0) + 1
    if len(examples.setdefault(v, [])) < 3:
        examples[v].append((term, (ex.get("text") or "")[:80]))

print(json.dumps({"tally": dict(sorted(tally.items())),
                  "examples": examples}, ensure_ascii=False, indent=1))
