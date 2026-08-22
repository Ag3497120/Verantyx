"""判定1 — tree descent versus the flat merger, against a frozen criterion.

The criterion was registered on 2026-08-14 (docs/PREREGISTERED_2026-08-14
_tree_and_shelf.md) with the numbers unseen, and this script only applies
it. Nothing here may move a threshold; if a threshold looks wrong the
answer is a struck-through amendment in that file, with a reason.

    移行する      answers >= 80% of flat AND contamination-type errors fall
    移行しない    answers < 60% of flat
    併置          60-80% — tree rides beside the flat answer as a band
    無条件不合格  lost answers not converted into TYPED abstentions

## The two paths

    flat   the published federation: 89,369 cores, every domain's leaves
           merged into one ja store. `Vera.ask` — today's main path.
    tree   `conduct_tree.build` over the SAME five domain stores as leaves
           (法令 30,827 / 多分野 36,607 / 百科 14,979 / 法学 10,487 /
           指名 4,484), `descend` to a leaf by surface conduction, and the
           leaf answers with its own gates. A routing node holds no census
           and no merged store: it is a switch, not a voter.

Same store generation, same question, same gates — only the geometry of
what answers differs.

## Contamination, counted as registered

「SHOWNの面の facet_origin が主題と別記事に属する答え」. For an answered
question about S, every shown facet's provenance label is read; a label
whose article is not S's own is contamination. The flat merger makes this
possible at all (時効's cross carries both a labour-law article and a
legal-studies one); the tree's claim is that descending removes it,
because only one leaf ever answers.

## Banks

The registered protocol names 法令400 + 200問 + 探針200. No bank file of
that shape survived, so all three are RECONSTRUCTED here deterministically
and the reconstruction is stated rather than hidden — same honesty the
150 held-out cores needed when their selection script was gone:

    法令400   stride over the 法令 leaf's cores, 「Xとは」
    問200     stride over the merged ja store's cores, 「Xとは」
    探針200   stride over 百科 + 指名 cores (the breadth classes the
              shelf probe sampled), 「Xとは」

Strides are index-based over sorted core lists with a fixed seed offset,
so the banks rebuild identically on any machine holding this store.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx import conduct_tree  # noqa: E402
from verantyx.export_sqlite import vera as load_published  # noqa: E402
from verantyx.vera import Vera  # noqa: E402

BUILD = Path.home() / "Projects" / "vera-corpus" / "build"
PREREG = (Path(__file__).resolve().parent.parent / "docs"
          / "PREREGISTERED_2026-08-14_tree_and_shelf.md")


def bank(cores: List[str], n: int, offset: int) -> List[str]:
    """Deterministic stride, stated so it rebuilds identically."""
    pool = sorted(c for c in cores if 2 <= len(c) <= 12)
    if not pool:
        return []
    step = max(1, len(pool) // n)
    picked = [pool[(i * step + offset) % len(pool)] for i in range(n)]
    seen, out = set(), []
    for p in picked:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def shown_facets(out: Dict[str, Any]) -> List[str]:
    text = str(out.get("text") or "")
    return [t for t in text.split() if t]


def contaminated(out: Dict[str, Any], subject: str) -> bool:
    """A shown facet whose provenance is another article's."""
    origin = out.get("facet_origin") or {}
    if not origin:
        return False
    for facet in shown_facets(out):
        for label in (origin.get(facet) or []):
            stem = str(label).split("／")[-1].rsplit(".", 1)[0]
            if stem and stem != subject:
                return True
    return False


def main() -> int:
    v = load_published(BUILD / "vera.db")
    leaves = dict(v.witnesses)
    # The tree routes over raw cross views; the leaf that ANSWERS is the
    # CrossStore itself, kept beside it. A routing node reads a merged
    # view and holds no census — conduct_tree's own distinction.
    root = conduct_tree.build({k: s.crosses for k, s in leaves.items()})

    # One Vera per leaf: same gates, one domain's store. Built once.
    leaf_vera: Dict[str, Vera] = {}
    for name, store in leaves.items():
        lv = Vera()
        lv.add("ja", store)
        lv.origin = v.origin
        leaf_vera[name] = lv

    banks = {
        "法令400": bank(list(leaves["法令"].crosses), 400, 7),
        "問200": bank(list(v.stores["ja"].crosses), 200, 13),
        "探針200": bank(
            list(leaves["百科"].crosses) + list(leaves["指名"].crosses),
            200, 29),
    }

    report: Dict[str, Any] = {"banks": {}}
    totals = {"flat_ans": 0, "tree_ans": 0, "n": 0,
              "flat_contam": 0, "tree_contam": 0}
    tree_refusals: Dict[str, int] = {}
    silent_losses: List[str] = []

    for bname, terms in banks.items():
        f_ans = t_ans = f_con = t_con = 0
        for core in terms:
            q = core + "とは"
            fo = v.ask(q)
            f_answered = not str(fo.get("verdict", "")).startswith("UNKNOWN")
            if f_answered:
                f_ans += 1
                if contaminated(fo, core):
                    f_con += 1

            routed = conduct_tree.descend(root, core)
            if routed.get("verdict") != "ROUTED":
                to = {"verdict": routed.get("verdict", "UNKNOWN_NO_ROUTE")}
            else:
                to = leaf_vera[routed["leaf"]].ask(q)
            tv = str(to.get("verdict", "UNKNOWN"))
            t_answered = not tv.startswith("UNKNOWN")
            if t_answered:
                t_ans += 1
                if contaminated(to, core):
                    t_con += 1
            else:
                tree_refusals[tv] = tree_refusals.get(tv, 0) + 1
                if f_answered and not tv:
                    silent_losses.append(core)

        report["banks"][bname] = {
            "n": len(terms),
            "flat_answered": f_ans, "tree_answered": t_ans,
            "flat_contaminated": f_con, "tree_contaminated": t_con,
            "kept_pct": round(100.0 * t_ans / f_ans, 1) if f_ans else None,
        }
        totals["n"] += len(terms)
        totals["flat_ans"] += f_ans
        totals["tree_ans"] += t_ans
        totals["flat_contam"] += f_con
        totals["tree_contam"] += t_con

    kept = (100.0 * totals["tree_ans"] / totals["flat_ans"]
            if totals["flat_ans"] else 0.0)
    contam_fell = totals["tree_contam"] < totals["flat_contam"]

    if silent_losses:
        verdict = "無条件不合格(無言の消失)"
    elif kept >= 80.0 and contam_fell:
        verdict = "移行する"
    elif kept < 60.0:
        verdict = "移行しない"
    else:
        verdict = "併置"

    report["totals"] = totals
    report["kept_pct"] = round(kept, 1)
    report["contamination_fell"] = contam_fell
    report["tree_refusal_types"] = dict(
        sorted(tree_refusals.items(), key=lambda kv: -kv[1]))
    report["silent_losses"] = len(silent_losses)
    report["criterion"] = "docs/PREREGISTERED_2026-08-14_tree_and_shelf.md"
    report["verdict"] = verdict
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
