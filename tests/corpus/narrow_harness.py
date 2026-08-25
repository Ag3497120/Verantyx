# -*- coding: utf-8 -*-
"""The same harness with the guard NARROWED — the shape T8 must REJECT.

``except ValueError`` reads as a guard to a detector that only asks whether a
``try`` is present, and restores the exact defect T8 exists to find: a
TimeoutExpired, a FileNotFoundError or a KeyError ends the sweep at entry N,
and every number the harness prints then describes a prefix presented as the
whole. The restore is out of ``finally`` here too, so the tree stays mutated.
"""
MUTATIONS = [
    ("a zone disappears", "mini/store.py", '"zone:2": "hem"',
     '"zone:2": "HEM"', ["H-tracks-the-store"]),
    ("an entry whose anchor is not there", "mini/store.py",
     "no such text in the file", "x", ["H-tracks-the-store"]),
    ("an entry that expects a check nobody wrote", "mini/store.py",
     '"label": "mini coat"', '"label": "moved"', ["no such check"]),
]


def run(repo):
    return {"failed": []}


def main(mutations=None):
    mutations = list(MUTATIONS if mutations is None else mutations)
    bad = 0
    ran = 0
    for name, rel, find, repl, expect in mutations:
        ran += 1
        try:
            orig = path(rel).read_text()
            path(rel).write_text(orig.replace(find, repl, 1))
            got = run(rel)
            if expect != got["failed"]:
                bad += 1
        except ValueError as exc:                           # noqa: BLE001
            bad += 1
            print(f"  MISS  {name}: {exc}")
        path(rel).write_text(orig)
    print(f"ran {ran} of {len(mutations)} entries")
    return 1 if bad else 0


def path(rel):
    from pathlib import Path
    return Path(rel)
