"""Term rewriting kernel — 規則を十字に格納する数学の共通基盤.

数学の各分野を個別実装せず、**式木 + 規則適用**の1カーネルに載せる:

  項:      int | 識別子 | ("?a" 変数) | (op, args...)   op ∈ {+,-,*} ∪ 関数名
  規則:    lhs パターン → rhs テンプレート  (例: "?a + 0" → "?a")
  格納:    RuleStore — JSON save/load、CrossStore へ pour 可能
           (core = 規則名, facets = lhs/rhs) — 「規則もデータ」
  許可:    allowed (H と同型) — 許可された規則しか適用されない
  定数:    int⊕int は wire_add/sub/mul で畳む (構成上正確な算術に接地)
  戦略:    leftmost-innermost・登録順 (決定論)。予算超過 → UNKNOWN_BUDGET
  停止:    不動点 (どの規則も発火しない) → 正規形

代数・論理は同カーネル上の規則セット (ALGEBRA_RULES / LOGIC_RULES)。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from .cross_store import CrossStore
from .math_sim import wire_add, wire_mul, wire_sub

Term = Union[int, str, Tuple]

_TOKEN = re.compile(r"\d+|\?[a-z][a-z0-9_]*|[a-z_][a-z0-9_]*|[()+\-*,]")


# ---------------------------------------------------------------------------
# term parse / print
# ---------------------------------------------------------------------------

def _lex(s: str) -> Optional[List[str]]:
    s2 = (s or "").casefold()
    toks = _TOKEN.findall(s2)
    if re.sub(r"\s+", "", s2) != "".join(toks):
        return None
    return toks


class _P:
    def __init__(self, toks: List[str]):
        self.t = toks
        self.i = 0

    def peek(self) -> Optional[str]:
        return self.t[self.i] if self.i < len(self.t) else None

    def eat(self, x: Optional[str] = None) -> str:
        c = self.peek()
        if c is None or (x is not None and c != x):
            raise ValueError(f"parse@{self.i}")
        self.i += 1
        return c

    def addsub(self) -> Term:
        left = self.mul()
        while self.peek() in ("+", "-"):
            op = self.eat()
            left = (op, left, self.mul())
        return left

    def mul(self) -> Term:
        left = self.atom()
        while self.peek() == "*":
            self.eat("*")
            left = ("*", left, self.atom())
        return left

    def atom(self) -> Term:
        c = self.peek()
        if c == "(":
            self.eat("(")
            inner = self.addsub()
            self.eat(")")
            return inner
        if c is None or c in (")", ",", "+", "*"):
            raise ValueError(f"parse@{self.i}")
        if c == "-":  # 単項マイナスは v0 非対応 (自然数)
            raise ValueError("unary_minus")
        self.eat()
        if c.isdigit():
            return int(c)
        if self.peek() == "(":  # 関数適用 f(a, b, ...)
            self.eat("(")
            args: List[Term] = [self.addsub()]
            while self.peek() == ",":
                self.eat(",")
                args.append(self.addsub())
            self.eat(")")
            return (c, *args)
        return c  # 識別子 or ?変数


def parse_term(s: str) -> Optional[Term]:
    toks = _lex(s)
    if not toks:
        return None
    p = _P(toks)
    try:
        t = p.addsub()
    except ValueError:
        return None
    return t if p.peek() is None else None


def term_to_str(t: Term) -> str:
    if isinstance(t, int):
        return str(t)
    if isinstance(t, str):
        return t
    op = t[0]
    if op in ("+", "-", "*"):
        a, b = t[1], t[2]
        sa, sb = term_to_str(a), term_to_str(b)
        if isinstance(a, tuple) and a[0] in ("+", "-") and op == "*":
            sa = f"({sa})"
        # 右側の複合項は、演算子が左結合である限り**常に**括弧が要る。
        # 以前は op が - か * のときだけ括弧を付けており、`a + (b + c)` が
        # `a + b + c` と印字されて `(a + b) + c` に読み直されていた
        # (往復 2/8 で破綻、2026-08-19実測)。Int では両方とも真の等式に
        # なるので実害は出ていなかったが、印字は項の表現であって
        # 「たまたま同値な別の項」ではない。非結合的な演算子を載せた
        # 瞬間に嘘になるし、実際この欠陥は測定を一件誤らせた
        # (帰納法の壁の実験で、結合律が「導出された」ように見えた)。
        if isinstance(b, tuple) and b[0] in ("+", "-", "*"):
            sb = f"({sb})"
        return f"{sa} {op} {sb}"
    return f"{op}({', '.join(term_to_str(a) for a in t[1:])})"


# ---------------------------------------------------------------------------
# rules as data
# ---------------------------------------------------------------------------

@dataclass
class Rule:
    name: str
    lhs: Term
    rhs: Term
    lhs_src: str = ""
    rhs_src: str = ""


@dataclass
class RuleStore:
    rules: List[Rule] = field(default_factory=list)

    def add(self, name: str, lhs: str, rhs: str) -> None:
        lt, rt = parse_term(lhs), parse_term(rhs)
        if lt is None or rt is None:
            raise ValueError(f"bad rule {name}: {lhs} -> {rhs}")
        self.rules.append(Rule(name, lt, rt, lhs, rhs))

    def names(self) -> List[str]:
        return [r.name for r in self.rules]

    # --- 規則もデータ: JSON / CrossStore へ ---
    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(
            [{"name": r.name, "lhs": r.lhs_src, "rhs": r.rhs_src}
             for r in self.rules], ensure_ascii=False))

    @classmethod
    def load(cls, path: Path) -> "RuleStore":
        rs = cls()
        for d in json.loads(Path(path).read_text()):
            rs.add(d["name"], d["lhs"], d["rhs"])
        return rs

    def pour_into(self, store: CrossStore) -> None:
        """core = rule:<name>, facets = lhs|rhs — 規則を十字として格納."""
        for r in self.rules:
            store.add(f"rule:{r.name}", [f"lhs:{r.lhs_src}", f"rhs:{r.rhs_src}"])

    @classmethod
    def from_cross_store(cls, store: CrossStore) -> "RuleStore":
        rs = cls()
        for core in sorted(store.crosses):
            if not core.startswith("rule:"):
                continue
            lhs = rhs = None
            for f in store.crosses[core]:
                if f.startswith("lhs:"):
                    lhs = f[4:]
                elif f.startswith("rhs:"):
                    rhs = f[4:]
            if lhs is not None and rhs is not None:
                rs.add(core[5:], lhs, rhs)
        return rs


def default_algebra_rules() -> RuleStore:
    rs = RuleStore()
    rs.add("add_zero_r", "?a + 0", "?a")
    rs.add("add_zero_l", "0 + ?a", "?a")
    rs.add("mul_one_r", "?a * 1", "?a")
    rs.add("mul_one_l", "1 * ?a", "?a")
    rs.add("mul_zero_r", "?a * 0", "0")
    rs.add("mul_zero_l", "0 * ?a", "0")
    rs.add("sub_zero", "?a - 0", "?a")
    rs.add("sub_self", "?a - ?a", "0")
    return rs


def default_logic_rules() -> RuleStore:
    rs = RuleStore()
    rs.add("not_not", "lnot(lnot(?a))", "?a")
    rs.add("and_true_l", "land(true, ?a)", "?a")
    rs.add("and_true_r", "land(?a, true)", "?a")
    rs.add("and_false_l", "land(false, ?a)", "false")
    rs.add("and_false_r", "land(?a, false)", "false")
    rs.add("or_false_l", "lor(false, ?a)", "?a")
    rs.add("or_false_r", "lor(?a, false)", "?a")
    rs.add("or_true_l", "lor(true, ?a)", "true")
    rs.add("or_true_r", "lor(?a, true)", "true")
    return rs


# ---------------------------------------------------------------------------
# matching / substitution
# ---------------------------------------------------------------------------

def _is_var(t: Term) -> bool:
    return isinstance(t, str) and t.startswith("?")


def match(pat: Term, term: Term, binding: Dict[str, Term]) -> Optional[Dict[str, Term]]:
    if _is_var(pat):
        if pat in binding:
            return binding if binding[pat] == term else None
        b = dict(binding)
        b[pat] = term
        return b
    if isinstance(pat, tuple):
        if not isinstance(term, tuple) or len(pat) != len(term) or pat[0] != term[0]:
            return None
        b: Optional[Dict[str, Term]] = binding
        for p, t in zip(pat[1:], term[1:]):
            b = match(p, t, b)  # type: ignore[arg-type]
            if b is None:
                return None
        return b
    return binding if pat == term else None


def subst(tpl: Term, binding: Dict[str, Term]) -> Term:
    if _is_var(tpl):
        return binding[tpl]
    if isinstance(tpl, tuple):
        return (tpl[0], *(subst(a, binding) for a in tpl[1:]))
    return tpl


# ---------------------------------------------------------------------------
# kernel
# ---------------------------------------------------------------------------

_WIRE = {"+": wire_add, "-": wire_sub, "*": wire_mul}


def _fold_const(t: Term) -> Optional[Tuple[Term, str]]:
    """int⊕int → wire 演算 (構成上正確)。失敗 (負/overflow) は畳まない."""
    if (
        isinstance(t, tuple)
        and t[0] in _WIRE
        and isinstance(t[1], int)
        and isinstance(t[2], int)
    ):
        r = _WIRE[t[0]](t[1], t[2])
        if r["verdict"] == "ANSWER":
            return r["value"], f"wire_{r['op']}"
    return None


def term_size(t: Term) -> int:
    """項のノード数。順序の第一要素。"""
    if isinstance(t, tuple):
        return 1 + sum(term_size(x) for x in t[1:])
    return 1


def order_key(t: Term):
    """項の全順序 `(サイズ, 印字)`。向き付き書き換えの減少測度。

    対称規則(可換律など)は有限個の置換しか生まないので、この順序で
    真に減少する適用だけを許せば停止する — 順序付き書き換えの古典的手法。
    """
    return (term_size(t), term_to_str(t))


def _step(
    t: Term,
    rules: RuleStore,
    allowed: Optional[Set[str]],
    oriented: Optional[Set[str]] = None,
) -> Optional[Tuple[Term, str]]:
    """leftmost-innermost で最初に発火する書き換えを 1 回 (決定論).

    ``oriented`` に挙げた規則は、**結果が項順序で真に小さくなる時だけ**
    適用される。対称規則(`?a + ?b → ?b + ?a`)は無向きだと a+b→b+a→a+b と
    往復して停止しないが(実測 60→19)、向きを付けると停止し、さらに置換を
    同一視する(a+b+c の12通り→単一の正規形)。探索ではない — 適用可否を
    決定論的な述語で決めるだけ。experiments/ordered_rewrite。
    """
    if isinstance(t, tuple):
        for i, sub in enumerate(t[1:], start=1):
            r = _step(sub, rules, allowed, oriented)
            if r is not None:
                new_sub, rule_name = r
                return (t[:i] + (new_sub,) + t[i + 1:]), rule_name
    folded = _fold_const(t)
    if folded is not None:
        return folded
    for rule in rules.rules:
        if allowed is not None and rule.name not in allowed:
            continue
        b = match(rule.lhs, t, {})
        if b is not None:
            out = subst(rule.rhs, b)
            if oriented and rule.name in oriented and \
                    not (order_key(out) < order_key(t)):
                continue
            return out, rule.name
    return None


def simplify(
    expr: str,
    rules: Optional[RuleStore] = None,
    *,
    allowed: Optional[Sequence[str]] = None,
    oriented: Optional[Sequence[str]] = None,
    budget: int = 200,
) -> Dict[str, Any]:
    """正規形まで書き換え。トレース付き・型付き verdict.

    ``oriented`` は向き付き適用にする規則名(既定 None = 従来どおり)。
    既定を変えていないので、既存の測定の前提は一切動かない。
    """
    rules = rules or default_algebra_rules()
    t = parse_term(expr)
    if t is None:
        return {"verdict": "UNKNOWN_UNPARSED", "term": None, "steps": []}
    allow = set(allowed) if allowed is not None else None
    orient = set(oriented) if oriented else None
    steps: List[Dict[str, str]] = []
    for _ in range(budget):
        r = _step(t, rules, allow, orient)
        if r is None:
            return {
                "verdict": "ANSWER",
                "term": term_to_str(t),
                "value": t if isinstance(t, int) else None,
                "steps": steps,
                "normal_form": True,
            }
        new_t, rule_name = r
        steps.append(
            {"rule": rule_name, "before": term_to_str(t), "after": term_to_str(new_t)}
        )
        t = new_t
    return {
        "verdict": "UNKNOWN_BUDGET",
        "term": term_to_str(t),
        "steps": steps,
        "normal_form": False,
    }
