"""AC正規化を比較に足したら G7/G8 が解けるか。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path.home()/"Projects/Verantyx-Vera-alpha"))
sys.path.insert(0, str(Path.home()/"Projects/Verantyx-Vera-alpha/experiments/search"))
from run_search import DEFS, GOALS, LEAN, generalise, sub, vars_of, store
from verantyx.rewrite_kernel import parse_term, simplify, term_to_str
from verantyx.lean_witness import verify

AC_OPS = ("add", "mul")

def _flat(t, op):
    if isinstance(t, tuple) and t[0] == op and len(t) == 3:
        return _flat(t[1], op) + _flat(t[2], op)
    return [ac(t)]

def ac(t):
    """AC 演算子の入れ子を平坦化し、整列して右結合で組み直す。"""
    if isinstance(t, tuple) and t[0] in AC_OPS and len(t) == 3:
        parts = sorted(_flat(t, t[0]),
                       key=lambda x: x if isinstance(x, str) else term_to_str(x))
        out = parts[-1]
        for p in reversed(parts[:-1]):
            out = (t[0], p, out)
        return out
    if isinstance(t, tuple):
        return (t[0],) + tuple(ac(x) for x in t[1:])
    return t

def nf_ac(e, rules, oriented):
    r = simplify(e, store(rules), oriented=oriented or None, budget=600)
    if str(r.get("verdict")) != "ANSWER":
        return None
    return ac(parse_term(r.get("term")))

def try_prove(lhs, rhs, rules, oriented, stats):
    stats["nodes"] += 1
    a, b = nf_ac(lhs, rules, oriented), nf_ac(rhs, rules, oriented)
    if a is not None and b is not None and a == b:
        return True, "direct"
    for v in vars_of(lhs, rhs):
        stats["nodes"] += 1
        b0 = nf_ac(sub(lhs,v,"0"), rules, oriented)
        b1 = nf_ac(sub(rhs,v,"0"), rules, oriented)
        if b0 is None or b1 is None or b0 != b1:
            continue
        ih = [("IH", generalise(sub(lhs,v,"k")), generalise(sub(rhs,v,"k")))]
        s0 = nf_ac(sub(lhs,v,"s(k)"), rules+ih, oriented)
        s1 = nf_ac(sub(rhs,v,"s(k)"), rules+ih, oriented)
        if s0 is not None and s1 is not None and s0 == s1:
            return True, "induction on %s" % v
    return False, None

def run(use_ac, oriented_all, label):
    rules=list(DEFS); oriented=[]; proven=[]; stats={"nodes":0}; rounds=0
    pending=list(GOALS)
    while True:
        rounds+=1; got=[]
        for name,l,r in pending:
            ok,_ = (try_prove(l,r,rules,oriented,stats) if use_ac
                    else try_prove(l,r,rules,oriented,stats))
            if ok:
                proven.append(name); gl,gr=generalise(l),generalise(r)
                rules.append((name,gl,gr))
                if oriented_all and name in ("G3","G4","G8"): oriented.append(name)
                got.append(name)
        pending=[g for g in pending if g[0] not in proven]
        if not got or not pending: break
    return {"label":label,"proved":proven,"unproved":[g[0] for g in pending],
            "rounds":rounds,"nodes":stats["nodes"],"oriented":oriented}

t0=time.time()
out={"arms":[run(True, True, "AC正規化 + G3/G4/G8向き付け")]}
ver=uns=0; bad=[]
for a in out["arms"]:
    for n in a["proved"]:
        v=verify(LEAN[n])
        if str(v.get("verdict"))=="VERIFIED": ver+=1
        else: uns+=1; bad.append({"goal":n,"lean":v.get("verdict")})
out["lean_verified"]=ver; out["unsound"]=uns; out["unsound_detail"]=bad
out["seconds"]=round(time.time()-t0,1)
for a in out["arms"]:
    print("%s\n  証明 %s\n  未証明 %s (巡%d ノード%d)" % (
        a["label"], ",".join(a["proved"]) or "なし",
        ",".join(a["unproved"]) or "なし", a["rounds"], a["nodes"]))
print("\nLean検査:", ver, "| 不健全:", uns, bad)
Path("/private/tmp/claude-501/-Users-motonishikoudai-Projects-Vera/c56bbede-f983-4538-b2e5-cfeeaec5c491/scratchpad/ac.json").write_text(json.dumps(out,ensure_ascii=False,indent=1))
