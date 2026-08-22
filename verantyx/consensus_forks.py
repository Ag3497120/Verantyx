"""Forks for multi-frontier consensus search (typed verdicts, carry modes)."""
from __future__ import annotations

from typing import Any, Dict, List

from .consensus import (
    ConsensusConfig,
    matryoshka_consensus,
    run_consensus,
)
from .cross import ShellCross
from .face_roles import place_core_facts_on_shell


def _shell_apple_stone() -> ShellCross:
    """apple: evidenced core; stone: bare distractor tip far away."""
    shell = ShellCross()
    place_core_facts_on_shell(shell, "apple", ["fruit", "red", "sweet"], axis="+x")
    shell.faces["-y"]["tip"] = "stone"
    return shell


def _shell_two_evidenced() -> ShellCross:
    """Two evidenced hypotheses on opposite arms (equal default mass).

    Both carry the shared facet "round" so a bare "round" query grounds
    both equally (the genuine-ambiguity case).
    """
    shell = ShellCross()
    place_core_facts_on_shell(shell, "apple", ["fruit", "round"], axis="+x")
    place_core_facts_on_shell(shell, "stone", ["hard", "round"], axis="-y")
    return shell


def consensus_answer_fork() -> Dict[str, Any]:
    """ANSWER only via 3 gates; deterministic; text from agreed arm."""
    shell = _shell_apple_stone()
    r1 = run_consensus(shell, "what is apple")
    r2 = run_consensus(shell, "what is apple")
    ok = (
        r1.verdict == "ANSWER"
        and r1.core == "apple"
        and r1.tokens[:1] == ["apple"]
        and {"fruit", "red", "sweet"}.issubset(set(r1.tokens))
        and r1.local_stable
        and r1.as_dict() == r2.as_dict()
    )
    return {
        "experiment": "consensus",
        "fork": "CONSENSUS_ANSWER",
        "pass": bool(ok),
        "result": r1.as_dict(),
    }


def consensus_evidence_gate_fork() -> Dict[str, Any]:
    """Agreement alone must not ship: bare core → INSUFFICIENT_EVIDENCE."""
    shell = ShellCross()
    shell.faces["+x"]["tip"] = "ghost"
    r = run_consensus(shell, "what is ghost")
    ok = (
        r.verdict == "UNKNOWN_INSUFFICIENT_EVIDENCE"
        and r.core is None
        and r.text == ""
    )
    return {
        "experiment": "consensus",
        "fork": "CONSENSUS_EVIDENCE_GATE",
        "pass": bool(ok),
        "result": r.as_dict(),
    }


def consensus_ambiguous_tie_fork() -> Dict[str, Any]:
    """Two grounded, evidenced hypotheses tie in energy → AMBIGUOUS, never vote."""
    shell = _shell_two_evidenced()
    r = run_consensus(shell, "round")
    ok = r.verdict == "AMBIGUOUS" and r.core is None and len(r.hypotheses) >= 2
    return {
        "experiment": "consensus",
        "fork": "CONSENSUS_AMBIGUOUS_TIE",
        "pass": bool(ok),
        "result": r.as_dict(),
    }


def consensus_budget_fork() -> Dict[str, Any]:
    """Improving move available but budget spent → UNKNOWN_BUDGET."""
    shell = _shell_apple_stone()
    r = run_consensus(
        shell, "what is apple", cfg=ConsensusConfig(max_moves=0)
    )
    free = run_consensus(shell, "what is apple")
    ok = (
        r.verdict in ("UNKNOWN_BUDGET", "ANSWER")
        and free.verdict == "ANSWER"
        and (r.verdict != "ANSWER" or free.moves_used == 0)
    )
    # Honest check: budget verdict must fire when the free run needed moves.
    if free.moves_used > 0:
        ok = r.verdict == "UNKNOWN_BUDGET" and r.core is None
    return {
        "experiment": "consensus",
        "fork": "CONSENSUS_BUDGET",
        "pass": bool(ok),
        "result": {"budget0": r.as_dict(), "free_moves": free.moves_used},
    }


def consensus_no_evidence_fork() -> Dict[str, Any]:
    shell = ShellCross()
    r = run_consensus(shell, "what is anything")
    ok = r.verdict == "UNKNOWN_NO_EVIDENCE" and r.text == ""
    return {
        "experiment": "consensus",
        "fork": "CONSENSUS_NO_EVIDENCE",
        "pass": bool(ok),
        "result": r.as_dict(),
    }


def consensus_query_grounding_fork() -> Dict[str, Any]:
    """Unrelated query must not surface an agreeable but ungrounded node."""
    shell = _shell_apple_stone()
    off_topic = run_consensus(shell, "what is quantum")
    on_topic = run_consensus(shell, "what is apple")
    ok = (
        off_topic.verdict == "UNKNOWN_NO_EVIDENCE"
        and off_topic.core is None
        and off_topic.text == ""
        and on_topic.verdict == "ANSWER"
    )
    return {
        "experiment": "consensus",
        "fork": "CONSENSUS_QUERY_GROUNDING",
        "pass": bool(ok),
        "result": {
            "off_topic_verdict": off_topic.verdict,
            "on_topic_verdict": on_topic.verdict,
        },
    }


def consensus_escape_fork() -> Dict[str, Any]:
    """Escape resolves narrow-view disagreement; disabling it must not ANSWER."""
    shell = _shell_apple_stone()
    with_esc = run_consensus(shell, "what is apple")
    no_esc = run_consensus(
        shell, "what is apple", cfg=ConsensusConfig(allow_escape=False)
    )
    ok = (
        with_esc.verdict == "ANSWER"
        and with_esc.escape_used
        and no_esc.verdict == "UNKNOWN_LOCAL_MINIMUM"
    )
    return {
        "experiment": "consensus",
        "fork": "CONSENSUS_ESCAPE_HELPS",
        "pass": bool(ok),
        "result": {
            "with_escape": with_esc.as_dict(),
            "no_escape_verdict": no_esc.verdict,
        },
    }


def matryoshka_carry_fork() -> Dict[str, Any]:
    """Layer-0 disagreement handed upward; carry A/B/C behave differently.

    A (常時クエリ): query bonus breaks the tie upstairs → ANSWER.
    B (初層限定): upper layer query-free → evidenced tie stays → not ANSWER.
    C (意図固定・内容減衰): head token alone still favors apple → ANSWER.
    """
    outs: Dict[str, Dict[str, Any]] = {}
    for mode in ("A", "B", "C"):
        shell = _shell_two_evidenced()
        outs[mode] = matryoshka_consensus(
            shell, "what is apple", carry=mode, n_layers=3
        )
    ok = (
        outs["A"]["verdict"] == "ANSWER"
        and outs["A"]["core"] == "apple"
        and outs["A"]["resolved_at"] is not None
        and outs["A"]["resolved_at"] >= 1
        and outs["B"]["verdict"] != "ANSWER"
        and outs["C"]["verdict"] == "ANSWER"
        and outs["C"]["core"] == "apple"
    )
    summary = {
        m: {
            "verdict": o["verdict"],
            "core": o["core"],
            "resolved_at": o["resolved_at"],
            "n_layers_run": o["n_layers_run"],
        }
        for m, o in outs.items()
    }
    return {
        "experiment": "consensus",
        "fork": "MATRYOSHKA_CARRY_MODES",
        "pass": bool(ok),
        "result": summary,
    }


def all_consensus_forks() -> List[Dict[str, Any]]:
    return [
        consensus_answer_fork(),
        consensus_evidence_gate_fork(),
        consensus_ambiguous_tie_fork(),
        consensus_budget_fork(),
        consensus_no_evidence_fork(),
        consensus_query_grounding_fork(),
        consensus_escape_fork(),
        matryoshka_carry_fork(),
    ]
