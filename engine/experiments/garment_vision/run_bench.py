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


def ask(base, model, path, timeout, max_tokens):
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
        "max_tokens": max_tokens, "temperature": 0.1, "stream": False,
    }
    req = urllib.request.Request(
        f"{base}/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
        return d["choices"][0]["message"]["content"], time.time() - t0, None
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
    a = ap.parse_args()

    results = {"prereg": "experiments/garment_vision/PREREG.md",
               "base": a.base, "models": {}}
    for model in a.models:
        print(f"\n===== {model} =====", flush=True)
        per = []
        for fn, sec, truth_pocket, truth_button in TRUTH:
            path = os.path.join(os.path.expanduser(a.clips), fn)
            text, dt, err = ask(a.base, model, path, a.timeout, a.max_tokens)
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
        vm1 = all(not (p["judged"]["pocket"] is True and not p["truth"]["pocket"])
                  for p in graded) and bool(graded)
        vm2 = all(not p["judged"]["fabric_claimed"] for p in graded) and bool(graded)
        seen = {p["judged"]["button"] for p in graded
                if isinstance(p["judged"]["button"], int)}
        vm3 = len(seen) >= 2
        vm4 = len(graded) == len(TRUTH)
        results["models"][model + "__verdict"] = {
            "VM1_no_fabrication": vm1, "VM2_no_unseen_claim": vm2,
            "VM3_discriminates": vm3, "VM4_json": vm4,
            "median_sec": (sorted(p["sec"] for p in per)[len(per) // 2]
                           if per else None)}
        print(f"  → VM1捏造なし={vm1} VM2断言なし={vm2} "
              f"VM3区別={vm3} VM4JSON={vm4}", flush=True)

    out = Path(__file__).with_name("results.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
