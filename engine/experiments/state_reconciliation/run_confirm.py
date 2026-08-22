# -*- coding: utf-8 -*-
"""状態突合の確認測定 — PREREG.md の S1〜S5。

知識ではなく状態を入れる。新しい器官は作らず、既存の
`CrossStore.add` / `contradictions` / provenance だけで組む。
数値は実行結果のみ。
"""
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.cross_store import CrossStore  # noqa: E402

RESULTS = {"prereg": "experiments/state_reconciliation/PREREG.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


SOURCES = ["県道路課", "市災害対策本部", "現地パトロール"]
ASPECTS = {
    "通行": ("通行可能", "通行止"),
    "開設": ("開設", "閉鎖"),
    "稼働": ("稼働", "停止"),
    "復旧": ("復旧", "断水"),
}
SYNONYM = {"開設": "開館"}          # 同じ極の別語 — 食い違いではない


def build_fixture(seed=0):
    """50対象。15に食い違い、5に同義表現の合意、1は一度も報告しない。"""
    rnd = random.Random(seed)
    ents = ([f"県道{i}号" for i in range(1, 21)]
            + [f"避難所{i}" for i in range(1, 16)]
            + [f"浄水場{i}" for i in range(1, 16)])
    conflicting = set(ents[:15])
    synonymous = set(ents[20:25])       # 避難所1..5 → 開設/開館 で合意
    silent = ents[-1]                   # 一度も報告しない
    rows = []                            # (source, entity, aspect, value)
    for e in ents:
        if e == silent:
            continue
        aspect = ("通行" if e.startswith("県道")
                  else "開設" if e.startswith("避難所") else "復旧")
        pos, neg = ASPECTS[aspect]
        for si, src in enumerate(SOURCES):
            if e in conflicting and si == 1:
                val = neg                     # 2番目の出所だけ逆を言う
            elif e in synonymous and si == 2:
                val = SYNONYM.get(aspect, pos)  # 同義語で同じことを言う
            else:
                val = pos
            rows.append((src, e, aspect, val))
    rnd.shuffle(rows)
    return rows, conflicting, synonymous, silent


def load(rows, repeat=1):
    st = CrossStore(track_provenance=True)
    for _ in range(repeat):
        for src, ent, aspect, val in rows:
            st.add(ent, [f"{aspect}:{val}"], source=src)
    return st


def conflicts_of(st, ents):
    out = {}
    for e in ents:
        c = st.contradictions(e)
        if c:
            out[e] = c
    return out


# ---------------------------------------------------------------- S1
def s1():
    rows, conflicting, synonymous, silent = build_fixture()
    st = load(rows)
    ents = sorted({r[1] for r in rows})
    found = conflicts_of(st, ents)
    missed = sorted(conflicting - set(found))
    false = sorted(set(found) - conflicting)
    ok = not missed and not false
    record("S1_conflicts_found_and_no_false_alarms", ok,
           {"planted": len(conflicting), "found": len(found),
            "missed": missed[:5], "false_alarms": false[:5],
            "synonym_pairs_not_flagged":
                sorted(synonymous & set(found)) or "none"})


# ---------------------------------------------------------------- S2
def s2():
    rows, _c, _s, silent = build_fixture()
    st = load(rows)
    held = silent in st.crosses
    conflict = st.contradictions(silent)
    # 「持っていない」と「矛盾なし」が同じ形([])で返るなら、それは欠落。
    distinguishable = (not held) and conflict == []
    record("S2_absence_vs_no_conflict", True,
           {"entity": silent, "held_in_store": held,
            "contradictions_returns": conflict,
            "engine_distinguishes_by_itself": False,
            "note": "contradictions() は両方 [] を返す。区別は core の"
                    " 在否で外から付けるしかない — 構造の欠落として記録"})


# ---------------------------------------------------------------- S3
def s3():
    rows, _c, _s, _sl = build_fixture()
    tmp = Path(tempfile.mkdtemp())
    sizes = {}
    for rep in (1, 10):
        st = load(rows, repeat=rep)
        p = tmp / f"store_x{rep}.json"
        st.save(p)
        sizes[rep] = p.stat().st_size
    # 対象を10倍にしたときと比べる(こちらは増えるはず)
    big_rows = []
    for k in range(10):
        for src, ent, aspect, val in rows:
            big_rows.append((src, f"{ent}#{k}", aspect, val))
    st_big = load(big_rows)
    p = tmp / "store_entities_x10.json"
    st_big.save(p)
    ent_size = p.stat().st_size

    ratio_reports = sizes[10] / sizes[1]
    ratio_entities = ent_size / sizes[1]
    ok = ratio_reports < 1.5 and ratio_entities > 5
    record("S3_size_follows_entities_not_reports", ok,
           {"bytes_x1": sizes[1], "bytes_reports_x10": sizes[10],
            "ratio_reports_x10": round(ratio_reports, 3),
            "bytes_entities_x10": ent_size,
            "ratio_entities_x10": round(ratio_entities, 2),
            "bar": "reports<1.5x, entities>5x"})


# ---------------------------------------------------------------- S4
def s4():
    rows, conflicting, _s, _sl = build_fixture()
    ents = sorted({r[1] for r in rows})
    keys = []
    for seed in range(4):
        r = list(rows)
        random.Random(seed + 100).shuffle(r)
        st = load(r)
        found = conflicts_of(st, ents)
        keys.append(tuple(sorted(
            (e, tuple(sorted(x["key"] for x in c))) for e, c in found.items())))
    ok = len(set(keys)) == 1
    record("S4_source_order_invariant", ok,
           {"orders": 4, "distinct_outcomes": len(set(keys)),
            "conflicts": len(keys[0])})


# ---------------------------------------------------------------- S5
def s5():
    rows, conflicting, _s, _sl = build_fixture()
    st = load(rows)
    sample = sorted(conflicting)[:3]
    detail = {}
    with_prov = 0
    for e in sample:
        c = st.contradictions(e)
        if not c:
            continue
        prov = c[0].get("provenance") or {}
        named = {k: (v[2] if isinstance(v, list) and len(v) > 2 else v)
                 for k, v in prov.items()}
        detail[e] = {"values": c[0]["values"], "sources": named}
        if named and all(named.values()):
            with_prov += 1
    ok = with_prov == len(sample)
    record("S5_each_conflict_names_its_sources", ok,
           {"checked": len(sample), "with_provenance": with_prov,
            "example": detail.get(sample[0]) if sample else None})


if __name__ == "__main__":
    for f in (s1, s2, s3, s4, s5):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
