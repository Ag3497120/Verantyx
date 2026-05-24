#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Phase 29: Boundary graph -> conjecture (theorem candidate) generator.

Goal:
- Find "real verified counterexamples" in the KB (counterexample_schema entries whose refutation is verified).
- Extract boundary signatures from refutation fields:
  Domain / Dropped Assumption / Failure Point / Structure (Phase E format)
- Generate conjecture entries (kind="theorem" but tagged as status:conjecture) as KB-appendable JSONL.

Robustness:
- Verified tags may exist in:
  - patterns (preferred)
  - patch_note (string)
  - yields / prerequisites (arrays)
  - statement/refutation (string)  [fallback, last resort]
- Verified tag variants:
  - min_verified:real_true, min_verified:true, min_verified:verified, theorem_verified:true (etc)
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

# ---------------- IO ----------------

def read_jsonl(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out

def write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

# ---------------- Tag detection ----------------

VERIFIED_POSITIVE_TAGS = [
    "min_verified:real_true",
    "min_verified:true",
    "min_verified:verified",
    "refutation_verified:true",
    "verified:true",
    "real_verified:true",
    "phase27.1 verified",
    "phase28.4 real_verified",
]

VERIFIED_NEGATIVE_TAGS = [
    "min_verified:real_false",
    "min_verified:false",
    "refutation_verified:false",
    "verified:false",
    "real_verified:false",
]

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())

def _contains_any(hay: str, needles: List[str]) -> bool:
    h = _norm(hay)
    for n in needles:
        if _norm(n) in h:
            return True
    return False

def is_verified_counterexample(entry: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Returns (is_verified_true_counterexample, reason)
    True means: this entry is a counterexample_schema and its refutation is verified as a real counterexample.
    """

    if entry.get("kind") != "counterexample_schema":
        return (False, "kind!=counterexample_schema")

    # Gather all possible text sources
    sources: List[str] = []

    # patterns
    pats = entry.get("patterns")
    if isinstance(pats, list):
        sources.extend([str(x) for x in pats if isinstance(x, (str, int, float))])

    # patch_note / note fields (common in your pipeline)
    for k in ["patch_note", "note", "audit_note", "meta_note"]:
        v = entry.get(k)
        if isinstance(v, str) and v.strip():
            sources.append(v)

    # yields / prerequisites often used as tags
    for k in ["yields", "prerequisites"]:
        v = entry.get(k)
        if isinstance(v, list):
            sources.extend([str(x) for x in v if isinstance(x, (str, int, float))])

    # refutation sometimes includes tags after Phase E
    ref = entry.get("refutation")
    if isinstance(ref, str) and ref.strip():
        sources.append(ref)

    # statement fallback
    st = entry.get("statement")
    if isinstance(st, str) and st.strip():
        sources.append(st)

    blob = " | ".join(sources)

    # If explicitly negative, it's not a verified true counterexample
    if _contains_any(blob, VERIFIED_NEGATIVE_TAGS):
        return (False, "explicit_negative_tag")

    # Positive evidence
    if _contains_any(blob, VERIFIED_POSITIVE_TAGS):
        return (True, "positive_tag_match")

    # Final fallback: sometimes patterns contain "min_verified:real_true" but broken into tokens
    # e.g. "min_verified", "real_true"
    if "min_verified" in _norm(blob) and ("real_true" in _norm(blob) or "true" in _norm(blob)):
        return (True, "fallback_min_verified_true_tokens")

    return (False, "no_verified_tag_found")

# ---------------- Refutation field extraction (Phase E format) ----------------

KEY_PAT = {
    "domain": re.compile(r"\bDomain\s*:\s*(.+)", re.IGNORECASE),
    "dropped": re.compile(r"\bDropped\s*Assumption\s*:\s*(.+)", re.IGNORECASE),
    "failure": re.compile(r"\bFailure\s*Point\s*:\s*(.+)", re.IGNORECASE),
    "structure": re.compile(r"\bStructure\s*:\s*(.+)", re.IGNORECASE),
}

def extract_refutation_fields(ref_text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, pat in KEY_PAT.items():
        m = pat.search(ref_text)
        if m:
            out[k] = m.group(1).strip()
    return out

def normalize_assumption(a: str) -> str:
    a = a.strip()
    a = re.sub(r"\s+", "_", a)
    a = a.replace("assume:", "").replace("property:", "")
    return a

# ---------------- Domain prefix + ID allocation ----------------

def domain_prefix(domain: str) -> str:
    # Accept common variants
    d = domain.strip().lower()
    mapping = {
        "propositional_logic": "prop",
        "prop": "prop",
        "first_order_logic": "fol",
        "fol": "fol",
        "model_theory": "mt",
        "mt": "mt",
        "modal_logic": "modal",
        "modal": "modal",
        "computational_complexity": "comp",
        "complexity": "comp",
        "comp": "comp",
        "group_theory": "grp",
        "group": "grp",
        "grp": "grp",
        "ring_theory": "ring",
        "ring": "ring",
        "topology": "topo",
        "topo": "topo",
        "graph_theory": "graph",
        "graph": "graph",
        "cross_domain": "xdom",
        "xdom": "xdom",
    }
    return mapping.get(d, "xdom")

def next_id_for_prefix(kb: List[Dict[str, Any]], prefix: str) -> int:
    """
    IDs: <prefix>.thm.<>=5 digits
    """
    mx = 0
    for e in kb:
        eid = e.get("id", "")
        if not isinstance(eid, str):
            continue
        if not eid.startswith(prefix + "."):
            continue
        m = re.search(r"\.(\d{5,})$", eid)
        if m:
            mx = max(mx, int(m.group(1)))
    return mx + 1

# ---------------- Conjecture synthesis ----------------

def make_conjecture(domain: str, dropped: str, failure: str) -> Tuple[str, str, List[str], List[str]]:
    d = normalize_assumption(dropped)
    dom = domain.strip()

    # Modal logic: very natural wording
    if dom.lower() in ["modal_logic", "modal"]:
        title = f"Conjecture: keep {d} prevents {failure[:48]}"
        statement = (
            f"Conjecture (modal): In Kripke frames satisfying '{d}', "
            f"the boundary failure '{failure}' is not realizable; the corresponding modal principle is valid under '{d}'."
        )
        prereq = [f"assume:{d}", "modal:kripke_frame"]
        yields = ["status:conjecture", "modal:validity_candidate"]
        return title, statement, prereq, yields

    # FOL / MT: keep it general but concrete
    if dom.lower() in ["first_order_logic", "fol", "model_theory", "mt"]:
        title = f"Conjecture: {d} blocks failure ({failure[:40]})";
        statement = (
            f"Conjecture (FOL/MT): Assuming '{d}', the failure point '{failure}' is conjectured impossible; "
            f"i.e., no structure satisfying '{d}' realizes the corresponding counterexample pattern."
        )
        prereq = [f"assume:{d}"]
        yields = ["status:conjecture", "logic:validity_candidate"]
        return title, statement, prereq, yields

    # Default
    title = f"Conjecture: {d} blocks boundary failure"
    statement = (
        f"Conjecture: Under assumption '{d}', the boundary failure '{failure}' is conjectured to be unattainable."
    )
    prereq = [f"assume:{d}"]
    yields = ["status:conjecture", "theorem:candidate"]
    return title, statement, prereq, yields

# ---------------- Main ----------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--out-conjectures", required=True)
    ap.add_argument("--out-append", required=True)
    ap.add_argument("--topk", type=int, default=2000)
    ap.add_argument("--require-phaseE-format", action="store_true",
                    help="If set, only use counterexamples whose refutation contains Domain/Dropped Assumption/Failure Point.")
    args = ap.parse_args()

    kb = read_jsonl(args.kb)

    # 1) collect verified counterexamples
    verified_ce: List[Dict[str, Any]] = []
    stats_reason = Counter()

    for e in kb:
        ok, reason = is_verified_counterexample(e)
        stats_reason[reason] += 1
        if ok:
            verified_ce.append(e)

    # 2) extract signatures
    sig_counts: Counter[Tuple[str, str, str]] = Counter()
    dropped_missing = 0
    failure_missing = 0
    ref_missing = 0

    for e in verified_ce:
        domain = str(e.get("domain", "")).strip() or "cross_domain"
        
        # Try structured candidate first (more robust)
        cand = e.get("refutation_candidate")
        dropped = ""
        failure = ""
        
        if isinstance(cand, dict):
            # Phase 28 candidate format
            dropped = cand.get("dropped_assumption") or cand.get("DroppedAssumption") or ""
            failure = cand.get("failure_point") or cand.get("FailurePoint") or ""
            if cand.get("domain"): domain = cand.get("domain")

        if not dropped or not failure:
            # Fallback to parsing refutation text
            ref = e.get("refutation")
            if isinstance(ref, str) and ref.strip():
                fields = extract_refutation_fields(ref)
                if not dropped: dropped = fields.get("dropped", "")
                if not failure: failure = fields.get("failure", "")
            else:
                if not dropped and not failure: # both missing
                    ref_missing += 1
                    continue

        if args.require_phaseE_format:
            if not dropped:
                dropped_missing += 1
                continue
            if not failure:
                failure_missing += 1
                continue

        # fallback: if Phase E fields missing, create a coarse signature
        if not dropped:
            dropped = "unknown_assumption"
        if not failure:
            failure = "unknown_failure_point"

        sig_counts[(domain, dropped, failure)] += 1

    ranked = sig_counts.most_common(args.topk)

    # 3) allocate IDs per domain prefix
    next_ids: Dict[str, int] = {}
    for (domain, _, _), _cnt in ranked:
        pfx = domain_prefix(domain)
        if pfx not in next_ids:
            next_ids[pfx] = next_id_for_prefix(kb, pfx)

    # 4) output
    conjectures: List[Dict[str, Any]] = []
    append_entries: List[Dict[str, Any]] = []

    for (domain, dropped, failure), cnt in ranked:
        pfx = domain_prefix(domain)
        title, statement, prereq, yields = make_conjecture(domain, dropped, failure)

        conjectures.append({
            "domain": domain,
            "dropped_assumption": dropped,
            "failure_point": failure,
            "support_counterexamples": cnt,
            "conjecture_title": title,
        })

        n = next_ids[pfx]
        next_ids[pfx] += 1
        eid = f"{pfx}.thm.{n:05d}"

        append_entries.append({
            "id": eid,
            "domain": domain,
            "kind": "theorem",
            "title": title,
            "statement": statement,
            "prerequisites": prereq,
            "yields": yields + ["phase29:conjecture_generated"],
            "refutation": None,
            "patterns": [
                "status:conjecture",
                "phase29:boundary_to_conjecture",
                f"dropped_assumption:{normalize_assumption(dropped)}",
            ],
            "links": [
                f"sig:{domain}|{normalize_assumption(dropped)}|{failure[:120]}",
            ],
        })

    write_jsonl(args.out_conjectures, conjectures)
    write_jsonl(args.out_append, append_entries)

    print("[PHASE29] verified counterexamples:", len(verified_ce))
    print("[PHASE29] signature types:", len(sig_counts))
    print("[PHASE29] conjectures emitted:", len(append_entries))
    print("[PHASE29] refutation missing:", ref_missing)
    print("[PHASE29] dropped missing:", dropped_missing)
    print("[PHASE29] failure missing:", failure_missing)
    print("[PHASE29] tag_reason_stats (top10):", stats_reason.most_common(10))
    print("[PHASE29] out_append:", args.out_append)

if __name__ == "__main__":
    main()