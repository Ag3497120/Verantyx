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

``check()`` は一枚の draft を数える。``loop()`` はその一段上 —
``cross.CrossStore`` を住所空間として、revision の一周がその空間に対して
何をしたかで終わりを決める(``mcp.garment_revision_loop`` が呼ぶ)。
どちらも同じ ``STAGNATION_LIMIT``/``history`` の約束を共有する。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .cross import CONTESTED_IN_CROSS, ORDER_DEPENDENT, CrossStore, ingest_order_check
from .garment import OBSERVED, CONTESTED as LEDGER_CONTESTED, Ledger

CONVERGED = "CONVERGED"
IN_PROGRESS = "IN_PROGRESS"
ESCALATE = "ESCALATE_HUMAN"

#: 同じ状態の許容回数。これを超えたら人へ。
STAGNATION_LIMIT = 3

#: ``loop()`` が返す追加の終わり方。CONVERGED / ESCALATE は上と共有する
#: (呼び側が二つの語彙を覚えずに済むように)。
CONTESTED = "CONTESTED"
CONTINUE = "CONTINUE"


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


# ---------------------------------------------------------------------------
# loop() — 収束をストアに繋ぐ
# ---------------------------------------------------------------------------
#
# ``check()`` は「今の状態がどう見えるか」を数える。ここから先は「一周分の
# revision をストアに通したら、次に何が起きるべきか」を決める側で、判定は
# 停滞のカウンタではなく **住所空間の構造** から来る:
#
#   新しい住所に着地      -> CONTINUE   (住所空間は有限で、まだ席がある)
#   既にある値に同意      -> CONVERGED  (不動点。もう一周要らない)
#   既にある値と食い違う  -> CONTESTED  (終端。両方残し、人に聞く)
#   格納順で答えが動く    -> UNKNOWN_ORDER_DEPENDENT (終端。構造の欠陥)
#   ADOPTED 住所を別の値で再提案 -> Ledger.adopt を通す。名前が無ければ
#                                    その revision だけが REOPEN_BLOCKED
#
# **これは主張であって定理ではない。** 「合意は不動点」「矛盾は終端」が
# 本当にループを止めるという証明はここには無い — 確かめられるのは、この
# 装置が各節を個別に測れる形にしたということだけ。停滞(同じ却下が
# STAGNATION_LIMIT 回続く)は ``check()`` に**そのまま**渡す — 書き直さない。


def _rev_id(rev: Dict[str, Any], i: int) -> str:
    rid = rev.get("id")
    if rid:
        return str(rid)
    return f'{rev.get("core")}:{rev.get("key")}:{i}'


def loop(revisions: Sequence[Dict[str, Any]], store: CrossStore, *,
         ledger: Optional[Ledger] = None,
         history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """revision を一周ぶんストアへ通し、CONVERGED/CONTESTED/ESCALATE_HUMAN/
    CONTINUE のどれで終わるかを、理由と現在のカウンタ状態つきで返す。

    ``revisions`` は ``{"core", "key", "value", "kind", "source", "by",
    "id"}`` の並び。``core``/``key`` が住所、``by`` は ADOPTED 住所を
    別の値で再提案するときだけ要る採用者名(``Ledger.adopt`` が検査する)。

    ``store`` と ``ledger`` は **呼び側が持ち、周をまたいで同じものを渡す**
    — ``check()`` の ``history`` と同じ約束。ここで毎回新しく建てると、
    「既にある値」も「ADOPTED」もこの一周しか見えなくなる。

    書き口は常に ``store.put()``(分ける方)。``put_strict`` は cross.py
    自身が「分けない書き口を ingest に使ってはいけない」と言っている
    ものなので、ここでは選ばせない。
    """
    ledger = ledger if ledger is not None else Ledger()
    history = history if history is not None else []
    revisions = list(revisions or [])

    results: List[Dict[str, Any]] = []
    rejected_ids: List[str] = []
    new_addresses: List[str] = []
    contested: List[Dict[str, Any]] = []
    signed_overrides: List[Dict[str, Any]] = []

    for i, rev in enumerate(revisions):
        rid = _rev_id(rev, i)
        core, key = rev.get("core"), rev.get("key")
        if not isinstance(core, str) or not core or not isinstance(key, str) or not key:
            results.append({"id": rid, "status": "UNKNOWN_BAD_REVISION",
                            "why": "revision には文字列の core と key が要る"})
            rejected_ids.append(rid)
            continue
        value, kind = rev.get("value"), rev.get("kind")
        source = str(rev.get("source") or "")
        by = str(rev.get("by") or "")

        # **ADOPTED 住所の再オープン。** 台帳に、この住所の採用済みの値が
        # あり、それが今回の値と違うなら、書く前に採用を通す。台帳の
        # ``adopt`` が空の名前を UNKNOWN_NO_ADOPTER で断る — ここでは
        # その断りを潰さず、この revision だけを REOPEN_BLOCKED にする。
        #
        # **OBSERVED だけでなく CONTESTED も見る。** 一度目の再オープンが
        # 通ると、台帳には元の値と採用された新しい値の二本の観測が並び、
        # ``Ledger.state`` は CONTESTED を返すようになる — ADOPTED状態が
        # 消えたのではなく、単に別の観測がもう一本積まれただけなのに、
        # ゲートが ``state == OBSERVED`` だけを見ていると二度目の再
        # オープンから無条件で通ってしまう(実測で見つかった欠陥)。
        # ``Ledger.state`` は CONTESTED でも直近に採用された行の
        # ``adopted_by``/``adopted_value`` を運ぶので、ここではその二つを
        # 状態に関わらず読む。
        reopened_by = ""
        prior = ledger.state(core, key)
        if prior["state"] == OBSERVED:
            prior_adopted_value = prior.get("value")
        elif prior["state"] == LEDGER_CONTESTED:
            prior_adopted_value = prior.get("adopted_value")
        else:
            prior_adopted_value = None
        if (prior.get("adopted_by") and prior_adopted_value is not None
                and str(prior_adopted_value) != str(value)):
            try:
                ledger.propose(core, key, str(value), source or rid)
                reopened = ledger.adopt(core, key, str(value), by=by)
            except ValueError as exc:
                results.append({"id": rid, "status": "REOPEN_BLOCKED",
                                "core": core, "key": key,
                                "adopted_value": prior_adopted_value,
                                "proposed_value": value,
                                "why": str(exc)})
                rejected_ids.append(rid)
                continue
            if reopened is None:
                # 採用者名はあったが、対になる未採用の提案が見つからな
                # かった (``propose`` は同じ提案の重複を積まない道はある
                # が、通常はここに来ない — 手で組んだ台帳だけの経路)。
                results.append({"id": rid, "status": "REOPEN_BLOCKED",
                                "core": core, "key": key,
                                "why": "採用できる提案が見つからなかった"})
                rejected_ids.append(rid)
                continue
            # 再採用が通ったので、下のストア書き込みへ続ける。同じ
            # revision に二つの結果行を作らない — ``reopened_by`` を
            # 最終行に乗せる。
            reopened_by = reopened.adopted_by

        r = store.put(core, key, value, kind, source)
        if r["verdict"] == CONTESTED_IN_CROSS:
            if reopened_by:
                # **署名は店の記録を書き換えない。** store は今後も両方の
                # 値を ``resolve()`` に出し続ける — それが cross.py の
                # 約束 ("外から一方を書き換えて CONTESTED を ANSWER に戻せ
                # ない")。ここで変わるのは店ではなく **この周が続くかどうか
                # だけ**: 生の証拠は割れたままでも、どちらの値に人が
                # 署名したかは台帳が持つので、この周は止まらない。
                signed_overrides.append(dict(r, id=rid, adopted_by=reopened_by))
                results.append({"id": rid, "status": "REOPENED_OVER_CONTEST",
                                "reopened_by": reopened_by, **r})
                continue
            contested.append(dict(r, id=rid))
            rejected_ids.append(rid)
            results.append({"id": rid, "status": "CONTESTED",
                            "reopened_by": reopened_by, **r})
            continue
        if r["verdict"] != "ANSWER":
            results.append({"id": rid, "status": "REFUSED",
                            "reopened_by": reopened_by, **r})
            rejected_ids.append(rid)
            continue

        # **plain ANSWER はまだ「合意した」ではない。** ``store.put`` の
        # exact-match 枝(同じ値・同じ種別が既に座席にある)は ANSWER を
        # 返す — その席が「他の値とも同時に割れている(CONTESTED_IN_CROSS)」
        # 状態でもだ。ここで ``store.resolve`` を引かずに ANSWER をそのまま
        # AGREES/CONVERGED と読むと、既に割れているアドレスへ片方の値を
        # 再提出するだけで「不動点」と静かに言えてしまう(実測で見つかった
        # 欠陥 — 生の証拠は割れたままなのに、この一周の判定だけが動く)。
        # 署名済みの再オープンと同じ扱いにする: 生の証拠は書き換えない、
        # 動くのはこの周が続くかどうかだけ。
        resolved = store.resolve(core, key)
        if resolved["verdict"] == CONTESTED_IN_CROSS:
            if reopened_by:
                signed_overrides.append(dict(r, id=rid, adopted_by=reopened_by,
                                             resolved=resolved))
                results.append({"id": rid, "status": "REOPENED_OVER_CONTEST",
                                "reopened_by": reopened_by, **r})
                continue
            contested.append(dict(r, id=rid, resolved=resolved))
            rejected_ids.append(rid)
            results.append({"id": rid, "status": "CONTESTED",
                            "reopened_by": reopened_by,
                            "why": "この書き込み自体は既存の値と一致した"
                                   "が、住所そのものは別の値とまだ割れて"
                                   "いる — 不動点ではない",
                            **r})
            continue

        if r.get("seat_created"):
            new_addresses.append(rid)
            results.append({"id": rid, "status": "NEW_ADDRESS",
                            "reopened_by": reopened_by, **r})
        else:
            results.append({"id": rid, "status": "REOPENED" if reopened_by
                            else "AGREES", "reopened_by": reopened_by, **r})

    # **停滞は check() に聞く。** 却下された claim の id をそのまま渡す —
    # 同じ id が STAGNATION_LIMIT 回続けば ESCALATE、周ごとに違う id なら
    # 続く。draft はここでは幾何を持たないので常に ANSWER — 「幾何側の
    # 未決」は ``confirm.sheet`` の側の話で、ここは住所空間の話。
    conv = check({"verdict": "ANSWER"}, rejected=rejected_ids, history=history)

    base = {"results": results, "rejected": rejected_ids,
            "new_addresses": new_addresses,
            "signed_overrides": signed_overrides,
            "counters": conv["counters"],
            "total_open": conv["total_open"], "history_len": len(history),
            "stagnation_limit": STAGNATION_LIMIT,
            "honest_limit": (
                "この判定は主張であって定理ではない。「合意は不動点」"
                "「矛盾は終端」がループを本当に止めるという証明はここには"
                "無い。測れるのは各節を個別に測れる形にしたということだけ"
                "— CONVERGED/CONTESTED/ESCALATE_HUMAN/CONTINUE のどれも、"
                "対応する falsifier が個別に落ちることでしか裏付けられて"
                "いない")}

    # 1. **矛盾は即終端。** 同じ住所に二つの値が立ったら、store は両方を
    #    残して選ばない — ここはその上で「もう一周しない」を言うだけ。
    #    停滞回数を待たない: 一回でも矛盾が立てば終わる。
    if contested:
        return dict(base, verdict=CONTESTED, contested=contested,
                    reason=f"{len(contested)} 件の住所で値が食い違った。"
                           f"store は両方の値を残して選んでいない — "
                           f"正しい方を人が決めるまでこの周回は再開しない")

    # 2. **格納順で答えが動くなら、収束の議論そのものが立たない。**
    #    「合意」も「新しい住所」も、順で違う地図の上では意味が無い。
    order = ingest_order_check(store.write_plan())
    if order["verdict"] != "ANSWER":
        return dict(base, verdict=ORDER_DEPENDENT, order_check=order,
                    reason=f"{len(order['differences'])} 件の住所が、"
                           f"同じ書き込み計画を別の順で入れ直すと違う答えに"
                           f"なった。並びが答えを決めているなら、まだ宣言"
                           f"ではなく並びの産物 — 停滞のカウンタでは"
                           f"直らない")

    if conv["verdict"] == ESCALATE:
        return dict(base, verdict=ESCALATE, reason=conv["why_escalate"])

    # 3. **新しい住所は CONTINUE。** 住所空間は有限だが、まだ埋まって
    #    いない — 進んだことと終わったことは別。
    if new_addresses:
        return dict(base, verdict=CONTINUE,
                    reason=f"{len(new_addresses)} 件が新しい住所に着地した。"
                           f"住所空間はまだ埋まっていない")

    # 4. 却下されたままの claim が残っているが、まだ ESCALATE の回数には
    #    達していない。
    if rejected_ids:
        return dict(base, verdict=CONTINUE,
                    reason=f"{len(rejected_ids)} 件がこの周では通らなかった"
                           f"(却下 {conv['stagnation_limit']} 回で人へ)")

    # 4b. store は割れたままだが、その割れに人の署名が付いた。店の記録は
    #     直さない — この周を止めない、というだけ。
    if signed_overrides:
        return dict(base, verdict=CONTINUE,
                    reason=f"{len(signed_overrides)} 件は store 上ではまだ"
                           f"割れているが、採用者の署名が付いた。生の証拠"
                           f"は両方残る — 止まるのは署名が無い場合だけ")

    # 5. **不動点。** revision が無かった、または全部が既にある値に同意
    #    した。もう一周する理由が無い。
    return dict(base, verdict=CONVERGED,
                reason="この周で住所空間は動かなかった — 提案は無いか、"
                       "既にある値と一致した。不動点")
