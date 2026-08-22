"""Connective-licensed skeleton sentences over a structural diff.

SPEC_2026-08-14_eight_gaps W3a. The three bundles (shared / only_a /
only_b) are already observed tokens. This module does not invent
predicates. It joins the closed observation shapes

    Aでは「X」が実測あり
    Bでは実測なし

with a CLOSED connective table bound to structural evidence. Fluency
is out of scope. A connective that has no edge is not placed.

Closed table
    そして   within-bucket juxtaposition (enumeration inside one bundle)
    また     shared-bucket lead-in / 共有束の並置
    一方     only_a → only_b turn (licensed by the diff structure)
    しかし   opposition — ONLY an observed ¬ pair (W1a polarity mark)

Defense 1. 実測あり vs 実測なし is a turn, not opposition. That path
emits 一方 and cannot reach しかし. しかし is constructed in one
function, and that function refuses an empty pair list.

No negative sentence is assembled (no 〜でない / 〜られない). A
¬-prefixed token is quoted as testimony.

Abstaining diffs (INSUFFICIENT_PROFILE / AMBIGUOUS_SENSE) render as
their typed silence with both sides' coverage numbers spoken.

Selection (選択と圧縮 — not fluency)
    Dedup     identical tokens inside one bucket are spoken once.
              The item keeps every layer citation (layers: ["②","⑥"]).
    Bound     each bucket speaks at most 8 items. Rank is ratio desc,
              then layer ①<②<③<④<⑤<⑥, then lex. A remainder is
              spoken as 「ほか n 件が実測あり。」 — counted, never
              silent. A tie that straddles the 8th place drops the
              whole tied-ratio group to the tail (same gate as
              structural_diff._topk).
    Junk      closed gate, listed below. No open filter.

Junk gate (closed)
    Drop a token that has no content character (kanji / kana /
    Latin letter), after stripping a leading ¬ mark.
    Drop a pure figure/reference artifact:
        図 + digits (ASCII or fullwidth)
        表 + digits
        exact: ref, name, nam, thumb, px, file, infobox,
               reported, wikitable, style, class, sub, sup,
               quot, amp, nbsp, サムネイル

## Measured — 30-pair bank, senses+provenance, seed 20260814

    pairs                            30
    RENDER                           23
    INSUFFICIENT_PROFILE             7
    AMBIGUOUS_SENSE                  0
    fork CONNECTIVE_EDGE_LICENSE     pass
    subjects                         1,419,406
    senses                           122,988
    lattice                          527,175 words, 787,333 slots
    extractor                        fugashi
    render_calls                     36          (6 regression + 30 bank)
    wall_seconds                     9.6

    machine
        (a) every connective licensed    697 / 697   PASS
        (b) assembled negation           0           PASS
        (c) しかし                       0  (no observed ¬ pair in the bank)

    connective counts
        そして  611   within-bucket
        また     65   shared-lead-in
        一方     21   bucket-transition
        しかし    0   observed-negation

    21 of 23 RENDERs have only_a and only_b (一方). The two without
    are 川/河川 and 海/海洋 — shared-only, また only. しかし did not
    fire: default profiles carry no ¬ keys. That is honest.

    Eyeball (tools/render_axes_2026-08-14.json, 5 axes, 1/0)
        リンゴ/電気     5 / 5   そして + 一方 + また
        米/光           5 / 5   INSUFFICIENT_PROFILE。米と光。
                                Aの被覆は述語0・面5。Bの被覆は述語0・面2。
        水/音           5 / 5   一方 at only_a→only_b

## Measured — selection fix, same bank, same axes, 2026-08-14

    pairs                            30
    RENDER                           23
    INSUFFICIENT_PROFILE             7
    AMBIGUOUS_SENSE                  0
    fork CONNECTIVE_EDGE_LICENSE     pass
    subjects                         1,419,406
    senses                           122,988
    lattice                          527,175 words, 787,333 slots
    extractor                        fugashi
    render_calls                     39          (9 regression + 30 bank)
    wall_seconds                     9.3

    machine (original three, still)
        (a) every connective licensed    243 / 243   PASS
        (b) assembled negation           0           PASS
        (c) しかし                       0  []        PASS (honest zero)

    machine (selection)
        (d) duplicate tokens spoken      0           PASS
        (e) max bucket enumeration       8  (<= 8)   PASS
        (f) junk tokens spoken           0           PASS

    connective counts
        そして  199   within-bucket
        また     23   shared-lead-in
        一方     21   bucket-transition
        しかし    0   observed-negation

    Eyeball (same 3 pairs, same 5 axes)
        リンゴ/電気     5 / 5   果実 once (layers ①④⑥); 図1 gone;
                                ほか 8 件 / ほか 6 件
        米/光           5 / 5   INSUFFICIENT_PROFILE (unchanged)
        水/音           5 / 5   8 + 8, no tail, 一方
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .polarity import POLARITY_MARK
from .structural_diff import OBSERVED, UNOBSERVED

CONNECTIVE_SOSHITE = "そして"
CONNECTIVE_MATA = "また"
CONNECTIVE_IPPOU = "一方"
CONNECTIVE_SHIKASHI = "しかし"

LICENSE_WITHIN_BUCKET = "within-bucket"
LICENSE_SHARED_LEADIN = "shared-lead-in"
LICENSE_BUCKET_TRANSITION = "bucket-transition"
LICENSE_OBSERVED_NEGATION = "observed-negation"

# Structure-only map. しかし is deliberately absent — opposition is
# not a bucket edge.
CONNECTIVE_TABLE: Dict[str, str] = {
    CONNECTIVE_SOSHITE: LICENSE_WITHIN_BUCKET,
    CONNECTIVE_MATA: LICENSE_SHARED_LEADIN,
    CONNECTIVE_IPPOU: LICENSE_BUCKET_TRANSITION,
}

CLOSED_CONNECTIVES: Tuple[str, ...] = (
    CONNECTIVE_SHIKASHI,
    CONNECTIVE_SOSHITE,
    CONNECTIVE_IPPOU,
    CONNECTIVE_MATA,
)

ABSTAIN_VERDICTS = frozenset({
    "INSUFFICIENT_PROFILE",
    "AMBIGUOUS_SENSE",
})

RENDER = "RENDER"

BUCKET_LIMIT = 8

_LAYER_RANK = {
    "①": 0, "②": 1, "③": 2, "④": 3, "⑤": 4, "⑥": 5,
}

# Closed junk. Figure/table numbers, then the ingest-skip fragments
# that land as tokens. Not an open classifier.
_JUNK_EXACT = frozenset({
    "ref", "name", "nam", "thumb", "px", "file", "infobox",
    "reported", "wikitable", "style", "class", "sub", "sup",
    "quot", "amp", "nbsp", "サムネイル",
})
_JUNK_FIGURE = re.compile(r"^[図表][0-9０-９]+$")
_CONTENT_CHAR = re.compile(r"[A-Za-zぁ-んァ-ヺー㐀-䶿一-鿿々〆〇]")


def is_junk_token(token: str) -> bool:
    """True iff ``token`` fails the closed junk gate."""
    bare = _bare(token or "")
    if not bare:
        return True
    if _JUNK_FIGURE.match(bare):
        return True
    if bare.casefold() in _JUNK_EXACT:
        return True
    if not _CONTENT_CHAR.search(bare):
        return True
    return False


def _layer_rank(layer: str) -> int:
    return _LAYER_RANK.get(layer or "", 9)


def _ratio_of(item: Dict[str, Any], side: str) -> float:
    if side == "shared":
        return min(float(item.get("a_ratio") or 0.0),
                   float(item.get("b_ratio") or 0.0))
    if side == "a":
        return float(item.get("a_ratio") or 0.0)
    return float(item.get("b_ratio") or 0.0)


def _dedup_bucket(
    items: Sequence[Any],
    side: str,
) -> List[Dict[str, Any]]:
    """One row per token. Layers unioned; ratio is the max seen."""
    merged: Dict[str, Dict[str, Any]] = {}
    for raw in items or ():
        if not isinstance(raw, dict):
            continue
        tok = str(raw.get("token") or "")
        if not tok or is_junk_token(tok):
            continue
        ratio = _ratio_of(raw, side)
        layer = str(raw.get("layer") or "")
        rec = merged.get(tok)
        if rec is None:
            merged[tok] = {
                "token": tok,
                "layers": [layer] if layer else [],
                "ratio": ratio,
                "layer": layer,
            }
            continue
        if layer and layer not in rec["layers"]:
            rec["layers"].append(layer)
        if ratio > rec["ratio"]:
            rec["ratio"] = ratio
        if _layer_rank(layer) < _layer_rank(rec["layer"]):
            rec["layer"] = layer
    out = []
    for rec in merged.values():
        rec["layers"] = sorted(set(rec["layers"]), key=_layer_rank)
        out.append(rec)
    return out


def _bound_bucket(
    items: Sequence[Dict[str, Any]],
    k: int = BUCKET_LIMIT,
) -> Tuple[List[Dict[str, Any]], int]:
    """Keep at most ``k``. A ratio tie on the cut goes to the tail."""
    ranked = sorted(
        items,
        key=lambda it: (-it["ratio"], _layer_rank(it["layer"]), it["token"]),
    )
    if len(ranked) <= k:
        return ranked, 0
    if ranked[k - 1]["ratio"] == ranked[k]["ratio"]:
        tied = ranked[k - 1]["ratio"]
        kept = [it for it in ranked if it["ratio"] > tied]
        return kept, len(ranked) - len(kept)
    return ranked[:k], len(ranked) - k


def select_bucket(
    items: Sequence[Any],
    side: str,
    k: int = BUCKET_LIMIT,
) -> Tuple[List[Dict[str, Any]], int]:
    """Junk → dedup → rank → bound. Returns (spoken items, tail count)."""
    return _bound_bucket(_dedup_bucket(items, side), k)


def _is_observed_negation(token: str) -> bool:
    return bool(token) and token.startswith(POLARITY_MARK) and len(token) > len(POLARITY_MARK)


def _bare(token: str) -> str:
    if _is_observed_negation(token):
        return token[len(POLARITY_MARK):]
    return token


def _opposition_pairs(
    left: Sequence[str],
    right: Sequence[str],
) -> List[Tuple[str, str]]:
    """(¬T, T) where one side wrote the mark and the other asserts T."""
    right_set = set(right)
    left_set = set(left)
    pairs: List[Tuple[str, str]] = []
    seen = set()
    for tok in left:
        if not _is_observed_negation(tok):
            continue
        bare = _bare(tok)
        if bare in right_set:
            key = (tok, bare)
            if key not in seen:
                seen.add(key)
                pairs.append(key)
    for tok in right:
        if not _is_observed_negation(tok):
            continue
        bare = _bare(tok)
        if bare in left_set:
            key = (tok, bare)
            if key not in seen:
                seen.add(key)
                pairs.append(key)
    return pairs


def _emit(connective: str) -> Dict[str, str]:
    """Table lookup. しかし cannot pass."""
    if connective == CONNECTIVE_SHIKASHI:
        raise RuntimeError("しかし is not table-emitted")
    license = CONNECTIVE_TABLE[connective]
    return {"connective": connective, "license": license}


def _license_shikashi(pairs: Sequence[Tuple[str, str]]) -> Dict[str, Any]:
    """The only constructor for しかし. Empty pairs are a hard refuse."""
    if not pairs:
        raise RuntimeError("しかし is unreachable without an observed ¬ pair")
    checked: List[List[str]] = []
    for neg, pos in pairs:
        if not _is_observed_negation(neg) or _bare(neg) != pos:
            raise RuntimeError("しかし pair is not an ObservedNegation mark")
        checked.append([neg, pos])
    return {
        "connective": CONNECTIVE_SHIKASHI,
        "license": LICENSE_OBSERVED_NEGATION,
        "pairs": checked,
    }


def _atom_observed(subject: str, token: str) -> str:
    return "%sでは「%s」が%s" % (subject, token, OBSERVED)


def _atom_unobserved(subject: str) -> str:
    return "%sでは%s" % (subject, UNOBSERVED)


def _exclusive_item(observed_side: str, token: str, other_side: str) -> str:
    return _atom_observed(observed_side, token) + "。" + _atom_unobserved(other_side)


def _shared_item(a: str, b: str, token: str) -> str:
    return _atom_observed(a, token) + "。" + _atom_observed(b, token)


def _coverage_of(diff_result: Dict[str, Any]) -> Dict[str, Any]:
    cov = diff_result.get("coverage") or {}
    a = cov.get("a") or {}
    b = cov.get("b") or {}
    return {
        "a": {
            "predicates": int(a.get("predicates") or 0),
            "facets": int(a.get("facets") or 0),
        },
        "b": {
            "predicates": int(b.get("predicates") or 0),
            "facets": int(b.get("facets") or 0),
        },
    }


def _speak_coverage(cov: Dict[str, Any]) -> str:
    return (
        "Aの被覆は述語%d・面%d。Bの被覆は述語%d・面%d。"
        % (cov["a"]["predicates"], cov["a"]["facets"],
           cov["b"]["predicates"], cov["b"]["facets"])
    )


def _sense_cores(rec: Any) -> List[str]:
    if not isinstance(rec, dict):
        return []
    named = rec.get("senses")
    if isinstance(named, list) and named:
        cores = []
        for it in named:
            if isinstance(it, dict) and it.get("core"):
                cores.append(str(it["core"]))
        return cores
    cores = []
    if rec.get("core"):
        cores.append(str(rec["core"]))
    for it in rec.get("other_senses") or []:
        if isinstance(it, dict) and it.get("core"):
            cores.append(str(it["core"]))
    return cores


def _speak_abstention(diff_result: Dict[str, Any], verdict: str) -> str:
    a = str(diff_result.get("a") or "")
    b = str(diff_result.get("b") or "")
    cov = _coverage_of(diff_result)
    parts = [verdict + "。"]
    if a or b:
        parts.append("%sと%s。" % (a, b))
    senses = diff_result.get("senses") or {}
    if verdict == "AMBIGUOUS_SENSE" and isinstance(senses, dict):
        ca = _sense_cores(senses.get("a"))
        cb = _sense_cores(senses.get("b"))
        if ca:
            parts.append("Aの語義は%s。" % "、".join(ca))
        if cb:
            parts.append("Bの語義は%s。" % "、".join(cb))
    parts.append(_speak_coverage(cov))
    return "".join(parts)


def _join(chunks: List[str]) -> str:
    text = "".join(chunks)
    if text and not text.endswith("。"):
        text += "。"
    return text


def render_diff(diff_result: Dict[str, Any]) -> Dict[str, Any]:
    """Skeleton text + per-connective licenses from a structural diff.

    Abstentions stay typed. A DIFF with empty buckets is still a
    RENDER (no connective is invented to fill the silence).
    """
    src = dict(diff_result or {})
    verdict = str(src.get("verdict") or "")
    cov = _coverage_of(src)
    a = str(src.get("a") or "")
    b = str(src.get("b") or "")
    base: Dict[str, Any] = {
        "a": a,
        "b": b,
        "canonical": src.get("canonical") or {"a": a, "b": b},
        "coverage": cov,
        "source_verdict": verdict,
        "connectives": [],
        "text": "",
    }
    if src.get("senses") is not None:
        base["senses"] = src["senses"]
    if src.get("abstain") is not None:
        base["abstain"] = src["abstain"]

    if verdict in ABSTAIN_VERDICTS:
        base["verdict"] = verdict
        base["text"] = _speak_abstention(src, verdict)
        return base

    kept_a, tail_a = select_bucket(src.get("only_a") or [], "a")
    kept_b, tail_b = select_bucket(src.get("only_b") or [], "b")
    kept_s, tail_s = select_bucket(src.get("shared") or [], "shared")
    only_a = [it["token"] for it in kept_a]
    only_b = [it["token"] for it in kept_b]
    shared = [it["token"] for it in kept_s]
    a_present = bool(only_a) or tail_a > 0
    b_present = bool(only_b) or tail_b > 0
    s_present = bool(shared) or tail_s > 0
    pairs = _opposition_pairs(only_a, only_b)

    chunks: List[str] = []
    licenses: List[Dict[str, Any]] = []

    def add_item(segment: str, connective: Optional[Dict[str, Any]]) -> None:
        if connective is not None:
            chunks.append(connective["connective"])
            licenses.append(connective)
        chunks.append(segment)
        if not segment.endswith("。"):
            chunks.append("。")

    def add_tail(n: int) -> None:
        if n > 0:
            chunks.append("ほか %d 件が実測あり。" % n)

    for i, tok in enumerate(only_a):
        conn = _emit(CONNECTIVE_SOSHITE) if i else None
        add_item(_exclusive_item(a, tok, b), conn)
    add_tail(tail_a)

    if a_present and b_present:
        if pairs:
            trans: Optional[Dict[str, Any]] = _license_shikashi(pairs)
        else:
            trans = _emit(CONNECTIVE_IPPOU)
    else:
        trans = None

    for i, tok in enumerate(only_b):
        if i == 0:
            conn = trans
            trans = None
        else:
            conn = _emit(CONNECTIVE_SOSHITE)
        add_item(_exclusive_item(b, tok, a), conn)
    if trans is not None:
        # only_b was all tail; the turn still sits before the count.
        chunks.append(trans["connective"])
        licenses.append(trans)
    add_tail(tail_b)

    shared_lead = s_present and (a_present or b_present)
    for i, tok in enumerate(shared):
        if i == 0 and shared_lead:
            conn = _emit(CONNECTIVE_MATA)
        elif i:
            conn = _emit(CONNECTIVE_MATA)
        else:
            conn = None
        add_item(_shared_item(a, b, tok), conn)
    if shared_lead and not shared and tail_s:
        rec = _emit(CONNECTIVE_MATA)
        chunks.append(rec["connective"])
        licenses.append(rec)
    add_tail(tail_s)

    def _item_out(it: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "token": it["token"],
            "layers": list(it["layers"]),
            "ratio": it["ratio"],
        }

    base["verdict"] = RENDER
    base["text"] = _join(chunks)
    base["connectives"] = licenses
    base["items"] = {
        "only_a": [_item_out(it) for it in kept_a],
        "only_b": [_item_out(it) for it in kept_b],
        "shared": [_item_out(it) for it in kept_s],
    }
    base["tail"] = {"only_a": tail_a, "only_b": tail_b, "shared": tail_s}
    return base


def render_summary(summary_result: Dict[str, Any]) -> Dict[str, Any]:
    """Optional path: summarize claim lists, same closed table.

    Kept claims are one bundle — juxtaposition is そして. A typed
    summarize refusal is spoken, not rewritten into a claim.
    """
    src = dict(summary_result or {})
    verdict = str(src.get("verdict") or "")
    out: Dict[str, Any] = {
        "verdict": verdict,
        "connectives": [],
        "text": "",
        "source_verdict": verdict,
    }
    if verdict != "SUMMARY":
        note = str(src.get("note") or "")
        held = src.get("held") or []
        parts = [verdict + "。"]
        if held:
            parts.append("主題は%s。" % "、".join(str(s) for s in held))
        if note:
            parts.append(note if note.endswith("。") else note + "。")
        out["text"] = "".join(parts)
        return out

    kept = src.get("kept") or []
    chunks: List[str] = []
    licenses: List[Dict[str, Any]] = []
    for i, claim in enumerate(kept):
        if not isinstance(claim, dict):
            continue
        subj = str(claim.get("subject") or "")
        pair = claim.get("pair") or []
        f1 = str(pair[0]) if len(pair) > 0 else ""
        f2 = str(pair[1]) if len(pair) > 1 else ""
        if not (subj and f1 and f2):
            continue
        seg = "%s: %s と %s（同一文）" % (subj, f1, f2)
        if i and chunks:
            rec = _emit(CONNECTIVE_SOSHITE)
            chunks.append(rec["connective"])
            licenses.append(rec)
        chunks.append(seg)
        chunks.append("。")
    out["verdict"] = RENDER
    out["text"] = _join(chunks)
    out["connectives"] = licenses
    return out


def regression() -> Dict[str, Any]:
    """Fork-equivalent: licenses, defense 1, しかし unreachable, abstention."""
    from .cross_store import CrossStore
    from .lattice import build
    from .structural_diff import diff

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

    raw = diff("りんご", "電気", profiles=profiles, aliases=aliases,
               lattice=lat, shelf=shelf, k=8, min_profile=3)
    hit = render_diff(raw)
    conns = [c["connective"] for c in hit["connectives"]]
    licenses = {c["connective"]: c["license"] for c in hit["connectives"]}
    hit_ok = (
        hit["verdict"] == RENDER
        and "りんご" in hit["text"] and "電気" in hit["text"]
        and CONNECTIVE_IPPOU in conns
        and licenses.get(CONNECTIVE_IPPOU) == LICENSE_BUCKET_TRANSITION
        and CONNECTIVE_SHIKASHI not in conns
        and CONNECTIVE_SHIKASHI not in hit["text"]
        and OBSERVED in hit["text"] and UNOBSERVED in hit["text"]
        and all(c.get("license") for c in hit["connectives"])
        and CONNECTIVE_SHIKASHI not in CONNECTIVE_TABLE
    )
    if CONNECTIVE_SOSHITE in conns:
        hit_ok = hit_ok and licenses[CONNECTIVE_SOSHITE] == LICENSE_WITHIN_BUCKET
    if CONNECTIVE_MATA in conns:
        hit_ok = hit_ok and licenses[CONNECTIVE_MATA] == LICENSE_SHARED_LEADIN

    thin = render_diff(diff(
        "薄", "電気", profiles=profiles, aliases=aliases,
        lattice=lat, shelf=shelf, k=8, min_profile=3,
    ))
    thin_ok = (
        thin["verdict"] == "INSUFFICIENT_PROFILE"
        and "INSUFFICIENT_PROFILE" in thin["text"]
        and "述語" in thin["text"]
        and str(thin["coverage"]["a"]["predicates"]) in thin["text"]
        and str(thin["coverage"]["b"]["predicates"]) in thin["text"]
        and str(thin["coverage"]["a"]["facets"]) in thin["text"]
        and str(thin["coverage"]["b"]["facets"]) in thin["text"]
        and thin["connectives"] == []
        and CONNECTIVE_SHIKASHI not in thin["text"]
    )

    toy_senses = {
        "水 (曖昧さ回避)": [
            {"core": "水 (曖昧さ回避)", "domain_tag": "曖昧さ回避",
             "lead_tokens": []},
        ],
    }
    dab = render_diff(diff(
        "水 (曖昧さ回避)", "電気", profiles=profiles, aliases=aliases,
        lattice=lat, shelf=shelf, k=8, min_profile=3, senses=toy_senses,
    ))
    dab_ok = (
        dab["verdict"] == "AMBIGUOUS_SENSE"
        and "AMBIGUOUS_SENSE" in dab["text"]
        and "水 (曖昧さ回避)" in dab["text"]
        and "電気" in dab["text"]
        and "述語" in dab["text"]
        and dab["connectives"] == []
    )

    # Hand-built ¬ pair. structural_diff is not modified; the mark is
    # W1a testimony already sitting on a token.
    opposed = render_diff({
        "a": "川", "b": "湖",
        "canonical": {"a": "川", "b": "湖"},
        "verdict": "DIFF",
        "coverage": {
            "a": {"predicates": 3, "facets": 3},
            "b": {"predicates": 3, "facets": 3},
        },
        "shared": [],
        "only_a": [{"token": POLARITY_MARK + "流れる"}],
        "only_b": [{"token": "流れる"}],
        "abstain": {},
    })
    shikashi = [c for c in opposed["connectives"]
                if c["connective"] == CONNECTIVE_SHIKASHI]
    opposed_ok = (
        opposed["verdict"] == RENDER
        and len(shikashi) == 1
        and shikashi[0]["license"] == LICENSE_OBSERVED_NEGATION
        and shikashi[0]["pairs"] == [[POLARITY_MARK + "流れる", "流れる"]]
        and CONNECTIVE_IPPOU not in opposed["text"]
        and CONNECTIVE_SHIKASHI in opposed["text"]
        and (POLARITY_MARK + "流れる") in opposed["text"]
        and "でない" not in opposed["text"].replace("「" + POLARITY_MARK + "流れる」", "")
    )

    # Absence vs presence is not opposition.
    absence = render_diff({
        "a": "川", "b": "湖",
        "verdict": "DIFF",
        "coverage": {
            "a": {"predicates": 3, "facets": 0},
            "b": {"predicates": 3, "facets": 0},
        },
        "shared": [],
        "only_a": [{"token": "流れる"}],
        "only_b": [{"token": "凍る"}],
        "abstain": {},
    })
    absence_ok = (
        CONNECTIVE_IPPOU in absence["text"]
        and CONNECTIVE_SHIKASHI not in absence["text"]
        and all(c["connective"] != CONNECTIVE_SHIKASHI
                for c in absence["connectives"])
    )

    shikashi_blocked = False
    try:
        _license_shikashi([])
    except RuntimeError:
        shikashi_blocked = True

    table_ok = CONNECTIVE_SHIKASHI not in CONNECTIVE_TABLE
    emit_blocked = False
    try:
        _emit(CONNECTIVE_SHIKASHI)
    except RuntimeError:
        emit_blocked = True

    shared_only = render_diff({
        "a": "川", "b": "河川",
        "verdict": "DIFF",
        "coverage": {
            "a": {"predicates": 4, "facets": 4},
            "b": {"predicates": 4, "facets": 4},
        },
        "shared": [{"token": "水流"}, {"token": "地理"}],
        "only_a": [],
        "only_b": [],
        "abstain": {},
    })
    shared_ok = (
        CONNECTIVE_MATA in shared_only["text"]
        and all(c["license"] == LICENSE_SHARED_LEADIN
                for c in shared_only["connectives"])
        and CONNECTIVE_IPPOU not in shared_only["text"]
        and "川" in shared_only["text"] and "河川" in shared_only["text"]
    )

    summary = render_summary({
        "verdict": "SUMMARY",
        "kept": [
            {"subject": "中断", "pair": ["停止", "更新"]},
            {"subject": "中断", "pair": ["完成猶予", "更新"]},
        ],
    })
    summary_ok = (
        summary["verdict"] == RENDER
        and CONNECTIVE_SOSHITE in summary["text"]
        and all(c["license"] == LICENSE_WITHIN_BUCKET
                for c in summary["connectives"])
    )
    silent = render_summary({
        "verdict": "UNKNOWN_NO_CROSSING",
        "held": ["殺人罪", "超伝導"],
        "note": "no facet is shared by two subjects",
    })
    silent_ok = (
        silent["verdict"] == "UNKNOWN_NO_CROSSING"
        and "UNKNOWN_NO_CROSSING" in silent["text"]
        and silent["connectives"] == []
    )

    assembled = ("でない", "ではない", "られない", "しない")

    def _outside_quotes(text: str) -> str:
        out = []
        depth = 0
        for ch in text:
            if ch == "「":
                depth += 1
                continue
            if ch == "」" and depth:
                depth -= 1
                continue
            if depth == 0:
                out.append(ch)
        return "".join(out)

    texts = [hit["text"], thin["text"], dab["text"], opposed["text"],
             absence["text"], shared_only["text"], summary["text"]]
    no_assembly = all(
        not any(p in _outside_quotes(t) for p in assembled) for t in texts
    )

    # Selection: dedup, bound, junk. Spoken once; layers kept.
    dup_src = {
        "a": "リンゴ", "b": "電気", "verdict": "DIFF",
        "coverage": {
            "a": {"predicates": 3, "facets": 3},
            "b": {"predicates": 3, "facets": 3},
        },
        "shared": [],
        "only_a": [
            {"token": "果実", "layer": "②", "a_ratio": 0.4, "b_ratio": 0.0},
            {"token": "果実", "layer": "⑥", "a_ratio": 0.2, "b_ratio": 0.0},
            {"token": "図1", "layer": "④", "a_ratio": 0.9, "b_ratio": 0.0},
            {"token": "科リンゴ", "layer": "⑥", "a_ratio": 0.1, "b_ratio": 0.0},
        ],
        "only_b": [{"token": "電荷", "layer": "②", "a_ratio": 0.0, "b_ratio": 0.5}],
        "abstain": {},
    }
    dup = render_diff(dup_src)
    fruit = [it for it in dup["items"]["only_a"] if it["token"] == "果実"]
    spoken_a = [it["token"] for it in dup["items"]["only_a"]]
    dup_ok = (
        spoken_a.count("果実") == 1
        and fruit[0]["layers"] == ["②", "⑥"]
        and "図1" not in dup["text"]
        and "図1" not in spoken_a
        and is_junk_token("図1")
        and not is_junk_token("果実")
        and dup["text"].count("「果実」") == 1
    )

    many = render_diff({
        "a": "A", "b": "B", "verdict": "DIFF",
        "coverage": {
            "a": {"predicates": 12, "facets": 0},
            "b": {"predicates": 3, "facets": 0},
        },
        "shared": [],
        "only_a": [
            {"token": "項%d" % i, "layer": "②",
             "a_ratio": 1.0 - i * 0.01, "b_ratio": 0.0}
            for i in range(12)
        ],
        "only_b": [{"token": "対", "layer": "②", "a_ratio": 0.0, "b_ratio": 1.0}],
        "abstain": {},
    })
    bound_ok = (
        len(many["items"]["only_a"]) == 8
        and many["tail"]["only_a"] == 4
        and "ほか 4 件が実測あり。" in many["text"]
    )

    tied = render_diff({
        "a": "A", "b": "B", "verdict": "DIFF",
        "coverage": {
            "a": {"predicates": 10, "facets": 0},
            "b": {"predicates": 3, "facets": 0},
        },
        "shared": [],
        "only_a": [
            {"token": "同%d" % i, "layer": "②",
             "a_ratio": 0.5, "b_ratio": 0.0}
            for i in range(10)
        ],
        "only_b": [],
        "abstain": {},
    })
    tie_ok = (
        tied["items"]["only_a"] == []
        and tied["tail"]["only_a"] == 10
        and "ほか 10 件が実測あり。" in tied["text"]
        and "「同" not in tied["text"]
    )

    ok = all([
        hit_ok, thin_ok, dab_ok, opposed_ok, absence_ok,
        shikashi_blocked, table_ok, emit_blocked, shared_ok,
        summary_ok, silent_ok, no_assembly,
        dup_ok, bound_ok, tie_ok,
    ])
    return {
        "experiment": "connective_render",
        "fork": "CONNECTIVE_EDGE_LICENSE",
        "pass": bool(ok),
        "result": {
            "hit_connectives": hit["connectives"],
            "thin": thin["verdict"],
            "dab": dab["verdict"],
            "shikashi_pairs": shikashi[0]["pairs"] if shikashi else [],
            "absence_has_shikashi": CONNECTIVE_SHIKASHI in absence["text"],
            "shikashi_blocked": shikashi_blocked,
            "table_excludes_shikashi": table_ok,
            "dedup_layers": fruit[0]["layers"] if fruit else [],
            "bound_tail": many["tail"]["only_a"],
            "tie_tail": tied["tail"]["only_a"],
        },
    }
