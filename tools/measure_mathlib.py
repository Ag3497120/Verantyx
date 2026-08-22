"""mathlib as cores: does statement->theorem retrieval hold at scale?

The first step of the Lean-witness plan is a measurement, not a design:
ingest mathlib4's named theorems (core = fully qualified name, facets =
identifier tokens of the statement) into a FRESH store — a separate
math sovereign, never pooled with the federation — and ask whether a
theorem's own statement identifies it uniquely, the way statute
headings identified statutes (300/300 there).

Bank: 300 theorems by deterministic stride. A query is the statement's
distinct identifier tokens (name segments excluded — asking with the
answer's own name would test nothing). Retrieval is condition
intersection (Puzzle semantics): the cores holding every query token.

    unique survivor == the theorem   hit
    survivors include it, tied       ambiguous (reported, not scored)
    it is absent / no survivor       miss

Fabrication probe: 20 statements assembled from token pairs of
theorems in DIFFERENT top-level areas (Algebra x Topology etc.); the
right answer is no unique survivor.

## Measured — mathlib4 @ depth-1 clone, 2026-08-14

    identifiers only (77,242 thms, 67,206 cores)
        unique 154/300   ambiguous 146   missing 0
        fabricated: 20/20 refused
    identifiers, full-statement queries          unique 157/300
    + symbol tokens (126,351 thms, 105,141 cores)
        unique 139/300   ambiguous 161   missing 0
        fabricated: 20/20 refused

Three readings. The flat bag is a SOUND INDEX at 10^5 scale: the
statement always finds its theorem among the survivors (missing 0) and
a cross-area fabrication never finds a unique one (0/40 across both
runs). The flat bag is NOT an identifier: uniqueness saturates near
50% whichever tokens ride, because mathlib's near-variants (the same
lemma over Group/Monoid/Ring) share their whole identifier vocabulary
— the discriminator is the TERM STRUCTURE, which is exactly the
representation `rewrite_kernel` holds and a facet bag erases. So the
Lean-witness plan's layer split is measured, not aesthetic: the store
indexes and witnesses (candidate generation, ties abstain), and
identity lives in the formal term.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.cross_store import CrossStore

MATHLIB = Path.home() / "Projects" / "vera-corpus" / "corpora" / "mathlib4" / "Mathlib"

DECL = re.compile(
    r"^(?:@\[[^\]]*\]\s*)?(?:protected\s+|private\s+|noncomputable\s+)*"
    r"(?:theorem|lemma)\s+([A-Za-z0-9_.'\u00ab\u00bb]+)")
IDENT = re.compile(r"[A-Za-z][A-Za-z0-9_']+")
#: The symbolic operators are most of a mathematical statement's
#: identity; an identifier-only bag erases them. Each symbol is its own
#: token.
SYMBOL = re.compile(r"[\u2200-\u22ff\u27e8\u27e9\u2190-\u21ff\u00ac\u00b1"
                    r"\u00d7\u00f7\u2032\u207b\u00b9\u2080-\u2089]")

STOP = {"fun", "let", "have", "show", "with", "this", "by", "of", "and",
        "or", "not", "if", "then", "else", "the", "in", "to", "at"}


def statements():
    for path in sorted(MATHLIB.rglob("*.lean")):
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        i = 0
        while i < len(lines):
            m = DECL.match(lines[i])
            if not m:
                i += 1
                continue
            name = m.group(1)
            block = lines[i][m.end():]
            j = i + 1
            while ":=" not in block and j < len(lines) and j - i < 6:
                block += " " + lines[j]
                j += 1
            stmt = block.split(":=")[0]
            toks = sorted({t for t in IDENT.findall(stmt)
                           if len(t) >= 2 and t not in STOP}
                          | set(SYMBOL.findall(stmt)))
            name_parts = {p for p in re.split(r"[._']", name) if p}
            toks = [t for t in toks if t not in name_parts]
            if len(toks) >= 3:
                yield name, toks
            i = j if j > i + 1 else i + 1


store = CrossStore()
area_of = {}
n = 0
for name, toks in statements():
    store.add(name, toks)
    area_of[name.casefold()] = None
    n += 1
print("theorems ingested:", n, "| cores:", len(store.crosses), flush=True)

cores = sorted(store.crosses)
stride = max(1, len(cores) // 300)
bank = cores[::stride][:300]


def holders(term):
    return {c for c, cross in store.crosses.items() if term in (cross or ())}


hits = ambiguous = missing = 0
miss_examples = []
for name in bank:
    toks = sorted(store.crosses[name])
    cand = None
    for t in toks:
        got = holders(t) | ({t} if t in store.crosses else set())
        cand = got if cand is None else (cand & got)
        if not cand:
            break
    cand = cand or set()
    if cand == {name}:
        hits += 1
    elif name in cand:
        ambiguous += 1
    else:
        missing += 1
        if len(miss_examples) < 5:
            miss_examples.append(name)

# Fabricated statements: half the tokens from an Algebra theorem, half
# from a Topology one — no theorem states this.
alg = [c for c in cores if c.startswith(("mul_", "add_", "algebra"))][:40]
top = [c for c in cores if "continuous" in c or "topology" in c][:40]
fab_refused = fab_answered = 0
for i in range(min(20, len(alg), len(top))):
    toks = sorted(store.crosses[alg[i]])[:4] + sorted(store.crosses[top[i]])[:4]
    cand = None
    for t in toks:
        got = holders(t)
        cand = got if cand is None else (cand & got)
        if not cand:
            break
    if cand and len(cand) == 1:
        fab_answered += 1
    else:
        fab_refused += 1

print(json.dumps({
    "bank": len(bank), "unique_hit": hits, "ambiguous": ambiguous,
    "missing": missing, "miss_examples": miss_examples,
    "fabricated": {"refused": fab_refused, "answered": fab_answered},
}, ensure_ascii=False, indent=1))
