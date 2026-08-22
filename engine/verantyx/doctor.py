# -*- coding: utf-8 -*-
"""二つの顔の自己検査 — 番人(G1〜G4)と単体の装置(S1〜S4)。

事前登録: experiments/guard/PREREG5_FREEZE.md / PREREG6_STANDALONE.md

他人のマシンに入れた直後に叩くもの。**「実装されている」ではなく
「今このマシンで動いた」を見る**ので、検査は毎回その場で店と台帳を
作って実際に走らせる。利用者の店にも台帳にも触らない。

壊れた実装を注入できるようにしてあるのは、**壊れているときに
BROKEN と言えることを測るため**。通るだけの自己検査は自己申告と同じで、
嘘をつく自己検査は無いより悪い。
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any, Callable, Dict, List

#: 治具は小さく閉じたものにする(導入直後に叩くので速さが要る)。
#: 企業文書2件と技術方針1件 — 条番号を持つ文を入れてあるのは、
#: 答えが取り込んだ文の語だけでできていることを見るため。
_FIXTURE = [
    ("社内規程", "第3条 出張費は事前承認が必要である。"
                 "第4条 交際費は上限を月5万円とする。"),
    ("就業規則", "第7条 在宅勤務は週3日まで認める。"),
    ("技術方針", "実装言語はTypeScriptを用いる。テストはpytestで書く。"),
]
#: 在庫内の問いと、期待する核。在庫外の問いは何を返しても ANSWER で
#: あってはならない(近傍を返す装置との差はここに出る)。
_IN_STOCK = [("出張費", "出張費"), ("交際費", "交際費"),
             ("在宅勤務", "在宅勤務")]
_OUT_OF_STOCK = ["ゾルタクスゼイアン", "深海探査船の定員", "quantum flux capacitor"]


def _build_store(order: List[int], ingest: Callable, store_cls: Any):
    from .document_ingest import Document

    st = store_cls()
    ingest(st, [Document(source=_FIXTURE[i][0], text=_FIXTURE[i][1])
                for i in order])
    return st


def store_self_check(ask: Callable = None, ingest: Callable = None,
                     store_cls: Any = None) -> Dict[str, Any]:
    """単体の装置としての保証 S1〜S4 を、その場で実演して確かめる。"""
    from .cross_store import CrossStore
    from .document_ingest import ingest_documents

    ask = ask or _default_ask
    ingest = ingest or ingest_documents
    store_cls = store_cls or CrossStore

    probes: List[Dict[str, Any]] = []

    def probe(name, ok, detail):
        probes.append({"probe": name, "pass": bool(ok), "detail": detail})

    try:
        st = _build_store([0, 1, 2], ingest, store_cls)
    except Exception as e:                     # noqa: BLE001
        for n in ("S1_in_stock_answers", "S2_absence_is_refused",
                  "S3_ingest_order_invariant", "S4_answer_uses_only_stored_words"):
            probe(n, False, {"error": repr(e)})
        return _verdict(probes)

    # S1 在庫にあることは答える
    try:
        got = [(q, ask(st, q)) for q, _core in _IN_STOCK]
        ok = all(o.get("verdict") == "ANSWER" and o.get("core") == core
                 for (q, o), (_q, core) in zip(got, _IN_STOCK))
        probe("S1_in_stock_answers", ok,
              {q: [o.get("verdict"), o.get("core")] for q, o in got})
    except Exception as e:                     # noqa: BLE001
        probe("S1_in_stock_answers", False, {"error": repr(e)})

    # S2 無いことは型つきで断る(近傍を返さない)
    try:
        got = [(q, ask(st, q)) for q in _OUT_OF_STOCK]
        # 「不在」は UNKNOWN_* で、理由が付いていること。ANSWER は不可。
        ok = all(str(o.get("verdict", "")).startswith("UNKNOWN")
                 and not o.get("text") for _q, o in got)
        probe("S2_absence_is_refused", ok,
              {q: [o.get("verdict"), o.get("reason")] for q, o in got})
    except Exception as e:                     # noqa: BLE001
        probe("S2_absence_is_refused", False, {"error": repr(e)})

    # S3 取り込み順に依らない
    try:
        seen: Dict[str, set] = {q: set() for q, _c in _IN_STOCK}
        for order in itertools.permutations(range(len(_FIXTURE))):
            s2 = _build_store(list(order), ingest, store_cls)
            for q, _core in _IN_STOCK:
                o = ask(s2, q)
                seen[q].add((o.get("verdict"), o.get("core")))
        ok = all(len(v) == 1 for v in seen.values())
        probe("S3_ingest_order_invariant", ok,
              {"permutations": 6,
               "distinct_outcomes": {q: len(v) for q, v in seen.items()}})
    except Exception as e:                     # noqa: BLE001
        probe("S3_ingest_order_invariant", False, {"error": repr(e)})

    # S4 答えは店にある語だけでできている(店の外の語を持ち込まない)
    try:
        known = set(st.crosses)
        for _core, facets in st.crosses.items():
            known.update(facets)
        strangers: Dict[str, List[str]] = {}
        for q, _core in _IN_STOCK:
            o = ask(st, q)
            out = [t for t in (o.get("tokens") or str(o.get("text", "")).split())
                   if t not in known]
            if out:
                strangers[q] = out
        probe("S4_answer_uses_only_stored_words", not strangers,
              {"strangers": strangers or "none",
               "store_vocabulary": len(known)})
    except Exception as e:                     # noqa: BLE001
        probe("S4_answer_uses_only_stored_words", False, {"error": repr(e)})

    return _verdict(probes)


def _default_ask(store: Any, question: str) -> Dict[str, Any]:
    from .consensus_store import consensus_over_store

    return consensus_over_store(store, question)


def _verdict(probes: List[Dict[str, Any]]) -> Dict[str, Any]:
    failed = [p["probe"] for p in probes if not p["pass"]]
    return {"verdict": "BROKEN" if failed else "OK",
            "guarantees": probes, "failed": failed}


# ---------------------------------------------------------------------------
# ① 配線 — 静かに壊れないこと(PREREG8)
# ---------------------------------------------------------------------------
#: 探す設定ファイル(閉じた表)。無い場所は「未導入」であって故障ではない。
_HOOK_SETTINGS = ["~/.claude/settings.json", "~/.claude/settings.local.json",
                  ".claude/settings.json", ".claude/settings.local.json"]
_MCP_CONFIGS = [".mcp.json", "~/.claude.json",
                "~/Library/Application Support/Claude/"
                "claude_desktop_config.json", "~/.cursor/mcp.json"]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _hook_commands(cfg: Any) -> List[str]:
    """設定から番人の台本を指す command だけを拾う(閉じた読み方)。"""
    out: List[str] = []
    hooks = (cfg or {}).get("hooks") if isinstance(cfg, dict) else None
    if not isinstance(hooks, dict):
        return out
    for entries in hooks.values():
        for entry in (entries if isinstance(entries, list) else []):
            for h in (entry.get("hooks") or []) if isinstance(entry, dict) else []:
                cmd = str(h.get("command", ""))
                if "hook_prompt" in cmd or "hook_stop" in cmd \
                        or "hook_posttool" in cmd:
                    out.append(cmd)
    return out


def installation_check(repo_root: Any = None,
                       settings_files: Any = None,
                       mcp_files: Any = None) -> Dict[str, Any]:
    """配線が生きているかを見る — 保証(G/S)とは別の問い。

    番人は CLI が落ちれば素通しする(利用者の作業を Vera の都合で
    止めない)。裏返すと**配線が死んでも画面は正常に見える**。三週間
    守られていなかったことに後から気づく、が一番怖い故障なので、
    ここだけは名指しで報せる。

    未導入は故障ではない(単体だけ使う人がいる)。だから三値:
    WIRED / PARTIAL / NOT_WIRED。**健全な環境で PARTIAL を出したら
    この検査ごと棄てる**(狼少年の番人は切られる)。
    """
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[1]
    rows: List[Dict[str, Any]] = []
    configured = 0

    # W1 フックの設定と、それが指す台本
    for rel in (settings_files if settings_files is not None
                else _HOOK_SETTINGS):
        path = Path(rel).expanduser()
        cfg = _read_json(path) if path.is_file() else None
        cmds = _hook_commands(cfg)
        if not cmds:
            continue
        configured += 1
        for cmd in cmds:
            script = next((tok for tok in cmd.split()
                           if tok.endswith(".py")), "")
            exists = bool(script) and Path(script).expanduser().is_file()
            rows.append({"what": "hook", "where": str(path), "cmd": cmd[:120],
                         "state": "OK" if exists else "MISSING_SCRIPT"})

    # W2 呼ばれる実体(ソース or 凍結)と、凍結の鮮度
    # 凍結バイナリの中では __file__ が展開先を指すので、そこに repo が
    # 無いのは当たり前 — 実体はバイナリ自身。ここを見落とすと**健全な
    # 環境で誤警報**になる(この検査の停止条件そのもの。実測して直した)。
    import sys as _sys

    frozen = bool(getattr(_sys, "frozen", False))
    src_ok = (root / "verantyx" / "cli.py").is_file()
    if frozen:
        rows.append({"what": "implementation", "where": _sys.executable,
                     "state": "OK", "note": "凍結バイナリ自身が実体"})
    else:
        rows.append({"what": "source", "where": str(root),
                     "state": "OK" if src_ok else "MISSING"})
    vendor = Path.home() / "Projects/Verantyx/cli/VerantyxIDE/Vendor/vera-memory"
    # 鮮度は**ソースがある機械でしか判定できない**(比べる相手が要る)。
    # 無い機械で「古いかもしれない」と言うのは推測なので言わない。
    if vendor.exists() and src_ok:
        newest = max((f.stat().st_mtime for f in
                      (root / "verantyx").glob("*.py")), default=0)
        stale = vendor.stat().st_mtime < newest
        rows.append({"what": "frozen_binary", "where": str(vendor),
                     "state": "STALE" if stale else "OK",
                     "note": ("凍結が repo より古い — 再凍結が要る"
                              if stale else "")})

    # W3 MCP 設定が実在する command と store を指しているか
    for rel in (mcp_files if mcp_files is not None else _MCP_CONFIGS):
        path = Path(rel).expanduser()
        cfg = _read_json(path) if path.is_file() else None
        servers = (cfg or {}).get("mcpServers") if isinstance(cfg, dict) else None
        if not isinstance(servers, dict):
            continue
        for name, entry in servers.items():
            if "vera" not in str(name).lower():
                continue
            configured += 1
            cmd = str((entry or {}).get("command", ""))
            args = [str(a) for a in ((entry or {}).get("args") or [])]
            cmd_ok = bool(cmd) and (Path(cmd).expanduser().exists()
                                    or cmd in ("python3", "python3.11",
                                               "python"))
            store = args[args.index("--store") + 1] \
                if "--store" in args and len(args) > args.index("--store") + 1 \
                else ""
            store_ok = (not store
                        or Path(store).expanduser().parent.is_dir())
            state = ("OK" if cmd_ok and store_ok else
                     "MISSING_COMMAND" if not cmd_ok else "MISSING_STORE_DIR")
            rows.append({"what": "mcp_server", "where": str(path),
                         "name": name, "state": state})

    bad = [r for r in rows if r["state"] not in ("OK", "")]
    if not configured:
        verdict = "NOT_WIRED"
    elif bad:
        verdict = "PARTIAL"
    else:
        verdict = "WIRED"
    return {"verdict": verdict, "rows": rows, "configured_places": configured,
            "problems": [f"{r['what']}: {r['state']}" for r in bad],
            "note": "未導入(NOT_WIRED)は故障ではない — 保証が壊れたときだけ "
                    "BROKEN。ここは『黙って素通しになっていないか』だけを見る"}


def full_doctor() -> Dict[str, Any]:
    """二つの顔を1回で。**片方が壊れていれば全体は BROKEN**。

    番人だけ緑で単体が壊れている(あるいはその逆)を「概ね健全」と
    まとめない — 要約が証拠を隠さない、はこの装置の線。
    """
    from .covenant import self_check

    guard = self_check()
    standalone = store_self_check()
    wiring = installation_check()
    failed = list(guard["failed"]) + list(standalone["failed"])
    verdict = ("BROKEN" if failed else
               "DEGRADED" if wiring["verdict"] == "PARTIAL" else "OK")
    return {
        "verdict": verdict,
        "guard": guard,
        "standalone": standalone,
        "wiring": wiring,
        "failed": failed,
        "note": "guaranteed properties are re-run here and now; what is "
                "NOT guaranteed is named in experiments/guard/"
                "PREREG5_FREEZE.md (N1-N7) and PREREG6_STANDALONE.md",
    }
