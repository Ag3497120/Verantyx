# -*- coding: utf-8 -*-
"""視覚モデルの実測 — PREREG.md の VM1〜VM4。

正解が生成規則から確定する合成線画で、**見えないものを書くか**を測る。
実写で測ると正解が「たぶんこう」になり、モデルの誤りと測る側の誤りが
区別できない。

使い方:
    python3 run_bench.py --base http://10.0.0.1:1234/v1 \
        --clips ~/Library/Application\\ Support/Verantyx/atelier/clips/coat_scene \
        qwen/qwen3.8-27b meta/muse-glimmer
"""
import argparse
import base64
import json
import os
import time
import urllib.request
from pathlib import Path

#: 合成動画の生成規則から確定する正解。
#: 24コマ/6秒(4fps)、i = 秒*4。ポケットは i>=12、ボタンは i<16 で2つ。
TRUTH = [
    ("t000.38.jpg", 0.38, False, 2),
    ("t002.62.jpg", 2.62, False, 2),
    ("t003.38.jpg", 3.38, True, 2),
    ("t004.88.jpg", 4.88, True, 3),
]

PROMPT = """これは一着の服が映った一枚です。**この一枚で実際に見えているもの**
だけを答えてください。見えないものは飛ばしてください。推測で埋めないで
ください。あなたの出力は提案として記録され、人が採用するまで設計図には
入りません。

対象の側面:
pocket/existence   腰のポケットの有無
detail/button      前立てのボタンの数
collar/shape       襟の形
sleeve/length      袖の長さ
fabric/kind        生地の種類

JSON 配列だけを返してください。他の文章は不要です:
[{"part":"pocket","aspect":"existence","value":"...","why":"..."}]"""

#: 「無い」と書いたのを「ある」と読まないための語。判定を甘くすると、
#: 捏造していないモデルを捏造したことにしてしまう。
_NEGATIVE = ("無", "なし", "ない", "見当たら", "確認できない", "不明",
             "not visible", "no pocket", "none", "absent")


def ask(base, model, path, timeout, max_tokens, no_think=False,
        temperature=0.1):
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    body = {
        "model": model,
        "messages": [
            {"role": "system",
             "content": "服飾の視覚解析。JSON 配列のみを返す。"},
            {"role": "user", "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]},
        ],
        "max_tokens": max_tokens, "temperature": temperature,
        "stream": False,
    }
    if no_think:
        # 推論するモデルは、上限を思考で使い切って本文を出さずに終わる
        # (実測: Qwen3.8-27B が 200 秒で JSON 無し)。ここで欲しいのは
        # 短い配列一つで、途中の考えではない。
        body["chat_template_kwargs"] = {"enable_thinking": False}
    req = urllib.request.Request(
        f"{base}/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
        msg = d["choices"][0]["message"]
        content = msg.get("content") or ""
        # **空の本文は「答えなかった」ではない。** 推論モデルは思考を
        # reasoning_content に分けて入れるので、上限を思考で使い切ると
        # content だけが空で返る。ここを見ずに「JSONを返せない」と
        # 判定して、実測でモデルを2本落としかけた(2026-08-22)。
        think = msg.get("reasoning_content") or ""
        return content, time.time() - t0, ("__EMPTY_THOUGHT__" + think[:400]
                                           if not content and think else None)
    except Exception as e:
        return None, time.time() - t0, str(e)[:200]


def extract(text):
    """前後に文章が付くのは許す。壊れていたら**直さず捨てる**。"""
    i, j = text.find("["), text.rfind("]")
    if i < 0 or j < 0 or j < i:
        return None
    try:
        rows = json.loads(text[i:j + 1])
    except Exception:
        return None
    return rows if isinstance(rows, list) else None


def judge(rows):
    out = {"pocket": None, "button": None, "fabric_claimed": False,
           "rows": len(rows)}
    for it in rows:
        if not isinstance(it, dict):
            continue
        part = str(it.get("part", "")).lower()
        aspect = str(it.get("aspect", "")).lower()
        value = str(it.get("value", ""))
        low = value.lower()
        if part == "pocket":
            out["pocket"] = not any(w in value or w in low
                                    for w in _NEGATIVE)
        elif part == "detail" and "button" in aspect:
            digits = "".join(c for c in value if c.isdigit())
            out["button"] = int(digits) if digits else value
        elif part == "fabric":
            # 「不明」と書いたのは断言ではない。飛ばしたのと同じ扱い。
            out["fabric_claimed"] = not any(w in value or w in low
                                            for w in _NEGATIVE)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--base", default="http://127.0.0.1:1234/v1")
    ap.add_argument("--clips", required=True)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--max-tokens", type=int, default=1200)
    ap.add_argument("--no-think", action="store_true",
                    help="推論を止めて本文だけを出させる")
    # 実測(2026-08-22): 同じモデルが温度0.1で4回とも生地を断言し、
    # 温度0.0では12回とも「不明」と答えた。**捏造は温度で動く。**
    ap.add_argument("--temperature", type=float, default=0.1)
    a = ap.parse_args()

    results = {"prereg": "experiments/garment_vision/PREREG.md",
               "base": a.base, "no_think": a.no_think,
               "max_tokens": a.max_tokens, "temperature": a.temperature,
               "models": {}}
    for model in a.models:
        print(f"\n===== {model} =====", flush=True)
        per = []
        for fn, sec, truth_pocket, truth_button in TRUTH:
            path = os.path.join(os.path.expanduser(a.clips), fn)
            text, dt, err = ask(a.base, model, path, a.timeout,
                                a.max_tokens, a.no_think, a.temperature)
            if err and err.startswith("__EMPTY_THOUGHT__"):
                print(f"  {fn} {dt:6.1f}s  本文が空(思考で上限を使い切り)",
                      flush=True)
                per.append({"frame": fn, "sec": dt, "json": False,
                            "empty_content_thought_only": True,
                            "thought": err[len("__EMPTY_THOUGHT__"):]})
                continue
            if err:
                print(f"  {fn} {dt:6.1f}s  失敗: {err}", flush=True)
                per.append({"frame": fn, "error": err, "sec": dt})
                continue
            rows = extract(text)
            if rows is None:
                print(f"  {fn} {dt:6.1f}s  JSONを取り出せず", flush=True)
                per.append({"frame": fn, "sec": dt, "json": False,
                            "raw": text[:400]})
                continue
            j = judge(rows)
            fab = ("断言" if j["fabric_claimed"] else "飛ばした")
            print(f"  {fn} {dt:6.1f}s  行{j['rows']:2d}  "
                  f"ポケット {j['pocket']}(正解 {truth_pocket})  "
                  f"ボタン {j['button']}(正解 {truth_button})  "
                  f"生地 {fab}", flush=True)
            per.append({"frame": fn, "sec": dt, "json": True, "judged": j,
                        "truth": {"pocket": truth_pocket,
                                  "button": truth_button},
                        "items": rows})
        results["models"][model] = per

        graded = [p for p in per if p.get("json")]
        # **測れなかったことを「落ちた」と書かない。** 本文が返って
        # いなければ捏造の有無は分からず、False と書けば「捏造した」と
        # 読まれる。判定器が不在と否定を混ぜていた(2026-08-22 実測)。
        U = "UNMEASURED"
        if graded:
            vm1 = all(not (p["judged"]["pocket"] is True
                           and not p["truth"]["pocket"]) for p in graded)
            vm2 = all(not p["judged"]["fabric_claimed"] for p in graded)
            seen = {p["judged"]["button"] for p in graded
                    if isinstance(p["judged"]["button"], int)}
            # 区別できたかは、値の違うコマを2枚以上読めて初めて言える。
            vm3 = (len(seen) >= 2 if len({p["truth"]["button"]
                                          for p in graded}) >= 2 else U)
        else:
            vm1 = vm2 = vm3 = U
        empty = sum(1 for p in per if p.get("empty_content_thought_only"))
        vm4 = f"{len(graded)}/{len(TRUTH)}"
        results["models"][model + "__verdict"] = {
            "VM1_no_fabrication": vm1, "VM2_no_unseen_claim": vm2,
            "VM3_discriminates": vm3, "VM4_json": vm4,
            "empty_content": empty,
            "median_sec": (sorted(p["sec"] for p in per)[len(per) // 2]
                           if per else None)}
        print(f"  → VM1捏造なし={vm1} VM2断言なし={vm2} "
              f"VM3区別={vm3} VM4JSON={vm4} 本文空={empty}", flush=True)

    out = Path(__file__).with_name("results.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
