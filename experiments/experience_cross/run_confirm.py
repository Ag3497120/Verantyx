# -*- coding: utf-8 -*-
"""確認測定 — PREREG.md が事前登録。経験十字。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verantyx.experience import compile_view
from verantyx.experience_cross import contested, pour, reevaluate_math_gaps


def main():
    t0 = time.time()
    v = compile_view()
    res = {"view_rows": v["n_rows"], "view_counts": v["counts"]}

    # ① 注ぎ込み + 分布
    p1 = pour(v)
    st = p1["store"]
    res["poured"] = p1["poured"]
    res["untagged"] = p1["untagged"]
    arm_totals = {}
    for slot in p1["arms"].values():
        for arm, fs in slot.items():
            arm_totals[arm] = arm_totals.get(arm, 0) + len(fs)
    res["arm_totals"] = arm_totals
    res["store"] = {"cores": st.n_cores(), "links": st.n_facet_links()}

    # ② 実データの contested + 合成矛盾対の検出
    real_contested = contested(st, p1["arms"])
    res["contested_real"] = {"n": len(real_contested),
                             "sample": real_contested[:5]}
    from verantyx.cross_store import CrossStore
    syn = CrossStore(track_provenance=True)
    syn.add("合成主題", ["結果:proved", "支持:verified:test"], source="t1")
    syn.add("合成主題", ["結果:refuted", "反論:反例あり"], source="t2")
    syn_c = syn.contradictions("合成主題")
    res["contested_synthetic"] = {
        "detected": any(c["key"] == "結果" for c in syn_c),
        "detail": syn_c}

    # ④ 順序: 逆順で注いで facet 集合が同一か
    v_rev = dict(v)
    v_rev["rows"] = list(reversed(v["rows"]))
    p2 = pour(v_rev)
    same = ({c: set(f) for c, f in st.crosses.items()} ==
            {c: set(f) for c, f in p2["store"].crosses.items()})
    res["order_invariant"] = same

    # ① 後半: GAP再評価 — proof_ledger4 時点の open 数学Gap(B1/B10含む)
    base = Path(__file__).resolve().parents[1] / "cross_energy_prover"
    from verantyx.experience import _rows_from_gaps
    gap_rows = []
    for name in ("proof_ledger.gaps.json",      # 確認4時点(B1/B10 open)
                 "proof_ledger14.gaps.json"):   # 確認14時点(M束・F束)
        gap_rows += [r for r in _rows_from_gaps(base / name)
                     if r["state"] == "GAP"]
    res["gap_input"] = [r["subject"] for r in gap_rows]
    reev = reevaluate_math_gaps(st, gap_rows)
    res["reevaluation"] = reev

    # ⑤ counts 整合(注げた行 + 未タグ = view の行数)
    res["counts_consistent"] = (p1["poured"] + p1["untagged"]
                                == v["n_rows"])
    res["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    Path(__file__).with_name("results.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")


if __name__ == "__main__":
    main()
