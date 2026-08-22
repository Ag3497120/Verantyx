"""The imported commonsense sovereign against the frozen 50-item bank.

Protocol: the bank (tools/commonsense_bank_2026-08-14.json) and the
scoring (measure_commonsense_baseline.classify) are UNCHANGED; the
thresholds were pre-registered in
tools/commonsense_import_preregistration_2026-08-16.json (edf4d5a)
before ConceptNet was downloaded. This script only adds the route:

    輸入   commonsense_conceptnet.db, direct core lookup, casefold.
           Core absent -> UNKNOWN_NO_EVIDENCE (TYPED_REFUSAL).
           Core present -> the answer is the facet objects rendered
           with their relation names, and it is scored exactly like
           the shelf: axis in the blob or it is WRONG.

The verdict at the bottom applies the registered criterion mechanically:
adopt if correct >= 18 and wrong <= 2, else park.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from measure_commonsense_baseline import axis_hit  # noqa: E402
from verantyx.cross_store import CrossStore  # noqa: E402

ROOT = Path.home() / "Projects" / "vera-corpus"
BANK = Path(__file__).resolve().parent / "commonsense_bank_2026-08-14.json"
PREREG = (Path(__file__).resolve().parent
          / "commonsense_import_preregistration_2026-08-16.json")

REL_JA = {"isa": "とは", "prop": "性質", "use": "用途", "can": "できる",
          "loc": "場所", "part": "部分", "madeof": "素材",
          "causes": "引き起こす", "sub": "含む出来事", "has": "持つ",
          "want": "望む", "needs": "前提"}


def render(cross) -> str:
    # v2 question gate (pre-registered): a 「XはYですか」 property
    # question reads every arm EXCEPT loc — a place answers where,
    # never whether.
    parts = []
    for f in sorted(cross):
        if "|" in f:            # weight-bucket shadow facets are not text
            continue
        rel, _, obj = f.partition(":")
        if rel == "loc":
            continue
        parts.append("%s:%s" % (REL_JA.get(rel, rel), obj))
    return " ".join(parts)


def main() -> int:
    bank = json.loads(BANK.read_text())
    prereg = json.loads(PREREG.read_text())
    store = CrossStore.load(ROOT / "build" / "commonsense_conceptnet.db")

    rows = []
    counts = {"ANSWERED_CORRECT": 0, "TYPED_REFUSAL": 0, "WRONG": 0}
    for item in bank["items"]:
        subj = item["subject"].casefold()
        cross = store.crosses.get(subj)
        if not cross:
            outcome, blob = "TYPED_REFUSAL", ""
        else:
            blob = render(cross)
            tokens = list(item["axis_tokens"]) + [item["property"]]
            outcome = ("ANSWERED_CORRECT" if axis_hit(blob, tokens)
                       else "WRONG")
        counts[outcome] += 1
        rows.append({"id": item["id"], "subject": item["subject"],
                     "outcome": outcome, "blob": blob[:120]})

    adopt = (counts["ANSWERED_CORRECT"] >= prereg["adopt_if"]["correct_min"]
             and counts["WRONG"] <= prereg["adopt_if"]["wrong_max"])
    print(json.dumps({
        "route": "輸入(conceptnet5.7)", "n": bank["n"], **counts,
        "baseline_to_beat": prereg["baseline_to_beat"],
        "criterion": prereg["adopt_if"],
        "verdict": "ADOPT" if adopt else "PARK",
        "rows": rows,
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
