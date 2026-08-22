# -*- coding: utf-8 -*-
"""mathlib の文構造つき再抽出 — 名前→文・束縛・出所、および Nat 等式断片。

build_mathlib_store.py は文の識別子トークンだけを残した(検索には健全、
在庫には不足)。ここでは := の前の宣言ヘッダを丸ごと取り、束縛部と型部に
割って保存する。等式断片は閉じた文法(識別子・数字・+ * - ・括弧)だけを
通し、書き換え核のパターン規則に変換する — 開いた賢さは持ち込まない。

出力(全て票なしのサイドカー):
  vera-corpus/build/mathlib_statements.json   name → {stmt, binders, file, line}
  vera-corpus/build/mathlib_eq_rules.json     Nat等式断片(核パターン形式)
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.rewrite_kernel import parse_term

ROOT = Path.home() / "Projects" / "vera-corpus"
MATHLIB = ROOT / "corpora" / "mathlib4"
OUT_STMT = ROOT / "build" / "mathlib_statements.json"
OUT_EQ = ROOT / "build" / "mathlib_eq_rules.json"
STORE = ROOT / "build" / "mathlib_store.json"

DECL = re.compile(
    r"^(@\[[^\]]*\]\s*)?(?:protected\s+|private\s+|noncomputable\s+)*"
    r"(?:theorem|lemma)\s+([A-Za-z0-9_.'«»]+)")
_TO_ADDITIVE = re.compile(r"to_additive(?:\s+\(?[a-z_]+\)?)?"
                          r"(?:\s+([A-Za-z0-9_.'«»]+))?")
NS_OPEN = re.compile(r"^namespace\s+([A-Za-z0-9_.']+)")
NS_CLOSE = re.compile(r"^end(\s+([A-Za-z0-9_.']+))?\s*$")

#: 束縛グループ: (n m : ℕ) / {a : α} / [inst : Group G]
BINDER = re.compile(r"^\s*([({\[⦃])")
_CLOSE = {"(": ")", "{": "}", "[": "]", "⦃": "⦄"}


def split_header(header: str):
    """'NAME の後ろ' を束縛列と型部に割る。深さ0の最初の : が型コロン。"""
    binders = []
    i = 0
    n = len(header)
    while i < n:
        while i < n and header[i].isspace():
            i += 1
        if i >= n:
            break
        m = BINDER.match(header[i:])
        if not m:
            break
        open_ch = m.group(1)
        close_ch = _CLOSE[open_ch]
        depth = 0
        j = i
        while j < n:
            if header[j] == open_ch:
                depth += 1
            elif header[j] == close_ch:
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= n:
            return None
        binders.append(header[i:j + 1])
        i = j + 1
    while i < n and header[i].isspace():
        i += 1
    if i >= n or header[i] != ":":
        return None
    return binders, header[i + 1:].strip()


_SECTION = re.compile(r"^section(\s+[A-Za-z0-9_.']+)?\s*$")
_VARIABLE = re.compile(r"^variable[s]?\s+(.*)$")
_CLASS = re.compile(r"^(?:@\[[^\]]*\]\s*)?class\s+([A-Za-z0-9_.'₀-₉]+)")
_FIELD = re.compile(r"^\s{2,}(?:protected\s+)?([a-z][A-Za-z0-9_']*)\s*:"
                    r"\s*(∀.+)$")


def class_fields(path: Path):
    """`class X … where` のフィールド(∀ 形の等式公理)を定理と同格に拾う。

    zero_mul / mul_zero / zero_add 等は mathlib では定理でなくクラスの
    フィールド — 旧抽出の「クラスのフィールドは構造上不在」の穴
    (PREREG8)。健全性は呼び出し側の決定門が持つ。
    """
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    i = 0
    while i < len(lines):
        m = _CLASS.match(lines[i])
        if not m:
            i += 1
            continue
        cls = m.group(1)
        # where までヘッダを辿る(extends 節が複数行のことがある)
        j = i
        while j < len(lines) and "where" not in lines[j] and j - i < 8:
            j += 1
        j += 1
        # インデントされたフィールド行を読む(空行は許す、dedent で終了)
        while j < len(lines):
            ln = lines[j]
            if ln.strip() == "":
                j += 1
                continue
            if not ln.startswith("  "):
                break
            f = _FIELD.match(ln)
            if f:
                yield f"{cls}.{f.group(1)}", f.group(2).strip(), j + 1
            j += 1
        i = j


def _binder_groups(text: str):
    """テキスト先頭から束縛グループの列を貪欲に読む(split_header と同じ走査)。"""
    out = []
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        m = BINDER.match(text[i:])
        if not m:
            break
        open_ch = m.group(1)
        close_ch = _CLOSE[open_ch]
        depth = 0
        j = i
        while j < n:
            if text[j] == open_ch:
                depth += 1
            elif text[j] == close_ch:
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= n:
            break
        out.append(text[i:j + 1])
        i = j + 1
    return out


def theorems_with_statements(path: Path):
    """宣言を、名前空間と section の variable 束縛(スコープ追跡)込みで読む。

    mathlib は束縛の大半を section の `variable` 行に置く
    (`variable [CommMagma G]` → `theorem mul_comm : ∀ a b : G, …`)。
    スコープ追跡は近似(named end の照合は namespace のみ厳密)であり、
    誤帰属は下流の数値接地検査が捕まえる — 検査の無い輸入はしない。
    """
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    stack = []          # (kind, name, [binder groups])
    i = 0
    while i < len(lines):
        line = lines[i]
        ns = NS_OPEN.match(line)
        if ns:
            stack.append(("ns", ns.group(1), []))
            i += 1
            continue
        if _SECTION.match(line):
            nm = _SECTION.match(line).group(1)
            stack.append(("sec", nm.strip() if nm else None, []))
            i += 1
            continue
        closed = NS_CLOSE.match(line)
        if closed and stack:
            nm = closed.group(2)
            if nm is None or (stack and stack[-1][1] == nm):
                stack.pop()
            else:
                # 名前つき end が積の途中を指す — 一致する所まで巻き戻す
                for k in range(len(stack) - 1, -1, -1):
                    if stack[k][1] == nm:
                        del stack[k:]
                        break
            i += 1
            continue
        mv = _VARIABLE.match(line)
        if mv and stack:
            stack[-1][2].extend(_binder_groups(mv.group(1)))
            i += 1
            continue
        m = DECL.match(line)
        if not m:
            i += 1
            continue
        # 属性は宣言の前行に居ることも多い(@[simp]\n theorem …)
        attr_text = m.group(1) or ""
        k = i - 1
        while k >= 0 and (lines[k].strip().startswith("@[")
                          or (attr_text == "" and lines[k].strip() == "")):
            if lines[k].strip().startswith("@["):
                attr_text = lines[k].strip() + " " + attr_text
            k -= 1
        ns_prefix = [s[1] for s in stack if s[0] == "ns" and s[1]]
        name = ".".join(ns_prefix + [m.group(2)])
        block = line[m.end():]
        j = i + 1
        while ":=" not in block and j < len(lines) and j - i < 12:
            block += " " + lines[j]
            j += 1
        header = block.split(":=")[0].strip()
        parsed = split_header(header)
        if parsed is not None:
            binders, stmt = parsed
            scope_binders = [g for s in stack for g in s[2]]
            ta = _TO_ADDITIVE.search(attr_text)
            twin = None
            if ta:
                twin = (".".join(ns_prefix + [ta.group(1)]) if ta.group(1)
                        else name + ".to_additive")
            yield (name, scope_binders + binders,
                   " ".join(stmt.split()), i + 1, twin)
        i = j if j > i + 1 else i + 1


# ---------------------------------------------------------------------------
# 等式断片 — 決定手続きの門
# ---------------------------------------------------------------------------
# 実測の経緯: ①(n m : ℕ) 明示のNat等式は mathlib4 に実質存在しない
# (初回18本の正体はテスト治具)。②実物は section の variable 束縛 +
# ∀ 前置の型クラス一般形(mul_comm = ∀ a b : G, a * b = b * a)。
# ③型クラス許可表は不要になった: この断片(変数・数字・+・*・括弧のみ)
# では**多項式同一性検査が決定手続き**になる — 両辺は ℕ⊂ℤ(整域)上の
# 多項式で、各変数の次数上限 d に対し 0..d+1 の格子で一致すれば恒等式、
# 一点でも食い違えば反例つきで偽。仮説束縛(h : a = 0 等)を無視して
# 無条件輸入しても、無条件では偽になる等式をこの門が必ず落とす。
# 門が判定できない(規模超過)ものは輸入しない — 主張しない。
_TYPE_BINDER = re.compile(
    r"^\{\s*([A-Za-zα-ωΑ-Ω][A-Za-z0-9_'α-ωΑ-Ω]*(?:\s+[A-Za-zα-ωΑ-Ω]"
    r"[A-Za-z0-9_'α-ωΑ-Ω]*)*)\s*:\s*Type[^}]*\}$")
_VAR_BINDER = re.compile(r"^[({⦃]\s*([a-z][a-z0-9' ]*)\s*:\s*"
                         r"([^)}⦄]+?)\s*[)}⦄]$")
_FORALL = re.compile(r"^∀\s+([a-z][a-z0-9' ]*)\s*:\s*([^,]+),\s*(.*)$")
#: 1文字(ラテン/ギリシャ)の型名は型変数と見なす。外側スコープの
#: {G : Type*} を近似追跡が落とす実測への対処で、誤受理しても
#: 格子門(決定手続き)が ℕ 上の真偽を決めるため健全性は崩れない。
_TYPEVAR_NAME = re.compile(r"^[A-Zα-ωΑ-Ω][₀-₉0-9']?$")
#: 減算・除算は含めない — ℕ の減算は切り捨てで、多項式でなくなる。
_EQ_BODY = re.compile(r"^[A-Za-z0-9_'+* ()]+$")
MAX_GRID_EVALS = 20000


def _eval_term(t, env):
    if isinstance(t, int):
        return t
    if isinstance(t, str):
        return env[t]
    if t[0] == "+":
        return _eval_term(t[1], env) + _eval_term(t[2], env)
    if t[0] == "*":
        return _eval_term(t[1], env) * _eval_term(t[2], env)
    raise ValueError(t[0])


def _grid_decides(pl: str, pr: str, vs):
    """多項式同一性の決定: 一致→True、反例→False、規模超過→None。"""
    import itertools
    tl, tr = parse_term(pl.replace("?", "")), parse_term(pr.replace("?", ""))
    if tl is None or tr is None:
        return None
    deg = max(pl.count("*"), pr.count("*")) + 1
    pts = range(deg + 2)
    if (deg + 2) ** max(1, len(vs)) > MAX_GRID_EVALS:
        return None
    for combo in itertools.product(pts, repeat=len(vs)):
        env = dict(zip(vs, combo))
        try:
            if _eval_term(tl, env) != _eval_term(tr, env):
                return False
        except (KeyError, ValueError):
            return None
    return True


def nat_eq_rule(name: str, binders, stmt: str):
    """決定門を通る等式を ℕ の核パターン規則へ。通らなければ None。"""
    vs: list = []
    type_vars: set = set()
    for b in binders:
        bt = " ".join(b.split())
        m = _TYPE_BINDER.match(bt)
        if m:
            type_vars |= set(m.group(1).split())
            continue
        m = _VAR_BINDER.match(bt)
        if m:
            ty = m.group(2).strip()
            if (ty in ("ℕ", "Nat") or ty in type_vars
                    or _TYPEVAR_NAME.match(ty)):
                vs += m.group(1).replace("'", "_p").split()
            continue          # 仮説・インスタンス束縛は無視 — 門が決める
    # ∀ 前置(入れ子可)を剥がして変数に足す
    while True:
        m = _FORALL.match(stmt)
        if not m:
            break
        ty = m.group(2).strip()
        if not (ty in ("ℕ", "Nat") or ty in type_vars
                or _TYPEVAR_NAME.match(ty)):
            return None
        vs += m.group(1).replace("'", "_p").split()
        stmt = m.group(3).strip()
    if not vs or "=" not in stmt or stmt.count("=") != 1:
        return None
    lhs, rhs = (s.strip() for s in stmt.split("="))
    if not (_EQ_BODY.match(lhs) and _EQ_BODY.match(rhs)):
        return None
    def to_pat(side: str) -> str:
        s = side.replace("'", "_p")
        for v in sorted(set(vs), key=len, reverse=True):
            s = re.sub(r"(?<![A-Za-z0-9_?])%s(?![A-Za-z0-9_])" % re.escape(v),
                       "?" + v, s)
        return s
    pl, pr = to_pat(lhs), to_pat(rhs)
    # 変数以外の識別子(関数呼び出し等)が残る文は断片の外(succ/min 等)
    leftover = re.findall(r"(?<!\?)\b[A-Za-z_][A-Za-z0-9_.]*", pl + " " + pr)
    if leftover:
        return None
    if parse_term(pl) is None or parse_term(pr) is None:
        return None
    used = sorted({v for v in set(vs)
                   if re.search(r"\?%s(?![A-Za-z0-9_])" % re.escape(v),
                                pl + " " + pr)})
    decided = _grid_decides(pl, pr, used)
    if decided is not True:
        # False = 無条件では偽(仮説つき定理の無条件化) / None = 判定不能
        return {"__rejected__": ("refuted" if decided is False
                                 else "undecided"), "name": name}
    return {"name": name, "lhs": pl, "rhs": pr, "vars": used}


def main():
    t0 = time.time()
    store = json.loads(STORE.read_text(encoding="utf-8"))
    known = set(store.get("crosses", {}))
    witnessed = {k for k, f in store.get("crosses", {}).items()
                 if any(str(x).startswith("verified:lean4") for x in f)}

    stmts = {}
    eq_rules = []
    rejected = []
    # Mathlib/ を先に読む — .lake/packages(外部)が辞書順で先に来ると、
    # 同名 dedup が本物の mul_comm を食う(実測: 断片5本の原因)。
    files = sorted(MATHLIB.rglob("*.lean"),
                   key=lambda p: (0 if str(p.relative_to(MATHLIB))
                                  .startswith("Mathlib/") else 1, str(p)))
    for p in files:
        rel = str(p.relative_to(MATHLIB))
        # テスト・カウンタ例のディレクトリは断片に入れない(実測: 初回の
        # 「Nat等式18本」の正体はテスト治具だった)
        is_fixture = rel.split("/")[0].casefold() in (
            "test", "counterexamples", "archive", "cache", "scripts")
        for name, binders, stmt, line, twin in theorems_with_statements(p):
            key = name.casefold()
            if key in stmts:
                continue
            stmts[key] = {"stmt": stmt, "binders": binders,
                          "file": rel, "line": line}
            if is_fixture or not rel.startswith("Mathlib/") \
                    or rel.startswith("Mathlib/Tactic"):
                continue
            r = nat_eq_rule(key, binders, stmt)
            if r is None:
                continue
            if "__rejected__" in r:
                rejected.append({"name": key, "why": r["__rejected__"]})
                continue
            eq_rules.append(r)
            # @[to_additive] の加法双子: * → + / 1 → 0 の閉じた写像で導出
            # し、同じ格子門(決定手続き)を通す — 写像が雑でも偽は落ちる
            # (実測: two_mul の双子 2+n=n+n は門が反駁して入らない)。
            if twin:
                tl = re.sub(r"(?<![0-9])1(?![0-9])", "0",
                            r["lhs"].replace("*", "+"))
                tr = re.sub(r"(?<![0-9])1(?![0-9])", "0",
                            r["rhs"].replace("*", "+"))
                if _grid_decides(tl, tr, r["vars"]) is True and \
                        parse_term(tl) is not None:
                    eq_rules.append({"name": twin.casefold(), "lhs": tl,
                                     "rhs": tr, "vars": r["vars"],
                                     "derived": "to_additive:" + key})
                else:
                    rejected.append({"name": twin.casefold(),
                                     "why": "twin_refuted_or_unparsed"})

    # クラスフィールド(PREREG8): 定理と同格に、同じ決定門を通す
    for p in files:
        rel = str(p.relative_to(MATHLIB))
        if not rel.startswith("Mathlib/") or rel.startswith("Mathlib/Tactic"):
            continue
        for fname, stmt, line in class_fields(p):
            key = fname.casefold()
            if key in stmts:
                continue
            stmts[key] = {"stmt": stmt, "binders": [], "file": rel,
                          "line": line, "kind": "class_field"}
            r = nat_eq_rule(key, [], stmt)
            if r is None:
                continue
            if "__rejected__" in r:
                rejected.append({"name": key, "why": r["__rejected__"]})
            else:
                r["kind"] = "class_field"
                eq_rules.append(r)

    # 証人はファイル単位(旧店の kernel 検証はファイルごと): 証人つき名の
    # 居るファイル = kernel が通したファイル。その中の等式は同じ run の
    # 証言の傘の下に居る。
    wit_files = {stmts[k]["file"] for k in witnessed if k in stmts}
    for r in eq_rules:
        src = r.get("derived", "").split(":", 1)[-1] or r["name"]
        f = stmts.get(src, stmts.get(r["name"], {})).get("file")
        r["witness"] = ("verified:lean4:4.34.0-rc1:file"
                        if f in wit_files else None)

    covered = len(known & set(stmts))
    out = {"votes": "none",
           "note": "statement sidecar; separate sovereign, never federation",
           "n_statements": len(stmts),
           "coverage_of_store_cores": covered,
           "store_cores": len(known),
           "statements": stmts}
    OUT_STMT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    OUT_EQ.write_text(json.dumps(
        {"votes": "none", "n_rules": len(eq_rules), "rules": eq_rules,
         "rejected": rejected},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({
        "files": len(files), "statements": len(stmts),
        "store_cores": len(known), "covered": covered,
        "coverage": round(covered / max(1, len(known)), 4),
        "eq_rules": len(eq_rules),
        "eq_rules_witnessed": sum(1 for r in eq_rules if r["witness"]),
        "gate_rejected": {"refuted": sum(1 for x in rejected
                                         if x["why"] == "refuted"),
                          "undecided": sum(1 for x in rejected
                                           if x["why"] == "undecided")},
        "seconds": round(time.time() - t0, 1),
        "out": [str(OUT_STMT), str(OUT_EQ)]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
