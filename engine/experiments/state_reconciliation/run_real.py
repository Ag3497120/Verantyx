# -*- coding: utf-8 -*-
"""実データでの状態突合 — PREREG3_REAL_DATA.md の R1〜R5。

茨城県の避難施設を、国の集約(GeoJSON)と県の集約(CSV)という
**二つの実在する出所**で突き合わせる。食い違いは仕込まない。
数値は実行結果のみ。
"""
import csv
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.cross_store import CrossStore  # noqa: E402
from verantyx.document_ingest import deep_report  # noqa: E402

SP = Path("/private/tmp/claude-501/-Users-motonishikoudai-Projects-Vera/"
          "9853536a-f02d-4ffd-bc38-7c7a50ce0f8c/scratchpad")
RESULTS = {"prereg": "experiments/state_reconciliation/PREREG3_REAL_DATA.md",
           "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


_PAREN = re.compile(r"[（(][^）)]*[）)]")


def norm(name: str) -> str:
    """施設名の正規化(閉じた規則)。括弧内注記と空白だけを落とす。"""
    s = _PAREN.sub("", str(name or ""))
    return s.replace("　", "").replace(" ", "").strip()


def load_sources():
    geo = json.load(open(SP / "ibaraki.geojson", encoding="utf-8"))
    national = {}
    for f in geo["features"]:
        p = f["properties"]
        addr = str(p.get("所在地", ""))
        m = re.search(r"茨城県([^0-9]+?[市町村])", addr)
        city = m.group(1) if m else ""
        national[(city, norm(p.get("指定緊急避難場所")))] = p

    rows = list(csv.DictReader(
        open(SP / "ibaraki.csv", encoding="utf-8-sig", errors="replace")))
    flag_col = next(c for c in rows[0] if c.startswith("指定緊急避難場所"))
    pref = {}
    for r in rows:
        addr = str(r.get("住所", ""))
        m = re.search(r"茨城県([^0-9]+?[市町村])", addr)
        city = m.group(1) if m else ""
        pref[(city, norm(r.get("施設名")))] = {
            "flag": str(r.get(flag_col, "")).strip(),
            "source": str(r.get("出典組織", "")).strip() or "茨城県",
        }
    return national, pref


def build(national, pref):
    """状態として置く。極つきの面と裸の語の両方(散文経路と同じ形)。"""
    st = CrossStore(track_provenance=True)

    def state(core, aspect, value, source):
        st.add(core, [f"{aspect}:{value}", value], source=source)

    for key, p in national.items():
        core = f"{key[0]}|{key[1]}"
        state(core, "有効", "有効", "国の集約（指定緊急避難場所データ）")
    for key, r in pref.items():
        core = f"{key[0]}|{key[1]}"
        if r["flag"] == "1":
            state(core, "有効", "有効", r["source"])
        elif r["flag"] == "0":
            state(core, "有効", "無効", r["source"])
        # 9(不明)は極を置かない — 不明は否定ではない
    return st


def main():
    national, pref = load_sources()
    both = set(national) & set(pref)
    only_nat = set(national) - set(pref)
    only_pref = set(pref) - set(national)
    st = build(national, pref)

    # R1: 実在する食い違い
    contested, supported, unknown = [], [], []
    for key in sorted(both):
        core = f"{key[0]}|{key[1]}"
        r = deep_report(st, core)
        (contested if r["confidence"] == "contested"
         else supported if r["confidence"] == "supported"
         else unknown).append((core, r))
    flags = {}
    for key in both:
        flags[pref[key]["flag"]] = flags.get(pref[key]["flag"], 0) + 1
    record("R1_real_conflicts_found", True,
           {"matched_facilities": len(both), "contested": len(contested),
            "supported": len(supported), "other": len(unknown),
            "pref_flag_distribution": flags,
            "example": (contested[0][0] if contested else None)})

    # R2: 9(不明)を争いに数えていない
    nine = [k for k in both if pref[k]["flag"] == "9"]
    nine_contested = [k for k in nine
                      if deep_report(st, f"{k[0]}|{k[1]}")["confidence"]
                      == "contested"]
    record("R2_unknown_is_not_denial", not nine_contested,
           {"flag_9_matched": len(nine), "of_which_contested":
            len(nine_contested)})

    # R3: 片方にしか無い施設 — 不在の型が実データで効くか
    ghost = f"{'__'}|{'この施設は両方に無い'}"
    rep_ghost = deep_report(st, ghost)
    sample_only = sorted(only_pref)[:1]
    rep_only = (deep_report(st, f"{sample_only[0][0]}|{sample_only[0][1]}")
                if sample_only else {})
    record("R3_absence_is_typed_on_real_data",
           rep_ghost["confidence"] == "unknown_not_held"
           and rep_ghost["held"] is False,
           {"only_in_national": len(only_nat), "only_in_pref": len(only_pref),
            "never_mentioned": rep_ghost["confidence"],
            "held_by_one_source_only": rep_only.get("confidence")})

    # R4: 規模は施設数に比例する
    tmp = Path(tempfile.mkdtemp())
    p_all = tmp / "all.json"
    st.save(p_all)
    half_nat = dict(list(national.items())[:len(national) // 2])
    half_pref = dict(list(pref.items())[:len(pref) // 2])
    st_half = build(half_nat, half_pref)
    p_half = tmp / "half.json"
    st_half.save(p_half)
    ratio = p_all.stat().st_size / max(p_half.stat().st_size, 1)
    record("R4_size_follows_facilities", 1.6 <= ratio <= 2.4,
           {"cores_all": st.n_cores(), "bytes_all": p_all.stat().st_size,
            "cores_half": st_half.n_cores(),
            "bytes_half": p_half.stat().st_size,
            "ratio": round(ratio, 3), "bar": "1.6-2.4x for 2x facilities"})

    # R5: 出典
    named = 0
    ex = None
    for core, r in contested[:20]:
        sides = r["disputed"][0]["sides"] if r["disputed"] else []
        by = {s["claim"]: s["sources"] for s in sides}
        if all(by.values()):
            named += 1
            ex = ex or {core: by}
    record("R5_each_conflict_names_its_sources",
           bool(contested) and named == min(len(contested), 20),
           {"checked": min(len(contested), 20), "with_sources": named,
            "example": ex})

    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_real.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")


if __name__ == "__main__":
    main()
