# -*- coding: utf-8 -*-
"""Falsifier harness — **can each check actually fail?**

    python3 tests/falsifiers.py

A check that cannot fail is not a check, and this project shipped EIGHT of
those before anyone noticed, in FOUR passes — 1, then 3, then 5-6, then 7-8.
Every pass somebody read the suite harder and found more, which is why the
sweep is now a program (``tests/unfalsifiable.py``, wired into the suite as
"no check that cannot fail") rather than a habit:

  1. ``placement_check`` read one unmutated store twice.
  2. ``coat fills its root node exactly`` only held while the arms were
     storage drawers.
  3. ``formulas served from the cross`` compared ``b.formulas()`` against
     ``garment_pattern.FORMULAS``, which IS ``b.formulas()``.
  4. ``seams served from the cross`` compared ``b.seams()`` against
     ``garment_sew.SEAMS``, which IS ``b.seams()``.
  5. ``every tool returns an object`` was ``check(name, True, ...)`` — a
     literal. Found by hunting the shape of 3 and 4 across the whole suite
     instead of fixing only the two that were reported.
  6. ``every tool has a schema`` — the line DIRECTLY ABOVE the fifth, left
     alone when the fifth was repaired. ``all(pred for t in tools)`` over a
     list that arrives over the wire is vacuously True when the list is
     empty, so a server answering ``tools/list`` with ``[]`` left it GREEN
     while its sibling went red. The count clause lived on a neighbouring
     check line, which fails separately and therefore protects nothing.

The shape to hunt is wider than "compares a value against itself": it is
**any condition that cannot be false**. A literal, a self-comparison, and an
``all()``/``any()`` over a possibly-empty sequence are the same defect.

  7. ``BlockView.placement()`` and 8. ``BlockView.label()`` — SERVED READERS
     no check pinned to a literal. Not a defective condition but a MISSING
     one: each was replaced with a frozen constant that never touches the
     store, and all 81 checks stayed green. Under the placement bypass the
     SKIRT was served the coat's sleeve placement and three skirt checks
     printed byte-identical details.

**Two numbers this file used to state, corrected.** It said "0 compare
against any of the 10 module constants that are read off the coat store" —
the substantive claim was right, but there are **6** such constants
(``garment_pattern`` REQUIRED / SLEEVE_REQUIRED / FORMULAS / EASE_IN and
``garment_sew`` SEAMS / PLACEMENT), not 10. And it said "every surviving
``all()`` now has its iterable's length pinned inside the same condition":
**six did not** — that sweep read the expression PASSED to ``check()``, so an
``all()`` hoisted into a local one line above was invisible to it. Both are
why the sweep is a program now: it resolves single-assignment locals, and it
prints how many call sites it actually read.

Every one of them survived a review because nobody built the store, or the
code, that violates the property. That is what this file is for.

So this runs the other direction. It copies the tree, regresses ONE fix at a
time back to the pre-repair behaviour, re-runs the cross checks, and asserts
that the check which claims that property turns FAIL. A mutation that leaves
everything green means the check is decoration and the property is not
actually pinned.

``tests/run_checks.py`` carries the other half: every check there builds the
store that violates its property inline and asserts the store is rejected.
This file proves the checks notice when the CODE regresses; those assertions
prove they notice when the DATA is wrong.

**And this file had the defect it exists to find, one level up.** Its own
loop had no guard, so one raise — a missing file, ``run``'s own
``subprocess.TimeoutExpired``, an ``eval`` of a marker that never arrived —
ended ``main()`` at mutation N: the entries after it neither ran nor were
named, none of the three summary lines printed, and because the restoring
``write_text`` sat AFTER ``run`` rather than in a ``finally``, the working
copy was left mutated for everybody after it. Measured before the repair: a
poisoned entry at index 35 of 38 printed 35 verdicts, a bare traceback and
rc=1, and 7 of 43 entries vanished without a word. Now every entry is
wrapped, a raise is that ENTRY going MISS, the file is restored in
``finally``, the run prints **how many entries it got through**, and every
file it touched is compared against the pristine source at the end.

    python3 tests/falsifiers.py --self-test

runs the harness over three entries with a poisoned one in the middle, twice
— raising before the file is read, and raising inside the run after the file
is already mutated — and passes only if the entries after the poison still
ran and went red, the poison was named, the summary printed and the tree came
back clean. The suite runs it as "the falsifier harness reports every
mutation".
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple

SRC = Path(__file__).resolve().parent.parent

#: The in-process runner, once, over whichever named sections a sweep is
#: scored against. **The whole suite takes seven minutes**, and a mutation
#: that only a handful of checks can notice does not need the other 120 run
#: to prove it: the LOOP sweep below regresses the look loop and is scored
#: against the look loop's own three sections. What still needs the whole
#: suite — a check DISAPPEARING, which by construction cannot be seen by
#: running only the functions that still declare it — is in WHOLE_SUITE.
_RUNNER_TEMPLATE = '''
import sys, io, contextlib
sys.path.insert(0, ".")
import tests.run_checks as rc
FNS = (%s)
# Every name these three functions promise, from the functions themselves.
DECLARED = [n for fn in FNS for n in fn.check_names]
out = io.StringIO()
crashes = []
with contextlib.redirect_stdout(out):
    for fn in FNS:
        try:
            fn()
        except BaseException as e:
            # ``@declares`` should make this unreachable — every name reports
            # from inside ``section``, crash or no crash. If it fires anyway
            # the harness must say so rather than score the run.
            crashes.append(fn.__name__ + ": " + type(e).__name__ + ": " + str(e))
print("::DECLARED::" + repr(DECLARED))
print("::NEVERRAN::" + repr(rc.NEVER_RAN))
print("::GUARDCRASH::" + repr(rc.CRASHED_NAMES))
print("::REPORTED::" + repr(rc.REPORTED))
print("::CRASHED::" + repr(crashes))
print("::FAILED::" + repr(rc.FAILED_NAMES))
# **Why** each red line went red, not only which. A mutation that turns an
# UNEXPECTED check red is a fact about the tree, and reading it used to mean
# re-running the section by hand.
print("::WHY::" + repr([f[:300] for f in rc.FAILURES]))
'''

RUNNER = _RUNNER_TEMPLATE % ("rc.the_block_lives_on_the_cross, "
                             "rc.the_arms_carry_meaning,\n"
                             "       rc.the_cross_refuses_what_it_should")

#: The look loop's own three sections: retrieval, construction/confirmation,
#: and the gate.
LOOP_RUNNER = _RUNNER_TEMPLATE % ("rc.retrieval_asks_per_part, "
                                  "rc.the_look_becomes_a_shape,\n"
                                  "       rc.the_gate_holds")

# (name, file, find, replace, checks we expect to go red)
MUTATIONS = [
    ("#1 the seat arm goes back to being whichever kind arrived first",
     "photoloset/cross.py",
     '    out: List[str] = []\n'
     '    for e in (seat.get("values") or []):',
     '    out: List[str] = []\n'
     '    for e in (seat.get("values") or [])[:1]:',
     ["a seat carries every kind that reached it"]),

    ("#1 the same claim may be seated twice", "photoloset/cross.py",
     '                    if tok in claims:',
     '                    if False:',
     ["a seat carries every kind that reached it"]),

    ("#0 corroboration discards the incoming kind", "photoloset/cross.py",
     'or entry["kind"] != kind:', 'or False:',
     ["a specific claim cannot buy a generic one"]),

    ("#4 agreement goes back to bare ==", "photoloset/cross.py",
     'if _vkey(entry["value"]) != vkey ', 'if entry["value"] != value ',
     ["equal is not the same observation"]),

    # The write-side branch this entry used to regress is gone: counting the
    # quarantine seats ALONE could never be the binding constraint once the
    # core's total is counted, and a constraint that can never bind is the
    # code form of a check that cannot fail. What is still worth regressing
    # is the REPORTING — census() naming the quarantined seats, which is what
    # keeps the exemption from being silent.
    ("#5 census stops naming the quarantined seats", "photoloset/cross.py",
     '            free = sum(1 for x in s if x["arm"] is None)\n'
     '            if free:',
     '            free = 0\n'
     '            if free:',
     ["the quarantine core obeys the same law"]),

    ("P1 order check re-reads one store instead of re-ingesting",
     "photoloset/cross.py",
     "    for name, order in orders.items():\n        st = CrossStore()",
     "    _shared = CrossStore()\n"
     "    for name, order in orders.items():\n        st = _shared",
     ["ingest order does not move answers"]),

    ("P2 capacity consulted before contest", "photoloset/cross.py",
     '        found = self._find_seat(core, key)\n        if found is not None:',
     '        found = self._find_seat(core, key)\n'
     '        if arm is not None and found is not None and \\\n'
     '                self._arm_load(found[0], arm) >= FACES_PER_ARM:\n'
     '            return {"verdict": ARM_FULL, "core": found[0], "arm": arm,\n'
     '                    "key": key, "how_to_close": "regressed"}\n'
     '        if found is not None:',
     ["contest is reachable at every address"]),

    ("P2b resolution goes back to core-local", "photoloset/cross.py",
     '        out = [core]\n        seen = {core}\n        i = 0',
     '        return [core]\n        out = [core]\n        seen = {core}\n        i = 0',
     ["a contest survives the matryoshka"]),

    ("P3 the arm stops being derived from the kind", "photoloset/cross.py",
     '                if vals and vals[0].get("kind") in KIND_ARM:',
     '                if False and vals and vals[0].get("kind") in KIND_ARM:',
     ["arms are derived, not chosen", "absence is not a claim"]),

    ("P3 typed gaps go back to prose", "photoloset/cross.py",
     '        cen = self.arm_census(core)\n'
     '        return [ARM_GAP_VERDICT[a] for a in ARMS if not cen[a]]',
     '        return []',
     ["empty arms are typed gaps"]),

    ("P7 capacity counts triples again", "photoloset/cross.py",
     "        found = self._find_seat(core, key)",
     "        found = None if source else self._find_seat(core, key)",
     ["agreement does not consume seats"]),

    ("P7 a generic claim is believed on one source", "photoloset/cross.py",
     'GENERIC_MIN_SOURCES = 2', 'GENERIC_MIN_SOURCES = 1',
     ["a generic claim needs two sources"]),

    ("P4 link stores whatever it is handed", "photoloset/cross.py",
     "        if bad:\n"
     "            r = {\"verdict\": DANGLING_EDGE, \"why\": bad, "
     "\"stored\": False,",
     "        if bad:\n"
     "            self.edges.append({\"a\": a, \"b\": b, \"label\": label,\n"
     "                               \"value\": value})\n"
     "            return {\"verdict\": \"ANSWER\",\n"
     "                    \"index\": len(self.edges) - 1}\n"
     "        if bad:\n"
     "            r = {\"verdict\": DANGLING_EDGE, \"why\": bad, "
     "\"stored\": False,",
     ["an edge with one end is refused"]),

    ("P5 reading invents the core it failed to find", "photoloset/cross.py",
     '        seats: List[Tuple[str, Dict[str, Any]]] = []\n'
     '        for cname in self._closure(core):',
     '        seats: List[Tuple[str, Dict[str, Any]]] = []\n'
     '        self._core(core)\n'
     '        for cname in self._closure(core):',
     ["reads create nothing, loads are verified"]),

    ("P5 from_dict stops verifying the geometry", "photoloset/cross.py",
     '        st.load_verdict = st.verify()',
     '        st.load_verdict = {"verdict": "ANSWER"}',
     ["arms are derived, not chosen", "absence is not a claim",
      "agreement does not consume seats", "a contest survives the matryoshka",
      "an edge with one end is refused",
      "reads create nothing, loads are verified"]),

    ("P6 the store keeps the caller's object", "photoloset/cross.py",
     '        seat = {"key": key, "arm": arm,\n'
     '                "seq": self._next_seq() if seq is None else seq,\n'
     '                "values": [{"value": copy.deepcopy(value), "kind": kind,',
     '        seat = {"key": key, "arm": arm,\n'
     '                "seq": self._next_seq() if seq is None else seq,\n'
     '                "values": [{"value": value, "kind": kind,',
     ["the store owns its values"]),

    ("P0 ordered reads follow traversal again", "photoloset/block.py",
     '        out.sort(key=lambda r: (r["seq"], r["key"]))\n        return out',
     '        return out',
     ["ordered reads follow the declaration"]),

    ("P8 ingest goes back to the non-nesting writer", "photoloset/block.py",
     '        st.put(core, "role", {"name": piece_name, "required": required},\n'
     '               "declared", source)',
     '        st.put_strict(core, "role",\n'
     '                      {"name": piece_name, "required": required},\n'
     '                      "declared", source)',
     ["a fourth piece and a fifth measurement are declarable"]),

    ("an undeclared subject strands the seat", "photoloset/block.py",
     '    if subject in declared:\n        return piece_core(root, subject)',
     '    return piece_core(root, subject)\n'
     '    if subject in declared:\n        return piece_core(root, subject)',
     ["an undeclared subject does not swallow the seat"]),

    ("the new cross-subject hazard is picked silently", "photoloset/block.py",
     '        vals = [_cross._vkey(h["value"]) for h in hits]\n'
     '        if any(v != vals[0] for v in vals[1:]):',
     '        vals = [_cross._vkey(h["value"]) for h in hits]\n'
     '        if False:',
     ["param refuses across subjects"]),

    # ---- #4: the repair that stopped at the writer ----------------------
    ("#4 resolve() folds equal-but-distinguishable back together",
     "photoloset/cross.py",
     '        if all(_vkey(e["value"]) == vk_first for _cn, e in entries):',
     '        if all(e["value"] == first for _cn, e in entries):',
     ["equal is not the same observation"]),

    ("#4 contested() folds them back together", "photoloset/cross.py",
     '                if any(v != vks[0] for v in vks[1:]):',
     '                if any(v != vals[0] for v in vals[1:]):',
     ["equal is not the same observation"]),

    # ---- #2: the guard that was on _collect but not _ordered ------------
    ("#2 a collection read picks silently across subjects",
     "photoloset/block.py",
     '        seen: Dict[Any, Dict[str, Any]] = {}\n        for r in out:',
     '        seen: Dict[Any, Dict[str, Any]] = {}\n        for r in []:',
     ["two subjects cannot declare the same thing"]),

    ("#2 pieces() stops asking about the served name", "photoloset/block.py",
     'for f in self._ordered("role", ident=lambda r: r["value"]["name"]):',
     'for f in self._ordered("role"):',
     ["two subjects cannot declare the same thing"]),

    # The hole the #2 fix left open: the ident callback can itself fail, and
    # answering that with `continue` let the malformed seat evade the gate
    # AND stay in the returned list, so the reader crashed on it.
    ("#2 a seat that cannot name itself is skipped instead of refused",
     "photoloset/block.py",
     '            except Exception as exc:',
     '            except Exception as exc:\n'
     '                continue',
     ["a seat that cannot name itself is refused"]),

    # ---- #3 / #11: the arm-valued answers outside the order map ---------
    ("#3 the order check stops comparing the arm", "photoloset/cross.py",
     '            shape = (r.get("arm"), tuple(r.get("arms") or ()))',
     '            shape = ()',
     ["placement does not move answers"]),

    ("#11 the order check stops comparing which arm was charged",
     "photoloset/cross.py",
     '            shape = (r.get("arm"), tuple(r.get("arms") or ()))',
     '            shape = (None, tuple(r.get("arms") or ()))',
     ["ingest order does not move answers",
      "placement does not move answers"]),

    # ---- #9: "formulas served from the cross" could not fail ------------
    ("#9 formulas() bypasses the store entirely", "photoloset/block.py",
     '        return {f["key"].split(":", 1)[1]: f["value"]\n'
     '                for f in self._ordered("formula:")}',
     '        return {n: t for n, t, _s in FORMULA_ORDER}',
     ["formulas served from the cross"]),

    ("#9 one formula never reaches the store", "photoloset/block.py",
     '    for row in formulas:\n        name, text, subject = _formula_row(row)',
     '    for row in list(formulas)[1:]:\n'
     '        name, text, subject = _formula_row(row)',
     ["formulas served from the cross"]),

    # ---- #8: "seams served from the cross" could not fail ---------------
    ("#8 seams() bypasses the store entirely", "photoloset/block.py",
     '    def seams(self) -> List[Dict[str, Any]]:\n'
     '        return [f["value"] for f in self._ordered("seam:")]',
     '    def seams(self) -> List[Dict[str, Any]]:\n'
     '        return list(COAT_DECLARATION["seams"])',
     ["seams served from the cross"]),

    ("#7 seam_edges' endpoints drift back to arm coordinates",
     "photoloset/block.py",
     '        return self.store.edges_labeled("seam:")',
     '        return [dict(e, a=("block:coat", "pieces", "x"))\n'
     '                for e in self.store.edges_labeled("seam:")]',
     ["seams served from the cross"]),

    # ---- #10: placement_check reporting a constant ----------------------
    ("#10 placement_check goes back to reporting a constant",
     "photoloset/cross.py",
     '        plan = self.write_plan()\n'
     '        r = ingest_order_check(plan, nest=True)',
     '        plan = []\n'
     '        r = {"verdict": "ANSWER", "addresses": 0, "orders": 3,\n'
     '             "differences": [], "structural": True}',
     ["placement does not move answers"]),

    # ---- #12: the tool boundary that was never refused ------------------
    ("#12 from_dict_checked answers ANSWER whatever it is handed",
     "photoloset/cross.py",
     '        return {"verdict": st.load_verdict["verdict"], "store": st,',
     '        return {"verdict": "ANSWER", "store": st,',
     ["reads create nothing, loads are verified"]),

    # ---- #13: three refusals nothing exercised --------------------------
    ("#13 an unknown claim kind is registered silently",
     "photoloset/cross.py",
     '        if kind not in KIND_ARM:\n'
     '            return {"verdict": NO_SUCH_KIND, "which": kind,',
     '        if kind not in KIND_ARM:\n'
     '            KIND_ARM[kind] = "kind-"\n'
     '        if kind not in KIND_ARM:\n'
     '            return {"verdict": NO_SUCH_KIND, "which": kind,',
     ["reads create nothing, loads are verified"]),

    ("#13 census() stops reporting over capacity", "photoloset/cross.py",
     '                if load > FACES_PER_ARM:\n'
     '                    over.append((n, arm, load))',
     '                if load > FACES_PER_ARM and False:\n'
     '                    over.append((n, arm, load))',
     ["reads create nothing, loads are verified"]),

    ("#13 contested() scans one core instead of the nest closure",
     "photoloset/cross.py",
     '        for cname in list(self.cores):\n'
     '            closure = self._closure(cname)\n'
     '            token = frozenset(closure)\n'
     '            if token in done:\n'
     '                continue\n'
     '            done.add(token)\n'
     '            by_key:',
     '        for cname in list(self.cores):\n'
     '            closure = [cname]\n'
     '            token = frozenset(closure)\n'
     '            if token in done:\n'
     '                continue\n'
     '            done.add(token)\n'
     '            by_key:',
     ["a contest survives the matryoshka"]),

    # ---- #5: the quarantine exemption must stay visible -----------------
    ("#5 census() stops naming the quarantined seats", "photoloset/cross.py",
     '            free = sum(1 for x in s if x["arm"] is None)\n'
     '            if free:',
     '            free = sum(1 for x in s if x["arm"] is None)\n'
     '            if False:',
     ["the quarantine core obeys the same law"]),

]


class Run:
    """One mutated run: which lines reported, which went red, what crashed.

    ``reported`` is the exact name list, not a column slice of the printed
    output — see the note on ``run_checks.REPORTED``.
    """

    def __init__(self, reported: list, failed: list, crashed: list,
                 note: str = "", declared: list = (), never_ran: list = (),
                 guard_crash: list = (), why: list = ()) -> None:
        self.reported = reported
        self.failed = failed
        self.crashed = crashed
        self.note = note
        self.declared = list(declared)
        self.never_ran = list(never_ran)
        self.guard_crash = list(guard_crash)
        self.why = list(why)


#: **No bytecode, ever, in a mutated tree.** ``-B`` plus the environment
#: variable, because a cached ``.pyc`` outlives the source it was compiled
#: from: CPython validates the cache against the source's SIZE and its mtime
#: IN WHOLE SECONDS, and a mutation whose replacement is the same length
#: ("no_match" -> "proposed") changes neither when the mutate-and-restore
#: completes inside one second. Measured before this: the look sweep's
#: no_match entry leaked into the NEXT entry's run in roughly one run of
#: three, turning a check red under mutations that cannot reach it, while the
#: tree on disk was restored correctly every time.
_NO_BYTECODE = {"PYTHONDONTWRITEBYTECODE": "1"}


def _run_with(script: str, tmp: Path) -> Run:
    r = subprocess.run([sys.executable, "-B", "-c", script], cwd=tmp,
                       capture_output=True, text=True, timeout=900,
                       env=dict(os.environ, **_NO_BYTECODE))
    got = {}
    for marker in ("DECLARED", "NEVERRAN", "GUARDCRASH", "REPORTED",
                   "CRASHED", "FAILED", "WHY"):
        m = re.search(r"::%s::(\[.*\])" % marker, r.stdout)
        if not m:
            return Run([], [], [],
                       note=f"<<no {marker} marker>> "
                            f"{r.stdout[-300:]} {r.stderr[-300:]}")
        got[marker] = eval(m.group(1))
    return Run(got["REPORTED"], got["FAILED"], got["CRASHED"],
               declared=got["DECLARED"], never_ran=got["NEVERRAN"],
               guard_crash=got["GUARDCRASH"], why=got["WHY"])



#: --- pass 4: the store's own residuals ------------------------------------
#: Each of these regresses ONE repair made in this pass back to the behaviour
#: the finding measured, and names the check that has to notice it.
MUTATIONS += [
    ("#5 a split child does not inherit its parent's quarantine",
     "photoloset/cross.py",
     '        if self._is_quarantine(home):\n'
     '            self.quarantine.add(child)\n',
     '',
     ["a proposal stays quarantined"]),

    ("#5 quarantine goes back to a substring of a name the writer controls",
     "photoloset/cross.py",
     '        return isinstance(core, str) and core in self.quarantine',
     '        return isinstance(core, str) and "#proposed" in core',
     ["a proposal stays quarantined"]),

    # The suffix test the LAST pass shipped as "structural". It is not: the
    # store publishes such names itself, so a writer who round-trips the
    # store's own core list writes straight into the test.
    ("#0 quarantine goes back to a suffix of a name the writer controls",
     "photoloset/cross.py",
     '        return isinstance(core, str) and core in self.quarantine',
     '        return (isinstance(core, str)\n'
     '                and core.split("·")[0].endswith(QUARANTINE_SUFFIX))',
     ["a proposal stays quarantined"]),

    ("#0 the store stops recording the quarantine core it minted",
     "photoloset/cross.py",
     '        self.quarantine.add(home)\n        return home',
     '        return home',
     ["a proposal stays quarantined"]),

    ("#0 quarantine does not survive storage", "photoloset/cross.py",
     '                "quarantine": sorted(self.quarantine),\n', '',
     ["a proposal stays quarantined"]),

    ("#6 an armed claim may sit inside a quarantine core",
     "photoloset/cross.py",
     '        elif arm is not None and self._is_quarantine(core):',
     '        elif False:',
     ["a proposal stays quarantined"]),

    ("#6 verify stops naming an armed seat inside quarantine",
     "photoloset/cross.py",
     '                if arm is not None and self._is_quarantine(cname):',
     '                if False:',
     ["a proposal stays quarantined"]),

    ("#5 a split whose nest link was refused reports ANSWER again",
     "photoloset/cross.py",
     '        edge = self.link((chain[-1], ""), (child, ""), "nest")\n'
     '        if edge["verdict"] != "ANSWER":',
     '        edge = self.link((chain[-1], ""), (child, ""), "nest")\n'
     '        if False:',
     ["a proposal stays quarantined"]),

    ("#5 a child whose parent was never created is not called an orphan",
     "photoloset/cross.py",
     '            if parent not in self.cores:\n'
     '                problems.append(\n'
     '                    {"verdict": ORPHANED_CORE, "core": cname,\n'
     '                     "parent": parent,\n'
     '                     "why": "分れた子の親核が店に無い — "\n'
     '                            "この核は誰からも届かない"})\n'
     '            elif cname not in self._closure(parent):',
     '            if False:\n'
     '                problems.append(\n'
     '                    {"verdict": ORPHANED_CORE, "core": cname,\n'
     '                     "parent": parent,\n'
     '                     "why": "分れた子の親核が店に無い — "\n'
     '                            "この核は誰からも届かない"})\n'
     '            elif parent in self.cores '
     'and cname not in self._closure(parent):',
     ["a proposal stays quarantined"]),

    ("#5 the core's own 24 goes back to per-arm budgets only",
     "photoloset/cross.py",
     '        if len(self.cores.get(core, [])) >= CAPACITY_PER_CORE:',
     '        if False:',
     ["the quarantine core obeys the same law"]),

    ("#5 verify stops counting a core's total seats", "photoloset/cross.py",
     '            if len(seats) > CAPACITY_PER_CORE:',
     '            if False:',
     ["the quarantine core obeys the same law"]),

    ("#0 the anonymous source is counted as a source again",
     "photoloset/cross.py",
     '        if kind == "generic" and not _source_key(source):',
     '        if False:',
     ["an anonymous source buys nothing"]),

    ("#8 source normalisation drops NFKC and punctuation",
     "photoloset/cross.py",
     '    folded = unicodedata.normalize("NFKC", source)\n'
     '    out = []\n'
     '    for ch in folded:\n'
     '        cat = unicodedata.category(ch)\n'
     '        out.append(" " if cat[0] in _SEPARATOR_CATEGORIES else ch)\n'
     '    return " ".join("".join(out).split()).casefold()',
     '    return " ".join(source.split()).casefold()',
     ["an anonymous source buys nothing"]),

    ("#0 source independence goes back to raw string identity",
     "photoloset/cross.py",
     '    return " ".join("".join(out).split()).casefold()',
     '    return source',
     ["an anonymous source buys nothing"]),

    ("#0 a blank source pays for a generic claim again",
     "photoloset/cross.py",
     '                weight = max((len(_independent(e["sources"])) for e in gen),\n'
     '                             default=0)',
     '                weight = max((len(e["sources"]) for e in gen), default=0)',
     ["an anonymous source buys nothing"]),

    ("#4 the store accepts values it cannot persist", "photoloset/cross.py",
     '                ("source", source, _persistable(source))):\n'
     '            if why_not:',
     '                ("source", source, _persistable(source))):\n'
     '            if False:',
     ["the store refuses what it cannot persist"]),

    ("#1 only the VALUE is checked, as it was", "photoloset/cross.py",
     '        for field, culprit, why_not in (\n'
     '                ("core", core, _addressable(core)),\n'
     '                ("key", key, _addressable(key)),\n'
     '                ("value", value, _persistable(value)),\n'
     '                ("source", source, _persistable(source))):',
     '        for field, culprit, why_not in (\n'
     '                ("value", value, _persistable(value)),):',
     ["the store refuses what it cannot persist"]),

    ("#7 NaN and Infinity are floats, so they are persistable again",
     "photoloset/cross.py",
     '    if isinstance(v, float):\n'
     '        if not math.isfinite(v):',
     '    if isinstance(v, float):\n'
     '        if False:',
     ["the store refuses what it cannot persist"]),

    ("#29 a value that contains itself raises out of the store again",
     "photoloset/cross.py",
     '    if isinstance(v, (list, tuple, dict)) and id(v) in _path:',
     '    if False:',
     ["the store refuses what it cannot persist"]),

    ("#4 verify stops looking for values the store cannot hold",
     "photoloset/cross.py",
     '                    why_not = _persistable(e.get("value"))\n'
     '                    if why_not:',
     '                    why_not = _persistable(e.get("value"))\n'
     '                    if False:',
     ["the store refuses what it cannot persist"]),

    ("#0 resolve stops pricing a generic claim by its own kind",
     "photoloset/cross.py",
     '            by_kind_w = {k: len(_independent(v)) '
     'for k, v in by_kind.items()}',
     '            by_kind_w = {k: len(_independent(sources)) '
     'for k, v in by_kind.items()}',
     ["a generic claim is priced by its own kind"]),

    # The number the LAST pass left beside the honest one: `weight` summing
    # across kinds, so four kinds with one source each read as 4 while the
    # gate priced the claim at 1.
    ("#3 weight goes back to the union across kinds", "photoloset/cross.py",
     '                    "weight": by_kind_w[priced],',
     '                    "weight": len(_independent(sources)),',
     ["a generic claim is priced by its own kind",
      "a seat carries every kind that reached it"]),

    ("#1 the free-riding arm stops being reported", "photoloset/cross.py",
     '        if arm is None or arm == seat.get("arm"):\n            return None',
     '        if True:\n            return None',
     ["the budget arm is reported, never hidden"]),

    ("#1 the order check stops separating the budget arm",
     "photoloset/cross.py",
     '    budget_only = 0\n    for d in differences:',
     '    budget_only = 0\n    for d in []:',
     ["the budget arm is reported, never hidden"]),

    ("#8/#9 placement() bypasses the store entirely", "photoloset/block.py",
     '    def placement(self) -> Dict[str, Tuple[float, float, float]]:\n'
     '        out: Dict[str, Tuple[float, float, float]] = {}',
     '    def placement(self) -> Dict[str, Tuple[float, float, float]]:\n'
     '        return {n: tuple(sp[0])\n'
     '                for n, sp in COAT_DECLARATION["placement"].items()}\n'
     '        out: Dict[str, Tuple[float, float, float]] = {}',
     ["the whole declaration is served from the cross"]),

    ("#8/#9 label() bypasses the store entirely", "photoloset/block.py",
     '    def label(self) -> str:\n'
     '        return self.store.require(self.root, "label")',
     '    def label(self) -> str:\n'
     '        if self.root == "block:coat":\n'
     '            return COAT_DECLARATION["label"]\n'
     '        return self.store.require(self.root, "label")',
     ["the whole declaration is served from the cross"]),

    ("#8/#9 params() bypasses the store entirely", "photoloset/block.py",
     '        return {f["key"].split(":", 1)[1]: f["value"]["value"]\n'
     '                for f in self._ordered("param:")}',
     '        return {_param_row(r)[0]: _param_row(r)[1]\n'
     '                for r in COAT_DECLARATION["params"]}',
     ["the whole declaration is served from the cross"]),

    ("served() hands every block the coat's own params",
     "photoloset/block.py",
     '            "params": self.params(),',
     '            "params": {k: self.param(k)\n'
     '                       for k, _v, _f, _kd, _s\n'
     '                       in (_param_row(r)\n'
     '                           for r in COAT_DECLARATION["params"])},',
     ["the whole declaration is served from the cross"]),

    ("#17 served() quietly stops carrying the formulas",
     "photoloset/block.py",
     '            "formulas": self.formulas(),\n            "seams": self.seams(),',
     '            "seams": self.seams(),',
     ["round trip moves nothing"]),

    ("Library.families() answers from a list instead of the store",
     "photoloset/parts.py",
     '    def families(self) -> List[str]:\n'
     '        """家族を**宣言順で**。並びは格納場所ではなく seq が決める。"""\n'
     '        out = []',
     '    def families(self) -> List[str]:\n'
     '        """家族を**宣言順で**。並びは格納場所ではなく seq が決める。"""\n'
     '        return list(FAMILIES)\n'
     '        out = []',
     ["a generic claim needs two sources"]),
]


#: --- pass 5: the store's residuals --------------------------------------
MUTATIONS += [
    ("#5 census reads the write-session log instead of the store",
     "photoloset/cross.py",
     '                "uncharged": uncharged,',
     '                "uncharged": [dict(u) for u in self.uncharged],',
     ["the budget arm is reported, never hidden"]),

    ("#26 the seat-creating write stops naming the arm it charged",
     "photoloset/cross.py",
     '                "key": key, "arm": arm, "charged_arm": arm,\n'
     '                "arms": seat_arms(seat), "weight": 1, '
     '"seat_created": True}',
     '                "key": key, "arm": arm,\n'
     '                "weight": 1, "seat_created": True}',
     ["the budget arm is reported, never hidden"]),

    ("#2 the loader stops checking the shape of a seat's seq",
     "photoloset/cross.py",
     '                if isinstance(seq, bool) or not isinstance(seq, int):',
     '                if False:',
     ["the loader never raises"]),

    ("#2 the loader stops checking the shape of a seat's key",
     "photoloset/cross.py",
     '                key = s.get("key")\n'
     '                if _addressable(key):',
     '                key = s.get("key")\n'
     '                if False:',
     ["the loader never raises"]),

    ("#2 the loader takes whatever it is handed for cores",
     "photoloset/cross.py",
     '        if not isinstance(cores, dict):',
     '        if False:',
     ["the loader never raises"]),

    ("#2 resolve raises again on a seat with no claims",
     "photoloset/cross.py",
     '        if not entries:',
     '        if False:',
     ["the loader never raises"]),
]


def run_suite(repo: Path):
    """The whole suite, once, under whatever mutation is in place."""
    return subprocess.run([sys.executable, "-B", "tests/run_checks.py"],
                          cwd=repo, capture_output=True, text=True,
                          timeout=1800, env=dict(os.environ, **_NO_BYTECODE))


#: **Test seams.** ``self_test()`` swaps these so ONE entry raises INSIDE the
#: run — after its file is already mutated, which is the case a missing
#: restore poisons: every later entry would then be scored against a tree
#: that is still carrying somebody else's mutation. Nothing else reads them.
def run(tmp: Path) -> Run:
    """The three cross sections, in process."""
    return _run_with(RUNNER, tmp)


def run_loop(tmp: Path) -> Run:
    """The three look-loop sections, in process. **Seconds, not minutes** —
    the whole suite takes seven, and a mutation the loop's own checks are
    supposed to catch does not need the coat drafted twice to prove it."""
    return _run_with(LOOP_RUNNER, tmp)


_RUN = [run]
_RUN_LOOP = [run_loop]
_RUN_SUITE = [run_suite]



#: --- the look loop ---------------------------------------------------------
#: Every check the loop added, regressed one at a time back to the behaviour
#: it forbids. These are scored against the loop's OWN three sections rather
#: than the whole suite, because the whole suite takes seven minutes and a
#: mutation in `resemble.py` cannot be noticed by the coat.
#:
#: The two that matter most are pinned deliberately: the KEY mutation (the
#: source in the address, which is what makes ranking possible) and the GATE
#: mutations (a shape argument on the search, and the digest comparison
#: deleted). If those three stay green the whole design is decoration.
LOOP_MUTATIONS = [
    # ---- resemble: the refusals ----------------------------------------
    ("retrieval with no backend answers with an empty list",
     "photoloset/resemble.py",
     '    if not _BACKENDS:\n        return _no_backend("per_part")',
     '    if not _BACKENDS:\n        return {"verdict": "ANSWER", "hits": []}',
     ["retrieval without a backend refuses by name"]),

    ("a backend that found nothing is reported as no backend",
     "photoloset/resemble.py",
     '    hits, trouble = _run(per_part_capable, qs)\n'
     '    return {"verdict": "ANSWER", "hits": hits,',
     '    hits, trouble = _run(per_part_capable, qs)\n'
     '    if not hits:\n'
     '        return _no_backend("per_part")\n'
     '    return {"verdict": "ANSWER", "hits": hits,',
     ["an empty result is not a refusal"]),

    ("a whole-image backend is allowed to answer per-part questions",
     "photoloset/resemble.py",
     '    per_part_capable = [b for b in ordered\n'
     '                        if b["modality"] != "image_embedding"]',
     '    per_part_capable = [b for b in ordered\n'
     '                        if True]',
     ["a whole-image backend cannot answer a per-part question"]),

    ("a backend is registered at import", "photoloset/resemble.py",
     'def whole(image_ref: Any, *, queries: Sequence[str] = (),',
     'register("siglip:marqo-fashionSigLIP", "parallel", "image_embedding",\n'
     '         lambda q: {"hits": []})\n\n\n'
     'def whole(image_ref: Any, *, queries: Sequence[str] = (),',
     ["photoloset registers no backend at import"]),

    ("a fixture may be registered under a model's name",
     "photoloset/resemble.py",
     '    named_fixture = model_id.startswith(FIXTURE_PREFIX)\n'
     '    if named_fixture != bool(fixture):',
     '    named_fixture = model_id.startswith(FIXTURE_PREFIX)\n'
     '    if False:',
     ["a fixture cannot pass as a backend"]),

    # ---- resemble: the landing -----------------------------------------
    ("a retrieval hit lands as a claim about this garment",
     "photoloset/resemble.py",
     '        r = store.put(core, key, value, "proposed", source)',
     '        r = store.put(core, key, value, "specific", source)',
     ["a retrieval hit is unreadable at the part address"]),

    # **The most important entry in the sweep.** With the source in the key
    # two backends write two addresses, both resolve ANSWER, and somebody
    # downstream sorts them — which is the ranking the whole design forbids.
    ("the address carries the source, so rivals stop colliding",
     "photoloset/resemble.py",
     '    aspect = str(hit.get("aspect") or "")\n'
     '    return aspect',
     '    aspect = str(hit.get("aspect") or "")\n'
     '    return f\'{aspect}:{hit.get("model_id")}\'',
     ["two sources that disagree become contested, not ranked"]),

    ("one source buys a generic construction claim",
     "photoloset/garment_rights.py",
     'GENERIC_MIN_SOURCES = 2', 'GENERIC_MIN_SOURCES = 1',
     ["one corpus cannot buy a generic construction claim"]),

    ("a search that found nothing is seated as a proposal",
     "photoloset/resemble.py",
     '                          "no_match", _searched_source(searched))',
     '                          "proposed", _searched_source(searched))',
     ["a search that found nothing is not seated"]),

    # ---- compose.graph_from --------------------------------------------
    # Partial construction is the failure that collects approval for a
    # garment that is not the one retrieved, so TWO checks are pinned to it.
    ("the construction skips the parts it cannot draft",
     "photoloset/compose.py",
     '    if unknown or undraftable:\n'
     '        known = sorted(_parts.PART_GEOMETRY)',
     '    records = [r for r in records\n'
     '               if str(r.get("part")) in _parts.PART_GEOMETRY]\n'
     '    if False:\n'
     '        known = sorted(_parts.PART_GEOMETRY)',
     ["a retrieved family with no procedure refuses the whole construction",
      "the constructed graph names every part the retrieval named"]),

    ("instance numbers follow the order the retrieval happened to return",
     "photoloset/compose.py",
     '    ordered = sorted(records, key=lambda r: (_catalog_rank(r.get("part")),\n'
     '                                             _shape_key(r)))',
     '    ordered = list(records)',
     ["instance numbering does not move between rounds"]),

    # ---- confirm: the solid and the sheet ------------------------------
    ("the confirmation solid falls back to a body ratio",
     "photoloset/confirm.py",
     '    return float(edge["length"]) * factor',
     '    from .garment_draw import DEFAULT_RATIO\n'
     '    return 80.0 * DEFAULT_RATIO["chest"] * factor',
     ["the confirmation solid is built from the composed pieces"]),

    ("the sheet keeps only its own disclaimer", "photoloset/confirm.py",
     '    does_not_claim = [\n'
     '        solid.get("not_a_simulation"),\n'
     '        solid.get("surface_carries_no_information"),\n'
     '        draft.get("seam_allowance"),\n'
     '        draft.get("not_a_published_system"),\n'
     '    ]',
     '    does_not_claim = [\n'
     '        solid.get("not_a_simulation"),\n'
     '    ]',
     ["the sheet states what the render does not claim"]),

    ("a rejection may name nothing at all", "photoloset/confirm.py",
     '    if not ids:\n        return {"verdict": UNNAMED_REJECTION,',
     '    if False:\n        return {"verdict": UNNAMED_REJECTION,',
     ["a rejection must name a claim"]),

    ("an open port is filled instead of asked about",
     "photoloset/confirm.py",
     '    for op in (draft.get("open") or []):\n        n += 1',
     '    for op in []:\n        n += 1',
     ["an open port becomes a claim, not a silent default"]),

    # convergence.py had no importer, no check and no falsifier at all: it
    # could have stopped working and nothing in the tree would have said so.
    ("the sheet stops asking whether the loop is ending",
     "photoloset/confirm.py",
     '    ending = _convergence.check(draft, measures=measures, sew=sew,\n'
     '                                rejected=list(rejected or []),\n'
     '                                history=history)',
     '    ending = {"verdict": "CONVERGED", "counters": {}}',
     ["an open port becomes a claim, not a silent default"]),

    # ---- confirm: the gate ---------------------------------------------
    ("an unnamed approval is attributed to the machine",
     "photoloset/confirm.py",
     '    if ledger is None:\n        return {"verdict": NO_LEDGER,',
     '    by = by.strip() or "auto"\n'
     '    if ledger is None:\n        return {"verdict": NO_LEDGER,',
     ["an approval carries the name of the approver"]),

    ("the approval stops naming the claims it accepted",
     "photoloset/confirm.py",
     '        for c in accepted:\n'
     '            value = json.dumps(c.get("value"), ensure_ascii=False,',
     '        for c in []:\n'
     '            value = json.dumps(c.get("value"), ensure_ascii=False,',
     ["an approval names the claims it accepted"]),

    ("the shape digest covers only the label", "photoloset/confirm.py",
     '            "digest": _md5({"structure": structure, "geometry": geometry}),\n'
     '            "structure_digest": _md5(structure),',
     '            "digest": _md5(draft.get("label")),\n'
     '            "structure_digest": _md5(draft.get("label")),',
     ["an approval dies when the shape moves"]),

    ("the approval is written straight into the entry list",
     "photoloset/confirm.py",
     '        ledger.propose(APPROVAL_PART, APPROVAL_ASPECT, shape["digest"],\n'
     '                       source="confirm.approve",\n'
     '                       note=f\'{len(accepted)} claims accepted, \'\n'
     '                            f\'{len(cannot_tell)} not visible\')\n'
     '        entry = ledger.adopt(APPROVAL_PART, APPROVAL_ASPECT, shape["digest"],\n'
     '                             by=by)',
     '        entry = ledger._add(APPROVAL_PART, APPROVAL_ASPECT,\n'
     '                            shape["digest"], "observation",\n'
     '                            "confirm.approve", "")',
     ["approval writes through the same door as an adoption"]),

    # ---- sewing_search: the gate ---------------------------------------
    # The deliverable. If these stay green the approval is decoration.
    ("the search grows a convenience argument for a draft",
     "photoloset/sewing_search.py",
     'def methods_for(approval_id: str, corpus: str = "") -> Dict[str, Any]:',
     'def methods_for(approval_id: str, corpus: str = "",\n'
     '                draft_json: str = "") -> Dict[str, Any]:',
     ["the sewing search has no argument for an unapproved shape"]),

    ("the MCP tool grows a json_text argument and passes it through",
     "photoloset/mcp.py",
     'def sewing_methods(approval_id: str = "", corpus: str = "") -> str:',
     'def sewing_methods(approval_id: str = "", corpus: str = "",\n'
     '                   json_text: str = "") -> str:',
     ["the sewing search has no argument for an unapproved shape"]),

    ("any adopted approval opens the search, whichever shape it named",
     "photoloset/sewing_search.py",
     '    entry = _adopted(ledger, _confirm.APPROVAL_PART, _confirm.APPROVAL_ASPECT,\n'
     '                     key)',
     '    entry = _adopted(ledger, _confirm.APPROVAL_PART,\n'
     '                     _confirm.APPROVAL_ASPECT)',
     ["the sewing search refuses an unknown approval"]),

    ("the digest comparison is deleted, so a stale approval still opens it",
     "photoloset/sewing_search.py",
     '    if now.get("digest") != key:', '    if False:',
     ["a stale approval does not open the search"]),

    ("the refusal stops naming the corpora that would close it",
     "photoloset/sewing_search.py",
     '                f"register one with sewing_search.register_corpus(corpus). "\n'
     '                f"The corpora that would serve: {\', \'.join(WOULD_SERVE)}. "\n',
     '                f"register one with sewing_search.register_corpus(corpus). "\n',
     ["the sewing search names the corpora that would close it"]),

    ("an embedding backend is accepted as a construction corpus",
     "photoloset/sewing_search.py",
     '    if modality == "image_embedding":', '    if False:',
     ["an embedding backend cannot be a construction corpus"]),

    ("two corpora from one generator count as two sources",
     "photoloset/sewing_search.py",
     '            shared = roots[a] & roots[b]\n            if shared:',
     '            shared = roots[a] & roots[b]\n            if False:',
     ["two corpora from one root are not two sources"]),

    # ---- convergence ----------------------------------------------------
    ("the loop is allowed to churn ninety-nine rounds",
     "photoloset/convergence.py",
     'STAGNATION_LIMIT = 3', 'STAGNATION_LIMIT = 99',
     ["a repeated structural rejection escalates to a human"]),

    ("a rejected claim is not counted", "photoloset/convergence.py",
     '    counters["rejected_claims"] = len(rejected_ids)',
     '    counters.pop("rejected_claims", None)',
     ["convergence counts a rejected claim"]),

    ("stagnation stops looking at WHICH claim was rejected",
     "photoloset/convergence.py",
     '            if (prev.get("counters") == counters\n'
     '                    and prev.get("rejected", []) == rejected_ids):',
     '            if prev.get("counters") == counters:',
     ["a repeated structural rejection escalates to a human"]),

    ("the escalation goes back to saying nothing in particular",
     "photoloset/convergence.py",
     '    refusal = details.get("refusal")\n'
     '    if refusal in ("UNKNOWN_NO_SUCH_PART", "UNKNOWN_PART_NOT_DRAFTABLE"):',
     '    refusal = details.get("refusal")\n'
     '    if False:',
     ["a repeated structural rejection escalates to a human"]),
]


#: #6 needs the WHOLE suite, not the three cross functions, because the name
#: pin it exercises spans every check. One extra full run (~30s) rather than
#: 30s x every mutation.
WHOLE_SUITE = [
    # A SILENT retirement removes the @declares entry as well as the body —
    # that is what makes it silent, and it is exactly what happened to
    # "coat fills its root node exactly". Leaving the declaration behind is
    # caught by ``section`` reporting NEVER RAN, which is a different and
    # much louder failure. So this entry carries two edits.
    ("#6 a check is retired without saying so, and the total keeps rising",
     "tests/run_checks.py",
     [("          'support- is never written, only emerges',\n", ""),
      ('        check("support- is never written, only emerges",',
       '        _retired_silently = (')],
     ["no check went missing"]),

    # The FIFTH check this project shipped that could not fail, found by
    # hunting the shape of #8/#9 across the whole suite rather than fixing
    # only the two that were reported: "every tool returns an object" was
    # `check(name, True, ...)`. A literal True is the same defect as
    # comparing a value against itself. One tool returning a bare list used
    # to leave it GREEN (the loop printed a FAIL under a DYNAMIC name that
    # no pinned set could see); it now has to go red.
    ("the fifth tautology: one MCP tool stops returning an object",
     "photoloset/mcp.py",
     [('    return {"content": [{"type": "text", "text": text}]}',
       '    if name == "design_sheet":\n'
       '        text = "[]"\n'
       '    return {"content": [{"type": "text", "text": text}]}')],
     ["every tool returns an object"]),

    ("the fifth tautology: one MCP tool crashes", "photoloset/mcp.py",
     [('    try:\n        text = fn(**(args or {}))',
       '    try:\n'
       '        if name == "design_sheet":\n'
       '            raise RuntimeError("regressed")\n'
       '        text = fn(**(args or {}))')],
     ["every tool returns an object"]),

    # A SIXTH, and the line directly above the fifth. "every tool has a
    # schema" was `all(... for t in tools)` over a list that arrives over the
    # wire — vacuously True when the list is empty. Measured on head before
    # the repair: `tools/list` mutated to answer `[]` left this line GREEN
    # while its own sibling went red. The empty case is the falsifier the
    # count clause exists for; the bad-schema case is the property it is
    # named for. Both have to go red.
    ("the sixth tautology: the tool list comes back empty",
     "photoloset/mcp.py",
     [('def _list() -> Dict[str, Any]:\n    out = []',
       'def _list() -> Dict[str, Any]:\n    return {"tools": []}\n    out = []')],
     ["every tool has a schema"]),

    ("the sixth tautology: one tool's schema is not an object",
     "photoloset/mcp.py",
     [('        out.append({"name": name, "description": doc,\n'
       '                    "inputSchema": _schema(fn)})',
       '        _sch = _schema(fn)\n'
       '        if name == "design_sheet":\n'
       '            _sch = {"type": "string"}\n'
       '        out.append({"name": name, "description": doc,\n'
       '                    "inputSchema": _sch})')],
     ["every tool has a schema"]),
]



#: --- pass 5: the detectors themselves -------------------------------------
#: The pass that repaired the scanner added three checks with no falsifier —
#: the T7 gate, the scanner's self-test, and the readers that now have to
#: track their stores. A check nobody can turn red is the defect this whole
#: file exists for, so each is regressed here.
WHOLE_SUITE += [
    # T7 by mutation, done BY the harness this time: freeze a reader to the
    # literal it returns today. Before this pass that left the suite green —
    # it satisfied every comparison against that literal. Two lines have to
    # notice now: the one that reads the reader from a SECOND store, and the
    # ledger gate, whose record is keyed by a digest of this very body.
    ("#9 a reader is frozen to the literal it returns today",
     "photoloset/block.py",
     [("    def sleeve_required(self) -> Tuple[str, ...]:\n"
       "        return tuple(k for k in self.measures()\n"
       "                     if k not in self.required())",
       "    def sleeve_required(self) -> Tuple[str, ...]:\n"
       "        return (\"sleeve_length\",)")],
     ["reads follow a second declaration",
      "every served reader reads its store"]),

    # The ledger is a RECORD. If it can be edited into a clean bill of health
    # the gate is decoration, so the gate reads what the record SAYS.
    ("#9 the T7 ledger claims a reader can be bypassed",
     "tests/t7_readers.json",
     [('  "BlockView.arm_census": {\n   "bypassable": false,',
       '  "BlockView.arm_census": {\n   "bypassable": true,')],
     ["every served reader reads its store"]),

    # B3: chained comparisons were invisible to T1, T4 and T5 at once. The
    # self-test plants one of each; blinding _comparisons again has to turn
    # the self-test red rather than quietly reporting a smaller number.
    ("#B3 the scanner goes blind to chained comparisons again",
     "tests/unfalsifiable.py",
     [("        left = n.left\n"
       "        for op, right in zip(n.ops, n.comparators):",
       "        continue\n"
       "        left = n.left\n"
       "        for op, right in zip(n.ops, n.comparators):")],
     ["the scanner finds every planted shape"]),

    # B8a: a tautology one call away from the check. Stop following helpers
    # and the planted `_same_thing(v)` goes unreported.
    ("#B8a the scanner stops following helpers in the checks file",
     "tests/unfalsifiable.py",
     [("                helper = src.helpers.get(n.func.id)",
       "                helper = None")],
     ["the scanner finds every planted shape"]),
]


#: --- pass 4: the checks that could not fail, each regressed ---------------
#: These need the WHOLE suite because the repaired lines live outside the
#: three cross functions. Every one of them was measured LEAVING THE SUITE
#: GREEN before this pass; each has to turn its own line red now.
#: --- pass 5: what only the WHOLE suite can see ---------------------------
WHOLE_SUITE += [
    # **THE COAT MUST NOT MOVE, as a number rather than a sentence.** The
    # gravity constant moves the drape by ~0.02 cm — not enough to change
    # `closed` or the count over tolerance, which is all the suite used to
    # assert, and enough to change every coordinate in the mesh. Three lines
    # have to notice: the two drape figures and the digest over the whole
    # geometry.
    ("#11 gravity moves, and the coat moves with it",
     "photoloset/garment_drape.py",
     [("GRAVITY = -980.0", "GRAVITY = -1000.0")],
     ["default stitch_k leaves it open", "64x closes it",
      "the coat has not moved"]),

    # The other half of #9: arm_census was pinned only as the literal dict
    # the coat returns, so a frozen dict passed every check.
    ("#9 arm_census answers from a frozen dict", "photoloset/block.py",
     [("    def arm_census(self) -> Dict[str, int]:\n"
       "        return self.store.arm_census(self.root)",
       "    def arm_census(self) -> Dict[str, int]:\n"
       "        return {'support+': 0, 'support-': 0, 'cause+': 10,\n"
       "                'cause-': 0, 'kind+': 0, 'kind-': 17}")],
     ["the arm census counts the store it is given"]),

    ("#22 the pinned coat digest is not the one it recomputes",
     "tests/coat_digest.py",
     [('GEOMETRY_DIGEST = "bbc1d025184d1cff58977def178faf49"',
       'GEOMETRY_DIGEST = "0" * 32')],
     ["the coat has not moved"]),

    # **The schema says what the signature says.** Under
    # `from __future__ import annotations` the annotation is a STRING, so
    # dropping the resolution puts every numeric parameter back to
    # {"type": "string"} — which is what shipped, unnoticed, because the
    # check only asked whether a schema was an object.
    # **#10: a zone number has to keep naming the same knob.** Both of
    # these leave the count, the id range and the two-calls-agree clause
    # exactly as they were — which is all the check used to assert.
    ("#10 the zone sort order is reversed", "photoloset/zones.py",
     [('    for inst in sorted(graph.get("parts") or [],\n'
       '                       key=lambda i: i.get("instance", "")):',
       '    for inst in sorted(graph.get("parts") or [],\n'
       '                       key=lambda i: i.get("instance", ""),\n'
       '                       reverse=True):')],
     ["zones are numbered deterministically",
      "applying a delta records what changed"]),

    ("#10 a part's zone catalogue is reordered", "photoloset/zones.py",
     [('    "bodice": [\n'
       '        {"param": "chest_ease", "label": "胸のゆとり"},\n'
       '        {"param": "waist_ease", "label": "ウエストの楽"},\n'
       '        {"param": "armhole_depth_add", "label": "袖ぐり深さの追加"},\n'
       '    ],',
       '    "bodice": [\n'
       '        {"param": "armhole_depth_add", "label": "袖ぐり深さの追加"},\n'
       '        {"param": "waist_ease", "label": "ウエストの楽"},\n'
       '        {"param": "chest_ease", "label": "胸のゆとり"},\n'
       '    ],')],
     ["zones are numbered deterministically",
      "applying a delta records what changed"]),

    # **Where the sweep's writes land.** The mutation points the server at
    # a fixed directory instead of the HOME it is given, so the temporary
    # HOME comes back empty. It writes into the system temp, never into the
    # operator's ledger — which is also why the check is stated positively:
    # the before/after form could only be falsified by writing there.
    ("#23 the server ignores the HOME it is given", "photoloset/mcp.py",
     [('HOME = Path.home() / ".photoloset"',
       'HOME = Path("/tmp/photoloset-falsifier-not-your-ledger")')],
     ["the sweep writes into a HOME of its own"]),

    ("#25 the MCP schema stops resolving its own annotations",
     "photoloset/mcp.py",
     [("        hints = typing.get_type_hints(fn)", "        hints = {}")],
     ["every tool has a schema"]),

    ("#25 a stdlib message poses as a verdict again", "photoloset/mcp.py",
     [('    if not (code.startswith("UNKNOWN_") '
       'or code.startswith("CONTESTED_")):', "    if False:")],
     ["a refusal is typed, and the reply is JSON"]),

    ("#24 a measurement may be NaN again",
     "photoloset/garment_measure.py",
     [("    if not math.isfinite(v):", "    if False:")],
     ["a refusal is typed, and the reply is JSON"]),

    # The wide sweep is only worth its classification: a string that is
    # neither an address, a document nor prompt-bank text is prose an
    # English caller was meant to read.
    ("#27 a seat's reason goes back to Japanese only", "photoloset/i18n.py",
     [('    "袖は横": "the sleeve is off to the side",\n', "")],
     ["the untranslated residue is measured"]),
]


WHOLE_SUITE += [
    ("the example runs but prints nothing", "examples/black_coat.py",
     [("import sys\nfrom pathlib import Path",
       "import builtins\nimport sys\nfrom pathlib import Path\n"
       "builtins.print = lambda *a, **k: None")],
     ["example runs"]),

    ("the drafter answers ANSWER with nothing measured",
     "photoloset/garment_pattern.py",
     [('            "verdict": "UNKNOWN_MISSING_MEASUREMENTS",',
       '            "verdict": "ANSWER",')],
     ["draft answers"]),

    ("the coat loses two of its three seam checks",
     "photoloset/garment_pattern.py",
     [("    checks = _seam_checks(pieces)", "    checks = _seam_checks(pieces)[:1]")],
     ["seam checks self-report"]),

    ("i18n.svg() becomes the identity", "photoloset/i18n.py",
     [('    if lang == "ja":\n        return document\n\n    items = '
       'list(_SVG_TEXT.finditer(document))',
       '    if True:\n        return document\n\n    items = '
       'list(_SVG_TEXT.finditer(document))')],
     ["SVG geometry untouched"]),

    ("the third-party scan covers no files at all",
     "tests/run_checks.py",
     [('scanned = sorted((ROOT / "photoloset").glob("*.py"))',
       'scanned = sorted((ROOT / "photoloset").glob("*.pyx"))')],
     ["no third-party imports"]),

    ("the DEFAULT prompt loses its discipline", "photoloset/prompts.py",
     [('_DEFAULT = {\n    "role": "center",\n    "version": "v2026-08-24.1",\n'
       '    "text": _decomposition_prompt(),\n}',
       '_DEFAULT = {\n    "role": "center",\n    "version": "v2026-08-24.1",\n'
       '    "text": "Describe the garment as JSON.",\n}')],
     ["discipline is inside every prompt"]),

    ("marks stop computing seam allowances", "photoloset/garment_marks.py",
     [("        allowances[name] = off", "        pass")],
     ["skirt marks pair and face outward",
      "allowances face outward on every part"]),

    ("zones leak into the coat's ANSWER draft",
     "photoloset/garment_pattern.py",
     [('        "verdict": "ANSWER",\n        "pieces": pieces,\n'
       '        "seam_checks": checks,',
       '        "verdict": "ANSWER",\n        "zones": [{"id": 1}],\n'
       '        "pieces": pieces,\n        "seam_checks": checks,')],
     ["the coat has no zones (untouched path)"]),

    ("one output path drops out of the i18n sweep", "tests/run_checks.py",
     [('    outs["parts.unbought_generics"] = _parts.Library().unbought_generics()',
       '    pass')],
     ["0 untranslated"]),

    ("compose() emits no seam checks at all", "photoloset/compose.py",
     [('        "seam_checks": checks,', '        "seam_checks": [],')],
     ["cape dress composes from parts"]),

    ("a check goes back to being a literal", "tests/run_checks.py",
     [('    check("unknown zone refused",\n'
       '          e["verdict"] == "UNKNOWN_NO_SUCH_ZONE" and e.get("valid"),',
       '    check("unknown zone refused",\n          True,')],
     ["no check that cannot fail"]),

    ("the falsifier harness loses its per-entry guard",
     "tests/falsifiers.py",
     [("        except BaseException as exc:                    # noqa: BLE001\n"
       "            # A raise HERE is this entry failing, not the sweep "
       "ending.",
       "        except KeyboardInterrupt as exc:\n"
       "            # A raise HERE is this entry failing, not the sweep "
       "ending.")],
     ["the falsifier harness reports every mutation"]),

    # **The anchor carries the comment on purpose.** `whole_suite` and
    # `_sweep` now end with a byte-identical `finally` block, so the bare
    # `if orig is not None:` matched the FIRST of the two — `whole_suite`'s —
    # and the self-test, which runs with `whole=[]`, never touched it. This
    # entry went MISS on the sweep that found it: a falsifier pointed at the
    # wrong line is a falsifier for nothing, and it looked exactly like a
    # passing one.
    ("the falsifier harness stops restoring the file it mutated",
     "tests/falsifiers.py",
     [("            # SOURCE and the bytecode both, see _clear_pycache.\n"
       "            if orig is not None:\n"
       "                p.write_text(orig, encoding=\"utf-8\")\n"
       "                _clear_pycache(repo)",
       "            # SOURCE and the bytecode both, see _clear_pycache.\n"
       "            if False:\n"
       "                p.write_text(orig, encoding=\"utf-8\")\n"
       "                _clear_pycache(repo)")],
     ["the falsifier harness reports every mutation"]),
]


def whole_suite(repo: Path, entries: Optional[Sequence[Any]] = None,
                touched: Optional[set] = None) -> Tuple[int, int]:
    """Run ``run_checks.py`` end to end under a mutation and read its exit.

    This is the falsifier for the pinned NAME SET: the failure it exists for
    is a check DISAPPEARING, which by construction cannot be observed by
    running only the functions that still declare it.

    Same crash-proofing as ``main``: one entry that raises is that entry
    going MISS, not the sweep ending. Returns ``(bad, ran)`` so a short run
    cannot be reported as a complete one.
    """
    entries = WHOLE_SUITE if entries is None else list(entries)
    bad = 0
    ran = 0
    for name, rel, edits, expect in entries:
        p = repo / rel
        orig = None
        ran += 1
        try:
            orig = p.read_text(encoding="utf-8")
            if touched is not None:
                touched.add(rel)
            body = orig
            missing = [f for f, _r in edits if f not in body]
            if missing:
                print(f"  SKIP  {name}: anchor not found in {rel}")
                bad += 1
                continue
            for find, repl in edits:
                body = body.replace(find, repl, 1)
            p.write_text(body, encoding="utf-8")
            _clear_pycache(repo)
            r = _RUN_SUITE[0](repo)
            # Fixed column, not a whitespace split: the name is padded into
            # a 34-char field, so anything longer runs into its own detail
            # text and a naive split silently merges the two. That is
            # exactly how a deleted check hid inside a rising total once.
            failed = [m.group(1).rstrip() for m in
                      re.finditer(r"^  FAIL  (.{1,34})", r.stdout, re.M)]
            hit = [e for e in expect
                   if any(f == e or e.startswith(f) for f in failed)]
            ok = len(hit) == len(expect) and r.returncode != 0
            bad += 0 if ok else 1
            print(f"  {'RED ' if ok else 'MISS'}  {name}")
            print(f"        expected red: {expect}")
            print(f"        actually red: {failed}  (exit {r.returncode})")
        except BaseException as exc:                        # noqa: BLE001
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            bad += 1
            print(f"  MISS  {name}: HARNESS RAISED "
                  f"{type(exc).__name__}: {exc}")
        finally:
            if orig is not None:
                p.write_text(orig, encoding="utf-8")
                _clear_pycache(repo)
    _clear_pycache(repo)
    return bad, ran


def _clear_pycache(repo: Path) -> int:
    """Delete every cached bytecode file in the copy — **listing them BEFORE
    deleting any of them.**

    ``for c in repo.rglob("__pycache__"): rmtree(c)`` mutates the tree the
    generator is walking, so a cache directory it has not reached yet can be
    skipped. That used to look harmless. It is not:

    A mutation whose replacement is the SAME LENGTH as what it replaces
    (``"no_match"`` -> ``"proposed"``) leaves the source file's size
    unchanged, and CPython's cache header records the source's mtime in
    WHOLE SECONDS. So a mutate-run-restore that completes inside one second
    produces a restored source the stale bytecode still claims to describe,
    and if its ``__pycache__`` survived the sweep, the NEXT entry runs
    against the PREVIOUS entry's regression.

    Measured on this harness before the repair: the look sweep's
    ``no_match -> proposed`` entry leaked into the following entries in
    roughly one run in three, turning "a search that found nothing is not
    seated" red under mutations of ``compose.py`` and ``confirm.py``, which
    cannot reach it. The tree was restored correctly every time — the file
    on disk was right and the bytecode was wrong — which is why it read as
    flakiness rather than as a leak.
    """
    caches = list(repo.rglob("__pycache__")) + list(repo.rglob("*.pyc"))
    for c in caches:
        if c.is_dir():
            shutil.rmtree(c, ignore_errors=True)
        elif c.exists():
            c.unlink()
    return len(caches)


def _baseline(repo: Path, runner, label: str):
    """A clean run, and the set of names the FUNCTIONS declare.

    Pinning the observed output instead would let a mutation that suppresses
    a check agree with a baseline that also suppressed it.
    """
    clean = runner(repo)
    print(f"unmutated: {len(clean.reported)} {label} checks reported, "
          f"{len(clean.failed)} failing, {len(clean.crashed)} crashed "
          f"-> {clean.failed or clean.note or 'clean'}")
    if clean.crashed:
        print(f"  BASELINE CRASHED: {clean.crashed}")
    baseline = list(clean.declared)
    drift = ([n for n in baseline if n not in clean.reported]
             + [n for n in clean.reported if n not in baseline])
    print(f"pinned name set: {len(baseline)} declared names"
          + (f" — DECLARATION DRIFT: {drift}" if drift else "") + "\n")
    if drift or clean.failed or clean.crashed or clean.never_ran:
        return baseline, 1
    return baseline, 0


def _sweep(repo: Path, entries, runner, baseline, touched: set, label: str):
    """Run every entry, report every entry, restore the tree.

    **The harness had the defect it exists to find, one level up.** Until
    this was written the loop below carried no guard: one raise — a missing
    file, the ``subprocess.TimeoutExpired`` from ``run``'s own timeout, an
    ``eval`` of a marker that did not arrive — ended the sweep at mutation N.
    The entries after it neither ran nor were named, none of the summary
    lines printed, and because the restoring ``write_text`` sat AFTER ``run``
    rather than in a ``finally``, the working copy was left MUTATED, so any
    entry that did continue would have been scored against somebody else's
    regression. Measured on head before this repair: one poisoned entry at
    index 35 of 38 printed 35 verdicts, a bare traceback and rc=1, and 7 of
    43 entries vanished without a word.

    So: every entry is wrapped, a raise is that ENTRY going MISS, the file is
    restored in ``finally``, and the run reports **how many entries it got
    through** so a short run cannot look like a complete one.
    """
    bad = 0
    ran = 0
    for name, rel, find, repl, expect in entries:
        p = repo / rel
        orig = None
        ran += 1
        try:
            orig = p.read_text(encoding="utf-8")
            touched.add(rel)
            if find not in orig:
                print(f"  SKIP  {name}: anchor not found in {rel}")
                bad += 1
                continue
            p.write_text(orig.replace(find, repl, 1), encoding="utf-8")
            _clear_pycache(repo)
            got = runner(repo)
            # A hit is the NAMED check going red HAVING RUN. Three things
            # that look like evidence and are not:
            #   - a bare function crash, which used to be scraped into the
            #     failed list and stand in for the check it aborted;
            #   - a NEVER RAN line, which is red because nothing was
            #     measured;
            #   - a line that vanished from the output entirely.
            # All three are misses. Only a check that reached its own
            # assertion and rejected the store proves the property is
            # pinned.
            hit = [e for e in expect
                   if e in got.failed and e not in got.never_ran]
            missing = [n for n in baseline if n not in got.reported]
            ok = (len(hit) == len(expect) and not got.crashed
                  and not missing and not got.never_ran and not got.note)
            if not ok:
                bad += 1
            print(f"  {'RED ' if ok else 'MISS'}  {name}")
            print(f"        expected red: {expect}")
            print(f"        actually red: "
                  f"{[f for f in got.failed if f not in got.never_ran]}")
            surprise = [w for w in got.why
                        if not any(w.startswith(e) for e in expect)]
            for w in surprise:
                print(f"        AND WHY: {w}")
            if got.guard_crash:
                print(f"        red by raising in its own setup: "
                      f"{got.guard_crash}")
            if got.crashed:
                print(f"        CRASHED OUT OF section() — the harness "
                      f"itself is unreliable here: {got.crashed}")
            if got.never_ran:
                print(f"        NEVER RAN, so measured nothing (a miss, "
                      f"not a hit) ({len(got.never_ran)}): "
                      f"{got.never_ran}")
            if missing:
                print(f"        NEVER REPORTED ({len(missing)}): {missing}")
            if got.note:
                print(f"        harness note: {got.note}")
        except BaseException as exc:                    # noqa: BLE001
            # A raise HERE is this entry failing, not the sweep ending.
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            bad += 1
            print(f"  MISS  {name}: HARNESS RAISED "
                  f"{type(exc).__name__}: {exc}")
        finally:
            # Restore whatever happened, so the NEXT entry is scored
            # against a clean tree rather than this one's leftovers — the
            # SOURCE and the bytecode both, see _clear_pycache.
            if orig is not None:
                p.write_text(orig, encoding="utf-8")
                _clear_pycache(repo)
    _clear_pycache(repo)
    print(f"\nran {ran} of {len(entries)} {label} entries")
    print(f"{len(entries) - bad}/{len(entries)} {label} mutations "
          f"produced the expected failures with no check going unreported")
    return bad, ran


def main(mutations: Optional[Sequence[Any]] = None,
         whole: Optional[Sequence[Any]] = None,
         loop: Optional[Sequence[Any]] = None) -> int:
    """Three sweeps over one copy of the tree, and the copy checked afterwards.

    - CROSS: the store's own sections, in process, seconds per entry.
    - LOOP: the look loop's three sections, likewise. It is separate because
      the whole suite takes seven minutes and a mutation in ``resemble.py``
      cannot be noticed by the coat; scoring it against 120 unrelated checks
      would buy nothing and cost hours.
    - WHOLE SUITE: the entries whose failure is a check DISAPPEARING, which
      by construction cannot be seen by running only the functions that still
      declare it.

    The per-entry discipline lives in :func:`_sweep`, which every phase
    shares — one guard, one restore, one place a defect in the harness can
    hide. See its docstring for what that guard is for, and
    :func:`_clear_pycache` for the stale-bytecode leak that made one entry's
    regression score the NEXT entry's run.

    At the end every file any phase touched is compared against the pristine
    source, because a ``finally`` that restores is a claim and this is the
    measurement of it.
    """
    mutations = list(MUTATIONS if mutations is None else mutations)
    loop = list(LOOP_MUTATIONS if loop is None else loop)
    whole = list(WHOLE_SUITE if whole is None else whole)
    base = Path(tempfile.mkdtemp(prefix="mutate_"))
    try:
        shutil.copytree(SRC, base / "repo",
                        ignore=shutil.ignore_patterns(".git", "__pycache__"))
        repo = base / "repo"
        touched: set = set()
        baseline, code = _baseline(repo, _RUN[0], "cross")
        if code:
            return code
        bad, ran = _sweep(repo, mutations, _RUN[0], baseline, touched, "cross")
        if loop:
            print("\nand the look loop, scored against its own sections:")
            loop_base, code = _baseline(repo, _RUN_LOOP[0], "loop")
            if code:
                return code
            lbad, lran = _sweep(repo, loop, _RUN_LOOP[0], loop_base, touched,
                                "loop")
        else:
            lbad, lran = 0, 0
        print("\nand the ones that need the whole suite:")
        wbad, wran = whole_suite(repo, whole, touched)
        print(f"\nran {wran} of {len(whole)} whole-suite entries")
        print(f"{len(whole) - wbad} of {len(whole)} whole-suite "
              f"mutations produced the expected failures")
        # **Was the tree left as it was found?** The restore used to sit
        # after ``run``, so a raise inside ``run`` left the copy mutated and
        # every later entry was scored against it. This measures it rather
        # than trusting the ``finally``.
        still = sorted(rel for rel in touched
                       if (repo / rel).read_text(encoding="utf-8")
                       != (SRC / rel).read_text(encoding="utf-8"))
        print(f"tree restored: {len(touched)} files mutated, {len(still)} "
              f"still differ from the source"
              + (f" — STILL MUTATED: {still}" if still else ""))
        total = len(mutations) + len(loop) + len(whole)
        print(f"{total - bad - lbad - wbad}/{total} mutations red overall")
        short = (ran != len(mutations) or lran != len(loop)
                 or wran != len(whole))
        if short:
            print("THE SWEEP DID NOT REACH EVERY ENTRY — the numbers above "
                  "describe a prefix, not the list")
        return 1 if (bad or lbad or wbad or still or short) else 0
    finally:
        shutil.rmtree(base, ignore_errors=True)


def self_test() -> int:
    """**Does THIS harness stop early?** The defect one level up, measured.

        python3 tests/falsifiers.py --self-test

    Runs ``main`` over three entries — a real one, a POISONED one that
    raises, a real one — twice: once where the poison raises before its file
    is read (a path that does not exist) and once where it raises INSIDE the
    run, after the file is already mutated, which is the case that used to
    leave the working copy poisoned for everybody after it.

    It passes only if, in both runs: the entries AFTER the poison still ran
    and still went RED, the poison was named rather than swallowed, all
    three summary lines printed, the tree was restored, and the exit code
    said the sweep was not clean.
    """
    import contextlib
    import io

    first, last = MUTATIONS[0], MUTATIONS[-1]
    ghost = ("(self-test) an entry whose file does not exist",
             "photoloset/no_such_module.py", "x", "y", ["nothing"])
    inside = ("(self-test) an entry that raises INSIDE the run",
              first[1], first[2], first[3], first[4])

    def score(label, out, code, poison_name):
        lines = out.splitlines()
        named = [l for l in lines if l.startswith(("  RED ", "  MISS", "  SKIP"))]
        after = [l for l in named if last[0] in l]
        red_after = [l for l in after if l.startswith("  RED ")]
        poisoned = [l for l in named
                    if poison_name in l and "HARNESS RAISED" in l]
        ran_line = [l for l in lines if l.startswith("ran 3 of 3 cross")]
        restored = [l for l in lines if l.startswith("tree restored:")
                    and "0 still differ" in l]
        overall = [l for l in lines if l.endswith("mutations red overall")]
        ok = (len(named) == 3 and red_after and poisoned and ran_line
              and restored and overall and code == 1)
        print(f"  {'RED ' if ok else 'MISS'}  {label}")
        print(f"        entries named: {len(named)} of 3; the one after the "
              f"poison went red: {bool(red_after)}; poison named: "
              f"{bool(poisoned)}; 'ran 3 of 3': {bool(ran_line)}; "
              f"tree restored: {bool(restored)}; summary printed: "
              f"{bool(overall)}; exit {code}")
        return 0 if ok else 1

    bad = 0
    for label, poison in (("a raise BEFORE the file is read", ghost),
                          ("a raise INSIDE the run, file already mutated",
                           inside)):
        buf = io.StringIO()
        calls = [0]

        def boom(repo, _real=_RUN[0]):
            calls[0] += 1
            if poison is inside and calls[0] == 3:   # baseline, first, poison
                raise RuntimeError("the run itself blew up")
            return _real(repo)

        _RUN[0] = boom
        try:
            with contextlib.redirect_stdout(buf):
                code = main([first, poison, last], [], [])
        finally:
            _RUN[0] = run
        bad += score(label, buf.getvalue(), code, poison[0])
    print(f"\n{2 - bad}/2 harness self-tests behaved as they must")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        raise SystemExit(self_test())
    raise SystemExit(main())
