"""Forks for agent tools, approval gating, ReAct loop, config allocation."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List

from .agent import Agent
from .agent_tools import build_registry
from .config import DEFAULT_ALLOCATION, VeraConfig
from .cross_store import CrossStore
from .router import route


def agent_readonly_runs_fork() -> Dict[str, Any]:
    """Read-only tools run without approval; results are real."""
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "a.txt"
        f.write_text("hello vera")
        reg = build_registry(CrossStore(), lambda: None)
        out = reg["read_file"].fn(path=str(f))
        ld = reg["list_dir"].fn(path=td)
    ok = out["ok"] and out["content"] == "hello vera" and "a.txt" in ld["entries"]
    return {"experiment": "agent", "fork": "AGENT_READONLY_RUNS",
            "pass": bool(ok), "result": {}}


def agent_approval_gate_fork() -> Dict[str, Any]:
    """Mutating tools blocked on deny, allowed on approve/always."""
    with tempfile.TemporaryDirectory() as td:
        st = CrossStore()
        target = Path(td) / "out.txt"

        denied = Agent(st, approver=lambda t, a: "deny")
        r_deny = denied._run_tool("write_file", {"path": str(target),
                                                 "content": "x"})
        denied_absent = not target.exists()
        approved = Agent(st, approver=lambda t, a: "approve")
        r_ok = approved._run_tool("write_file", {"path": str(target),
                                                 "content": "y"})
        # 'always' remembers the tool
        ag = Agent(st, approver=lambda t, a: "always")
        ag._run_tool("write_file", {"path": str(target), "content": "z1"})
        second = ag._run_tool("write_file", {"path": str(target),
                                             "content": "z2"})
    ok = (
        r_deny.get("error") == "denied_by_user"
        and denied_absent            # deny → file never created
        and r_ok["ok"]               # approve → written
        and "write_file" in ag.always  # always → remembered
        and second["ok"]
    )
    return {"experiment": "agent", "fork": "AGENT_APPROVAL_GATE",
            "pass": bool(ok),
            "result": {"deny": r_deny.get("error"), "approve_ok": r_ok["ok"]}}


def agent_react_loop_fork() -> Dict[str, Any]:
    """Scripted LLM drives a read → final loop; deterministic tool use."""
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "note.txt"
        f.write_text("the secret is 42")
        st = CrossStore()
        calls = {"n": 0}

        def scripted_llm(prompt, system):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"ok": True,
                        "text": '{"thought":"read it","tool":"read_file",'
                                f'"args":{{"path":"{f}"}}}}'}
            return {"ok": True,
                    "text": '{"thought":"done","final":"the secret is 42"}'}

        ag = Agent(st, llm=scripted_llm, max_steps=5)
        out = ag.run("what is the secret in note.txt")
    ok = (
        out["source"] == "react"
        and out["final"] == "the secret is 42"
        and out["steps"] == 2
        and any(t.get("action", {}).get("tool") == "read_file"
                for t in out["transcript"])
    )
    return {"experiment": "agent", "fork": "AGENT_REACT_LOOP",
            "pass": bool(ok), "result": {"steps": out["steps"]}}


def agent_vera_direct_fork() -> Dict[str, Any]:
    """Exact math finishes with no LLM and no tools (Vera as controller)."""
    ag = Agent(CrossStore(), llm=lambda p, s: {"ok": True, "text": "{}"})
    out = ag.run("what is 247 + 385")
    ok = out["source"] == "vera_direct" and out["final"]["value"] == 632 \
        and out["steps"] == 0
    return {"experiment": "agent", "fork": "AGENT_VERA_DIRECT",
            "pass": bool(ok), "result": {"value": out["final"].get("value")}}


def config_allocation_fork() -> Dict[str, Any]:
    """Allocation dial changes routing; round-trips through disk."""
    st = CrossStore()
    st.ingest_sentence("The bright apple is a sweet fruit .")

    def stub(p, s):
        return {"ok": True, "text": "surface"}

    guided = route(st, "what is apple", llm=stub,
                   allocation={"known": "llm_guided"})
    raw = route(st, "what is apple", llm=stub, allocation={"known": "vera"})
    refuse = route(st, "what is dark matter", llm=stub,
                   allocation={"unknown": "refuse"})
    free = route(st, "what is dark matter", llm=stub,
                 allocation={"unknown": "llm_free"})
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "c.json"
        cfg = VeraConfig(llm_model="qwen", allocation={"math": "vera"})
        cfg.save(p)
        loaded = VeraConfig.load(p)
    ok = (
        guided["source"] == "llm_guided"
        and raw["source"] == "vera"
        and refuse["source"] == "refused"
        and free["source"] == "llm_free"
        and loaded.llm_model == "qwen"
        and loaded.allocation["unknown"] == DEFAULT_ALLOCATION["unknown"]
    )
    return {"experiment": "config", "fork": "CONFIG_ALLOCATION",
            "pass": bool(ok),
            "result": {"guided": guided["source"], "raw": raw["source"],
                       "refuse": refuse["source"], "free": free["source"]}}


def multiline_paste_capture_fork() -> Dict[str, Any]:
    """Bracketed-paste state machine: embedded CRLF → one string, CRLF
    pairs collapse to one newline, backspace edits, Ctrl-C aborts.
    Pure function — no real TTY needed, so this is a genuine test (unlike
    the raw-mode I/O wrapper itself, which needs a live terminal)."""
    from .tui import _consume_raw_input

    paste_chars = (
        list("\x1b[200~") + list("first line\r\nsecond line")
        + list("\x1b[201~") + ["\r"]
    )
    it1 = iter(paste_chars)
    pasted = _consume_raw_input(lambda: next(it1, ""), echo=False)

    it2 = iter(list("ab") + ["\x7f", "c", "\r"])
    backspaced = _consume_raw_input(lambda: next(it2, ""), echo=False)

    it3 = iter(["a", "\x03"])
    cancelled = _consume_raw_input(lambda: next(it3, ""), echo=False)

    ok = (
        pasted == "first line\nsecond line"
        and backspaced == "ac"
        and cancelled is None
    )
    return {
        "experiment": "tui",
        "fork": "MULTILINE_PASTE_CAPTURE",
        "pass": bool(ok),
        "result": {"pasted": pasted, "backspaced": backspaced,
                   "cancelled": cancelled},
    }


def tui_fallback_fork() -> Dict[str, Any]:
    """Non-TTY select falls back to indexed input deterministically."""
    import io
    import sys

    from . import tui

    old_in, old_out = sys.stdin, sys.stdout
    try:
        sys.stdin = io.StringIO("2\n")
        sys.stdout = io.StringIO()  # suppress the fallback menu print
        i = tui.select("pick", ["a", "b", "c"], default=0)
    finally:
        sys.stdin, sys.stdout = old_in, old_out
    ok = i == 2
    return {"experiment": "agent", "fork": "TUI_FALLBACK",
            "pass": bool(ok), "result": {"chosen": i}}


def grain_band_annotation_fork() -> Dict[str, Any]:
    """The grain band rides beside `ask`'s verdict and never changes it.

    The MCP `ask` tool attaches `graded.band_annotation` to the consensus
    verdict. Two invariants are load-bearing: annotating changes nothing
    about the verdict (the band is structure, the verdict is evidence,
    and pooling the two is the measured mistake), and the band's count is
    bounded by its own denominator. A fabricated subject must read as
    agree 0 or no band at all — never as a positive count.
    """
    from .consensus_store import consensus_over_store
    from .graded import GradedJudge, band_annotation, settings_for

    st = CrossStore()
    for s in (
        "The capital of France is Paris.",
        "Paris is the largest city of France.",
        "The capital of Japan is Tokyo.",
    ):
        st.ingest_sentence(s)
    judge = GradedJudge(settings_for("This is English.")).build(st)

    results: Dict[str, Any] = {}
    ok = True
    for q in ("capital of France", "capital of Japan",
              "quantum chromodynamics"):
        base = consensus_over_store(st, q)
        band = band_annotation(judge, q)
        annotated = dict(base)
        if band is not None:
            annotated["grain"] = band
        never_votes = annotated["verdict"] == base["verdict"]
        bounded = band is None or 0 <= band["agree"] <= band["of"]
        results[q] = {"verdict": base["verdict"], "band": band}
        ok = ok and never_votes and bounded
    # The out-of-corpus subject must not collect a positive count.
    fabricated = band_annotation(judge, "quantum chromodynamics")
    ok = ok and (fabricated is None or fabricated["agree"] == 0)
    return {"experiment": "agent", "fork": "GRAIN_BAND_ANNOTATES_NEVER_VOTES",
            "pass": bool(ok), "result": results}


def refusal_ledger_keeps_resolved_fork() -> Dict[str, Any]:
    """An auto-resolved refusal stays on the ledger, with its outcome.

    Typed unknowns becoming control signals (refusal -> action branch)
    creates the risk this fork closes: a branch that resolves a refusal
    silently would make the demand ledger read as if the refusal never
    happened — the invisible-ingestion lie in a new place. Recording an
    outcome, resolved or not, must never touch the refusal's bucket, and
    both must survive a save/load roundtrip.
    """
    import tempfile
    from pathlib import Path

    from .growth_signals import GrowthSignals

    gs = GrowthSignals()
    gs.record_unknown("譲渡担保とは", "UNKNOWN_NOT_PRESENT")
    before = len(gs.buckets)
    gs.record_branch_outcome("譲渡担保とは", "UNKNOWN_NOT_PRESENT",
                             "gather-evidence", resolved=False)
    gs.record_branch_outcome("譲渡担保とは", "UNKNOWN_NOT_PRESENT",
                             "gather-evidence", resolved=True)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "growth.json"
        gs.save(p)
        back = GrowthSignals.load(p)
    ok = (len(gs.buckets) == before
          and len(back.buckets) == before
          and len(back.branch_outcomes) == 2
          and back.branch_outcomes[0]["resolved"] is False
          and back.branch_outcomes[1]["resolved"] is True)
    return {"experiment": "agent", "fork": "REFUSAL_LEDGER_KEEPS_RESOLVED",
            "pass": bool(ok),
            "result": {"buckets": len(back.buckets),
                       "outcomes": len(back.branch_outcomes)}}


def refusal_feeds_the_gap_graph_fork() -> Dict[str, Any]:
    """Unresolved refusals become GapNodes; resolution moves, never deletes.

    The frontier map must accumulate from operation, not by hand: an
    unresolved refusal creates (or reuses — the double-call at hand-off
    and close must be idempotent) a node under (agent_refusal, query),
    and a later resolution moves THAT node to RESOLVED with the branch
    named. Nothing is ever deleted — a resolved gap is history, and
    history is what stops the same hole being re-detected from scratch.
    """
    from .gap_graph import GapGraph, refusal_to_gap

    g = GapGraph()
    a = refusal_to_gap(g, "譲渡担保とは", "UNKNOWN_NOT_PRESENT",
                       "gather-evidence", resolved=False)
    b = refusal_to_gap(g, "譲渡担保とは", "UNKNOWN_NOT_PRESENT",
                       "gather-evidence", resolved=False)
    none_yet = refusal_to_gap(g, "準委任とは", "UNKNOWN_NOT_PRESENT",
                              "gather-evidence", resolved=True)
    closed = refusal_to_gap(g, "譲渡担保とは", "UNKNOWN_NOT_PRESENT",
                            "gather-evidence", resolved=True)
    node = g.get(a) if a else None
    ok = (a is not None and a == b          # double-call is idempotent
          and none_yet is None               # nothing to resolve, no node
          and closed == a                    # resolution moves THAT node
          and node is not None
          and node.status == "RESOLVED"
          and node.failure_type == "UNKNOWN_NOT_PRESENT"
          and len(g.nodes) == 1)             # moved, never deleted or duped
    return {"experiment": "agent", "fork": "REFUSAL_FEEDS_THE_GAP_GRAPH",
            "pass": bool(ok),
            "result": {"gap_id": a, "status": node.status if node else None,
                       "nodes": len(g.nodes)}}


def coverage_names_the_shelf_or_the_hole_fork() -> Dict[str, Any]:
    """The atlas names a shelf it HAS, or the hole — never a wrong shelf.

    A gap node telling a human "prepare a 法学 document" when no shelf
    holds anything near the subject sends them after the wrong
    document, which is worse than the honest hole. Proximity is
    recountable presence only (held core / unit held), ties display
    rather than break, and the ranked shelves ride the GapNode as
    allowed_sources.
    """
    from .coverage import closing_domains, document_needed
    from .gap_graph import GapGraph, refusal_to_gap

    law = CrossStore()
    law.add("譲渡", ["担保", "移転"])
    law.add("担保", ["債権", "物権"])
    wiki = CrossStore()
    wiki.add("超新星", ["天文", "爆発"])

    domains = {"法学": law, "百科": wiki}
    near = closing_domains(domains, "譲渡担保")
    hole = document_needed(domains, "量子縺れ")
    named = document_needed(domains, "譲渡担保")

    # The alias sidecar: パワハラ is nobody's core, but its canonical
    # title is — the hop must be NAMED in the signal, and it must be
    # exactly one hop (an alias of an alias is a chain nobody attested).
    wiki.add("パワーハラスメント", ["職場", "行為"])
    al = {"パワハラ": "パワーハラスメント",
          "PH": "パワハラ"}
    via_alias = closing_domains(domains, "パワハラ", aliases=al)
    two_hops = closing_domains(domains, "PH", aliases=al)

    g = GapGraph()
    gid = refusal_to_gap(g, "譲渡担保とは", "UNKNOWN_NOT_PRESENT",
                         "gather-evidence", resolved=False,
                         sources=["法学"])
    node = g.get(gid)

    ok = (near["closest"] and near["closest"][0]["domain"] == "法学"
          and not near["coverage_hole"]
          and hole["coverage_hole"] is True
          and "ジャンルごと不足" in hole["document"]
          and "法学" in named["document"]
          and node is not None and node.allowed_sources == ["法学"]
          # one alias hop closes the hole, with the hop named
          and via_alias["coverage_hole"] is False
          and any("alias held: パワハラ → パワーハラスメント" in s
                  for d in via_alias["closest"] for s in d["signals"])
          # two hops stay a hole: nobody attested the chain
          and two_hops["coverage_hole"] is True)
    return {"experiment": "agent",
            "fork": "COVERAGE_NAMES_THE_SHELF_OR_THE_HOLE",
            "pass": bool(ok),
            "result": {"near": near["closest"][:1],
                       "hole": hole["coverage_hole"],
                       "via_alias": via_alias["closest"][:1],
                       "node_sources": node.allowed_sources if node else None}}


def all_agent_forks() -> List[Dict[str, Any]]:
    return [
        agent_readonly_runs_fork(),
        agent_approval_gate_fork(),
        agent_react_loop_fork(),
        agent_vera_direct_fork(),
        config_allocation_fork(),
        tui_fallback_fork(),
        multiline_paste_capture_fork(),
        grain_band_annotation_fork(),
        refusal_ledger_keeps_resolved_fork(),
        refusal_feeds_the_gap_graph_fork(),
        coverage_names_the_shelf_or_the_hole_fork(),
    ]
