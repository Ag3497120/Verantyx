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
from verantyx.garment_sew import (NO_PATTERN, SEAMS, _shoulder_pins, build,         # noqa: E402
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
    expected = {spec.get("label",
                         f"{spec['a'][0]}/{spec['a'][1]} ↔ "
                         f"{spec['b'][0]}/{spec['b'][1]}")
                for spec in SEAMS}
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
    # 2026-08-23: 縫い目のばねを正しい硬さにし、袖下線を足したので、
    # 500 回では閉じません。**数字を下げて通すのではなく、閉じるまでに
    # 要る回数を測って書きます。** 既定は収束で止まるので実行回数も出す。
    runs = [sew_and_drape(b, mat, iterations=it) for it in (2000, 8000)]
    gaps = [r["seam_gap"] for r in runs]
    finite = all(g["last"] == g["last"] for g in gaps)     # nan 除け
    ok = (finite
          and all(g["closed"] for g in gaps)
          and gaps[0]["last"] < gaps[0]["first"]
          # 収束: 反復を4倍にしても隙間が動かない
          and abs(gaps[1]["worst"] - gaps[0]["worst"]) < 0.02
          # **一本でも許容を超えていたら閉じていない**
          and all(g["over_tolerance"] == 0 for g in gaps))
    record("VF4_the_seam_gap_shrinks_and_settles", ok,
           {"first": gaps[0]["first"],
            "worst_at_2000": gaps[0]["worst"],
            "worst_at_8000": gaps[1]["worst"],
            "tolerance": gaps[0]["tolerance"],
            "over_tolerance": [gaps[0]["over_tolerance"],
                               gaps[1]["over_tolerance"]],
            "iterations_used": [runs[0]["iterations"], runs[1]["iterations"]],
            "seams_settled": [runs[0]["seams_settled"],
                              runs[1]["seams_settled"]],
            "step": runs[0]["step"]})


# ---------------------------------------------------------------- VF5
def vf5():
    """**検査が効く。** 落ちれば形を返さず、割れたら全部返す。

    許容を緩めて通す誘惑を断つ: この型紙から縫った服は**実際に**
    局所最小に落ちる(VF8)。通らないのが正しい振る舞いなので、
    そこを測る。
    """
    got = validate(measures(), material())
    # 順序は Jacobi で構成上 0 なので、そこは噛ませられない。
    # 噛むのは縫い目の側に変える。
    strict = validate(measures(), material(),
                      tolerances={"seam_closed": 0.0})
    # 2026-08-23 書き直し(二度目)。門が効くことは、**落ちる側と通る側の
    # 両方**で確かめます。袖を筒にしたので、袖のある一着は初期配置に
    # よって袖が 11cm 振れ、形を返しません。袖の無い二枚仕立ては
    # 0.9cm で一致して形を返します。**同じ道具が、決まるものは返し、
    # 決まらないものは名指しして断る** — そこを測ります。
    class _NoSleeve:
        def sheet(self):
            sh = measures().sheet()
            return {**sh, "measured": [r for r in sh["measured"]
                                       if r["spot"] != "sleeve_length"]}

    passes = validate(_NoSleeve(), material())
    tight = validate(measures(), material(),
                     tolerances={"starts": 0.0001})
    ok = (set(got["checks"]) == {"seam_closed", "order", "starts"}
          and got["checks"]["seam_closed"]["verdict"] == "ANSWER"
          # 落ちる側: 袖のある一着は形を返さず、責任のピースを名指しする
          and got["verdict"] != "ANSWER"
          and "points" not in got
          and got.get("blame", {}).get("worst_piece") == "袖"
          and "袖" in got.get("why_no_shape", "")
          # 通る側: 袖の無い二枚仕立ては形を返す
          and passes["verdict"] == "ANSWER" and "points" in passes
          and not passes.get("shapes")
          # 極端に締めれば、通っていた側も落ちる
          and tight["verdict"] != "ANSWER"
          and len(tight.get("shapes", [])) == 3
          # 順序は構成上そうなるので、検査として数えない
          and got["checks"]["order"].get("structural") is True)
    record("VF5_the_validator_bites_and_names_the_piece", ok,
           {"with_sleeve": got["verdict"],
            "with_sleeve_blame": got.get("blame", {}).get("worst_piece"),
            "with_sleeve_by_piece": got.get("blame", {}).get("by_piece"),
            "two_piece": passes["verdict"],
            "two_piece_returned_shape": "points" in passes,
            "tight_shapes_returned": len(tight.get("shapes", [])),
            "order_is_structural":
                got["checks"]["order"].get("structural")})


# ---------------------------------------------------------------- VF8
def vf8():
    """**三つの始点はどれも極小に着いている。それでも形が違う。**

    2026-08-23 に測り直した。前の数字(5.9→12.6cm)は欠陥の上で出たもので、
    多点始動の検査が **布そのものを差し替えていた** (VF11)。直した後は
    1.26 → 1.92 → 3.19cm で、桁が一つ小さい。

    ただし食い違いは消えず、**反復を増やすほど広がる**。そして下の
    勾配が示すとおり、広がった先はどれも極小 — 回し足りないのではない。
    SIGGRAPH の言葉では non-uniqueness。
    """
    diffs = []
    for it in (400, 1500, 5000):
        v = validate(measures(), material(), iterations=it)
        diffs.append(v["checks"]["starts"]["worst_difference"])
    tol = 3.0
    grads = _start_gradients(iterations=5000)
    converged = max(grads["ratios"]) < 0.01
    ok = (converged and diffs[-1] > diffs[0])
    record("VF8_all_starts_converge_yet_disagree", ok,
           {"iterations": [400, 1500, 5000], "start_differences": diffs,
            "tolerance": tol, "grows_with_iterations": diffs[-1] > diffs[0],
            "gradient_ratio_per_start": grads["ratios"],
            "all_converged": converged,
            "why": "勾配が初期の1%未満まで落ちていれば極小。そこで形が"
                   "違うなら、回し足りないのではなく解が一つに決まらない"})


def _start_gradients(iterations=5000):
    """各始点の終着で、エネルギーの勾配がどこまで落ちたか。

    **非一意と収束不足を分ける唯一の測り方。** 形が違うことだけでは
    どちらとも言えない。
    """
    import math as _m
    from verantyx.garment_drape import GRAVITY, _stiffness
    b = build(draft(measures()))
    mat = material()
    edges, pairs = b["edges"], b["seam_pairs"]
    stiff = _stiffness(mat)
    mass = mat["gsm"] / 10000.0
    rest = [_m.dist(b["points"][x], b["points"][y]) for x, y, _ in edges]
    pin = set(_shoulder_pins(b))
    # **最小化している式と同じ定数を使う。** 0.25 を直に書いていたので、
    # 縫い目の剛性を直した後、別の式の勾配を測っていました
    # (2026-08-23: 0.037 と出たが、実際は 0.00017 だった)。
    from verantyx.garment_sew import STITCH_STIFFNESS_RATIO
    k_st = round(max(stiff.values()) * STITCH_STIFFNESS_RATIO, 3)

    def gnorm(pos):
        n = len(pos)
        g = [[0.0] * 3 for _ in range(n)]
        for e, (x, y, kind) in enumerate(edges):
            d = [pos[y][t] - pos[x][t] for t in range(3)]
            L = _m.sqrt(sum(c * c for c in d)) or 1e-9
            f = stiff.get(kind, stiff["warp"]) * (L - rest[e]) / L
            for t in range(3):
                g[x][t] -= f * d[t]
                g[y][t] += f * d[t]
        for x, y in pairs:
            for t in range(3):
                d = k_st * (pos[x][t] - pos[y][t])
                g[x][t] += d
                g[y][t] -= d
        for i in range(n):
            g[i][1] += -mass * GRAVITY
        free = [i for i in range(n) if i not in pin]
        return _m.sqrt(sum(sum(c * c for c in g[i]) for i in free)
                       / max(len(free), 1))

    g0 = gnorm([list(p) for p in b["points"]])
    ratios = []
    for kk in (0.0, 0.8, -0.8):
        begin = [(p[0], p[1] + kk * _m.sin(i * 0.7), p[2] + kk * 0.4)
                 for i, p in enumerate(b["points"])]
        out = sew_and_drape(b, mat, start=begin, iterations=iterations)
        ratios.append(round(gnorm([list(p) for p in out["points"]]) / g0, 6))
    return {"initial_gradient": round(g0, 3), "ratios": ratios}


# ---------------------------------------------------------------- VF11
def vf11():
    """**始点は布を変えない。**

    2026-08-23 に見つけた欠陥: `sew_and_drape` が初期位置と自然長の
    両方を `built["points"]` から取っていたので、多点始動の検査が
    `built["points"]` を差し替えて **別の布を三着** 作っていた。
    「始点を変えたら形が変わる」ではなく「違う服を比べていた」。

    直した後の不変条件: 始点をどれだけ動かしても、落ちた服の辺の
    総長は変わらない(布は伸びない)。壊れていた道でこれを測ると、
    差が出る。
    """
    import math as _m
    b = build(draft(measures()))
    mat = material()

    def total_edge(pts):
        return sum(_m.dist(pts[x], pts[y]) for x, y, _ in b["edges"])

    begin = [(p[0], p[1] + 0.8 * _m.sin(i * 0.7), p[2] + 0.8 * 0.4)
             for i, p in enumerate(b["points"])]
    good = sew_and_drape(b, mat, start=begin, iterations=800)
    plain = sew_and_drape(b, mat, iterations=800)

    # 壊れていた道を再現する: built["points"] ごと差し替える
    broken_built = dict(b)
    broken_built["points"] = begin
    broken = sew_and_drape(broken_built, mat, iterations=800)

    L_plain = total_edge(plain["points"])
    L_good = total_edge(good["points"])
    L_broken = total_edge(broken["points"])
    ok = (abs(L_good - L_plain) / L_plain < 0.02
          and abs(L_broken - L_plain) / L_plain > abs(L_good - L_plain) / L_plain)
    record("VF11_the_start_does_not_change_the_cloth", ok,
           {"total_edge_flat_start_cm": round(L_plain, 1),
            "total_edge_moved_start_cm": round(L_good, 1),
            "total_edge_old_broken_path_cm": round(L_broken, 1),
            "moved_start_drift": round(abs(L_good - L_plain) / L_plain, 5),
            "broken_path_drift": round(abs(L_broken - L_plain) / L_plain, 5),
            "why": "始点は解き始める場所であって布ではない。自然長は"
                   "平らな型紙から取る"})


# ---------------------------------------------------------------- VF9
def vf9():
    """**揺れているのか、別の形なのかを分ける。**

    座標の差だけでは区別が付きません。同じ形が吊り点まわりに振れた
    だけなら、形の中の距離は変わらないはずです。実測では中の距離まで
    10cm 動いていて、**別の畳まれ方**に落ちています。
    """
    v = validate(measures(), material(), iterations=800)
    st = v["checks"]["starts"]
    # 2026-08-23 書き直し。前は「別の形である」を assert していたが、
    # その判定は欠陥の上で出ていた(VF11)。直した後の実測では、
    # 既定の反復では **同じ形が動いているだけ**。判別器が両者を
    # 区別できること自体を測る — 結論を固定しない。
    ok = ("shape_difference" in st and "same_shape_moved" in st
          and st["same_shape_moved"] == (st["shape_difference"]
                                         <= st["tolerance"])
          and set(st["by_piece"]) == {"前身頃", "後身頃", "袖"}
          and st["shape_difference"] >= 0.0)
    record("VF9_swing_and_different_shape_are_told_apart", ok,
           {"coordinate_difference": st["worst_difference"],
            "internal_distance_difference": st["shape_difference"],
            "same_shape_moved": st["same_shape_moved"],
            "by_piece": st["by_piece"]})


# --------------------------------------------------------------- VF10
def vf10():
    """**吊った点には目を付けない。**

    吊った点は動けないので、そこに縫い目が乗ると原理的に閉じません。
    前の版は前後の肩を別々に吊っていて、肩の縫い目が初期の前後間隔
    24.0cm をそのまま抱えたまま「縮んだので閉じた」と報告していました。
    """
    from verantyx.garment_sew import _shoulder_pins

    b = build(draft(measures()))
    pins = _shoulder_pins(b)
    sewn = {i for pair in b["seam_pairs"] for i in pair}
    owners = {b["owner"][i] for i in pins}
    gap = sew_and_drape(b, material(), iterations=800)["seam_gap"]
    ok = (len(pins) >= 1
          and not (set(pins) & sewn)
          # 前だけで吊る。後ろは肩の縫い目を通してぶら下がる。
          and owners == {"前身頃"}
          and gap["closed"] and gap["last"] <= gap["tolerance"])
    record("VF10_pins_never_sit_on_a_stitch", ok,
           {"pins": pins, "pin_pieces": sorted(owners),
            "pins_on_stitches": sorted(set(pins) & sewn),
            "gap_last": gap["last"], "gap_tolerance": gap["tolerance"]})


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
    for f in (vf1, vf2, vf3, vf4, vf5, vf6, vf7, vf8, vf9, vf10, vf11):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_sew.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
