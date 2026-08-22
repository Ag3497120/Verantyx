# -*- coding: utf-8 -*-
"""確認測定 — PREREG.md が事前登録。決定論・乱数なし。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from prover import (Prover, VAR_TYPES, ground_check, parse_term, t_vars,
                    term_to_str)
from verantyx.lean_witness import lean_binary, verify

CONFIRM = [
    ("C1", "rev(app(x, y))", "app(rev(y), rev(x))"),
    ("C2", "len(rev(x))", "len(x)"),
    ("C3", "app(app(x, y), z)", "app(x, app(y, z))"),
    ("C4", "mul(a, add(b, c))", "add(mul(a, b), mul(a, c))"),
]
REGRESS = [
    ("R1", "add(0, a)", "a"),
    ("R2", "add(s(a), b)", "s(add(a, b))"),
    ("R3", "add(a, b)", "add(b, a)"),
    ("R4", "add(add(a, b), c)", "add(a, add(b, c))"),
    ("R5", "mul(0, a)", "0"),
    ("R6", "mul(a, 0)", "0"),
    ("R7", "mul(s(a), b)", "add(mul(a, b), b)"),
    ("R8", "mul(a, b)", "mul(b, a)"),
]
LEAN = {
    "C1": "theorem t (x y : List Nat) : (x ++ y).reverse = y.reverse ++ x.reverse := by simp",
    "C2": "theorem t (x : List Nat) : x.reverse.length = x.length := by simp",
    "C3": "theorem t (x y z : List Nat) : (x ++ y) ++ z = x ++ (y ++ z) := by simp",
    "C4": "theorem t (a b c : Nat) : a * (b + c) = a * b + a * c := by "
          "simp [Nat.mul_add]",
    "R1": "theorem t (a : Nat) : 0 + a = a := by omega",
    "R2": "theorem t (a b : Nat) : (a+1) + b = (a + b) + 1 := by omega",
    "R3": "theorem t (a b : Nat) : a + b = b + a := by omega",
    "R4": "theorem t (a b c : Nat) : (a + b) + c = a + (b + c) := by omega",
    "R5": "theorem t (a : Nat) : 0 * a = 0 := by simp",
    "R6": "theorem t (a : Nat) : a * 0 = 0 := by simp",
    "R7": "theorem t (a b : Nat) : (a+1) * b = a * b + b := by "
          "induction b with | zero => simp | succ n ih => "
          "simp [Nat.mul_succ] at * <;> omega",
    "R8": "theorem t (a b : Nat) : a * b = b * a := by exact Nat.mul_comm a b",
}


# --- 発明した補題の Lean 訳(型駆動・閉じた表) -----------------------------
def to_lean(t):
    if isinstance(t, int):
        return str(t)
    if isinstance(t, str):
        if t == "0":
            return "0"
        if t == "nil":
            return "([] : List Nat)"
        if t in ("true", "false"):
            return t
        return t
    op = t[0]
    if op == "s":
        return "(%s + 1)" % to_lean(t[1])
    if op == "add":
        return "(%s + %s)" % (to_lean(t[1]), to_lean(t[2]))
    if op == "mul":
        return "(%s * %s)" % (to_lean(t[1]), to_lean(t[2]))
    if op == "cons":
        return "(%s :: %s)" % (to_lean(t[1]), to_lean(t[2]))
    if op == "app":
        return "(%s ++ %s)" % (to_lean(t[1]), to_lean(t[2]))
    if op == "rev":
        return "(%s).reverse" % to_lean(t[1])
    if op == "len":
        return "(%s).length" % to_lean(t[1])
    # PREREG12/13 の署名: 不等式は等式に畳まれている(le=Nat.ble)
    if op == "le":
        return "(Nat.ble %s %s)" % (to_lean(t[1]), to_lean(t[2]))
    if op == "monus":
        return "(%s - %s)" % (to_lean(t[1]), to_lean(t[2]))
    if op == "min":
        return "(Nat.min %s %s)" % (to_lean(t[1]), to_lean(t[2]))
    if op == "max":
        return "(Nat.max %s %s)" % (to_lean(t[1]), to_lean(t[2]))
    raise ValueError(op)


# omega は線形算術のみ・素の simp は乗法の結合/分配の補題を引かない。
# B9/B12(真の定理)が UNPROVEN_ALL_TACTICS になった実測を受けて、核の
# 補題を名指しする戦術を足した — 検査器の修理であって基準の変更ではない
# (induction_by_rewriting の「omega が全目標消化後に失敗」と同じ型)。
TACTICS = ["simp", "omega", "simp <;> omega",
           "simp [Nat.ble_eq] <;> omega", "simp [Nat.ble_eq]",
           # Bool=false / Bool=Bool 形(le の否定的補題)の閉じ方(実測)
           "simp only [← Bool.not_eq_true, Nat.ble_eq]; omega",
           "rw [Bool.eq_iff_iff]; simp only [Nat.ble_eq]; omega",
           # min/max: 定義展開+場合分け(omega はこの版では min/max 不可)
           "simp only [Nat.min_def, Nat.max_def] <;> "
           "repeat (first | omega | split)",
           "simp [Nat.add_mul, Nat.mul_add]",
           "simp [Nat.mul_assoc]",     # 混ぜた simp 集合は落ちる(実測) —
           "ac_rfl"]                   # 単独指定と ac_rfl が確実に閉じる


def lean_lemma(lhs, rhs):
    vs = t_vars(lhs) + [v for v in t_vars(rhs) if v not in t_vars(lhs)]
    binds = " ".join("(%s : %s)" % (v, "Nat" if VAR_TYPES[v] == "N"
                                    else "List Nat") for v in vs)
    for tac in TACTICS + [
            "induction %s with | nil => simp | cons h t ih => simp [ih]"
            % v for v in vs if VAR_TYPES[v] == "L"]:
        src = "theorem t %s : %s = %s := by %s" % (
            binds, to_lean(lhs), to_lean(rhs), tac)
        v = verify(src)
        if str(v.get("verdict")) == "VERIFIED":
            return {"verdict": "VERIFIED", "tactic": tac}
    return {"verdict": "UNPROVEN_ALL_TACTICS"}


def arm(goals, use_energy):
    out = []
    for name, l, r in goals:
        p = Prover()
        if not use_energy:
            # 対照: エネルギーを無効化(列挙順そのまま)。門は全て同じ。
            import prover as P
            _orig = P.energy
            P.energy = lambda cand, syms, led: 0.0
        t0 = time.time()
        try:
            ok, how = p.prove(parse_term(l), parse_term(r))
        finally:
            if not use_energy:
                P.energy = _orig
        out.append({"name": name, "proved": ok, "how": how,
                    "lemmas": p.stats["lemmas"], "nodes": p.stats["nodes"],
                    "invented": p.stats["invented"],
                    "lemma_terms": [(term_to_str(parse_term(x.split(": ", 1)[1].split(" = ")[0])),
                                     x.split(" = ", 1)[1])
                                    for x in p.stats["lemmas"]],
                    "seconds": round(time.time() - t0, 1)})
    return out


def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"}))
        return
    t0 = time.time()
    res = {"confirm": arm(CONFIRM, True), "regress": arm(REGRESS, True)}

    # Q1: 主張した目標の Lean 検査
    unsound = []
    ver = 0
    for group in ("confirm", "regress"):
        for g in res[group]:
            if not g["proved"]:
                continue
            v = verify(LEAN[g["name"]])
            if str(v.get("verdict")) == "VERIFIED":
                ver += 1
            else:
                unsound.append({"goal": g["name"], "lean": v.get("verdict")})
    res["lean_verified_targets"] = ver
    res["unsound"] = len(unsound)
    res["unsound_detail"] = unsound

    # Q4: 昇格補題の拡大接地再検査 + Lean 訳の検査(報告)
    import prover as P
    big_n = ["0"]
    for _ in range(4):
        big_n.append(("s", big_n[-1]))
    nats = ["0", ("s", "0")]
    big_l = ["nil"]
    for h in nats:
        big_l.append(("cons", h, "nil"))
        for g2 in nats:
            big_l.append(("cons", h, ("cons", g2, "nil")))
            for f in nats[:1]:
                big_l.append(("cons", h, ("cons", g2, ("cons", f, "nil"))))
    P._GROUND = {"N": big_n, "L": big_l}
    lemma_audit = []
    for group in ("confirm", "regress"):
        for g in res[group]:
            for l_str, r_str in g.get("lemma_terms", []):
                gc = ground_check(parse_term(l_str), parse_term(r_str),
                                  max_cases=200)
                lv = lean_lemma(parse_term(l_str), parse_term(r_str))
                lemma_audit.append({"goal": g["name"],
                                    "lemma": "%s = %s" % (l_str, r_str),
                                    "ground": gc["verdict"],
                                    "lean": lv.get("verdict"),
                                    "tactic": lv.get("tactic")})
    res["lemma_audit"] = lemma_audit
    res["lemma_refuted"] = sum(1 for a in lemma_audit
                               if a["ground"] == "REFUTED")

    # 参考: エネルギー無効の対照(採否に使わない)
    res["ablation_no_energy"] = {
        "confirm": arm(CONFIRM, False), "regress": arm(REGRESS, False)}
    res["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results_confirm.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
