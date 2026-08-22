"""Structural difference — A vs B as three observed bundles.

SPEC_2026-08-14_meaning_layers 納品2. Local computation only: each
subject's own profile, kin family, shelf facets, and shelf definition
tokens. The lattice may be built once up front; a query never scans
the store.

Defense 1. only_a means observed on A, not observed on B. The schema
has no slot for a negated claim. Output vocabulary is 実測あり /
実測なし. Bundles are assembled from observed tokens; no sentence is
built around a missing observation.

Defense 2. Predicates and facets are compared as ratios, never as raw
counts. A layer whose either side has fewer than ``min_profile``
(default 3) items of that layer's kind abstains with
INSUFFICIENT_PROFILE. Coverage of both sides is always attached; the
thin side is the confidence.

Layers
    ① predicate-family type (stems of observed predicates)
    ② normalized predicate profile
    ③ lattice kin families
    ④ shelf facet-mass distribution
    ⑤ edge orientation (される / られる mark the patient side)
    ⑥ shelf definition tokens

Ties at a top-k cutoff abstain. Display order inside a bundle is
layer, then ratio, then token length, then lex — a display order,
not an election.

## Measured — W2a sense wiring on, same 30-pair bank, seed 20260814

    hits                         0 / 30     (was 11 / 30)
    misses                       1
    abstentions                  29
    of which AMBIGUOUS_SENSE     29
    oracle containment           0.9739     (was 0.9750)
    馬/自転車                    AMBIGUOUS_SENSE (麻雀 gone from only_a)

    See tools/measure_structural_diff.py. Old sections there stay.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .lattice import kin
from .lex_filters import is_junk_facet
from .sense_split import AMBIGUOUS_SENSE, resolve

OBSERVED = "実測あり"
UNOBSERVED = "実測なし"

LAYER_FAMILY = "①"
LAYER_PROFILE = "②"
LAYER_KIN = "③"
LAYER_FACET = "④"
LAYER_ORIENT = "⑤"
LAYER_DEFINE = "⑥"

# Closed orientation labels — the spec's 作用する側 / される側.
ORIENT_AGENT = "作用する側"
ORIENT_PATIENT = "される側"

# Longest-first. A remainder shorter than the ending is left intact
# so a bare frame (である) stays a family of its own.
_FAMILY_ENDS: Tuple[str, ...] = (
    "のことである", "の一種である", "の総称である", "の名称である",
    "と呼ばれている", "と呼ばれた", "と呼ばれる",
    "とされている", "とされた", "とされる",
    "といわれている", "といわれる",
    "を意味する", "を指している", "を指す",
    "にあたる", "に当たる",
    "のこと", "の一種", "の総称",
    "であった", "である", "でした", "です", "だった",
    "されている", "される",
    "られている", "られる",
    "れている", "れる",
    "している", "する",
    "できる",
)

_PATIENT_ENDS: Tuple[str, ...] = ("される", "られる")

# Wiki / ingest remnants that land as facets. Same family as
# lex_filters.STOP_CORES (lt/gt/quot): markup, not a subject's mass.
_INGEST_SKIP = frozenset({
    "ref", "name", "nam", "thumb", "px", "file", "infobox",
    "reported", "wikitable", "style", "class", "sub", "sup",
    "quot", "amp", "nbsp", "サムネイル",
})

_LAYER_RANK = {
    LAYER_PROFILE: 0,
    LAYER_FAMILY: 1,
    LAYER_DEFINE: 2,
    LAYER_FACET: 3,
    LAYER_ORIENT: 4,
    LAYER_KIN: 5,
}

DEFAULT_K = 8
DEFAULT_MIN_PROFILE = 3


def _canonical(term: str, aliases: Optional[Dict[str, str]]) -> str:
    t = (term or "").strip()
    if not t:
        return t
    hit = (aliases or {}).get(t)
    return hit if hit else t


def _context_tokens(term: str) -> List[str]:
    from .lang import ja_content_runs
    t = (term or "").strip()
    toks = ja_content_runs(t)
    if t and t not in toks:
        toks = [t] + toks
    return toks


def _sense_subject(
    term: str,
    other: str,
    aliases: Optional[Dict[str, str]],
    senses: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Canonicalize through the sense sidecar (primary default).

    The other term is the comparison partner, not a sense specifier.
    Context-given resolve stays available on ``resolve`` itself.
    """
    return resolve(term, [], senses=senses, aliases=aliases)


def _predicates(profiles: Dict[str, Any], subject: str) -> Dict[str, float]:
    rec = (profiles or {}).get(subject)
    if not isinstance(rec, dict):
        return {}
    preds = rec.get("predicates") or {}
    return {str(p): float(n) for p, n in preds.items() if p and float(n) > 0}


def _normalize(counts: Dict[str, float]) -> Dict[str, float]:
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in counts.items()}


def _family_of(pred: str) -> str:
    for end in _FAMILY_ENDS:
        if pred.endswith(end) and len(pred) > len(end):
            stem = pred[:-len(end)]
            if stem:
                return stem
    return pred


def _is_patient(pred: str) -> bool:
    return pred.endswith(_PATIENT_ENDS[0]) or pred.endswith(_PATIENT_ENDS[1])


def _family_mass(norm: Dict[str, float]) -> Dict[str, float]:
    mass: Dict[str, float] = {}
    for pred, ratio in norm.items():
        fam = _family_of(pred)
        mass[fam] = mass.get(fam, 0.0) + ratio
    return mass


def _orient_mass(norm: Dict[str, float]) -> Dict[str, float]:
    patient = 0.0
    agent = 0.0
    for pred, ratio in norm.items():
        if _is_patient(pred):
            patient += ratio
        else:
            agent += ratio
    out: Dict[str, float] = {}
    if agent > 0:
        out[ORIENT_AGENT] = agent
    if patient > 0:
        out[ORIENT_PATIENT] = patient
    return out


_PROV_SRC = re.compile(r"\(reported by (jawiki-lead:.+)\)\s*$")


def _prov_source(slot: Any) -> Optional[str]:
    snippet = ""
    if isinstance(slot, (list, tuple)) and len(slot) > 2:
        snippet = str(slot[2] or "")
    elif isinstance(slot, str):
        snippet = slot
    m = _PROV_SRC.search(snippet)
    return m.group(1) if m else None


def _lead_mass(
    tokens: Optional[List[str]],
    subject: str,
    *,
    limit: Optional[int] = None,
) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for tok in tokens or []:
        if not tok or tok == subject:
            continue
        if tok in _INGEST_SKIP or tok.casefold() in _INGEST_SKIP:
            continue
        if is_junk_facet(tok):
            continue
        out[str(tok)] = 1.0
        if limit is not None and len(out) >= limit:
            break
    return out


def _shelf_cross(
    shelf: Any,
    subject: str,
    *,
    article: Optional[str] = None,
) -> Dict[str, float]:
    if shelf is None:
        return {}
    crosses = getattr(shelf, "crosses", None) or {}
    labels = getattr(shelf, "source_labels", None) or set()
    raw = crosses.get(subject)
    if raw is None:
        raw = crosses.get(subject.casefold())
    if not raw:
        return {}
    out: Dict[str, float] = {}
    for facet, n in raw.items():
        if not facet or facet == subject or facet in labels:
            continue
        if str(facet) in _INGEST_SKIP or str(facet).casefold() in _INGEST_SKIP:
            continue
        if is_junk_facet(str(facet)):
            continue
        out[str(facet)] = float(n)
    if not article:
        return out
    prov = getattr(shelf, "provenance", None) or {}
    slots = prov.get(subject) or prov.get(subject.casefold()) or {}
    if not slots:
        return out
    want = "jawiki-lead:%s" % article
    return {
        f: n for f, n in out.items()
        if _prov_source(slots.get(f)) == want
    }


def _definition_tokens(
    shelf: Any,
    subject: str,
    *,
    article: Optional[str] = None,
) -> Dict[str, float]:
    """Presence mass over tokens of the shelf definition, when held.

    Provenance snippets are the lead sentences. When ``article`` is
    set, only snippets whose source is ``jawiki-lead:{article}`` are
    read — parenthetical siblings stay out. When provenance is
    absent, the subject's own facet keys are the definition tokens
    (presence, not mass — layer ④ already carries mass).
    """
    if shelf is None:
        return {}
    from .lang import ja_content_runs

    labels = getattr(shelf, "source_labels", None) or set()
    prov = getattr(shelf, "provenance", None) or {}
    slots = prov.get(subject) or prov.get(subject.casefold()) or {}
    want = ("jawiki-lead:%s" % article) if article else None
    seen: Dict[str, float] = {}
    for _facet, slot in slots.items():
        if want and _prov_source(slot) != want:
            continue
        snippet = ""
        if isinstance(slot, (list, tuple)) and len(slot) > 2:
            snippet = str(slot[2] or "")
        elif isinstance(slot, str):
            snippet = slot
        for tok in ja_content_runs(snippet):
            if not tok or tok == subject or tok in labels:
                continue
            if tok in _INGEST_SKIP or tok.casefold() in _INGEST_SKIP:
                continue
            if is_junk_facet(tok):
                continue
            seen[tok] = seen.get(tok, 0.0) + 1.0
    if seen:
        return seen
    if want and slots:
        return {}
    # Presence-only fallback: one tick per held facet.
    return {f: 1.0 for f in _shelf_cross(shelf, subject, article=article)}


def _kin_mass(lattice: Any, subject: str, k: int) -> Dict[str, float]:
    if lattice is None or not subject:
        return {}
    families = kin(lattice, subject, limit=k)
    mass: Dict[str, float] = {}
    for slot, words in families.items():
        mass[slot] = mass.get(slot, 0.0) + 1.0
        for w in words:
            if w and w != subject:
                mass[w] = mass.get(w, 0.0) + 1.0
    return mass


def _item(
    token: str,
    layer: str,
    edge: str,
    a_on: bool,
    b_on: bool,
    a_ratio: float,
    b_ratio: float,
) -> Dict[str, Any]:
    return {
        "token": token,
        "layer": layer,
        "edge": edge,
        "a_status": OBSERVED if a_on else UNOBSERVED,
        "b_status": OBSERVED if b_on else UNOBSERVED,
        "a_ratio": round(float(a_ratio), 6),
        "b_ratio": round(float(b_ratio), 6),
    }


def _topk(
    items: List[Dict[str, Any]],
    k: int,
    score: Callable[[Dict[str, Any]], float],
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Keep the top-k. A tie that straddles the cutoff abstains those items."""
    if not items:
        return [], None
    ranked = sorted(items, key=lambda it: (-score(it), it["token"]))
    if len(ranked) <= k:
        return ranked, None
    if score(ranked[k - 1]) == score(ranked[k]):
        tied = score(ranked[k - 1])
        kept = [it for it in ranked if score(it) > tied]
        return kept, "TIE"
    return ranked[:k], None


def _split_layer(
    norm_a: Dict[str, float],
    norm_b: Dict[str, float],
    layer: str,
    edge: str,
    k: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Optional[str]]:
    shared: List[Dict[str, Any]] = []
    only_a: List[Dict[str, Any]] = []
    only_b: List[Dict[str, Any]] = []
    for tok in set(norm_a) | set(norm_b):
        a_on = tok in norm_a
        b_on = tok in norm_b
        item = _item(
            tok, layer, edge, a_on, b_on,
            norm_a.get(tok, 0.0), norm_b.get(tok, 0.0),
        )
        if a_on and b_on:
            shared.append(item)
        elif a_on:
            only_a.append(item)
        elif b_on:
            only_b.append(item)
    sh, w1 = _topk(shared, k, lambda it: min(it["a_ratio"], it["b_ratio"]))
    oa, w2 = _topk(only_a, k, lambda it: it["a_ratio"])
    ob, w3 = _topk(only_b, k, lambda it: it["b_ratio"])
    why = w1 or w2 or w3
    return sh, oa, ob, why


def _sort_bucket(items: List[Dict[str, Any]], side: str) -> List[Dict[str, Any]]:
    def key(it: Dict[str, Any]) -> Tuple[Any, ...]:
        if side == "shared":
            ratio = min(it["a_ratio"], it["b_ratio"])
        elif side == "a":
            ratio = it["a_ratio"]
        else:
            ratio = it["b_ratio"]
        return (
            _LAYER_RANK.get(it["layer"], 9),
            -ratio,
            -len(it["token"]),
            it["token"],
        )
    return sorted(items, key=key)


def _run_layer(
    counts_a: Dict[str, float],
    counts_b: Dict[str, float],
    *,
    layer: str,
    edge: str,
    k: int,
    min_profile: int,
    abstain: Dict[str, str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    if len(counts_a) < min_profile or len(counts_b) < min_profile:
        abstain[layer] = "INSUFFICIENT_PROFILE"
        return [], [], []
    sh, oa, ob, why = _split_layer(
        _normalize(counts_a), _normalize(counts_b), layer, edge, k,
    )
    if why:
        abstain[layer] = why
    return sh, oa, ob


def diff(
    a: str,
    b: str,
    *,
    profiles: Dict[str, Any],
    aliases: Dict[str, str],
    lattice: Any,
    shelf: Any,
    k: int = DEFAULT_K,
    min_profile: int = DEFAULT_MIN_PROFILE,
    senses: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compare ``a`` and ``b`` across the six layers.

    Inputs are canonicalized through ``aliases`` (one hop). When
    ``senses`` is supplied, canonicalization consults the W2a sidecar
    (primary default, or a unique context hit). The pair abstains as
    AMBIGUOUS_SENSE only when a side has no primary (a 曖昧さ回避
    title). Shelf layers ④ and ⑥ keep only facets whose provenance
    is ``jawiki-lead:{resolved}``. Each layer that cannot meet
    ``min_profile`` on both sides abstains. The return always carries
    ``coverage``.
    """
    sense_hits: Optional[Dict[str, Any]] = None
    article_a = article_b = None
    leads_a: List[str] = []
    leads_b: List[str] = []
    if senses is not None:
        ra = _sense_subject(a, b, aliases, senses)
        rb = _sense_subject(b, a, aliases, senses)
        sense_hits = {"a": ra, "b": rb}
        if (ra.get("verdict") == AMBIGUOUS_SENSE
                or rb.get("verdict") == AMBIGUOUS_SENSE):
            return {
                "a": a,
                "b": b,
                "canonical": {
                    "a": ra.get("core") or _canonical(a, aliases),
                    "b": rb.get("core") or _canonical(b, aliases),
                },
                "verdict": AMBIGUOUS_SENSE,
                "senses": sense_hits,
                "coverage": {
                    "a": {"predicates": 0, "facets": 0},
                    "b": {"predicates": 0, "facets": 0},
                },
                "confidence": {"predicates": 0, "facets": 0},
                "k": k,
                "min_profile": min_profile,
                "shared": [],
                "only_a": [],
                "only_b": [],
                "abstain": {"sense": AMBIGUOUS_SENSE},
            }
        ca = ra.get("core") or _canonical(a, aliases)
        cb = rb.get("core") or _canonical(b, aliases)
        article_a, article_b = ca, cb
        leads_a = list(ra.get("lead_tokens") or [])
        leads_b = list(rb.get("lead_tokens") or [])
    else:
        ca = _canonical(a, aliases)
        cb = _canonical(b, aliases)

    preds_a = _predicates(profiles, ca)
    preds_b = _predicates(profiles, cb)
    facets_a = _shelf_cross(shelf, ca, article=article_a)
    facets_b = _shelf_cross(shelf, cb, article=article_b)
    if article_a and not facets_a:
        facets_a = _lead_mass(leads_a, ca, limit=k)
    if article_b and not facets_b:
        facets_b = _lead_mass(leads_b, cb, limit=k)

    coverage = {
        "a": {"predicates": len(preds_a), "facets": len(facets_a)},
        "b": {"predicates": len(preds_b), "facets": len(facets_b)},
    }
    confidence = {
        "predicates": min(coverage["a"]["predicates"], coverage["b"]["predicates"]),
        "facets": min(coverage["a"]["facets"], coverage["b"]["facets"]),
    }

    shared: List[Dict[str, Any]] = []
    only_a: List[Dict[str, Any]] = []
    only_b: List[Dict[str, Any]] = []
    abstain: Dict[str, str] = {}

    def _take(sh, oa, ob):
        shared.extend(sh)
        only_a.extend(oa)
        only_b.extend(ob)

    pred_ok = (len(preds_a) >= min_profile and len(preds_b) >= min_profile)
    norm_a = _normalize(preds_a)
    norm_b = _normalize(preds_b)

    # ①②⑤ share the predicate-count gate. Family and orientation
    # bins can be fewer than min_profile; the gate is the raw count.
    if pred_ok:
        _take(*_run_layer(
            _family_mass(norm_a), _family_mass(norm_b),
            layer=LAYER_FAMILY, edge="family", k=k,
            min_profile=1, abstain=abstain,
        ))
        if abstain.get(LAYER_FAMILY) == "INSUFFICIENT_PROFILE":
            abstain.pop(LAYER_FAMILY)
    else:
        abstain[LAYER_FAMILY] = "INSUFFICIENT_PROFILE"
    _take(*_run_layer(
        preds_a, preds_b,
        layer=LAYER_PROFILE, edge="predicate", k=k,
        min_profile=min_profile, abstain=abstain,
    ))
    _take(*_run_layer(
        _kin_mass(lattice, ca, k), _kin_mass(lattice, cb, k),
        layer=LAYER_KIN, edge="kin", k=k,
        min_profile=min_profile, abstain=abstain,
    ))
    _take(*_run_layer(
        facets_a, facets_b,
        layer=LAYER_FACET, edge="facet", k=k,
        min_profile=min_profile, abstain=abstain,
    ))
    if pred_ok:
        _take(*_run_layer(
            _orient_mass(norm_a), _orient_mass(norm_b),
            layer=LAYER_ORIENT, edge="orientation", k=k,
            min_profile=1, abstain=abstain,
        ))
        if abstain.get(LAYER_ORIENT) == "INSUFFICIENT_PROFILE":
            abstain.pop(LAYER_ORIENT)
    else:
        abstain[LAYER_ORIENT] = "INSUFFICIENT_PROFILE"
    defs_a = _definition_tokens(shelf, ca, article=article_a)
    defs_b = _definition_tokens(shelf, cb, article=article_b)
    if article_a and not defs_a:
        defs_a = _lead_mass(leads_a, ca, limit=k)
    if article_b and not defs_b:
        defs_b = _lead_mass(leads_b, cb, limit=k)
    _take(*_run_layer(
        defs_a, defs_b,
        layer=LAYER_DEFINE, edge="definition", k=k,
        min_profile=min_profile, abstain=abstain,
    ))

    shared = _sort_bucket(shared, "shared")
    only_a = _sort_bucket(only_a, "a")
    only_b = _sort_bucket(only_b, "b")

    # Same primary article (河川→川, 海洋→海): the resolved core is
    # the shared identity. Length-sort would bury the 1-char title.
    if ca == cb:
        core_item = _item(ca, LAYER_DEFINE, "definition", True, True, 1.0, 1.0)
        shared = [core_item] + [it for it in shared if it["token"] != ca]

    if not shared and not only_a and not only_b and abstain:
        verdict = "INSUFFICIENT_PROFILE"
    else:
        verdict = "DIFF"

    out = {
        "a": a,
        "b": b,
        "canonical": {"a": ca, "b": cb},
        "verdict": verdict,
        "coverage": coverage,
        "confidence": confidence,
        "k": k,
        "min_profile": min_profile,
        "shared": shared,
        "only_a": only_a,
        "only_b": only_b,
        "abstain": abstain,
    }
    if sense_hits is not None:
        out["senses"] = sense_hits
    return out


def regression() -> Dict[str, Any]:
    """Fork-equivalent: both defense lines on a toy store. No corpus."""
    from .cross_store import CrossStore
    from .lattice import build

    profiles = {
        "リンゴ": {"predicates": {"果実のことである": 2, "栽培される": 1, "である": 1},
                   "total": 4},
        "電気": {"predicates": {"発生する": 2, "流れる": 2, "である": 1},
                 "total": 5},
        "薄": {"predicates": {"である": 1}, "total": 1},
    }
    aliases = {"りんご": "リンゴ"}
    lat = build(["リンゴ", "電気", "電子", "電荷", "電流"])
    shelf = CrossStore()
    shelf.crosses["リンゴ"] = {"果実": 3, "植物": 2, "食用": 1}
    shelf.crosses["電気"] = {"電流": 4, "エネルギー": 2, "熱源": 1}
    shelf.core_count["リンゴ"] = 1
    shelf.core_count["電気"] = 1

    out = diff("りんご", "電気", profiles=profiles, aliases=aliases,
               lattice=lat, shelf=shelf, k=8, min_profile=3)

    # Defense 1: statuses are the closed pair; only_a never claims a
    # fact about B beyond UNOBSERVED.
    statuses = {OBSERVED, UNOBSERVED}
    items = out["shared"] + out["only_a"] + out["only_b"]
    status_ok = all(
        it["a_status"] in statuses and it["b_status"] in statuses
        for it in items
    )
    only_a_ok = all(
        it["a_status"] == OBSERVED and it["b_status"] == UNOBSERVED
        for it in out["only_a"]
    )
    only_b_ok = all(
        it["b_status"] == OBSERVED and it["a_status"] == UNOBSERVED
        for it in out["only_b"]
    )
    shared_ok = all(
        it["a_status"] == OBSERVED and it["b_status"] == OBSERVED
        for it in out["shared"]
    )
    # Alias hop: りんご is リンゴ.
    alias_ok = out["canonical"]["a"] == "リンゴ"
    # 果実 is on A, not on B, so it must land in only_a (family or pred).
    tokens_a = {it["token"] for it in out["only_a"]}
    fruit_ok = any("果実" in t for t in tokens_a)
    # である is on both → shared, never only_*.
    both = ({it["token"] for it in out["only_a"]}
            | {it["token"] for it in out["only_b"]})
    copula_ok = "である" not in both
    # Defense 2: coverage present; ratios sum near 1 on a layer-② side.
    cov_ok = (
        "coverage" in out
        and out["coverage"]["a"]["predicates"] == 3
        and out["coverage"]["b"]["predicates"] == 3
        and out["coverage"]["a"]["facets"] == 3
        and out["coverage"]["b"]["facets"] == 3
    )
    thin = diff("薄", "電気", profiles=profiles, aliases=aliases,
                lattice=lat, shelf=shelf, k=8, min_profile=3)
    thin_ok = thin["abstain"].get(LAYER_PROFILE) == "INSUFFICIENT_PROFILE"
    # Same counts, different totals: comparison uses ratios. 流れる is
    # 2/5 on 電気 and absent on リンゴ → only_b, independent of 2 vs 1.
    flow_ok = any(it["token"] == "流れる" for it in out["only_b"])

    # W2a: primary default still DIFFs; sibling provenance is dropped.
    toy_senses = {
        "リンゴ": [
            {"core": "リンゴ", "domain_tag": "", "lead_tokens": ["果実"]},
            {"core": "リンゴ (アルバム)", "domain_tag": "アルバム",
             "lead_tokens": ["音楽"]},
        ],
        "水 (曖昧さ回避)": [
            {"core": "水 (曖昧さ回避)", "domain_tag": "曖昧さ回避",
             "lead_tokens": []},
        ],
    }
    prim = diff("りんご", "電気", profiles=profiles, aliases=aliases,
                lattice=lat, shelf=shelf, k=8, min_profile=3,
                senses=toy_senses)
    prim_ok = (
        prim.get("verdict") == "DIFF"
        and prim.get("canonical", {}).get("a") == "リンゴ"
        and any("果実" in it["token"] for it in prim["only_a"])
    )
    shelf.track_provenance = True
    shelf.crosses["リンゴ"]["麻雀"] = 9
    shelf.provenance["リンゴ"] = {
        "果実": [0, 0, "x (reported by jawiki-lead:リンゴ)"],
        "植物": [0, 0, "x (reported by jawiki-lead:リンゴ)"],
        "食用": [0, 0, "x (reported by jawiki-lead:リンゴ)"],
        "麻雀": [0, 0, "x (reported by jawiki-lead:リンゴ (麻雀))"],
    }
    filt = diff("りんご", "電気", profiles=profiles, aliases=aliases,
                lattice=lat, shelf=shelf, k=8, min_profile=3,
                senses=toy_senses)
    filt_tokens = {it["token"] for it in
                   filt["shared"] + filt["only_a"] + filt["only_b"]}
    filter_ok = "麻雀" not in filt_tokens
    dab = diff("水 (曖昧さ回避)", "電気", profiles=profiles, aliases=aliases,
               lattice=lat, shelf=shelf, k=8, min_profile=3,
               senses=toy_senses)
    dab_ok = dab.get("verdict") == AMBIGUOUS_SENSE

    ok = all([status_ok, only_a_ok, only_b_ok, shared_ok, alias_ok,
              fruit_ok, copula_ok, cov_ok, thin_ok, flow_ok,
              prim_ok, filter_ok, dab_ok])
    return {
        "experiment": "structural_diff",
        "fork": "STRUCTURAL_DIFF_DEFENSE",
        "pass": bool(ok),
        "result": {
            "verdict": out["verdict"],
            "canonical": out["canonical"],
            "coverage": out["coverage"],
            "only_a_tokens": sorted(tokens_a),
            "thin_abstain": thin["abstain"],
            "sense_verdict": prim.get("verdict"),
            "filter_ok": filter_ok,
            "dab": dab.get("verdict"),
        },
    }
