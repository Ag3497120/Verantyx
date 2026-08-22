"""Do mathlib's retrieval ties split by STRUCTURE?

measure_mathlib.py found the flat bag sound (0 missing, 0 fabricated)
and non-identifying (~50% unique). Two suspects, measured apart here:

  1. My extraction bug: names were taken as declared, without the
     enclosing `namespace` — Nat.add_comm and List.add_comm collapsed
     into one core. Qualified names undo that much.
  2. Genuine bag saturation: near-variants sharing their vocabulary.
     For those, the ORDERED, whitespace-normalized statement text is
     the weakest structural signature there is — if even it splits a
     tie, term-level identity (rewrite_kernel's representation) will.

Reported: uniqueness with qualified names; then, of the remaining
ties, how many the signature splits (the true theorem's signature
unique within its tie set).

## Measured — mathlib4 depth-1, 77,242 theorems, 75,171 qualified cores

    bag alone (qualified names)       unique 137/300   missing 0
    + ordered statement signature     ties 163, split 159
    identified in total               296/300 (98.7%)

The namespace fix recovered 8k collapsed cores (67,206 -> 75,171) and
did not move bag uniqueness — the ~50% saturation was genuine, and the
weakest structural identity there is (whitespace-normalized statement
text) resolves 97.5% of it. The four that stay tied are true twins:
the same lemma over different carriers (real vs nnreal rpow,
subsemiring vs subring unop_closure, jacobian vs projective
smul_equiv) whose statement TEXT is identical because the
distinguishing context lives outside the statement — in the namespace
and variable environment. That is the exact seam where the textual
signature ends and the elaborated Lean term (the toolchain step)
begins: bag -> candidates, signature -> 296, elaboration -> the rest.
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
NS_OPEN = re.compile(r"^namespace\s+([A-Za-z0-9_.']+)")
NS_CLOSE = re.compile(r"^end(\s+([A-Za-z0-9_.']+))?\s*$")
IDENT = re.compile(r"[A-Za-z][A-Za-z0-9_']+")

STOP = {"fun", "let", "have", "show", "with", "this", "by", "of", "and",
        "or", "not", "if", "then", "else", "the", "in", "to", "at"}


def declarations():
    for path in sorted(MATHLIB.rglob("*.lean")):
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
            signature = " ".join(stmt.split())
            if len(toks) >= 3:
                yield name, toks, signature
            i = j if j > i + 1 else i + 1


store = CrossStore()
sig_of = {}
n = 0
for name, toks, sig in declarations():
    store.add(name, toks)
    sig_of[name.casefold()] = sig
    n += 1
print("theorems:", n, "| qualified cores:", len(store.crosses), flush=True)

cores = sorted(store.crosses)
stride = max(1, len(cores) // 300)
bank = cores[::stride][:300]


def holders(term):
    return {c for c, cross in store.crosses.items() if term in (cross or ())}


unique = missing = 0
ties = []
for name in bank:
    cand = None
    for t in sorted(store.crosses[name]):
        got = holders(t) | ({t} if t in store.crosses else set())
        cand = got if cand is None else (cand & got)
        if not cand:
            break
    cand = cand or set()
    if cand == {name}:
        unique += 1
    elif name in cand:
        ties.append((name, cand))
    else:
        missing += 1

split_by_sig = 0
unsplit = []
for name, cand in ties:
    mine = sig_of.get(name, "")
    rivals = [sig_of.get(c, "") for c in cand if c != name]
    if mine and all(r != mine for r in rivals):
        split_by_sig += 1
    else:
        twins = sorted(c for c in cand if c != name
                       and sig_of.get(c, "") == mine)
        unsplit.append({"name": name, "twins": twins[:3]})

print(json.dumps({
    "bank": len(bank), "unique_qualified": unique,
    "ties": len(ties), "missing": missing,
    "ties_split_by_signature": split_by_sig,
    "identified_total": unique + split_by_sig,
    "unsplit": unsplit,
}, ensure_ascii=False, indent=1))
