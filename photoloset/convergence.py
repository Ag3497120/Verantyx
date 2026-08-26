# -*- coding: utf-8 -*-
"""収束監視。**ループは AI だけだと終わらない。** ここが終わりを決める。

Vera-a(監視役)に渡す状態を、構造から数える:

- 開いた接続口(組立ての門が断っているなら 0、断り自体が未決)
- 寸法の割れ(CONTESTED)
- 未解決の拒否(draft が ANSWER でない)
- 縫えない接続(seam_checks の差が許容外)
- 物理の検査落ち(order/starts/seam_closed)

**同じ状態が繰り返されたら人へ。** 収束しないループを回し続けるのは、
進歩の捏造です。履歴の中で状態が N 回変わらなければ ESCALATE。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

CONVERGED = "CONVERGED"
IN_PROGRESS = "IN_PROGRESS"
ESCALATE = "ESCALATE_HUMAN"

#: 同じ状態の許容回数。これを超えたら人へ。
STAGNATION_LIMIT = 3


def check(draft: Dict[str, Any], *,
          measures: Optional[Any] = None,
          sew: Optional[Dict[str, Any]] = None,
          rejected: Optional[List[str]] = None,
          history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """現在の状態を数え、収束したか・停滞しているかを返す。

    ``rejected`` は確認シートで人が ``no`` と答えた claim の id。**これを
    数えないと、他の全部が 0 の周回で total==0 になり、人が拒否し続けて
    いる服を CONVERGED と報告する。**
    """
    counters: Dict[str, int] = {
        "open_ports": 0, "contested": 0, "unknown": 0,
        "not_sewable": 0, "failed_checks": 0, "rejected_claims": 0,
    }
    details: Dict[str, Any] = {}

    rejected_ids = sorted({str(x) for x in (rejected or [])})
    counters["rejected_claims"] = len(rejected_ids)
    if rejected_ids:
        details["rejected_claims"] = rejected_ids

    if draft.get("verdict") != "ANSWER":
        counters["unknown"] = 1
        details["refusal"] = draft.get("verdict")
        details["which"] = draft.get("which")
        if draft.get("verdict") == "UNKNOWN_OPEN_PORT":
            counters["open_ports"] = len(draft.get("open", []))
    else:
        bad = [c for c in draft.get("seam_checks", [])
               if not c.get("sewable", True)]
        counters["not_sewable"] = len(bad)
        if bad:
            details["not_sewable"] = [c["label"] for c in bad]

    if measures is not None:
        try:
            contested = [r["spot"] for r in measures.sheet().get(
                "contested", [])]
        except Exception:
            contested = []
        counters["contested"] = len(contested)
        if contested:
            details["contested"] = contested

    if sew is not None:
        checks = sew.get("checks", {})
        failed = [k for k, v in checks.items() if v.get("verdict") != "ANSWER"]
        counters["failed_checks"] = len(failed)
        if failed:
            details["failed_checks"] = failed

    total = sum(counters.values())
    verdict = CONVERGED if total == 0 else IN_PROGRESS

    # **停滞の検出。** 履歴は呼び側が持つ(監視役の記帳)。
    # 拒否された claim の **id まで**比べる — 毎周回で違う claim が
    # 直っているなら、それは進んでいる。同じ claim を三度拒否されるのが
    # 「もう直らない」の形です。
    escalate = False
    if history is not None:
        history.append({"counters": dict(counters), "rejected": rejected_ids})
        same = 0
        for prev in reversed(history[:-1]):
            if (prev.get("counters") == counters
                    and prev.get("rejected", []) == rejected_ids):
                same += 1
            else:
                break
        if total > 0 and same + 1 >= STAGNATION_LIMIT:
            escalate = True
            verdict = ESCALATE

    return {"verdict": verdict, "counters": counters,
            "total_open": total, "details": details,
            "stagnation_limit": STAGNATION_LIMIT,
            "why_escalate": _why(escalate, counters, details)}


def _why(escalate: bool, counters: Dict[str, int],
         details: Dict[str, Any]) -> Optional[str]:
    """**「もう一度やってみて」とは言わない。** 何が動いていないかを言う。

    同じ状態が繰り返されているとき、その状態の中身は既に分かっている:
    引けない部品なら手続きが無いのだし、拒否された claim なら検索が
    その部品を当てられていない。当てられない理由まではここでは言えない
    ので、**次に人がどこを触るか**だけを名指しする。
    """
    if not escalate:
        return None
    refusal = details.get("refusal")
    if refusal in ("UNKNOWN_NO_SUCH_PART", "UNKNOWN_PART_NOT_DRAFTABLE"):
        which = details.get("which")
        return (f"{which} を引く手続きがありません。"
                f"garment_parts に手続きを書き、parts.PART_GEOMETRY に"
                f"登録するまで、この周回は何度回しても同じ所で止まります")
    if counters.get("rejected_claims"):
        ids = details.get("rejected_claims", [])
        return (f"同じ主張 {ids} が繰り返し拒否されています。"
                f"検索はこの部品を当てられていません。"
                f"人がその部品を直接宣言するか、別の出典を足してください")
    if counters.get("open_ports"):
        return ("同じ接続口が開いたままです。"
                "写真に写っていない面は、人が決めるまで閉じません")
    if counters.get("contested"):
        return (f"寸法が {details.get('contested')} で割れたままです。"
                f"どちらが正しいかはこの装置では決めません")
    return ("同じ状態が許容回数繰り返されました。"
            "人に決めてもらう項目があります")
