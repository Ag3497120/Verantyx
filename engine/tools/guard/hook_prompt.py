#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UserPromptSubmit: 指示→約束の抽出・登録、薄れた約束だけ再注入、
「もう〜していいよ」の退役。抽出は器官(extract_covenants)に一元化。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import guard, read_hook_input, store_path

def main():
    data = read_hook_input()
    prompt = str(data.get("prompt", ""))
    store = store_path()

    # 1)+2) 抽出も解除も器官に一元化(閉じた表は covenant.py が持つ —
    # フックは配管だけ)。ja+en 対称。
    ex = guard("extract", {"text": prompt}, store=store) or {}
    if ex.get("releases"):
        listed = guard("list", {}, store=store) or {}
        for term in ex["releases"]:
            for c in listed.get("covenants", []):
                if not c.get("retired") and term in c.get("forbids", []):
                    guard("retire", {"name": c["name"],
                                     "quote": prompt[:80]}, store=store)
    # 規則が読んだ約束は**隔離席へ**(2026-08-21、誤遮断の実測)。
    # set(執行に入る)ではなく propose。人が実際に書く指示20本で測ると
    # 4本が間違った語を捕まえ、`No new dependencies` → forbids=["new"] は
    # 返答「I added a new helper function.」を遮断した。候補は shadow で
    # 照合されるだけで、採用は人の行為(門)のまま。
    for cand in ex.get("candidates", []):
        guard("propose", cand, store=store)

    # 3) 前のターンの required 監査(証人ベース・遮断しない)を報せてから
    #    境界を切る。「このターンに要ったか」は文脈なので判定は運ばず、
    #    無かったという事実だけを運ぶ。
    audit_lines = []
    audit = guard("audit", {}, store=store) or {}
    if audit.get("verdict") == "REQUIRED_UNWITNESSED":
        for r in audit.get("rows", []):
            if not r.get("witnessed"):
                audit_lines.append(
                    f"・前のターン、「{r.get('inject')}」の実行記録"
                    f"({r.get('requires')})が見当たらなかった")
    guard("boundary", {}, store=store)

    # 店が育っていれば「焼き直せる」とだけ報せる(stat のみ・店は読まない)。
    # 焼き直しは執行を変える行為なので、フックは決してやらない。
    st = guard("stale", {}, store=store) or {}
    if st.get("verdict") == "STALE":
        names = [r.get("covenant") for r in st.get("rows", [])][:3]
        audit_lines.append(
            f"・店が更新されている — 推論の焼き込みが古い({', '.join(names)})。"
            f"`vera-memory guard rebake` で焼き直せる")

    # 3.5) 隔離席で実績を積んだ候補を**見せるだけ**(2026-08-21)。
    # 自動採用は絶対にしない — 「過検出の番人は切られる」の罠そのもの。
    # 毎ターン出ないのは promotion_review の帯(圏内照合8回以上)が
    # 効くから: 提案されたばかりの候補は UNKNOWN_TOO_FEW_CHECKS で黙る。
    promo = guard("promote", {}, store=store) or {}
    for r in promo.get("rows", []):
        if r.get("verdict") != "PROMOTABLE":
            continue
        src = "規則が読んだ候補" if r.get("origin") == "regex" else "候補"
        audit_lines.append(
            f"・{src}「{r.get('covenant')}」が実績を積んだ"
            f"({r.get('checks')}回中{r.get('hits')}回発火)。"
            f"中身を見て良ければ `vera-memory guard adopt` で執行に入る"
            f"(こちらでは採用しない)")

    # 4) 薄れた約束だけ再注入(毎ターン全部は情報を運ばない — Vera自身の注記)
    fading = guard("fading", {}, store=store) or {}
    rows = fading.get("fading") if isinstance(fading, dict) else None
    lines = []
    for r in (rows or []):
        if isinstance(r, dict) and r.get("delta", 0) < 0:
            lines.append(f"・「{r.get('covenant')}」"
                         f"(守れていた率 {r.get('kept_before')}"
                         f" → {r.get('kept_recently')})")
    lines = audit_lines + lines
    if lines:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "<vera-covenant-reminder>\n"
                                 + "\n".join(lines)
                                 + "\n</vera-covenant-reminder>"}},
            ensure_ascii=False))


if __name__ == "__main__":
    main()
