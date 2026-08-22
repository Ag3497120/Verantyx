# -*- coding: utf-8 -*-
"""確認測定 — PREREG.md が事前登録。転移の読む層。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verantyx.transfer_reading import (MIN_CONTEXTS, calibrate,
                                       check_claimed_transfers, judge_transfer,
                                       normalize_fact, read, unify)

#: 人の仮説(機械は生成しない)。今日の読み: 情報構造に根ざす事実は
#: 転移し、モデルの癖に根ざす事実は転移しない。**これは主張であり、
#: 台帳は仮説として運ぶだけ**。
HYPOTHESES = {
    "htrunc(f,64)": "情報構造由来(質問ごと切る)",
    "hretry(f,3)": "モデル能力由来(弱さの補償)",
    "htrunc(f,400)": "モデル能力由来(弱さの補償)",
}


def main():
    t0 = time.time()
    res = {}
    r = read(HYPOTHESES)
    res["facts"] = [{k: f[k] for k in ("fact", "verdict", "contexts",
                                       "n_contexts", "raw_names")}
                    for f in r["facts"]]

    # L1: 実測と一致するか(手検算できる形で)
    want = {"htrunc(f,64)": "TRANSFERRED",
            "hretry(f,3)": "CONTEXT_BOUND",
            "htrunc(f,400)": "CONTEXT_BOUND"}
    got = {f["fact"]: f["verdict"] for f in r["facts"]}
    res["L1"] = {"want": want, "got": got, "ok": got == want,
                 "facts_folded": f"{sum(len(f['contexts']) for f in r['facts'])}観測 → {r['n_facts']}事実"}

    # L2: 合成の偽転移主張を検出
    claims = [
        {"fact": "hretry(f,3) は転移する", "claims": "TRANSFERRED"},
        {"fact": "htrunc(f,64)", "claims": "TRANSFERRED"},
        {"fact": "hpar(f,2)", "claims": "TRANSFERRED"},
    ]
    checked = check_claimed_transfers(r["facts"], claims)
    res["L2"] = checked
    res["L2_ok"] = (checked[0]["verdict"] == "CONTRADICTED"
                    and checked[1]["verdict"] == "CONSISTENT"
                    and checked[2]["verdict"] == "UNKNOWN_NOT_OBSERVED")

    # L3: 1文脈の事実は予測しない / 閾値未満の次元は数字を出さない
    single = judge_transfer({"fact": "hsys(f)", "raw_names": ["hsys(f)"],
                             "contexts": {"only-model": "adopt"},
                             "labels": {"only-model": ["ADOPTED"]},
                             "source": "synthetic"})
    thin = calibrate([single], {"hsys(f)": "未知の次元"})
    res["L3"] = {"single_context": single["verdict"],
                 "thin_dimension": thin["未知の次元"]["verdict"],
                 "min_contexts": MIN_CONTEXTS}
    res["L3_ok"] = (single["verdict"] == "UNKNOWN_SINGLE_CONTEXT"
                    and thin["未知の次元"]["verdict"]
                    == "UNKNOWN_TOO_FEW_CONTEXTS"
                    and "counts" in thin["未知の次元"])

    # L4: 読み込み順を反転しても較正が一致
    u = unify()
    rows_rev = [judge_transfer(s) for s in reversed(list(u["facts"].values()))]
    cal_rev = calibrate(rows_rev, HYPOTHESES)
    res["L4"] = {"forward": r["calibration"], "reversed": cal_rev}
    res["L4_ok"] = r["calibration"] == cal_rev

    # L5: 生データと突合(第三者が手で数えられること)
    src = Path(__file__).resolve().parents[1] / "harness_algebra" \
        / "harness_facts.json"
    raw = json.loads(src.read_text(encoding="utf-8"))
    # 文脈鍵は model@battery(2026-08-21、課題集合も文脈と判明した後)。
    # 検査側が古い鍵のままだと、実装ではなく検査が落ちる — 一度そうなった。
    counted = {}
    for f in raw["facts"]:
        key = normalize_fact(str(f.get("fact", "")))
        ctx = str(f.get("model"))
        if f.get("battery"):
            ctx = f"{ctx}@{f['battery']}"
        counted.setdefault(key, set()).add(ctx)
    res["L5"] = {k: sorted(v) for k, v in counted.items()}
    res["L5_ok"] = all(
        set(res["L5"].get(f["fact"], [])) == set(f["contexts"])
        for f in r["facts"])

    res["calibration"] = r["calibration"]
    res["all_pass"] = all([res["L1"]["ok"], res["L2_ok"], res["L3_ok"],
                           res["L4_ok"], res["L5_ok"]])
    res["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    Path(__file__).with_name("results.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")


if __name__ == "__main__":
    main()
