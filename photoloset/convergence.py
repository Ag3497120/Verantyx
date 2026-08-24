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
          history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """現在の状態を数え、収束したか・停滞しているかを返す。"""
    counters: Dict[str, int] = {
        "open_ports": 0, "contested": 0, "unknown": 0,
        "not_sewable": 0, "failed_checks": 0,
    }
    details: Dict[str, Any] = {}

    if draft.get("verdict") != "ANSWER":
        counters["unknown"] = 1
        details["refusal"] = draft.get("verdict")
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
    escalate = False
    if history is not None:
        history.append({"counters": dict(counters)})
        same = 0
        for prev in reversed(history[:-1]):
            if prev.get("counters") == counters:
                same += 1
            else:
                break
        if total > 0 and same + 1 >= STAGNATION_LIMIT:
            escalate = True
            verdict = ESCALATE

    return {"verdict": verdict, "counters": counters,
            "total_open": total, "details": details,
            "stagnation_limit": STAGNATION_LIMIT,
            "why_escalate": ("同じ状態が許容回数繰り返されました。"
                             "人に決めてもらう項目があります"
                             if escalate else None)}
