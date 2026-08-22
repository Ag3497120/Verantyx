"""正準化で等式の同値判定ができるか — 真の等式は通り、偽は落ちるか。"""
import json, random, sys
from pathlib import Path
sys.path.insert(0, str(Path.home()/"Projects/Verantyx-Vera-alpha"))
sys.path.insert(0, str(Path.home()/"Projects/Verantyx-Vera-alpha/experiments/ordered_rewrite"))
from run_ordered import simplify_ordered, gen
from verantyx.rewrite_kernel import default_algebra_rules, parse_term
from verantyx.lean_witness import verify

SYM = [("add_comm","?a + ?b","?b + ?a"),("mul_comm","?a * ?b","?b * ?a"),
       ("add_assoc_l","(?a + ?b) + ?c","?a + (?b + ?c)"),
       ("mul_assoc_l","(?a * ?b) * ?c","?a * (?b * ?c)")]
rs = default_algebra_rules()
for n,l,r in SYM: rs.add(n,l,r)
COMM = {n for n,_,_ in SYM}

def canon(e):
    r = simplify_ordered(e, rs, COMM)
    return r.get("term") if str(r.get("verdict"))=="ANSWER" else None

rng = random.Random(4242)
TRUE, FALSE = [], []
while len(TRUE) < 40:
    e = gen(rng)
    if sum(1 for c in e if c not in "() ") < 4: continue
    # 真の等式: 同じ式に 0 を足す/1 を掛ける等の変形を施した対
    v = rng.choice(["(%s + 0)", "(1 * %s)", "(%s - 0)", "(%s * 1)", "(0 + %s)"])
    TRUE.append((e, v % e))
while len(FALSE) < 40:
    a, b = gen(rng), gen(rng)
    if a == b: continue
    FALSE.append((a, b))

res = {"true_pairs": len(TRUE), "false_pairs": len(FALSE),
       "true_judged_equal": 0, "true_missed": 0,
       "false_judged_equal": 0, "false_correctly_separated": 0,
       "false_positive_confirmed_by_lean": 0}
wrong = []
for a, b in TRUE:
    ca, cb = canon(a), canon(b)
    if ca is not None and ca == cb: res["true_judged_equal"] += 1
    else: res["true_missed"] += 1
for a, b in FALSE:
    ca, cb = canon(a), canon(b)
    if ca is not None and ca == cb:
        res["false_judged_equal"] += 1
        # 本当に等しくないのか Lean に訊く(生成が偶然同値な場合がある)
        v = verify("theorem t (a b c : Int) : %s = %s := by omega" % (a, b))
        if str(v.get("verdict")) != "VERIFIED":
            res["false_positive_confirmed_by_lean"] += 1
            wrong.append({"a": a, "b": b, "canon": ca})
    else:
        res["false_correctly_separated"] += 1
res["false_positives"] = wrong[:5]
print(json.dumps(res, ensure_ascii=False, indent=1))
