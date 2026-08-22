"""Forks for phase 2: debug consensus, memory provenance/contradiction,
SQLite backend, Japanese consensus decomposer."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List

from .consensus_store import ja_consensus_ask
from .cross_store import CrossStore
from .debug_consensus import (
    baseline_recent_change,
    baseline_traceback_top,
    locate_bug,
)
from .lang import ingest_text
from .store_sqlite import SqliteSync, load_sqlite, save_sqlite


def _buggy_repo_store() -> CrossStore:
    """Synthetic call graph: test → api → parse → normalize (bug here)."""
    st = CrossStore()
    st.add("fn:test_pipeline", ["file:tests.py", "calls:api_handler"])
    st.add("fn:api_handler", ["file:api.py", "calls:parse_input", "calls:log"])
    st.add("fn:parse_input", ["file:parse.py", "calls:normalize"])
    st.add("fn:normalize", ["file:parse.py", "calls:strip"])
    st.add("fn:log", ["file:util.py"])
    st.add("fn:unrelated_helper", ["file:util.py", "calls:log"])
    return st


_TRACEBACK = """Traceback (most recent call last):
  File "tests.py", line 10, in test_pipeline
  File "api.py", line 22, in api_handler
  File "parse.py", line 31, in parse_input
  File "parse.py", line 40, in normalize
TypeError: unsupported operand
"""


def debug_consensus_locates_fork() -> Dict[str, Any]:
    """3断面 (traceback/diff/test) が normalize に収束 → ANSWER."""
    st = _buggy_repo_store()
    out = locate_bug(
        st,
        traceback_text=_TRACEBACK,
        changed_functions=["normalize", "unrelated_helper"],
        failing_tests=["test_pipeline"],
    )
    ok = (
        out["verdict"] == "ANSWER"
        and out["cause"] == "normalize"
        and set(out["agreed_by"]) == {"traceback", "diff", "test"}
    )
    return {"experiment": "debug", "fork": "DEBUG_CONSENSUS_LOCATES",
            "pass": bool(ok), "result": {k: out[k] for k in ("verdict", "cause", "agreed_by") if k in out}}


def debug_disagreement_unknown_fork() -> Dict[str, Any]:
    """断面が別の関数を指すとき多数決せず型付き UNKNOWN / 単断面は出荷しない."""
    st = _buggy_repo_store()
    # diff は unrelated_helper だけ、traceback なし、test 断面は経路全部
    out = locate_bug(
        st,
        changed_functions=["unrelated_helper"],
        failing_tests=["test_pipeline"],
    )
    single = locate_bug(st, changed_functions=["normalize"])
    ok = (
        out["verdict"] in ("UNKNOWN_SECTION_DISAGREEMENT", "AMBIGUOUS")
        and out["cause"] is None
        and single["verdict"] != "ANSWER"  # 1断面では出荷しない
    )
    return {"experiment": "debug", "fork": "DEBUG_DISAGREE_UNKNOWN",
            "pass": bool(ok),
            "result": {"multi": out["verdict"], "single": single["verdict"]}}


def debug_beats_baselines_fork() -> Dict[str, Any]:
    """誤変更ノイズ下で、単一根拠ベースラインより正しい原因に当たる."""
    st = _buggy_repo_store()
    # ノイズ: 直近変更の先頭は無関係関数 (recent-change baseline を騙す)
    changed = ["unrelated_helper", "normalize"]
    consensus = locate_bug(
        st, traceback_text=_TRACEBACK, changed_functions=changed,
        failing_tests=["test_pipeline"],
    )
    b_change = baseline_recent_change(st, changed)
    b_tb = baseline_traceback_top(st, _TRACEBACK)
    ok = (
        consensus["verdict"] == "ANSWER"
        and consensus["cause"] == "normalize"
        and b_change == "unrelated_helper"  # baseline は騙される
        and b_tb == "normalize"             # tb-top は今回は正しい (記録)
    )
    return {"experiment": "debug", "fork": "DEBUG_BEATS_BASELINES",
            "pass": bool(ok),
            "result": {"consensus": consensus["cause"],
                       "baseline_recent_change": b_change,
                       "baseline_traceback_top": b_tb}}


def memory_provenance_contradiction_fork() -> Dict[str, Any]:
    """出典・時刻の記録と、key:value 排他の矛盾検出 (上書きしない)."""
    st = CrossStore(track_provenance=True)
    st.add("ticket:db-choice", ["db:postgres"], source="meeting 6/1")
    st.add("ticket:db-choice", ["db:mysql"], source="slack 7/2")
    cons = st.contradictions("ticket:db-choice")
    prov = st.provenance["ticket:db-choice"]["db:postgres"]
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "s.json"
        st.save(p)
        st2 = CrossStore.load(p)
    ok = (
        len(cons) == 1
        and cons[0]["key"] == "db"
        and set(cons[0]["values"]) == {"db:postgres", "db:mysql"}
        and prov[2] == "meeting 6/1"
        and st2.track_provenance
        and st2.contradictions("ticket:db-choice") == cons
    )
    return {"experiment": "memory", "fork": "MEMORY_PROVENANCE_CONTRADICTION",
            "pass": bool(ok), "result": {"contradictions": cons}}


def sqlite_roundtrip_fork() -> Dict[str, Any]:
    """SQLite full save → load 同一 / SqliteSync の差分 flush."""
    st = CrossStore(track_provenance=True)
    ingest_text(st, "The bright apple is sweet .")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "s.db"
        save_sqlite(st, p)
        st2 = load_sqlite(p)
        same = st2.crosses == st.crosses and st2.core_count == st.core_count
        sync = SqliteSync(st2, p)
        st2.add("banana", ["yellow"], source="manual")
        n = sync.flush()
        st3 = load_sqlite(p)
        delta_ok = n == 1 and "banana" in st3.crosses
    ok = same and delta_ok
    return {"experiment": "sqlite", "fork": "SQLITE_ROUNDTRIP",
            "pass": bool(ok), "result": {"flushed": n}}


def ja_consensus_fork() -> Dict[str, Any]:
    """日本語 run → qset → 三段ゲート合意 (接地・根拠・拒否が日本語でも効く)."""
    st = CrossStore()
    ingest_text(st, "リンゴは甘い果物です。リンゴは赤い果物です。バナナは黄色い果物です。")
    a = ja_consensus_ask(st, "リンゴとは何ですか")
    u = ja_consensus_ask(st, "量子とは何ですか")
    ok = (
        a["verdict"] == "ANSWER"
        and a["core"] == "リンゴ"
        and "果物" in a["text"]
        and u["verdict"] == "UNKNOWN_NO_EVIDENCE"
    )
    return {"experiment": "lang", "fork": "LANG_JA_CONSENSUS",
            "pass": bool(ok),
            "result": {"answer": a.get("text"), "unknown": u["verdict"]}}


def all_phase2_forks() -> List[Dict[str, Any]]:
    return [
        debug_consensus_locates_fork(),
        debug_disagreement_unknown_fork(),
        debug_beats_baselines_fork(),
        memory_provenance_contradiction_fork(),
        sqlite_roundtrip_fork(),
        ja_consensus_fork(),
    ]
