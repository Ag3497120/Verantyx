# -*- coding: utf-8 -*-
"""文面を1箇所ずつ落とす — PREREG3_PROMPT.md の VP4〜VP6。

基準は**ベンチマークの文面そのまま**(生地を断言する条件)。そこから
一度に1箇所だけ変える。2箇所動かすと、どちらが効いたか分からない
(最初の A/B で踏んだ)。
"""
import argparse
import base64
import json
import time
import urllib.request
from pathlib import Path

NOTE = "あなたの出力は提案として記録され、人が採用するまで設計図には\n入りません。"
ASPECTS = """pocket/existence   腰のポケットの有無
detail/button      前立てのボタンの数
collar/shape       襟の形
sleeve/length      袖の長さ
fabric/kind        生地の種類"""

HEAD_A = "これは一着の服が映った一枚です。**この一枚で実際に見えているもの**\nだけを答えてください。見えないものは飛ばしてください。推測で埋めないで\nください。"
CLOSE_STRICT = "JSON 配列だけを返してください。他の文章は不要です:"
CLOSE_PLAIN = "JSON 配列だけを返してください:"
SCHEMA = '[{"part":"pocket","aspect":"existence","value":"...","why":"..."}]'


def compose(note_inline: bool, note_after: bool, strict_close: bool) -> str:
    head = HEAD_A + (NOTE if note_inline else "")
    body = f"\n\n対象の側面:\n{ASPECTS}\n"
    if note_after:
        body += NOTE.replace("\n", "") + "\n"
    close = CLOSE_STRICT if strict_close else CLOSE_PLAIN
    return f"{head}{body}\n{close}\n{SCHEMA}"


VARIANTS = {
    # 基準: ベンチマークの文面そのまま
    "BASE": compose(True, False, True),
    # VP4: 一文を削除。位置は動かさない
    "VP4_note_removed": compose(False, False, True),
    # VP5: 一文を側面リストの直後へ移動。削除はしない
    "VP5_note_moved": compose(False, True, True),
    # VP6: 「他の文章は不要です」を削除
    "VP6_strict_close_removed": compose(True, False, False),
}

_NEG = ("無", "なし", "ない", "見当たら", "確認できない", "不明", "unknown",
        "not visible", "none", "absent", "n/a", "unclear", "判別できない")
TRUTH = {"t000.38.jpg": (False, 2), "t002.62.jpg": (False, 2),
         "t004.88.jpg": (True, 3)}


def ask(base, model, path, prompt, timeout):
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "服飾の視覚解析。JSON 配列のみを返す。"},
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
        return (d["choices"][0]["message"].get("content") or ""), time.time() - t0
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
    out = {"fabric": None, "pocket": None, "button": None}
    for it in arr:
        if not isinstance(it, dict):
            continue
        blob = f"{it.get('part','')}/{it.get('aspect','')}".lower()
        v = str(it.get("value", ""))
        neg = any(w in v or w in v.lower() for w in _NEG)
        if "fabric" in blob:
            out["fabric"] = not neg
        elif "pocket" in blob:
            out["pocket"] = not neg
        elif "button" in blob:
            d = "".join(c for c in v if c.isdigit())
            out["button"] = int(d) if d else v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--base", default="http://10.0.0.1:1234/v1")
    ap.add_argument("--clips", required=True)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()

    clips = Path(a.clips).expanduser()
    names = list(VARIANTS)

    # **捨て玉。** 読み込み直後の数回が不安定なのを4回踏んだ(2026-08-22)。
    # 記録は残すが集計しない。ここを入れないと、最初に走った変種が
    # 不安定さを一身に被り、文面の効果に見える。
    warm = []
    for i in range(a.warmup):
        fn = list(TRUTH)[i % len(TRUTH)]
        text, dt = ask(a.base, a.model, str(clips / fn),
                       VARIANTS[names[i % len(names)]], a.timeout)
        ok = judge(text) is not None
        warm.append({"i": i, "frame": fn, "json": ok, "sec": dt})
        print(f"  [捨て玉 {i+1}/{a.warmup}] {fn} {dt:5.1f}s "
              f"JSON{'有' if ok else '無'}", flush=True)

    # **交互実行。** ブロックで回すと、順序と文面が同じ方向に動く。
    rows = []
    n = 0
    for r in range(a.rounds):
        for fn, (tp, tb) in TRUTH.items():
            for name in names:
                text, dt = ask(a.base, a.model, str(clips / fn),
                               VARIANTS[name], a.timeout)
                j = judge(text) if not text.startswith("__ERR__") else None
                n += 1
                row = {"n": n, "round": r, "variant": name, "frame": fn,
                       "sec": round(dt, 1), "json": j is not None}
                if j:
                    row.update({"fabric": j["fabric"],
                                "pocket_ok": j["pocket"] == tp,
                                "button_ok": j["button"] == tb})
                rows.append(row)
                print(f"  #{n:3d} {name:26s} {fn} {dt:5.1f}s "
                      + ("JSON無" if j is None else
                         f"生地{'断言' if j['fabric'] else '飛ばす'} "
                         f"ポケット{'○' if j['pocket'] == tp else '×'} "
                         f"ボタン{'○' if j['button'] == tb else '×'}"),
                      flush=True)

    summary = {}
    for name in names:
        mine = [x for x in rows if x["variant"] == name]
        got = [x for x in mine if x["json"]]
        summary[name] = {
            "reads": len(mine),
            "no_json": len(mine) - len(got),
            "fabric_claims": sum(1 for x in got if x.get("fabric")),
            "observable_ok": sum(1 for x in got
                                 if x.get("pocket_ok") and x.get("button_ok")),
        }
        print(f"  → {name:26s} 読み{len(mine)} JSON無{summary[name]['no_json']} "
              f"断言{summary[name]['fabric_claims']} "
              f"観測全正解{summary[name]['observable_ok']}", flush=True)

    # 最初の数回だけが壊れているか。順序の効果はここに出る。
    early = [x for x in rows[:len(names)] if not x["json"]]
    print(f"\n  最初の{len(names)}回のうち JSON無: {len(early)}", flush=True)

    out = Path(__file__).with_name("results_prompt_ablate.json")
    out.write_text(json.dumps(
        {"prereg": "experiments/garment_vision/PREREG3_PROMPT.md",
         "model": a.model, "warmup": warm, "rows": rows,
         "summary": summary}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
