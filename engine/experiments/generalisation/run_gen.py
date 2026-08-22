# -*- coding: utf-8 -*-
"""汎化 — PREREG.md が事前登録。カーネル無改造・決定論。"""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verantyx.lean_witness import lean_binary, verify
from verantyx.rewrite_kernel import RuleStore, parse_term, simplify, term_to_str

DEFS = [("rev_nil",  "rev(nil)", "nil"),
        ("rev_cons", "rev(cons(?h, ?t))", "app(rev(?t), cons(?h, nil))"),
        ("acc_nil",  "revacc(nil, ?a)", "?a"),
        ("acc_cons", "revacc(cons(?h, ?t), ?a)", "revacc(?t, cons(?h, ?a))"),
        ("app_nil",  "app(nil, ?l)", "?l"),
        ("app_cons", "app(cons(?h, ?t), ?l)", "cons(?h, app(?t, ?l))"),
        # app の結合律(既知の補題として与える。汎化の測定が主題なので)
        ("app_assoc", "app(app(?x, ?y), ?z)", "app(?x, app(?y, ?z))")]

VAR = re.compile(r"(?<![A-Za-z0-9_])([lath])(?![A-Za-z0-9_])")

def store(rules):
    rs = RuleStore()
    for n, l, r in rules:
        rs.add(n, l, r)
    return rs

def nf(e, rules):
    r = simplify(e, store(rules), budget=400)
    return r.get("term") if str(r.get("verdict")) == "ANSWER" else None

def gen_pat(e):
    return VAR.sub(lambda m: "?" + m.group(1), e)

def sub(e, var, val):
    """**語境界つきの置換**。素の str.replace を使うと `revacc(l, nil)` の
    `nil` の中の l まで置換して `ninil` になる(2026-08-19、この実験の
    初回がそれで壊れた)。"""
    return re.sub(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(var),
                  val, e)

def induct(lhs, rhs, rules, var="l"):
    """リストの帰納: var := nil / cons(h, t)、仮定は t の形で規則に。"""
    b0 = nf(sub(lhs, var, "nil"), rules)
    b1 = nf(sub(rhs, var, "nil"), rules)
    if b0 is None or b1 is None or b0 != b1:
        return False, {"base": (b0, b1)}
    ih = [("IH", gen_pat(sub(lhs, var, "t")), gen_pat(sub(rhs, var, "t")))]
    # **二段階正規化**(2026-08-19実測)。IH を最初から混ぜると
    # leftmost-innermost が内側で早く発火し、定義による整形(結合律など)を
    # 妨げる — 正しい汎化 T' がそれで閉じなかった。まず定義だけで正規形へ
    # 落とし、**その後に IH を適用**する。探索ではなく、段の固定された順序。
    p0 = nf(sub(lhs, var, "cons(h, t)"), rules)
    p1 = nf(sub(rhs, var, "cons(h, t)"), rules)
    s0 = nf(p0, rules + ih) if p0 is not None else None
    s1 = nf(p1, rules + ih) if p1 is not None else None
    ok = s0 is not None and s1 is not None and s0 == s1
    return ok, {"base": (b0, b1), "step": (s0, s1),
                "ih": "%s -> %s" % (ih[0][1], ih[0][2])}

def auto_generalise(step_lhs, step_rhs):
    """詰まった段に現れた定数 `nil` を変数に置き換えて命題を強める。

    機械的な手順: 段の両辺に共通して現れる `nil` を新しい変数 `a` にする。
    探索でも推測でもなく、**現れた定数の一般化**。
    """
    if "nil" not in (step_lhs or "") or "nil" not in (step_rhs or ""):
        return None
    return (step_lhs.replace("nil", "a"), step_rhs.replace("nil", "a"))

def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"})); return
    t0 = time.time()
    out = {}

    # 1. T: rev(l) = revacc(l, nil) — 汎化なしで通るか
    okT, trT = induct("rev(l)", "revacc(l, nil)", DEFS)
    out["T_direct"] = {"proved": okT, "base": trT.get("base"),
                       "step": trT.get("step"), "ih": trT.get("ih")}

    # 2. T': app(rev(l), a) = revacc(l, a) — 汎化した形
    okT2, trT2 = induct("app(rev(l), a)", "revacc(l, a)", DEFS)
    out["Tprime"] = {"proved": okT2, "base": trT2.get("base"),
                     "step": trT2.get("step")}

    # 3. T' から T が出るか(a := nil)
    if okT2:
        rules2 = DEFS + [("Tp", gen_pat("app(rev(l), a)"), gen_pat("revacc(l, a)"))]
        a = nf("rev(l)", rules2)
        b = nf("revacc(l, nil)", rules2)
        # rev(l) = app(rev(l), nil) を使うので、app の右単位元が要る
        rules3 = rules2 + [("app_nil_r", "app(?x, nil)", "?x")]
        a3, b3 = nf("rev(l)", rules3), nf("revacc(l, nil)", rules3)
        out["T_from_Tprime"] = {"without_app_nil_r": (a, b, a == b and a is not None),
                                "with_app_nil_r": (a3, b3, a3 == b3 and a3 is not None)}

    # 4. 汎化は自動でできるか — 詰まった段から作れるか
    sl, sr = (trT.get("step") or (None, None))
    cand = auto_generalise(sl, sr) if sl else None
    out["auto_generalise"] = {"from_step": [sl, sr], "candidate": cand}
    if cand:
        okA, trA = induct(cand[0], cand[1], DEFS)
        out["auto_generalise"]["proved"] = okA
        out["auto_generalise"]["trace"] = {"base": trA.get("base"),
                                           "step": trA.get("step")}

    # Lean 検査
    LEAN = {
      "T": "theorem t (l : List Nat) : l.reverse = l.reverseAux [] := by simp [List.reverseAux_eq]",
      "Tprime": "theorem t (l a : List Nat) : l.reverse ++ a = l.reverseAux a := by "
                "simp [List.reverseAux_eq]",
    }
    out["lean"] = {k: verify(v).get("verdict") for k, v in LEAN.items()}
    out["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()
