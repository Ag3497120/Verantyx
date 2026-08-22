"""Planted ground truth on corpora the pipeline was never tuned on.

Every other suite in this package pins a defect that a REAL corpus exposed —
which is the right way to fix defects and the wrong way to claim generality:
a pipeline polished against one archive may simply have memorised its shape.
This suite generates its corpora, from vocabulary chosen to overlap nothing
in the archives used during development, and knows the right answer in
advance because it planted it.

It also measures the number nothing else measures: RECALL. The false-
positive work drove contradictions on the development corpus from 24 to 0,
and 0 proves nothing about detection — a detector that never fires also
scores 0. Here, contradictions exist by construction, and the question is
how many come back.

Two tiers, reported separately and held to different standards:

  Tier A — canonical claim forms ("The X is open." / 「Xは開設されました。」).
           Recall must be 100%. These are the forms the subject gate was
           designed around; missing one is a regression, not a limitation.

  Tier B — harder phrasings (passive, adverbs between subject and state,
           formal register). Recall is MEASURED AND PRINTED, with a floor of
           zero. This is the honest number for "what would this miss in the
           wild", and pinning it to today's value would freeze a limitation
           in place as if it were a specification.

Precision is asserted at 100% on both tiers together: the planted traps
(compound nouns, prepositional on/off, subordinate clauses) must produce
nothing, whatever else happens. A missed disagreement costs one finding;
an invented one costs the reader's trust in all of them.

Run:  python3 -m verantyx.generalization_eval
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

from .catalog import build_catalog
from .cross_store import CrossStore
from .document_ingest import Document, deep_report, ingest_documents
from .intake_quality import assess

# ---------------------------------------------------------------------------
# Planted corpus. Nouns deliberately disjoint from the development archives
# (which were about gateways, models, agents, shelters and roads).
# ---------------------------------------------------------------------------

_EN_NOUNS = ["aquarium", "greenhouse", "observatory", "brewery", "lighthouse"]
_JA_NOUNS = ["水族館", "温室", "天文台", "醸造所", "灯台"]

#: (positive sentence template, negative sentence template)
_EN_TIER_A = ("The {n} is open.", "The {n} is closed.")
_JA_TIER_A = ("{n}は開設されました。", "{n}は閉鎖されました。")

#: Once tier B, promoted after the fixes they motivated: adverbs between the
#: copula and the state ("remains fully open"), small-clause participles
#: ("was reported closed"), and Japanese formal topic marking
#: (「につきましては」). Promotion is the tier system working as designed —
#: a form the grammar now covers is a regression if it ever misses again.
_EN_TIER_A2 = ("The {n} remains fully open today.",
               "The {n} was reported closed by staff.")
_JA_TIER_A2 = ("{n}は本日も開設されたままです。",
               "{n}につきましては閉鎖されましたのでご注意ください。")

#: The new frontier — quotative report, humble keigo, and negation scoped
#: inside a longer predicate. What the wild writes when it is being careful.
_EN_TIER_B = ("Staff confirmed that the {n} has been open since spring.",
              "According to the notice, the {n} is closed indefinitely.")
_JA_TIER_B = ("{n}は開館しておりますのでご利用いただけます。",
              "{n}が閉鎖されたとの報告が寄せられています。")

#: Traps: polar words present, no claim made. Each is a class of false
#: positive that development actually produced, rephrased onto neutral nouns.
_TRAPS = [
    "The curator put the sign on top of the shelf.",
    "Opening hours are a trade-off between staff and visitors.",
    "If the annex is renovated but the elevator is unavailable, visitors complain.",
    "危険物の保管庫が敷地内にあります。",
    "停止線の位置を確認してください。",
    "開始時刻は未定です。",
    # Hypotheticals assert nothing. Both shapes produced a placed pole at
    # some point during development — the second one on a real document,
    # where the parenthetical "(when group access is available…)" met a
    # genuine "was not available" claim from the SAME file and the file
    # appeared to contradict itself.
    "If the elevator is unavailable, visitors should use the stairs.",
    "The policy values (when group access is available on your surface) are listed.",
    "エレベーターが使用不可の場合は階段を使ってください。",
    # Both found on a real 内閣府 case-study PDF, where they met each other
    # inside ONE document and were reported as that document contradicting
    # itself. Narrative past is history, not a current state; a polar term
    # inside an enumeration is being named, not asserted.
    "避難所が閉鎖した後にPCR検査を実施したところ陽性が判明した。",
    "避難所の開設、運営等については留意事項を発出しています。",
    "避難所が開設された際の対応を記載しています。",
]

_FILLER_EN = ["The {n} was founded decades ago.",
              "Many visitors praised the {n} last spring."]
_FILLER_JA = ["{n}の来場者数は昨年より増えました。",
              "{n}の設立は数十年前です。"]


def _corpus() -> Tuple[List[Document], List[str], List[str]]:
    """Two disagreeing sources over ten planted oppositions, plus noise.

    Returns (documents, tier_a_topics, tier_b_topics). Tier A uses the first
    three nouns of each language, tier B the remaining two — no noun appears
    in both tiers, so a tier B miss cannot be masked by a tier A hit on the
    same topic.
    """
    a_lines, b_lines = [], []
    tier_a, tier_b = [], []
    for n in _EN_NOUNS[:2]:
        a_lines.append(_EN_TIER_A[0].format(n=n))
        b_lines.append(_EN_TIER_A[1].format(n=n))
        tier_a.append(n)
    for n in _JA_NOUNS[:2]:
        a_lines.append(_JA_TIER_A[0].format(n=n))
        b_lines.append(_JA_TIER_A[1].format(n=n))
        tier_a.append(n)
    # The promoted forms ride the third noun of each language, so canonical
    # and promoted shapes are asserted on disjoint topics.
    a_lines.append(_EN_TIER_A2[0].format(n=_EN_NOUNS[2]))
    b_lines.append(_EN_TIER_A2[1].format(n=_EN_NOUNS[2]))
    tier_a.append(_EN_NOUNS[2])
    a_lines.append(_JA_TIER_A2[0].format(n=_JA_NOUNS[2]))
    b_lines.append(_JA_TIER_A2[1].format(n=_JA_NOUNS[2]))
    tier_a.append(_JA_NOUNS[2])
    for n in _EN_NOUNS[3:]:
        a_lines.append(_EN_TIER_B[0].format(n=n))
        b_lines.append(_EN_TIER_B[1].format(n=n))
        tier_b.append(n)
    for n in _JA_NOUNS[3:]:
        a_lines.append(_JA_TIER_B[0].format(n=n))
        b_lines.append(_JA_TIER_B[1].format(n=n))
        tier_b.append(n)
    for n in _EN_NOUNS:
        a_lines.append(_FILLER_EN[0].format(n=n))
        b_lines.append(_FILLER_EN[1].format(n=n))
    for n in _JA_NOUNS:
        a_lines.append(_FILLER_JA[0].format(n=n))
        b_lines.append(_FILLER_JA[1].format(n=n))
    a_lines.extend(_TRAPS[:3])
    b_lines.extend(_TRAPS[3:])
    docs = [Document("source_alpha", " ".join(a_lines)),
            Document("source_beta", " ".join(b_lines))]
    return docs, tier_a, tier_b


def main() -> int:
    print("generalization — planted ground truth, vocabulary never tuned on\n")
    failures: List[str] = []

    docs, tier_a, tier_b = _corpus()
    store = CrossStore()
    rep = ingest_documents(store, docs)

    contested: Dict[str, bool] = {}
    for topic in tier_a + tier_b:
        detail = deep_report(store, topic)
        contested[topic] = bool(detail["disputed"])

    # -- Tier A: canonical forms must all come back -------------------------
    missed_a = [t for t in tier_a if not contested[t]]
    recall_a = 1 - len(missed_a) / len(tier_a)
    ok = not missed_a
    print(f"[{'ok  ' if ok else 'FAIL'}] tier A recall {recall_a:.0%} "
          f"({len(tier_a) - len(missed_a)}/{len(tier_a)}) — canonical "
          f"claim forms, both languages")
    if missed_a:
        print(f"        missed: {missed_a}")
        failures.append(f"tier A recall: missed {missed_a}")

    # -- Tier B: measured, printed, floor of honesty ------------------------
    hit_b = [t for t in tier_b if contested[t]]
    recall_b = len(hit_b) / len(tier_b)
    print(f"[info] tier B recall {recall_b:.0%} ({len(hit_b)}/{len(tier_b)}) — "
          f"passive/adverbial/formal phrasings; the honest wild-text number, "
          f"not a target")

    # -- Precision: the traps must stay silent ------------------------------
    invented = []
    for core in store.crosses:
        if core in tier_a or core in tier_b:
            continue
        if deep_report(store, core)["disputed"]:
            invented.append(core)
    ok = not invented
    print(f"[{'ok  ' if ok else 'FAIL'}] precision 100%: no contradiction "
          f"outside the planted set")
    if invented:
        for c in invented:
            print(f"        invented on: {c}")
        failures.append(f"invented contradictions: {invented}")

    # -- Attribution survives on unseen vocabulary --------------------------
    sample = deep_report(store, tier_a[0])
    attributed = all(side.get("sources")
                     for d in sample["disputed"] for side in d["sides"])
    ok = attributed and sample["disputed"]
    print(f"[{'ok  ' if ok else 'FAIL'}] contested sides carry their source "
          f"on never-seen nouns")
    if not ok:
        failures.append("attribution")
    print()

    # -- Intake self-assessment: clean corpus passes, garbage is flagged ----
    intake = assess(store, rep)
    ok = intake["verdict"] == "INTAKE_OK"
    print(f"[{'ok  ' if ok else 'FAIL'}] intake calls this healthy corpus "
          f"{intake['verdict']} (coverage {intake['metrics']['coverage']})")
    if not ok:
        failures.append(f"intake on healthy corpus: {intake['verdict']}")

    garbage_store = CrossStore()
    garbage = Document("noise", "xq zv qwp. " * 400)
    g_rep = ingest_documents(garbage_store, [garbage])
    g = assess(garbage_store, g_rep)
    ok = g["verdict"] != "INTAKE_OK"
    print(f"[{'ok  ' if ok else 'FAIL'}] intake refuses to bless garbage "
          f"({g['verdict']})")
    if not ok:
        failures.append("intake blessed garbage")
    print()

    # -- End to end through files: the whole catalogue path, same standard --
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "alpha.txt").write_text(docs[0].text, encoding="utf-8")
        (root / "beta.txt").write_text(docs[1].text, encoding="utf-8")
        cat = build_catalog([str(root / "alpha.txt"), str(root / "beta.txt")])
        cat_contested = {e.topic for e in cat.entries if e.contested}
        missed = [t for t in tier_a if t not in cat_contested]
        ok = not missed
        print(f"[{'ok  ' if ok else 'FAIL'}] catalogue path preserves every "
              f"tier A contradiction ({len(tier_a) - len(missed)}/{len(tier_a)})")
        if missed:
            print(f"        lost in the catalogue: {missed}")
            failures.append(f"catalogue lost: {missed}")
    print()

    if failures:
        print(f"{len(failures)} failed: {', '.join(failures)}")
        return 1
    print("recall measured, precision held, on vocabulary never tuned on")
    return 0


if __name__ == "__main__":
    sys.exit(main())
