# -*- coding: utf-8 -*-
"""構造→Lean の閉ループ — PREREG.md が事前登録。決定論・読み取り専用。"""
import json, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verantyx.lean_witness import lean_binary, verify
from verantyx.rewrite_math import rewrite_add

def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"}, ensure_ascii=False))
        return
    rng = random.Random(20260819)
    pairs = [(rng.randint(0, 999), rng.randint(0, 999)) for _ in range(30)]
    t0 = time.time()
    res = {"derived": 0, "unparsed": 0, "verified": 0, "unproven": 0,
           "wrong_value": 0, "pairs": len(pairs)}
    bad = []
    for a, b in pairs:
        r = rewrite_add(a, b)
        if str(r.get("verdict")) != "ANSWER":
            res["unparsed"] += 1
            bad.append((a, b, r.get("verdict")))
            continue
        res["derived"] += 1
        c = r.get("value")
        if c != a + b:
            res["wrong_value"] += 1
            bad.append((a, b, "derived %s" % c))
        # ② Lean が独立に検査する。①の値をそのまま定理にする。
        src = "theorem t : %d + %d = %d := by decide" % (a, b, c)
        v = verify(src)
        if str(v.get("verdict")) == "VERIFIED":
            res["verified"] += 1
        else:
            res["unproven"] += 1
            bad.append((a, b, "lean:" + str(v.get("verdict"))))
    # 嘘は通らないか: 故意に1を足した結論を Lean に出す
    a, b = pairs[0]
    liar = verify("theorem t : %d + %d = %d := by decide" % (a, b, a + b + 1))
    res["liar_rejected"] = str(liar.get("verdict")) != "VERIFIED"
    res["liar_verdict"] = liar.get("verdict")
    res["seconds"] = round(time.time() - t0, 1)
    res["failures"] = bad[:6]
    print(json.dumps(res, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()
