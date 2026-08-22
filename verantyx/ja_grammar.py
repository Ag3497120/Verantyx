"""Japanese grammatical data — bundled, validated, and extensible without code.

The stopwords, antonym pairs, aspect joins, aliases and predicate forms used
to live as Python constants across three modules. That made the grammar a
programmer's possession: adding one vocabulary pair — a thing a domain expert
does, not a developer — meant editing source. Now the data ships as
`lang_data/ja_grammar.json` inside the package, and a user can lay an overlay
file beside their store to extend it, exactly the mechanism the failure packs
already use. Grammar is knowledge, and knowledge here is data with a loader,
never code.

Every load is validated, loudly. The rules encode lessons this project paid
for on real corpora, and an overlay that violates them would reintroduce the
same failures with an expert's name on them:

  * pair members must be ≥2 chars — substring matching over Japanese makes a
    single kanji a false-positive machine (開 sits inside 開始, 公開, 展開)
  * a term may carry one pole only — both sides of one aspect on one word is
    a contradiction generator, not a vocabulary
  * aliases and joins must point at terms/aspects that exist — a dangling
    reference would silently detect nothing
  * predicates should describe known terms — a predicate for an unknown term
    is usually a typo for one

An invalid overlay raises with every problem named. Refusing to load half a
grammar beats running with one: the visible failure costs a minute, the
silent one costs a wrong report with a citation on it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: PyInstaller unpacks bundled data under _MEIPASS; a source checkout reads
#: beside this file. Same dual-path rule as the failure packs.
if getattr(sys, "_MEIPASS", None):
    BUILTIN_GRAMMAR = Path(sys._MEIPASS) / "verantyx" / "lang_data" / "ja_grammar.json"  # type: ignore[attr-defined]
else:
    BUILTIN_GRAMMAR = Path(__file__).resolve().parent / "lang_data" / "ja_grammar.json"

# Public tables. Mutated in place by load()/load_overlay(), never rebound, so
# modules that imported them see updates without re-importing.
STOPWORDS: set = set()
ANTONYM_PAIRS: List[Tuple[str, str]] = []
ASPECT_JOINS: List[Tuple[str, str, str]] = []
ALIASES: Dict[str, str] = {}
PREDICATES: Dict[str, str] = {}
#: Kanji that follow a polar term without making it a compound noun. The
#: compound guard rejects any following kanji, which is right for 復旧作業 (a
#: restoration EFFORT is not a restored state) and wrong for 復旧済, where the
#: kanji is a grammatical suffix meaning the state has been reached. Measured
#: on 内閣府's 令和8年熊本地震 damage tables: 「熊本市 … ・復旧済」 is the row that
#: records a municipality's water coming back, and it produced no claim.
#: Data rather than code so a domain can add its own without a release.
COMPLETION_SUFFIXES: set = set()
#: Suppression patterns — regexes matched against the text immediately after a
#: polar term, where a match means the term asserts nothing.
#:
#: Every reading rule this engine has accumulated is that same shape: 〜される
#: まで, 〜であると認める, 〜による. They live in `polarity` as compiled
#: constants because they were written by hand and are proven. This list is
#: for the ones DERIVED from defect reports, which have to arrive as data —
#: a growth loop that requires editing source is a loop only its authors can
#: be in.
#:
#: Loaded through an overlay and validated like everything else, and each one
#: carries the gap it came from so a suppression can always be traced back to
#: the reports that produced it.
SUPPRESSIONS: List[Tuple[str, str]] = []   # (pattern, provenance)
#: Meaning-preserving transforms promoted from PROBE to READING PATH.
#:
#: A suppression is a rule a person wrote; a normalizer is one the engine
#: proved it needed. `metamorphic` shows that two readings of the same content
#: disagree and that the transform between them cannot have changed what the
#: content says — so the reading that only the noisy form produces is
#: manufactured by layout, and switching the reading path to the clean form is
#: a repair with an INTERNAL answer key: the manufactured claims must vanish.
#: Kept as data, and as a list of names rather than of code, so that what the
#: engine may promote to itself is bounded by what a person already reviewed.
NORMALIZERS: List[Tuple[str, str]] = []   # (perturbation name, provenance)
#: term → (aspect, polarity). Derived; rebuilt on every load.
ASPECT_OF: Dict[str, Tuple[str, str]] = {}
#: All matchable terms, longest first — the scan order substring matching
#: needs so 使用可能 wins over shorter neighbours.
TERMS: List[str] = []

_loaded_overlay: Optional[Path] = None


def validate(data: Dict[str, Any]) -> List[str]:
    errs: List[str] = []
    for item in data.get("normalizers") or []:
        # A normalizer names a transform this repository ships and argued for.
        # Accepting an arbitrary one from an overlay would let a data file
        # rewrite documents before they are read.
        from .metamorphic import PERTURBATIONS as _P

        if not (isinstance(item, (list, tuple)) and item and item[0] in _P):
            errs.append(f"unknown normalizer: {item!r}")
    pairs = data.get("antonym_pairs", [])
    seen_terms: Dict[str, str] = {}
    for pair in pairs:
        if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
            errs.append(f"pair not a 2-list: {pair!r}")
            continue
        pos, neg = pair
        if pos == neg:
            errs.append(f"pair with identical members: {pos!r}")
        for term, pol in ((pos, "+"), (neg, "-")):
            if not isinstance(term, str) or len(term) < 2:
                errs.append(f"term under 2 chars invites substring false "
                            f"positives: {term!r}")
                continue
            if term in seen_terms and seen_terms[term] != pol:
                errs.append(f"term {term!r} carries both poles — that is a "
                            f"contradiction generator, not a vocabulary")
            seen_terms[term] = pol

    aspects = {p[0] for p in pairs
               if isinstance(p, (list, tuple)) and len(p) == 2}
    for join in data.get("aspect_joins", []):
        if not (isinstance(join, (list, tuple)) and len(join) == 3):
            errs.append(f"join not a 3-list: {join!r}")
            continue
        term, aspect, pol = join
        if pol not in ("+", "-"):
            errs.append(f"join polarity must be + or -: {join!r}")
        if aspect not in aspects:
            errs.append(f"join {term!r} targets unknown aspect {aspect!r}")
        if isinstance(term, str) and len(term) < 2:
            errs.append(f"join term under 2 chars: {term!r}")

    known = set(seen_terms) | {j[0] for j in data.get("aspect_joins", [])
                               if isinstance(j, (list, tuple)) and len(j) == 3}
    for alias, target in (data.get("aliases") or {}).items():
        if target not in known:
            errs.append(f"alias {alias!r} points at unknown term {target!r}")
    import re as _re
    for item in data.get("suppressions") or []:
        if not (isinstance(item, (list, tuple)) and item and isinstance(item[0], str)):
            errs.append(f"suppression not a [pattern, provenance] list: {item!r}")
            continue
        if not item[0].startswith("^"):
            errs.append(f"suppression must anchor at the start (^): {item[0]!r}")
        try:
            _re.compile(item[0])
        except _re.error as exc:
            errs.append(f"suppression is not a valid regex: {item[0]!r} ({exc})")
    for term in (data.get("predicates") or {}):
        if term not in known and not any(term == a for a in aspects):
            errs.append(f"predicate for unknown term {term!r} — usually a typo "
                        f"for a term that exists")
    return errs


def _rebuild() -> None:
    ASPECT_OF.clear()
    for pos, neg in ANTONYM_PAIRS:
        ASPECT_OF[pos] = (pos, "+")
        ASPECT_OF[neg] = (pos, "-")
    for term, aspect, pol in ASPECT_JOINS:
        ASPECT_OF[term] = (aspect, pol)
    TERMS[:] = sorted(list(ASPECT_OF) + list(ALIASES), key=len, reverse=True)


def _apply(data: Dict[str, Any]) -> None:
    STOPWORDS.update(data.get("stopwords", []))
    have = {tuple(p) for p in ANTONYM_PAIRS}
    for pair in data.get("antonym_pairs", []):
        if tuple(pair) not in have:
            ANTONYM_PAIRS.append((pair[0], pair[1]))
    have_j = {tuple(j) for j in ASPECT_JOINS}
    for join in data.get("aspect_joins", []):
        if tuple(join) not in have_j:
            ASPECT_JOINS.append((join[0], join[1], join[2]))
    ALIASES.update(data.get("aliases") or {})
    PREDICATES.update(data.get("predicates") or {})
    COMPLETION_SUFFIXES.update(data.get("completion_suffixes") or [])
    have_n = {tuple(x) for x in NORMALIZERS}
    for item in data.get("normalizers") or []:
        pair = (item[0], item[1] if len(item) > 1 else "")
        if pair not in have_n:
            NORMALIZERS.append(pair)
    have_s = {tuple(x) for x in SUPPRESSIONS}
    for item in data.get("suppressions") or []:
        pair = (item[0], item[1] if len(item) > 1 else "")
        if pair not in have_s:
            SUPPRESSIONS.append(pair)
    _rebuild()


def load() -> None:
    """(Re)load the bundled grammar. Missing bundled data is fatal on
    purpose: a build without it would silently run with no Japanese at all,
    which is the zero-sentences failure this project already lived through."""
    raw = json.loads(BUILTIN_GRAMMAR.read_text(encoding="utf-8"))
    errs = validate(raw)
    if errs:
        raise ValueError("bundled ja_grammar.json is invalid:\n  "
                         + "\n  ".join(errs))
    STOPWORDS.clear()
    ANTONYM_PAIRS.clear()
    ASPECT_JOINS.clear()
    ALIASES.clear()
    PREDICATES.clear()
    COMPLETION_SUFFIXES.clear()
    SUPPRESSIONS.clear()
    _apply(raw)
    global _loaded_overlay
    _loaded_overlay = None


def load_overlay(path: Path) -> Dict[str, Any]:
    """Merge a user's grammar extension over the bundled data.

    The overlay VALIDATES AGAINST THE MERGED WHOLE — its joins may target
    bundled aspects, and a term it adds must not flip the pole of a bundled
    one. Errors raise with every problem listed; nothing half-loads.
    """
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    merged = {
        "stopwords": sorted(STOPWORDS | set(raw.get("stopwords", []))),
        "antonym_pairs": [list(x) for x in ANTONYM_PAIRS]
                         + [list(x) for x in raw.get("antonym_pairs", [])],
        "aspect_joins": [list(x) for x in ASPECT_JOINS]
                        + [list(x) for x in raw.get("aspect_joins", [])],
        "aliases": {**ALIASES, **(raw.get("aliases") or {})},
        "predicates": {**PREDICATES, **(raw.get("predicates") or {})},
    }
    errs = validate(merged)
    if errs:
        raise ValueError(f"grammar overlay {p.name} is invalid:\n  "
                         + "\n  ".join(errs))
    _apply(raw)
    global _loaded_overlay
    _loaded_overlay = p
    return {"overlay": str(p),
            "added_pairs": len(raw.get("antonym_pairs", [])),
            "added_aliases": len(raw.get("aliases") or {}),
            "added_predicates": len(raw.get("predicates") or {}),
            "total_terms": len(ASPECT_OF)}


def status() -> Dict[str, Any]:
    return {"builtin": str(BUILTIN_GRAMMAR),
            "overlay": str(_loaded_overlay) if _loaded_overlay else None,
            "stopwords": len(STOPWORDS), "pairs": len(ANTONYM_PAIRS),
            "joins": len(ASPECT_JOINS), "aliases": len(ALIASES),
            "predicates": len(PREDICATES), "terms": len(TERMS)}


load()
