"""Tree replication: the witness law lifted to the tree's scale.

The single-level measurement said data-varied replicas agree as witnesses
(dissent 97.6% evidence-agreement) and cut-varied replicas must never vote
(out-of-corpus 0 -> 8 when they did). The record's design note promised the
next step: "データ違いの複製 — 木ごと複製し、木同士は証人 — 一致の帯が付く".
This module is that step, measured.

Five trees are grown, one per selection-rule witness (法令 / 百科 / 法学 /
多分野 / 指名) — same construction, different DATA, which is what makes them
witnesses and not copies. Leaves inside each tree are the corpus's own
source documents (the natural units it asserts); `--blocks` reruns the
deliberately-arbitrary alphabetical ablation for comparison.

A probe (a subject some witnesses hold) is dropped through every tree:

    holds it   -> the tree should ROUTE it to the leaf that contains it
    lacks it   -> the tree should ABSTAIN (routing would be a guess)

The witness band of a probe is (trees that routed it correctly) over
(trees that hold it) — the tree-scale analogue of the answer-level
witnesses n/m, and like it, the band annotates; it never votes. Fabricated
terms must abstain in all five trees, or the band is theatre.

Measured (python3 -m verantyx.tree_witness, 120 shared probes + 6 fabricated,
document leaves; --blocks reruns the alphabetical ablation):

    trees                     5 (leaves 54..1976, one per source document)
    descents, correct       143 / 403   — every one lands on a leaf that
    descents, WRONG           0 / 403     truly holds the subject
    abstained               260 / 403   — shared generic terms tie across
                                          arms; the router says so instead
                                          of guessing
    fabricated 6 terms       30 / 30 abstained (5 trees x 6, zero error)
    band histogram           4/4 x1, 3/3 x3, 2/n x39, 1/n x49, 0/n x27

    ablation, alphabetical leaves (--blocks): 5 correct / 0 wrong /
    398 abstained — mixed-content blocks give every arm the same face and
    the router honestly falls silent. Leaf choice is not cosmetic: the
    natural units the corpus asserts (documents) are what make faces
    discriminative, same as the 36-law tree's per-law leaves.

The witness law survives the lift: at tree scale as at one level, nothing
is ever fabricated (wrong 0, invented terms all abstain), disagreement is
expressed as abstention, and the band annotates without voting. The open
cost is abstention on generic shared vocabulary — the next lever is
conduction depth, not grouping.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .conduct_tree import Node, build, descend

#: Crosses per leaf block. ~1k keeps depth at log6 without huge nodes.
LEAF_BLOCK = 1024

#: Terms that exist nowhere; every tree must abstain on every one.
FABRICATED = ["蒼穹罪", "逆時効権", "断層信託", "referendum囲", "空目条約", "虚数抵当"]


def leaves_of(crosses: Dict[str, Dict[str, int]],
              block: int = LEAF_BLOCK) -> Dict[str, Any]:
    """Sorted-name blocks as leaves — the arbitrary ablation (see module doc)."""
    names = sorted(crosses)
    out: Dict[str, Any] = {}
    for i in range(0, len(names), block):
        chunk = names[i:i + block]
        out[f"leaf:{chunk[0]}"] = {c: dict(crosses[c]) for c in chunk}
    return out


def document_leaves(db_path: Path, domain: str,
                    min_cores: int = 8) -> Dict[str, Any]:
    """Natural leaves: one per source document, read from the artifact.

    The 36-law tree's leaves were laws — natural, data-varied units — and
    that is what its 95% descent was measured on. The alphabetical ablation
    below shows why this matters: mixed-content blocks give every arm the
    same face and the router (honestly) abstains. Documents are the units
    the corpus itself asserts, so using them is not clustering.

    Tiny documents (< min_cores cores) are folded into one 小文書 leaf per
    initial: a leaf whose profile is three crosses cannot hold a face.
    """
    import sqlite3

    db = sqlite3.connect(str(db_path))
    leaves: Dict[str, Dict[str, Dict[str, int]]] = {}
    rows = db.execute(
        "SELECT l.name, f.core, f.facet, f.count FROM facets f "
        "JOIN leaves l ON l.id = f.leaf WHERE l.domain = ?", (domain,))
    for doc, core, facet, count in rows:
        leaves.setdefault(doc, {}).setdefault(core, {})[facet] = count
    db.close()

    out: Dict[str, Any] = {}
    for doc in sorted(leaves):
        if len(leaves[doc]) >= min_cores:
            out[doc] = leaves[doc]
        else:
            bucket = f"小文書:{doc[:1]}"
            dst = out.setdefault(bucket, {})
            for c, cr in leaves[doc].items():
                d = dst.setdefault(c, {})
                for f, n in cr.items():
                    d[f] = d.get(f, 0) + n
    return out


def leaf_holding(tree_leaves: Dict[str, Any], subject: str) -> Optional[str]:
    for name, store in tree_leaves.items():
        if subject in store:
            return name
    return None


def probe_set(wits: Dict[str, Any], n: int = 120) -> List[str]:
    """Subjects held by >=3 witnesses, sampled deterministically.

    >=3 so every probe has a band worth reading; deterministic stride
    instead of random.sample so the run is a measurement, not a dice roll.
    """
    counts: Dict[str, int] = {}
    for w in wits.values():
        for c in w.crosses:
            counts[c] = counts.get(c, 0) + 1
    shared = sorted(c for c, k in counts.items() if k >= 3)
    if len(shared) <= n:
        return shared
    stride = len(shared) // n
    return shared[::stride][:n]


def main(argv: Optional[List[str]] = None) -> int:
    from .export_sqlite import witnesses

    root = corpus_root()
    wits = witnesses(root / "build" / "vera.db")

    use_blocks = "--blocks" in (argv or sys.argv)
    trees: Dict[str, Node] = {}
    tree_leaves: Dict[str, Dict[str, Any]] = {}
    for wname, store in sorted(wits.items()):
        lv = (leaves_of(store.crosses) if use_blocks
              else document_leaves(root / "build" / "vera.db", wname))
        if not lv:
            lv = leaves_of(store.crosses)
        tree_leaves[wname] = lv
        trees[wname] = build(lv, name=f"root:{wname}")

    probes = probe_set(wits)
    correct = wrong = abstained = 0
    band_hist: Dict[str, int] = {}
    wrong_examples: List[Dict[str, str]] = []

    for subject in probes:
        holders = [w for w in trees if subject in wits[w].crosses]
        ok = 0
        for w in holders:
            r = descend(trees[w], subject)
            if r["verdict"] != "ROUTED":
                abstained += 1
                continue
            # Correct = the routed leaf HOLDS the subject. A shared word
            # legitimately lives in many documents; demanding one canonical
            # document made real routes count as wrong ("二人" routed to a
            # document that contains 二人 is not an error).
            if subject in tree_leaves[w].get(r["leaf"], {}):
                correct += 1
                ok += 1
            else:
                wrong += 1
                if len(wrong_examples) < 5:
                    wrong_examples.append({"subject": subject, "witness": w,
                                           "routed": r["leaf"],
                                           "held_in": leaf_holding(tree_leaves[w], subject) or "?"})
        key = f"{ok}/{len(holders)}"
        band_hist[key] = band_hist.get(key, 0) + 1

    fab_abstain = fab_routed = 0
    for term in FABRICATED:
        for w in trees:
            r = descend(trees[w], term)
            if r["verdict"] == "ROUTED":
                fab_routed += 1
            else:
                fab_abstain += 1

    total = correct + wrong + abstained
    full_band = sum(v for k, v in band_hist.items()
                    if k.split("/")[0] == k.split("/")[1] and k != "0/0")
    print(json.dumps({
        "verdict": "ANSWER",
        "trees": {w: {"leaves": len(tree_leaves[w]),
                      "crosses": len(wits[w].crosses)} for w in sorted(trees)},
        "probes": len(probes),
        "descents": {"correct": correct, "wrong": wrong,
                     "abstained": abstained, "of": total},
        "band_histogram": dict(sorted(band_hist.items())),
        "full_band_probes": full_band,
        "fabricated": {"abstained": fab_abstain, "routed_WRONG": fab_routed},
        "wrong_examples": wrong_examples,
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
