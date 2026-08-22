"""vera — CLI for Verantyx Vera α (lab + chat in one binary).

Knowledge:
  vera pour --source synthetic|wikitext|hf:<name>[#config][:field]|file:<path>
  vera remember "The bright apple is sweet ."
  vera ask "what is apple"
  vera forget apple
  vera stats
  vera chat                    interactive REPL (knowledge + math + code)

Math / logic:
  vera math "x + 3 = 7"        wire arithmetic / typed equations
  vera simplify "x + 0"        term rewriting (rules are data)

Code reasoning:
  vera code ingest <path>
  vera code ask "who calls foo"

Lab:
  vera lab                     run the fork self-test suites
  vera mcp                     start the MCP server (see docs/MCP.md)

Default store: ./vera_store.json (override with --store).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .code_ingest import code_ask, ingest_python_repo
from .consensus_store import consensus_over_store
from .cross_store import CrossStore, pour_corpus
from .math_sim import math_ask
from .rewrite_kernel import default_algebra_rules, simplify

DEFAULT_STORE = "vera_store.json"


def _load(path: str, *, base_repo: str = "") -> CrossStore:
    p = Path(path)
    if not p.is_file() and base_repo:
        from .hf_store import ensure_store

        res = ensure_store(path, base_repo)
        if res.get("ok"):
            print(f"[store] fetched base store from HuggingFace: {base_repo}")
    return CrossStore.load(p) if p.is_file() else CrossStore()


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _route(store: CrossStore, query: str) -> Dict[str, Any]:
    """math → code → knowledge, refusing rather than guessing."""
    m = math_ask(query)
    if m["verdict"] != "UNKNOWN_UNPARSED":
        m["route"] = "math"
        return m
    c = code_ask(store, query)
    if c["verdict"] != "UNKNOWN_UNPARSED":
        c["route"] = "code"
        return c
    out = consensus_over_store(store, query)
    out["route"] = "knowledge"
    return out


def cmd_pour(args) -> int:
    ckpt = Path(args.store)
    prev = CrossStore.load(ckpt) if ckpt.is_file() else None
    source = args.source
    kw: Dict[str, Any] = {}
    if source.startswith("file:"):
        from .corpus_en import iter_local_rows

        rows = iter_local_rows(Path(source[5:]))
        st = prev or CrossStore()
        if not args.no_two_pass:
            st.scan_cap_stats(iter_local_rows(Path(source[5:])))
        rep = st.ingest_rows(rows, max_sentences=args.max_sentences)
        st.source = source
        st.save(ckpt)
        _print({"pour": rep, "store": str(ckpt)})
        return 0
    st, rep = pour_corpus(
        source=source,
        max_rows=args.max_rows,
        max_sentences=args.max_sentences,
        checkpoint_path=ckpt,
        store=prev,
        two_pass=not args.no_two_pass,
        checkpoint_every=args.checkpoint_every,
        **kw,
    )
    _print({"pour": rep, "store": str(ckpt)})
    return 0


def cmd_remember(args) -> int:
    st = _load(args.store)
    key = st.ingest_sentence(args.text)
    st.save(Path(args.store))
    _print({"remembered": key, "facets": st.top_facets(key or "", 8)})
    return 0 if key else 1


def cmd_forget(args) -> int:
    st = _load(args.store)
    removed = []
    for key in (args.core, args.core + "#p"):
        if key in st.crosses:
            del st.crosses[key]
            st.core_count.pop(key, None)
            removed.append(key)
    st.save(Path(args.store))
    _print({"forgot": removed})
    return 0 if removed else 1


def cmd_ask(args) -> int:
    st = _load(args.store)
    _print(_route(st, args.query))
    return 0


def _doors(store_path: str) -> Dict[str, Any]:
    """126扉を**走らせずに**取り出す。CLI と MCP は同じ扉を使う。

    扉ごとに CLI のコマンドを書き写すと二つの表面が必ずずれるので、
    入口だけを増やして実体は一つに保つ(2026-08-22)。
    """
    from .mcp_server import build

    mcp = build(store_path)
    if mcp is None:
        return {}
    return {t.name: t for t in mcp._tool_manager.list_tools()}


def _coerce(fn, kwargs: Dict[str, str]) -> Dict[str, Any]:
    """`k=v` を扉の型注釈に合わせる(閉じた4型のみ。推測しない)。"""
    import inspect

    sig = inspect.signature(fn)
    out: Dict[str, Any] = {}
    for k, v in kwargs.items():
        ann = sig.parameters[k].annotation if k in sig.parameters else str
        if ann is bool:
            out[k] = str(v).strip().lower() in ("1", "true", "yes", "on")
        elif ann is int:
            out[k] = int(v)
        elif ann is float:
            out[k] = float(v)
        else:
            out[k] = v
    return out


def _call_door(store_path: str, name: str, payload: Dict[str, Any]) -> int:
    doors = _doors(store_path)
    if not doors:
        _print({"verdict": "UNKNOWN_NO_MCP_SDK"})
        return 2
    if name not in doors:
        near = [n for n in doors if name in n][:8]
        _print({"verdict": "UNKNOWN_NO_SUCH_DOOR", "door": name,
                "did_you_mean": near, "doors": len(doors)})
        return 1
    out = doors[name].fn(**payload)
    try:
        _print(json.loads(out) if isinstance(out, str) else out)
    except Exception:              # 扉が素の文字列を返す場合はそのまま
        print(out)
    return 0


def cmd_tool(args) -> int:
    """MCP の扉を CLI から。IDE を経由せずに全機能へ届かせるための橋。"""
    doors = _doors(args.store)
    if not doors:
        _print({"verdict": "UNKNOWN_NO_MCP_SDK"})
        return 2
    if args.tool_op == "list":
        pat = (args.name or "").lower()
        rows = [{"door": n,
                 "about": " ".join((t.description or "").split())[:90]}
                for n, t in sorted(doors.items())
                if not pat or pat in n.lower()]
        _print({"doors": len(rows), "list": rows})
        return 0
    if not args.name:
        _print({"verdict": "UNKNOWN_NO_DOOR_NAMED"})
        return 1
    if args.tool_op == "show":
        t = doors.get(args.name)
        if t is None:
            return _call_door(args.store, args.name, {})
        import inspect

        print(f"{args.name}{inspect.signature(t.fn)}\n")
        print(inspect.getdoc(t.fn) or "(no docstring)")
        return 0
    # call
    payload: Dict[str, Any] = {}
    if args.json:
        payload.update(json.loads(args.json))
    pairs = {}
    for kv in (args.arg or []):
        if "=" not in kv:
            _print({"verdict": "UNKNOWN_BAD_ARG", "arg": kv})
            return 1
        k, v = kv.split("=", 1)
        pairs[k] = v
    t = doors.get(args.name)
    if t is not None and pairs:
        payload.update(_coerce(t.fn, pairs))
    return _call_door(args.store, args.name, payload)


def cmd_documents(args) -> int:
    """文書を CLI から入れる(PDF/Word/HTML/CSV/JSON/テキスト、フォルダ可)。

    実体は扉 `load_documents` — IDE と同じ経路を通す(別経路を書くと
    「IDE では入るが CLI では入らない」が生まれる)。
    """
    return _call_door(args.store, "load_documents",
                      {"paths": ",".join(args.paths),
                       "ingest": not args.no_ingest})


def cmd_domain(args) -> int:
    """分野(語彙)の登録と確認。実体は既存の扉。"""
    op = args.domain_op
    if op == "list":
        return _call_door(args.store, "vera_domains", {})
    if op == "add":
        if not (args.name and args.path):
            _print({"verdict": "UNKNOWN_NEEDS_NAME_AND_PATH"})
            return 1
        return _call_door(args.store, "vera_domain",
                          {"name": args.name, "path": args.path})
    if op == "pending":
        return _call_door(args.store, "list_pending_domain_modules", {})
    if op in ("accept", "reject"):
        if args.index is None:
            _print({"verdict": "UNKNOWN_NEEDS_INDEX"})
            return 1
        return _call_door(args.store, f"{op}_domain_module",
                          {"index": args.index})
    _print({"verdict": "UNKNOWN_OP", "op": op})
    return 1


#: 貼り先(閉じた表)。IDE の MCP 画面が発行していたスニペットを CLI へ
#: 移す(2026-08-22)。**書き込みは --install を打った人の行為**で、
#: 既定は表示だけ — 設定ファイルを黙って書き換えない。
_MCP_CLIENTS = {
    "claude-code": ".mcp.json",
    "claude-desktop": "~/Library/Application Support/Claude/"
                      "claude_desktop_config.json",
    "cursor": "~/.cursor/mcp.json",
}


def _vera_binary() -> List[str]:
    """この機械で MCP を起動する実際のコマンド(推測しない)。"""
    import shutil
    import sys as _s

    vendor = Path.home() / ("Projects/Verantyx/cli/VerantyxIDE/Vendor/"
                            "vera-memory")
    if getattr(_s, "frozen", False):
        return [_s.executable]
    if vendor.exists():
        return [str(vendor)]
    found = shutil.which("vera-memory")
    if found:
        return [found]
    return [_s.executable, "-m", "verantyx.cli"]


def cmd_mcp_config(args) -> int:
    """MCP の設定スニペットを出す(必要なら貼る)。

    IDE の MCP 画面がやっていた仕事のうち、CLI に無かったのはこれ。
    他サーバの接続管理は Claude Code 自身の機能なので写さない
    (同じ仕事を二つ持つと必ずずれる)。
    """
    store = str(Path(args.store or DEFAULT_STORE).resolve())
    cmd = _vera_binary()
    entry = {"command": cmd[0],
             "args": cmd[1:] + ["--store", store, "mcp"]}
    snippet = {"mcpServers": {"vera-memory": entry}}
    targets = ([(k, v) for k, v in _MCP_CLIENTS.items()]
               if args.client == "all"
               else [(args.client, _MCP_CLIENTS[args.client])])
    out = {"verdict": "ANSWER", "snippet": snippet,
           "targets": {k: str(Path(v).expanduser()) for k, v in targets},
           "note": "既定は表示のみ。--install で貼る(貼るのは打った人の行為)"}
    if args.install:
        wrote = {}
        for name, rel in targets:
            path = (Path(rel).expanduser() if rel.startswith("~")
                    else Path.cwd() / rel)
            try:
                cur = json.loads(path.read_text(encoding="utf-8")) \
                    if path.is_file() else {}
            except Exception:
                out["verdict"] = "UNKNOWN_UNREADABLE_CONFIG"
                wrote[name] = "読めない設定があるので触らない"
                continue
            servers = dict(cur.get("mcpServers") or {})
            servers["vera-memory"] = entry     # 同名だけ差し替える
            cur["mcpServers"] = servers
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(cur, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            wrote[name] = str(path)
        out["installed"] = wrote
    _print(out)
    return 0


def cmd_index(args) -> int:
    """「それは既に在るか」に答える索引 — 実装の前に必ずここを引く。

    67,145行・129扉・89 fork は誰の作業記憶にも文脈窓にも入らない。
    索引が無いと、人もモデルも既にあるものを作り直す(実際に起きた)。
    索引はコードと文書から**その場で導出**するので、古くならない。
    """
    from .index import build, markdown, search

    if args.index_op == "build":
        idx = build()
        _print({"verdict": "ANSWER", "counts": idx["counts"],
                "total": idx["total"], "root": idx["root"]})
    elif args.index_op == "markdown":
        text = markdown()
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            _print({"verdict": "ANSWER", "wrote": args.out,
                    "bytes": len(text.encode("utf-8"))})
        else:
            print(text)
    else:
        _print(search(" ".join(args.query), limit=args.limit))
    return 0


def cmd_doctor(args) -> int:
    """入れた直後に叩く自己検査 — 二つの顔を1回で確かめる。

    番人(フック)の G1〜G4 と、単体の装置の S1〜S4 を**その場で実演**
    する。利用者の店にも台帳にも触らない(治具は毎回その場で作る)。
    片方が壊れていれば全体は BROKEN で、終了コードは1。
    """
    from .doctor import full_doctor

    out = full_doctor()
    _print(out)
    return 1 if out.get("verdict") == "BROKEN" else 0


def cmd_stats(args) -> int:
    st = _load(args.store)
    top = sorted(st.core_count.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    _print({**st.report(), "top_cores": top})
    return 0


def cmd_heartbeat(args) -> int:
    """Milestone M: scans growth_signals.json for recurring UNKNOWN
    patterns, drafts+verifies a candidate module via an LLM if one clears
    the boundary detector, and queues it for human review — never
    auto-activates. Intended for a daily cron/launchd job, not per-turn."""
    from . import boundary, domains
    from .growth_signals import GrowthSignals, growth_signals_path
    from .llm_local import ollama_available
    from .module_forge import build_test_queries, draft_module
    from .module_ingest import DomainModuleQuarantine
    from .module_verify import verify_module

    st = _load(args.store)
    store_path = Path(args.store)
    pkg_dir = Path(__file__).resolve().parent
    domains.register_builtins()
    domains.register_generated(pkg_dir)

    gpath = growth_signals_path(store_path)
    growth = GrowthSignals.load(gpath)
    drifted = growth.record_mass_snapshot(st)

    mqpath = store_path.with_name(store_path.stem + ".module_quarantine.json")
    module_quarantine = DomainModuleQuarantine.load(mqpath)

    candidates, drafted_out = [], []
    for bucket in growth.buckets.values():
        verdict = boundary.classify(bucket)
        if verdict.classification != "growth_candidate":
            continue
        candidates.append({"normalized": bucket.normalized, "reason": verdict.reason})
        if not args.llm_model or not ollama_available():
            continue
        draft = draft_module(bucket, args.llm_model)
        if not draft["ok"]:
            drafted_out.append({"normalized": bucket.normalized, "ok": False, "error": draft["error"]})
            continue
        ok, reports = verify_module(draft["source"], build_test_queries(bucket), st, draft["name"])
        report_dicts = [r.as_dict() for r in reports]
        if ok:
            module_quarantine.propose(draft["name"], draft["source"], bucket.normalized, report_dicts)
            drafted_out.append({"normalized": bucket.normalized, "ok": True, "name": draft["name"], "queued": True})
        else:
            drafted_out.append({"normalized": bucket.normalized, "ok": False, "verify_reports": report_dicts})

    # Capacity pass — same helper the MCP heartbeat uses, so the CLI and
    # server cannot drift apart in what a heartbeat means.
    from .capacity_calibration import capacity_pass
    from .capacity_ingest import CapacityQuarantine
    from .config import VeraConfig

    cqpath = store_path.with_name(store_path.stem + ".capacity_quarantine.json")
    capacity_quarantine = CapacityQuarantine.load(cqpath)
    capacity = capacity_pass(
        list(growth.buckets.values()), VeraConfig.load(), capacity_quarantine)
    if any(r.get("queued") for r in capacity):
        capacity_quarantine.save(cqpath)

    growth.save(gpath)
    module_quarantine.save(mqpath)
    _print({"drifted_cores": drifted, "growth_candidates": candidates,
            "drafted": drafted_out, "capacity": capacity})
    return 0


def _quarantine_path(args) -> Path:
    return Path(args.store).with_suffix("").with_name(
        Path(args.store).stem + ".ai_quarantine.json"
    )


def cmd_propose_ai_facts(args) -> int:
    """Feed an assistant's FINAL text (never a thinking block) into
    quarantine — nothing here is queryable until accepted."""
    from .ai_ingest import AiFactQuarantine

    qpath = _quarantine_path(args)
    q = AiFactQuarantine.load(qpath)
    added = q.propose(args.text, source=args.source)
    q.save(qpath)
    _print({"proposed": [e.text for e in added], "quarantine": str(qpath)})
    return 0


def cmd_review_ai_facts(args) -> int:
    from .ai_ingest import AiFactQuarantine
    from .tui import select

    qpath = _quarantine_path(args)
    q = AiFactQuarantine.load(qpath)
    pending = q.pending()
    if not pending:
        print("no pending AI-proposed facts")
        return 0

    if args.list:
        _print([e.as_dict() for e in pending])
        return 0

    st = _load(args.store)
    store_path = Path(args.store)
    for entry in list(pending):  # snapshot: entries resolve as we go
        choice = select(
            f"[{entry.source}] {entry.text}",
            ["Accept → remember in trusted store", "Reject", "Skip (decide later)"],
            default=0,
        )
        if choice == 0:
            key = q.accept(entry, st)
            st.save(store_path)
            print(f"  accepted → core={key}")
        elif choice == 1:
            q.reject(entry)
            print("  rejected")
        else:
            break
    q.save(qpath)
    return 0


def cmd_chat(args) -> int:
    from .config import VeraConfig
    from .router import route as harness_route

    cfg = VeraConfig.load()
    st = _load(args.store, base_repo=cfg.hf_store_repo)
    store_path = Path(args.store)

    llm_fn = None
    if args.mode == "hybrid":
        from .llm_local import ollama_available, ollama_generate

        if ollama_available():
            model = args.llm if args.llm != "llama3.2" else (cfg.llm_model or args.llm)

            def llm_fn(prompt, system):  # noqa: E731 — closure over model
                return ollama_generate(model, prompt, system=system)

            print(f"[hybrid] local model '{model}' under Vera control "
                  "(vera / llm_guided / llm_free / refused)")
        else:
            print("[hybrid] Ollama not reachable at localhost:11434 — "
                  "falling back to lab mode (deterministic only)")

    from .tui import read_input

    auto_mem = not args.no_auto_memory
    print("Verantyx Vera α — "
          f"mode={args.mode}, lang={args.lang}, auto-memory={'on' if auto_mem else 'off'}. "
          "Commands: :remember <text>, :forget <core>, :stats, :quit "
          "(multi-line paste is captured as one message)")
    while True:
        raw = read_input("you> ")
        if raw is None:
            print()
            break
        line = raw.strip()
        if not line:
            continue
        if line in (":quit", ":q", "exit"):
            break
        if line.startswith(":remember "):
            from .lang import ingest_text

            rep = ingest_text(st, line[len(":remember "):], lang=args.lang)
            st.save(store_path)
            print(f"vera> remembered {rep['cores']} [{rep['lang']}]")
            continue
        if line.startswith(":forget "):
            core = line[len(":forget "):].strip()
            n = 0
            for key in (core, core + "#p"):
                if key in st.crosses:
                    del st.crosses[key]
                    st.core_count.pop(key, None)
                    n += 1
            st.save(store_path)
            print(f"vera> forgot {n} cross(es)")
            continue
        if line == ":stats":
            print(f"vera> {st.report()}")
            continue

        out = harness_route(
            st, line,
            llm=llm_fn,
            lang=args.lang,
            auto_memory=auto_mem,
            save=lambda: st.save(store_path),
            allocation=cfg.allocation,
        )
        mem = out.get("remembered")
        if mem and mem.get("cores"):
            print(f"      (remembered: {mem['cores']} [{mem['lang']}])")
        src = out.get("source", "vera")
        if src in ("llm_guided", "llm_free"):
            tag = "llm←vera-facts" if src == "llm_guided" else "llm UNVERIFIED"
            print(f"vera> {out.get('surface','')}   [{tag}]")
        elif out.get("verdict") == "ANSWER":
            body = (
                out.get("text")
                or out.get("value")
                or out.get("x")
                or out.get("callers")
                or out.get("calls")
                or out.get("impacted")
            )
            print(f"vera> {body}   [{out.get('route','?')}]")
        else:
            print(f"vera> {out.get('verdict')}   [{out.get('route','?')}] "
                  "(I do not know — no guessing)")
    return 0


def cmd_math(args) -> int:
    _print(math_ask(args.query))
    return 0


def cmd_simplify(args) -> int:
    _print(simplify(args.expr, default_algebra_rules()))
    return 0


def cmd_code(args) -> int:
    st = _load(args.store)
    if args.action == "ingest":
        rep = ingest_python_repo(st, Path(args.target))
        st.save(Path(args.store))
        _print({**rep, "store": args.store})
        return 0
    _print(code_ask(st, args.target))
    return 0


def cmd_lab(args) -> int:
    from .consensus_forks import all_consensus_forks
    from .cross_geometry_forks import all_cross_geometry_forks
    from .structure_forks import all_structure_forks
    from .kripke_rewrite_forks import all_kripke_rewrite_forks
    from .lean_witness_forks import all_lean_witness_forks
    from .agent_forks import all_agent_forks
    from .ai_ingest_forks import all_ai_ingest_forks
    from .obfuscate_forks import all_obfuscate_forks
    from .watermark_forks import all_watermark_forks
    from .lang_router_forks import all_lang_router_forks
    from .math_sim_forks import all_math_sim_forks
    from .phase2_forks import all_phase2_forks
    from .pour_forks import all_pour_forks

    experiments = (
        all_consensus_forks()
        + all_cross_geometry_forks()
        + all_structure_forks()
        + all_pour_forks()
        + all_math_sim_forks()
        + all_kripke_rewrite_forks()
        + all_lean_witness_forks()
        + all_lang_router_forks()
        + all_phase2_forks()
        + all_agent_forks()
        + all_ai_ingest_forks()
        + all_obfuscate_forks()
        + all_watermark_forks()
    )
    # A fork that could not run is reported by name and kept OUT of the pass
    # count, never folded into it. Optional extras are the usual reason (a
    # fork needing `cryptography` on an install without it); counting an
    # unrun check as a pass would make the suite quietly weaker on exactly
    # the installs where it is least verified.
    skipped = {e["fork"]: e["skipped"] for e in experiments if e.get("skipped")}
    forks = {e["fork"]: e["pass"] for e in experiments if not e.get("skipped")}
    all_pass = all(forks.values())
    _print({"all_pass": all_pass, "n_forks": len(forks),
            "n_skipped": len(skipped), "skipped": skipped, "forks": forks})
    return 0 if all_pass else 1


def cmd_mcp(args) -> int:
    from .mcp_server import serve

    return serve(args.store)


def cmd_field(args) -> int:
    """The whole thing on one screen, for somebody with a phone ringing.

    Separate from `vera audit` because the audience is: audit is for a person
    checking whether the ENGINE is right; this is for a person trying to find
    out whether the water is back on in their town.
    """
    from .field_app import serve

    return serve(port=args.port, open_browser=not args.no_browser)


def cmd_lexicon(args) -> int:
    """The dictionary half of a local model: state-likeness and neighbours.

    Never polarity — measured at 54.8%, a coin flip, and absent from the API.
    """
    import json as _json
    from pathlib import Path as _Path

    from .ja_grammar import ASPECT_OF
    from .jgen_lexicon import open_configured

    home = _Path.home() / ".verantyx-audit"
    lex = open_configured(home)
    if lex is None:
        print(_json.dumps({
            "verdict": "UNKNOWN_NO_LEXICON",
            "how": f"write {home / 'lexicon.json'} with "
                   '{"jgen": "...", "tokenizer": "..."} — build one with '
                   "jgen_forge pull <model> --parts lexicon",
        }, ensure_ascii=False, indent=2))
        return 1
    known = sorted(ASPECT_OF)
    out = []
    for w in args.words:
        out.append({
            "word": w,
            "state_likeness": lex.state_likeness(w, known),
            "nearest_known": lex.nearest(w, known, k=5),
        })
    print(_json.dumps({"verdict": "ANSWER", "words": out,
                       "not_in_this_dictionary": "polarity — measured 54.8%"},
                      ensure_ascii=False, indent=2))
    return 0


def cmd_self_evolve(args) -> int:
    """Read, prove, repair, measure, keep — with nothing outside the machine.

    The acceptance is mechanical only where the answer key is internal: a
    transform that cannot change what a document says, changing what the
    engine reads out of it. Everything else is filed for a person.
    """
    import json as _json
    from pathlib import Path as _Path

    from .self_evolve import run

    home = _Path.home() / ".verantyx-audit"
    overlay = _Path(args.overlay) if args.overlay else home / "grammar.json"
    out = run(list(args.paths), home=home, overlay=overlay, write=args.write)
    print(_json.dumps({"verdict": "ANSWER", **out}, ensure_ascii=False,
                      indent=2))
    return 0


def cmd_placement(args) -> int:
    """Decide which facts occupy an arm's four faces — once, before shipping.

    A build-time stage, not a query-time one: it computes the anticipated
    answer distribution, bakes a placement into a copy of the store, and the
    engine that reads it stays as deterministic as it was. Refuses to write
    unless the placement is measured better on held-out questions.
    """
    from .placement import main as _placement_main

    argv = [args.store, "--n-queries", str(args.n_queries),
            "--demand", args.demand, "--weight", str(args.weight)]
    if args.queries:
        argv += ["--queries", args.queries]
    if args.sweep:
        argv += ["--sweep"]
    if args.write:
        argv += ["--write", args.write]
    return _placement_main(argv)


def cmd_sovereign(args) -> int:
    """Documents in, one sovereign node out — every stage, in order.

    ingest -> simulate placement -> plan the depth capacity requires ->
    assemble routers -> federate -> descend real questions. Refuses to skip
    a stage; a tree assembled without the placement simulation routes on
    whichever four facts sorted first.
    """
    from .sovereign import main as _sovereign_main

    argv: list = []
    for d in args.domain:
        argv += ["--domain", d]
    for q in args.ask or []:
        argv += ["--ask", q]
    if args.questions:
        argv += ["--questions", args.questions]
    argv += ["--n-queries", str(args.n_queries), "--name", args.name]
    if args.out:
        argv += ["--out", args.out]
    return _sovereign_main(argv)


def cmd_self_audit(args) -> int:
    """Signals a defect leaves in the store, without anybody reading output.

    This is the end of the loop that still needed a person. It does NOT mark
    anything wrong — a suspected gap is a place to look, never a verdict, and
    it never reaches rule synthesis on its own.
    """
    import json as _json
    from pathlib import Path as _Path

    from .arm_schema import ArmIndex
    from .catalog import collect as _collect
    from .cross_store import CrossStore
    from .document_ingest import ingest_documents
    from .document_loaders import load_paths
    from .self_audit import scan, summary, to_gaps

    docs = load_paths(_collect(list(args.paths))["files"])["documents"]
    if not docs:
        print(_json.dumps({"verdict": "UNKNOWN_NO_DOCUMENTS"},
                          ensure_ascii=False))
        return 1
    store, arms = CrossStore(track_provenance=True), ArmIndex()
    ingest_documents(store, docs, arms)
    found = scan(store, arms)

    out = {"verdict": "ANSWER", "documents": len(docs), **summary(found),
           "signals": [s.as_dict() for s in found]}
    if args.file_gaps:
        from .gap_graph import GapGraph, gap_graph_path

        home = _Path.home() / ".verantyx-audit"
        home.mkdir(parents=True, exist_ok=True)
        path = gap_graph_path(home / "audit.json")
        graph = GapGraph.load(path)
        out["filed"] = to_gaps(graph, found)
        graph.save(path)
    print(_json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_audit(args) -> int:
    """A local page for auditing documents — the tool that lets somebody
    other than the author of the fixes read the output. Binds to 127.0.0.1
    only: the documents may be unpublished drafts."""
    from .audit_app import serve as serve_audit

    return serve_audit(port=args.port, open_browser=not args.no_open)


def cmd_serve(args) -> int:
    """Milestone N: HTTP+SSE daemon — Vera as the harness, the IDE (or any
    local caller) as a subscriber/tool-provider instead of an MCP client
    driving Vera as a flat tool. See vera_server.py's own docstring."""
    from .config import VeraConfig
    from .vera_server import serve as serve_http

    st = _load(args.store)
    store_path = Path(args.store)
    cfg = VeraConfig.load()
    model = args.llm or cfg.llm_model

    def save() -> None:
        st.save(store_path)

    return serve_http(st, save, port=args.port, default_model=model,
                       jgen_endpoint=args.jgen_endpoint, store_path=store_path)


def cmd_setup(args) -> int:
    from .config import run_setup_menu

    cfg = run_setup_menu()
    _print({"llm_model": cfg.llm_model, "store": cfg.store,
            "allocation": cfg.allocation, "hf_store_repo": cfg.hf_store_repo})
    return 0


def cmd_wizard(args) -> int:
    """Guided data-placement: choose a source with arrow keys and pour."""
    from .tui import select

    presets = [
        ("hf:dbpedia_14:content", "DBpedia abstracts — best definitional pour"),
        ("hf:ag_news", "AG News headlines — current events"),
        ("wikitext", "WikiText-2 from local HF cache"),
        ("hf:wikitext#wikitext-103-raw-v1", "WikiText-103 — large"),
        ("synthetic", "tiny offline synthetic corpus (smoke test)"),
        ("file:", "a local text file (one document per line)"),
    ]
    i = select(
        "Choose a data source to pour into the store:",
        [p[0] for p in presets],
        descriptions=[p[1] for p in presets],
    )
    if i is None:
        print("cancelled")
        return 1
    source = presets[i][0]
    if source == "file:":
        source = "file:" + input("path to text file: ").strip()
    caps = ["2000", "40000", "120000", "560000", "all (2000000)"]
    j = select("Row budget:", caps, default=1)
    max_rows = {0: 2000, 1: 40000, 2: 120000, 3: 560000, 4: 2000000}[j or 1]
    print(f"pouring {source} (max_rows={max_rows}) → {args.store}")
    ns = argparse.Namespace(
        store=args.store, source=source, max_rows=max_rows,
        max_sentences=None, checkpoint_every=100000, no_two_pass=False,
    )
    return cmd_pour(ns)


def cmd_agent(args) -> int:
    from .agent import Agent
    from .config import VeraConfig
    from .tui import confirm_action

    cfg = VeraConfig.load()
    st = _load(args.store, base_repo=cfg.hf_store_repo)
    store_path = Path(args.store)

    llm_fn = None
    model = args.llm or cfg.llm_model
    if model:
        from .llm_local import ollama_available, ollama_generate

        if ollama_available():
            def llm_fn(prompt, system):  # noqa: E731
                return ollama_generate(model, prompt, system=system, timeout=180)
            print(f"[agent] planner LLM: {model}")
        else:
            print("[agent] Ollama unreachable — solo mode (manual !tool calls)")

    def approver(tool, tool_args):
        return confirm_action(
            f"{tool.name}({tool.args_hint})",
            detail=json.dumps(tool_args, ensure_ascii=False, indent=2),
        )

    agent = Agent(
        st, llm=llm_fn, save=lambda: st.save(store_path),
        approver=approver, allocation=cfg.allocation,
        auto_approve=args.yes,
    )

    if args.task:
        out = agent.run(args.task)
        _print(out.get("final", out))
        return 0

    from .tui import read_input

    print("Verantyx agent mode. Type a task, or '!tool {\"arg\":..}' for a "
          "manual tool call, ':quit' to exit. "
          "(multi-line paste is captured as one task)")
    while True:
        raw = read_input("task> ")
        if raw is None:
            print()
            break
        line = raw.strip()
        if not line or line in (":quit", ":q"):
            break
        if line.startswith("!"):
            out = agent.step_solo(line)
            _print(out)
            continue
        out = agent.run(line)
        final = out.get("final", out)
        print(f"agent> {final if isinstance(final, str) else json.dumps(final, ensure_ascii=False)[:600]}")
    return 0


def cmd_obfuscate(args) -> int:
    from .obfuscate import export_recovery_key, key_from_store, obfuscate_file

    st = _load(args.store)
    rep = obfuscate_file(Path(args.file), st)
    if args.export_key and rep.get("ok"):
        export_recovery_key(key_from_store(st), Path(args.export_key))
        rep["recovery_key"] = args.export_key
    _print(rep)
    return 0 if rep.get("ok") else 1


def cmd_deobfuscate(args) -> int:
    from .obfuscate import deobfuscate_file, load_recovery_key

    key = load_recovery_key(Path(args.key_file)) if args.key_file else None
    st = None if key is not None else _load(args.store)
    rep = deobfuscate_file(
        Path(args.obf_file), Path(args.map_file), store=st, key=key
    )
    _print(rep)
    return 0 if rep.get("ok") else 1


def cmd_watermark(args) -> int:
    from .watermark import identify_candidates, register_owner

    if args.action == "register":
        st = _load(args.store)
        rep = register_owner(Path(args.registry), args.owner_id, st)
    else:  # identify
        source = Path(args.file).read_text()
        rep = identify_candidates(Path(args.registry), source)
    _print(rep)
    return 0 if rep.get("ok") else 1


def cmd_push_store(args) -> int:
    from .config import VeraConfig
    from .hf_store import upload_store

    repo = args.repo or VeraConfig.load().hf_store_repo
    if not repo:
        print("no repo given; pass --repo user/name or set hf_store_repo in setup")
        return 2
    _print(upload_store(args.store, repo, private=args.private))
    return 0


def cmd_guard(args) -> int:
    """番人の高速経路 — 連邦を読まず covenants.json だけを読む。

    実地試験の限界5: 橋(常駐)の起動 15〜45秒の間 fail-open だった。
    この経路は Register だけを読むので、凍結バイナリでも秒台で返り、
    フックは橋なしで直接呼べる(fail-open の窓が消える)。
    """
    import sys as _sys

    from .covenant import (Covenant, Register, bake_inferred,
                           extract_covenants, extract_releases, self_check)

    store_path = Path(args.store or DEFAULT_STORE)
    cov_path = store_path.with_name(store_path.stem + ".covenants.json")
    reg = Register.load(cov_path)
    op = args.guard_op
    payload = {}
    if not _sys.stdin.isatty():
        raw = _sys.stdin.read().strip()
        if raw:
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"text": raw}
    def _mk_covenant():
        return Covenant(
            name=str(payload.get("name", ""))[:60] or "covenant",
            requires=list(payload.get("requires", [])),
            forbids=list(payload.get("forbids", [])),
            topic=list(payload.get("topic", [])),
            said_at_turn=int(payload.get("turn", -1)),
            quote=str(payload.get("quote", "")),
            origin=str(payload.get("origin", "")))

    def _bake(c):
        # ③ 書かれていない禁止 — 登録・採用の時だけ店を読む(check の
        # 速い道を守る)。店が無ければ何も焼かない(推測しない)。
        if not payload.get("infer"):
            return None
        if not store_path.is_file():
            return {"verdict": "UNKNOWN_NO_STORE", "path": str(store_path)}
        return bake_inferred(c, CrossStore.load(store_path),
                             store_name=store_path.name,
                             store_path=store_path)

    if op == "extract":
        _text = str(payload.get("text", ""))
        out = {"candidates": extract_covenants(
            _text, turn=int(payload.get("turn", -1))),
            "releases": extract_releases(_text)}
    elif op == "set":
        c = _mk_covenant()
        if c.origin == "regex":
            # 戻り止め(2026-08-21、誤遮断の実測)。閉じた抽出規則が読んだ
            # 約束は、どの入口から入っても執行には入れない — `No new
            # dependencies` → forbids=["new"] が返答を遮断した実測があり、
            # 規則を足して被覆を上げる道は閉じないと分かっている。
            # フックは propose を呼ぶが、別の配管が set を呼んでも法が
            # 破れないよう、ここでも隔離席へ落とす。**黙って落とさない**:
            # 隔離席に入れたことを返り値で名指す。
            reg.propose(c)
            reg.save(cov_path)
            out = {"verdict": "ANSWER", "candidate": c.as_dict(),
                   "routed_to_quarantine": True,
                   "note": "規則が読んだ約束は執行に入れない — shadow で"
                           "照合されるだけ。採用は adopt(門)"}
        else:
            reg.add(c)
            baked = _bake(c)
            reg.save(cov_path)
            out = {"verdict": "ANSWER", "covenant": c.as_dict(),
                   "in_force": len([x for x in reg.covenants
                                    if not x.retired
                                    and x.status == "adopted"])}
            if baked:
                out["inference"] = baked
    elif op == "propose":
        # ① 隔離席 — LLM の候補は shadow で照合されるだけで執行されない。
        c = _mk_covenant()
        if not (c.forbids or c.requires):
            out = {"verdict": "UNKNOWN_EMPTY_CANDIDATE",
                   "note": "禁止も要求も無い候補は約束にならない"}
        else:
            reg.propose(c)
            reg.save(cov_path)
            out = {"verdict": "ANSWER", "candidate": c.as_dict()}
    elif op == "adopt":
        d = reg.adopt(str(payload.get("name", "")))
        if d is None:
            out = {"verdict": "UNKNOWN_NO_SUCH_CANDIDATE"}
        else:
            c = next(x for x in reg.covenants if x.name == d["name"])
            baked = _bake(c)
            reg.save(cov_path)
            out = {"verdict": "ANSWER", "adopted": c.as_dict()}
            if baked:
                out["inference"] = baked
    elif op == "witness":
        _ok = payload.get("ok", None)
        out = reg.witness(str(payload.get("tool", "")),
                          detail=str(payload.get("detail", "")),
                          turn=int(payload.get("turn", -1)),
                          ok=None if _ok is None else bool(_ok))
        reg.save(cov_path)
    elif op == "prune":
        # 台帳を有界に。**消さず書庫へ移す**(PREREG9)。
        out = reg.prune(path=cov_path,
                        max_history=int(payload.get("max_history", 200)),
                        max_live=int(payload.get("max_live", 300)))
        reg.save(cov_path)
    elif op == "promote":
        # 推薦だけ — 採用は adopt(門)のまま。保存も要らない。
        out = reg.promotion_review(
            min_checks=int(payload.get("min_checks", 8)),
            max_fire_rate=float(payload.get("max_fire_rate", 0.5)))
    elif op == "doctor":
        # 導入直後に叩く自己検査(PREREG5)。**利用者の台帳には触らない** —
        # 一時の台帳で保証を実演し、環境は stat と実時間だけを見る。
        import os as _os
        import time as _time

        out = self_check()
        t0 = _time.time()
        _probe = Register()
        _probe.add(Covenant(name="_speed", quote="q", forbids=["絵文字"]))
        for _ in range(200):
            _probe.check("できました。")
        per_check_ms = round((_time.time() - t0) / 200 * 1000, 4)
        frozen = bool(getattr(_sys, "frozen", False))
        env = {
            "path": "frozen-binary" if frozen else "source",
            "per_check_ms": per_check_ms,
            "covenants_ledger": str(cov_path),
            "ledger_exists": cov_path.is_file(),
            "ledger_writable": _os.access(
                cov_path if cov_path.is_file() else cov_path.parent,
                _os.W_OK),
            "covenants_in_force": len([c for c in reg.covenants
                                       if not c.retired
                                       and c.status == "adopted"]),
            "candidates_in_quarantine": len([c for c in reg.covenants
                                             if c.status == "candidate"]),
        }
        notes = []
        if not env["ledger_writable"]:
            notes.append("台帳に書けない — 約束を登録できない(DEGRADED)")
        if frozen and per_check_ms > 50:
            notes.append("1照合が遅い — onedir 凍結かソース直呼びを勧める")
        out["environment"] = env
        if out["verdict"] == "OK" and notes:
            out["verdict"] = "DEGRADED"
        out["notes"] = notes
    elif op == "stale":
        out = reg.stale(store_path)      # stat のみ — 店は読まない
    elif op == "rebake":
        dry = bool(payload.get("dry_run", False))
        if not store_path.is_file():
            out = {"verdict": "UNKNOWN_NO_STORE", "path": str(store_path)}
        else:
            out = reg.rebake(CrossStore.load(store_path),
                             store_path=store_path, dry_run=dry)
            if not dry and out.get("verdict") == "ANSWER":
                reg.save(cov_path)
    elif op == "boundary":
        out = reg.boundary(turn=int(payload.get("turn", -1)))
        reg.save(cov_path)
    elif op == "audit":
        out = reg.audit()
    elif op == "check":
        out = reg.check(str(payload.get("reply", "")),
                        asked=str(payload.get("asked", "")))
        reg.save(cov_path)          # 履歴(風化の材料)を残す
    elif op == "fading":
        out = reg.fading(window=int(payload.get("window", 5)))
    elif op == "retire":
        r = reg.retire(str(payload.get("name", "")),
                       quote=str(payload.get("quote", "")),
                       turn=int(payload.get("turn", -1)))
        if r is None:
            out = {"verdict": "UNKNOWN_NO_SUCH_COVENANT"}
        else:
            reg.save(cov_path)
            out = {"verdict": "ANSWER", "retired": r}
    elif op == "list":
        out = {"covenants": [c.as_dict() for c in reg.covenants]}
    else:
        out = {"verdict": "UNKNOWN_OP", "op": op}
    _print(out)
    # doctor だけは終了コードで答える — 導入の自動確認に使えるように。
    if op == "doctor" and out.get("verdict") == "BROKEN":
        return 1
    return 0


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="vera", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", default=None,
                    help="store path (default: config, else vera_store.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pour", help="stream a corpus into the store")
    p.add_argument("--source", default="synthetic")
    p.add_argument("--max-rows", type=int, default=20000)
    p.add_argument("--max-sentences", type=int, default=None)
    p.add_argument("--checkpoint-every", type=int, default=100000)
    p.add_argument("--no-two-pass", action="store_true")
    p.set_defaults(fn=cmd_pour)

    p = sub.add_parser("remember", help="teach one sentence")
    p.add_argument("text")
    p.set_defaults(fn=cmd_remember)

    p = sub.add_parser("forget", help="delete a core (really deletes)")
    p.add_argument("core")
    p.set_defaults(fn=cmd_forget)

    p = sub.add_parser("ask", help="one-shot question (typed verdict)")
    p.add_argument("query")
    p.set_defaults(fn=cmd_ask)

    p = sub.add_parser(
        "index",
        help="does this already exist? one search over doors, commands, "
             "modules, forks and every prereg/result — derived, never listed")
    p.add_argument("index_op", choices=["search", "build", "markdown"])
    p.add_argument("query", nargs="*", default=[])
    p.add_argument("--limit", type=int, default=12)
    p.add_argument("--out", default="")
    p.set_defaults(fn=cmd_index)

    p = sub.add_parser(
        "mcp-config",
        help="print (or install) the MCP snippet pointing a client at this "
             "binary and this store")
    p.add_argument("--client", default="claude-code",
                   choices=list(_MCP_CLIENTS) + ["all"])
    p.add_argument("--install", action="store_true",
                   help="write it into the client config (merges, replacing "
                        "only the vera-memory entry)")
    p.set_defaults(fn=cmd_mcp_config)

    p = sub.add_parser(
        "tool", help="call any of the MCP doors from the CLI (same doors, "
                     "second entrance — nothing is rewritten per command)")
    p.add_argument("tool_op", choices=["list", "show", "call"])
    p.add_argument("name", nargs="?", default="")
    p.add_argument("--json", default="", help="arguments as a JSON object")
    p.add_argument("--arg", action="append",
                   help="key=value (repeatable), typed from the door")
    p.set_defaults(fn=cmd_tool)

    p = sub.add_parser(
        "documents",
        help="load documents into the store from the CLI — PDF, Word, "
             "HTML, CSV, JSON, text; a directory is walked")
    p.add_argument("paths", nargs="+")
    p.add_argument("--no-ingest", action="store_true",
                   help="read and register the documents without ingesting")
    p.set_defaults(fn=cmd_documents)

    p = sub.add_parser("domain", help="register/inspect domain vocabularies")
    p.add_argument("domain_op",
                   choices=["list", "add", "pending", "accept", "reject"])
    p.add_argument("name", nargs="?", default="")
    p.add_argument("path", nargs="?", default="")
    p.add_argument("--index", type=int, default=None)
    p.set_defaults(fn=cmd_domain)

    p = sub.add_parser(
        "doctor",
        help="self-check both faces on THIS machine: the covenant guard "
             "(G1-G4) and the standalone device (S1-S4). Exit 1 if broken")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("stats", help="store statistics")
    p.set_defaults(fn=cmd_stats)

    p = sub.add_parser(
        "guard",
        help="covenant guard fast path: no federation load, covenants.json "
             "only — for Claude Code hooks (stdin: JSON payload)")
    p.add_argument("guard_op",
                   choices=["extract", "set", "check", "fading", "retire", "list",
                            "propose", "adopt", "witness", "boundary", "audit",
                            "promote", "stale", "rebake",
                            "doctor", "prune"])
    p.set_defaults(fn=cmd_guard)

    p = sub.add_parser(
        "heartbeat",
        help="Milestone M: scan growth signals, draft+verify candidate "
             "domain modules, queue for human review (never auto-activates)",
    )
    p.add_argument("--llm-model", default="", dest="llm_model",
                    help="Ollama model to draft with; omit to only report candidates")
    p.set_defaults(fn=cmd_heartbeat)

    p = sub.add_parser(
        "propose-ai-facts",
        help="quarantine sentence candidates from an AI's FINAL text "
             "(never thinking/chain-of-thought)",
    )
    p.add_argument("text")
    p.add_argument("--source", default="ai_output")
    p.set_defaults(fn=cmd_propose_ai_facts)

    p = sub.add_parser(
        "review-ai-facts",
        help="review quarantined AI-proposed facts (arrow-key accept/reject)",
    )
    p.add_argument("--list", action="store_true", help="print pending, no prompts")
    p.set_defaults(fn=cmd_review_ai_facts)

    p = sub.add_parser("chat", help="interactive REPL (lab | hybrid)")
    p.add_argument("--mode", choices=["lab", "hybrid"], default="lab",
                   help="lab: deterministic only; hybrid: local LLM under Vera control")
    p.add_argument("--llm", default="llama3.2",
                   help="Ollama model name for hybrid mode")
    p.add_argument("--lang", default="auto",
                   help="auto | en | ja | es | fr | de | latin")
    p.add_argument("--no-auto-memory", action="store_true",
                   help="disable the native always-on memory harness")
    p.set_defaults(fn=cmd_chat)

    p = sub.add_parser("math", help="wire arithmetic / typed equations")
    p.add_argument("query")
    p.set_defaults(fn=cmd_math)

    p = sub.add_parser("simplify", help="term rewriting (algebra rules)")
    p.add_argument("expr")
    p.set_defaults(fn=cmd_simplify)

    p = sub.add_parser("code", help="code reasoning: ingest / ask")
    p.add_argument("action", choices=["ingest", "ask"])
    p.add_argument("target")
    p.set_defaults(fn=cmd_code)

    p = sub.add_parser("lab", help="run fork self-test suites")
    p.set_defaults(fn=cmd_lab)

    p = sub.add_parser("mcp", help="start MCP server (stdio)")
    p.set_defaults(fn=cmd_mcp)

    p = sub.add_parser(
        "field",
        help="the full local app for a municipal desk (127.0.0.1, no network)")
    p.add_argument("--port", type=int, default=8900)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(fn=cmd_field)

    p = sub.add_parser(
        "lexicon",
        help="ask the configured static dictionary about a word")
    p.add_argument("words", nargs="+")
    p.set_defaults(fn=cmd_lexicon)

    p = sub.add_parser(
        "self-evolve",
        help="prove defects from the documents themselves, repair, and keep")
    p.add_argument("paths", nargs="+")
    p.add_argument("--write", action="store_true",
                   help="write an accepted repair to the overlay")
    p.add_argument("--overlay", default=None,
                   help="default ~/.verantyx-audit/grammar.json")
    p.set_defaults(fn=cmd_self_evolve)

    p = sub.add_parser(
        "placement",
        help="simulate which facts go on the faces, before shipping a store")
    p.add_argument("store")
    p.add_argument("--queries",
                   help="one anticipated question per line; strongly "
                        "preferred over the synthetic stand-in")
    p.add_argument("--n-queries", type=int, default=120)
    p.add_argument("--demand", choices=("zipf", "uniform"), default="zipf",
                   help="how synthetic questions pick a facet; zipf models "
                        "concentrated stable demand, uniform models none")
    p.add_argument("--weight", type=float, default=0.0,
                   help="discrimination weight; measured as unhelpful at "
                        "one arm per query, see verantyx/placement.py")
    p.add_argument("--sweep", action="store_true",
                   help="measure the weight instead of using it")
    p.add_argument("--write", metavar="OUT",
                   help="bake the placement into a copy of the store")
    p.set_defaults(fn=cmd_placement)

    p = sub.add_parser(
        "sovereign",
        help="build one federated node from documents, stage by stage")
    p.add_argument("--domain", action="append", metavar="NAME=PATH", required=True,
                   help="a field and the folder its documents live in")
    p.add_argument("--ask", action="append", default=[],
                   help="a question to descend after the build")
    p.add_argument("--questions", help="a file of questions, one per line")
    p.add_argument("--n-queries", type=int, default=200)
    p.add_argument("--name", default="主権")
    p.add_argument("--out", help="write the build record as JSON")
    p.set_defaults(fn=cmd_sovereign)

    p = sub.add_parser(
        "self-audit",
        help="find structural signals of defects, with no person reading")
    p.add_argument("paths", nargs="+")
    p.add_argument("--file-gaps", action="store_true",
                   help="record what it finds in the local gap graph")
    p.set_defaults(fn=cmd_self_audit)

    p = sub.add_parser(
        "audit",
        help="drop documents in a browser and read what the engine did")
    p.add_argument("--port", type=int, default=8899)
    p.add_argument("--no-open", action="store_true",
                   help="do not launch a browser")
    p.set_defaults(fn=cmd_audit)

    p = sub.add_parser(
        "serve",
        help="Milestone N: HTTP+SSE daemon (Vera as harness, not an MCP tool) "
             "— POST /agent/run, GET /events?run_id=, GET /agent/run/<id>",
    )
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--llm", default=None, help="Ollama model; falls back to config's llm_model")
    p.add_argument("--jgen-endpoint", default=None, dest="jgen_endpoint",
                    help="e.g. http://127.0.0.1:8766 — the IDE's JGenAgentServer (N4), "
                         "only needed if a request sets \"backend\": \"jgen\"")
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("setup", help="interactive settings (LLM, allocation)")
    p.set_defaults(fn=cmd_setup)

    p = sub.add_parser("wizard", help="guided data-placement (arrow keys)")
    p.set_defaults(fn=cmd_wizard)

    p = sub.add_parser("agent", help="agent mode: tools + ReAct + approvals")
    p.add_argument("task", nargs="?", default=None)
    p.add_argument("--llm", default=None)
    p.add_argument("--yes", action="store_true", help="auto-approve (careful)")
    p.set_defaults(fn=cmd_agent)

    p = sub.add_parser(
        "obfuscate",
        help="reversible identifier obfuscation, mapping encrypted with a "
             "key derived from your store's personal state",
    )
    p.add_argument("file")
    p.add_argument("--export-key", default=None,
                   help="also export a portable recovery key to this path")
    p.set_defaults(fn=cmd_obfuscate)

    p = sub.add_parser("deobfuscate", help="restore original names")
    p.add_argument("obf_file")
    p.add_argument("map_file")
    p.add_argument("--key-file", default=None,
                   help="use an exported recovery key instead of --store")
    p.set_defaults(fn=cmd_deobfuscate)

    p = sub.add_parser(
        "watermark",
        help="leak attribution: register an owner's naming-variant, or "
             "identify candidate owners of an obfuscated file (evidence, "
             "not proof — see docs/WATERMARK.md)",
    )
    p.add_argument("action", choices=["register", "identify"])
    p.add_argument("registry", help="path to the watermark registry JSON file")
    p.add_argument("--owner-id", default=None, help="required for register")
    p.add_argument("--file", default=None, help="obfuscated .obf file, required for identify")
    p.set_defaults(fn=cmd_watermark)

    p = sub.add_parser("push-store", help="upload the store to HuggingFace")
    p.add_argument("--repo", default=None)
    p.add_argument("--private", action="store_true")
    p.set_defaults(fn=cmd_push_store)

    args = ap.parse_args(argv)
    # resolve store: --store > config > default
    if getattr(args, "store", None) is None:
        from .config import VeraConfig

        args.store = VeraConfig.load().store or DEFAULT_STORE
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
