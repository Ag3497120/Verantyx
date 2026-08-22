import itertools, json, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path.home()/"Projects/Verantyx-Vera-alpha"))
sys.path.insert(0, str(Path.home()/"Projects/Verantyx-Vera-alpha/experiments/ordered_rewrite"))
from run_ordered import simplify_ordered, gen
from verantyx.rewrite_kernel import default_algebra_rules
from verantyx.lean_witness import verify

rng = random.Random(20260819)
exprs, seen = [], set()
while len(exprs) < 60:
    e = gen(rng)
    if e not in seen and sum(1 for c in e if c not in "() ") >= 4:
        seen.add(e); exprs.append(e)

SYM = [("add_comm","?a + ?b","?b + ?a"),
       ("mul_comm","?a * ?b","?b * ?a"),
       ("add_assoc_l","(?a + ?b) + ?c","?a + (?b + ?c)"),
       ("mul_assoc_l","(?a * ?b) * ?c","?a * (?b * ?c)")]

def arm(extra, ordered):
    rs = default_algebra_rules()
    for n,l,r in extra: rs.add(n,l,r)
    comm = {n for n,_,_ in extra} if ordered else set()
    res = {"answer":0,"budget":0,"verified":0,"unsound":0}
    for e in exprs:
        r = simplify_ordered(e, rs, comm)
        v = str(r.get("verdict"))
        if v == "UNKNOWN_BUDGET": res["budget"] += 1; continue
        if v != "ANSWER": continue
        res["answer"] += 1
        lv = verify("theorem t (a b c : Int) : %s = %s := by omega" % (e, r["term"]))
        if str(lv.get("verdict"))=="VERIFIED": res["verified"] += 1
        else: res["unsound"] += 1
    return res

out = {"n": len(exprs)}
t0=time.time()
out["対称4規則_無向き"] = arm(SYM, False)
out["対称4規則_向き付き"] = arm(SYM, True)
# 正準性: a+b+c の全順列が一つの形に落ちるか
rs = default_algebra_rules()
for n,l,r in SYM: rs.add(n,l,r)
forms = set()
for p in itertools.permutations(["a","b","c"]):
    for shape in ("(%s + (%s + %s))", "((%s + %s) + %s)"):
        e = shape % p
        r = simplify_ordered(e, rs, {n for n,_,_ in SYM})
        forms.add(r.get("term") if str(r.get("verdict"))=="ANSWER" else "BUDGET")
out["a+b+c の12通り→正規形の種類"] = sorted(forms)
out["正準形か"] = (len(forms) == 1)
out["seconds"] = round(time.time()-t0,1)
print(json.dumps(out, ensure_ascii=False, indent=1))
