"""Router — Vera as the controller that allocates work between itself and
an optional local LLM (制御配分).

Native harness behavior (no MCP, no triggers):
  * every declarative user utterance is auto-remembered into the store
  * every query runs Vera-first: math → code → knowledge consensus
  * the local LLM speaks only when Vera allows it, and always labeled:

      vera          deterministic grounded answer (LLM not consulted)
      llm_guided    LLM phrases an answer AROUND Vera's grounded facts
      llm_free      Vera has nothing (typed UNKNOWN); LLM may converse,
                    explicitly labeled as unverified
      refused       no LLM configured → the typed UNKNOWN itself is the answer

The allocation is deterministic; only the LLM's wording is not.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from . import domains
from .consensus_store import consensus_over_store
from .cross_store import CrossStore
from .lang import detect, ingest_text, is_question, ja_ask

domains.register_builtins()

LlmFn = Callable[[str, Optional[str]], Dict[str, Any]]  # (prompt, system) → {ok,text}

_GUIDED_SYSTEM = (
    "You are the language surface of a deterministic knowledge engine. "
    "Answer ONLY from the verified facts given. If the facts do not cover "
    "the question, say you do not know. Never add outside knowledge."
)
_FREE_SYSTEM = (
    "The knowledge engine has NO verified facts for this input. You may "
    "converse helpfully, but you MUST NOT present factual claims as "
    "verified. Prefix factual guesses with 'unverified:'."
)


def _vera_answer(
    store: CrossStore, query: str, lang: str,
    allocation: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    alloc = allocation or {}
    skip = {name for name in ("math", "code") if alloc.get(name, "vera") != "vera"}
    reg_out = domains.try_all(store, query, skip=skip)
    if reg_out["verdict"] != domains.NOT_MY_DOMAIN:
        return reg_out
    if lang == "ja":
        from .consensus_store import ja_consensus_ask

        out = ja_consensus_ask(store, query)
        if out["verdict"].startswith("UNKNOWN") and out["verdict"] != "UNKNOWN_UNPARSED":
            # consensus は語彙が薄いと厳しすぎることがある — 想起で再挑戦し、
            # それでも無ければ型付き拒否のまま
            fallback = ja_ask(store, query)
            if fallback["verdict"] == "ANSWER":
                fallback["route"] = "knowledge_ja_recall"
                return fallback
        out["route"] = "knowledge_ja"
        return out
    # The knowledge layer reads its tuning from config per call — same
    # pattern and same justification as the math domain's limits: a few
    # hundred bytes of JSON per query, in exchange for accepted changes
    # taking effect without a restart and without a cached value someone
    # must remember to invalidate.
    from .config import VeraConfig
    _cfg = VeraConfig.load()
    from .consensus import ConsensusConfig as _CC
    out = consensus_over_store(
        store, query,
        cfg=_CC(geometric_visibility=True) if _cfg.consensus_geometric else None,
        matryoshka=_cfg.consensus_matryoshka,
        carry=_cfg.consensus_carry if _cfg.consensus_carry in ("A", "B", "C") else "A",
    )
    out["route"] = "knowledge"
    return out


def route(
    store: CrossStore,
    user_text: str,
    *,
    llm: Optional[LlmFn] = None,
    lang: str = "auto",
    auto_memory: bool = True,
    save: Optional[Callable[[], None]] = None,
    allocation: Optional[Dict[str, str]] = None,
    growth: "Optional[Any]" = None,
    gap_graph: "Optional[Any]" = None,
    cognition_mode: str = "normal",
) -> Dict[str, Any]:
    """One chat turn under Vera's control. Deterministic allocation.

    ``allocation`` (config dial): math/code "vera"|"llm", known
    "vera"|"llm_guided", unknown "refuse"|"llm_free".

    ``growth`` (optional `growth_signals.GrowthSignals`): every normal
    call is "power-on" for Milestone M's self-growth loop — a real typed
    UNKNOWN just gets logged here, no extra wiring needed at call sites.

    ``gap_graph``/``cognition_mode`` (Milestone O): when cognition_mode is
    "normal" (the default), this is a pure no-op -- no GapNode is ever
    created, matching pre-Milestone-O behavior exactly for anyone who
    hasn't opted in. "experiment"/"sleep" persist a GapNode on a typed
    UNKNOWN; actual resolution only ever happens in "sleep" mode, and only
    from mcp_server.py's heartbeat(), never from here.
    """
    alloc = allocation or {}
    if lang == "auto":
        lang = detect(user_text)

    # 1. native memory harness: declaratives are remembered, always
    remembered = None
    if auto_memory and not is_question(user_text, lang):
        rep = ingest_text(store, user_text, lang=lang)
        if rep["cores"]:
            remembered = rep
            if save:
                save()

    # 2. Vera-first answer
    vera = _vera_answer(store, user_text, lang, allocation=alloc)
    verdict = vera.get("verdict")
    if growth is not None and isinstance(verdict, str) and verdict.startswith("UNKNOWN"):
        # "route" set (even on a typed UNKNOWN) means some domain module
        # recognized the query's shape and just lacks facts/evidence for
        # it — a needs_more_facts signal, not a missing-domain signal.
        matched = bool(vera.get("route")) and vera.get("route") not in ("knowledge", "knowledge_ja")
        growth.record_unknown(user_text, verdict, matched_domain=matched)

    if gap_graph is not None and cognition_mode in ("experiment", "sleep") and \
            isinstance(verdict, str) and verdict.startswith("UNKNOWN"):
        from .gap_severity import classify as classify_gap, is_repo_study_intent

        gap_class = classify_gap(user_text)
        acquisition_methods = ["web_search", "fetch_url", "vera_ask"]
        if is_repo_study_intent(user_text):
            acquisition_methods = ["vera_git_clone", "vera_code_ingest"] + acquisition_methods
        gap_graph.create(
            gap_type=gap_class.gap_type, subject=user_text[:200],
            scope=f"query:{user_text[:100]}", severity=gap_class.severity,
            status="BLOCKED_POLICY" if gap_class.blocked_policy else "DETECTED",
            acquisition_methods=acquisition_methods,
            allowed_sources=["web", "local_repository"],
        )

    if verdict == "ANSWER":
        # exact routes (math / code) are never paraphrased by the LLM —
        # a language model must not be allowed to garble a proven value.
        # allocation "known": "vera" keeps raw facet answers even with an LLM.
        if (
            llm is None
            or vera.get("route") in ("math", "code")
            or alloc.get("known", "llm_guided") == "vera"
        ):
            return {**vera, "source": "vera", "remembered": remembered}
        # grounded rephrasing: LLM speaks around Vera's facts only
        facts = (
            vera.get("text")
            or vera.get("facets")
            or vera.get("value")
            or vera.get("x")
            or vera.get("callers")
            or vera.get("calls")
        )
        r = llm(
            f"Verified facts: {facts}\nUser question ({lang}): {user_text}\n"
            f"Answer in the user's language using ONLY these facts.",
            _GUIDED_SYSTEM,
        )
        if r.get("ok"):
            return {
                **vera,
                "source": "llm_guided",
                "surface": r["text"],
                "remembered": remembered,
            }
        return {**vera, "source": "vera", "remembered": remembered,
                "llm_error": r.get("error")}

    # 3. Vera knows nothing usable
    # explicit allocation may forbid free LLM chat; without an allocation
    # dial, an available LLM may speak (labeled) — backwards compatible
    unknown_policy = alloc.get("unknown", "llm_free") if alloc else "llm_free"
    if llm is None or unknown_policy == "refuse":
        return {**vera, "source": "refused", "remembered": remembered}
    if verdict in ("AMBIGUOUS",):
        # genuine ambiguity is Vera's own verdict — the LLM may explain it
        # but must not resolve it by vibes.
        return {**vera, "source": "refused", "remembered": remembered}
    r = llm(user_text, _FREE_SYSTEM)
    if r.get("ok"):
        return {
            **vera,
            "source": "llm_free",
            "surface": r["text"],
            "remembered": remembered,
        }
    return {**vera, "source": "refused", "remembered": remembered,
            "llm_error": r.get("error")}
