"""Is this theorem verified? The mathlib witness store answers.

Why this is a module and not a door body
----------------------------------------
The lookup used to live inside `mcp_server.vera_math`. Logic inside a door
is reachable only by a caller that knows to call that door — which is the
exact failure this session is undoing: seventeen organs sat outside every
question because the composition lived in whoever was calling. A door
should be a thin binding over a module, never the only copy.

What this answers, and what it does not
---------------------------------------
75,919 of mathlib's 77,242 theorems carry a `verified:lean4:4.34.0-rc1`
facet earned by an actual kernel run — the hardest witness layer in the
project. This answers about the STORE: a name it holds without the facet
is UNVERIFIED_IN_STORE, and a name it does not hold at all is
UNKNOWN_NOT_IN_MATHLIB_STORE. **Absence of a witness is never a claim of
falsehood.** The `sorry` trap in `lean_witness_forks` — a declaration that
type-checks because its proof is a hole — is why the wording stays this
careful.

Lookup is by case-folded declaration name or a trailing segment
(`semiconj` finds `addconstmapclass.semiconj` when that is unique).
Ambiguity lists candidates rather than choosing one.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

_CACHE: Dict[str, Any] = {}

#: A Lean declaration name: ASCII identifier runs joined by dots or
#: underscores. Closed on purpose — 「フェルマーの最終定理は証明済みですか」
#: names no declaration in this store, and matching it loosely would
#: produce a confident-looking answer about an unrelated lemma.
_DECL = re.compile(r"^[A-Za-z][A-Za-z0-9_'.]*$")


def store_path() -> Path:
    return corpus_root() / "build" / "mathlib_store.json"


def looks_like_declaration(name: str) -> bool:
    """True when this could name a Lean declaration at all."""
    return bool(_DECL.match((name or "").strip()))


def lookup(name: str, *, path: Optional[Path] = None) -> Dict[str, Any]:
    """The store's verdict on one declaration name."""
    q = (name or "").strip()
    if not looks_like_declaration(q):
        return {"verdict": "UNKNOWN_NOT_A_DECLARATION_NAME", "name": name,
                "note": "Lean の宣言名ではない。この店は数学ではなく"
                        "宣言名について答える"}
    p = path or store_path()
    key = str(p)
    if key not in _CACHE:
        if not p.is_file():
            return {"verdict": "UNKNOWN_NOT_LOADED",
                    "note": "mathlib_store.json not present beside the "
                            "published build"}
        _CACHE[key] = json.loads(p.read_text(encoding="utf-8"))["crosses"]
    crosses = _CACHE[key]

    q = q.casefold()
    hit = crosses.get(q)
    matches = [q] if hit is not None else [
        k for k in crosses if k == q or k.endswith("." + q)]
    if not matches:
        # 被覆を名乗る(2026-08-19実測)。この店は mathlib の**一部**で、
        # 75,171宣言・出所メタデータなし。core Lean の宣言(Nat.add_comm)
        # とクラスのフィールド(add_comm)は構造上入っていない。
        # 「この店に無い」と「mathlib に無い」は違う — 前者しか言えない。
        return {"verdict": "UNKNOWN_NOT_IN_MATHLIB_STORE", "name": name,
                "store_declarations": len(crosses),
                "note": "no declaration by this name or trailing segment. "
                        "This store holds %d declarations and is a SUBSET of "
                        "mathlib with no provenance metadata: core-Lean "
                        "declarations and class fields are absent by "
                        "construction. Absent here is not absent from "
                        "mathlib, and neither is a claim of falsehood."
                        % len(crosses)}
    if len(matches) > 12:
        return {"verdict": "UNKNOWN_AMBIGUOUS_NAME", "name": name,
                "candidates": len(matches), "sample": sorted(matches)[:12]}
    out = []
    for m in sorted(matches):
        facets = crosses[m]
        wit = sorted(f for f in facets if str(f).startswith("verified:"))
        out.append({"declaration": m,
                    "verdict": "VERIFIED" if wit else "UNVERIFIED_IN_STORE",
                    "witness": wit or None,
                    "facets": len(facets)})
    return {"verdict": out[0]["verdict"] if len(out) == 1 else "MULTIPLE",
            "name": name, "results": out}
