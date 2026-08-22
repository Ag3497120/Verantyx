"""転移の読む層 — transfer_outcomes が意図的に保留した較正段。

そのモジュールの docstring が穴を自分で名指していた:

    This module deliberately does ONLY the recording. No calibration
    analysis ... those need real accumulated data to be anything but a
    guess, and were explicitly agreed to be a later step once this log
    has something in it.

2026-08-20、実データが出た(harness_facts: 3モデル×3変分の採否)。

## 機械が言えること / 言ってはいけないこと

言えるのは**転移したかどうか**だけ: 同じ事実が複数の文脈で観測され、
判定が全て一致すれば TRANSFERRED、割れれば CONTEXT_BOUND、
1文脈しか無ければ UNKNOWN_SINGLE_CONTEXT(予測しない)。

言ってはいけないのは**なぜ転移したか**。「情報構造に根ざすから転移した」
「モデルの癖だから転移しなかった」は人の仮説で、それ自体が証拠を要する
主張である。台帳は仮説を運ぶが、この器官は生成しない — 「record first,
judge later」を、判断の側でも守る。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

#: 事実名の正規化(閉じた規則)。同じ事実が測定ごとに違う名前で書かれた
#: — 「hretry(f,3) が成功を増やす」と「hretry(f,3)」は同一。ハーネス項
#: (括弧つきの呼び名)を鍵にし、残りは説明として捨てる。捨てた分は
#: raw_names に残す(写像が読者に見えること)。
_TERM = re.compile(r"[a-z_]+\([^)]*\)")

#: 判定の同値類。ラベルの揺れ(HARMFUL と HARMFUL_UNSTABLE)は
#: 「採る/採らない/害」の三値に畳む — 揺れたことは note に残す。
_CLASS = {"ADOPTED": "adopt", "ABSTAIN": "abstain",
          "ABSTAIN(天井)": "abstain", "HARMFUL": "harm",
          "HARMFUL_UNSTABLE": "harm"}

#: 較正に数字を出す最低文脈数。これ未満は数えない(同点棄権の系譜)。
MIN_CONTEXTS = 2


def normalize_fact(name: str) -> str:
    """事実名 → ハーネス項の鍵。項が無ければ元の名前(切り詰め)。"""
    m = _TERM.search(name or "")
    if not m:
        return (name or "").strip()[:60]
    key = m.group(0)
    # 「は害」のような判定語は名前に含めない — 判定は verdict 側の仕事
    return key


def _classify(verdict: str) -> Optional[str]:
    v = (verdict or "").strip()
    if v in _CLASS:
        return _CLASS[v]
    for k, c in _CLASS.items():
        if v.startswith(k.split("(")[0]):
            return c
    return None


def unify(facts_paths: Optional[List[Path]] = None) -> Dict[str, Any]:
    """観測を「事実 × 文脈 → 判定」に畳む。元のファイルは読むだけ。"""
    paths = facts_paths or [
        Path(__file__).resolve().parent.parent / "experiments"
        / "harness_algebra" / "harness_facts.json"]
    table: Dict[str, Dict[str, Any]] = {}
    for p in paths:
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        conditions = d.get("conditions", {})
        for f in d.get("facts", []):
            key = normalize_fact(str(f.get("fact", "")))
            cls = _classify(str(f.get("verdict", "")))
            if not key or cls is None:
                continue
            slot = table.setdefault(key, {"fact": key, "raw_names": [],
                                          "contexts": {}, "labels": {},
                                          "conditions": conditions,
                                          "source": str(p)})
            raw = str(f.get("fact", ""))
            if raw not in slot["raw_names"]:
                slot["raw_names"].append(raw)
            # 文脈は**モデルだけではない**。2026-08-21 実測: 課題集合を
            # 難しくしたら、easy24 で 0.5B 限定だった採択が3モデルとも
            # 一致に変わり、htrunc(f,400) は採択→害へ反転した。同じ
            # ハーネス項が課題分布で逆の評価になる — 版を鍵に含めないと、
            # 台帳は害になる規則を「効く」として手渡すことになる。
            ctx = str(f.get("model", "?"))
            battery = f.get("battery")
            if battery:
                ctx = f"{ctx}@{battery}"
            slot["contexts"][ctx] = cls
            slot["labels"].setdefault(ctx, []).append(
                str(f.get("verdict", "")))
    return {"facts": table, "n_facts": len(table),
            "sources": [str(p) for p in paths if p.exists()]}


def judge_transfer(slot: Dict[str, Any]) -> Dict[str, Any]:
    """一つの事実について、転移したかを**数えるだけ**で決める。"""
    ctxs = slot["contexts"]
    classes = set(ctxs.values())
    if len(ctxs) < MIN_CONTEXTS:
        verdict = "UNKNOWN_SINGLE_CONTEXT"
        note = ("観測が1文脈しかない — 転移するかは、まだ言えない"
                "(予測しない)")
    elif len(classes) == 1:
        verdict = "TRANSFERRED"
        note = f"{len(ctxs)}文脈すべてで判定が一致した"
    else:
        verdict = "CONTEXT_BOUND"
        note = "文脈によって判定が割れた — この事実は文脈に縛られる"
    # ラベルの揺れ(同じ三値だが名前が違う)は隠さない
    wobble = {c: ls for c, ls in slot["labels"].items() if len(set(ls)) > 1}
    return {"fact": slot["fact"], "verdict": verdict,
            "contexts": dict(ctxs), "n_contexts": len(ctxs),
            "note": note, "raw_names": slot["raw_names"],
            "label_wobble": wobble or None, "source": slot["source"]}


def calibrate(rows: List[Dict[str, Any]],
              hypotheses: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """次元ごとの転移を**数える**。閾値未満は数字を出さない。

    `hypotheses` は 事実→次元 の**人の仮説**。無ければ次元なしで数える。
    この関数は仮説を生成しない — なぜ転移したかは別種の主張。
    """
    hyp = hypotheses or {}
    by_dim: Dict[str, Dict[str, int]] = {}
    for r in rows:
        dim = hyp.get(r["fact"], "(仮説なし)")
        slot = by_dim.setdefault(dim, {"TRANSFERRED": 0, "CONTEXT_BOUND": 0,
                                       "UNKNOWN_SINGLE_CONTEXT": 0})
        slot[r["verdict"]] = slot.get(r["verdict"], 0) + 1
    out = {}
    for dim, counts in by_dim.items():
        n = counts["TRANSFERRED"] + counts["CONTEXT_BOUND"]
        if n < MIN_CONTEXTS:
            out[dim] = {"verdict": "UNKNOWN_TOO_FEW_CONTEXTS",
                        "observations": n, "min": MIN_CONTEXTS,
                        "counts": counts,
                        "note": "観測が少なすぎる — 数字は出さない"}
        else:
            out[dim] = {"verdict": "COUNTED", "observations": n,
                        "counts": counts,
                        "note": "この観測でこう出た、という記録 — "
                                "予測ではない"}
    return out


def check_claimed_transfers(rows: List[Dict[str, Any]],
                            claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """「転移する」と書かれた主張を、実観測と突き合わせる。

    主張が観測と食い違えば CONTRADICTED(どの文脈が割れたかを名指す)。
    """
    index = {r["fact"]: r for r in rows}
    out = []
    for c in claims:
        key = normalize_fact(str(c.get("fact", "")))
        claimed = str(c.get("claims", "")).upper()
        obs = index.get(key)
        if obs is None:
            out.append({"fact": key, "verdict": "UNKNOWN_NOT_OBSERVED",
                        "claimed": claimed})
            continue
        if claimed and claimed != obs["verdict"]:
            out.append({"fact": key, "verdict": "CONTRADICTED",
                        "claimed": claimed, "observed": obs["verdict"],
                        "contexts": obs["contexts"],
                        "note": "主張と観測が食い違う — 観測が名指す"})
        else:
            out.append({"fact": key, "verdict": "CONSISTENT",
                        "claimed": claimed, "observed": obs["verdict"]})
    return out


def read(hypotheses: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """入口: 統合 → 事実ごとの転移判定 → 次元ごとの較正。"""
    u = unify()
    rows = [judge_transfer(s) for s in u["facts"].values()]
    rows.sort(key=lambda r: r["fact"])
    return {"votes": "none",
            "note": "機械は転移を報告する。なぜ転移したかは主張しない",
            "n_facts": len(rows), "sources": u["sources"],
            "facts": rows, "calibration": calibrate(rows, hypotheses)}
