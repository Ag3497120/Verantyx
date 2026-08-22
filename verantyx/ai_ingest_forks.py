"""Forks for AI-output quarantine (hedge/meta filtering, accept/reject)."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List

from .ai_ingest import AiFactQuarantine, candidate_sentences
from .cross_store import CrossStore


def ai_ingest_filters_hedges_fork() -> Dict[str, Any]:
    """Hedge-worded and meta-commentary sentences never become candidates —
    the whole point is not laundering an LLM's own uncertainty into facts."""
    text = (
        "The staging database runs postgres 14. "
        "It might also support replication, I'm not sure. "
        "Let me check the config file for you. "
        "The API rate limit is 100 requests per minute."
    )
    cands = candidate_sentences(text)
    ok = (
        len(cands) == 2
        and "postgres 14" in cands[0]
        and "rate limit" in cands[1]
        and not any("might" in c or "check the config" in c for c in cands)
    )
    return {"experiment": "ai_ingest", "fork": "AI_INGEST_FILTERS_HEDGES",
            "pass": bool(ok), "result": {"candidates": cands}}


def ai_ingest_drops_questions_tasks_fork() -> Dict[str, Any]:
    """Questions/imperatives/task-labeled sentences (the same gate chat
    uses) never reach quarantine either."""
    text = (
        "What is the deployment target? "
        "Please run the migration script. "
        "The deployment target is production-eu."
    )
    cands = candidate_sentences(text)
    ok = (
        len(cands) == 1
        and "production-eu" in cands[0]
    )
    return {"experiment": "ai_ingest", "fork": "AI_INGEST_DROPS_QUESTIONS_TASKS",
            "pass": bool(ok), "result": {"candidates": cands}}


def ai_quarantine_never_auto_promotes_fork() -> Dict[str, Any]:
    """Proposing never touches the trusted store; only explicit accept
    does — this is the entire safety property of the design."""
    st = CrossStore()
    q = AiFactQuarantine()
    added = q.propose(
        "The payments service owner is Kenji.", source="ai_output:test-model"
    )
    untouched = len(st.crosses) == 0 and len(added) == 1
    key = q.accept(added[0], st)
    promoted = st.has("payments") or st.has(key or "")
    remaining_pending = q.pending()
    ok = untouched and key is not None and promoted and not remaining_pending
    return {"experiment": "ai_ingest", "fork": "AI_QUARANTINE_NEVER_AUTO_PROMOTES",
            "pass": bool(ok),
            "result": {"key": key, "store_cores_before_accept": 0 if untouched else None}}


def ai_quarantine_reject_and_persist_fork() -> Dict[str, Any]:
    """Reject never touches the store; quarantine state round-trips
    through save/load (so a CLI review session can resume)."""
    st = CrossStore()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "q.json"
        q = AiFactQuarantine()
        added = q.propose("The config file lives at /etc/vera/config.yaml.",
                          source="ai_output:test")
        q.save(p)
        q2 = AiFactQuarantine.load(p)
        entry = q2.pending()[0]
        rejected = q2.reject(entry)
        q2.save(p)
        q3 = AiFactQuarantine.load(p)
    ok = (
        len(added) == 1
        and rejected
        and not q3.pending()
        and q3.entries[0].status == "rejected"
        and len(st.crosses) == 0
    )
    return {"experiment": "ai_ingest", "fork": "AI_QUARANTINE_REJECT_AND_PERSIST",
            "pass": bool(ok), "result": {"final_status": q3.entries[0].status}}


def all_ai_ingest_forks() -> List[Dict[str, Any]]:
    return [
        ai_ingest_filters_hedges_fork(),
        ai_ingest_drops_questions_tasks_fork(),
        ai_quarantine_never_auto_promotes_fork(),
        ai_quarantine_reject_and_persist_fork(),
    ]
