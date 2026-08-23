# -*- coding: utf-8 -*-
"""型紙を縫って落とす確認測定 — PREREG13_SEW.md の VF1〜VF7。

測るのは「型紙を無視して近さで縫っていないこと」と、
「一貫して計算された不合理を通していないこと」。
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.garment import Ledger, mark_generated                # noqa: E402
from verantyx.garment_drape import material_from                    # noqa: E402
from verantyx.garment_material import Fabrics                       # noqa: E402
from verantyx.garment_measure import Measures                       # noqa: E402
from verantyx.garment_pattern import draft                          # noqa: E402
from verantyx.garment_sew import (NO_PATTERN, SEAMS, build,         # noqa: E402
                                  sew_and_drape, validate)

RESULTS = {"prereg": "experiments/garment/PREREG13_SEW.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def measures() -> Measures:
    m = Measures()
    for spot, v in (("body_length", 96.0), ("chest", 104.0),
                    ("shoulder", 47.0), ("sleeve_length", 59.0)):
        m.measured(spot, v, "cm", source="実物採寸", by="担当:西小田")
    return m


def material():
    f = Fabrics()
    f.record("テスト布", "weight", 200, "試験資料 A")
    f.record("テスト布", "thickness", 0.5, "試験資料 A")
    return material_from(f, "テスト布")


# ---------------------------------------------------------------- VF1
def vf1():
    """**型紙が無ければ縫えない。**"""
    empty = build(draft(Measures()))
    ok = (empty["verdict"] == NO_PATTERN
          and empty["missing"]
          and empty.get("how_to_close")
          and "points" not in empty)
    record("VF1_no_pattern_no_sewing", ok,
           {"verdict": empty["verdict"], "missing": empty["missing"]})


# ---------------------------------------------------------------- VF2
def vf2():
    """**縫い目は名前付き辺から決まる。** 近さで勝手に繋がない。"""
    b = build(draft(measures()))
    names = {r["seam"] for r in b["seams"]}
    expected = {f"{pa}/{ea} ↔ {pb}/{eb}" for pa, ea, pb, eb, _ in SEAMS}
    sewn = [r for r in b["seams"] if r["state"] == "SEWN"]
    ok = (names == expected and len(sewn) == len(SEAMS)
          and all(r["stitches"] > 0 for r in sewn)
          and all("length_a" in r and "length_b" in r for r in sewn)
          and "近さで勝手に繋いでいません" in b["note"])
    record("VF2_seams_come_from_named_pattern_edges", ok,
           {"seams": sorted(names), "stitches":
            {r["seam"]: r["stitches"] for r in sewn}})


# ---------------------------------------------------------------- VF3
def vf3():
    """**出身が残る。** どの頂点がどのピース由来か。"""
    b = build(draft(measures()))
    counts = {name: b["owner"].count(name) for name in b["pieces"]}
    ok = (len(b["owner"]) == len(b["points"])
          and set(counts) == {"前身頃", "後身頃", "袖"}
          and all(v > 0 for v in counts.values())
          and sum(counts.values()) == len(b["points"]))
    record("VF3_every_vertex_remembers_its_piece", ok, {"counts": counts})


# ---------------------------------------------------------------- VF4
def vf4():
    """**縫い目が縮む。** 縮まなければ縫えていない。

    刻みを剛性から決めないと nan で発散した(実測)。同じ物理を解く
    二箇所が別の刻みを持つと、片方だけ壊れる。
    """
    b = build(draft(measures()))
    mat = material()
    runs = [sew_and_drape(b, mat, iterations=it) for it in (500, 2000)]
    gaps = [r["seam_gap"] for r in runs]
    finite = all(g["last"] == g["last"] for g in gaps)     # nan 除け
    ok = (finite
          and all(g["closed"] for g in gaps)
          and gaps[0]["last"] < gaps[0]["first"]
          # 収束: 反復を4倍にしても隙間が動かない
          and abs(gaps[1]["last"] - gaps[0]["last"]) < 0.5)
    record("VF4_the_seam_gap_shrinks_and_settles", ok,
           {"first": gaps[0]["first"], "at_500": gaps[0]["last"],
            "at_2000": gaps[1]["last"], "step": runs[0]["step"]})


# ---------------------------------------------------------------- VF5
def vf5():
    """**検査が効く。** 落ちれば形を返さず、割れたら全部返す。

    許容を緩めて通す誘惑を断つ: この型紙から縫った服は**実際に**
    局所最小に落ちる(VF8)。通らないのが正しい振る舞いなので、
    そこを測る。
    """
    got = validate(measures(), material(), iterations=400)
    strict = validate(measures(), material(), iterations=400,
                      tolerances={"order": 0.00001})
    ok = (set(got["checks"]) == {"seam_closed", "order", "starts"}
          and got["checks"]["seam_closed"]["verdict"] == "ANSWER"
          # 割れているので形を返さず、代わりに全部の形を返す
          and "points" not in got
          and got.get("why_no_shape")
          and len(got.get("shapes", [])) == 3
          # 順序を極端に厳しくすると、そちらでも落ちる
          and strict["verdict"] != "ANSWER"
          and "points" not in strict)
    record("VF5_the_validator_bites_and_withholds_the_shape", ok,
           {"verdict": got["verdict"], "shapes_returned":
            len(got.get("shapes", [])), "seam": got["checks"]["seam_closed"]["verdict"],
            "strict": strict["verdict"]})


# ---------------------------------------------------------------- VF8
def vf8():
    """**縫った服は局所最小に落ちる。反復では消えない。**

    始点を変えると 22cm 違う形に落ち着き、反復を 12 倍にしても
    差は縮まない。VE3(順序依存が反復で育つ)と同じ形の発見で、
    「もっと回した」は答えにならない。
    """
    diffs = []
    for it in (400, 1500, 5000):
        v = validate(measures(), material(), iterations=it)
        diffs.append(v["checks"]["starts"]["worst_difference"])
    spread = max(diffs) - min(diffs)
    ok = (all(d > 10.0 for d in diffs) and spread < 1.0)
    record("VF8_the_sewn_garment_sits_in_a_local_minimum", ok,
           {"iterations": [400, 1500, 5000], "start_differences": diffs,
            "does_not_shrink": spread < 1.0})


# ---------------------------------------------------------------- VF6
def vf6():
    """同じ型紙・同じ順序から同じ座標。"""
    b = build(draft(measures()))
    mat = material()
    a = sew_and_drape(b, mat, iterations=300)
    c = sew_and_drape(b, mat, iterations=300)
    b2 = build(draft(measures()))
    ok = (a["points"] == c["points"]
          and b2["points"] == b["points"]
          and b2["seam_pairs"] == b["seam_pairs"])
    record("VF6_deterministic", ok,
           {"same_drape": a["points"] == c["points"],
            "same_build": b2["seam_pairs"] == b["seam_pairs"],
            "vertices": len(a["points"])})


# ---------------------------------------------------------------- VF7
def vf7():
    """落とした服は生成物。**観測の出典にできない。**"""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sewn.obj"
        p.write_text("x", encoding="utf-8")
        mark_generated(p)
        led = Ledger()
        refused = False
        try:
            led.observe("back", "structure", "落とした服から", "シミュ",
                        ref_path=str(p))
        except ValueError as e:
            refused = "UNKNOWN_GENERATED_NOT_EVIDENCE" in str(e)
    good = validate(measures(), material(), iterations=300)
    ok = (refused
          and "観測の出典にはできません" in good["not_a_measurement"]
          and good.get("assumed"))
    record("VF7_the_sewn_garment_is_generated", ok,
           {"observe_refused": refused,
            "assumption_shown": bool(good.get("assumed"))})


if __name__ == "__main__":
    for f in (vf1, vf2, vf3, vf4, vf5, vf6, vf7, vf8):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_sew.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
