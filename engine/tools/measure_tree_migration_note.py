"""A NOTE beside 判定1 — never a criterion.

The registered contamination definition is 「SHOWNの面の facet_origin が
主題と別記事に属する答え」 — another ARTICLE. The tree separates by
DOMAIN (法令 / 法学 / 百科 / 多分野 / 指名), so a cross-article overlap
inside one domain (時効 shown from 時効.txt, 消滅時効.txt, 公訴時効.txt —
all 指名) is counted by the criterion and is untouchable by the tree.

That is a flaw in the metric, not in the tree, and it was registered
before anyone could see it. This script therefore reports the
domain-level count SEPARATELY. It decides nothing: 判定1 stands on the
number its own criterion produced. The purpose here is to give the next
registration something measured to stand on, per the pre-registration's
own amendment rule (struck-through additions with a reason, never a
rewrite).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from measure_tree_migration import BUILD, bank, shown_facets  # noqa: E402
from verantyx import conduct_tree  # noqa: E402
from verantyx.export_sqlite import vera as load_published  # noqa: E402
from verantyx.vera import Vera  # noqa: E402


def domains_of(out) -> set:
    origin = out.get("facet_origin") or {}
    doms = set()
    for facet in shown_facets(out):
        for label in (origin.get(facet) or []):
            d = str(label).partition("／")[0]
            if d:
                doms.add(d)
    return doms


def main() -> int:
    v = load_published(BUILD / "vera.db")
    leaves = dict(v.witnesses)
    root = conduct_tree.build({k: s.crosses for k, s in leaves.items()})
    leaf_vera = {}
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

    flat_multi = tree_multi = flat_ans = tree_ans = 0
    for terms in banks.values():
        for core in terms:
            q = core + "とは"
            fo = v.ask(q)
            if not str(fo.get("verdict", "")).startswith("UNKNOWN"):
                flat_ans += 1
                if len(domains_of(fo)) > 1:
                    flat_multi += 1
            r = conduct_tree.descend(root, core)
            if r.get("verdict") == "ROUTED":
                to = leaf_vera[r["leaf"]].ask(q)
                if not str(to.get("verdict", "")).startswith("UNKNOWN"):
                    tree_ans += 1
                    if len(domains_of(to)) > 1:
                        tree_multi += 1

    print(json.dumps({
        "note": "domain-level contamination; decides nothing",
        "flat_answered": flat_ans, "flat_multi_domain": flat_multi,
        "tree_answered": tree_ans, "tree_multi_domain": tree_multi,
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
