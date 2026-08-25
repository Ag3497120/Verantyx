#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**Find checks that cannot fail — mechanically, and report a NUMBER.**

    python3 tests/unfalsifiable.py            # scan the shipped suite
    python3 tests/unfalsifiable.py --weak     # add the low-precision tier
    python3 tests/unfalsifiable.py --json     # machine readable
    python3 tests/unfalsifiable.py --runtime  # T7 by mutation, not by reading
    python3 tests/unfalsifiable.py --checks PATH --pkg DIR   # another tree

Eight checks that could not fail have been found in this project BY HAND,
across four passes: one, then three, then two, then two more. Every pass
someone looked harder and found more. That is not bad luck — a manual search
has unknown completeness and rising cost. This file replaces the eye with a
sweep that reads ``tests/run_checks.py`` as an ABSTRACT SYNTAX TREE (never a
regular expression: a line-based scan reads the shapes inside docstrings and
misses every condition that wraps) and names, per check, the shape by which
its condition can be true while its property is false.

**The shapes.** T1..T7 are the seven found by hand; T8 is the harness itself.

  T1  the two sides of the comparison are the same thing. Module-level
      assignment is followed: ``FORMULAS = _COAT.formulas()`` makes
      ``b.formulas() == garment_pattern.FORMULAS`` a comparison of X with X.
      A literal condition (``check(name, True, ...)``) is the degenerate case.
  T2  ``all()``/``any()``/``not <collection>`` whose iterable is not pinned
      NON-EMPTY inside the SAME boolean condition. A length clause on a
      neighbouring check line does not count: that line fails separately and
      therefore protects nothing.
  T3  the subject under test is the wrong object — a refusal, a default, one
      sample where the name promises an invariance.
  T4  both sides grow from ONE source, and the only difference between them
      is a transform that is allowed to be the identity.
  T5  a count or ratio that holds trivially at zero (``len(a) == len(b)``
      with neither pinned).
  T6  the real measurement is printed in the DETAIL while the asserted
      condition never constrains it.
  T7  a served reader can bypass its store entirely with the suite green.
      Not decidable by reading: ``--runtime`` replaces the reader's body with
      a frozen literal and re-runs the suite. Statically this pass reports
      only COVERAGE — which readers no check pins against a literal.
  T8  the harness's own loop stops early, so what it did not run it also did
      not report.

**What this cannot see** is stated by the tool itself, at the end of every
run, because a scanner that hides its blind spots is the same defect one
level up.

Nothing here raises across its own boundary: ``scan()`` returns a verdict
dict, and a check whose AST defeats a detector is COUNTED and NAMED as
unscanned rather than skipped in silence.
"""
from __future__ import annotations

import argparse
import ast
import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: How deep a name is followed through assignments before we give up.
MAX_DEPTH = 8

#: Verdicts. A refusal is a return value, never an exception.
ANSWER = "ANSWER"
UNKNOWN_NO_SUCH_FILE = "UNKNOWN_NO_SUCH_FILE"
UNKNOWN_UNPARSEABLE = "UNKNOWN_UNPARSEABLE"


def _norm(node) -> str:
    """The source of one node, whitespace-flattened, for comparing shapes."""
    if node is None:
        return ""
    try:
        return re.sub(r"\s+", " ", ast.unparse(node)).strip()
    except Exception:                                        # noqa: BLE001
        return f"<unparseable {type(node).__name__}>"


def _is_display(node) -> bool:
    """A literal collection written out here — non-empty by construction."""
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return bool(node.elts)
    if isinstance(node, ast.Dict):
        return bool(node.keys)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "range" and node.args:
            return all(isinstance(a, ast.Constant) for a in node.args)
    return False


# ---------------------------------------------------------------------------
class Source:
    """One parsed file, plus everything needed to resolve a name to a value.

    Resolution has two levels and the difference between them decides a
    verdict, so they are never merged:

      * a MODULE-level assignment is evaluated once at import, so a live call
        compared against it is a comparison with itself — a real T1;
      * a LOCAL assignment is a snapshot taken at a point in time, so the
        same comparison may be an honest before/after — reported apart.
    """

    def __init__(self, path, pkg_dir=None):
        self.path = Path(path)
        self.ok = True
        self.why = ""
        try:
            self.src = self.path.read_text(encoding="utf-8")
            self.tree = ast.parse(self.src)
        except FileNotFoundError:
            self.ok, self.why = False, UNKNOWN_NO_SUCH_FILE
            self.src, self.tree = "", ast.parse("")
        except SyntaxError as exc:                           # noqa: BLE001
            self.ok, self.why = False, f"{UNKNOWN_UNPARSEABLE}: {exc}"
            self.src, self.tree = "", ast.parse("")

        self.module_consts = self._top_level(self.tree)
        self.alias = {}          # local name -> package module stem
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    self.alias[a.asname or a.name] = a.name
            elif isinstance(node, ast.Import):
                for a in node.names:
                    tail = a.name.split(".")[-1]
                    self.alias[a.asname or tail] = tail

        self.pkg = {}            # (module stem, NAME) -> value expression
        self.pkg_dir = Path(pkg_dir) if pkg_dir else None
        if self.pkg_dir and self.pkg_dir.is_dir():
            for p in sorted(self.pkg_dir.glob("*.py")):
                try:
                    t = ast.parse(p.read_text(encoding="utf-8"))
                except Exception:                            # noqa: BLE001
                    continue
                for name, value in self._top_level(t).items():
                    self.pkg[(p.stem, name)] = value

        self.funcs = [n for n in ast.walk(self.tree)
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        self._locals = {}        # func id -> name -> [(lineno, value)]
        self._loops = {}         # func id -> name -> [iter expressions]
        for fn in self.funcs:
            self._locals[id(fn)] = self._assignments(fn)
            self._loops[id(fn)] = self._loop_sources(fn)

    # -- collection ---------------------------------------------------------
    @staticmethod
    def _top_level(tree):
        out = {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        out[t.id] = node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                if isinstance(node.target, ast.Name):
                    out[node.target.id] = node.value
        return out

    @staticmethod
    def _assignments(fn):
        out = {}
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        out.setdefault(t.id, []).append((node.lineno, node.value))
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                if isinstance(node.target, ast.Name):
                    out.setdefault(node.target.id, []).append(
                        (node.lineno, node.value))
        return out

    @staticmethod
    def _loop_sources(fn):
        """name -> the iterables of every ``for`` that fills it.

        A set filled by ``.add()`` three loops deep is still a scan over the
        OUTERMOST iterable, and that is the count nobody pinned.
        """
        out = {}
        def walk(node, stack):
            for child in ast.iter_child_nodes(node):
                nxt = stack
                if isinstance(child, (ast.For, ast.AsyncFor)):
                    nxt = stack + [child.iter]
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                names = []
                if isinstance(child, ast.AugAssign) and isinstance(child.target, ast.Name):
                    names.append(child.target.id)
                elif isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                    if child.func.attr in ("append", "add", "extend", "update"):
                        if isinstance(child.func.value, ast.Name):
                            names.append(child.func.value.id)
                for n in names:
                    if stack:
                        out.setdefault(n, []).append(stack[0])
                walk(child, nxt)
        walk(fn, [])
        return out

    # -- resolution ---------------------------------------------------------
    def enclosing(self, lineno):
        best = None
        for fn in self.funcs:
            end = getattr(fn, "end_lineno", fn.lineno)
            if fn.lineno <= lineno <= (end or fn.lineno):
                if best is None or fn.lineno > best.lineno:
                    best = fn
        return best

    def local_value(self, name, fn, line):
        if fn is None:
            return None
        prior = [(ln, v) for ln, v in self._locals.get(id(fn), {}).get(name, [])
                 if ln <= line]
        return prior[-1][1] if prior else None

    def loop_iters(self, name, fn):
        if fn is None:
            return []
        return self._loops.get(id(fn), {}).get(name, [])

    def canon(self, node, fn, line, *, package=True, trace=None,
              depth=0, seen=frozenset()):
        """``node`` with names replaced by what they were assigned.

        ``trace`` collects ("module"|"local"|"package", name) so a caller can
        tell a fixed constant from a snapshot without guessing.
        """
        if node is None or depth > MAX_DEPTH:
            return node
        if isinstance(node, ast.Name):
            key = ("n", node.id)
            if key in seen:
                return node
            value = self.local_value(node.id, fn, line)
            kind = "local"
            if value is None:
                value = self.module_consts.get(node.id)
                kind = "module"
            if value is None:
                return node
            if trace is not None:
                trace.append((kind, node.id))
            return self.canon(value, fn, line, package=package, trace=trace,
                              depth=depth + 1, seen=seen | {key})
        if (package and isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)):
            mod = self.alias.get(node.value.id)
            key = ("a", node.value.id, node.attr)
            if mod and (mod, node.attr) in self.pkg and key not in seen:
                if trace is not None:
                    trace.append(("package", f"{node.value.id}.{node.attr}"))
                return self.canon(self.pkg[(mod, node.attr)], fn, line,
                                  package=package, trace=trace,
                                  depth=depth + 1, seen=seen | {key})
        kids = {}
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                kids[field] = [
                    self.canon(v, fn, line, package=package, trace=trace,
                               depth=depth, seen=seen)
                    if isinstance(v, ast.AST) else v for v in value]
            elif isinstance(value, ast.AST):
                kids[field] = self.canon(value, fn, line, package=package,
                                         trace=trace, depth=depth, seen=seen)
            else:
                kids[field] = value
        try:
            out = type(node)(**kids)
            ast.copy_location(out, node)
            ast.fix_missing_locations(out)
            return out
        except Exception:                                    # noqa: BLE001
            return node

    def cnorm(self, node, fn, line, **kw):
        return _norm(self.canon(node, fn, line, **kw))


# ---------------------------------------------------------------------------
class Check:
    """One ``check(name, condition, detail)`` call site."""

    def __init__(self, call, src):
        self.call = call
        self.line = call.lineno
        self.fn = src.enclosing(call.lineno)
        self.func_name = self.fn.name if self.fn else "<module>"
        args = list(call.args)
        self.name_node = args[0] if args else None
        self.cond = args[1] if len(args) > 1 else None
        self.detail = args[2] if len(args) > 2 else None
        self.name = self._literal_name(self.name_node)

    @staticmethod
    def _literal_name(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            out = []
            for v in node.values:
                if isinstance(v, ast.Constant):
                    out.append(str(v.value))
                else:
                    out.append("{" + _norm(getattr(v, "value", v)) + "}")
            return "".join(out)
        return _norm(node)


def _find_checks(src, func_name="check"):
    out = []
    for node in ast.walk(src.tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == func_name:
            out.append(Check(node, src))
    out.sort(key=lambda c: c.line)
    return out


# ---------------------------------------------------------------------------
# The shapes.
# ---------------------------------------------------------------------------
def _short(text, n=220):
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text if len(text) <= n else text[:n - 1] + "…"


def _hit(chk, shape, why, evidence, confidence):
    return {"shape": shape, "check": chk.name, "line": chk.line,
            "function": chk.func_name, "why": why,
            "evidence": _short(evidence, 320), "confidence": confidence}


COMPUTED = (ast.Call, ast.Compare, ast.BoolOp, ast.UnaryOp, ast.ListComp,
            ast.SetComp, ast.GeneratorExp, ast.DictComp, ast.IfExp, ast.BinOp)


def _shallow(node, src, fn, line, rounds=4):
    """``node`` with local names replaced by the EXPRESSION they were given.

    Only names bound to a COMPUTED expression are followed — a name bound to
    a literal stays a name, so the text a reader sees is the text they wrote.
    This is deliberately not ``canon``: deep resolution is right for deciding
    whether two things are one thing, and wrong for saying so out loud.
    """
    try:
        out = copy.deepcopy(node)
    except Exception:                                        # noqa: BLE001
        return node
    for _ in range(rounds):
        changed = [False]

        class T(ast.NodeTransformer):
            def visit_Name(self, n):                        # noqa: N802
                v = src.local_value(n.id, fn, line)
                if isinstance(v, COMPUTED) and _norm(v) != n.id:
                    changed[0] = True
                    return copy.deepcopy(v)   # never mutate the original tree
                return n

        try:
            out = T().visit(out)
            ast.fix_missing_locations(out)
        except Exception:                                    # noqa: BLE001
            return out
        if not changed[0]:
            break
    return out


def _nonempty_by_construction(node, src, fn, line):
    """A literal written out somewhere up the chain cannot be empty."""
    if _is_display(node):
        return True
    deep = src.canon(node, fn, line)
    return _is_display(deep)


def _wrappers(node, mods=frozenset(), deep=False):
    """(base, chain) — the innermost data source and the transforms over it.

    Descends only through transforms with exactly one data operand, so
    ``strip(x).split(">")[1:]`` reduces to base ``x`` under a chain of three,
    while ``BlockView(rt, b.root)`` — two operands — stops and IS the base.
    """
    chain = []
    cur = node
    for _ in range(24):
        if isinstance(cur, ast.Call) and isinstance(cur.func, ast.Name) \
                and len(cur.args) == 1 and not cur.keywords:
            chain.append(cur.func.id)
            cur = cur.args[0]
        elif isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute) \
                and not cur.keywords:
            module_call = (isinstance(cur.func.value, ast.Name)
                           and cur.func.value.id in mods)
            if module_call and not deep:
                break                      # a module call IS the data source
            if module_call:
                # `i18n.svg(x)` carries its data in the ARGUMENT, not the
                # receiver: descending into `i18n` loses the seed entirely.
                if len(cur.args) != 1:
                    break
                chain.append("." + cur.func.attr)
                cur = cur.args[0]
                continue
            chain.append("." + cur.func.attr)
            cur = cur.func.value
        elif isinstance(cur, ast.Subscript):
            chain.append("[]")
            cur = cur.value
        elif isinstance(cur, (ast.ListComp, ast.SetComp, ast.GeneratorExp)) \
                and len(cur.generators) == 1:
            chain.append("comprehension")
            cur = cur.generators[0].iter
        elif isinstance(cur, ast.Attribute):
            chain.append("." + cur.attr)
            cur = cur.value
        else:
            break
    chain.reverse()
    return _norm(cur), chain


#: Steps that are the identity ON PURPOSE. ``x == deepcopy(x)`` taken at two
#: different times is the standard "nothing changed here" test, not a
#: tautology — the transform is meant to preserve the value, and what is
#: being measured is the TIME between the two reads.
COPY_STEPS = ("deepcopy", ".deepcopy", "copy", ".copy", "list", "dict", "set",
              "tuple", "frozenset")


def _subsequence_plus_one(short, long_):
    """True when ``long_`` is ``short`` with exactly one element inserted."""
    if len(long_) != len(short) + 1:
        return False
    i = 0
    skipped = False
    for item in long_:
        if i < len(short) and item == short[i]:
            i += 1
        elif not skipped:
            skipped = True
        else:
            return False
    return i == len(short)


def _exprs(node):
    """The expression subnodes of a tree, by source text.

    Context and operator nodes are excluded on purpose: they all unparse to
    the same placeholder, and a set that contains that placeholder makes any
    two unrelated expressions look like they overlap — which is how a
    detector quietly stops detecting.
    """
    return {_norm(n) for n in ast.walk(node) if isinstance(n, ast.expr)}


def _comparisons(node):
    for n in ast.walk(node):
        if isinstance(n, ast.Compare) and len(n.ops) == 1:
            yield n, n.left, n.comparators[0], n.ops[0]


def _has_constant_operand(cmp_node):
    for side in (cmp_node.left, cmp_node.comparators[0]):
        if isinstance(side, ast.Constant) or _is_display(side):
            return True
    return False


def _mutated_between(src, fn, receiver, lo, hi):
    """Is there a call on ``receiver`` between two lines?

    This is what separates ``x.f() == snapshot`` the tautology from
    ``x.f() == snapshot`` the honest before/after: something has to happen in
    between, or the two reads are one read written twice.
    """
    if fn is None or not receiver:
        return False
    for n in ast.walk(fn):
        if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Attribute):
            continue
        if not (lo < getattr(n, "lineno", 0) < hi):
            continue
        if _norm(n.func.value) == receiver:
            return True
    return False


def t1_same_thing(chk, src, eff):
    """Both sides resolve to one value — including through a module constant."""
    hits = []
    cond = chk.cond
    if cond is None:
        return hits
    if isinstance(cond, ast.Constant):
        if cond.value is False:
            return hits                    # an unconditional FAIL report
        return [_hit(chk, "T1", "the condition is a literal",
                     f"condition is {cond.value!r} — no measurement happens",
                     "real")]
    if _is_display(cond):
        return [_hit(chk, "T1", "the condition is a non-empty literal",
                     f"condition is {_norm(cond)}", "real")]
    flat = src.canon(cond, chk.fn, chk.line, package=False)
    if isinstance(flat, ast.Constant) and flat.value is not False:
        return [_hit(chk, "T1", "the condition resolves to a literal",
                     f"{_norm(cond)} is {flat.value!r} here", "real")]

    pairs = list(_comparisons(cond)) or list(_comparisons(eff))
    for cmp_node, left, right, op in pairs:
        if not isinstance(op, (ast.Eq, ast.Is)):
            continue
        tl, tr = [], []
        lc = src.canon(left, chk.fn, chk.line, trace=tl)
        rc = src.canon(right, chk.fn, chk.line, trace=tr)
        cl, cr = _norm(lc), _norm(rc)
        raw_l, raw_r = _norm(left), _norm(right)
        trace = tl + tr
        if cl == cr and cl:
            fixed = [n for k, n in trace if k in ("module", "package")]
            if raw_l == raw_r:
                hits.append(_hit(chk, "T1", "the same expression on both sides",
                                 f"{raw_l} == {raw_r}", "real"))
            elif fixed:
                hits.append(_hit(
                    chk, "T1",
                    "one side is a constant evaluated from the other",
                    f"{raw_l} == {raw_r}; both are `{cl}` once the "
                    f"module-level assignment of {', '.join(fixed)} is "
                    f"followed", "real"))
            else:
                alias_line, other = 0, None
                for side in (left, right):
                    if isinstance(side, ast.Name):
                        got = [ln for ln, _v in src._locals.get(
                            id(chk.fn), {}).get(side.id, []) if ln <= chk.line]
                        if got:
                            alias_line = max(alias_line, got[-1])
                    else:
                        other = side
                recv = _wrappers(other if other is not None else left,
                                 set(src.alias))[0]
                if _mutated_between(src, chk.fn, recv, alias_line, chk.line):
                    continue          # something happens in between: honest
                hits.append(_hit(
                    chk, "T1", "one expression written twice",
                    f"{raw_l} == {raw_r}; both are `{_short(cl, 90)}`, and no "
                    f"call on `{recv}` stands between the two reads",
                    "real"))
            continue
        if isinstance(lc, ast.Call) and isinstance(rc, ast.Call) \
                and isinstance(lc.func, ast.Attribute) \
                and isinstance(rc.func, ast.Attribute) \
                and lc.func.attr == rc.func.attr \
                and [_norm(a) for a in lc.args] == [_norm(a) for a in rc.args] \
                and _norm(lc.func.value) != _norm(rc.func.value):
            through = [n for k, n in trace if k in ("module", "package")]
            if through:
                hits.append(_hit(
                    chk, "T1",
                    "compared against a module constant that IS this call",
                    f"{raw_l} == {raw_r}: {', '.join(through)} is assigned "
                    f"`.{lc.func.attr}()` on the same store at import, so both "
                    f"sides are one call written twice", "real"))
            else:
                pinned = any(
                    _has_constant_operand(c)
                    and (raw_l in _norm(c) or raw_r in _norm(c))
                    for c, _l, _r, _o in pairs if c is not cmp_node)
                hits.append(_hit(
                    chk, "T1",
                    "two calls of one method, nothing pinning what it returns",
                    f"{raw_l} == {raw_r} — the same .{lc.func.attr}() on two "
                    f"receivers; whatever one side drops, the other drops too"
                    + ("" if pinned else
                       ". No other clause pins either side to a literal"),
                    "borderline" if pinned else "real"))
    return hits


def _pins(cond, src, fn, line):
    """Everything THIS ONE condition asserts to be non-empty."""
    out = set()
    for cmp_node, left, right, op in _comparisons(cond):
        def is_len(x):
            return (isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
                    and x.func.id in ("len", "sum") and x.args)
        for a, b, flip in ((left, right, False), (right, left, True)):
            if not is_len(a):
                continue
            if is_len(b) and _nonempty_by_construction(b.args[0], src, fn, line) \
                    and isinstance(op, ast.Eq):
                out.add(_norm(a.args[0]))
                continue
            if not (isinstance(b, ast.Constant) and isinstance(b.value, int)
                    and not isinstance(b.value, bool)):
                continue
            c, o = b.value, op
            if flip:
                o = {ast.Gt: ast.Lt, ast.Lt: ast.Gt, ast.GtE: ast.LtE,
                     ast.LtE: ast.GtE}.get(type(op), type(op))()
            if ((isinstance(o, ast.Eq) and c > 0)
                    or (isinstance(o, ast.GtE) and c >= 1)
                    or (isinstance(o, ast.Gt) and c >= 0)
                    or (isinstance(o, ast.NotEq) and c == 0)):
                out.add(_norm(a.args[0]))
    for n in ast.walk(cond):
        if isinstance(n, ast.BoolOp) and isinstance(n.op, ast.And):
            for v in n.values:
                if isinstance(v, (ast.Name, ast.Attribute, ast.Subscript,
                                  ast.Call)):
                    out.add(_norm(v))
    return out


def _quantifiers(node):
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id in ("all", "any") and n.args:
            arg = n.args[0]
            if isinstance(arg, (ast.GeneratorExp, ast.ListComp, ast.SetComp)) \
                    and arg.generators:
                yield n, arg.generators[0].iter
            else:
                yield n, arg


def t2_vacuous(chk, src, eff):
    """A quantifier, or a `not <scan>`, over something that may be empty."""
    hits = []
    if chk.cond is None:
        return hits
    pinned = _pins(eff, src, chk.fn, chk.line) | _pins(chk.cond, src, chk.fn,
                                                       chk.line)
    negated = set()
    for n in ast.walk(eff):
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            negated |= {_norm(x) for x in ast.walk(n.operand)
                        if isinstance(x, ast.expr)}
    seen = set()
    for call, iterable in _quantifiers(eff):
        name = _norm(iterable)
        if name in seen:
            continue
        seen.add(name)
        if _is_display(iterable) or isinstance(iterable, ast.Constant):
            continue
        if name in pinned or _nonempty_by_construction(iterable, src, chk.fn,
                                                       chk.line):
            continue
        empty_true = (call.func.id == "all") != (_norm(call) in negated)
        polarity = ("vacuously TRUE over an empty iterable — the check cannot "
                    "fail" if empty_true else
                    "vacuously FALSE over an empty iterable, so the check "
                    "cannot PASS: the same defect mirrored, and the safe "
                    "direction")
        hits.append(_hit(
            chk, "T2", f"{call.func.id}() over an unpinned iterable",
            f"{call.func.id}(… for … in {_short(name, 90)}) is {polarity}; "
            f"no clause in THIS condition asserts that iterable is non-empty",
            "real" if empty_true else "borderline"))
    for n in ast.walk(chk.cond):
        if not (isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not)):
            continue
        target = n.operand
        if not isinstance(target, ast.Name) or _norm(target) in pinned:
            continue
        value = src.local_value(target.id, chk.fn, chk.line)
        root = None
        if isinstance(value, (ast.ListComp, ast.SetComp, ast.GeneratorExp)) \
                and value.generators:
            root = value.generators[0].iter
        else:
            iters = src.loop_iters(target.id, chk.fn)
            root = iters[0] if iters else None
        if root is None:
            continue
        rname = _norm(root)
        if rname in pinned or _nonempty_by_construction(root, src, chk.fn,
                                                        chk.line):
            continue
        hits.append(_hit(
            chk, "T2", "`not <scan>` over an unpinned scan",
            f"`not {target.id}` is true when the scan found nothing AND when "
            f"the scan covered nothing: {target.id} is filled from "
            f"{_short(rname, 80)}, whose size this condition never asserts",
            "real"))
    return hits


VERDICT_KEYS = ("verdict",)
REFUSAL_PREFIX = ("UNKNOWN", "CONTESTED", "AMBIGUOUS", "ORDER_", "OVER_",
                  "DANGLING", "ORPHANED", "DUPLICATE", "ALIASED", "ARM_",
                  "NOT_", "GENERIC_")
NAME_EXEMPT = ("refus", "reject", "not in this build")
UNIVERSAL = ("every", "all ", "each")


def _verdict_callees(src):
    """Callees whose result is read as ``x["verdict"]`` somewhere in the file.

    The tool learns from the suite itself which functions answer WITH a
    verdict, so it can notice a check that tests such an object without ever
    constraining which branch it came back on.
    """
    subjects = set()
    for node in ast.walk(src.tree):
        base = None
        if isinstance(node, ast.Subscript):
            sl = node.slice
            k = sl.value if isinstance(sl, ast.Constant) else None
            if isinstance(k, str) and k in VERDICT_KEYS:
                base = node.value
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get" and node.args:
            a = node.args[0]
            if isinstance(a, ast.Constant) and a.value in VERDICT_KEYS:
                base = node.func.value
        if isinstance(base, ast.Name):
            subjects.add(base.id)
    callees = set()
    for fn in src.funcs:
        for name, entries in src._locals.get(id(fn), {}).items():
            if name not in subjects:
                continue
            for _ln, value in entries:
                if isinstance(value, ast.Call):
                    callees.add(_norm(value.func))
    return callees


def t3_wrong_subject(chk, src, eff, verdict_callees):
    hits = []
    cond = chk.cond
    if cond is None:
        return hits
    low = (chk.name or "").lower()
    # (a) a verdict-bearing subject whose verdict is never constrained, under
    #     a condition that any refusal satisfies.
    names = {n.id for n in ast.walk(cond) if isinstance(n, ast.Name)}
    positive = any(isinstance(o, (ast.Eq, ast.Gt, ast.GtE, ast.Lt, ast.LtE))
                   for _c, _l, _r, o in _comparisons(cond))
    for name in sorted(names):
        value = src.local_value(name, chk.fn, chk.line)
        if not isinstance(value, ast.Call):
            continue
        if _norm(value.func) not in verdict_callees:
            continue
        text = _norm(cond)
        if f"{name}['verdict']" in text or f"{name}.get('verdict')" in text:
            continue
        if positive:
            continue
        dead = [a for a in ast.walk(value)
                if isinstance(a, ast.IfExp) and isinstance(a.test, ast.Constant)]
        extra = (" The subject is built by a dead conditional "
                 f"(`{_norm(value)}`), which always takes the default."
                 if dead else "")
        hits.append(_hit(
            chk, "T3", "the subject's verdict is never constrained",
            f"`{name} = {_norm(value)}` answers WITH a verdict, and "
            f"`{_norm(cond)}` is satisfied by any refusal — the branch the "
            f"name promises is never entered.{extra}", "real"))
    # (b) the whole property is delegated to the thing under test. This one
    #     is deliberately BORDERLINE: such a check CAN go red — it goes red
    #     when the callee says so. What it cannot do is notice that the
    #     callee's own verdict is wrong, which is how "placement does not
    #     move answers" stayed green while placement_check() read one
    #     unmutated store twice. The shape is visible; the cause is not.
    if not any(w in low for w in NAME_EXEMPT):
        cmps = list(_comparisons(cond))
        consts = []
        for _c, left, right, _o in cmps:
            for side in (left, right):
                node = src.canon(side, chk.fn, chk.line)
                if isinstance(node, ast.Constant):
                    consts.append(node.value)
        answers = [c for c in consts if c == "ANSWER"]
        others = [c for c in consts if c != "ANSWER"]
        refusals = [c for c in others if isinstance(c, str)
                    and c.upper() == c and len(c) > 3]
        others = [c for c in others if c not in refusals]
        subj = {_wrappers(src.canon(s, chk.fn, chk.line, package=False),
                          set(src.alias))[0]
                for _c, l, r, _o in cmps for s in (l, r)
                if not isinstance(s, ast.Constant)}
        if cmps and answers and not refusals and not others and len(subj) <= 1:
            hits.append(_hit(
                chk, "T3", "the property is delegated to the code under test",
                f"`{_norm(cond)}` asks {', '.join(sorted(subj)) or 'the code'} "
                f"for its own verdict and believes it. Every number this check "
                f"is named for is measured by the thing it is checking, so a "
                f"callee that reports ANSWER while doing nothing keeps it "
                f"green", "borderline"))
    # (c) the name generalises; the condition reads one sample.
    m = re.search(r"\b(every|all|each)\s+([A-Za-z][\w-]*)", low)
    if m:
        noun = m.group(2)
        singular = noun[:-1] if noun.endswith("s") and len(noun) > 4 else noun
        pool = set()
        for n in list(ast.walk(eff)) + list(ast.walk(cond)):
            if isinstance(n, ast.Name) and n.id not in src.alias:
                pool.add(n.id)
            elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                pool.add(n.value)
            elif isinstance(n, ast.Attribute):
                pool.add(n.attr)
        if not any(noun in p.lower() or singular in p.lower() for p in pool):
            hits.append(_hit(
                chk, "T3",
                f"the name quantifies over {noun}; the condition does not",
                f"nothing the condition touches is named for `{noun}` — "
                f"`{_short(_norm(chk.cond), 120)}`. The universal in the name "
                f"is not the universal that is measured", "real"))
    return hits


def t4_one_seed(chk, src, eff, already):
    hits = []
    if chk.cond is None:
        return hits
    for cmp_node, left, right, op in _comparisons(eff):
        if not isinstance(op, (ast.Eq, ast.NotEq)):
            continue
        if isinstance(left, ast.Constant) or isinstance(right, ast.Constant):
            continue
        if _is_display(left) or _is_display(right):
            continue
        mods = set(src.alias)
        bl, chl = _wrappers(left, mods)
        br, chr = _wrappers(right, mods)
        if bl != br:
            # Stopping at a module call keeps the report readable, but the
            # shared seed can be UNDER that call — `i18n.svg(x)` against `x`
            # is exactly the transform-that-may-be-the-identity this looks
            # for. So when the readable form disagrees, look all the way down.
            bl, chl = _wrappers(left, mods, deep=True)
            br, chr = _wrappers(right, mods, deep=True)
        if not bl or bl != br:
            continue
        if _norm(left) == _norm(right):
            continue
        short, long_ = (chl, chr) if len(chl) <= len(chr) else (chr, chl)
        if not _subsequence_plus_one(short, long_):
            continue
        extra = [c for c in long_ if c not in short] or ["one transform"]
        if extra[0] in COPY_STEPS:
            continue
        if f"{bl}|{extra[0]}" in already:
            continue
        already.add(f"{bl}|{extra[0]}")
        hits.append(_hit(
            chk, "T4", "both sides grow from one source",
            f"{_short(_norm(left), 80)} == {_short(_norm(right), 80)}: both "
            f"start at `{_short(bl, 60)}` and differ by exactly one step "
            f"({extra[0]}). The comparison holds whenever that step is the "
            f"identity — including on the day it silently becomes one", "real"))
    return hits


def t5_zero_ratio(chk, src, eff):
    hits = []
    if chk.cond is None:
        return hits
    pinned = _pins(eff, src, chk.fn, chk.line)
    for cmp_node, left, right, op in _comparisons(eff):
        if not isinstance(op, ast.Eq):
            continue
        def is_len(x):
            return (isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
                    and x.func.id == "len" and x.args)
        if not (is_len(left) and is_len(right)):
            continue
        a, b = left.args[0], right.args[0]
        na, nb = _norm(a), _norm(b)
        if na in pinned or nb in pinned:
            continue
        # `len(a) == len(b) and a != b` excludes the both-empty case already.
        if any(isinstance(o, ast.NotEq)
               and {_norm(l2), _norm(r2)} == {na, nb}
               for _c2, l2, r2, o in _comparisons(eff)):
            continue
        if _nonempty_by_construction(a, src, chk.fn, chk.line) or \
                _nonempty_by_construction(b, src, chk.fn, chk.line):
            continue
        hits.append(_hit(
            chk, "T5", "a ratio that holds at zero",
            f"len({_short(na, 60)}) == len({_short(nb, 60)}) is true when both "
            f"are 0, and true for any subset that happens to match in size; "
            f"nothing in this condition asserts either is non-zero", "real"))
    return hits


COUNTERS = ("len", "sum", "max", "min", "count")


def _detail_parts(node):
    out = []
    if node is None:
        return out
    for n in ast.walk(node):
        if isinstance(n, ast.FormattedValue):
            out.append(n.value)
    return out


def t6_detail_says_more(chk, src, eff, weak=False):
    """The detail prints a measurement; the condition never constrains it."""
    hits = []
    if chk.cond is None or chk.detail is None:
        return hits
    cond_text = _norm(chk.cond)
    parts = _exprs(chk.cond) | _exprs(eff)
    seen = set()
    for expr in _detail_parts(chk.detail):
        text = _norm(expr)
        if text in seen:
            continue
        counter = (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name)
                   and expr.func.id in COUNTERS and expr.args)
        if not counter and not weak:
            continue
        if text in parts or _norm(_shallow(expr, src, chk.fn, chk.line)) in parts:
            continue
        if counter:
            # printing len(X) is constrained enough if the condition says
            # anything at all about X — and the comparison has to be made
            # after the same substitution the condition got, or two spellings
            # of one expression look like two expressions.
            inner = expr.args[0]
            if (_exprs(inner) | _exprs(_shallow(inner, src, chk.fn, chk.line))) \
                    & parts:
                continue
        seen.add(text)
        hits.append(_hit(
            chk, "T6" if counter else "T6-weak",
            "the detail reports a number the condition never constrains",
            f"the detail computes `{_short(text, 80)}`; the condition is "
            f"`{_short(cond_text, 120)}`, which never mentions it. That number "
            f"can move to anything and the line still prints PASS",
            "real" if counter else "borderline"))
    return hits


# ---------------------------------------------------------------------------
# T7 — served readers. Coverage statically; proof only by mutation.
# ---------------------------------------------------------------------------
def served_readers(pkg_dir, checks_src, checks, effective):
    """Public no-argument readers of a store, and whether any check pins one.

    A reader is PINNED when some check compares its result against a literal
    written in the checks file. A reader that no check pins can be replaced
    by a frozen constant — it stops reading the store — with the suite green.
    That is the shape of findings #7 and #8 and it is not visible in any one
    check: it is visible only in the ABSENCE of one.
    """
    out = []
    pkg_dir = Path(pkg_dir)
    if not pkg_dir.is_dir():
        return out
    literal_names = {n for n, v in checks_src.module_consts.items()
                     if _is_display(v)}
    for path in sorted(pkg_dir.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception:                                    # noqa: BLE001
            continue
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            init = next((n for n in cls.body
                         if isinstance(n, ast.FunctionDef) and n.name == "__init__"),
                        None)
            if init is None:
                continue
            arg_names = [a.arg for a in init.args.args]
            if not any("store" in a for a in arg_names):
                continue
            for meth in [n for n in cls.body if isinstance(n, ast.FunctionDef)]:
                if meth.name.startswith("_"):
                    continue
                if len(meth.args.args) != 1:      # self only
                    continue
                call = f".{meth.name}()"
                pinning = []
                mentions = []
                for chk in checks:
                    if chk.cond is None:
                        continue
                    cond = effective.get(chk.line, chk.cond)
                    text = _norm(cond) + " " + _norm(chk.cond)
                    if call not in text:
                        continue
                    mentions.append(chk.name)
                    for cmp_node, left, right, _op in _comparisons(cond):
                        sides = (_norm(left), _norm(right))
                        if not any(call in s for s in sides):
                            continue
                        other = right if call in sides[0] else left
                        if isinstance(other, ast.Constant) or _is_display(other):
                            pinning.append(chk.name)
                        elif isinstance(other, ast.Name) and other.id in literal_names:
                            pinning.append(chk.name)
                out.append({
                    "class": cls.name, "method": meth.name,
                    "file": f"{path.name}:{meth.lineno}",
                    "mentioned_by": sorted(set(mentions)),
                    "pinned_by": sorted(set(pinning)),
                })
    return out


PROBE = r'''
import json, sys
sys.path.insert(0, {root!r})
from photoloset import block
b = block.coat()
print(json.dumps({{"value": repr(getattr(b, {meth!r})())}}))
'''


def runtime_probe(reader, repo_root, timeout=900):
    """Freeze one reader to a literal and re-run the suite.

    This is the only honest way to answer T7: a reader that no longer reads
    its store, with every check still green, is a reader nothing pins.
    """
    cls, meth = reader["class"], reader["method"]
    got = subprocess.run(
        [sys.executable, "-c", PROBE.format(root=str(repo_root), meth=meth)],
        capture_output=True, text=True, cwd=str(repo_root), timeout=300)
    if got.returncode != 0:
        return {"verdict": "UNKNOWN_READER_NOT_REACHABLE",
                "reader": f"{cls}.{meth}", "why": got.stderr.strip()[-300:]}
    frozen = json.loads(got.stdout)["value"]
    base = Path(tempfile.mkdtemp(prefix="unfalsifiable_"))
    repo = base / "repo"
    shutil.copytree(repo_root, repo,
                    ignore=shutil.ignore_patterns(".git", "__pycache__",
                                                  "*.pyc", "build", "dist"))
    target = None
    for path in (repo / "photoloset").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == cls:
                for m in node.body:
                    if isinstance(m, ast.FunctionDef) and m.name == meth:
                        target = (path, m)
    if target is None:
        shutil.rmtree(base, ignore_errors=True)
        return {"verdict": "UNKNOWN_NO_SUCH_READER", "reader": f"{cls}.{meth}"}
    path, m = target
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    body_start = m.body[0].lineno - 1
    end = m.body[-1].end_lineno
    indent = " " * (len(lines[body_start]) - len(lines[body_start].lstrip()))
    frozen_line = (f"{indent}return {frozen}  # BYPASS: never reads the store\n")
    lines[body_start:end] = [frozen_line]
    path.write_text("".join(lines), encoding="utf-8")
    run = subprocess.run([sys.executable, "tests/run_checks.py"],
                         cwd=str(repo), capture_output=True, text=True,
                         timeout=timeout)
    reds = [l.strip() for l in run.stdout.splitlines() if l.strip().startswith("FAIL")]
    shutil.rmtree(base, ignore_errors=True)
    return {"verdict": ANSWER, "reader": f"{cls}.{meth}",
            "suite_exit": run.returncode,
            "went_red": reds[:12], "red_count": len(reds),
            "bypassable": run.returncode == 0,
            "frozen_to": frozen[:80] + ("…" if len(frozen) > 80 else "")}


# ---------------------------------------------------------------------------
# T8 — the harness itself.
# ---------------------------------------------------------------------------
def t8_harness(fal_src, check_names):
    """The falsifier harness's own loop: does one raise stop the sweep?"""
    hits = []
    if not fal_src.ok:
        return hits
    for fn in fal_src.funcs:
        if fn.name != "main":
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.For):
                continue
            iter_name = _norm(node.iter)
            if "MUTATION" not in iter_name.upper() and "SUITE" not in iter_name.upper():
                continue
            guarded = any(isinstance(n, ast.Try) for n in ast.walk(node))
            restores = [n for n in ast.walk(node)
                        if isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Attribute)
                        and n.func.attr == "write_text"]
            if not guarded:
                hits.append({
                    "shape": "T8", "check": f"falsifiers.main() loop over {iter_name}",
                    "line": node.lineno, "function": "main",
                    "why": "the sweep's own loop has no exception guard",
                    "evidence": (
                        f"the body calls run()/write_text() with no try/finally, "
                        f"so one raise ends main() at mutation N: the mutations "
                        f"after it neither run nor report, no summary line is "
                        f"printed, and the {len(restores)} write_text() calls "
                        f"that restore the mutated file never happen. Every "
                        f"number the harness reports is then a number about a "
                        f"prefix of the list, presented as the whole"),
                    "confidence": "real"})
    # a mutation whose anchor is not in the file changes nothing
    mut = fal_src.module_consts.get("MUTATIONS")
    if isinstance(mut, (ast.List, ast.Tuple)):
        for elt in mut.elts:
            if not isinstance(elt, (ast.Tuple, ast.List)) or len(elt.elts) < 5:
                continue
            name = elt.elts[0]
            rel = elt.elts[1]
            find = elt.elts[2]
            expect = elt.elts[4]
            try:
                nm = ast.literal_eval(name)
                rl = ast.literal_eval(rel)
                fd = ast.literal_eval(find)
                ex = ast.literal_eval(expect)
            except Exception:                                # noqa: BLE001
                continue
            target = ROOT / rl
            text = target.read_text(encoding="utf-8") if target.exists() else ""
            n = text.count(fd)
            if n != 1:
                hits.append({
                    "shape": "T8", "check": f"mutation {nm!r}", "line": elt.lineno,
                    "function": "MUTATIONS",
                    "why": ("the anchor occurs %d times in %s" % (n, rl)),
                    "evidence": ("a mutation whose anchor is absent applies "
                                 "nothing; one that matches twice mutates only "
                                 "the first"),
                    "confidence": "real"})
            unknown = [e for e in ex if e not in check_names]
            if unknown:
                hits.append({
                    "shape": "T8", "check": f"mutation {nm!r}", "line": elt.lineno,
                    "function": "MUTATIONS",
                    "why": f"expects checks that do not exist: {unknown}",
                    "evidence": "an expectation no check can satisfy",
                    "confidence": "real"})
    return hits


# ---------------------------------------------------------------------------
def scan(checks_path, pkg_dir, falsifiers_path=None, weak=False):
    """Sweep one suite. Returns a verdict dict; never raises at this boundary."""
    src = Source(checks_path, pkg_dir)
    if not src.ok:
        return {"verdict": src.why, "path": str(checks_path)}
    checks = _find_checks(src)
    verdict_callees = _verdict_callees(src)
    hits, unscanned, effective = [], [], {}
    for chk in checks:
        got = []
        seeds = set()
        try:
            eff = (_shallow(chk.cond, src, chk.fn, chk.line)
                   if chk.cond is not None else None)
        except Exception as exc:                             # noqa: BLE001
            eff = chk.cond
            unscanned.append({"check": chk.name, "line": chk.line,
                              "detector": "substitution",
                              "why": f"{type(exc).__name__}: {exc}"})
        if eff is None:
            continue
        effective[chk.line] = eff
        for detector, fnc in (
                ("T1", lambda: t1_same_thing(chk, src, eff)),
                ("T2", lambda: t2_vacuous(chk, src, eff)),
                ("T3", lambda: t3_wrong_subject(chk, src, eff, verdict_callees)),
                ("T4", lambda: t4_one_seed(chk, src, eff, seeds)),
                ("T5", lambda: t5_zero_ratio(chk, src, eff)),
                ("T6", lambda: t6_detail_says_more(chk, src, eff, weak=weak))):
            try:
                got += fnc()
            except Exception as exc:                         # noqa: BLE001
                # A detector that dies must not take the sweep with it, and
                # must not be silently counted as "nothing found here".
                unscanned.append({"check": chk.name, "line": chk.line,
                                  "detector": detector,
                                  "why": f"{type(exc).__name__}: {exc}"})
        seen = set()
        for h in got:
            key = (h["shape"], h["line"], h["evidence"][:60])
            if key in seen:
                continue
            seen.add(key)
            hits.append(h)
    readers = served_readers(pkg_dir, src, checks, effective)
    names = {c.name for c in checks}
    fal_hits = []
    fal = None
    if falsifiers_path:
        fal = Source(falsifiers_path, pkg_dir)
        try:
            fal_hits = t8_harness(fal, names)
        except Exception as exc:                             # noqa: BLE001
            unscanned.append({"check": "tests/falsifiers.py", "line": 0,
                              "detector": "t8", "why": str(exc)})
    conditional = [c for c in checks
                   if not (isinstance(c.cond, ast.Constant) and c.cond.value is False)]
    return {
        "verdict": ANSWER,
        "checks_seen": len(checks),
        "checks_with_a_condition": len(conditional),
        "hits": hits + fal_hits,
        "unscanned": unscanned,
        "readers": readers,
        "unpinned_readers": [r for r in readers if not r["pinned_by"]],
    }


BLIND = """WHAT THIS SWEEP CANNOT SEE — the honest half of the number.
  * Anything inside the CODE UNDER TEST. A check whose condition is perfectly
    shaped still cannot fail if the function it calls answers from a cache,
    reads one store twice, or never enters the branch. T7 is the visible
    corner of that, and only --runtime measures it.
  * WHETHER A PROPERTY IS THE RIGHT ONE. Every check here could be green,
    non-vacuous and pinned, and still measure something nobody cares about.
  * MISSING CHECKS. A property with no check at all leaves no AST to read.
    (`unpinned_readers` is one narrow slice of this, no more.)
  * VALUES. `len(x) == 42` is pinned as a shape and wrong as a number if the
    coat has 41 pieces. Static reading cannot tell.
  * ANY CHECK NOT WRITTEN AS `check(name, condition, detail)`. Asserts,
    raises, and conditions built at run time are outside the sweep, and the
    count below says how many call sites it did read so that gap is visible.
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--checks", default=str(ROOT / "tests" / "run_checks.py"))
    ap.add_argument("--pkg", default=str(ROOT / "photoloset"))
    ap.add_argument("--falsifiers", default=str(ROOT / "tests" / "falsifiers.py"))
    ap.add_argument("--weak", action="store_true",
                    help="add the low-precision T6 tier (every unconstrained "
                         "interpolation, not only counters)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--runtime", action="store_true",
                    help="prove T7 by freezing each unpinned reader to a "
                         "literal and re-running the suite (~1 min each)")
    ap.add_argument("--runtime-also", default="",
                    help="comma-separated Class.method to probe as controls — "
                         "a reader a check DOES pin should come back red, "
                         "which is how the probe proves it can fail")
    ap.add_argument("--only", default="",
                    help="restrict --runtime to these Class.method readers")
    args = ap.parse_args(argv)

    out = scan(args.checks, args.pkg, args.falsifiers, weak=args.weak)
    if out["verdict"] != ANSWER:
        print(f"REFUSED {out['verdict']}: {out.get('path','')}")
        return 2

    if args.runtime:
        probes = list(out["unpinned_readers"])
        only = [w.strip() for w in args.only.split(",") if w.strip()]
        if only:
            probes = [r for r in probes
                      if f"{r['class']}.{r['method']}" in only]
        want = [w.strip() for w in args.runtime_also.split(",") if w.strip()]
        for w in want:
            cls, _, meth = w.partition(".")
            probes += [r for r in out["readers"]
                       if r["class"] == cls and r["method"] == meth]
        out["runtime"] = []
        for r in probes:
            try:
                out["runtime"].append(runtime_probe(r, ROOT))
            except Exception as exc:                         # noqa: BLE001
                out["runtime"].append({"verdict": "UNKNOWN_PROBE_FAILED",
                                       "reader": f"{r['class']}.{r['method']}",
                                       "why": f"{type(exc).__name__}: {exc}"})

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    print(f"scanned {out['checks_with_a_condition']} conditional check() call "
          f"sites of {out['checks_seen']} in {args.checks}\n")
    by_shape = {}
    for h in out["hits"]:
        by_shape.setdefault(h["shape"], []).append(h)
    for shape in sorted(by_shape):
        rows = by_shape[shape]
        print(f"{shape} — {len(rows)} hit(s)")
        for h in rows:
            print(f"  [{h['confidence']:10}] line {h['line']:<5} {h['check']}")
            print(f"      {h['why']}")
            print(f"      {h['evidence']}")
        print()
    print(f"T7 — served readers no check pins to a literal "
          f"({len(out['unpinned_readers'])} of {len(out['readers'])}). A "
          f"reader here can be replaced by a frozen constant — it stops "
          f"reading the store — with the suite green:")
    for r in out["unpinned_readers"]:
        how = ("read by " + ", ".join(f"`{n}`" for n in r["mentioned_by"])
               + ", but never against a literal") if r["mentioned_by"] \
            else "NO CHECK READS IT AT ALL"
        print(f"  {r['class']}.{r['method']:<20} {r['file']:<22} {how}")
    if out.get("runtime"):
        print("\nT7 by mutation — each reader below was replaced by the "
              "literal it returns today and the whole suite re-run:")
    for probe in out.get("runtime", []):
        if probe["verdict"] != ANSWER:
            print(f"  {probe.get('reader')}: {probe['verdict']} "
                  f"{probe.get('why', '')}")
            continue
        if probe["bypassable"]:
            print(f"  {probe['reader']:<26} BYPASSABLE — the store is never "
                  f"read and all checks stayed green (exit 0)")
        else:
            print(f"  {probe['reader']:<26} pinned — {probe['red_count']} "
                  f"check(s) went red: {probe['went_red'][:3]}")
    if out["unscanned"]:
        print(f"\nUNSCANNED ({len(out['unscanned'])}) — a detector refused "
              f"these and the sweep did not stop:")
        for u in out["unscanned"]:
            print(f"  {u['detector']} on line {u['line']} {u['check']}: {u['why']}")
    real = sum(1 for h in out["hits"] if h["confidence"] == "real")
    print(f"\n{len(out['hits'])} hits — {real} real, "
          f"{len(out['hits']) - real} borderline\n")
    print(BLIND)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
