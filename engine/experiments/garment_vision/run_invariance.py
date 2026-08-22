# -*- coding: utf-8 -*-
"""置き直して消える答えは捏造 — PREREG2_INVARIANCE.md の VI1〜VI2。

同じコマを、プロンプト内の**側面の並び順だけ**変えて複数回読ませる。
絵も問いも同じなので、本当に見えているものは同じ答えになるはず。
揺れる答えは、絵ではなくモデルの中から出てきている。

VI3/VI4(台帳への印)は本体側の測定で、ここでは前提の VI1/VI2 を測る。
"""
import argparse
import base64
import json
import time
import urllib.request
from itertools import permutations
from pathlib import Path

ASPECTS = [
    ("pocket/existence", "腰のポケットの有無"),
    ("detail/button", "前立てのボタンの数"),
    ("collar/shape", "襟の形"),
    ("fabric/kind", "生地の種類"),
]

HEAD = """これは一着の服が映った一枚です。**この一枚で実際に見えているもの**
だけを答えてください。見えないものは飛ばしてください。推測で埋めないで
ください。

対象の側面:
"""

TAIL = """
JSON 配列だけを返してください:
[{"part":"pocket","aspect":"existence","value":"...","why":"..."}]"""

_NEG = ("無", "なし", "ない", "見当たら", "確認できない", "不明",
        "not visible", "none", "absent", "判別できない", "読み取れない",
        # 英語で飛ばしたときの言い方。落とすと、正しく「分からない」と
        # 答えたモデルが「値を書いた」ことになる。
        "unknown", "n/a", "not determinable", "cannot tell",
        "not visible in", "unclear", "indeterminate")


def prompt_for(order):
    lines = "\n".join(f"{ASPECTS[i][0]}   {ASPECTS[i][1]}" for i in order)
    return HEAD + lines + TAIL


def ask(base, model, path, order, timeout, max_tokens):
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    body = {
        "model": model,
        "messages": [
            {"role": "system",
             "content": "服飾の視覚解析。JSON 配列のみを返す。"},
            {"role": "user", "content": [
                {"type": "text", "text": prompt_for(order)},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]},
        ],
        "max_tokens": max_tokens, "temperature": 0.0, "stream": False,
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


#: 肯定の言い方。**存在するかどうか**の側面でだけ使う。
_AFF = ("有", "あり", "ある", "存在", "yes", "present", "visible",
        "confirmed", "true")

#: 形の揺れを畳むための、部位と側面の正準名。中身は畳まない。
_PARTS = ("collar", "sleeve", "body", "back", "pocket", "fabric",
          "lining", "detail")
_ASPECTS = ("existence", "button", "shape", "kind", "length", "material",
            "closure", "construction", "cuff", "silhouette", "dart",
            "structure", "vent", "type", "position", "weight", "pattern",
            "stitch", "trim", "count")


#: 訊いている側面 → 部位。閉じた表なので、部位が省かれても引ける。
_PART_OF_ASPECT = {a.split("/")[1]: a.split("/")[0]
                   for a, _ in ASPECTS}


def canon_key(part_raw, aspect_raw):
    """**モデルが返すキーの形は毎回変わる。**

    実測(2026-08-22)で同じ一枚から `detail/button`、`button/count`、
    `detail/button/count`、`collar/shape/shape` が返った。同じ主張が
    別のキーに見えると、突き合わせが「欠落」を拾い、形の揺れを答えの
    揺れとして数える。ここで正準形に畳む — **畳むのは形だけ**で、
    違う服飾用語は別のままにする。
    """
    blob = f"{part_raw}/{aspect_raw}".lower()
    part = next((p for p in _PARTS if p in blob), None)
    if part is None:
        # 実測(2026-08-22): モデルが part を省いて `button/count` だけを
        # 返した。訊いた側面は閉じた表なので、側面から部位を引ける。
        part = _PART_OF_ASPECT.get(
            next((a for a in _ASPECTS if a in blob), ""), None)
    # 側面は後ろから探す。`detail/button/count` の意図は button。
    aspect = None
    for a in _ASPECTS:
        if a in blob and a != part:
            aspect = a
            break
    if part is None or aspect is None:
        return blob
    return f"{part}/{aspect}"


def rows_of(text):
    i, j = text.find("["), text.rfind("]")
    if i < 0 or j < 0 or j < i:
        return {}
    try:
        arr = json.loads(text[i:j + 1])
    except Exception:
        return {}
    out = {}
    for it in arr:
        if not isinstance(it, dict):
            continue
        key = canon_key(it.get("part", ""), it.get("aspect", ""))
        out[key] = str(it.get("value", ""))
    return out


def normal(v, key=""):
    """値を粗く正規化する。**言い回しの違いを揺れと数えない** —
    「ポケット無し」と「ポケットは見当たらない」は同じ答えである。

    大文字小文字も畳む。実測で `V-neck` と `v-neck` を揺れと数え、
    正しく同じ答えを返したモデルを捏造扱いしかけた(2026-08-22)。
    検査が雑音を拾うと、**正しく振る舞ったものほど落ちる**。
    """
    v = v.strip()
    low = v.lower()
    if any(w in v or w in low for w in _NEG):
        return "<否定/不明>"
    # 有無を問う側面では、「存在する」と "yes" は同じ答えである。
    # ここを畳まないと、正しく「有る」と答え続けたモデルが揺れる。
    if key.endswith("/existence") and any(w in v or w in low for w in _AFF):
        return "<肯定>"
    digits = "".join(c for c in v if c.isdigit())
    if digits:
        return digits
    # 記号と空白の揺れも畳む(「ノッチド ラペル」と「ノッチドラペル」)
    return "".join(ch for ch in low if ch.isalnum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--base", default="http://10.0.0.1:1234/v1")
    ap.add_argument("--clips", required=True)
    ap.add_argument("--frames", default="t002.62.jpg,t004.88.jpg")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--max-tokens", type=int, default=1200)
    a = ap.parse_args()

    orders = list(permutations(range(len(ASPECTS))))[:a.repeats]
    results = {"prereg": "experiments/garment_vision/PREREG2_INVARIANCE.md",
               "orders": [list(o) for o in orders], "models": {}}

    for model in a.models:
        print(f"\n===== {model} =====", flush=True)
        per = {}
        for fn in a.frames.split(","):
            path = Path(a.clips).expanduser() / fn
            answers = []
            for order in orders:
                text, dt = ask(a.base, model, str(path), order,
                               a.timeout, a.max_tokens)
                if text.startswith("__ERR__"):
                    print(f"  {fn} 失敗 {text[:80]}", flush=True)
                    continue
                answers.append(rows_of(text))
                print(f"  {fn} 順{list(order)} {dt:5.1f}s "
                      f"{ {k: normal(v, k) for k, v in answers[-1].items()} }",
                      flush=True)
            # 側面ごとに、並び順をまたいで答えが一つに定まるか
            stability = {}
            keys = set().union(*answers) if answers else set()
            for k in sorted(keys):
                vals = {normal(a_.get(k, "<欠落>"), k) for a_ in answers}
                stability[k] = {"stable": len(vals) == 1,
                                "values": sorted(vals)}
            per[fn] = {"answers": answers, "stability": stability}
            for k, v in stability.items():
                mark = "安定" if v["stable"] else "**揺れた**"
                print(f"    {k:20s} {mark}  {v['values']}", flush=True)
        results["models"][model] = per

    out = Path(__file__).with_name("results_invariance.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
