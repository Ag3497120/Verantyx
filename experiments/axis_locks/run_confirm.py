# -*- coding: utf-8 -*-
"""確認測定 — PREREG.md が事前登録。軸のロック。"""
import json, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verantyx.consensus import settled_axes
from verantyx.consensus_store import ja_consensus_ask
from verantyx.cross_store import CrossStore
from verantyx.export_sqlite import vera as load_published

DB = Path.home() / "Projects" / "vera-corpus" / "build" / "vera.db"
N = 300


def mid_facets(store, core, n=3, seed=0):
    cross = store.crosses.get(core) or {}
    fs = sorted((f for f, c in cross.items() if f.isalpha() or
                 all("぀" <= ch or ch.isalnum() for ch in f)),
                key=lambda f: (-cross[f], f))
    if len(fs) < n:
        return None
    mid = fs[len(fs) // 4: len(fs) // 4 + max(n * 3, n)]
    if len(mid) < n:
        mid = fs
    rng = random.Random(f"{seed}:{core}")
    return rng.sample(mid, n) if len(mid) >= n else None


def main():
    t0 = time.time()
    res = {}

    # S2: 同点だけの店ではロックが空 / counts が割れればロック可
    tied = CrossStore()
    for a in ("aspa", "aspb", "aspc", "aspd"):
        tied.ingest_sentence(f"gadget has {a}")
    from verantyx.consensus_store import consensus_over_store
    r_tied = consensus_over_store(tied, "what is gadget aspa",
                                  placement_invariant=True)
    w = CrossStore()
    for _ in range(5):
        w.ingest_sentence("gadget is heavy")
    for _ in range(4):
        w.ingest_sentence("gadget is fast")
    for _ in range(3):
        w.ingest_sentence("gadget is small")
    for _ in range(2):
        w.ingest_sentence("gadget is quiet")
    r_ranked = consensus_over_store(w, "what is gadget heavy",
                                    placement_invariant=True)
    res["S2"] = {"tied_locks": r_tied.get("locks"),
                 "ranked_locks": r_ranked.get("locks")}
    res["S2_ok"] = (r_tied.get("locks") == []
                    and bool(r_ranked.get("locks")))

    # S1/S4/S5: 実店で、ロック無し vs ロック継承(循環)で判定と手数を比較
    v = load_published(DB)
    store = v.stores["ja"]
    rich = sorted(c for c, f in store.crosses.items() if len(f) >= 8)
    picks = random.Random(42).sample(rich, min(N, len(rich)))

    def battery(use_circulation):
        circ = {} if use_circulation else None
        verdicts, moves, locks_seen = [], 0, 0
        for want in picks:
            t = mid_facets(store, want, seed=999)
            if not t:
                continue
            q = " ".join(t)
            out = ja_consensus_ask(store, q, placement_invariant=True)
            verdicts.append((want, out.get("verdict"), out.get("core_key")))
            moves += int(out.get("moves_used") or 0)
            if out.get("locks"):
                locks_seen += 1
            # 循環への書き戻しは consensus_over_store 側(en経路)なので、
            # ja経路では locks を明示的に運ぶ
            if circ is not None and out.get("locks") and out.get("core_key"):
                circ.setdefault(out["core_key"], {})["locks"] = out["locks"]
        return verdicts, moves, locks_seen, circ

    v_off, m_off, seen_off, _ = battery(False)
    v_on, m_on, seen_on, circ = battery(True)

    # 名前形の族でも測る — facet3語の族は大半が逆方向回答/拒否で、
    # ANSWER+配置不変がほぼ起きず、ロックは構造上発火しない。
    # 機構が発火しうる族(名前形は ANSWER 100/100)でも測って両方報告する。
    from verantyx.lex_filters import display_sym

    def name_battery(use_circulation):
        circ2 = {} if use_circulation else None
        verdicts, moves, seen = [], 0, 0
        for want in picks[:100]:
            q = display_sym(want) + "とは"
            out = ja_consensus_ask(store, q, placement_invariant=True)
            verdicts.append((want, out.get("verdict"), out.get("core_key")))
            moves += int(out.get("moves_used") or 0)
            if out.get("locks"):
                seen += 1
                if circ2 is not None and out.get("core_key"):
                    circ2.setdefault(out["core_key"], {})["locks"] = out["locks"]
        return verdicts, moves, seen, circ2

    nv_off, nm_off, nseen_off, _ = name_battery(False)
    nv_on, nm_on, nseen_on, ncirc = name_battery(True)
    res["name_form"] = {
        "n": len(nv_off), "queries_with_locks": nseen_off,
        "identical_verdicts": nv_off == nv_on,
        "moves_without": nm_off, "moves_with": nm_on,
        "cores_locked": len(ncirc or {})}
    same = v_off == v_on
    res["S1"] = {"facet_family_with_locks": seen_off,
                 "cores_locked_in_circulation": len(circ or {}),
                 "note": "facet3語の族は逆方向回答/拒否が大半で、"
                         "ANSWER+配置不変が構造上ほとんど起きない"}
    res["S1_ok"] = seen_off > 0 or res["name_form"]["queries_with_locks"] > 0
    res["S4"] = {"identical_verdicts": same,
                 "n": len(v_off),
                 "diff": [a for a, b in zip(v_off, v_on) if a != b][:5]}
    res["S4_ok"] = same and res["name_form"]["identical_verdicts"]
    res["S5"] = {"moves_without": m_off, "moves_with": m_on}
    res["all_pass"] = all([res["S1_ok"], res["S2_ok"], res["S4_ok"]])
    res["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    Path(__file__).with_name("results.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")


if __name__ == "__main__":
    main()
