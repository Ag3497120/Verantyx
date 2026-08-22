# -*- coding: utf-8 -*-
"""Lean core の List 補題を我々の署名に写す — PREREG11 の輸入器。

出所: ~/.elan/toolchains/<ver>/src/lean/Init/Data/List/*.lean
(List.length_append 等の基礎は mathlib でなく core に居る — 実測)。

輸入の門は二段(リストでは多項式同一性が決定手続きにならないため):
  (a) 接地検査 — 偽(仮説つき定理の無条件化)を反例つきで落とす
  (b) 規則ごとのEan 個別検証 — 我々の項から自動翻訳した文をこの機体の
      Lean が VERIFIED にしたものだけ輸入(証人 verified:lean4:local)。
      パースの誤りがあっても、輸入されるのは検証された文そのもの。
閉じた文法: 識別子・++・::・[]・.length・.reverse・+・*・数字・括弧。
文法の外は不搭載(開いた賢さは持ち込まない)。
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prover import VAR_TYPES, ground_check, infer_type, term_to_str
from run_confirm import lean_lemma

TOOLCHAIN = (Path.home() / ".elan" / "toolchains"
             / "leanprover--lean4---v4.34.0-rc1" / "src" / "lean"
             / "Init" / "Data" / "List")
OUT = (Path.home() / "Projects" / "vera-corpus" / "build"
       / "mathlib_list_rules.json")

DECL = re.compile(
    r"^(?:@\[[^\]]*\]\s*)?(?:protected\s+|private\s+|noncomputable\s+)*"
    r"(?:theorem|lemma)\s+([A-Za-z0-9_.'«»]+)")
NS_OPEN = re.compile(r"^namespace\s+([A-Za-z0-9_.']+)")
_TOK = re.compile(r"\+\+|::|\[\]|\.length|\.reverse|[()+*]|"
                  r"[A-Za-z_][A-Za-z0-9_'!?₀-₉]*|\d+")

L_POOL = ["x", "y", "z", "l", "m"]
N_POOL = ["a", "b", "c", "n"]


def nat_lit(n: int):
    t = "0"
    for _ in range(n):
        t = ("s", t)
    return t


class P:
    """閉じた文法の再帰下降パーサ(Lean の優先度: * 70 / :: 67 / + ++ 65)。"""

    def __init__(self, toks, env):
        self.t = toks
        self.i = 0
        self.env = env      # 元変数名 → 我々の変数名

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def eat(self):
        self.i += 1
        return self.t[self.i - 1]

    def atom(self):
        tok = self.peek()
        if tok is None:
            return None
        if tok == "(":
            self.eat()
            e = self.level_add()
            if self.peek() != ")":
                return None
            self.eat()
        elif tok == "[]":
            self.eat()
            e = "nil"
        elif re.fullmatch(r"\d+", tok):
            self.eat()
            n = int(tok)
            if n > 3:
                return None
            e = nat_lit(n)
        elif tok in self.env:
            self.eat()
            e = self.env[tok]
        else:
            return None
        while self.peek() in (".length", ".reverse"):
            e = ("len" if self.eat() == ".length" else "rev", e)
        return e

    def level_mul(self):
        e = self.atom()
        if e is None:
            return None
        while self.peek() == "*":
            self.eat()
            r = self.atom()
            if r is None:
                return None
            e = ("mul", e, r)
        return e

    def level_cons(self):
        e = self.level_mul()
        if e is None:
            return None
        if self.peek() == "::":
            self.eat()
            r = self.level_cons()      # 右結合
            if r is None:
                return None
            return ("cons", e, r)
        return e

    def level_add(self):
        parts = [self.level_cons()]
        ops = []
        if parts[0] is None:
            return None
        while self.peek() in ("+", "++"):
            ops.append(self.eat())
            nxt = self.level_cons()
            if nxt is None:
                return None
            parts.append(nxt)
        if not ops:
            return parts[0]
        if all(o == "+" for o in ops):       # 左結合
            e = parts[0]
            for r in parts[1:]:
                e = ("add", e, r)
            return e
        if all(o == "++" for o in ops):      # 右結合
            e = parts[-1]
            for l in reversed(parts[:-1]):
                e = ("app", l, e)
            return e
        return None                           # + と ++ の混在は文法の外


def parse_side(text: str, env) -> object:
    toks = _TOK.findall(text)
    if "".join(toks).replace(" ", "") != re.sub(r"\s+", "", text):
        return None
    p = P(toks, env)
    e = p.level_add()
    return e if e is not None and p.i == len(p.t) else None


_BINDER_VAR = re.compile(r"^[({⦃]\s*([A-Za-zα-ω][A-Za-z0-9_'₀-₉ ]*)\s*:\s*"
                         r"([^)}⦄]+?)\s*[)}⦄]$")
_FORALL = re.compile(r"^∀\s+([A-Za-zα-ω][A-Za-z0-9_'₀-₉ ]*)\s*:\s*"
                     r"([^,]+),\s*(.*)$")


def collect_vars(binders, stmt):
    """束縛から (元名→型) を読む。List系→L、ℕ/α→N。仮説は無視(門が決める)。"""
    tenv = {}
    for b in binders:
        m = _BINDER_VAR.match(" ".join(b.split()))
        if not m:
            continue
        ty = m.group(2).strip()
        kind = ("L" if ty.startswith("List") else
                "N" if ty in ("ℕ", "Nat", "α", "β") else None)
        if kind:
            for v in m.group(1).split():
                tenv[v] = kind
    while True:
        m = _FORALL.match(stmt)
        if not m:
            break
        ty = m.group(2).strip()
        kind = ("L" if ty.startswith("List") else
                "N" if ty in ("ℕ", "Nat", "α", "β") else None)
        if kind is None:
            return None, None
        for v in m.group(1).split():
            tenv[v] = kind
        stmt = m.group(3).strip()
    return tenv, stmt


def theorems(path: Path):
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    stack = []
    i = 0
    while i < len(lines):
        ns = NS_OPEN.match(lines[i])
        if ns:
            stack.append(ns.group(1))
            i += 1
            continue
        if re.match(r"^end\b", lines[i]) and stack:
            stack.pop()
            i += 1
            continue
        m = DECL.match(lines[i])
        if not m:
            i += 1
            continue
        name = ".".join(stack + [m.group(1)])
        block = lines[i][m.end():]
        j = i + 1
        while ":=" not in block and " := " not in block and j < len(lines) \
                and j - i < 10:
            block += " " + lines[j]
            j += 1
        header = block.split(":=")[0]
        # 束縛グループを貪欲に読み、深さ0の : で型部へ
        from tools_shim import split_binders_and_type
        parsed = split_binders_and_type(header)
        if parsed:
            binders, stmt = parsed
            yield name, binders, " ".join(stmt.split()), i + 1
        i = j if j > i + 1 else i + 1


def main():
    t0 = time.time()
    rules, rejected = [], []
    seen = set()
    for p in sorted(TOOLCHAIN.glob("*.lean")):
        for name, binders, stmt, line in theorems(p):
            key = ("list." + name).casefold()
            if key in seen:
                continue
            seen.add(key)
            tenv, body = collect_vars(binders, stmt)
            if tenv is None or body is None or "=" not in body \
                    or body.count("=") != 1:
                continue
            # 元変数 → 我々の閉じた変数名
            env, lp, np_ = {}, list(L_POOL), list(N_POOL)
            ok = True
            for v, k in tenv.items():
                pool = lp if k == "L" else np_
                if not pool:
                    ok = False
                    break
                env[v] = pool.pop(0)
            if not ok:
                continue
            l_txt, r_txt = (s.strip() for s in body.split("="))
            tl, tr = parse_side(l_txt, env), parse_side(r_txt, env)
            if tl is None or tr is None:
                continue
            te = {env[v]: k for v, k in tenv.items()}
            if infer_type(tl, te) is None or infer_type(tr, te) is None:
                continue
            gc = ground_check(tl, tr, max_cases=64)
            if gc["verdict"] == "REFUTED":
                rejected.append({"name": key, "why": "refuted",
                                 "witness": gc.get("witness")})
                continue
            if gc["verdict"] != "PASSED":
                rejected.append({"name": key, "why": "ground_undecided"})
                continue
            lv = lean_lemma(tl, tr)
            if lv["verdict"] != "VERIFIED":
                rejected.append({"name": key, "why": "lean_undecided"})
                continue
            def pat(t):
                if isinstance(t, str) and t in VAR_TYPES:
                    return "?" + t
                if isinstance(t, tuple):
                    s = term_to_str(t)
                    for v in sorted(set(te), key=len, reverse=True):
                        s = re.sub(r"(?<![A-Za-z0-9_?])%s(?![A-Za-z0-9_])"
                                   % v, "?" + v, s)
                    return s
                return t if isinstance(t, str) else term_to_str(t)
            rules.append({"name": key, "lhs": pat(tl), "rhs": pat(tr),
                          "vars": sorted(te),
                          "witness": "verified:lean4:local",
                          "tactic": lv.get("tactic"),
                          "file": str(p.name), "line": line})
    OUT.write_text(json.dumps(
        {"votes": "none", "n_rules": len(rules), "rules": rules,
         "rejected": rejected}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(json.dumps({
        "rules": len(rules),
        "rejected": {w: sum(1 for x in rejected if x["why"] == w)
                     for w in ("refuted", "ground_undecided",
                               "lean_undecided")},
        "seconds": round(time.time() - t0, 1), "out": str(OUT)},
        ensure_ascii=False, indent=1))
    for r in rules[:20]:
        print("  ", r["name"], "|", r["lhs"], "=", r["rhs"])


if __name__ == "__main__":
    main()
