"""Forks for mass pour → CrossStore → retrieval consensus."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List

from .cross_store import CrossStore, pour_corpus
from .consensus_store import consensus_over_store, probe_coverage


def pour_accumulates_fork() -> Dict[str, Any]:
    """同一 core の facets が文数に単調に累積する (spill/上書きしない)."""
    st = CrossStore()
    st.ingest_sentence("The bright apple is sweet.")
    after1 = dict(st.crosses.get("apple", {}))
    for _ in range(4):
        st.ingest_sentence("The bright apple is sweet.")
    st.ingest_sentence("The red apple is round.")
    facets = st.top_facets("apple", k=8)
    counts = dict(facets)
    ok = (
        after1.get("bright") == 1
        and counts.get("bright") == 5
        and counts.get("sweet") == 5
        and counts.get("red") == 1
        and st.mass("apple") == 6.0
    )
    return {
        "experiment": "pour",
        "fork": "POUR_ACCUMULATES",
        "pass": bool(ok),
        "result": {"facets": facets, "mass": st.mass("apple")},
    }


def pour_checkpoint_fork() -> Dict[str, Any]:
    """save → load round-trip preserves crosses + counts."""
    st = CrossStore()
    st.ingest_sentence("The bright apple is sweet.")
    st.ingest_sentence("Paris is a big city.")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cross_store.json"
        st.save(p)
        st2 = CrossStore.load(p)
    ok = (
        st2.crosses == st.crosses
        and st2.core_count == st.core_count
        and st2.n_sentences == st.n_sentences
    )
    return {
        "experiment": "pour",
        "fork": "POUR_CHECKPOINT",
        "pass": bool(ok),
        "result": st2.report(),
    }


def pour_retrieval_answers_fork() -> Dict[str, Any]:
    """retrieve→consensus: 既知は ANSWER、未知は型付き UNKNOWN、決定論."""
    st = CrossStore()
    for _ in range(3):
        st.ingest_sentence("The bright apple is sweet.")
    st.ingest_sentence("Paris is a big city.")
    a1 = consensus_over_store(st, "what is apple")
    a2 = consensus_over_store(st, "what is apple")
    u = consensus_over_store(st, "what is quantum")
    ok = (
        a1["verdict"] == "ANSWER"
        and a1["core"] == "apple"
        and a1["text"].startswith("apple")
        and a1 == a2
        and u["verdict"].startswith("UNKNOWN")
        and u.get("core") is None
    )
    return {
        "experiment": "pour",
        "fork": "POUR_RETRIEVAL_ANSWERS",
        "pass": bool(ok),
        "result": {"answer": a1["text"], "unknown_verdict": u["verdict"]},
    }


def lex_filter_junk_fork() -> Dict[str, Any]:
    """機能語崩れ core ("however", "two", "s"…) が十字にならない."""
    st = CrossStore()
    r1 = st.ingest_sentence("However , two of the three were lost .")
    r2 = st.ingest_sentence("Later , some said it was over .")
    st.ingest_sentence("The bright apple is sweet .")
    ok = (
        r1 is None
        and r2 is None
        and set(st.crosses) == {"apple"}
        and "s" not in st.crosses.get("apple", {})
    )
    return {
        "experiment": "pour",
        "fork": "LEX_FILTER_JUNK",
        "pass": bool(ok),
        "result": {"cores": sorted(st.crosses)},
    }


def compound_sense_channels_fork() -> Dict[str, Any]:
    """"Sun Tzu" は複合固有名の十字、"sun" は common の十字に分離され、
    what/who で正しい方が勝つ."""
    st = CrossStore()
    st.ingest_sentence("Sun Tzu wrote the ancient treatise on war .")
    st.ingest_sentence("Sun Tzu was a famous general .")
    st.ingest_sentence("The bright sun is hot .")
    st.ingest_sentence("The sun gives warm light .")
    common = consensus_over_store(st, "what is the sun")
    proper = consensus_over_store(st, "who is sun tzu")
    ok = (
        set(st.crosses) == {"sun", "sun_tzu#p"}
        and common["verdict"] == "ANSWER"
        and common["core"] == "sun"
        and "tzu" not in common["text"]
        and proper["verdict"] == "ANSWER"
        and proper["core"] == "sun tzu"
        and "general" in proper["text"]
    )
    return {
        "experiment": "pour",
        "fork": "COMPOUND_SENSE_CHANNELS",
        "pass": bool(ok),
        "result": {
            "cores": sorted(st.crosses),
            "common": common["text"],
            "proper": proper["text"],
        },
    }


def cap_twopass_proper_fork() -> Dict[str, Any]:
    """文頭大文字の二段判定: 文中大文字が優勢な語は文頭でも proper 行き."""
    st = CrossStore()
    stats_rows = [
        "The company Nintendo made a console .",
        "Games from Nintendo sold well .",
        "Critics praised Nintendo for quality .",
        "The bright apple is sweet .",
    ]
    st.scan_cap_stats(stats_rows)
    # pass 2: 文頭 "Nintendo" と文頭 "Apple"(統計なし) を投入
    k1 = st.ingest_sentence("Nintendo released the new console .")
    k2 = st.ingest_sentence("Apple trees grow in the garden .")
    ok = (
        "nintendo" in st.proper_lexicon
        and k1 == "nintendo#p"
        and k2 == "apple"
    )
    return {
        "experiment": "pour",
        "fork": "CAP_TWOPASS_PROPER",
        "pass": bool(ok),
        "result": {
            "proper_lexicon": sorted(st.proper_lexicon),
            "keys": [k1, k2],
        },
    }


def partial_query_gate_fork() -> Dict[str, Any]:
    """複合の意図 ("quantum chromodynamics") を core 単独で答えない."""
    st = CrossStore()
    for _ in range(3):
        st.ingest_sentence("The quantum computer is fast and new .")
    partial = consensus_over_store(st, "what is quantum chromodynamics")
    whole = consensus_over_store(st, "what is quantum")
    ok = (
        partial["verdict"] == "UNKNOWN_INSUFFICIENT_EVIDENCE"
        and partial.get("core") is None
        and "chromodynamics" in partial.get("uncovered_terms", [])
        and whole["verdict"] == "ANSWER"
    )
    return {
        "experiment": "pour",
        "fork": "PARTIAL_QUERY_GATE",
        "pass": bool(ok),
        "result": {
            "partial_verdict": partial["verdict"],
            "uncovered": partial.get("uncovered_terms"),
            "whole_verdict": whole["verdict"],
        },
    }


def sense_cluster_selects_fork() -> Dict[str, Any]:
    """混合 core の語義クラスタ分割 + 指定語での選択 (軸ずらしの実体)."""
    from .sense_split import facet_clusters

    st = CrossStore()
    # 天文の sun
    st.ingest_sentence("The sun is a bright star .")
    st.ingest_sentence("The sun gives light and heat .")
    st.ingest_sentence("A star gives light in the sky .")
    # 企業の sun (同じ common チャネルに混ぜる)
    st.ingest_sentence("The sun company sells java software .")
    st.ingest_sentence("Java is popular computer software .")

    clusters = facet_clusters(st, "sun", min_shared=2, max_mass=800)
    flat = {m for c in clusters for m in c}
    astro_ok = any(
        {"star", "light"} & set(c) and not {"java", "software"} & set(c)
        for c in clusters
    )
    corp_ok = any(
        {"java"} & set(c) and not {"star", "light"} & set(c)
        for c in clusters
    )

    sky = consensus_over_store(st, "what is the sun in the sky")
    corp = consensus_over_store(st, "what is the sun with java software")
    sky_ok = (
        sky["verdict"] == "ANSWER"
        and {"star", "light"} & set(sky["text"].split())
        and "java" not in sky["text"]
    )
    corp_ok2 = (
        corp["verdict"] == "ANSWER"
        and "java" in corp["text"]
        and "star" not in corp["text"]
    )
    ok = astro_ok and corp_ok and sky_ok and corp_ok2
    return {
        "experiment": "pour",
        "fork": "SENSE_CLUSTER_SELECTS",
        "pass": bool(ok),
        "result": {
            "clusters": clusters,
            "sky_text": sky["text"],
            "corp_text": corp["text"],
            "n_facets": len(flat),
        },
    }


def namespaced_key_nl_query_fork() -> Dict[str, Any]:
    """構造化 key:value レコード ("contest:2026h1") が recall だけでなく
    自然文の質問でも引ける — 以前は colon がトークナイザで落ちるため
    UNKNOWN_NO_EVIDENCE になっていた回帰."""
    st = CrossStore()
    st.add("contest:2026h1", [
        "deadline:2026-09-11", "mandatory:insert", "mandatory:select",
        "prohibited:javascript_validation",
    ])
    hit = consensus_over_store(st, "what is contest:2026h1")
    no_prefix = consensus_over_store(st, "contest:2026h1")
    unknown_id = consensus_over_store(st, "what is foo:bar")
    ok = (
        hit["verdict"] == "ANSWER"
        and hit["core"] == "contest:2026h1"
        and hit.get("uncovered_terms") == []
        and "deadline:2026-09-11" in hit["text"]
        and no_prefix["verdict"] == "ANSWER"
        and unknown_id["verdict"] == "UNKNOWN_NO_EVIDENCE"
    )
    return {
        "experiment": "pour",
        "fork": "NAMESPACED_KEY_NL_QUERY",
        "pass": bool(ok),
        "result": {"text": hit.get("text"), "uncovered": hit.get("uncovered_terms"),
                   "unknown_verdict": unknown_id["verdict"]},
    }


def pour_corpus_pilot_fork(
    *, source: str = "auto", max_rows: int = 400, max_sentences: int = 400
) -> Dict[str, Any]:
    """corpus stream → accumulate → coverage probe (source は正直に記録)."""
    st, rep = pour_corpus(
        source=source, max_rows=max_rows, max_sentences=max_sentences
    )
    top_cores = sorted(
        st.core_count.items(), key=lambda kv: (-kv[1], kv[0])
    )[:5]
    queries: List[str] = [f"what is {c}" for c, _ in top_cores]
    queries.append("what is zzzunseen")
    cov = probe_coverage(st, queries)
    unseen = cov["samples"][-1]
    ok = (
        rep["n_cores"] > 0
        and rep["n_facet_links"] > 0
        and cov["breakdown"].get("ANSWER", 0) >= 1
        and unseen["verdict"].startswith("UNKNOWN")
    )
    return {
        "experiment": "pour",
        "fork": "POUR_CORPUS_PILOT",
        "pass": bool(ok),
        "result": {
            "pour": rep,
            "top_cores": top_cores,
            "coverage": {
                "breakdown": cov["breakdown"],
                "answer_rate": cov["answer_rate"],
            },
        },
    }


def all_pour_forks() -> List[Dict[str, Any]]:
    return [
        pour_accumulates_fork(),
        pour_checkpoint_fork(),
        pour_retrieval_answers_fork(),
        lex_filter_junk_fork(),
        compound_sense_channels_fork(),
        cap_twopass_proper_fork(),
        partial_query_gate_fork(),
        sense_cluster_selects_fork(),
        namespaced_key_nl_query_fork(),
        pour_corpus_pilot_fork(),
    ]
