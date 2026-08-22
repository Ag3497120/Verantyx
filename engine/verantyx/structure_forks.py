"""Forks for the three woken structural properties: polarity, the arm
schema, and rotation signatures. Same contract as every *_forks module.

The discipline these encode: each property claims a specific new behaviour
(contradiction as lookup; intent-specific refusal; shape recognition), and
each fork constructs BOTH the case where the behaviour must fire and the
case where it must not. A gate that cannot be shown holding its fire is
indistinguishable from a gate that fires on everything.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .arm_schema import ArmIndex
from .consensus_store import consensus_over_store
from .cross import ShellCross
from .cross_store import CrossStore
from .polarity import bipolar_evidence, ingest_polar
from .rotation_signature import ROTATIONS, SignatureIndex, replay, signature


# ---------------------------------------------------------------------------
# Polarity
# ---------------------------------------------------------------------------

def polarity_contradiction_gate_fork() -> Dict[str, Any]:
    """Both poles held → contradiction with named sides and sources; one
    pole → a normal answer; a question that does not touch the dispute →
    the dispute must NOT block it. The third case is the restraint check:
    a store may hold a dozen disputes and still answer around them."""
    st = CrossStore(track_provenance=True)
    ingest_polar(st, "the shelter is open according to the city office")
    ingest_polar(st, "the shelter is closed according to the sns report")
    ingest_polar(st, "the market is open every morning")

    disputed = consensus_over_store(st, "is the shelter open")
    clean = consensus_over_store(st, "is the market open")
    unrelated = consensus_over_store(st, "what is the shelter")

    entry = (disputed.get("contradictions") or [{}])[0]
    has_sides = sorted(entry.get("values", [])) == ["open:closed", "open:open"]
    has_sources = bool(entry.get("provenance"))

    ok = (disputed["verdict"] == "UNKNOWN_UNRESOLVED_CONTRADICTION"
          and has_sides and has_sources
          and clean["verdict"] == "ANSWER"
          and unrelated["verdict"] == "ANSWER")
    return {
        "experiment": "structure",
        "fork": "POLARITY_CONTRADICTION_GATE",
        "pass": bool(ok),
        "result": {"disputed": disputed["verdict"], "sides": entry.get("values"),
                   "sourced": has_sources, "clean": clean["verdict"],
                   "unrelated_question": unrelated["verdict"]},
    }


def polarity_negation_fork() -> Dict[str, Any]:
    """'not open' must land on the negative pole and collide with 'open'.
    Negation handling is where a polarity vocabulary quietly breaks: a
    detector that only knows surface antonyms calls 'not open' positive."""
    st = CrossStore()
    ingest_polar(st, "the gate is open")
    # Kept deliberately clause-free. A first fixture said "not open after
    # dark" and the sentence classifier cored it as 'dark' — the pole landed
    # on the wrong core and the collision never happened. That is a REAL
    # hazard of polar ingestion (the pole follows whatever core the
    # classifier picks), recorded here so the next person widening the
    # negation vocabulary tests mis-coring too, not only detection.
    ingest_polar(st, "the gate is not open")
    disputes = bipolar_evidence(st, "gate")
    ok = (len(disputes) == 1 and disputes[0]["key"] == "open"
          and sorted(disputes[0]["values"]) == ["open:not_open", "open:open"])
    return {
        "experiment": "structure",
        "fork": "POLARITY_NEGATION",
        "pass": bool(ok),
        "result": {"disputes": disputes},
    }


# ---------------------------------------------------------------------------
# Arm schema
# ---------------------------------------------------------------------------

def arm_intent_gate_fork() -> Dict[str, Any]:
    """'why' with a filled cause arm answers WITH the cause sentences;
    'why' against a core whose cause arm is empty refuses with the arm's own
    typed verdict — known thing, unknown why. The refusal names what IS held
    so the caller learns the shape of the gap, not just its existence."""
    st = CrossStore()
    idx = ArmIndex()
    idx.ingest(st, "rivers flood because of heavy rain")
    idx.ingest(st, "glaciers are melting")  # no cue -> no arm

    why_known = consensus_over_store(st, "why do rivers flood")
    idx.gate(why_known, "why do rivers flood")

    why_unknown = consensus_over_store(st, "why are glaciers melting")
    idx.gate(why_unknown, "why are glaciers melting")

    plain = consensus_over_store(st, "what is glaciers")
    idx.gate(plain, "what is glaciers")

    ok = (why_known["verdict"] == "ANSWER"
          and why_known.get("arm") == "cause+"
          and any("because" in s for s in why_known.get("arm_evidence", []))
          and why_unknown["verdict"] == "UNKNOWN_NO_CAUSE_RECORDED"
          and why_unknown.get("missing_arm") == "cause+"
          and plain["verdict"] == "ANSWER")
    return {
        "experiment": "structure",
        "fork": "ARM_INTENT_GATE",
        "pass": bool(ok),
        "result": {"why_known": {"verdict": why_known["verdict"],
                                 "arm": why_known.get("arm")},
                   "why_unknown": {"verdict": why_unknown["verdict"],
                                   "missing": why_unknown.get("missing_arm")},
                   "no_intent_question": plain["verdict"]},
    }


def arm_checklist_fork() -> Dict[str, Any]:
    """The six questions as a completeness report: filled arms counted,
    empty arms surfaced as the typed gaps a GapNode can hold."""
    st = CrossStore()
    idx = ArmIndex()
    idx.ingest(st, "rivers flood because of heavy rain")
    idx.ingest(st, "rivers are confirmed by satellite imagery")
    rep = idx.report("rivers")
    ok = (rep["filled"].get("cause+") == 1
          and rep["filled"].get("support+") == 1
          and len(rep["empty"]) == 4
          and "UNKNOWN_NO_INSTANCE_RECORDED" in rep["gap_verdicts"])
    return {
        "experiment": "structure",
        "fork": "ARM_CHECKLIST",
        "pass": bool(ok),
        "result": rep,
    }


# ---------------------------------------------------------------------------
# Rotation signatures
# ---------------------------------------------------------------------------

def _filled_shell(spec: Dict[str, int]) -> ShellCross:
    """axis -> how many faces to fill (tip first)."""
    from .cross import FACE_SLOTS
    s = ShellCross()
    for axis, n in spec.items():
        for f in list(FACE_SLOTS)[:n]:
            s.faces[axis][f] = f"tok_{axis}_{f}"
    return s


def signature_invariance_fork() -> Dict[str, Any]:
    """Every one of the 24 rotations of a shell must produce the SAME
    signature (invariance, checked exhaustively, not on one sample), and a
    genuinely different fill pattern must produce a different one
    (discrimination — without which invariance is trivially satisfiable by
    a constant)."""
    base = _filled_shell({"+x": 3, "-y": 1})
    sig0 = signature(base)
    invariant = True
    for rot in ROTATIONS:
        rotated = ShellCross()
        for src, dst in rot.items():
            rotated.faces[dst] = dict(base.faces[src])
        if signature(rotated) != sig0:
            invariant = False
            break
    other = _filled_shell({"+x": 1, "-x": 1})
    ok = invariant and signature(other) != sig0
    return {
        "experiment": "structure",
        "fork": "SIGNATURE_INVARIANCE",
        "pass": bool(ok),
        "result": {"signature": sig0, "invariant_under_all_24": invariant,
                   "distinct_shape_differs": signature(other) != sig0},
    }


def signature_replay_verifies_fork() -> Dict[str, Any]:
    """Replay re-applies a recorded solution and RE-EVALUATES it — the check
    that turns a signature collision from a wrong answer into a fallback.
    Verified here from both sides: a genuine solution replays to agreement
    at move-sequence cost, and the same moves against an empty shell (the
    collision stand-in) fail the check instead of passing on trust."""
    from .consensus_forks import _shell_two_evidenced
    from .consensus import ConsensusConfig, run_consensus

    shell = _shell_two_evidenced()
    cfg = ConsensusConfig(window=len(ROTATIONS) // 4, allow_escape=True)
    res = run_consensus(shell, "what is apple", cfg=cfg)

    idx = SignatureIndex()
    sig = signature(shell)
    idx.record(sig, verdict=res.verdict, moves=res.accepted_moves,
               domain="fruit_toy", remedy="none")

    good = replay(shell, "what is apple", res.accepted_moves, cfg=cfg)
    collision = replay(ShellCross(), "what is apple", res.accepted_moves, cfg=cfg)

    prior = idx.transfer_prior(sig)
    idx.record(sig, verdict=res.verdict, moves=res.accepted_moves,
               domain="soc_toy", remedy="add_data_source")
    prior2 = idx.transfer_prior(sig)

    ok = (good["agree_all"] and not collision["agree_all"]
          and good["evaluations"] == len(res.accepted_moves) + 1
          and prior["known_shape"] and prior2["seen"] == 2
          and set(prior2["domains"]) == {"fruit_toy", "soc_toy"})
    return {
        "experiment": "structure",
        "fork": "SIGNATURE_REPLAY_VERIFIES",
        "pass": bool(ok),
        "result": {"replay_ok": good, "collision_rejected": not collision["agree_all"],
                   "transfer_prior": prior2},
    }


def all_structure_forks() -> List[Dict[str, Any]]:
    return [
        polarity_contradiction_gate_fork(),
        polarity_negation_fork(),
        arm_intent_gate_fork(),
        arm_checklist_fork(),
        signature_invariance_fork(),
        signature_replay_verifies_fork(),
        document_disagreement_survives_fork(),
        document_unanimous_is_supported_fork(),
    ]


# ---------------------------------------------------------------------------
# Multi-source documents — deep search over news / reports.
# ---------------------------------------------------------------------------

def document_disagreement_survives_fork() -> Dict[str, Any]:
    """Three reports, one contested aspect: the disagreement must survive
    ingestion with each side attributed, agreed facts must be listed
    separately, and a contested claim must appear in EXACTLY ONE list.

    The last property is the one a summariser cannot offer. If "open" can
    show up under settled while "open vs closed" shows up under disputed,
    a responder reading the top of the report is misinformed by the report's
    own structure.
    """
    from .arm_schema import ArmIndex as _AI
    from .document_ingest import Document, deep_report, ingest_documents

    st = CrossStore(track_provenance=True)
    arms = _AI()
    ingest_documents(st, [
        Document("city_office", "The shelter is open. The shelter has water supply."),
        Document("sns_report", "The shelter is closed."),
        Document("ntv_news", "The shelter has water supply."),
    ], arms=arms)
    rep = deep_report(st, "shelter", arms=arms)

    settled_claims = {s["claim"] for s in rep["settled"]}
    disputed = rep["disputed"]
    sides = {s["claim"]: s["sources"] for d in disputed for s in d["sides"]}

    attributed = (sides.get("open") == ["city_office"]
                  and sides.get("closed") == ["sns_report"])
    no_overlap = not (settled_claims & set(sides))
    agreed_kept = any(s["claim"] == "water" for s in rep["settled"])
    # A gap is a next search query, not just a label — the step that makes
    # this deep search rather than one pass over the articles.
    gap_is_query = any(m["next_query"].startswith("why") for m in rep["missing"])

    ok = (rep["confidence"] == "contested" and attributed and no_overlap
          and agreed_kept and gap_is_query)
    return {
        "experiment": "structure",
        "fork": "DOCUMENT_DISAGREEMENT_SURVIVES",
        "pass": bool(ok),
        "result": {"confidence": rep["confidence"], "sides": sides,
                   "settled": sorted(settled_claims),
                   "no_overlap": no_overlap,
                   "example_gap_query": next(
                       (m["next_query"] for m in rep["missing"]), None)},
    }


def document_unanimous_is_supported_fork() -> Dict[str, Any]:
    """No contradiction anywhere → 'supported', not 'contested'. The control
    that keeps the report from calling everything disputed: a detector that
    always fires carries no information."""
    from .document_ingest import Document, deep_report, ingest_documents

    st = CrossStore(track_provenance=True)
    ingest_documents(st, [
        Document("a_paper", "The bridge is passable."),
        Document("b_paper", "The bridge is passable for light vehicles."),
    ])
    rep = deep_report(st, "bridge")
    ok = rep["confidence"] == "supported" and not rep["disputed"]
    return {
        "experiment": "structure",
        "fork": "DOCUMENT_UNANIMOUS_IS_SUPPORTED",
        "pass": bool(ok),
        "result": {"confidence": rep["confidence"],
                   "settled": [s["claim"] for s in rep["settled"]]},
    }
