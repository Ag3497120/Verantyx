#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stop: 返答を約束と照合。遮断するのは**採用済み**の約束だけ。

遮断は forbidden_used のみ(required_missing は字面照合で誤検知が多い
ことを実地試験が実測済み — 記録のみ)。隔離席の候補(規則が読んだ
約束)は shadow_violations に出るが遮断はせず、非遮断の知らせとして
出す — 誤遮断を止めるのと、誤読を見えなくするのは別のことだから。
stop_hook_active で二度は止めない(無限ループ防止)。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import guard, read_hook_input, store_path


def last_reply(data):
    t = data.get("last_assistant_message") or ""
    if t:
        return str(t)
    # transcript_path から末尾の assistant 発話を拾う(形式差に耐える)
    p = data.get("transcript_path")
    if not p or not os.path.exists(p):
        return ""
    try:
        lines = open(p, encoding="utf-8").read().splitlines()
        for line in reversed(lines):
            try:
                d = json.loads(line)
            except Exception:
                continue
            msg = d.get("message") or d
            if (d.get("type") == "assistant" or
                    msg.get("role") == "assistant"):
                c = msg.get("content")
                if isinstance(c, list):
                    return " ".join(x.get("text", "") for x in c
                                    if isinstance(x, dict))
                return str(c or "")
    except Exception:
        pass
    return ""


def _reasons(rows, limit=3):
    """違反1件を一行にする。禁止側の証拠だけを言葉にする。"""
    out = []
    for v in rows[:limit]:
        found = v.get("class_hits")
        extra = (f"(見つけた文字: {found[0]['found']})" if found else "")
        out.append(f"「{v.get('inject')}」の禁止語 "
                   f"{v.get('forbidden_used')} を使っている{extra}")
    return out


def main():
    data = read_hook_input()
    if data.get("stop_hook_active"):
        return                       # 二度は止めない
    reply = last_reply(data)
    if not reply:
        return
    out = guard("check", {"reply": reply}, store=store_path())
    if not out:
        return
    payload = {}

    # ① 採用済みの約束だけが遮断する。禁止側の証拠がある行のみ
    #    (required_missing は字面照合で誤検知が多い — 記録のみ)。
    hard = [v for v in out.get("violations", [])
            if v.get("forbidden_used")]
    if out.get("verdict") == "BROKEN" and hard:
        payload["decision"] = "block"
        payload["reason"] = ("Vera が約束との矛盾を検出した: "
                             + " / ".join(_reasons(hard)))

    # ② 隔離席の候補は**遮断せずに知らせる**(2026-08-21)。
    #    これまで shadow_violations は完全に無視されていた。黙って捨てると
    #    誤遮断を「見えなくする」ことで消したのと同じで、それは番人を
    #    壊すのと変わらない。知らせは systemMessage(非遮断の経路)で出し、
    #    decision には決して混ぜない — 裏口からの執行を作らないため。
    shadow = [v for v in out.get("shadow_violations", [])
              if v.get("forbidden_used")]
    if shadow:
        payload["systemMessage"] = (
            "Vera 隔離席(遮断していない): "
            + " / ".join(_reasons(shadow, limit=2))
            + " — 良ければ `guard adopt`、誤読なら `guard retire`")

    if payload:
        print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
