"""Forks for the multilingual front-end and the control-allocation router.

All offline (llm=None or a stub) — deterministic and CI-safe.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .cross_store import CrossStore
from .lang import detect, ingest_text, is_question, ja_ask
from .router import route


def lang_detect_fork() -> Dict[str, Any]:
    ok = (
        detect("リンゴは甘い果物です") == "ja"
        and detect("The apple is sweet") == "en"
        and detect("La manzana es dulce") == "en"  # latin script → en pipeline default
    )
    return {"experiment": "lang", "fork": "LANG_DETECT", "pass": bool(ok),
            "result": {}}


def lang_ja_ingest_ask_fork() -> Dict[str, Any]:
    """日本語: 内容 run の core/facets 化と、想起・型付き拒否."""
    st = CrossStore()
    rep = ingest_text(st, "リンゴは甘い果物です。バナナは黄色い果物です。")
    a = ja_ask(st, "リンゴとは何ですか")
    u = ja_ask(st, "量子とは何ですか")
    ok = (
        rep["cores"] == ["リンゴ", "バナナ"]
        and a["verdict"] == "ANSWER"
        and set(a["facets"]) == {"甘い", "果物"}
        and u["verdict"] == "UNKNOWN_NO_EVIDENCE"
    )
    return {"experiment": "lang", "fork": "LANG_JA_INGEST_ASK",
            "pass": bool(ok), "result": {"ask": a.get("text"), "unknown": u["verdict"]}}


def lang_latin_generic_fork() -> Dict[str, Any]:
    """es/fr/de: 機能語ストップリストつき generic 経路."""
    st = CrossStore()
    ingest_text(st, "La manzana es una fruta dulce.", lang="es")
    ingest_text(st, "La pomme est un fruit sucré.", lang="fr")
    ok = (
        set(dict(st.top_facets("manzana", 4))) == {"fruta", "dulce"}
        and "pomme" in st.crosses
        and "est" not in st.crosses
    )
    return {"experiment": "lang", "fork": "LANG_LATIN_GENERIC",
            "pass": bool(ok), "result": {"cores": sorted(st.crosses)}}


def router_task_label_not_memorized_fork() -> Dict[str, Any]:
    """Labeled academic problem (multi-line paste) must not self-pollute
    the store as a fake fact — regression for a real bug found live: the
    first-token-only check missed "Problem 1: ... prove or disprove ..."
    because the first token is the label, not a question/imperative verb."""
    proof_task = (
        "Problem 1: Reflexivity and Axiom T\n"
        "For a Kripke frame F = (W, R), prove or disprove the following:\n"
        "It is equivalent that F ⊨ □p → p\n"
        "and that R is reflexive."
    )
    st = CrossStore()
    out = route(st, proof_task)
    ok = (
        is_question(proof_task)
        and out.get("remembered") is None
        and "problem" not in st.crosses
    )
    return {"experiment": "router", "fork": "ROUTER_TASK_LABEL_NOT_MEMORIZED",
            "pass": bool(ok), "result": {"cores": sorted(st.crosses)}}


def router_auto_memory_fork() -> Dict[str, Any]:
    """宣言文は記憶、疑問・命令は記憶しない (junk 自己汚染ガード)."""
    st = CrossStore()
    d = route(st, "The staging server is ubuntu .")
    q = route(st, "what is the staging server")
    imp = route(st, "tell me something interesting")
    ok = (
        d.get("remembered") is not None
        and q["verdict"] == "ANSWER"
        and q.get("remembered") is None
        and imp.get("remembered") is None
        and "tell" not in st.crosses
        and is_question("リンゴとは何ですか")
        and not is_question("リンゴは赤い")
    )
    return {"experiment": "router", "fork": "ROUTER_AUTO_MEMORY",
            "pass": bool(ok), "result": {"cores": sorted(st.crosses)}}


def router_allocation_fork() -> Dict[str, Any]:
    """制御配分: 既知→llm_guided(事実注入) / 未知→llm_free / 数学は LLM 不使用."""
    calls: List[Dict[str, Any]] = []

    def stub_llm(prompt: str, system: Optional[str]) -> Dict[str, Any]:
        calls.append({"prompt": prompt, "system": system})
        return {"ok": True, "text": "stub-surface"}

    st = CrossStore()
    st.ingest_sentence("The bright apple is a sweet fruit .")

    g = route(st, "what is apple", llm=stub_llm)
    guided_ok = (
        g["source"] == "llm_guided"
        and "Verified facts" in calls[-1]["prompt"]
        and "apple" in calls[-1]["prompt"]
    )
    f = route(st, "what is quantum theory", llm=stub_llm)
    free_ok = f["source"] == "llm_free" and "NO verified facts" in (calls[-1]["system"] or "")
    n_before = len(calls)
    m = route(st, "what is 247 + 385", llm=stub_llm)
    math_ok = m["source"] == "vera" and m.get("value") == 632 and len(calls) == n_before
    r = route(st, "what is quantum theory", llm=None)
    refuse_ok = r["source"] == "refused" and r["verdict"].startswith("UNKNOWN")
    ok = guided_ok and free_ok and math_ok and refuse_ok
    return {"experiment": "router", "fork": "ROUTER_ALLOCATION",
            "pass": bool(ok),
            "result": {"guided": g["source"], "free": f["source"],
                       "math": m["source"], "refused": r["source"]}}


def all_lang_router_forks() -> List[Dict[str, Any]]:
    return [
        lang_detect_fork(),
        lang_ja_ingest_ask_fork(),
        lang_latin_generic_fork(),
        router_task_label_not_memorized_fork(),
        router_auto_memory_fork(),
        router_allocation_fork(),
    ]
