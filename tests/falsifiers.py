# -*- coding: utf-8 -*-
"""Falsifier harness — **can each check actually fail?**

    python3 tests/falsifiers.py

A check that cannot fail is not a check, and this project shipped FIVE of
those before anyone noticed:

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
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent

RUNNER = '''
import sys, io, contextlib
sys.path.insert(0, ".")
import tests.run_checks as rc
FNS = (rc.the_block_lives_on_the_cross, rc.the_arms_carry_meaning,
       rc.the_cross_refuses_what_it_should)
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
'''

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

    ("#5 the quarantine core is exempt from the capacity law",
     "photoloset/cross.py",
     '        if arm is None and self._quarantine_load(core) '
     '>= CAPACITY_PER_CORE:',
     '        if False:',
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
                 guard_crash: list = ()) -> None:
        self.reported = reported
        self.failed = failed
        self.crashed = crashed
        self.note = note
        self.declared = list(declared)
        self.never_ran = list(never_ran)
        self.guard_crash = list(guard_crash)


def run(tmp: Path) -> Run:
    r = subprocess.run([sys.executable, "-c", RUNNER], cwd=tmp,
                       capture_output=True, text=True, timeout=900)
    got = {}
    for marker in ("DECLARED", "NEVERRAN", "GUARDCRASH", "REPORTED",
                   "CRASHED", "FAILED"):
        m = re.search(r"::%s::(\[.*\])" % marker, r.stdout)
        if not m:
            return Run([], [], [],
                       note=f"<<no {marker} marker>> "
                            f"{r.stdout[-300:]} {r.stderr[-300:]}")
        got[marker] = eval(m.group(1))
    return Run(got["REPORTED"], got["FAILED"], got["CRASHED"],
               declared=got["DECLARED"], never_ran=got["NEVERRAN"],
               guard_crash=got["GUARDCRASH"])


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
]


def whole_suite(repo: Path) -> int:
    """Run ``run_checks.py`` end to end under a mutation and read its exit.

    This is the falsifier for the pinned NAME SET: the failure it exists for
    is a check DISAPPEARING, which by construction cannot be observed by
    running only the functions that still declare it.
    """
    bad = 0
    for name, rel, edits, expect in WHOLE_SUITE:
        p = repo / rel
        orig = p.read_text(encoding="utf-8")
        body = orig
        missing = [f for f, _r in edits if f not in body]
        if missing:
            print(f"  SKIP  {name}: anchor not found in {rel}")
            bad += 1
            continue
        for find, repl in edits:
            body = body.replace(find, repl, 1)
        p.write_text(body, encoding="utf-8")
        for c in repo.rglob("__pycache__"):
            shutil.rmtree(c, ignore_errors=True)
        r = subprocess.run([sys.executable, "tests/run_checks.py"], cwd=repo,
                           capture_output=True, text=True, timeout=1800)
        p.write_text(orig, encoding="utf-8")
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
    for c in repo.rglob("__pycache__"):
        shutil.rmtree(c, ignore_errors=True)
    return bad


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="mutate_"))
    shutil.copytree(SRC, base / "repo",
                    ignore=shutil.ignore_patterns(".git", "__pycache__"))
    repo = base / "repo"
    clean = run(repo)
    print(f"unmutated: {len(clean.reported)} cross checks reported, "
          f"{len(clean.failed)} failing, {len(clean.crashed)} crashed "
          f"-> {clean.failed or clean.note or 'clean'}")
    if clean.crashed:
        print(f"  BASELINE CRASHED: {clean.crashed}")
    # The pinned set is what the FUNCTIONS declare, not what a clean run
    # happened to print. Pinning the observed output would let a mutation
    # that suppresses a check agree with a baseline that also suppressed it.
    baseline = list(clean.declared)
    drift = ([n for n in baseline if n not in clean.reported]
             + [n for n in clean.reported if n not in baseline])
    print(f"pinned name set: {len(baseline)} declared names"
          + (f" — DECLARATION DRIFT: {drift}" if drift else "") + "\n")
    if drift:
        return 1
    bad = 0
    for name, rel, find, repl, expect in MUTATIONS:
        p = repo / rel
        orig = p.read_text(encoding="utf-8")
        if find not in orig:
            print(f"  SKIP  {name}: anchor not found in {rel}")
            bad += 1
            continue
        p.write_text(orig.replace(find, repl, 1), encoding="utf-8")
        for c in repo.rglob("__pycache__"):
            shutil.rmtree(c, ignore_errors=True)
        got = run(repo)
        p.write_text(orig, encoding="utf-8")
        # A hit is the NAMED check going red HAVING RUN. Three things that
        # look like evidence and are not:
        #   - a bare function crash, which used to be scraped into the failed
        #     list and stand in for the check it aborted before it;
        #   - a NEVER RAN line, which is red because nothing was measured;
        #   - a line that vanished from the output entirely.
        # All three are misses. Only a check that reached its own assertion
        # and rejected the store proves the property is pinned.
        hit = [e for e in expect if e in got.failed and e not in got.never_ran]
        missing = [n for n in baseline if n not in got.reported]
        ok = (len(hit) == len(expect) and not got.crashed and not missing
              and not got.never_ran and not got.note)
        if not ok:
            bad += 1
        print(f"  {'RED ' if ok else 'MISS'}  {name}")
        print(f"        expected red: {expect}")
        print(f"        actually red: {[f for f in got.failed if f not in got.never_ran]}")
        if got.guard_crash:
            print(f"        red by raising in its own setup: {got.guard_crash}")
        if got.crashed:
            print(f"        CRASHED OUT OF section() — the harness itself is "
                  f"unreliable here: {got.crashed}")
        if got.never_ran:
            print(f"        NEVER RAN, so measured nothing (a miss, not a "
                  f"hit) ({len(got.never_ran)}): {got.never_ran}")
        if missing:
            print(f"        NEVER REPORTED ({len(missing)}): {missing}")
        if got.note:
            print(f"        harness note: {got.note}")
    for c in repo.rglob("__pycache__"):
        shutil.rmtree(c, ignore_errors=True)
    print(f"\n{len(MUTATIONS) - bad}/{len(MUTATIONS)} cross mutations produced "
          f"the expected failures with no check going unreported")
    print("\nand one that needs the whole suite:")
    wbad = whole_suite(repo)
    print(f"\n{len(WHOLE_SUITE) - wbad}/{len(WHOLE_SUITE)} whole-suite "
          f"mutations produced the expected failures")
    total = len(MUTATIONS) + len(WHOLE_SUITE)
    print(f"{total - bad - wbad}/{total} mutations red overall")
    shutil.rmtree(base, ignore_errors=True)
    return 1 if (bad or wbad or clean.failed or clean.crashed
                 or clean.never_ran) else 0


if __name__ == "__main__":
    raise SystemExit(main())
