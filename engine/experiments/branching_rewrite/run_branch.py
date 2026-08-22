# -*- coding: utf-8 -*-
"""分岐のある書き換え — PREREG.md が事前登録。決定論・読み取り専用。"""
import json, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verantyx.lean_witness import lean_binary, verify
from verantyx.rewrite_kernel import default_algebra_rules, simplify

VARS = ["a", "b", "c"]

def gen(rng, depth=0):
    """線形整数式。掛け算は定数(0/1)とだけ — omega が判定できる範囲に保つ。"""
    if depth >= 3 or rng.random() < 0.3:
        return rng.choice(VARS + ["0", "1"])
    op = rng.choice(["+", "-", "*", "+", "-"])
    l = gen(rng, depth + 1)
    if op == "*":
        # 変数×変数は非線形になるので、片側を定数に固定する
        return "(%s * %s)" % (l, rng.choice(["0", "1"]))
    return "(%s %s %s)" % (l, op, gen(rng, depth + 1))

def size(s):
    return sum(1 for ch in s if ch not in "() ")

def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"})); return
    rng = random.Random(20260819)
    rules = default_algebra_rules()
    exprs, seen = [], set()
    while len(exprs) < 200:
        e = gen(rng)
        if e not in seen and size(e) >= 4:
            seen.add(e); exprs.append(e)
    t0 = time.time()
    res = {"n": len(exprs), "answer": 0, "budget": 0, "unparsed": 0,
           "verified": 0, "unproven": 0, "shrink_num": 0.0, "shrink_den": 0}
    unsound, stuck = [], []
    for e in exprs:
        r = simplify(e, rules)
        v = str(r.get("verdict"))
        if v == "UNKNOWN_BUDGET":
            res["budget"] += 1; stuck.append(e); continue
        if v != "ANSWER":
            res["unparsed"] += 1; continue
        res["answer"] += 1
        out = r.get("term")
        res["shrink_num"] += size(e) / max(1, size(out)); res["shrink_den"] += 1
        lv = verify("theorem t (a b c : Int) : %s = %s := by omega" % (e, out))
        if str(lv.get("verdict")) == "VERIFIED":
            res["verified"] += 1
        else:
            res["unproven"] += 1
            unsound.append({"expr": e, "simplified": out,
                            "lean": lv.get("verdict"),
                            "steps": [s["rule"] for s in r.get("steps", [])][:8]})
    res["answer_rate"] = round(100.0 * res["answer"] / res["n"], 1)
    res["sound_rate"] = (round(100.0 * res["verified"] / res["answer"], 1)
                         if res["answer"] else None)
    res["mean_shrink"] = (round(res["shrink_num"] / res["shrink_den"], 2)
                          if res["shrink_den"] else None)
    res["seconds"] = round(time.time() - t0, 1)
    res["unsound_examples"] = unsound[:5]
    res["stuck_examples"] = stuck[:5]
    del res["shrink_num"], res["shrink_den"]
    print(json.dumps(res, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()
