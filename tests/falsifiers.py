# -*- coding: utf-8 -*-
"""Falsifier harness — **can each check actually fail?**

    python3 tests/falsifiers.py

A check that cannot fail is not a check, and this project shipped two of
those before anyone noticed (``placement_check`` read one unmutated store
twice; ``coat fills its root node exactly`` only held while the arms were
storage drawers). Both survived a first review because nobody built the
store that violates the property.

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
out = io.StringIO()
try:
    with contextlib.redirect_stdout(out):
        for fn in (rc.the_block_lives_on_the_cross, rc.the_arms_carry_meaning,
                   rc.the_cross_refuses_what_it_should):
            try:
                fn()
            except Exception as e:
                print(f"  FAIL  {fn.__name__:34} CRASHED {type(e).__name__}: {e}")
finally:
    txt = out.getvalue()
failed = [l.split("FAIL")[1].strip()[:40].strip() for l in txt.splitlines() if l.strip().startswith("FAIL")]
print("::FAILED::" + repr(failed))
'''

# (name, file, find, replace, checks we expect to go red)
MUTATIONS = [
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
     '        vals = [h["value"] for h in hits]\n'
     '        if any(v != vals[0] for v in vals[1:]):',
     '        vals = [h["value"] for h in hits]\n'
     '        if False:',
     ["param refuses across subjects"]),
]


def run(tmp: Path) -> list:
    r = subprocess.run([sys.executable, "-c", RUNNER], cwd=tmp,
                       capture_output=True, text=True, timeout=900)
    m = re.search(r"::FAILED::(\[.*\])", r.stdout)
    if not m:
        return ["<<no marker>>", r.stdout[-500:], r.stderr[-500:]]
    return eval(m.group(1))


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="mutate_"))
    shutil.copytree(SRC, base / "repo",
                    ignore=shutil.ignore_patterns(".git", "__pycache__"))
    repo = base / "repo"
    clean = run(repo)
    print(f"unmutated: {len(clean)} failing -> {clean}\n")
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
        hit = [e for e in expect
               if any(g.startswith(e[:38]) or e.startswith(g[:38])
                      for g in got)]
        ok = len(hit) == len(expect)
        if not ok:
            bad += 1
        print(f"  {'RED ' if ok else 'MISS'}  {name}")
        print(f"        expected red: {expect}")
        print(f"        actually red: {got}")
    for c in repo.rglob("__pycache__"):
        shutil.rmtree(c, ignore_errors=True)
    print(f"\n{len(MUTATIONS) - bad}/{len(MUTATIONS)} mutations produced the "
          f"expected failures")
    shutil.rmtree(base, ignore_errors=True)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
