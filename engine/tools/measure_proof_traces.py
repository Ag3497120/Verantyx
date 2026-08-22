"""Do goal shapes select tactics? The selection-restriction operation,
run over mathlib's proof traces.

The writer's selection restrictions were learned as (slot, word)
attestations: what the corpus actually put where. The math analogue is
(goal shape, tactic): what tactic mathlib's authors actually opened
proofs of this shape with. No elaboration — the shape is the cheap
textual signature of the STATEMENT (which relation/binder markers it
carries), and the tactic is the first step of a `by` proof.

Protocol: every theorem with an extractable `by` proof; deterministic
stride holds out 300 as the test bank; the rest train a majority table
shape -> first tactic, TIES ABSTAIN (a majority of one vote either way
is an accident, and every other organ here abstains on ties). Score
against the global-majority baseline (always guess the corpus's most
common opening tactic). An unseen shape abstains.

Both numbers ride: accuracy among answered, and abstention rate —
abstaining is load-bearing, not failure.

## Measured — mathlib4 depth-1, 88,575 proofs, 152 first tactics

    global majority (rw)                    0.253
    coarse shape (relation markers)         0.257   296 answered / 4 abst.
    fine shape (head constant + markers)    0.290   214 answered / 86 abst.
                                            table 18,940 shapes

The coarse cut carries nothing: rw is the majority opening for every
large shape, because mathlib is dominated by bare-equation lemmas whose
textual shape says only "eq". The fine cut lifts weakly (+15% relative
at 71% coverage) — real signal, saturating fast, same curve the
statement-identity measurement drew: textual proxies carry the first
half, and the discriminating context (here the elaborated goal state,
there the variable environment) belongs to the toolchain. The trace
corpus itself is the asset: 88k (shape, opening-tactic) attestations
extracted in seconds, waiting for a goal representation worth
conditioning on.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MATHLIB = Path.home() / "Projects" / "vera-corpus" / "corpora" / "mathlib4" / "Mathlib"

DECL = re.compile(
    r"^(?:@\[[^\]]*\]\s*)?(?:protected\s+|private\s+|noncomputable\s+)*"
    r"(?:theorem|lemma)\s+([A-Za-z0-9_.'\u00ab\u00bb]+)")
TACTIC = re.compile(r"^[\s·<;>]*([a-zA-Z_][a-zA-Z0-9_']*)")

#: Statement markers, coarse on purpose — the cheap end of "goal shape".
MARKERS = [
    ("iff", "\u2194"), ("eq", " = "), ("ne", "\u2260"),
    ("le", "\u2264"), ("lt", " < "), ("mem", "\u2208"),
    ("subset", "\u2286"), ("forall", "\u2200"), ("exists", "\u2203"),
    ("dvd", "\u2223"), ("arrow", "\u2192"),
]


IDENT = re.compile(r"[A-Za-z][A-Za-z0-9_'.]+")

#: Binder/context noise that opens most statements without being the
#: statement's subject.
_SKIP = {"fun", "let", "Type", "Sort", "Prop", "Set", "Finset", "instDecidable"}


def shape_of(stmt: str) -> str:
    got = [name for name, mark in MARKERS if mark in stmt]
    return "+".join(got) if got else "plain"


def head_of(stmt: str) -> str:
    """The statement's head constant — the fine end of goal shape.

    The conclusion follows the last top-level `:`; its first capitalized
    identifier is the head (Continuous, Measurable, …). Lowercase-only
    conclusions (bare equations) report their relation instead via
    shape_of, so the fine shape is head + markers.
    """
    concl = stmt.rsplit(":", 1)[-1]
    for tok in IDENT.findall(concl):
        if tok in _SKIP:
            continue
        if tok[0].isupper():
            return tok
    return "-"


def fine_shape(stmt: str) -> str:
    return head_of(stmt) + "|" + shape_of(stmt)


def traces():
    for path in sorted(MATHLIB.rglob("*.lean")):
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        i = 0
        while i < len(lines):
            m = DECL.match(lines[i])
            if not m:
                i += 1
                continue
            block = lines[i][m.end():]
            j = i + 1
            while ":=" not in block and j < len(lines) and j - i < 6:
                block += " " + lines[j]
                j += 1
            if ":=" not in block:
                i = j
                continue
            stmt, _, proof = block.partition(":=")
            proof = proof.strip()
            first = None
            if proof.startswith("by"):
                rest = proof[2:].strip()
                if not rest and j < len(lines):
                    rest = lines[j].strip()
                t = TACTIC.match(rest or "")
                if t:
                    first = t.group(1)
            if first:
                yield shape_of(stmt), fine_shape(stmt), first
            i = j if j > i + 1 else i + 1


rows = list(traces())
print("proofs with a first tactic:", len(rows), flush=True)

stride = max(1, len(rows) // 300)
test_set = set(range(0, len(rows), stride))
test = [rows[k] for k in sorted(test_set)][:300]
train = [r for k, r in enumerate(rows) if k not in test_set]

baseline_guess = Counter(t for _c, _f, t in train).most_common(1)[0][0]


def majority_table(pairs):
    by = {}
    for shape, tac in pairs:
        by.setdefault(shape, Counter())[tac] += 1
    table = {}
    for shape, counts in by.items():
        top = counts.most_common(2)
        # A tie abstains; so does a family of one observation — a
        # majority of one vote is an accident, not a restriction.
        if sum(counts.values()) < 2 or (len(top) > 1
                                        and top[0][1] == top[1][1]):
            table[shape] = None
        else:
            table[shape] = top[0][0]
    return by, table


def score(table, key_idx):
    hits = answered = abstained = 0
    for row in test:
        guess = table.get(row[key_idx])
        if guess is None:
            abstained += 1
            continue
        answered += 1
        hits += guess == row[2]
    return {"answered": answered, "abstained": abstained,
            "accuracy": round(hits / answered, 3) if answered else None}


by_coarse, coarse_table = majority_table([(c, t) for c, _f, t in train])
by_fine, fine_table = majority_table([(f, t) for _c, f, t in train])

base_hits = sum(t == baseline_guess for _c, _f, t in test)

print(json.dumps({
    "tactic_vocabulary": len({t for _c, _f, t in rows}),
    "test": len(test),
    "baseline": {"guess": baseline_guess,
                 "accuracy": round(base_hits / len(test), 3)},
    "coarse_shape": score(coarse_table, 0),
    "fine_shape": {**score(fine_table, 1),
                   "table_size": len(fine_table)},
    "fine_examples": {
        s: {"tactic": fine_table[s], "n": sum(by_fine[s].values())}
        for s in sorted(by_fine, key=lambda s: -sum(by_fine[s].values()))[:8]},
}, ensure_ascii=False, indent=1))
