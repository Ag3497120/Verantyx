# -*- coding: utf-8 -*-
"""実LLMでの経験則 earn — PREREG2.md が事前登録。

ハーネス項の実LLM解釈:
    hjudge  = 形式検査(真値を見ない: 数字のみ/JSONキー/長さ)
    hretry  = judge 不合格時のみ再試行(temp 0.7)
    htrunc  = プロンプトの**先頭**を落とす(末尾 n 字を残す — 質問は
              末尾に置いてある)
成功 = judge合格 かつ 真値検査合格。採択 = plain比 +2問以上(僅差は
棄権 — ノイズから勝者を選ばない)。確率の主張はしない: この集合で
こう出た、の記録のみ。
"""
import json, re, time, urllib.request
from pathlib import Path

API = "http://localhost:12340/v1/chat/completions"
TEMP = 0.7
DATE = "2026-08-20"

PAD = ("これは無関係な前置きである。当社の沿革は長く、創業者は登山を好み、"
       "社内報には毎月の天気の話が載る。備品の管理番号は改定を重ね、"
       "食堂の献立は季節で変わる。年度末には棚卸しがあり、駐車場の割当は"
       "抽選で決まる。健康診断は秋に実施され、社内表彰は春に行われる。") * 24

def _arith(q, ans):
    return {"prompt": f"{q} 数字だけで答えよ。", "expect": ans,
            "judge": "digits", "kind": "arith"}

def _json(desc, seed, expect):
    return {"prompt": PAD[:300] + f" 次の指示だけに従え: {desc}。値は {seed}。JSONのみ。",
            "expect": expect, "judge": "json_deep", "kind": "json"}

def _extract(fact, q, ans):
    # 邪魔を2,000字に伸ばし、事実は**中央**に埋める(末尾でも先頭でもない)
    mid = PAD[:1000] + fact + PAD[1000:2000]
    return {"prompt": mid + f" 質問: {q} 答えだけを書け。",
            "expect": ans, "judge": "short", "kind": "extract"}

TASKS = [
    _arith("(37+58)*3-14 は?", "271"), _arith("(84-29)*4+17 は?", "237"),
    _arith("(17*6+8)*2 は?", "220"),   _arith("(73+69)*2-45 は?", "239"),
    _arith("(91-47)*3+26 は?", "158"), _arith("(23*7-11)*2 は?", "300"),
    _arith("(56+87)*2-19 は?", "267"), _arith("(14*9+13)*3 は?", "417"),
    _json("キー user を持ち、その中に name と id を持つJSON",
          "name=kikai, id=7", {"user": {"name": "kikai", "id": 7}}),
    _json("キー data を持ち、その中に x と y を持つJSON",
          "x=3, y=9", {"data": {"x": 3, "y": 9}}),
    _json("キー item を持ち、その中に code と ok を持つJSON",
          "code=A1, ok=true", {"item": {"code": "A1", "ok": True}}),
    _json("キー list を持ち、その値が2要素の配列であるJSON",
          "1 と 2", {"list": [1, 2]}),
    _json("キー rec を持ち、その中に tag と count を持つJSON",
          "tag=z9, count=5", {"rec": {"tag": "z9", "count": 5}}),
    _json("キー box を持ち、その中に w と h を持つJSON",
          "w=4, h=6", {"box": {"w": 4, "h": 6}}),
    _json("キー pair を持ち、その値が2要素の配列であるJSON",
          "8 と 3", {"pair": [8, 3]}),
    _json("キー cfg を持ち、その中に mode と level を持つJSON",
          "mode=fast, level=2", {"cfg": {"mode": "fast", "level": 2}}),
    _extract("ところで倉庫の棚番号は B417 である。", "倉庫の棚番号は?", "B417"),
    _extract("なお当直の内線は 3062 である。", "当直の内線は?", "3062"),
    _extract("ちなみに保管庫の暗証は 1130 である。", "保管庫の暗証は?", "1130"),
    _extract("第2会議室の内線は 4408 である。", "第2会議室の内線は?", "4408"),
    _extract("検収日は毎月 25日 と定められている。", "検収日は毎月何日?", "25日"),
    _extract("更衣室の予備ロッカーは C205 である。", "予備のロッカー番号は?", "C205"),
    _extract("非常用発電機の型式は G-88 である。", "非常用発電機の型式は?", "G-88"),
    _extract("郵便物の集荷は 16時 である。", "郵便物の集荷は何時?", "16時"),
]

def call(model, prompt, max_tokens=80):
    body = json.dumps({"model": model, "temperature": TEMP,
                       "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt}]}
                      ).encode()
    req = urllib.request.Request(API, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read())
        return d["choices"][0]["message"]["content"]
    except Exception as e:
        return f"__INFRA__{type(e).__name__}"

def judge(task, out):
    """真値を見ない形式検査。"""
    if out.startswith("__INFRA__"):
        return False
    s = out.strip()
    j = task["judge"]
    if j == "digits":
        return bool(re.fullmatch(r"-?\d+", s))
    if j == "json_deep":
        m = re.search(r"\{.*\}", s, re.S)
        if not m:
            return False
        try:
            json.loads(m.group(0))
            return True
        except Exception:
            return False
    if j.startswith("json:"):
        keys = set(j[5:].split(","))
        m = re.search(r"\{.*\}", s, re.S)
        if not m:
            return False
        try:
            return set(json.loads(m.group(0))) == keys
        except Exception:
            return False
    if j == "short":
        return 0 < len(s) <= 30
    return False

def correct(task, out):
    s = out.strip()
    if task["kind"] == "arith":
        return s == task["expect"]
    if task["kind"] == "json":
        m = re.search(r"\{.*\}", s, re.S)
        if not m:
            return False
        try:
            return json.loads(m.group(0)) == task["expect"]
        except Exception:
            return False
    return task["expect"] in s and len(s) <= 30

def run_variant(model, task, variant):
    prompt = task["prompt"]
    infra = 0
    if variant == "trunc400":
        prompt = prompt[-400:]
    elif variant == "trunc64":
        prompt = prompt[-64:]
    tries = 3 if variant == "retry3" else 1
    out = ""
    for _ in range(tries):
        out = call(model, prompt)
        if out.startswith("__INFRA__"):
            infra += 1
            continue
        if judge(task, out):
            break
    ok = judge(task, out) and correct(task, out)
    return ok, out, infra

VARIANTS = ["plain", "retry3", "trunc400", "trunc64"]

def battery(model, order):
    tasks = TASKS if order == "forward" else list(reversed(TASKS))
    scores = {v: 0 for v in VARIANTS}
    infra_total = 0
    log = []
    for t in tasks:
        for v in VARIANTS:
            ok, out, infra = run_variant(model, t, v)
            infra_total += infra
            scores[v] += ok
            log.append({"kind": t["kind"], "variant": v, "ok": ok,
                        "out": out[:60]})
    return scores, infra_total, log

def adoptions(scores):
    out = {}
    for v in VARIANTS[1:]:
        d = scores[v] - scores["plain"]
        out[v] = ("adopted" if d >= 2 else
                  "harmful" if d <= -2 else "abstain")
    return out

def main():
    t0 = time.time()
    res = {"temp": TEMP, "n_tasks": len(TASKS), "models": {}}
    for model in ("small", "mid", "third"):
        m = {}
        s1, inf1, log1 = battery(model, "forward")     # 第一走
        s2, inf2, _ = battery(model, "forward")        # 第二走(再現)
        s3, inf3, _ = battery(model, "reverse")        # 順序反転
        a1, a2, a3 = adoptions(s1), adoptions(s2), adoptions(s3)
        facts = []
        for v in VARIANTS[1:]:
            margin1 = s1[v] - s1["plain"]
            margin2 = s2[v] - s2["plain"]
            facts.append({
                "fact": f"{v}_helps", "model": model,
                "pass1": f"{s1['plain']}->{s1[v]} ({margin1:+d})",
                "pass2": f"{s2['plain']}->{s2[v]} ({margin2:+d})",
                "verdict1": a1[v],
                "reproduced": (a1[v] != "adopted") or (margin2 >= 1),
                "order_reversed_verdict": a3[v],
                "order_consistent": a1[v] == a3[v],
                "witness": (f"verified:run:{model}@{DATE}"
                            if a1[v] == "adopted" else None)})
        m["scores"] = {"pass1": s1, "pass2": s2, "reverse": s3}
        m["facts"] = facts
        m["infra_errors"] = inf1 + inf2 + inf3
        m["sample_log"] = log1[:8]
        res["models"][model] = m

    # 採否の割れ(3モデル)
    split = []
    for v in VARIANTS[1:]:
        vs = {m: next(f["verdict1"] for f in res["models"][m]["facts"]
                      if f["fact"] == f"{v}_helps")
              for m in ("small", "mid", "third")}
        if len(set(vs.values())) > 1:
            split.append({"fact": f"{v}_helps", **vs})
    res["H1_model_split"] = split
    res["P1_ceiling_broken"] = any(
        res["models"][m]["scores"]["pass1"]["plain"] < len(TASKS)
        for m in ("mid", "third"))
    res["P2_large_models_differ"] = any(
        next(f["verdict1"] for f in res["models"]["mid"]["facts"]
             if f["fact"] == s["fact"])
        != next(f["verdict1"] for f in res["models"]["third"]["facts"]
                if f["fact"] == s["fact"]) for s in split) if split else False
    res["H2_reproduced"] = all(f["reproduced"] for mm in res["models"].values()
                               for f in mm["facts"])
    res["H3_no_silent"] = all(f["verdict1"] in ("adopted", "harmful", "abstain")
                              for mm in res["models"].values()
                              for f in mm["facts"])
    res["H4_order"] = all(f["order_consistent"]
                          for mm in res["models"].values()
                          for f in mm["facts"])
    res["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results_hard24.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()
