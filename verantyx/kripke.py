"""Kripke finite model checking — 世界=十字、R=接合、□=合意ゲート、◇=wire 到達.

有限 Kripke 構造 (W, R, V) を CrossStore に載せる:
  世界 w      → core (十字1個)
  V(w) の命題 → その十字の facets
  R(u, v)    → 接合 (edges)

評価は決定論の graph 走査:
  w ⊨ □φ  ⟺  全ての R-後続で φ (全断面一致ゲートと同型; 後続なしは空虚に真)
  w ⊨ ◇φ  ⟺  ある R-後続で φ (電流が1本でも通る)

型付き拒否: モデルに存在しない世界/どこにも現れない命題への問いは
UNKNOWN_NO_EVIDENCE (閉世界の false と「知らない」を区別する)。

構文 (ASCII): p, not φ, φ and ψ, φ or ψ, φ -> ψ, box φ, dia φ, 括弧。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .cross_store import CrossStore


@dataclass
class KripkeModel:
    store: CrossStore = field(default_factory=CrossStore)
    edges: Dict[str, List[str]] = field(default_factory=dict)

    def add_world(self, name: str, props: Optional[List[str]] = None) -> None:
        name = name.casefold()
        self.store.add(name, props or [])
        self.edges.setdefault(name, [])

    def add_edge(self, u: str, v: str) -> None:
        u, v = u.casefold(), v.casefold()
        for w in (u, v):
            if w not in self.store.crosses:
                self.add_world(w)
        if v not in self.edges[u]:
            self.edges[u].append(v)

    def worlds(self) -> List[str]:
        return sorted(self.store.crosses)

    def props_at(self, w: str) -> Set[str]:
        return set(self.store.crosses.get(w, {}))

    def all_props(self) -> Set[str]:
        out: Set[str] = set()
        for w in self.store.crosses:
            out |= self.props_at(w)
        return out


# ---------------------------------------------------------------------------
# formula parser
# ---------------------------------------------------------------------------

_TOK = re.compile(r"->|\(|\)|[a-z_][a-z0-9_]*")
_KEYWORDS = {"not", "and", "or", "box", "dia"}


def _lex(s: str) -> Optional[List[str]]:
    s2 = (s or "").casefold()
    toks = _TOK.findall(s2)
    if re.sub(r"\s+", "", s2) != "".join(toks):
        return None  # 字句にならない文字が混ざっている → 型付き拒否へ
    return toks


class _Parser:
    def __init__(self, toks: List[str]):
        self.toks = toks
        self.i = 0

    def peek(self) -> Optional[str]:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def eat(self, t: Optional[str] = None) -> str:
        cur = self.peek()
        if cur is None or (t is not None and cur != t):
            raise ValueError(f"parse error at {self.i}: want {t} got {cur}")
        self.i += 1
        return cur

    # imp := or ('->' imp)?   (right assoc, loosest)
    def imp(self):
        left = self.orx()
        if self.peek() == "->":
            self.eat("->")
            return ("->", left, self.imp())
        return left

    def orx(self):
        left = self.andx()
        while self.peek() == "or":
            self.eat("or")
            left = ("or", left, self.andx())
        return left

    def andx(self):
        left = self.unary()
        while self.peek() == "and":
            self.eat("and")
            left = ("and", left, self.unary())
        return left

    def unary(self):
        t = self.peek()
        if t == "not":
            self.eat()
            return ("not", self.unary())
        if t == "box":
            self.eat()
            return ("box", self.unary())
        if t == "dia":
            self.eat()
            return ("dia", self.unary())
        if t == "(":
            self.eat("(")
            inner = self.imp()
            self.eat(")")
            return inner
        if t is None or t in _KEYWORDS or t == ")" or t == "->":
            raise ValueError(f"parse error: unexpected {t}")
        self.eat()
        return ("prop", t)


def parse_formula(s: str):
    toks = _lex(s)
    if not toks:
        return None
    p = _Parser(toks)
    try:
        f = p.imp()
    except ValueError:
        return None
    if p.peek() is not None:
        return None
    return f


def _props_in(f) -> Set[str]:
    if f[0] == "prop":
        return {f[1]}
    return set().union(*(_props_in(sub) for sub in f[1:])) if len(f) > 1 else set()


# ---------------------------------------------------------------------------
# evaluation (決定論 graph 走査)
# ---------------------------------------------------------------------------

def _eval(model: KripkeModel, w: str, f, trace: List[Dict[str, Any]]) -> bool:
    kind = f[0]
    if kind == "prop":
        val = f[1] in model.props_at(w)
        trace.append({"world": w, "prop": f[1], "value": val})
        return val
    if kind == "not":
        return not _eval(model, w, f[1], trace)
    if kind == "and":
        return _eval(model, w, f[1], trace) and _eval(model, w, f[2], trace)
    if kind == "or":
        return _eval(model, w, f[1], trace) or _eval(model, w, f[2], trace)
    if kind == "->":
        return (not _eval(model, w, f[1], trace)) or _eval(model, w, f[2], trace)
    if kind == "box":
        succ = model.edges.get(w, [])
        # 全断面一致ゲート: 全後続で真 (後続なしは空虚に真)
        vals = [_eval(model, v, f[1], trace) for v in succ]
        trace.append({"world": w, "box_over": succ, "values": vals})
        return all(vals)
    if kind == "dia":
        succ = model.edges.get(w, [])
        # wire 到達: 1本でも通れば真
        for v in succ:
            if _eval(model, v, f[1], trace):
                trace.append({"world": w, "dia_via": v})
                return True
        trace.append({"world": w, "dia_via": None, "over": succ})
        return False
    raise ValueError(f"bad node {f!r}")


def check(
    model: KripkeModel,
    formula: str,
    world: Optional[str] = None,
) -> Dict[str, Any]:
    """w ⊨ φ (world 指定) / 全世界での妥当性 (world=None)。型付き verdict."""
    f = parse_formula(formula)
    if f is None:
        return {"verdict": "UNKNOWN_UNPARSED", "value": None, "formula": formula}
    unknown_props = _props_in(f) - model.all_props()
    if unknown_props:
        return {
            "verdict": "UNKNOWN_NO_EVIDENCE",
            "value": None,
            "formula": formula,
            "reason": f"props_absent_from_model:{sorted(unknown_props)}",
        }
    if world is not None:
        w = world.casefold()
        if w not in model.store.crosses:
            return {
                "verdict": "UNKNOWN_NO_EVIDENCE",
                "value": None,
                "formula": formula,
                "reason": f"world_absent:{w}",
            }
        trace: List[Dict[str, Any]] = []
        val = _eval(model, w, f, trace)
        return {
            "verdict": "ANSWER",
            "value": val,
            "world": w,
            "formula": formula,
            "trace": trace,
        }
    # 大域: 全世界一致ゲート
    per: Dict[str, bool] = {}
    for w in model.worlds():
        trace = []
        per[w] = _eval(model, w, f, trace)
    valid = all(per.values())
    return {
        "verdict": "ANSWER",
        "value": valid,
        "mode": "validity_in_model",
        "per_world": per,
        "formula": formula,
    }


_AT_WORLD_RE = re.compile(r"^(.*?)\s+at\s+(\w+)\s*$")

# Module-level default model — deliberately starts EMPTY (no worlds/props).
# There is no CrossStore <-> KripkeModel bridge yet (CrossStore has no
# accessibility-relation storage), so this honestly reflects "Vera knows no
# Kripke facts by default" rather than faking a populated model. Real
# queries against this model will mostly return UNKNOWN_NO_EVIDENCE until
# someone calls `register_kripke_world`/`register_kripke_edge` below — that
# recurring gap is itself the Milestone M growth signal, not a bug.
_default_model = KripkeModel()


def register_kripke_world(name: str, props: List[str]) -> None:
    _default_model.add_world(name, props)


def register_kripke_edge(u: str, v: str) -> None:
    _default_model.add_edge(u, v)


def kripke_ask(_store: Any, query: str) -> Dict[str, Any]:
    """Domain-registry adapter (see domains/__init__.py) over the module-
    level default model. Query shape: "<formula>" (validity across all
    worlds) or "<formula> at <world>". Formulas that don't parse as modal
    logic at all correctly fall through as UNKNOWN_UNPARSED ("not my
    domain") rather than a false negative on real Kripke queries."""
    q = (query or "").strip()
    m = _AT_WORLD_RE.match(q)
    formula, world = (m.group(1), m.group(2)) if m else (q, None)
    return check(_default_model, formula, world)
