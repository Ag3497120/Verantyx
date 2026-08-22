"""Build the mathlib sovereign, with kernel-checked witness facets.

Core = fully qualified theorem name, facets = statement identifier
tokens (the sound index measured in tools/measure_mathlib.py). On top,
the witness: a deterministic stride of source FILES is re-verified by
the kernel (`lake env lean <file>`, build cache supplying the imports),
and every theorem of a file the kernel accepts gains the facet
`verified:lean4:<version>`. Theorems of unverified files carry NO
witness facet — absence is the honest state, never a judgment.

This is the Lean-witness discipline at store scale: the downloaded
build cache is a convenience, not a citation; the facet is only put
where THIS machine's kernel actually ran. Widening the verified share
is a matter of compute, not design — rerun with a wider stride.

The store is saved to vera-corpus/build/mathlib_store.json — a
separate math sovereign, never pooled with the federation (the
abstract-noun warning stands).

## Measured — first run, 30-file stride

    77,242 theorems / 75,171 cores extracted in 4s
    30/30 files kernel-verified, 1.0-3.0s each (cache supplying
    imports), 442 theorems witnessed, 59.8s end to end

At that rate the whole library is ~2 hours of compute — the verified
share is a dial, not a design question.

## Measured — full run (argv 0), 2026-08-14, across three launches

    6,502 / 6,577 candidate files kernel-verified (98.9%)
    75 files FAIL (Analysis 30, MeasureTheory 6, LinearAlgebra 6,
    Algebra 5, ... — seconds-scale failures, environment/import
    shaped, not timeouts)
    75,919 / 77,242 theorems carry verified:lean4:4.34.0-rc1
    ~4.6h of kernel compute wall-clock, ended 20:26 JST

The run died twice (system sleep at 17:51; parent-shell teardown at
18:08) and finished on resume-from-log: ok lines are this machine's
kernel testimony and re-earn the facet without re-running. The store
holds the largest kernel-verified witness layer in the project.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.cross_store import CrossStore
from verantyx.lean_witness import lean_binary, witness_facet

ROOT = Path.home() / "Projects" / "vera-corpus"
MATHLIB = ROOT / "corpora" / "mathlib4"
OUT = ROOT / "build" / "mathlib_store.json"
#: Stride sample size; pass an integer argv[1] to widen (0 = all files).
N_VERIFY_FILES = int(sys.argv[1]) if len(sys.argv) > 1 else 30
#: Optional prior-run log (argv[2]); ok/FAIL lines are resumed, not re-run.
RESUME_LOG = Path(sys.argv[2]) if len(sys.argv) > 2 else None
TIMEOUT_S = 240
CHECKPOINT_EVERY = 200

DECL = re.compile(
    r"^(?:@\[[^\]]*\]\s*)?(?:protected\s+|private\s+|noncomputable\s+)*"
    r"(?:theorem|lemma)\s+([A-Za-z0-9_.'\u00ab\u00bb]+)")
NS_OPEN = re.compile(r"^namespace\s+([A-Za-z0-9_.']+)")
NS_CLOSE = re.compile(r"^end(\s+([A-Za-z0-9_.']+))?\s*$")
IDENT = re.compile(r"[A-Za-z][A-Za-z0-9_']+")
STOP = {"fun", "let", "have", "show", "with", "this", "by", "of", "and",
        "or", "not", "if", "then", "else", "the", "in", "to", "at"}


def theorems_of(path: Path):
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    stack = []
    i = 0
    while i < len(lines):
        ns = NS_OPEN.match(lines[i])
        if ns:
            stack.append(ns.group(1))
            i += 1
            continue
        if stack:
            closed = NS_CLOSE.match(lines[i])
            if closed and closed.group(2) == stack[-1]:
                stack.pop()
                i += 1
                continue
        m = DECL.match(lines[i])
        if not m:
            i += 1
            continue
        name = ".".join(stack + [m.group(1)])
        block = lines[i][m.end():]
        j = i + 1
        while ":=" not in block and j < len(lines) and j - i < 6:
            block += " " + lines[j]
            j += 1
        stmt = block.split(":=")[0]
        toks = sorted({t for t in IDENT.findall(stmt)
                       if len(t) >= 2 and t not in STOP})
        name_parts = {p for p in re.split(r"[._']", m.group(1)) if p}
        toks = [t for t in toks if t not in name_parts]
        if len(toks) >= 3:
            yield name, toks
        i = j if j > i + 1 else i + 1


def parse_witness_log(log_path: Path):
    """Read prior `ok  ` / `FAIL ` lines into relative-path sets."""
    ok_rels = set()
    fail_rels = set()
    for raw in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw.startswith("ok  "):
            rest, kind = raw[4:], "ok"
        elif raw.startswith("FAIL "):
            rest, kind = raw[5:], "fail"
        else:
            continue
        rel, _, tail = rest.rpartition(" ")
        if not rel or not tail.endswith("s"):
            continue
        if kind == "ok":
            ok_rels.add(rel)
            fail_rels.discard(rel)
        else:
            fail_rels.add(rel)
            ok_rels.discard(rel)
    return ok_rels, fail_rels


t0 = time.time()
files = sorted((MATHLIB / "Mathlib").rglob("*.lean"))
store = CrossStore()
by_file = {}
for path in files:
    names = []
    for name, toks in theorems_of(path):
        store.add(name, toks, source=str(path.relative_to(MATHLIB)))
        names.append(name.casefold())
    if names:
        by_file[path] = names
print("files: %d  theorems: %d  cores: %d  extract %.1fs"
      % (len(files), sum(len(v) for v in by_file.values()),
         len(store.crosses), time.time() - t0), flush=True)

binary = lean_binary()
version = subprocess.run([binary, "--version"], capture_output=True,
                         text=True).stdout.strip()
facet = witness_facet(version)
print("witness facet:", facet, flush=True)

candidates = sorted(by_file)
if N_VERIFY_FILES <= 0:
    sample = candidates
else:
    stride = max(1, len(candidates) // N_VERIFY_FILES)
    sample = candidates[::stride][:N_VERIFY_FILES]

verified_files = failed_files = witnessed = 0
resumed_ok = resumed_fail = 0
failures = []
ok_rels = fail_rels = set()
if RESUME_LOG is not None:
    ok_rels, fail_rels = parse_witness_log(RESUME_LOG)
    for path in sample:
        rel = str(path.relative_to(MATHLIB))
        if rel in ok_rels:
            verified_files += 1
            resumed_ok += 1
            for name in by_file[path]:
                store.add(name, [facet])
                witnessed += 1
        elif rel in fail_rels:
            failed_files += 1
            resumed_fail += 1
            failures.append({"file": rel, "why": "from log"})
    to_run = [p for p in sample
              if str(p.relative_to(MATHLIB)) not in ok_rels
              and str(p.relative_to(MATHLIB)) not in fail_rels]
    print("resumed: %d ok + %d FAIL from log, %d to verify"
          % (resumed_ok, resumed_fail, len(to_run)), flush=True)
else:
    to_run = sample

newly_done = 0
for path in to_run:
    t1 = time.time()
    try:
        run = subprocess.run(
            [str(Path.home() / ".elan" / "bin" / "lake"), "env", "lean",
             str(path)],
            cwd=MATHLIB, capture_output=True, text=True, timeout=TIMEOUT_S)
        ok = run.returncode == 0
    except subprocess.TimeoutExpired:
        ok = False
        run = None
    rel = str(path.relative_to(MATHLIB))
    if ok:
        verified_files += 1
        for name in by_file[path]:
            store.add(name, [facet])
            witnessed += 1
    else:
        failed_files += 1
        failures.append({"file": rel,
                         "why": "timeout" if run is None else
                         (run.stdout + run.stderr).strip()[:120]})
    print("%s %s %.1fs" % ("ok " if ok else "FAIL", rel, time.time() - t1),
          flush=True)
    newly_done += 1
    if newly_done % CHECKPOINT_EVERY == 0:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        store.save(OUT)
        print("checkpoint: %d files done" % newly_done, flush=True)

OUT.parent.mkdir(parents=True, exist_ok=True)
store.save(OUT)
print(json.dumps({
    "theorems": sum(len(v) for v in by_file.values()),
    "cores": len(store.crosses),
    "files_verified": verified_files, "files_failed": failed_files,
    "witnessed_theorems": witnessed,
    "resumed_ok": resumed_ok,
    "resumed_fail": resumed_fail,
    "failures": failures[:5],
    "store": str(OUT),
    "seconds": round(time.time() - t0, 1),
}, ensure_ascii=False, indent=1))
