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
import concurrent.futures
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SRC = Path(__file__).resolve().parent.parent

#: What a mutation sweep must NOT copy. Measured on this tree: the whole
#: repository is 1.3 GB, of which ``app/build`` alone is 1.2 GB of Xcode
#: module caches and DerivedData — untracked, gitignored, and referenced by
#: exactly zero lines of ``run_checks.py`` or this file (grep: 0 hits for
#: ``app/``). Copying it once per sweep was invisible; copying it once per
#: PARALLEL WORKER filled a 460 GB disk and killed the run with ENOSPC.
#: The engine, its tests, docs and examples together are 6.4 MB.
_COPY_IGNORE = shutil.ignore_patterns(
    ".git", "__pycache__", "build", ".build", "DerivedData",
    "*.xcworkspace", "*.xcuserdatad", "ModuleCache.noindex",
)



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

#: **Solver memoization, ON only for the WHOLE_SUITE subprocess.** Profiled:
#: ``sew_and_drape``+``solve`` are 55.5% of one ``run_checks.py`` process's
#: wall time (118.28s of 213.28s instrumented), and ``run_suite`` below is
#: the ONLY caller that re-runs the entire 129-check suite from scratch —
#: 32 times, one per ``WHOLE_SUITE`` entry, almost always over the SAME
#: handful of fixtures (the reference coat, the composed cape-dress, the
#: skirt) since 31 of the 32 entries never touch ``garment_sew.py`` or
#: ``garment_drape.py``. ``photoloset/_solve_cache.py`` folds the full
#: source bytes of both solver files into its cache key, so the one entry
#: that DOES mutate ``garment_drape.py`` ("gravity moves, and the coat
#: moves with it") still recomputes for real rather than serving a
#: pre-mutation answer — see that module's docstring for the argument.
#: Left OFF for ``_run_with`` below (the fast cross/loop path): the
#: profile only measured solver dominance inside the full suite that
#: ``run_suite`` runs, and this project's rule is "no number, no change".
_SOLVER_MEMO = {"PHOTOLOSET_SOLVER_MEMO": "1"}


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
                          timeout=1800,
                          env=dict(os.environ, **_NO_BYTECODE, **_SOLVER_MEMO))


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
      "the coat has not moved",
      # 2026-08-27: measured directly (not assumed) that this same
      # mutation also reddens four of the pass's new checks. The
      # preconditioned number ITSELF does not move (24.2118 both before
      # and after — at only 400 iterations that figure is set by the
      # initial snap, not by gravity's settling) but its check also
      # asserts `coarse_curve[0] == 0.0243` from the unpreconditioned
      # baseline above, and THAT moves (to 0.0244), which is enough to
      # redden the line — a check inheriting a neighbour's number is
      # exactly what a falsifier is supposed to notice, not paper over.
      "64x closes it is a snapshot, not the equilibrium",
      "the worst seam gap is non-increasing as iterations grow",
      "precondition=True changes the answer and stays finite",
      "bending is not wired in unless it changes the drape"]),

    # **The 2026-08-27 pass, regressed one fix at a time.**
    ("#29 the per-vertex step stops being used",
     "photoloset/garment_sew.py",
     [("            s = step_vec[i] if step_vec is not None else step",
       "            s = step")],
     ["precondition=True changes the answer and stays finite"]),

    ("#29 bending stops changing the drape",
     "photoloset/garment_sew.py",
     [('                if bend_k is not None and kind == "bias":\n'
       '                    cb = bend_k * (length - rest[e]) / length\n'
       '                    for t in range(3):\n'
       '                        g[t] += cb * d[t]',
       '                if False and kind == "bias":\n'
       '                    cb = bend_k * (length - rest[e]) / length\n'
       '                    for t in range(3):\n'
       '                        g[t] += cb * d[t]')],
     ["bending is not wired in unless it changes the drape"]),

    ("#29 a fabric missing only bending is not refused",
     "photoloset/garment_drape.py",
     [("    if bend is None:\n        missing.append(\"bending\")",
       "    if False:\n        missing.append(\"bending\")")],
     ["a fabric without bending is refused, the way weight and "
      "thickness already are"]),

    # **The early-stop fix, regressed.** Puts the pre-fix behaviour back —
    # `precondition=True` trusts the same 50-iteration worst-gap window a
    # non-preconditioned solve does, so it can (and, on this coat's coarse
    # mesh at 6400 iterations, does) declare "settled" before the full
    # budget runs.
    ("#29 precondition=True trusts the worst-gap window again",
     "photoloset/garment_sew.py",
     [("            if (not precondition and worst_now <= gap_tol\n"
       "                    and abs(worst_now - prev_worst) < 1e-4):",
       "            if (worst_now <= gap_tol\n"
       "                    and abs(worst_now - prev_worst) < 1e-4):")],
     ["precondition=True never declares settled early"]),

    # **The mcp.py bending-scope fix, regressed.** `drape_validate` goes
    # back to requiring `bending` even though its own call chain never
    # reads it.
    ("#29 drape_validate requires bending again",
     "photoloset/mcp.py",
     [("    mat = _fabric(fabric, require_bending=False)",
       "    mat = _fabric(fabric)")],
     ["mcp.py's fabric reader requires bending only where it is read"]),

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

    # The same defect, one door over: the SECOND garment's own digest
    # generator, checked the same way #22 checks the coat's.
    ("the pinned dress digest is not the one it recomputes",
     "tests/dress_digest.py",
     [('GEOMETRY_DIGEST = "4c1dabf60bfafa549f9084d9828b2871"',
       'GEOMETRY_DIGEST = "0" * 32')],
     ["the dress has not moved"]),

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
      "allowances face outward on every part",
      "the dress has no notches yet, and marks says so honestly"]),

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

    # Measured, not guessed: at the shipped default (1.2cm) the collar's
    # outer edge and the cape's own (independently measured) neckline are
    # 1.57cm apart, inside the 2.0cm tolerance. Raising the default to what
    # this file's own COLLAR_HEIGHT constant used to read before it was
    # tuned down (6.0cm) reopens that gap to 7.9cm, and the "collar joins…"
    # check's `not bad` catches it directly rather than the drape merely
    # sitting less flat — a collar tall enough is a collar the cape cannot
    # be sewn onto with this construction.
    ("the collar grows past what the cape can be sewn onto",
     "photoloset/garment_parts.py",
     [("COLLAR_HEIGHT = 1.2", "COLLAR_HEIGHT = 6.0")],
     ["the collar joins the bodice to the cape and the dress still sews "
      "shut"]),

    # 衿の初期位置をテーブルから消すと数値上は同じ (0.0,0.0,0.0) の無言
    # 既定に落ちる(drape は同じ結果に収束する)が、「明示して選んだ」
    # という主張そのものが崩れる — この check はその主張だけを見る。
    ("the collar's placement goes back to a silent default",
     "photoloset/compose.py",
     [('    "衿": (0.0, 0.0, 0.0),\n}', '}')],
     ["the collar joins the bodice to the cape and the dress still sews "
      "shut"]),

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


#: --- 点の安定番号 ---------------------------------------------------------
#: 番号が動くとエージェントループは収束しない。前の周回の「30番から35番」が
#: 別の場所を指すから。ここはその四つの壊し方を、全部赤にする。
WHOLE_SUITE += [
    ("the registry hands out a fresh base every time it is asked",
     "photoloset/points.py",
     [("        k = self.key(piece, edge)\n"
       "        if k not in self._bases:",
       "        k = self.key(piece, edge)\n"
       "        if True:")],
     ["a number is a function of its address",
      "a dress piece keeps its number when a piece is inserted ahead of "
      "it"]),

    # NOT `len(self._bases) * STRIDE`: at the moment of assignment k is not
    # in _bases yet, so that expression equals self._next exactly and the
    # mutation is a no-op. The sweep caught it as a MISS rather than scoring
    # it green, which is the whole reason the MISS column exists.
    ("the registry re-sorts itself, so a new piece shifts the old bases",
     "photoloset/points.py",
     [("            self._next += STRIDE\n        return self._bases[k]",
       "            self._next += STRIDE\n"
       "        for _i, _k in enumerate(sorted(self._bases)):\n"
       "            self._bases[_k] = _i * STRIDE\n"
       "        return self._bases[k]")],
     ["a number is a function of its address"]),

    ("a reshaped outline is silently renumbered again",
     "photoloset/points.py",
     [("    if reshaped:", "    if False:")],
     ["a reshaped outline is refused, not renumbered"]),

    ("a span stops caring which edge its ends are on",
     "photoloset/points.py",
     [('    if (a["piece"], a["edge"]) != (b["piece"], b["edge"]):',
       '    if False:')],
     ["a span across two edges is refused"]),

    ("a saved registry is read back under a different stride",
     "photoloset/points.py",
     [('        if int(o.get("stride", STRIDE)) != STRIDE:',
       '        if False:')],
     ["the registry round-trips"]),
]


#: --- ダーツ ---------------------------------------------------------------
#: 平らな布を立体にする唯一の道具。壊し方は「縮まない」「真度を取らない」
#: 「輪郭に焼き込む」「重なりを見ない」「頂点が外でも通す」の五つ。
WHOLE_SUITE += [
    ("closing a dart stops shortening the edge", "photoloset/darts.py",
     [('        "edge_cm_after_closing": round(edge_len - w, 6),',
       '        "edge_cm_after_closing": round(edge_len, 6),')],
     ["closing a dart shortens the edge by the intake",
      "a dart on the dress front closes at the address it sits"]),

    ("the dart is never trued, so its legs stay unequal",
     "photoloset/darts.py",
     [("    if abs(la - lb) > LEG_TOLERANCE_CM:\n        lo_u = w / 2.0 / edge_len",
       "    if False:\n        lo_u = w / 2.0 / edge_len")],
     ["truing moves the dart until the legs match"]),

    ("the dart writes its legs into the outline", "photoloset/darts.py",
     [("        r = open_one(out, d)",
       "        if d['edge'] in es:\n"
       "            p['outline'] = list(p['outline']) + [[0.0, 0.0]]\n"
       "        r = open_one(out, d)")],
     ["a dart never edits the outline it sits on"]),

    ("two darts on one edge stop noticing each other",
     "photoloset/darts.py",
     [("                if clash:", "                if False:")],
     ["overlapping darts are refused and separated ones are not"]),

    ("an apex outside the panel is accepted", "photoloset/darts.py",
     [("    if not _inside(out, apex) or margin < APEX_MARGIN_CM:",
       "    if False:")],
     ["a dart whose apex leaves the panel is refused"]),
]


#: --- 人台に着せる ---------------------------------------------------------
#: 型紙と「30番から35番をゆとりを」の間の一段。壊し方は「身体の無い高さで
#: 例外に戻る」「合わせが剛体でなくなる」「押し出した形を測る」「身体の無い
#: 点を離れとして数える」。
WHOLE_SUITE += [
    ("radius_at goes back to raising below the form",
     "photoloset/mannequin.py",
     [("    if y < levels[0][0] - 1e-9 or y > levels[-1][0] + 1e-9:\n"
       "        return None",
       "    if False:\n        return None")],
     ["there is no body below the dress form"]),

    ("the alignment scales the garment instead of moving it",
     "photoloset/mannequin.py",
     [("    moved = [(x + dx, y + dy, z + dz) for (x, y, z) in points]",
       "    moved = [((x + dx) * 1.02, y + dy, (z + dz) * 1.02)\n"
       "             for (x, y, z) in points]")],
     ["the garment is moved onto the form without changing shape"]),

    ("the garment is anchored by its hem instead of its neckline",
     "photoloset/mannequin.py",
     [("    dy = top - max(ys)", "    dy = top - min(ys)")],
     ["the garment is moved onto the form without changing shape",
      # align() is generic — the dress's own draped points run through the
      # SAME function, and its pinned dy (38.8742) is computed from the
      # SAME `top - max(ys)`. Measured: with min(ys) it comes out 156.05,
      # not 38.8742.
      "the dress mannequin builds now that body_length is measured, and "
      "the garment fits onto it"]),

    ("clearance measures the pushed-out garment, not the fallen one",
     "photoloset/mannequin.py",
     [("    al = align(man, points)\n"
       "    if al[\"verdict\"] != \"ANSWER\":\n"
       "        return al\n"
       "    rows: List[Dict[str, Any]] = []",
       "    al = align(man, dress(man, points)[\"points\"])\n"
       "    if al[\"verdict\"] != \"ANSWER\":\n"
       "        return al\n"
       "    rows: List[Dict[str, Any]] = []")],
     ["clearance is measured on the garment as it fell",
      # Same function, same effect on the dress's own c_fell — measuring
      # the pushed-out points instead of the fallen ones moves
      # inside_the_body and min_clearance_cm off their pins on this
      # garment too.
      "the dress mannequin builds now that body_length is measured, and "
      "the garment fits onto it"]),

    ("a height with no body is counted as clearance instead",
     "photoloset/mannequin.py",
     [("        if surface is None:\n"
       "            free += 1\n"
       "            rows.append({\"i\": i, \"y\": round(y, 3),"
       " \"state\": NO_BODY})\n"
       "            continue",
       "        if surface is None:\n"
       "            apart += 1\n"
       "            rows.append({\"i\": i, \"y\": round(y, 3),"
       " \"state\": \"APART\"})\n"
       "            continue")],
     ["the clearance states partition every point"]),

    # The coat's own measure set always has body_length, and the dress's own
    # measure set does too now (this task's ninth spot) — so on either
    # garment this mutation is invisible: `have[...]` still gets populated
    # by the loop above and nothing changes. `empty_man =
    # _mq.build(_gm.Measures())` inside "curvature refuses missing
    # measurements…" feeds a Measures object with NOTHING recorded, so it
    # is the one place this suite still calls build() on a measure set that
    # is missing every spot; with the guard skipped it stops refusing and
    # crashes instead at `dims(have["hip"])` — a KeyError the guard()
    # around the check catches and reports as that check going red.
    ("the mannequin stops refusing a missing measurement",
     "photoloset/mannequin.py",
     [("    if missing:\n"
       "        return {\"verdict\": NO_MEASURE, \"missing\": missing,",
       "    if False:\n"
       "        return {\"verdict\": NO_MEASURE, \"missing\": missing,")],
     ["curvature refuses missing measurements and a grid too coarse to "
      "triangulate"]),

    # ---- convergence.loop() ----------------------------------------------
    ("a new address stops continuing the loop",
     "photoloset/convergence.py",
     [("    if new_addresses:\n        return dict(base, verdict=CONTINUE,\n",
       "    if False:\n        return dict(base, verdict=CONTINUE,\n")],
     ["a new address continues the loop"]),

    ("the fixed point never converges",
     "photoloset/convergence.py",
     [('return dict(base, verdict=CONVERGED,\n'
       '                reason="この周で住所空間は動かなかった — 提案は無いか、"\n'
       '                       "既にある値と一致した。不動点")',
       'return dict(base, verdict=CONTINUE,\n'
       '                reason="この周で住所空間は動かなかった — 提案は無いか、"\n'
       '                       "既にある値と一致した。不動点")')],
     ["agreement is a fixed point without another round"]),

    ("a contradiction stops being terminal",
     "photoloset/convergence.py",
     [("    if contested:\n        return dict(base, verdict=CONTESTED, contested=contested,\n",
       "    if False:\n        return dict(base, verdict=CONTESTED, contested=contested,\n")],
     ["a contradiction is terminal, not a retry"]),

    # A plain store-layer ANSWER (exact match already on file) used to be
    # read as agreement without ever asking whether the ADDRESS itself was
    # still contested — a resubmission of one already-disputed side could
    # silently un-terminal a contradiction. Disabling the resolve() check
    # this fix added reproduces that exact defect.
    ("loop stops checking store.resolve before calling a write agreement",
     "photoloset/convergence.py",
     [('        resolved = store.resolve(core, key)\n'
       '        if resolved["verdict"] == CONTESTED_IN_CROSS:',
       '        resolved = store.resolve(core, key)\n'
       '        if False:')],
     ["a contradiction is terminal, not a retry",
      "reopening an adopted address needs a name"]),

    ("storage order stops being able to stop the loop",
     "photoloset/convergence.py",
     [('    order = ingest_order_check(store.write_plan())\n'
       '    if order["verdict"] != "ANSWER":\n',
       '    order = ingest_order_check(store.write_plan())\n'
       '    if False:\n')],
     ["storage order can stop the loop, not just the address map"]),

    ("an adopted address reopens anonymously",
     "photoloset/convergence.py",
     [('        by = str(rev.get("by") or "")\n',
       '        by = str(rev.get("by") or "") or "auto"\n')],
     ["reopening an adopted address needs a name"]),

    # The reopen-signature gate used to only look at `prior["state"] ==
    # OBSERVED`. The first successful reopen adds a second, differing
    # observation, which flips the ledger's own state to CONTESTED — so a
    # gate that only fires on OBSERVED silently stops protecting the
    # address after its first use. This mutation removes the CONTESTED
    # fallback this fix added, reproducing that exact hole.
    ("the reopen gate stops surviving past its first use",
     "photoloset/convergence.py",
     [('        elif prior["state"] == LEDGER_CONTESTED:\n'
       '            prior_adopted_value = prior.get("adopted_value")',
       '        elif False:\n'
       '            prior_adopted_value = prior.get("adopted_value")')],
     ["reopening an adopted address needs a name"]),

    ("the loop stops listening to convergence.check's escalation",
     "photoloset/convergence.py",
     [('    if conv["verdict"] == ESCALATE:\n'
       '        return dict(base, verdict=ESCALATE, reason=conv["why_escalate"])\n',
       '    if False:\n'
       '        return dict(base, verdict=ESCALATE, reason=conv["why_escalate"])\n')],
     ["the same rejected claim escalates, a different one each round does not"]),

    # Ledger.state()'s OBSERVED branch used to always read obs[0] — the
    # first observation in INSERTION order — for adopted_by. A plain
    # observe() recorded before the matching propose()+adopt() at the same
    # value sits first, so adopted_by silently read "" even though the
    # address HAD been adopted. This is the exact value loop()'s reopen
    # gate reads, so masking it would let an already-adopted address
    # reopen with no name required.
    ("Ledger.state reads the first observation instead of the adopted one",
     "photoloset/garment.py",
     [("            e0 = last_adopted if last_adopted is not None else obs[0]",
       "            e0 = obs[0]")],
     ["reopening an adopted address needs a name"]),
]


#: --- マーカー -------------------------------------------------------------
#: 生地を買う数字。壊し方は「知らないことを既定で埋める」「縫い代を落とす」
#: 「並べ替えを入力順にする」「幅の超過を通す」。
WHOLE_SUITE += [
    ("the marker fills in a cut count nobody stated",
     "photoloset/marker.py",
     [("    if missing:\n        return {\"verdict\": NO_COUNT",
       "    missing = []\n"
       "    cut = {(p.get(\"name\") or \"?\"): max(1, int(cut.get(\n"
       "        p.get(\"name\") or \"?\", 1))) for p in pieces}\n"
       "    if missing:\n        return {\"verdict\": NO_COUNT")],
     ["a marker refuses what it cannot know"]),

    ("the seam allowance never reaches the cloth",
     "photoloset/marker.py",
     [("        cw, ch = w + 2.0 * sa, h + 2.0 * sa",
       "        cw, ch = w, h")],
     ["the seam allowance is inside the fabric it needs",
      "the dress marker lays eight cut pieces onto real cloth"]),

    # This went MISS the first time, aimed at "more copies need more fabric":
    # the reference coat's pieces are ALREADY generated tallest-first
    # (112, 112, 78.6), so removing the sort changed nothing that check
    # watched. The check now hands the sleeve in first and requires the same
    # marker back, which is the property the sort exists for.
    ("the marker lays pieces in the order they arrived",
     "photoloset/marker.py",
     [('    items.sort(key=lambda it: (-it["h"], it["piece"], it["copy"]))',
       "    pass")],
     ["the same order lays the same marker"]),

    ("a piece wider than the cloth is laid anyway",
     "photoloset/marker.py",
     [("    if over:", "    if False:")],
     ["a marker refuses what it cannot know"]),

    ("the fabric width stops bounding the shelf",
     "photoloset/marker.py",
     [('        if x + it["w"] > fabric_width_cm + 1e-9:',
       "        if False:")],
     ["more copies need more fabric"]),
]


#: --- 部材表 ----------------------------------------------------------------
#: 買うものの一覧。壊し方は「宣言しても拒否が消えない」「生地をここで
#: 独自に作り直す」「比を渡しても答えが動かない」。
WHOLE_SUITE += [
    ("declaring notions does not clear the refusal",
     "photoloset/bom.py",
     [("    if not notions:\n        refused[\"notions\"] = {",
       "    if True:\n        refused[\"notions\"] = {")],
     ["a BOM names its known lines and its refused lines"]),

    ("the BOM recomputes fabric instead of reading the marker",
     "photoloset/bom.py",
     [('            "quantity": mk["length_m"],',
       '            "quantity": round(mk["length_m"] * 1.1, 3),')],
     ["the BOM's fabric line is the marker's, not a second calculation",
      "the dress BOM answers fabric and refuses three lines it cannot "
      "know"]),

    ("the thread ratio is named but never used",
     "photoloset/bom.py",
     [('            "quantity": round(seam_len * ratio / 100.0, 3),',
       '            "quantity": round(seam_len * 2.75 / 100.0, 3),')],
     ["the BOM's thread line depends on the ratio it names"]),
]


# ---------------------------------------------------------------------------
# photoloset/dxf.py — the DXF export has five checks. Every one below is a
# mutation of the WRITER, never of the check's own reader (that reader is
# built fresh from group-code pairs inside run_checks.py, independent of
# ``photoloset.dxf``'s internals — see ``_dxf_blocks``).
WHOLE_SUITE += [
    # The LAYER table drops one entry. The five layer NAMES are exactly what
    # "the layer names must make clear which is which" (the brief this
    # module answers) is checked against, so losing one is a structural
    # defect a CAD user would meet as "GRAIN_LINES has no layer" the moment
    # they tried to isolate it.
    ("the DXF layer table drops a layer",
     "photoloset/dxf.py",
     [("_LAYER_ORDER = (LAYER_SEW, LAYER_CUT, LAYER_NOTCH, LAYER_GRAIN, "
       "LAYER_LABEL)",
       "_LAYER_ORDER = (LAYER_SEW, LAYER_CUT, LAYER_NOTCH, LAYER_LABEL)")],
     ["the DXF file parses as group-code pairs"]),

    # Every coordinate drifts by a constant 0.3mm. A pure translation moves
    # nothing about SHAPE — area, "cut differs from sew", notch counts are
    # all unaffected — so this has to land on exactly the one check that
    # reads coordinates literally rather than derived quantities from them.
    ("DXF coordinates drift by a constant offset",
     "photoloset/dxf.py",
     [("    v = round(float(v), 4)\n    if v == 0.0:",
       "    v = round(float(v), 4) + 0.0003\n    if v == 0.0:")],
     ["every draft vertex survives to its DXF coordinate"]),

    # The cut line is written from the SEWING outline instead of the offset
    # ``off["cut_line"]`` — "the seam allowance never reached the export",
    # named directly in the brief as the failure mode to guard against. The
    # written CUT_LINE polygon becomes identical to SEWING_LINE, so both the
    # curve-identity check and the round-trip area check (which compares the
    # rebuilt CUT_LINE area against the marks' own cut_area_cm2) catch it —
    # two independent measurements of the same real defect, not one check
    # duplicating the other's math.
    ("the seam allowance never reaches the cut line",
     "photoloset/dxf.py",
     [('cut_line = ([(float(q[0]), float(q[1])) for q in off["cut_line"]]\n'
       '                    if cut_ok else [])',
       'cut_line = ([(float(q[0]), float(q[1])) for q in outline]\n'
       '                    if cut_ok else [])')],
     ["the cut line and sewing line are different curves on separate "
      "layers",
      "the DXF round-trips into rebuilt piece areas"]),

    # A double notch (the back's one and the sleeve cap's matching one) only
    # gets one line instead of two — the second stroke that tells a cutter
    # "this side, not the other" silently disappears.
    ("double notches lose their second line",
     "photoloset/dxf.py",
     [('offsets = (0.0,) if n["kind"] == "single" else (-0.3, 0.3)',
       'offsets = (0.0,)')],
     ["DXF notch and grain lines land at the marks' own positions"]),

    # The notch normal is flipped to the wrong side of the seam. Every tick
    # still exists, still has the right depth, and the population count
    # would not move at all — only a check that recomputes the expected
    # endpoint from (edge, arc_cm, depth_cm, kind) and matches it exactly
    # can tell a notch pointing into the garment from one pointing out of
    # it.
    ("a notch points to the wrong side of the seam",
     "photoloset/dxf.py",
     [("            nx, ny = ty / L, -tx / L",
       "            nx, ny = -ty / L, tx / L")],
     ["DXF notch and grain lines land at the marks' own positions"]),

    # The grain line is drawn as an unrelated constant segment instead of
    # the mark's own ``grain["line"]`` — the count of GRAIN_LINES entities
    # stays exactly right (one per piece), so only a position check can
    # tell the file is lying about which way the fabric grain runs.
    ("the grain line ignores the mark and draws a constant segment",
     "photoloset/dxf.py",
     [('            (gx1, gy1), (gx2, gy2) = g["line"]\n'
       '            a, b = T((gx1, gy1)), T((gx2, gy2))',
       '            a, b = T((0.0, 0.0)), T((10.0, 10.0))')],
     ["DXF notch and grain lines land at the marks' own positions"]),

    # The cut line loses its last vertex on the way out — one point short of
    # what the draft actually offset. The written CUT_LINE polygon has one
    # fewer vertex than the marks recorded, which the parse-time vertex
    # total catches (it counts vertices against the draft AND the cut
    # lines). Measured, not guessed: dropping the vertex next to the
    # closing edge does not shave a sliver off the polygon — the mitred
    # corner there means the implicit closing edge (VERTEX list wraps via
    # the POLYLINE closed flag) now spans a much longer jump, so the
    # rebuilt CUT_LINE area moves by over a thousand cm2 and even goes
    # SMALLER than SEWING_LINE on some pieces. Three checks catch three
    # different symptoms of the one dropped point: the vertex total (file
    # parses), the cut-no-longer-strictly-encloses-sew comparison (cut
    # differs from sew), and the rebuilt area (round-trips).
    ("the cut line loses its last vertex on the way out",
     "photoloset/dxf.py",
     [('cut_t = [T(q) for q in cut_line]',
       'cut_t = [T(q) for q in cut_line[:-1]]')],
     ["the DXF file parses as group-code pairs",
      "the cut line and sewing line are different curves on separate "
      "layers",
      "the DXF round-trips into rebuilt piece areas"]),

    # No coat check pins a literal extents_cm, so this is invisible to the
    # existing suite; the dress check does read extents_cm literally, and
    # widening the gap between laid-out pieces shifts the bounding box's max
    # x by exactly (pieces - 1) x the widening, moving it off the pin.
    ("the DXF export spaces pieces further apart on the sheet",
     "photoloset/dxf.py",
     [("GAP_CM = 15.0", "GAP_CM = 20.0")],
     ["the dress reaches DXF directly, because save() cannot draft it"]),

    # The STYLE table's font is blanked. Every TEXT byte is still correct
    # cp932 — the file still parses, the piece names still round-trip as
    # strings — so only a check that reads the STYLE table itself can see
    # this. Measured in QCAD (real CAD application, not this repository's
    # own code): a blank primary font here is exactly the state that drew
    # the piece names as three "?" apiece before this table existed at all.
    ("the STYLE table's font is blanked",
     "photoloset/dxf.py",
     [('TEXT_FONT = "MS-Gothic"', 'TEXT_FONT = ""')],
     ["the DXF declares a text style with a real font"]),

    # The STYLE entry is given a name other than "STANDARD". The table is
    # still there, the font is still MS-Gothic — but no TEXT entity in this
    # file sets group 7, so every reader falls back to the IMPLICIT default
    # style, never to a style that merely exists under some other name. A
    # check that only asked "is there a STYLE table with a real font"
    # (dropping the name comparison) would stay green here while a real CAD
    # application drew "?" again, for the same reason as the blank-font
    # entry above.
    ("the STYLE entry is renamed away from the implicit default",
     "photoloset/dxf.py",
     [('TEXT_STYLE = "STANDARD"', 'TEXT_STYLE = "JP"')],
     ["the DXF declares a text style with a real font"]),
]


#: --- pass 6: curvature.py, Gauss-Bonnet made into a number -----------------
#: Every entry here was verified in a FRESH interpreter before being wired
#: in — mutate the file, run ONLY
#: ``a_pattern_piece_absorbs_curvature_two_ways`` in a subprocess, read
#: which of its five declared names went red, restore. Two mutations that
#: looked plausible turned out to be no-ops and are recorded here rather
#: than silently dropped: (1) breaking ``angle_sums`` to only accumulate two
#: of a triangle's three vertices reddens the same three checks the z-drop
#: below does, so it was not kept as a second, redundant entry; (2) removing
#: the missing-measurement guard from EITHER ``mesh()`` or ``report()``
#: alone is caught by the OTHER guard before the removed one is ever
#: reached — the two are independent layers, not one check protected once —
#: so that specific sub-path has no dedicated entry here. The two
#: too-coarse-grid mutations below already turn "curvature refuses missing
#: measurements and a grid too coarse to triangulate" red by a different
#: door, which is what the falsifier owes the check's NAME, not every
#: clause inside it.
WHOLE_SUITE += [
    # The 3D angle formula drops the z term from its dot product while
    # still dividing by the full 3D norms — cos_t is no longer any angle's
    # cosine. A closed sphere no longer totals exactly 4*pi (it becomes
    # MESH-SIZE DEPENDENT: measured -11126.5 deg at 20x10 and -214722.4 deg
    # at 80x40, not even close to each other, let alone to 720), a cylinder
    # no longer totals 0 (-1.48e+04 deg at 20x12), and the mannequin's own
    # total stops converging to anything sane. One bad primitive, three
    # ground-truth checks catch it three different ways.
    ("curvature's 3D angle formula drops the z axis",
     "photoloset/curvature.py",
     [("    cos_t = (v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]) "
       "/ (n1 * n2)",
       "    cos_t = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)")],
     ["a closed sphere totals four pi by angle defect",
      "a developable cylinder carries no curvature",
      "the mannequin's total curvature converges while its band "
      "distribution does not"]),

    # The interior-vertex loop starts at the HIP ring (j=0) instead of
    # skipping it — exactly the boundary-inclusion bug this module's own
    # docstring warns against ("the hip base ring... is outline, not an
    # interior vertex"). The sphere and cylinder ground-truth checks do not
    # touch this loop at all (they sum their own meshes directly through
    # ``angle_sums``) and stay green, which is the point: only a check that
    # actually exercises the mannequin's boundary notices. Measured: total
    # jumps from ~183 deg to 3803.6 deg at the coarsest grid alone, and the
    # hip->waist band alone swings by 25192.8 deg across the refinement
    # sequence instead of the ~27 deg it swings by honestly.
    ("curvature sums the hip ring as if it were interior",
     "photoloset/curvature.py",
     [("    for j in range(1, height_steps):",
       "    for j in range(0, height_steps):")],
     ["the mannequin's total curvature converges while its band "
      "distribution does not"]),

    # The exact mistake this module's docstring records the FIRST attempt
    # making: converting the total straight into a dart intake in
    # centimetres (90 deg / 12 cm dart = 18.85 cm, against a real dart of
    # 2-4 cm) rather than leaving the outline/dart split to the pattern
    # maker. Measured: 2 forbidden keys appear in the report the moment
    # this ships.
    ("curvature starts converting the total into a dart intake",
     "photoloset/curvature.py",
     [('        "total_is_shared_not_split": (',
       '        "dart_intake_cm": finest["total_deg"] / 7.5,\n'
       '        "total_is_shared_not_split": (')],
     ["the curvature report shares the total, it does not compute a dart "
      "intake"]),

    # mesh() stops refusing a grid too coarse to triangulate (segments < 3
    # or height_steps < 1) — REFUSE, DON'T DEFAULT, broken. Measured: a
    # ZeroDivisionError inside mesh() itself (segments=2 makes the ring
    # step size divide by nothing sensible downstream), caught by the
    # check's own guard() and reported as a crash rather than the typed
    # UNKNOWN_RESOLUTION_TOO_COARSE the property promises.
    ("curvature stops refusing a grid too coarse to triangulate",
     "photoloset/curvature.py",
     [("    if segments < MIN_SEGMENTS or height_steps < MIN_HEIGHT_STEPS:",
       "    if False:")],
     ["curvature refuses missing measurements and a grid too coarse to "
      "triangulate"]),

    # report() stops requiring at least two resolutions to show a
    # refinement sequence — the "single resolution" refusal this function
    # exists for (there is nothing to call convergence with only one
    # point) silently disappears. Measured: an IndexError reaching into
    # ``steps[-2]`` when only one resolution was ever computed.
    ("curvature's report stops requiring two resolutions to show "
     "convergence",
     "photoloset/curvature.py",
     [("    if len(resolutions) < 2:", "    if False:")],
     ["curvature refuses missing measurements and a grid too coarse to "
      "triangulate"]),
]


#: --- プロジェクトの範囲 ---------------------------------------------------
#: UI に一覧が出ていて、別の服を選んでも何も変わらなかった。**分離されて
#: いるように見えて、されていない。**
WHOLE_SUITE += [
    ("the migration guard stops looking at whether projects/ exists",
     "photoloset/mcp.py",
     [("    if PROJECTS.exists():\n        return None\n"
       "    movable = [f for f in HOME.glob",
       "    if False:\n        return None\n"
       "    movable = [f for f in HOME.glob")],
     ["the flat store moves into a project once and only once"]),

    ("a project name goes straight into the path", "photoloset/mcp.py",
     [('    if any(c in n for c in "/\\\\\\0") or n.startswith("."):\n'
       "        return None",
       "    if False:\n        return None")],
     ["a project name cannot reach outside the store"]),

    ("the store forgets which project is open", "photoloset/mcp.py",
     [("    d = PROJECTS / _project()\n"
       "    d.mkdir(parents=True, exist_ok=True)\n"
       "    return d / name",
       "    return HOME / name")],
     ["two projects do not see each other"]),

    ("the fabric book is filed under the garment", "photoloset/mcp.py",
     [('_SHARED = ("fabrics.json",)', "_SHARED = ()")],
     ["the fabric book is shared, the garment is not"]),
]


#: --- pass 6: the geometric route (mannequin_spline / base_garment /
#: flatten) --- Measured 2026-08-27 on this suite's reference measurements
#: (chest 108, waist 92, hip 104, body_length 112): the boundary-tangent
#: choice moves the smooth mannequin's total curvature from a 0.88deg gap
#: against the linear one to a 170.6deg gap (12.85 vs 183.40); disabling
#: the extremum clamp in the Fritsch-Carlson limiter produces a real
#: 0.081cm overshoot past a measured girth (tolerance is 1e-6cm); dropping
#: `+ gap` from the radial offset moves every probed vertex by exactly
#: 1.3cm (the gap this entry's check asks for); removing the clip on a
#: requested range below the mannequin's own hip level drops 6 rings and
#: reports 0.0cm clipped instead of the 40.0cm actually missing; faking
#: every triangle's area ratio to 1.0 collapses the straddle the
#: distortion check asks for; and deleting the NO_MANNEQUIN refusal turns
#: an unbuilt mannequin into a bare KeyError on `man["_levels"]`, which
#: ``guard()`` reports as this check going red under its own name.
WHOLE_SUITE += [
    ("the smooth mannequin's boundary tangent stops matching the linear "
     "secant", "photoloset/mannequin_spline.py",
     [("    m[0] = d[0]\n    m[-1] = d[-1]",
       "    m[0] = 0.0\n    m[-1] = 0.0")],
     ["the smooth mannequin keeps the same five levels, and its total "
      "curvature converges near the linear one while its bands settle "
      "far tighter"]),

    ("the monotone limiter stops clamping extrema and the overshoot "
     "bound", "photoloset/mannequin_spline.py",
     [("    for i in range(1, n - 1):\n"
       "        if d[i - 1] == 0.0 or d[i] == 0.0 or (d[i - 1] > 0) != "
       "(d[i] > 0):\n"
       "            m[i] = 0.0          # 極値。水平にしないと必ず行き過ぎる\n"
       "        else:\n"
       "            m[i] = (d[i - 1] + d[i]) / 2.0\n"
       "    for i in range(n - 1):\n"
       "        if d[i] == 0.0:\n"
       "            m[i] = 0.0\n"
       "            m[i + 1] = 0.0\n"
       "            continue\n"
       "        a, b = m[i] / d[i], m[i + 1] / d[i]\n"
       "        s = a * a + b * b\n"
       "        if s > 9.0:",
       "    for i in range(1, n - 1):\n"
       "        m[i] = (d[i - 1] + d[i]) / 2.0\n"
       "    for i in range(n - 1):\n"
       "        if d[i] == 0.0:\n"
       "            m[i] = 0.0\n"
       "            m[i + 1] = 0.0\n"
       "            continue\n"
       "        a, b = m[i] / d[i], m[i + 1] / d[i]\n"
       "        s = a * a + b * b\n"
       "        if s > 900.0:")],
     ["the monotone spline's four spans stay within their own measured "
      "girths"]),

    ("the base garment forgets the air gap", "photoloset/base_garment.py",
     [("            surface = r + gap", "            surface = r")],
     ["the base garment is the body surface plus a constant radial "
      "offset"]),

    ("the base garment stops clipping to where the body actually is",
     "photoloset/base_garment.py",
     [("    lo = max(want_lo, body_lo)", "    lo = want_lo")],
     ["the base garment ends where the body ends instead of "
      "extrapolating past it"]),

    ("flatten fakes every triangle's area ratio as undistorted",
     "photoloset/flatten.py",
     [("        ratio = None if a3 <= 1e-9 else a2 / a3",
       "        ratio = None if a3 <= 1e-9 else 1.0")],
     ["flattening a non-developable panel distorts both area and angle, "
      "measured triangle by triangle"]),

    ("flatten stops refusing a mannequin that never stood up",
     "photoloset/flatten.py",
     [('    if man.get("verdict") != "ANSWER":\n'
       '        return {"verdict": NO_MANNEQUIN,\n'
       '                "why": "人台が立っていないので平面化できません",\n'
       '                "upstream_verdict": man.get("verdict")}',
       '    if False:\n'
       '        return {"verdict": NO_MANNEQUIN,\n'
       '                "why": "人台が立っていないので平面化できません",\n'
       '                "upstream_verdict": man.get("verdict")}')],
     ["flatten refuses a grid too coarse to triangulate and a mannequin "
      "that never stood up"]),

    # **The "one pipeline" claim, unwired.** 2026-08-27, an outside check
    # found that no check anywhere passed `radius_at=mannequin_spline.
    # radius_at` through to `base_garment.build`/`flatten.build` — silently
    # discarding the caller's `radius_at` argument (always falling back to
    # the linear default) left the whole suite green. These two entries
    # regress that fix one function at a time.
    ("base_garment silently ignores the caller's radius_at",
     "photoloset/base_garment.py",
     [("    rf: RadiusFn = radius_at or _mq.radius_at",
       "    rf: RadiusFn = _mq.radius_at")],
     ["the smooth mannequin actually reaches base_garment and flatten "
      "through radius_at, not just curvature"]),

    ("flatten silently ignores the caller's radius_at",
     "photoloset/flatten.py",
     [("    rf: RadiusFn = radius_at or _mq.radius_at",
       "    rf: RadiusFn = _mq.radius_at")],
     ["the smooth mannequin actually reaches base_garment and flatten "
      "through radius_at, not just curvature"]),
]


#: --- 縫う順序 -------------------------------------------------------------
WHOLE_SUITE += [
    ("every seam is called flat", "photoloset/sewing_order.py",
     [("        if u.join(r[\"a\"], r[\"b\"]):", "        if True:")],
     ["the flat seams come before the ones that close a loop"]),

    ("the closing seams are not held back", "photoloset/sewing_order.py",
     [("            later.append(r)",
       "            order.append(dict(r, how=ROUND, why=\"\"))")],
     ["the flat seams come before the ones that close a loop"]),

    ("the cycle rank forgets the components",
     "photoloset/sewing_order.py",
     [("    beta = len(rows) - len(pieces) + comps",
       "    beta = len(rows) - len(pieces)")],
     ["the number of in-the-round seams is not a choice"]),
]



#: --- 輪郭合わせ (silhouette) ------------------------------------------------
WHOLE_SUITE += [
    # The core formula: ease(y) = outline half-width - body half-width.
    # Biasing it breaks the self-consistency check directly (the base's
    # own silhouette should come back solving ease==GAP exactly).
    ("the ease formula picks up a constant bias",
     "photoloset/silhouette.py",
     [("    eases = [hw - a for hw, a in zip(half_widths, body_halfs)]",
       "    eases = [hw - a + 0.5 for hw, a in zip(half_widths, "
       "body_halfs)]")],
     ["ease solved from width alone reproduces the base's own silhouette "
      "near zero"]),

    # The min-ease bound (a body cannot fit into a narrower garment) is
    # pushed out of reach, so a silhouette narrower than the body at every
    # height no longer refuses.
    ("the min-ease bound is pushed out of reach",
     "photoloset/silhouette.py",
     [("        if e < MIN_EASE_CM - _EPS:",
       "        if e < MIN_EASE_CM - _EPS - 1000.0:")],
     ["a silhouette narrower than the body at any height is refused by "
      "name and shortfall"]),

    # Same shape on the other bound: a silhouette far wider than this
    # offset model can represent no longer refuses either.
    ("the max-ease bound is pushed out of reach",
     "photoloset/silhouette.py",
     [("        elif e > MAX_EASE_CM + _EPS:",
       "        elif e > MAX_EASE_CM + _EPS + 1000.0:")],
     ["a silhouette far wider than this offset model can reach is "
      "refused by name and excess"]),

    # One of the three typed one-view-limitation fields is dropped from
    # the answer — the honest statement stops being three separate,
    # substantive claims and becomes two.
    ("one single-view-limits field is dropped from the answer",
     "photoloset/silhouette.py",
     [('            "outline_scan_keeps_only_the_outer_extent": (\n'
       '                "高さごとの水平走査で交点が2点より多くても、外側の最小"\n'
       '                "・最大だけを幅として使い、内側の交点(凹みの証拠)は捨"\n'
       '                "てています ── upper boundの具体的な現れです"),\n',
       '')],
     ["depth moves as a stated byproduct of width-only ease, not as a "
      "second measurement"]),

    # The point-count guard is removed. A 2-point outline whose two points
    # sit at DIFFERENT heights is no longer caught by the height guard
    # beside it, so it slips past as something other than the typed
    # refusal.
    ("the outline point-count guard is removed",
     "photoloset/silhouette.py",
     [("    if (len(outline) < 3\n"
       "            or any(not math.isfinite(v) for p in outline "
       "for v in p)):",
       "    if (False\n"
       "            or any(not math.isfinite(v) for p in outline "
       "for v in p)):")],
     ["a degenerate or too-few-point outline is refused, not silently "
      "scanned"]),

    # outline_width_at stops reading the true leftmost/rightmost x and
    # instead assumes the outline is symmetric about x=0 — every check
    # built on a centered fixture stays green, only an off-center outline
    # can tell the two implementations apart.
    ("outline_width_at assumes the outline is centered on x=0",
     "photoloset/silhouette.py",
     [("    xs = _scan_x(outline, y)\n"
       "    if len(xs) < 2:\n"
       "        return None\n"
       "    return xs[0], xs[-1]",
       "    xs = _scan_x(outline, y)\n"
       "    if len(xs) < 2:\n"
       "        return None\n"
       "    m = max(abs(xs[0]), abs(xs[-1]))\n"
       "    return -m, m")],
     ["an outline whose left and right extents are not equal and "
      "opposite still solves the same ease"]),

    # OUTLINE_GAP stops being reachable — an outline that leaves some
    # requested ring heights uncovered is no longer refused by name.
    ("the outline-gap refusal is disabled",
     "photoloset/silhouette.py",
     [("    if missing_outline:",
       "    if False and missing_outline:")],
     ["silhouette refuses an unbuilt mannequin, too coarse a grid, a "
      "height range outside the body, and an outline that leaves a gap"]),

    # to_surface() stops passing its OWN height_steps through to
    # base_garment.build, so the materialized mesh no longer has the
    # ring count the match result itself reports.
    ("to_surface asks base_garment.build for the wrong ring count",
     "photoloset/silhouette.py",
     [('                     height_steps=result["height_steps"],',
       '                     height_steps=result["height_steps"] + 5,')],
     ["the matched radius function plugs into base_garment.build "
      "without a second mesh builder"]),
]


#: --- パネル分割 -----------------------------------------------------------
WHOLE_SUITE += [
    # #1 The cut criterion goes from "worst" to "least bad" — still cuts
    # SOMEWHERE, but not where distortion is worst, which moves the seam
    # positions and every downstream pinned number (before/after indices).
    ("the cut criterion picks the least-distorted line instead of the "
     "worst one", "photoloset/panels.py",
     [("        if s > best_s:\n            best_c, best_s = c, s",
       "        if s < best_s or best_c is None:\n"
       "            best_c, best_s = c, s")],
     ["a seam is placed where the flattened tube's distortion is worst, "
      "and buys a measured drop in it"]),

    # #1b The panel picked to split next is the LEAST distorted one, not
    # the worst — same family of defect, different call site.
    ("the panel chosen to split next is the least distorted one",
     "photoloset/panels.py",
     [("        worst = max(candidates, key=lambda p: p[\"flat\"]"
       "[\"distortion_index\"])",
       "        worst = min(candidates, key=lambda p: p[\"flat\"]"
       "[\"distortion_index\"])")],
     ["a seam is placed where the flattened tube's distortion is worst, "
      "and buys a measured drop in it"]),

    # #2 The boundary term's reference angle stops being pi (180deg) — the
    # combinatorial identity (interior + boundary == 2*pi per disc) is a
    # counting fact, not a geometric one, so ANY wrong reference constant
    # breaks the residual, whatever the mesh looks like.
    ("the boundary curvature's reference angle is no longer a straight "
     "line", "photoloset/panels.py",
     [("            boundary_deg += 180.0 - s", "            boundary_deg += 170.0 - s")],
     ["each panel's Gauss-Bonnet total splits into an outline share and "
      "a dart share, and the two sum back to exactly 360 degrees"]),

    # #3 The panel-count ceiling is loosened past the number of columns
    # that actually exist, so a request for MORE panels than columns stops
    # being refused.
    ("more panels than columns is accepted anyway", "photoloset/panels.py",
     [("    if n_panels > segments:", "    if n_panels > segments + 5:")],
     ["panels refuse a count that cannot fit the grid and a mannequin "
      "that never stood up"]),

    # #4 The ring seam (last panel's right edge back to the first panel's
    # left edge, closing the theta=0 cut) is dropped, turning a closed
    # ring of panels into an open chain — beta drops from 1 to 0 and every
    # seam becomes sewable flat.
    ("the panel ring never closes back to the first panel",
     "photoloset/panels.py",
     [("    n = len(panels)\n    seam_specs = []\n    for i in range(n):",
       "    n = len(panels)\n    seam_specs = []\n    for i in range(n - 1):")],
     ["the panel ring sews with exactly one seam in the round"]),

    # #5 The panel-area shoelace formula drops its /2, doubling every
    # panel's reported area_cm2 — the exact area pins this check reads
    # move, even though panel_count/draft_piece_count are untouched.
    ("panel area is reported without halving the shoelace sum",
     "photoloset/panels.py",
     [("def _poly_area(poly: Sequence[Vec2]) -> float:\n"
       "    n = len(poly)\n"
       "    s = 0.0\n"
       "    for i in range(n):\n"
       "        x1, y1 = poly[i]\n"
       "        x2, y2 = poly[(i + 1) % n]\n"
       "        s += x1 * y2 - x2 * y1\n"
       "    return abs(s) / 2.0",
       "def _poly_area(poly: Sequence[Vec2]) -> float:\n"
       "    n = len(poly)\n"
       "    s = 0.0\n"
       "    for i in range(n):\n"
       "        x1, y1 = poly[i]\n"
       "        x2, y2 = poly[(i + 1) % n]\n"
       "        s += x1 * y2 - x2 * y1\n"
       "    return abs(s)")],
     ["panels differ from the drafted coat in piece count and seam "
      "layout, not by accident"]),

    # #6 The dart depth ratio grows, so every requested intake grows with
    # it — at 0.5x the panel bounding box, panel 1's dart alone can no
    # longer fit any of the real seam's 8 segments (all ~9-11cm against a
    # ~14cm request), so only 2 of the 3 dart-bearing panels place a dart
    # at all and darts_list drops from 3 to 2.
    ("the dart depth ratio grows past what the real seam can take",
     "photoloset/panels.py",
     [("DEFAULT_DART_DEPTH_RATIO = 0.30", "DEFAULT_DART_DEPTH_RATIO = 0.50")],
     ["the drafted coat's own doors answer or refuse the panels for a "
      "reason they name"]),
]

#: --- 輪郭からの構造読み取り (structure.py) -----------------------------------
WHOLE_SUITE += [
    ("the symmetry axis goes back to a hardcoded 0.0",
     "photoloset/structure.py",
     [("    axis = centers[n // 2] if n % 2 == 1 else "
       "(centers[n // 2 - 1] + centers[n // 2]) / 2.0",
       "    axis = 0.0")],
     ["the symmetry axis is measured from the outline, not a hardcoded "
      "constant, and a tilted outline reports a large residual while a "
      "clean one reports zero"]),

    ("a concavity's reported height freezes to the search window's "
     "midpoint", "photoloset/structure.py",
     [('            "height_fraction": round((y - min_y) / height_span, 4),',
       '            "height_fraction": 0.5,')],
     ["the reported armpit height moves with the notch that produces it, "
      "not a fixed constant"]),

    ("the armpit bump-floor filter is disabled, so any deep concavity "
     "passes as an armpit", "photoloset/structure.py",
     [("    accepted = [(c, b, r) for c, b, r in scored if r >= bump_floor]",
       "    accepted = scored")],
     ["the armpit-vs-waist-taper bump-fraction boundary is a measured "
      "value, not assumed"]),

    ("the shoulder search window's upper edge turns exclusive",
     "photoloset/structure.py",
     [('        if k["height_fraction"] <= SHOULDER_WINDOW_MAX:',
       '        if k["height_fraction"] < SHOULDER_WINDOW_MAX:')],
     ["the shoulder search window's upper edge is a measured boundary, "
      "not open-ended"]),

    ("the self-intersection guard in _validate is disabled",
     "photoloset/structure.py",
     [("    if hits:", "    if False:")],
     ["from_outline refuses a missing-contract record, a degenerate "
      "outline, a re-closed outline, a self-crossing outline, and a "
      "non-positive frame by name -- and answers the valid neighbor of "
      "each"]),

    ("the too-small-outline floor is pushed out of reach",
     "photoloset/structure.py",
     [("    if area_frac < MIN_COVERAGE_FRACTION or height_frac < "
       "MIN_HEIGHT_FRACTION_OF_FRAME:",
       "    if area_frac < MIN_COVERAGE_FRACTION or height_frac < "
       "MIN_HEIGHT_FRACTION_OF_FRAME - 1000.0:")],
     ["the undersampled-outline and too-small-outline refusals fire at "
      "their exact measured boundary, not approximately there"]),

    ("cannot_answer's topic dispatch collapses to one topic's entry",
     "photoloset/structure.py",
     [("    hit = REFUSED_TOPICS.get(topic)",
       '    hit = REFUSED_TOPICS.get("fabric")')],
     ["each of the six refused topics answers with its own verdict, not "
      "a shared one, and an unknown topic refuses by a different name "
      "than any of them"]),

    ("the hem's front/back attribution refusal is dropped from the "
     "answer", "photoloset/structure.py",
     [('        "front_back_attribution": {\n'
       '            "verdict": CANNOT_HEM_ATTRIBUTION,\n'
       '            "why": "正面1枚の輪郭は外側の境界(visual hull)しか写しませ"\n'
       '                   "ん。前が短く後ろが長い「ハイロー」は、短い前端が長い"\n'
       '                   "後ろの陰に隠れて輪郭に現れないことがあり得るので、"\n'
       '                   "裾の高さ変化を前後に帰属させることはできません。ここ"\n'
       '                   "で言えるのは輪郭が左右方向にどう変化するかだけです",\n'
       '            "how_to_close": "側面・背面の写真を追加するか、前後を宣言する"\n'
       '                             "人による入力を追加してください",\n'
       '        },\n'
       '    }',
       '    }')],
     ["a resolved hem always carries the front/back attribution refusal, "
      "and a top-level refusal carries no landmarks at all"]),

    ("a part instance's own name is emitted blank",
     "photoloset/structure.py",
     [('"instance": "body:1", "part": "body",',
       '"instance": "", "part": "body",')],
     ["the part instances from_outline emits are consumable by "
      "resemble.per_part and resemble.structure_from, run for real"]),

    ("the symmetry axis picks up a random term, breaking determinism",
     "photoloset/structure.py",
     [("    axis = centers[n // 2] if n % 2 == 1 else "
       "(centers[n // 2 - 1] + centers[n // 2]) / 2.0",
       "    axis = (centers[n // 2] if n % 2 == 1 else "
       "(centers[n // 2 - 1] + centers[n // 2]) / 2.0) + "
       '__import__("random").random() * 10.0')],
     ["from_outline gives byte-identical output for the same outline "
      "called twice"]),
]


#: --- 合印・縫い代・布目線 (garment_marks.py / dxf.py) ------------------------
WHOLE_SUITE += [
    ("a known edge's width is read with an extra 1cm added",
     "photoloset/garment_marks.py",
     [("    width = sa[name] if name in sa else SEAM_ALLOWANCE[name][0]",
       "    width = sa[name] if name in sa else "
       "SEAM_ALLOWANCE[name][0] + 1.0")],
     ["a known edge reads its stated seam allowance, not a substituted "
      "number"]),

    ("the unstated-edge-name guard in offset_outline is disabled",
     "photoloset/garment_marks.py",
     [("    if unstated:", "    if False:")],
     ["an edge name missing from the table refuses by name, not by 0cm"]),

    ("the DXF export writes a cut line even when the seam allowance was "
     "refused", "photoloset/dxf.py",
     [('        cut_ok = off.get("verdict") == "ANSWER"',
       "        cut_ok = True")],
     ["a refused seam allowance leaves no cut line in the DXF, only the "
      "piece named"]),
]


def whole_suite(repo: Path, entries: Optional[Sequence[Any]] = None,
                touched: Optional[set] = None,
                out: Optional[Any] = None) -> Tuple[int, int]:
    """Run ``run_checks.py`` end to end under a mutation and read its exit.

    This is the falsifier for the pinned NAME SET: the failure it exists for
    is a check DISAPPEARING, which by construction cannot be observed by
    running only the functions that still declare it.

    Same crash-proofing as ``main``: one entry that raises is that entry
    going MISS, not the sweep ending. Returns ``(bad, ran)`` so a short run
    cannot be reported as a complete one.
    """
    entries = WHOLE_SUITE if entries is None else list(entries)
    out = sys.stdout if out is None else out
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
                print(f"  SKIP  {name}: anchor not found in {rel}", file=out)
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
            print(f"  {'RED ' if ok else 'MISS'}  {name}", file=out)
            print(f"        expected red: {expect}", file=out)
            print(f"        actually red: {failed}  (exit {r.returncode})", file=out)
        except BaseException as exc:                        # noqa: BLE001
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            bad += 1
            print(f"  MISS  {name}: HARNESS RAISED "
                  f"{type(exc).__name__}: {exc}", file=out)
        finally:
            if orig is not None:
                p.write_text(orig, encoding="utf-8")
                _clear_pycache(repo)
    _clear_pycache(repo)
    return bad, ran


def whole_suite_parallel(repo: Path, entries: Optional[Sequence[Any]] = None,
                         touched: Optional[set] = None,
                         jobs: Optional[int] = None) -> Tuple[int, int]:
    """``whole_suite`` spread over ``jobs`` independent copies of the tree.

    **Threads, not processes.** Every entry's real work happens inside a
    ``subprocess.run`` of ``run_checks.py``, so the interpreter lock is
    released for its whole duration and the parent only does file I/O.
    A process pool bought nothing here and brought its own failure class:
    the earlier attempt died with ``BrokenPipeError`` in every worker at
    once, which profiling traced to the DRIVER dying rather than to
    anything the workers returned.

    **One copy per worker, never a shared one.** ``whole_suite`` mutates
    the tree in place and restores it in a ``finally``. Two workers in one
    tree would let one entry's mutation be scored against another entry's
    run — the exact defect ``_clear_pycache`` exists to prevent, but
    across workers instead of across iterations.

    **A worker that dies is not a worker that passed.** Its unreached
    entries are counted as failures and named, because a sweep that
    silently covers less than it claims is worse than a slow one.

    **Every copy is checked pristine before it is deleted**, so the
    guarantee ``main`` makes over ``repo`` — that no entry left the tree
    mutated — still holds over the copies the caller never sees.
    """
    entries = list(WHOLE_SUITE if entries is None else entries)
    if jobs is None:
        jobs = max(1, min(8, (os.cpu_count() or 2) - 2))
    if jobs <= 1 or len(entries) <= 1:
        return whole_suite(repo, entries, touched)
    jobs = min(jobs, len(entries))

    # Round-robin, not contiguous blocks: the expensive entries are the ones
    # that mutate a solver file (they miss the memo cache and recompute for
    # real), and they sit next to each other in WHOLE_SUITE. A contiguous
    # split would hand one worker all of them.
    slices = [entries[i::jobs] for i in range(jobs)]

    # **Warm the solver memo ONCE, on the pristine tree, before fanning out.**
    # Measured: four cold workers took 113s each (2.57x over serial) because
    # none of them had written the cache entry yet, so all four recomputed
    # the SAME drape simultaneously — a cache stampede. The one worker that
    # happened to start warm finished the identical work in 23.5s. Since 31
    # of the 32 entries never touch a solver file, one unmutated run fills
    # the cache every later worker will hit.
    #
    # It runs the suite on an UNMUTATED tree, so it must come back clean; if
    # it does not, every verdict below would be scored against a broken
    # baseline and is worth nothing. That is reported, not swallowed.
    warm = _RUN_SUITE[0](repo)
    if warm.returncode != 0:
        print("  MISS  the pristine tree does not pass its own suite — "
              f"exit {warm.returncode}. Every verdict below would be "
              "scored against a broken baseline.")
        return len(entries), 0

    base = Path(tempfile.mkdtemp(prefix="mutate_par_"))
    trees: List[Path] = [repo]
    try:
        for k in range(1, jobs):
            d = base / f"repo{k}"
            shutil.copytree(repo, d, ignore=_COPY_IGNORE)
            trees.append(d)

        bufs = [io.StringIO() for _ in range(jobs)]
        marks: List[set] = [set() for _ in range(jobs)]
        got: List[Optional[Tuple[int, int]]] = [None] * jobs
        errs: Dict[int, BaseException] = {}

        def work(k: int) -> None:
            got[k] = whole_suite(trees[k], slices[k], marks[k], bufs[k])

        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
            futs = {ex.submit(work, k): k for k in range(jobs)}
            for fut in concurrent.futures.as_completed(futs):
                k = futs[fut]
                try:
                    fut.result()
                except BaseException as exc:                # noqa: BLE001
                    errs[k] = exc

        bad = ran = 0
        for k in range(jobs):
            print(bufs[k].getvalue(), end="")
            b, r = got[k] if got[k] else (0, 0)
            if k in errs:
                lost = len(slices[k]) - r
                print(f"  MISS  worker {k} DIED "
                      f"{type(errs[k]).__name__}: {errs[k]} — {lost} "
                      f"entr{'y' if lost == 1 else 'ies'} never ran")
                b += lost
            bad += b
            ran += r
            if touched is not None:
                touched |= marks[k]
            # the copy the caller will never see, checked before it goes
            left = sorted(rel for rel in marks[k]
                          if (trees[k] / rel).read_text(encoding="utf-8")
                          != (SRC / rel).read_text(encoding="utf-8"))
            if left:
                print(f"  MISS  worker {k} LEFT ITS COPY MUTATED: {left}")
                bad += len(left)
        return bad, ran
    finally:
        shutil.rmtree(base, ignore_errors=True)


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
         loop: Optional[Sequence[Any]] = None,
         jobs: Optional[int] = None) -> int:
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
        shutil.copytree(SRC, base / "repo", ignore=_COPY_IGNORE)
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
        wbad, wran = whole_suite_parallel(repo, whole, touched, jobs=jobs)
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

#: --- 裾の形は境界全体から (structure.py) ------------------------------------
#: 反証役が見つけた穴を塞ぐ三本。`_hem` は入力を一切見ない定数関数に
#: 差し替えても全検査が緑のままだった — 出力を読む検査が、いつも同じ
#: 前後帰属の断りしか見ていなかったため。
WHOLE_SUITE += [
    ("the hem is classified from its two ends instead of the whole "
     "boundary", "photoloset/structure.py",
     [("    if hem_range_norm < HEM_LEVEL_THRESHOLD_NORM:",
       "    if abs(diff_norm) < HEM_LEVEL_THRESHOLD_NORM:")],
     ["the hem's shape is read off the whole bottom boundary, not off its two ends, and each of level / asymmetric_left_right / uneven is reachable from an outline that earns it"]),

    ("the left-right difference loses its sign", "photoloset/structure.py",
     [('        "left_right_diff_norm": round(diff_norm, 5),',
       '        "left_right_diff_norm": round(abs(diff_norm), 5),')],
     ["the hem's shape is read off the whole bottom boundary, not off its two ends, and each of level / asymmetric_left_right / uneven is reachable from an outline that earns it"]),

    ("a tilt and a wave swap names", "photoloset/structure.py",
     [('        shape = "asymmetric_left_right" if sign_changes == 0 '
       'else "uneven"',
       '        shape = "uneven" if sign_changes == 0 '
       'else "asymmetric_left_right"')],
     ["the hem's shape is read off the whole bottom boundary, not off its two ends, and each of level / asymmetric_left_right / uneven is reachable from an outline that earns it"]),
]


#: --- 実行部より下に置かれた変異は走らない -----------------------------------
WHOLE_SUITE += [
    ("a mutation table is written below the line that starts the run",
     "tests/falsifiers.py",
     # **探索文字列をここで分割して書く。** そのまま書くと、この表の
     # 中に現れた一本目にも当たってしまい、置換が実行部ではなく自分の
     # エントリの中で起きる。隣り合う文字列リテラルは取り込み時に一本に
     # なるので値は同じ、ソースには連続して現れない。
     [("    raise SystemExit(main(" "jobs=_jobs))",
       "    raise SystemExit(main(" "jobs=_jobs))\n\nWHOLE_SUITE += []")],
     ['no falsifier is defined below the line where the harness starts running, because one defined there is silently skipped']),
]


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        raise SystemExit(self_test())
    # --jobs N spreads the whole-suite phase over N copies of the tree.
    # --jobs 1 is the serial path this replaced, kept so the two can be
    # compared on the same entries rather than trusted to agree.
    _jobs = None
    for _i, _a in enumerate(sys.argv[1:]):
        if _a == "--jobs" and _i + 2 <= len(sys.argv[1:]):
            _jobs = int(sys.argv[_i + 2])
        elif _a.startswith("--jobs="):
            _jobs = int(_a.split("=", 1)[1])
    raise SystemExit(main(jobs=_jobs))
