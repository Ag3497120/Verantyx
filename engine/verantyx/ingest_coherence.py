"""Ingest-time coherence check — a ledger, never a censor.

SPEC_2026-08-14_meaning_layers 納品3. A new subject's normalized
predicate profile is compared to the mean normalized profile of its
lattice-kin family. Deviation above the threshold is recorded as
COHERENCE_ANOMALY. The check never blocks ingestion: it returns a
record; the caller may append that record to a sidecar JSONL ledger.
Nothing here enters a census or a vote store.

Deviation measure (fixed for this measurement)
    1 − cosine over L1-normalized predicate vectors, missing keys
    treated as 0 (equivalently: restricted to the union support).
    Range [0, 1] on non-negative mass. No learned component.

Preregistered defaults (chosen from the measure's geometry, before
any corpus sweep; not moved after the curve is seen)
    threshold   0.70    1−cosine > 0.70 means cosine ≤ 0.30, closer
                        to orthogonal than to family alignment.
                        Intended to flag 伝導するりんご (a subject
                        wearing another family's predicates) and to
                        pass a subject that still shares directional
                        mass with its kin mean.
    min_family  3       same floor as structural_diff's min_profile.
                        Fewer usable kin is NO_FAMILY, an abstention,
                        never a pass.

Silence is typed. A family that cannot be drawn, or that has fewer
than min_family members with a normalizable profile, is NO_FAMILY.
A subject with no positive predicate mass is INSUFFICIENT_PROFILE.
Exact equality at the threshold is TIE (同点は棄権).

Measurement is tools/measure_ingest_coherence.py. The default was
not moved after the curve.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .lattice import kin

MEASURE = "1-cosine"
DEFAULT_THRESHOLD = 0.70
DEFAULT_MIN_FAMILY = 3

LEDGER = (corpus_root() / "build"
          / "ingest_coherence_ledger.jsonl")

VERDICT_COHERENT = "COHERENT"
VERDICT_ANOMALY = "COHERENCE_ANOMALY"
VERDICT_NO_FAMILY = "NO_FAMILY"
VERDICT_INSUFFICIENT = "INSUFFICIENT_PROFILE"
VERDICT_TIE = "TIE"


def _counts(predicates: Any) -> Dict[str, float]:
    if not predicates:
        return {}
    if (isinstance(predicates, dict)
            and "predicates" in predicates
            and isinstance(predicates["predicates"], dict)):
        predicates = predicates["predicates"]
    if not isinstance(predicates, dict):
        return {}
    out: Dict[str, float] = {}
    for pred, n in predicates.items():
        if not pred:
            continue
        mass = float(n)
        if mass > 0:
            out[str(pred)] = mass
    return out


def _normalize(counts: Dict[str, float]) -> Dict[str, float]:
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in counts.items()}


def _profile_of(profiles: Dict[str, Any], subject: str) -> Dict[str, float]:
    rec = (profiles or {}).get(subject)
    if not isinstance(rec, dict):
        return {}
    return _counts(rec.get("predicates") or rec)


def _cosine_deviation(p: Dict[str, float], q: Dict[str, float]) -> Optional[float]:
    """1 − cosine on the union support; None if either vector is empty."""
    if not p or not q:
        return None
    keys = set(p) | set(q)
    dot = 0.0
    np2 = 0.0
    nq2 = 0.0
    for k in keys:
        a = p.get(k, 0.0)
        b = q.get(k, 0.0)
        dot += a * b
        np2 += a * a
        nq2 += b * b
    if np2 <= 0.0 or nq2 <= 0.0:
        return None
    cos = dot / ((np2 ** 0.5) * (nq2 ** 0.5))
    if cos > 1.0:
        cos = 1.0
    elif cos < 0.0:
        cos = 0.0
    return 1.0 - cos


def family_members(
    subject: str,
    *,
    profiles: Dict[str, Any],
    lattice: Any,
    min_family: int = DEFAULT_MIN_FAMILY,
) -> Tuple[List[str], List[str], Optional[str]]:
    """Usable kin of ``subject``.

    Returns ``(members, slots, why)``. ``why`` is NO_FAMILY when the
    lattice yields no slots or fewer than ``min_family`` members have a
    normalizable profile. Members are unique, the subject excluded,
    deterministic order (slot key, then word).
    """
    if lattice is None or not subject:
        return [], [], VERDICT_NO_FAMILY
    families = kin(lattice, subject)
    if not families:
        return [], [], VERDICT_NO_FAMILY
    slots = sorted(families)
    seen = set()
    members: List[str] = []
    for slot in slots:
        for word in families[slot]:
            if not word or word == subject or word in seen:
                continue
            seen.add(word)
            if _normalize(_profile_of(profiles, word)):
                members.append(word)
    if len(members) < min_family:
        return [], slots, VERDICT_NO_FAMILY
    return members, slots, None


def _family_mean(
    members: List[str],
    profiles: Dict[str, Any],
) -> Dict[str, float]:
    acc: Dict[str, float] = {}
    used = 0
    for word in members:
        norm = _normalize(_profile_of(profiles, word))
        if not norm:
            continue
        used += 1
        for pred, ratio in norm.items():
            acc[pred] = acc.get(pred, 0.0) + ratio
    if used == 0:
        return {}
    return {pred: mass / used for pred, mass in acc.items()}


def _rounded(norm: Dict[str, float]) -> Dict[str, float]:
    return {k: round(v, 6) for k, v in sorted(norm.items())}


def check(
    subject: str,
    predicates: Any,
    *,
    profiles: Dict[str, Any],
    lattice: Any,
    min_family: int = DEFAULT_MIN_FAMILY,
    threshold: float = DEFAULT_THRESHOLD,
) -> Dict[str, Any]:
    """Compare a new subject's profile to its kin-family mean.

    Always returns a record. Never raises on anomaly, never writes the
    ledger, never refuses ingestion. ``blocks_ingest`` is always False.
    """
    subj_norm = _normalize(_counts(predicates))
    members, slots, why = family_members(
        subject, profiles=profiles, lattice=lattice, min_family=min_family,
    )
    mean = _family_mean(members, profiles) if members else {}
    deviation = _cosine_deviation(subj_norm, mean) if subj_norm and mean else None

    if not subj_norm:
        verdict = VERDICT_INSUFFICIENT
        reason = VERDICT_INSUFFICIENT
    elif why:
        verdict = why
        reason = why
    elif not mean or deviation is None:
        verdict = VERDICT_INSUFFICIENT
        reason = VERDICT_INSUFFICIENT
    elif deviation > threshold:
        verdict = VERDICT_ANOMALY
        reason = None
    elif deviation < threshold:
        verdict = VERDICT_COHERENT
        reason = None
    else:
        verdict = VERDICT_TIE
        reason = VERDICT_TIE

    union_n = len(set(subj_norm) | set(mean)) if subj_norm and mean else 0
    return {
        "subject": subject,
        "verdict": verdict,
        "reason": reason,
        "deviation": None if deviation is None else round(float(deviation), 6),
        "threshold": float(threshold),
        "measure": MEASURE,
        "min_family": int(min_family),
        "family_size": len(members),
        "family_slots": slots,
        "family_members": members,
        "coverage": {
            "subject_predicates": len(subj_norm),
            "family_members": len(members),
            "union_support": union_n,
        },
        "profile": _rounded(subj_norm),
        "family_mean": _rounded(mean),
        "blocks_ingest": False,
    }


def ledger_append(record: Dict[str, Any], path: Optional[Path] = None) -> Path:
    """Append one record as JSONL. Sidecar only; not a census write."""
    dest = Path(path) if path is not None else LEDGER
    dest.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with dest.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return dest


def regression() -> Dict[str, Any]:
    """Fork-equivalent: 伝導するりんご on a toy lattice. No corpus."""
    import tempfile

    from .lattice import build

    profiles = {
        "果実": {"predicates": {"食用である": 2, "栽培される": 1, "である": 1},
                 "total": 4},
        "果樹": {"predicates": {"栽培される": 2, "実る": 1, "である": 1},
                 "total": 4},
        "果汁": {"predicates": {"搾られる": 1, "食用である": 1, "である": 1},
                 "total": 3},
        "果肉": {"predicates": {"食用である": 2, "含まれる": 1, "である": 1},
                 "total": 4},
        "電気": {"predicates": {"流れる": 2, "発生する": 2, "である": 1},
                 "total": 5},
        "電子": {"predicates": {"帯電する": 1, "流れる": 1, "である": 1},
                 "total": 3},
        "電荷": {"predicates": {"帯電する": 2, "生じる": 1, "である": 1},
                 "total": 4},
        "電流": {"predicates": {"流れる": 3, "生じる": 1, "である": 1},
                 "total": 5},
    }
    lat = build(list(profiles) + ["果糖", "糖度"])

    fruit = {"食用である": 2, "栽培される": 1, "である": 1}
    electric = dict(profiles["電気"]["predicates"])

    clean = check("果糖", fruit, profiles=profiles, lattice=lat)
    swapped = check("果糖", electric, profiles=profiles, lattice=lat)
    lonely = check("糖度", fruit, profiles=profiles, lattice=lat)
    empty = check("果糖", {}, profiles=profiles, lattice=lat)
    thin_lat = build(["果実", "果樹", "果糖"])
    thin = check(
        "果糖", fruit,
        profiles={k: profiles[k] for k in ("果実", "果樹")},
        lattice=thin_lat, min_family=3,
    )

    ledger_path = Path(tempfile.mkdtemp()) / "ledger.jsonl"
    missing_before = not LEDGER.exists() or LEDGER.stat().st_size == 0
    # check must not create or grow the default ledger.
    size_before = LEDGER.stat().st_size if LEDGER.exists() else None
    check("果糖", electric, profiles=profiles, lattice=lat)
    size_after = LEDGER.stat().st_size if LEDGER.exists() else None
    no_write = size_before == size_after
    if missing_before and size_after is None:
        no_write = True

    ledger_append(swapped, ledger_path)
    ledger_append(clean, ledger_path)
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    ledger_ok = (
        len(lines) == 2
        and json.loads(lines[0])["verdict"] == VERDICT_ANOMALY
        and json.loads(lines[1])["verdict"] == VERDICT_COHERENT
    )

    ok = all([
        clean["verdict"] == VERDICT_COHERENT,
        swapped["verdict"] == VERDICT_ANOMALY,
        lonely["verdict"] == VERDICT_NO_FAMILY,
        empty["verdict"] == VERDICT_INSUFFICIENT,
        thin["verdict"] == VERDICT_NO_FAMILY,
        clean["blocks_ingest"] is False,
        swapped["blocks_ingest"] is False,
        lonely["blocks_ingest"] is False,
        no_write,
        ledger_ok,
        swapped["measure"] == MEASURE,
        swapped["threshold"] == DEFAULT_THRESHOLD,
    ])
    return {
        "experiment": "ingest_coherence",
        "fork": "INGEST_COHERENCE_LEDGER",
        "pass": bool(ok),
        "result": {
            "clean": clean["verdict"],
            "swapped": swapped["verdict"],
            "swapped_deviation": swapped["deviation"],
            "lonely": lonely["verdict"],
            "empty": empty["verdict"],
            "thin": thin["verdict"],
            "no_default_ledger_write": no_write,
            "ledger_lines": len(lines),
        },
    }
