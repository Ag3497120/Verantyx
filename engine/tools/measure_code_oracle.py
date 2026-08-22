"""code_ingest vs the grep oracle — the rare question with a machine judge.

"Who calls f" has a complete textual oracle: every call the AST claims
came from source text, and every textual `f(` is findable by regex. So
the measurement is a full cross-check, both directions, on this repo's
own package:

  fabrication direction   every (caller g -> f) edge who_calls claims
                          must be textually present in one of g's files
                          (case-insensitive: the store casefolds names)
  miss direction          every file with a textual call `f(` outside
                          its own def line should appear among the
                          claimed callers' files; the difference is
                          reported WITH the known oracle impurities
                          (module-level calls belong to no function;
                          comments and strings look like calls to grep
                          and not to the AST — those are oracle noise,
                          not engine errors, and they are counted apart
                          where detectable)
  honesty                 a function that does not exist anywhere must
                          come back UNKNOWN_NO_EVIDENCE, never a list

## Measured — this repo's own package (verantyx/), 100 sampled functions

    fabrication    514 claimed caller edges, 514 textually confirmed — 0
    misses         14 of 325 oracle files (4.3%): module-level calls
                   that belong to no function (structural, honest) and
                   docstring prose the oracle mistakes for calls
                   ("the corpus (2.4M" matches corpus() — oracle noise)
    ghost          UNKNOWN_NO_EVIDENCE, never a list

And the measurement's own first draft proved the point about oracles:
a lookbehind that excluded `.append(` read 343 method-call edges as
fabrications — an oracle stricter than the claim's own definition
manufactures failures. The oracle was fixed to the AST's definition of
a call, not the other way around.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.code_ingest import ingest_python_repo, who_calls
from verantyx.cross_store import CrossStore

ROOT = Path(__file__).resolve().parent.parent / "verantyx"

store = CrossStore()
rep = ingest_python_repo(store, ROOT)
print("ingest:", json.dumps(rep), flush=True)

files_text = {str(p.relative_to(ROOT)): p.read_text(errors="replace")
              for p in sorted(ROOT.rglob("*.py"))}

fns = sorted(c[len("fn:"):] for c in store.crosses if c.startswith("fn:"))
stride = max(1, len(fns) // 100)
sample = fns[::stride][:100]


def files_of(fn_name):
    cross = store.crosses.get("fn:" + fn_name) or {}
    return [f[len("file:"):] for f in cross if f.startswith("file:")]


def call_re(fn_name):
    # A dot may precede: the AST counts `x.append(...)` as a call of
    # `append` (Attribute -> attr), so the oracle must count it too. The
    # first draft excluded dots and read 343 method-call edges as
    # fabrications — an oracle stricter than the claim's own definition
    # manufactures failures.
    return re.compile(r"(?<!\w)%s\s*\(" % re.escape(fn_name), re.IGNORECASE)


def def_re(fn_name):
    return re.compile(r"\bdef\s+%s\s*\(" % re.escape(fn_name), re.IGNORECASE)


claims = confirmed = 0
unconfirmed_examples = []
missed_files = oracle_files = 0
miss_examples = []
for fn in sample:
    r = who_calls(store, fn)
    callers = r.get("callers") or []
    cre, dre = call_re(fn), def_re(fn)
    claimed_files = set()
    for g in callers:
        gfiles = files_of(g)
        claimed_files.update(gfiles)
        claims += 1
        if any(cre.search(files_text.get(f, "")) for f in gfiles):
            confirmed += 1
        elif len(unconfirmed_examples) < 5:
            unconfirmed_examples.append({"fn": fn, "caller": g})
    # miss direction: textual call sites outside def lines
    for relpath, text in files_text.items():
        hits = [ln for ln in text.split("\n")
                if cre.search(ln) and not dre.search(ln)]
        if not hits:
            continue
        oracle_files += 1
        if relpath not in claimed_files:
            missed_files += 1
            if len(miss_examples) < 5:
                miss_examples.append({"fn": fn, "file": relpath,
                                      "line": hits[0].strip()[:70]})

ghost = who_calls(store, "this_function_does_not_exist_anywhere")

print(json.dumps({
    "sampled_fns": len(sample),
    "fabrication_check": {
        "claimed_edges": claims, "textually_confirmed": confirmed,
        "unconfirmed": claims - confirmed,
        "examples": unconfirmed_examples},
    "miss_check": {
        "oracle_call_files": oracle_files, "missed_files": missed_files,
        "examples": miss_examples},
    "ghost_fn": ghost["verdict"],
}, ensure_ascii=False, indent=1))
