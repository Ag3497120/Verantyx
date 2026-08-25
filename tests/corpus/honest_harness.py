# -*- coding: utf-8 -*-
"""A mutation harness that reports every entry — the shape T8 must ACCEPT.

BaseException is caught so one raise is that ENTRY going miss; KeyboardInterrupt
and SystemExit are re-raised so the operator keeps control; and the restore
sits in ``finally`` so the next entry is scored against a clean tree.
"""
MUTATIONS = [
    ("a zone disappears", "mini/store.py", '"zone:2": "hem"',
     '"zone:2": "HEM"', ["H-tracks-the-store"]),
]


def run(repo):
    return {"failed": []}


def main(mutations=None):
    mutations = list(MUTATIONS if mutations is None else mutations)
    bad = 0
    ran = 0
    for name, rel, find, repl, expect in mutations:
        orig = None
        ran += 1
        try:
            orig = path(rel).read_text()
            path(rel).write_text(orig.replace(find, repl, 1))
            got = run(rel)
            if expect != got["failed"]:
                bad += 1
        except BaseException as exc:                        # noqa: BLE001
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            bad += 1
            print(f"  MISS  {name}: HARNESS RAISED {exc}")
        finally:
            if orig is not None:
                path(rel).write_text(orig)
    print(f"ran {ran} of {len(mutations)} entries")
    return 1 if bad else 0


def path(rel):
    from pathlib import Path
    return Path(rel)
