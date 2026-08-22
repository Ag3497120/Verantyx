# -*- coding: utf-8 -*-
"""プロンプトの一文が捏造を増やすか — PREREG3_PROMPT.md の VP1〜VP3。"""
import argparse
import base64
import json
import time
import urllib.request
from pathlib import Path

ASPECTS = """pocket/existence   腰のポケットの有無
detail/button      前立てのボタンの数
collar/shape       襟の形
sleeve/length      袖の長さ
fabric/kind        生地の種類"""

HEAD = """これは一着の服が映った一枚です。**この一枚で実際に見えているもの**
だけを答えてください。見えないものは飛ばしてください。推測で埋めないで
ください。

対象の側面:
"""

TAIL = """
JSON 配列だけを返してください:
[{"part":"pocket","aspect":"existence","value":"...","why":"..."}]"""

VARIANTS = {
    # A: 現行。台帳を守るために書いた一文が入っている。
    "A_proposal_note": "\nあなたの出力は提案として記録され、人が採用する"
                       "まで設計図には入りません。\n",
    # B: その一文を削るだけ。
    "B_removed": "",
    # C: 責任の所在を、人ではなくモデルの出力に戻す。
    "C_cost_of_guessing": "\n見えていないものを書くと、それを確かめる人の"
                          "時間を奪います。\n",
}

_NEG = ("無", "なし", "ない", "見当たら", "確認できない", "不明", "unknown",
        "not visible", "none", "absent", "n/a", "unclear", "判別できない")


def ask(base, model, path, variant, timeout):
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    prompt = HEAD + ASPECTS + VARIANTS[variant] + TAIL
    body = {
        "model": model,
        "messages": [
            {"role": "system",
             "content": "服飾の視覚解析。JSON 配列のみを返す。"},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]},
        ],
        "max_tokens": 1500, "temperature": 0.0, "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        f"{base}/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
        return (d["choices"][0]["message"].get("content") or "",
                time.time() - t0)
    except Exception as e:
        return f"__ERR__{e}", time.time() - t0


def judge(text):
    i, j = text.find("["), text.rfind("]")
    if i < 0 or j < 0:
        return None
    try:
        arr = json.loads(text[i:j + 1])
    except Exception:
        return None
    out = {"fabric_claimed": False, "pocket": None, "button": None}
    for it in arr:
        if not isinstance(it, dict):
            continue
        blob = f"{it.get('part','')}/{it.get('aspect','')}".lower()
        v = str(it.get("value", ""))
        neg = any(w in v or w in v.lower() for w in _NEG)
        if "fabric" in blob:
            out["fabric_claimed"] = not neg
        elif "pocket" in blob:
            out["pocket"] = not neg
        elif "button" in blob:
            d = "".join(c for c in v if c.isdigit())
            out["button"] = int(d) if d else v
    return out


TRUTH = {"t000.38.jpg": (False, 2), "t002.62.jpg": (False, 2),
         "t004.88.jpg": (True, 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--base", default="http://10.0.0.1:1234/v1")
    ap.add_argument("--clips", required=True)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()

    res = {"prereg": "experiments/garment_vision/PREREG3_PROMPT.md",
           "model": a.model, "variants": {}}
    for name in VARIANTS:
        fab = obs_ok = obs_n = 0
        rows = []
        for fn, (tp, tb) in TRUTH.items():
            for _ in range(a.repeats):
                text, dt = ask(a.base, a.model,
                               str(Path(a.clips).expanduser() / fn),
                               name, a.timeout)
                j = judge(text) if not text.startswith("__ERR__") else None
                if j is None:
                    rows.append({"frame": fn, "json": False, "sec": dt})
                    continue
                fab += 1 if j["fabric_claimed"] else 0
                obs_n += 2
                obs_ok += (1 if j["pocket"] == tp else 0)
                obs_ok += (1 if j["button"] == tb else 0)
                rows.append({"frame": fn, "sec": dt, **j})
                print(f"  {name:22s} {fn} {dt:5.1f}s "
                      f"生地{'断言' if j['fabric_claimed'] else '飛ばす'} "
                      f"ポケット{j['pocket']}({tp}) ボタン{j['button']}({tb})",
                      flush=True)
        res["variants"][name] = {"fabric_claims": fab,
                                 "observable_correct": f"{obs_ok}/{obs_n}",
                                 "rows": rows}
        print(f"  → {name}: 生地の断言 {fab} 回 / "
              f"観測できるもの {obs_ok}/{obs_n}", flush=True)

    out = Path(__file__).with_name("results_prompt_ab.json")
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
