#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**Find checks that cannot fail — mechanically, and report a NUMBER.**

    python3 tests/unfalsifiable.py             # scan the shipped suite
    python3 tests/unfalsifiable.py --self-test # prove the detectors detect
    python3 tests/unfalsifiable.py --weak      # add the low-precision tier
    python3 tests/unfalsifiable.py --json      # machine readable
    python3 tests/unfalsifiable.py --runtime --write-ledger --jobs 5
                                               # T7 by mutation: freeze every
                                               # reader, re-run the suite,
                                               # record what reddened
    python3 tests/unfalsifiable.py --checks PATH --pkg DIR   # another tree

Eleven checks that could not fail have been found in this project BY HAND,
across five passes. Every pass someone looked harder and found more. That is
not bad luck — a manual search has unknown completeness and rising cost. This
file replaces the eye with a sweep that reads ``tests/run_checks.py`` as an
ABSTRACT SYNTAX TREE (never a regular expression: a line-based scan reads the
shapes inside docstrings and misses every condition that wraps) and names,
per check, the shape by which its condition can be true while its property is
false.

**The shapes.**

  T1  the two sides of the comparison are the same thing. Module-level
      assignment is followed (``FORMULAS = _COAT.formulas()``); so are
      CHAINED comparisons, a tautology hoisted into a local beside an honest
      clause, a helper defined in this same file, and ``served["placement"]``
      where ``served`` came from a call on the same receiver. Two objects
      built by the same call read alike after substitution and ARE NOT the
      same thing: that is reported at borderline, never as a certainty.
  T2  ``all()``/``any()``, ``not <scan>``, ``len(bad) == 0``, ``bad == []``
      and ``sum(... ) == 0`` over an iterable this condition never pins
      NON-EMPTY. A length clause on a neighbouring check line does not count:
      that line fails separately and therefore protects nothing.
  T3  the subject under test is the wrong object — a refusal, a default, one
      sample where the name promises an invariance. Callees that answer WITH
      a verdict are learned from the PACKAGE as well as from this file, so
      the first check to introduce one is covered too.
  T4  both sides grow from ONE source and differ only by transforms that are
      allowed to be the identity (up to two). ``!=`` is NOT this shape: over
      one seed it goes red when the transform becomes the identity, which is
      the repair, not the defect.
  T5  a count or ratio that holds trivially at zero (``len(a) == len(b)``
      with neither pinned), chains included.
  T6  the real measurement is printed in the DETAIL while the asserted
      condition never constrains it — a counter over data the condition never
      names, or a second field of a measurement the condition does read
      (``gap["closed"]`` asserted, ``gap["worst"]`` only printed).
  T7  a served reader can bypass its store entirely with the suite green.
      **Not decidable by reading.** Freezing a reader to the literal it
      returns TODAY satisfies any comparison against that literal, so the
      static answer was a heuristic reported as a property; five readers
      passed it and could be replaced by a constant. ``--runtime`` freezes
      each reader and re-runs the whole suite, and ``tests/t7_readers.json``
      records the result keyed by a digest of the reader's own source.
  T8  the harness's own loop stops early, so what it did not run it also did
      not report. A ``try`` is not a guard: the handler has to catch
      everything, hand the operator's signals back, and restore in
      ``finally``.

**--self-test plants one check of every shape above and asserts each is
found**, alongside honest checks in the same shapes that must NOT be called
certainties. The corpus is ``tests/corpus/`` and it runs green: every planted
line PASSES and cannot fail, which is the only way to tell a detector from a
claim.

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
import os
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


def _single_return(fn):
    """The one expression a function returns, or ``None``.

    ``None`` for a function with no return, with more than one, or with a
    bare ``return`` — anything a reader could not follow in their head
    without executing it.
    """
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    if len(returns) != 1 or returns[0].value is None:
        return None
    return returns[0].value


def _substitute(node, mapping):
    """``node`` with each Name in ``mapping`` replaced by its expression."""
    if node is None:
        return None
    try:
        out = copy.deepcopy(node)
    except Exception:                                        # noqa: BLE001
        return node

    class T(ast.NodeTransformer):
        def visit_Name(self, n):                            # noqa: N802
            repl = mapping.get(n.id)
            return copy.deepcopy(repl) if repl is not None else n

    try:
        out = T().visit(out)
        ast.fix_missing_locations(out)
    except Exception:                                        # noqa: BLE001
        return node
    return out


def _dict_value(node, key):
    """``{...}[key]`` — the value expression under a literal key, or None."""
    if not isinstance(node, ast.Dict):
        return None
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and k.value == key:
            return v
    return None


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
        self.pkg_trees = {}      # module stem -> parsed tree
        self.pkg_dir = Path(pkg_dir) if pkg_dir else None
        if self.pkg_dir and self.pkg_dir.is_dir():
            for p in sorted(self.pkg_dir.glob("*.py")):
                try:
                    t = ast.parse(p.read_text(encoding="utf-8"))
                except Exception:                            # noqa: BLE001
                    continue
                self.pkg_trees[p.stem] = t
                for name, value in self._top_level(t).items():
                    self.pkg[(p.stem, name)] = value

        self.funcs = [n for n in ast.walk(self.tree)
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        #: Module-level ``def``s of the CHECKS file, by name. Name resolution
        #: used to stop at the check's own body, so a tautology one call away
        #: — ``def _same(v): return v.f() == v.f()`` — was invisible (B8a).
        self.helpers = {n.name: n for n in self.tree.body
                        if isinstance(n, ast.FunctionDef)}
        #: Every IDENTIFIER written in this file, lower-cased. Prose is not
        #: in here on purpose: a universal in a check name is a claim about
        #: data, and a noun that names no data is more likely English.
        self.identifiers = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Name):
                self.identifiers.add(node.id.lower())
            elif isinstance(node, ast.Attribute):
                self.identifiers.add(node.attr.lower())
            elif isinstance(node, ast.arg):
                self.identifiers.add(node.arg.lower())
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                   ast.ClassDef)):
                self.identifiers.add(node.name.lower())
            elif isinstance(node, ast.keyword) and node.arg:
                self.identifiers.add(node.arg.lower())
        #: Package functions and methods, by BARE NAME, with the single
        #: expression they return when they have exactly one. Two definitions
        #: of one name that return different text are dropped: guessing which
        #: one a call meant is how a detector starts inventing evidence.
        self.pkg_returns = self._package_returns()
        self._locals = {}        # func id -> name -> [(lineno, value)]
        self._loops = {}         # func id -> name -> [iter expressions]
        for fn in self.funcs:
            self._locals[id(fn)] = self._assignments(fn)
            self._loops[id(fn)] = self._loop_sources(fn)

    # -- collection ---------------------------------------------------------
    def _package_returns(self):
        """bare name -> the single expression that name returns, or None.

        A function with more than one ``return``, or two definitions of one
        name whose returns differ, maps to ``None`` — recorded rather than
        dropped, so a caller can tell "this cannot be followed" from "this
        name is unknown".
        """
        out = {}
        for tree in self.pkg_trees.values():
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                value = _single_return(node)
                if node.name in out and _norm(out[node.name]) != _norm(value):
                    out[node.name] = None
                    continue
                out[node.name] = value
        return out

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
        # A tautology one call away. Name resolution used to stop at the
        # check's own body, so ``def _same(v): return v.f() == v.f()`` with
        # ``check(name, _same(v), ...)`` was invisible (B8a). A helper
        # defined in this same file, with one return and matching arity, is
        # inlined the way a reader inlines it.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            key = ("h", node.func.id)
            helper = self.helpers.get(node.func.id)
            body = _single_return(helper) if helper is not None else None
            params = [a.arg for a in helper.args.args] if helper else []
            if (body is not None and key not in seen and not node.keywords
                    and len(node.args) == len(params)):
                if trace is not None:
                    trace.append(("helper", node.func.id))
                return self.canon(_substitute(body, dict(zip(params,
                                                             node.args))),
                                  fn, line, package=package, trace=trace,
                                  depth=depth + 1, seen=seen | {key})
        # ``served["placement"]`` where ``served = view.served()`` is the
        # call ``view.placement()`` written a second way — the shape found
        # by hand inside a check added the pass before this one.
        if (isinstance(node, ast.Subscript)
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)):
            skey = ("s", _norm(node.value), node.slice.value)
            if skey not in seen:
                inner = self.canon(node.value, fn, line, package=package,
                                   depth=depth + 1, seen=seen | {skey})
                got = self._returned_key(inner, node.slice.value)
                if got is not None:
                    if trace is not None:
                        trace.append(("returned", node.slice.value))
                    return self.canon(got, fn, line, package=package,
                                      trace=trace, depth=depth + 1,
                                      seen=seen | {skey})
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

    def _returned_key(self, call, key):
        """``f()[key]`` resolved to the expression ``f`` returns for it.

        Only for a callee with EXACTLY ONE return of a dict written out in
        full; ``self`` is rewritten to the receiver at the call site, so the
        answer is an expression the reader can check against the source.
        """
        if not isinstance(call, ast.Call):
            return None
        receiver = None
        if isinstance(call.func, ast.Attribute):
            name, receiver = call.func.attr, call.func.value
        elif isinstance(call.func, ast.Name):
            name = call.func.id
        else:
            return None
        body = self.pkg_returns.get(name)
        if body is None and name in self.helpers:
            body = _single_return(self.helpers[name])
        value = _dict_value(body, key)
        if value is None:
            return None
        return _substitute(value, {"self": receiver} if receiver is not None
                           else {})

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

            def visit_Call(self, n):                        # noqa: N802
                # A helper in this same file is one line of reading away, and
                # every detector below reads the EFFECTIVE condition — so a
                # vacuous all(), a zero ratio or a tautology written inside
                # `def _same(v): return v.f() == v.f()` was invisible to all
                # of them at once (B8a).
                self.generic_visit(n)
                if not isinstance(n.func, ast.Name) or n.keywords:
                    return n
                helper = src.helpers.get(n.func.id)
                body = _single_return(helper) if helper is not None else None
                if body is None:
                    return n
                params = [a.arg for a in helper.args.args]
                if len(params) != len(n.args):
                    return n
                changed[0] = True
                return _substitute(body, dict(zip(params, n.args)))

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


def _inserted_steps(short, long_, most=2):
    """The steps ``long_`` has that ``short`` does not, or None.

    ``None`` when ``long_`` is not ``short`` with up to ``most`` elements
    inserted. It used to demand EXACTLY ONE, so
    ``svg(tidy(doc)) == doc`` — two transforms over one seed, each free to
    become the identity — was outside the detector for no reason anyone had
    argued (B8b). Two is where it stops because the report has to name the
    steps, and a chain of five shares no seed a reader can check.
    """
    gap = len(long_) - len(short)
    if gap < 1 or gap > most:
        return None
    i = 0
    extra = []
    for item in long_:
        if i < len(short) and item == short[i]:
            i += 1
        elif len(extra) < gap:
            extra.append(item)
        else:
            return None
    return extra if i == len(short) else None


def _exprs(node):
    """The expression subnodes of a tree, by source text.

    Context and operator nodes are excluded on purpose: they all unparse to
    the same placeholder, and a set that contains that placeholder makes any
    two unrelated expressions look like they overlap — which is how a
    detector quietly stops detecting.
    """
    return {_norm(n) for n in ast.walk(node) if isinstance(n, ast.expr)}


def _comparisons(node):
    """Every PAIRWISE comparison in a tree, **chains decomposed**.

    ``a == b == c`` is two claims written as one node. Reading only
    ``len(n.ops) == 1`` — which is what this did — made every chained
    comparison invisible to T1, T4 and T5 at once (B3): ``b.seams() ==
    b.seams() == 5`` and ``len(a) == len(b) == len(c)`` both passed the
    sweep untouched. A chain is expanded into the comparisons it stands for,
    each as its own two-sided node, so the detectors need to know nothing
    about chains.
    """
    for n in ast.walk(node):
        if not isinstance(n, ast.Compare):
            continue
        if len(n.ops) == 1:
            yield n, n.left, n.comparators[0], n.ops[0]
            continue
        left = n.left
        for op, right in zip(n.ops, n.comparators):
            pair = ast.Compare(left=left, ops=[op], comparators=[right])
            ast.copy_location(pair, n)
            ast.fix_missing_locations(pair)
            yield pair, left, right, op
            left = right


def _cmp_pairs(chk, src, eff):
    """The comparisons of the condition AS WRITTEN **and** AS SUBSTITUTED.

    This was ``list(_comparisons(cond)) or list(_comparisons(eff))`` (B2),
    and the ``or`` meant that one honest comparison standing beside a
    tautology switched the substituted analysis off entirely — a tautology
    hoisted into a local one line above became invisible the moment anything
    else was compared in the same condition.

    Both are read now, and a pair is dropped only when another pair CANONS
    to the same claim, so one defect is still reported once and the quoted
    evidence is the text the reader wrote rather than the substituted form.
    """
    out, seen = [], set()
    for source in (chk.cond, eff):
        if source is None:
            continue
        for cmp_node, left, right, op in _comparisons(source):
            key = (src.cnorm(left, chk.fn, chk.line, package=False),
                   type(op).__name__,
                   src.cnorm(right, chk.fn, chk.line, package=False))
            if key in seen:
                continue
            seen.add(key)
            out.append((cmp_node, left, right, op))
    return out


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


def _is_literalish(node):
    """A value written out in full — a constant, or a display of constants."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_literalish(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(k is not None and _is_literalish(k) and _is_literalish(v)
                   for k, v in zip(node.keys, node.values))
    return False


def _root_name(node):
    """The innermost Name a chain of calls/attributes/subscripts hangs off."""
    cur = node
    for _ in range(24):
        if isinstance(cur, ast.Call):
            cur = cur.func
        elif isinstance(cur, ast.Attribute):
            cur = cur.value
        elif isinstance(cur, ast.Subscript):
            cur = cur.value
        else:
            break
    return cur.id if isinstance(cur, ast.Name) else None


def _independent_builds(src, chk, left, right):
    """Are the two sides rooted in two SEPARATELY BUILT objects?

    ``_shallow`` and ``canon`` rewrite a local to the expression it was
    assigned, so ``a = build(); b = build()`` makes ``a.f() == b.f()`` read
    as one text on both sides. That is a fact about the SOURCE, not about the
    values, and treating it as proof is B6 — the false positive that fires on
    every honest "two builds agree" check in a suite.

    One name appearing inside the other's construction is not independence:
    ``served = view.served()`` is derived FROM ``view``, and comparing a
    field of it against the same call IS one call written twice.
    """
    nl, nr = _root_name(left), _root_name(right)
    if nl is None or nr is None or nl == nr:
        return False
    vl = src.local_value(nl, chk.fn, chk.line)
    vr = src.local_value(nr, chk.fn, chk.line)
    if not isinstance(vl, ast.Call) or not isinstance(vr, ast.Call):
        return False
    if nr in {n.id for n in ast.walk(vl) if isinstance(n, ast.Name)}:
        return False
    if nl in {n.id for n in ast.walk(vr) if isinstance(n, ast.Name)}:
        return False
    return True


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

    pairs = _cmp_pairs(chk, src, eff)
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
            elif fixed and _is_literalish(lc) and _is_literalish(rc):
                # **Pinning a package constant is a check, not a tautology.**
                # `cross.GENERIC_MIN_SOURCES == 2` reads as `2 == 2` after
                # resolution and goes RED the day somebody edits the package
                # — which is the whole reason to write it. The T1 shape is a
                # constant that IS a live call (`FORMULAS = _COAT.formulas()`),
                # and that is what the branch below reports.
                continue
            elif fixed:
                hits.append(_hit(
                    chk, "T1",
                    "one side is a constant evaluated from the other",
                    f"{raw_l} == {raw_r}; both are `{cl}` once the "
                    f"module-level assignment of {', '.join(fixed)} is "
                    f"followed", "real"))
            elif _independent_builds(src, chk, left, right):
                # Two DIFFERENT objects that happen to be built by the same
                # call read alike after substitution — the text is identical
                # and the objects are not (B6). Such a check CAN go red: it
                # goes red the day the two builds disagree. Reporting it as
                # a certainty is the false positive that gets a scanner
                # switched off, so it is named and rated for what it is.
                hits.append(_hit(
                    chk, "T1", "two objects built by the same call",
                    f"{raw_l} == {raw_r}; both read as `{_short(cl, 70)}` "
                    f"because `{_root_name(left)}` and `{_root_name(right)}` "
                    f"are built the same way — but they are two objects, and "
                    f"this line goes red the day they disagree",
                    "borderline"))
            else:
                alias_line, other = 0, None
                for side in (left, right):
                    root = _root_name(side)
                    if root is not None:
                        got = [ln for ln, _v in src._locals.get(
                            id(chk.fn), {}).get(root, []) if ln <= chk.line]
                        if got:
                            # The window opens where the SNAPSHOT was taken,
                            # not at the top of the function: reading it from
                            # line 0 made every earlier call on the receiver
                            # look like the mutation in between, which is how
                            # `served["placement"] == view.placement()` was
                            # read as an honest before/after.
                            alias_line = max(alias_line, got[-1])
                    if not isinstance(side, ast.Name):
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
                # The receivers CANON DIFFERENTLY here — they were built from
                # different arguments, or one was mutated. Two such objects
                # agreeing is a property that can fail, and reporting it at
                # "real" is B6: `honest.build('a').pieces() ==
                # honest.build('b').pieces()` goes red the moment one build
                # drops a piece. Only receivers that resolve to ONE
                # expression are a certainty here.
                same_receiver = _norm(src.canon(lc.func.value, chk.fn,
                                                chk.line)) == \
                    _norm(src.canon(rc.func.value, chk.fn, chk.line))
                hits.append(_hit(
                    chk, "T1",
                    "two calls of one method, nothing pinning what it returns",
                    f"{raw_l} == {raw_r} — the same .{lc.func.attr}() on two "
                    f"receivers; whatever one side drops, the other drops too"
                    + ("" if pinned else
                       ". No other clause pins either side to a literal")
                    + ("" if same_receiver else
                       f". The receivers are different objects "
                       f"(`{_short(_norm(lc.func.value), 40)}` and "
                       f"`{_short(_norm(rc.func.value), 40)}`), so this line "
                       f"CAN go red — rated borderline for that reason"),
                    "real" if same_receiver and not pinned else "borderline"))
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


#: Names that wrap a collection without changing whether it is empty.
_SIZE_NEUTRAL = ("len", "sum", "sorted", "list", "set", "tuple", "frozenset")


def _empty_claims(chk, src, eff):
    """Every way this condition says "the scan found nothing".

    ``not bad`` was the only spelling this looked for. ``len(bad) == 0`` and
    ``sum(1 for x in xs if wrong(x)) == 0`` say exactly the same thing, are
    vacuously true over an empty scan in exactly the same way, and were
    matched by neither T2 nor T5 (B4). ``bad == []`` was caught only by
    accident, through T1.
    """
    out = []
    for source in (chk.cond, eff):
        if source is None:
            continue
        for n in ast.walk(source):
            if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
                if isinstance(n.operand, (ast.Name, ast.Attribute,
                                          ast.Subscript, ast.Call)):
                    out.append((n.operand, _norm(n)))
        for cmp_node, left, right, op in _comparisons(source):
            for a, b in ((left, right), (right, left)):
                zero = (isinstance(b, ast.Constant) and b.value == 0
                        and not isinstance(b.value, bool)
                        and isinstance(op, (ast.Eq, ast.LtE)))
                one_lt = (isinstance(b, ast.Constant) and b.value == 1
                          and isinstance(op, ast.Lt) and a is left)
                empty = (isinstance(op, ast.Eq) and isinstance(
                    b, (ast.List, ast.Tuple, ast.Set, ast.Dict))
                    and not _is_display(b))
                if not (zero or one_lt or empty):
                    continue
                node = a
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id in _SIZE_NEUTRAL and node.args):
                    node = node.args[0]
                out.append((node, _norm(cmp_node)))
    return out


def _scan_chain(target, src, fn, line, rounds=4):
    """``target`` and the iterables it was scanned from, outermost last.

    Empty when nothing says ``target`` is a scan at all — an emptiness claim
    over a value that was never filled by a loop or a comprehension is not
    this shape, and inventing a root for it would be inventing evidence.
    """
    chain = []
    node = target
    for _ in range(rounds):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in _SIZE_NEUTRAL and node.args):
            node = node.args[0]
            continue
        chain.append(node)
        # `for cn, seats in twin.cores.items()` is a scan over `twin.cores`,
        # and a condition that sizes `twin.cores` has pinned it. Reading only
        # the written form would demand the two be spelled the same way.
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("items", "values", "keys")
                and not node.args):
            chain.append(node.func.value)
        root = None
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)) \
                and node.generators:
            root = node.generators[0].iter
        elif isinstance(node, ast.Name):
            value = src.local_value(node.id, fn, line)
            if isinstance(value, (ast.ListComp, ast.SetComp,
                                  ast.GeneratorExp)) and value.generators:
                root = value.generators[0].iter
            else:
                iters = src.loop_iters(node.id, fn)
                root = iters[0] if iters else None
        if root is None:
            break
        node = root
    return chain if len(chain) > 1 else []


def t2_vacuous(chk, src, eff):
    """A quantifier, or any claim of emptiness, over something that may be
    empty — and nothing in the same condition says it is not."""
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
    told = set()
    for target, written in _empty_claims(chk, src, eff):
        text = _norm(target)
        if text in told or text in pinned:
            continue
        chain = _scan_chain(target, src, chk.fn, chk.line)
        if not chain:
            continue
        if any(_norm(node) in pinned
               or _nonempty_by_construction(node, src, chk.fn, chk.line)
               for node in chain):
            continue
        told.add(text)
        root = _norm(chain[-1])
        hits.append(_hit(
            chk, "T2", "an emptiness claim over an unpinned scan",
            f"`{_short(written, 60)}` is true when the scan found nothing AND "
            f"when the scan covered nothing: {_short(text, 50)} is filled "
            f"from {_short(root, 70)}, whose size this condition never "
            f"asserts", "real"))
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
    # **Learning only from this file leaves the FIRST such check unprotected**
    # — the moment a refusal subject is introduced is exactly the moment it
    # matters, and until some other check reads ['verdict'] off it the tool
    # said nothing (B8c). The package knows which functions answer with a
    # verdict: they return a dict that has one.
    for name, body in src.pkg_returns.items():
        if _dict_value(body, "verdict") is not None:
            callees.add(name)
    return callees


def _is_verdict_callee(func_node, callees):
    """Is this callee one that answers WITH a verdict?

    Matched on the written form and on the bare name, so a package function
    reached as ``mod.f()`` and one reached as ``f()`` are the same fact.
    """
    text = _norm(func_node)
    if text in callees:
        return True
    tail = func_node.attr if isinstance(func_node, ast.Attribute) else (
        func_node.id if isinstance(func_node, ast.Name) else "")
    return bool(tail) and tail in callees


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
        if not _is_verdict_callee(value.func, verdict_callees):
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
    m = re.search(r"\b(every|all|each)\s+([A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]*){0,2})",
                  low)
    if m:
        words = [w for w in m.group(2).split() if len(w) > 2]
        noun = words[0] if words else ""
        singulars = [w[:-1] if w.endswith("s") and len(w) > 4 else w
                     for w in words]
        singular = singulars[0] if singulars else noun
        pool = set()
        for n in list(ast.walk(eff)) + list(ast.walk(cond)):
            if isinstance(n, ast.Name) and n.id not in src.alias:
                pool.add(n.id)
            elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                pool.add(n.value)
            elif isinstance(n, ast.Attribute):
                pool.add(n.attr)
        if not any(w in p.lower() for p in pool
                   for w in set(words) | set(singulars)):
            # **Is the noun a thing, or is it prose?** `not all readers are
            # unpinned` reads like a universal over `unpinned`, and three
            # checks were flagged on that word alone. A noun that appears
            # NOWHERE in the file is far more likely to be English than data,
            # so it is reported at borderline: named, and not counted as a
            # certainty.
            known = any(singular in ident for ident in src.identifiers)
            hits.append(_hit(
                chk, "T3",
                f"the name quantifies over {noun}; the condition does not",
                f"nothing the condition touches is named for `{noun}` — "
                f"`{_short(_norm(chk.cond), 120)}`. The universal in the name "
                f"is not the universal that is measured"
                + ("" if known else
                   f". `{noun}` is not a name anywhere in this file, so this "
                   f"may be prose rather than a claim"),
                "real" if known else "borderline"))
    return hits


def t4_one_seed(chk, src, eff, already):
    """One seed, one transform that is allowed to be the identity.

    **Only ``==``.** This accepted ``!=`` too, and for ``!=`` the whole
    argument inverts: ``transform(x) != x`` goes RED exactly when the
    transform becomes the identity, which is the property holding. That is
    the repair a T4 asks for, and reporting it as the defect (B5) tells the
    author to undo the fix — the worst thing a detector can do.
    """
    hits = []
    if chk.cond is None:
        return hits
    for cmp_node, left, right, op in _cmp_pairs(chk, src, eff):
        if not isinstance(op, ast.Eq):
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
        extra = _inserted_steps(short, long_)
        if not extra:
            continue
        if all(step in COPY_STEPS for step in extra):
            continue
        if f"{bl}|{'+'.join(extra)}" in already:
            continue
        already.add(f"{bl}|{'+'.join(extra)}")
        steps = ", ".join(extra)
        hits.append(_hit(
            chk, "T4", "both sides grow from one source",
            f"{_short(_norm(left), 80)} == {_short(_norm(right), 80)}: both "
            f"start at `{_short(bl, 60)}` and differ by "
            f"{'one step' if len(extra) == 1 else f'{len(extra)} steps'} "
            f"({steps}). The comparison holds whenever "
            f"{'that step is' if len(extra) == 1 else 'those steps are'} the "
            f"identity — including on the day "
            f"{'it silently becomes one' if len(extra) == 1 else 'they silently do'}",
            "real"))
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


def _subscript_base(node):
    """``(object, key)`` for ``x['k']`` written with a literal key."""
    if (isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)):
        return _norm(node.value), node.slice.value
    return None, None


def t6_detail_says_more(chk, src, eff, weak=False):
    """The detail prints a measurement; the condition never constrains it.

    **The exemption is what makes or breaks this one.** It used to intersect
    the sub-expressions of the counter's argument with those of the
    SUBSTITUTED condition, and since substitution rewrites every local to the
    expression it was assigned, two different objects built by the same call
    become textually identical and ANY shared fragment — ``coat``, ``set()``,
    a string key — exempted the counter. Measured on the shipped suite: 96
    counters, 55 exempt by exact match, 41 exempt by a shared fragment, 0
    reported. A detector that reports zero because its exemption fires on
    nearly everything is not a clean bill of health; it is a dead detector
    (finding 10).

    So the exemption is now what it says: the condition has to mention THE
    COUNTED THING — the counter's own argument — not merely something the
    counted thing was built from.
    """
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
        base, key = _subscript_base(expr)
        sibling = None
        if base:
            asked = {k for b, k in
                     [_subscript_base(n) for n in
                      list(ast.walk(chk.cond)) + list(ast.walk(eff))]
                     if b == base and k}
            if asked and key not in asked:
                sibling = sorted(asked)
        if not counter and not sibling and not weak:
            continue
        if text in parts or _norm(_shallow(expr, src, chk.fn, chk.line)) in parts:
            continue
        if counter:
            # printing len(X) is constrained enough if the condition says
            # anything about X ITSELF — compared after the same substitution
            # the condition got, so two spellings of one expression are not
            # read as two expressions, and NOT by any shared fragment.
            inner = expr.args[0]
            # `len(set(missing))` is constrained by a condition that says
            # anything about `missing`: wrapping data in set()/sorted()/list()
            # does not make it a different measurement. Stripping only the
            # counter's OWN wrappers is not the old fragment rule — it never
            # looks at what the data was built from.
            while (isinstance(inner, ast.Call)
                   and isinstance(inner.func, ast.Name)
                   and inner.func.id in _SIZE_NEUTRAL and inner.args):
                inner = inner.args[0]
            spellings = {_norm(inner),
                         _norm(_shallow(inner, src, chk.fn, chk.line)),
                         src.cnorm(inner, chk.fn, chk.line, package=False)}
            if spellings & parts:
                continue
        seen.add(text)
        if sibling and not counter:
            # **The condition reads this very measurement, and asks a
            # different question of it.** `gap['closed']` asserted while
            # `gap['worst']` is only printed is the shape the drape figures
            # sit in: the project states its invariant in a distance, the
            # suite asserts a boolean, and the distance can move to anything.
            # Borderline on purpose — a sibling key may be a label rather
            # than a measurement, and this tool does not know types.
            hits.append(_hit(
                chk, "T6", "a second field of a measurement the condition "
                           "does read",
                f"the detail prints `{_short(text, 60)}` while the condition "
                f"asks {base} only for {', '.join(sibling)}. The printed "
                f"figure can move to anything and this line still says PASS",
                "borderline"))
            continue
        hits.append(_hit(
            chk, "T6" if counter else "T6-weak",
            "the detail reports a number the condition never constrains",
            f"the detail computes `{_short(text, 80)}`; the condition is "
            f"`{_short(cond_text, 120)}`, which never mentions it. That number "
            f"can move to anything and the line still prints PASS",
            "real" if counter else "borderline"))
    return hits


# ---------------------------------------------------------------------------
# T7 — served readers. **Answered by mutation. Never by reading.**
#
# This used to call a reader "pinned" when some check compared it against a
# literal, and report `0 of 18 pinned to nothing` as a clean bill of health.
# It is not the property. Freezing a reader to THE LITERAL IT RETURNS TODAY
# satisfies that comparison exactly, and five of the eighteen readers could be
# replaced by a frozen constant with the whole suite green (B1). A literal
# comparison is COVERAGE — evidence that somebody looked at the reader — and
# it is reported under that name now. The verdict comes from freezing the
# reader and re-running the suite, which is a measurement.
# ---------------------------------------------------------------------------
#: class -> (module to import, expression that builds one). A reader that
#: cannot be built cannot be probed, and that is reported, not skipped.
BUILDERS = {
    "BlockView": ("photoloset.block", "block.coat()"),
    "Library": ("photoloset.parts", "parts.Library()"),
}

#: Checks whose reddening says nothing about the reader. The ledger gate
#: below compares the current package against a recorded probe, so freezing
#: ANY reader reddens it; counting that would make every reader look pinned,
#: which is a detector that cannot fail — the disease itself, one level up.
PROBE_IGNORE = (
    # reads this very ledger, so freezing ANY reader reddens it
    "no check that cannot fail",
    "every served reader reads its store",
    # runs the whole suite again inside a mutated tree: with a reader frozen
    # its baseline is dirty before a single mutation is applied, so it
    # reddens for every reader and would make every reader look pinned
    "the falsifier harness reports every mutation",
)


def _method_source(pkg_dir, cls, meth):
    """The exact source of one reader, or "" — the thing a probe is about."""
    for path in sorted(Path(pkg_dir).glob("*.py")):
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except Exception:                                    # noqa: BLE001
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.ClassDef) and node.name == cls):
                continue
            for m in node.body:
                if isinstance(m, ast.FunctionDef) and m.name == meth:
                    return ast.get_source_segment(text, m) or ""
    return ""


def reader_fingerprint(pkg_dir, cls, meth):
    """A digest of the reader's own source, so a stale probe cannot pass.

    A recorded verdict is about ONE body of code. Re-using it after that body
    changes is the same error as pinning a reader against the literal it
    happens to return: it looks like evidence and measures nothing.
    """
    import hashlib
    src = _method_source(pkg_dir, cls, meth)
    return hashlib.md5(src.encode("utf-8")).hexdigest() if src else ""


def served_readers(pkg_dir, checks_src, checks, effective):
    """Public no-argument readers of a store, and what the suite does with one.

    ``compared_against_a_literal`` is not "pinned" and is not called that any
    more: it is the checks that put this reader's result next to a constant.
    Whether the reader can be REPLACED by that constant is answered by
    ``runtime_probe`` and by nothing else.
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
                    "fingerprint": reader_fingerprint(pkg_dir, cls.name,
                                                      meth.name),
                    "mentioned_by": sorted(set(mentions)),
                    "compared_against_a_literal": sorted(set(pinning)),
                })
    return out


PROBE = r'''
import json, sys
sys.path.insert(0, {root!r})
import {module} as _m
{alias}
print(json.dumps({{"value": repr({builder}.{meth}())}}))
'''

CONFIRM = r'''
import sys
sys.path.insert(0, {root!r})
import {module} as _m
{alias}
got = repr({builder}.{meth}())
print("SAME" if got == {frozen!r} else "DIFFERENT")
'''


def _probe_scripts(module, builder, meth, root, frozen=None):
    """The two one-liners a probe runs, with the import spelled once."""
    alias = f"{builder.split('.')[0]} = _m"
    kw = dict(root=str(root), module=module, alias=alias, builder=builder,
              meth=meth)
    if frozen is None:
        return PROBE.format(**kw)
    return CONFIRM.format(frozen=frozen, **kw)


def runtime_probe(reader, repo_root, *, pkg_rel="photoloset",
                  checks_rel="tests/run_checks.py", builders=None,
                  ignore=PROBE_IGNORE, timeout=1800):
    """**Freeze one reader to a literal and re-run the suite.**

    A reader that no longer reads its store, with every check still green, is
    a reader nothing pins — whatever the literals in the checks file suggest.
    This is the only honest answer to T7, and the control that shows the probe
    itself can fail is in the output: freezing ``formulas()`` reddens four
    checks, freezing ``sleeve_required()`` reddens none.

    Refusals are return values here too: a reader that cannot be built, or
    whose value has no literal form, comes back UNKNOWN with the reason.
    """
    builders = dict(BUILDERS if builders is None else builders)
    cls, meth = reader["class"], reader["method"]
    if cls not in builders:
        return {"verdict": "UNKNOWN_NO_BUILDER", "reader": f"{cls}.{meth}",
                "why": f"nothing in BUILDERS says how to construct a {cls}"}
    module, builder = builders[cls]
    env = dict(os.environ)
    env["PHOTOLOSET_T7_PROBE"] = "1"          # never probe from inside a probe
    got = subprocess.run(
        [sys.executable, "-c", _probe_scripts(module, builder, meth,
                                              repo_root)],
        capture_output=True, text=True, cwd=str(repo_root), timeout=600,
        env=env)
    if got.returncode != 0:
        return {"verdict": "UNKNOWN_READER_NOT_REACHABLE",
                "reader": f"{cls}.{meth}", "why": got.stderr.strip()[-300:]}
    frozen = json.loads(got.stdout)["value"]
    base = Path(tempfile.mkdtemp(prefix="unfalsifiable_"))
    repo = base / "repo"
    try:
        shutil.copytree(repo_root, repo,
                        ignore=shutil.ignore_patterns(".git", "__pycache__",
                                                      "*.pyc", "build", "dist"))
        target = None
        for path in sorted((repo / pkg_rel).glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == cls:
                    for m in node.body:
                        if isinstance(m, ast.FunctionDef) and m.name == meth:
                            target = (path, m)
        if target is None:
            return {"verdict": "UNKNOWN_NO_SUCH_READER",
                    "reader": f"{cls}.{meth}"}
        path, m = target
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        body_start = m.body[0].lineno - 1
        end = m.body[-1].end_lineno
        indent = " " * (len(lines[body_start]) - len(lines[body_start].lstrip()))
        lines[body_start:end] = [
            f"{indent}return {frozen}  # BYPASS: never reads the store\n"]
        path.write_text("".join(lines), encoding="utf-8")
        # **Did the freeze actually take?** A value with no literal form would
        # break the import and redden everything, which reads as "pinned" and
        # is not a measurement of anything.
        same = subprocess.run(
            [sys.executable, "-c", _probe_scripts(module, builder, meth, repo,
                                                  frozen=frozen)],
            capture_output=True, text=True, cwd=str(repo), timeout=600,
            env=env)
        if same.returncode != 0 or same.stdout.strip() != "SAME":
            return {"verdict": "UNKNOWN_FROZEN_VALUE_IS_NOT_A_LITERAL",
                    "reader": f"{cls}.{meth}",
                    "why": (same.stdout.strip() + " " +
                            same.stderr.strip()[-200:]).strip()}
        run = subprocess.run([sys.executable, checks_rel],
                             cwd=str(repo), capture_output=True, text=True,
                             timeout=timeout, env=env)
        reds = [l.strip() for l in run.stdout.splitlines()
                if l.strip().startswith("FAIL")]
        counted = [r for r in reds
                   if not any(name in r for name in ignore)]
        return {"verdict": ANSWER, "reader": f"{cls}.{meth}",
                "suite_exit": run.returncode,
                "went_red": [_short(r, 90) for r in counted[:12]],
                "red_count": len(counted),
                "ignored_reds": len(reds) - len(counted),
                "bypassable": not counted,
                "fingerprint": reader.get("fingerprint", ""),
                "frozen_to": frozen[:80] + ("…" if len(frozen) > 80 else "")}
    finally:
        shutil.rmtree(base, ignore_errors=True)


#: Where the runtime answers live between runs. A probe costs a whole suite
#: run per reader, so the suite reads this ledger every time and re-measures
#: it on demand — a detector nobody runs is worse than none.
LEDGER = ROOT / "tests" / "t7_readers.json"


def read_ledger(path=None):
    """The recorded probes. A refusal is a return value."""
    path = Path(path or LEDGER)
    if not path.exists():
        return {"verdict": "UNKNOWN_NO_LEDGER", "path": str(path),
                "readers": {}}
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:                                 # noqa: BLE001
        return {"verdict": f"UNKNOWN_UNREADABLE_LEDGER: {exc}",
                "path": str(path), "readers": {}}
    got.setdefault("readers", {})
    got["verdict"] = ANSWER
    return got


def ledger_gate(readers, ledger=None):
    """**Is every served reader covered by a probe of THIS code, and green?**

    Three ways to fail, and each is a different sentence: a reader nobody
    probed, a reader whose body changed since it was probed, and a reader the
    probe found BYPASSABLE. The third is the defect T7 is named for; the first
    two are the ways a recorded number stops being about the code.
    """
    got = read_ledger(ledger)
    recorded = got.get("readers", {})
    missing, stale, bypassable = [], [], []
    for r in readers:
        key = f"{r['class']}.{r['method']}"
        entry = recorded.get(key)
        if entry is None:
            missing.append(key)
            continue
        if entry.get("fingerprint") != r.get("fingerprint"):
            stale.append(key)
            continue
        # **The reader is half of it; the checks are the other half.** A
        # recorded "pinned" says some check went red when this reader was
        # frozen. Delete that check and the record is about a suite that no
        # longer exists — so the checks which READ this reader are recorded
        # too, and one going missing is staleness, not silence.
        lost = sorted(set(entry.get("mentioned_by", []))
                      - set(r.get("mentioned_by", [])))
        if lost:
            stale.append(f"{key} (the check(s) that read it are gone: {lost})")
            continue
        if entry.get("verdict") != ANSWER:
            missing.append(f"{key} ({entry.get('verdict')})")
            continue
        if entry.get("bypassable"):
            bypassable.append(key)
    return {"verdict": got.get("verdict", ANSWER),
            "probed": len(recorded), "readers": len(readers),
            "missing": sorted(missing), "stale": sorted(stale),
            "bypassable": sorted(bypassable),
            "generated": got.get("generated", ""),
            "ok": (got.get("verdict") == ANSWER and not missing and not stale
                   and not bypassable)}


def write_ledger(probes, readers, path=None, suite="tests/run_checks.py"):
    """Record what the probes measured, keyed by reader and fingerprint."""
    path = Path(path or LEDGER)
    prints = {f"{r['class']}.{r['method']}": r for r in readers}
    out = {
        "what": ("T7 by mutation: each reader below was replaced by the "
                 "literal it returns today and the whole suite was re-run. "
                 "`bypassable` means nothing went red — the reader stopped "
                 "reading its store and the suite did not notice."),
        "how": "python3 tests/unfalsifiable.py --runtime --write-ledger",
        "ignored": list(PROBE_IGNORE),
        "suite": suite,
        "generated": _now(),
        "readers": {},
    }
    for probe in probes:
        key = probe.get("reader", "?")
        entry = dict(probe)
        entry["file"] = prints.get(key, {}).get("file", "")
        entry["mentioned_by"] = prints.get(key, {}).get("mentioned_by", [])
        entry.setdefault("fingerprint", prints.get(key, {}).get("fingerprint", ""))
        out["readers"][key] = entry
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1,
                               sort_keys=True) + "\n", encoding="utf-8")
    return {"verdict": ANSWER, "path": str(path), "readers": len(out["readers"])}


def _now():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d")


def run_probes(readers, repo_root, *, jobs=4, **kw):
    """Every reader, probed. Order of the result follows ``readers``.

    Serial, this is one suite run per reader — 18 readers is half an hour,
    which is how the honest detector ended up switched off. They are
    independent, each in its own copy of the tree, so they run together.
    """
    import concurrent.futures as cf
    out = [None] * len(readers)

    def one(i):
        try:
            return i, runtime_probe(readers[i], repo_root, **kw)
        except Exception as exc:                             # noqa: BLE001
            return i, {"verdict": "UNKNOWN_PROBE_FAILED",
                       "reader": f"{readers[i]['class']}.{readers[i]['method']}",
                       "why": f"{type(exc).__name__}: {exc}"}

    with cf.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        for i, got in pool.map(one, range(len(readers))):
            out[i] = got
    return out


# ---------------------------------------------------------------------------
# T8 — the harness itself.
# ---------------------------------------------------------------------------
def _handler_kinds(handler):
    """What one ``except`` clause catches, as written."""
    if handler.type is None:
        return ["<bare except>"]
    if isinstance(handler.type, ast.Tuple):
        return [_norm(e) for e in handler.type.elts]
    return [_norm(handler.type)]


def _reraises_operator_signals(handler):
    """Does this handler hand ^C and SystemExit back to the operator?"""
    for n in ast.walk(handler):
        if not isinstance(n, ast.Raise):
            continue
        if n.exc is None:                       # a bare re-raise
            return True
        if _norm(n.exc) == handler.name:
            return True
    return False


def t8_harness(fal_src, check_names, root=None):
    """The falsifier harness's own loop: does one raise stop the sweep?

    **A ``try`` is not a guard.** This asked only whether a ``try`` appeared
    anywhere in the loop, so narrowing ``except BaseException`` to ``except
    ValueError`` — which restores the exact defect this exists to find, since
    a ``TimeoutExpired`` or a ``FileNotFoundError`` then ends the sweep at
    entry N — read as guarded and produced zero hits (B7). What the entry
    needs is: a handler that catches everything, the operator's own signals
    handed back, and the restore in a ``finally`` so the next entry is scored
    against a clean tree.
    """
    hits = []
    root = Path(root) if root is not None else ROOT
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
            tries = [n for n in ast.walk(node) if isinstance(n, ast.Try)]
            broad, narrow = [], []
            for t in tries:
                for h in t.handlers:
                    kinds = _handler_kinds(h)
                    if any(k in ("<bare except>", "BaseException", "Exception")
                           for k in kinds):
                        broad.append((t, h, kinds))
                    else:
                        narrow.append((t, h, kinds))
            guarded = bool(broad)
            restores = [n for n in ast.walk(node)
                        if isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Attribute)
                        and n.func.attr == "write_text"]
            in_finally = [n for t in tries for stmt in t.finalbody
                          for n in ast.walk(stmt)
                          if isinstance(n, ast.Call)
                          and isinstance(n.func, ast.Attribute)
                          and n.func.attr in ("write_text", "write")]
            if tries and not guarded:
                caught = sorted({k for _t, _h, kinds in narrow for k in kinds})
                hits.append({
                    "shape": "T8",
                    "check": f"falsifiers.main() loop over {iter_name}",
                    "line": node.lineno, "function": "main",
                    "why": (f"the sweep's guard catches only {', '.join(caught)}"),
                    "evidence": (
                        f"a try/except is present and it is not a guard: "
                        f"anything outside {', '.join(caught)} — a "
                        f"TimeoutExpired from run()'s own timeout, a "
                        f"FileNotFoundError from a moved anchor, a KeyError "
                        f"from a marker that did not arrive — still ends "
                        f"main() at entry N. The entries after it neither run "
                        f"nor are named, and every number printed then "
                        f"describes a prefix presented as the whole"),
                    "confidence": "real"})
            if tries and restores and not in_finally:
                hits.append({
                    "shape": "T8",
                    "check": f"falsifiers.main() loop over {iter_name}",
                    "line": node.lineno, "function": "main",
                    "why": "the restore is not in a finally",
                    "evidence": (
                        f"{len(restores)} write_text() call(s) restore the "
                        f"mutated file and none of them is in a finally, so a "
                        f"raise inside the run leaves the tree MUTATED and "
                        f"every later entry is scored against somebody else's "
                        f"regression"),
                    "confidence": "real"})
            for _t, h, kinds in broad:
                if "BaseException" in kinds and not _reraises_operator_signals(h):
                    hits.append({
                        "shape": "T8",
                        "check": f"falsifiers.main() loop over {iter_name}",
                        "line": h.lineno, "function": "main",
                        "why": "BaseException is caught and never handed back",
                        "evidence": (
                            "KeyboardInterrupt and SystemExit are swallowed "
                            "into a MISS line, so an interrupted sweep reports "
                            "as a measured one"),
                        "confidence": "borderline"})
            if not guarded and not tries:
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
            target = root / rl
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
def scan(checks_path, pkg_dir, falsifiers_path=None, weak=False, root=None,
         ledger=None):
    """Sweep one suite. Returns a verdict dict; never raises at this boundary."""
    root = Path(root) if root is not None else ROOT
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
            # One defect, one line. The condition and its substituted form are
            # both read now (B2), and a chained comparison is read link by
            # link (B3), so the same finding arrives in several spellings; the
            # key is the SHAPE and the REASON, not the wording.
            key = (h["shape"], h["line"], h["why"])
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
            fal_hits = t8_harness(fal, names, root=root)
        except Exception as exc:                             # noqa: BLE001
            unscanned.append({"check": "tests/falsifiers.py", "line": 0,
                              "detector": "t8", "why": str(exc)})
    # **Say how many were actually READ.** A `check(name=…, ok=…)` call site
    # carries no positional condition, and counting it as scanned inflates the
    # headline with call sites no detector ever looked at (B8d). Those are
    # named as unscanned instead.
    conditional = [c for c in checks if c.cond is not None
                   and not (isinstance(c.cond, ast.Constant)
                            and c.cond.value is False)]
    for c in checks:
        if c.cond is None:
            unscanned.append({"check": c.name, "line": c.line,
                              "detector": "all",
                              "why": ("no positional condition — written as "
                                      "check(name=…, ok=…), which no detector "
                                      "reads")})
    return {
        "verdict": ANSWER,
        "checks_seen": len(checks),
        "checks_with_a_condition": len(conditional),
        "hits": hits + fal_hits,
        "unscanned": unscanned,
        "readers": readers,
        "readers_no_check_reads": [r for r in readers if not r["mentioned_by"]],
        "readers_compared_to_a_literal":
            [r for r in readers if r["compared_against_a_literal"]],
        "ledger": ledger_gate(readers, ledger),
    }


BLIND = """WHAT THIS SWEEP CANNOT SEE — the honest half of the number.
  * ANYTHING INSIDE THE CODE UNDER TEST. A check whose condition is perfectly
    shaped still cannot fail if the function it calls answers from a cache,
    reads one store twice, or never enters the branch. T7 is the visible
    corner of that, and only --runtime measures it.
  * ONE READER AT A TIME. --runtime freezes readers singly, so two readers
    that pin only each other would both come back pinned. No pair, and no
    larger set, is ever frozen together.
  * A LEDGER IS A RECORD, NOT A MEASUREMENT. Between --runtime passes the T7
    verdict is read from tests/t7_readers.json. It is keyed by a digest of
    each reader's source and by the checks that read it, so stale answers and
    deleted checks turn it red — but a hand-edited ledger is believed.
  * WHETHER A PROPERTY IS THE RIGHT ONE. Every check here could be green,
    non-vacuous and pinned, and still measure something nobody cares about.
  * MISSING CHECKS. A property with no check at all leaves no AST to read.
  * VALUES. `len(x) == 42` is pinned as a shape and wrong as a number if the
    coat has 41 pieces. Static reading cannot tell.
  * ANY CHECK NOT WRITTEN AS `check(name, condition, detail)`. Asserts,
    raises, and conditions built at run time are outside the sweep; the
    keyword form `check(name=..., ok=...)` carries no positional condition
    and is counted as UNSCANNED rather than as swept.
  * A CONDITION ASSEMBLED AT RUN TIME — getattr, a dict of predicates, eval.
    There is no AST for a comparison that does not exist until it runs.
  * HELPERS THAT BRANCH. A helper in this file is followed only when it has
    exactly ONE return; a tautology behind an if/else, a loop or a helper in
    ANOTHER module is invisible.
  * SCANS FILLED BY A CALL. T2 follows a collection back through
    comprehensions and `for` loops in the same function. `bad = collect(x)`
    stops it, and `len(bad) == 0` over that is not reported.
  * MORE THAN TWO INSERTED TRANSFORMS. T4 names the steps it found; a chain
    of three or more shares a seed it no longer tries to prove.
  * COMPUTED KEYS. T6's "second field of the same measurement" reads literal
    string keys only: gap[k] and gap.get("worst") are not seen.
  * PROSE IN A NAME. T3's universal is a heuristic over English. A noun that
    names nothing in the file is demoted to borderline, not silenced.
"""

# ---------------------------------------------------------------------------
# --self-test — the scanner scanned.
# ---------------------------------------------------------------------------
CORPUS = ROOT / "tests" / "corpus"

#: check name -> (shape it must be reported under, what it is here to prove).
#: Every entry is a check that PASSES and carries a clause that cannot go red;
#: ``tests/corpus/planted_checks.py`` runs green on purpose.
PLANTED = {
    "P-T1-literal": ("T1", "a literal condition"),
    "P-T1-twice": ("T1", "one read written twice"),
    "P-T1-module-const": ("T1", "a module constant that IS the call"),
    "P-T1-hoisted-beside": ("T1", "B2 — a tautology hoisted into a local, "
                                  "beside an honest clause"),
    "P-T1-chained": ("T1", "B3 — the tautology is one link of a chain"),
    "P-T1-helper": ("T1", "B8a — the tautology is inside a helper"),
    "P-T1-subscript": ("T1", "a subscript of a local bound to a call on the "
                             "same receiver"),
    "P-T2-all-empty": ("T2", "all() over a scan nothing sizes"),
    "P-T2-not-scan": ("T2", "`not <scan>` over a scan nothing sizes"),
    "P-T2-len-zero": ("T2", "B4 — the same vacuum written as a count"),
    "P-T2-sum-zero": ("T2", "B4 — the same vacuum written as a sum"),
    "P-T3-verdict-known": ("T3", "a verdict subject never constrained"),
    "P-T3-verdict-unread": ("T3", "B8c — the same, over a callee this file "
                                  "never reads as ['verdict']"),
    "P-T3-universal: every sleeve is served": ("T3", "a universal in the name "
                                                     "the condition does not "
                                                     "measure"),
    "P-T4-one-step": ("T4", "one seed, one transform that may be the identity"),
    "P-T4-two-steps": ("T4", "B8b — the same with two inserted steps"),
    "P-T5-zero-ratio": ("T5", "a ratio that holds at zero"),
    "P-T5-chained": ("T5", "B3 — the same ratio written as a chain"),
    "P-T6-detail-shared": ("T6", "finding 10 — a counter the condition never "
                                 "constrains, sharing a fragment with it"),
    "P-T6-detail-clean": ("T6", "a counter the condition never mentions"),
}

#: What the honest file is allowed to draw. `borderline` means the tool may
#: name it as long as it does not call it a certainty; anything reported REAL
#: here is a false positive, and the number is printed either way.
HONEST_CEILING = {
    "H-two-objects-agree": "borderline",
    "H-prose: not all readers are unpinned": "borderline",
}


def self_test(corpus=None, verbose=True, report=False):
    """**Plant one check of every shape, and prove each one is found.**

        python3 tests/unfalsifiable.py --self-test

    A scanner with no self-test is a claim. This one runs four measurements
    and fails on any of them:

      1. every shape in ``PLANTED`` is reported, under the shape it claims;
      2. the honest file draws no REAL hit — the false-positive number, which
         is what decides whether anyone leaves the tool switched on;
      3. the T8 detector accepts an honest harness and rejects one whose
         ``except`` was narrowed;
      4. T7 by mutation, on a fixture whose answer is known: a reader the
         corpus suite makes TRACK its store comes back pinned, and a reader
         the suite only compares against a literal comes back BYPASSABLE —
         which is the difference the static reading cannot see.
    """
    corpus = Path(corpus or CORPUS)
    pkg = corpus / "mini"
    fails, lines = [], []
    say = lines.append

    say("1. PLANTED — one check of every shape, each of them green and "
        "unable to go red")
    got = scan(corpus / "planted_checks.py", pkg, corpus / "narrow_harness.py",
               root=corpus, ledger=corpus / "no_such_ledger.json")
    if got["verdict"] != ANSWER:
        fails.append(f"the planted corpus did not parse: {got['verdict']}")
        _self_test_end(fails, say)
        if verbose:
            print("\n".join(lines))
        return (fails, lines) if report else 1
    found = {}
    for h in got["hits"]:
        found.setdefault(h["check"], set()).add(h["shape"])
    for name, (shape, why) in sorted(PLANTED.items()):
        ok = shape in found.get(name, set())
        say(f"   {'FOUND ' if ok else 'MISSED'}  {shape}  {name:<42} {why}")
        if not ok:
            fails.append(f"{shape} {name}: planted and not reported "
                         f"(reported as {sorted(found.get(name, [])) or 'nothing'})")
    extra = sorted(set(found) - set(PLANTED))
    if extra:
        say(f"   also reported (not planted, so not asserted): {extra}")

    say("\n2. HONEST — checks that CAN go red, in the shapes the detectors "
        "get wrong")
    clean = scan(corpus / "honest_checks.py", pkg, corpus / "honest_harness.py",
                 root=corpus, ledger=corpus / "no_such_ledger.json")
    real = [h for h in clean["hits"] if h["confidence"] == "real"]
    borderline = [h for h in clean["hits"] if h["confidence"] != "real"]
    for h in clean["hits"]:
        ceiling = HONEST_CEILING.get(h["check"], "none")
        bad = (ceiling == "none") or (ceiling == "borderline"
                                      and h["confidence"] == "real")
        say(f"   {'FALSE+' if bad else 'named '}  {h['shape']}  "
            f"[{h['confidence']}] {h['check']}")
        if bad:
            fails.append(f"false positive: {h['shape']} {h['confidence']} on "
                         f"{h['check']}")
    say(f"   {clean['checks_with_a_condition']} honest checks, {len(real)} "
        f"reported REAL, {len(borderline)} borderline")

    say("\n3. T8 — the harness's own guard")
    for name, want in (("honest_harness", 0), ("narrow_harness", 1)):
        src = Source(corpus / f"{name}.py", pkg)
        hits = [h for h in t8_harness(src, {"H-tracks-the-store"}, root=corpus)
                if "guard catches only" in h["why"]]
        ok = (len(hits) >= want) if want else not hits
        say(f"   {'PASS' if ok else 'FAIL'}  {name}: "
            f"{len(hits)} narrowed-guard hit(s), wanted "
            f"{'at least one' if want else 'none'}")
        if not ok:
            fails.append(f"T8 on {name}: {len(hits)} hits, wanted {want}")

    say("\n4. T7 BY MUTATION — the same two readers, one pinned and one not, "
        "and the static reading cannot tell them apart")
    readers = {f"{r['class']}.{r['method']}": r for r in clean["readers"]}
    for meth, want_bypassable in (("zones", False), ("motto", True)):
        reader = readers.get(f"MiniView.{meth}")
        if reader is None:
            fails.append(f"T7: MiniView.{meth} is not even listed as a reader")
            continue
        literal = bool(reader["compared_against_a_literal"])
        probe = runtime_probe(reader, corpus, pkg_rel="mini",
                              checks_rel="honest_checks.py",
                              builders={"MiniView": ("mini.store",
                                                     "store.view()")},
                              ignore=(), timeout=300)
        if probe["verdict"] != ANSWER:
            fails.append(f"T7 probe on {meth}: {probe['verdict']} "
                         f"{probe.get('why','')}")
            say(f"   REFUSED  MiniView.{meth}: {probe['verdict']}")
            continue
        ok = probe["bypassable"] == want_bypassable
        verdict = ("BYPASSABLE — the store is never read and the suite "
                   "stayed green" if probe["bypassable"]
                   else f"pinned, {probe['red_count']} check(s) went red")
        say(f"   {'PASS' if ok else 'FAIL'}  MiniView.{meth:<8} "
            f"compared against a literal: {str(literal):<5} "
            f"frozen and re-run: {verdict}")
        if not ok:
            fails.append(f"T7 probe on {meth}: bypassable="
                         f"{probe['bypassable']}, wanted {want_bypassable}")
    _self_test_end(fails, say)
    if verbose:
        print("\n".join(lines))
    return (fails, lines) if report else (1 if fails else 0)


def _self_test_end(fails, say):
    if fails:
        say(f"\n{len(fails)} SELF-TEST FAILURE(S):")
        for f in fails:
            say(f"  {f}")
    else:
        say("\nself-test: every planted shape found, no honest check called "
            "a certainty, the harness guard read for what it catches, and T7 "
            "answered by mutation")
    return fails


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
                    help="answer T7 by freezing EVERY served reader to the "
                         "literal it returns today and re-running the whole "
                         "suite (one suite run per reader; see --jobs)")
    ap.add_argument("--write-ledger", action="store_true",
                    help="record what --runtime measured into "
                         "tests/t7_readers.json, which the suite then gates on")
    ap.add_argument("--jobs", type=int, default=4,
                    help="how many probes run at once (each gets its own copy "
                         "of the tree)")
    ap.add_argument("--only", default="",
                    help="restrict --runtime to these Class.method readers")
    ap.add_argument("--self-test", action="store_true",
                    help="plant one check of every shape this tool claims to "
                         "detect and assert each one is found")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    out = scan(args.checks, args.pkg, args.falsifiers, weak=args.weak)
    if out["verdict"] != ANSWER:
        print(f"REFUSED {out['verdict']}: {out.get('path','')}")
        return 2

    if args.runtime:
        # EVERY reader, not only the ones no literal touches. The old pass
        # probed `unpinned_readers`, which on this repo is empty — so the
        # honest detector ran on nothing and printed nothing precisely when
        # the static one claimed success (B1).
        probes = list(out["readers"])
        only = [w.strip() for w in args.only.split(",") if w.strip()]
        if only:
            probes = [r for r in probes
                      if f"{r['class']}.{r['method']}" in only]
        print(f"probing {len(probes)} reader(s), {args.jobs} at a time — one "
              f"whole suite run each\n", flush=True)
        out["runtime"] = run_probes(probes, ROOT, jobs=args.jobs)
        if args.write_ledger:
            wrote = write_ledger(out["runtime"], probes)
            print(f"ledger: {wrote['readers']} reader(s) -> {wrote['path']}\n")

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

    gate = out["ledger"]
    print(f"T7 — {len(out['readers'])} served reader(s). **A literal in a "
          f"check is not a pin**: freezing a reader to the literal it returns "
          f"today satisfies the comparison and reads the store never. The "
          f"verdict below is by mutation.")
    print(f"  ledger {LEDGER.name}: {gate['probed']} recorded"
          + (f", generated {gate['generated']}" if gate['generated'] else "")
          + (f" — {gate['verdict']}" if gate['verdict'] != ANSWER else ""))
    for label, rows in (("NEVER PROBED", gate["missing"]),
                        ("STALE (the reader changed since it was probed)",
                         gate["stale"]),
                        ("BYPASSABLE — frozen to a constant, suite green",
                         gate["bypassable"])):
        for name in rows:
            print(f"  {label:<52} {name}")
    for r in out["readers_no_check_reads"]:
        print(f"  {'NO CHECK READS IT AT ALL':<52} "
              f"{r['class']}.{r['method']} ({r['file']})")
    if gate["ok"]:
        print("  every served reader was probed against this exact code and "
              "at least one check went red for each")
    if out.get("runtime"):
        print("\nT7 by mutation — each reader below was replaced by the "
              "literal it returns today and the whole suite re-run "
              f"(reds from {', '.join(PROBE_IGNORE)} do not count: that check "
              f"reads this very ledger):")
    for probe in out.get("runtime", []):
        if probe["verdict"] != ANSWER:
            print(f"  {probe.get('reader')}: {probe['verdict']} "
                  f"{probe.get('why', '')}")
            continue
        if probe["bypassable"]:
            print(f"  {probe['reader']:<26} BYPASSABLE — the store is never "
                  f"read and every check stayed green")
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
