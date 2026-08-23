# -*- coding: utf-8 -*-
"""事前登録 14 の確認。experiments/garment/PREREG14_MARKS.md"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.garment_marks import (NOTCH_DEPTH_CM, SEAM_ALLOWANCE,  # noqa
                                    apply, arc_lengths, check_notch_depth,
                                    grain_line, offset_outline, rotate_piece)
from verantyx.garment_material import Fabrics                        # noqa
from verantyx.garment_drape import material_from                     # noqa
from verantyx.garment_measure import Measures                        # noqa
from verantyx.garment_pattern import draft                           # noqa
from verantyx.garment_sew import build, sew_and_drape                # noqa

RESULTS = {"prereg": "experiments/garment/PREREG14_MARKS.md", "checks": {}}
STORE = Path.home() / ".vera_garment"


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), **detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: "
          f"{json.dumps(detail, ensure_ascii=False)[:340]}")


#: **検査は利用者の台帳に依存しない。** 2026-08-23: 実寸の食い違い検出を
#: 入れた途端、利用者の store に入っていた袖丈の食い違いのせいで袖が
#: 引かれなくなり、この一式が KeyError で落ちました。可変のデータの上で
#: 走る検査は再現できません。ここで寸法を固定します。
FIXTURE = {"body_length": 96.0, "chest": 104.0,
           "shoulder": 47.0, "sleeve_length": 59.0}


def measures():
    m = Measures()
    for spot, value in FIXTURE.items():
        m.measured(spot, value, "cm", "PREREG14 の固定値", by="事前登録")
    return m


def material():
    return material_from(Fabrics.load(STORE / "fabrics.json"), "キュプラ")


def marked():
    return apply(draft(measures()))


# ---------------------------------------------------------------- VN1
def vn1():
    """**六つの釣り合い合印が出て、位置の根拠が付いている。**"""
    d = marked()
    roles = {p: {n["role"] for n in ns} for p, ns in d["notches"].items()}
    want_body = {"肩点", "脇"}
    ok = (want_body <= roles.get("前身頃", set())
          and want_body <= roles.get("後身頃", set())
          and "前振り" in roles.get("前身頃", set())
          and "後振り" in roles.get("後身頃", set())
          and "前胸" in roles.get("前身頃", set())
          and "後肩甲" in roles.get("後身頃", set())
          # **根拠が全部の合印に付いている**
          and all(n.get("basis") for ns in d["notches"].values() for n in ns))
    six = sorted({"肩点", "脇", "前振り", "後振り", "前胸", "後肩甲"})
    record("VN1_six_balance_notches_with_stated_basis", ok,
           {"roles_per_piece": {k: sorted(v) for k, v in roles.items()},
            "the_six": six,
            "front_pitch_basis": next(
                (n["basis"] for n in d["notches"]["前身頃"]
                 if n["role"] == "前振り"), "")[:120]})


# ---------------------------------------------------------------- VN2
def vn2():
    """**前は単、後ろの釣り合いは双。** 方向の約束であって飾りではない。"""
    d = marked()
    back_pitch = [n for n in d["notches"]["後身頃"] if n["role"] == "後振り"]
    front_all = [n for n in d["notches"]["前身頃"]]
    cap_back = [n for n in d["notches"]["袖"] if n["role"] == "後振り"]
    ok = (back_pitch and back_pitch[0]["kind"] == "double"
          and all(n["kind"] == "single" for n in front_all)
          and cap_back and cap_back[0]["kind"] == "double")
    record("VN2_single_is_front_double_is_back", ok,
           {"back_pitch_kind": back_pitch[0]["kind"] if back_pitch else None,
            "front_kinds": sorted({n["kind"] for n in front_all}),
            "cap_back_pitch_kind": cap_back[0]["kind"] if cap_back else None})


# ---------------------------------------------------------------- VN3
def vn3():
    """**合印は必ず対になる。相手のいない印は通さない。**"""
    d = marked()
    pairs = d["notch_pairs"]
    ok = (len(pairs) >= 8 and not d["notch_unpaired"]
          and all(p["kinds_agree"] for p in pairs))
    record("VN3_every_notch_is_paired", ok,
           {"pairs": len(pairs), "unpaired": len(d["notch_unpaired"]),
            "kinds_agree_all": all(p["kinds_agree"] for p in pairs),
            "roles": sorted({p["role"] for p in pairs})})


# ---------------------------------------------------------------- VN4
def vn4():
    """**いせは均等でない。脇の下は 0。**

    均等配分ならこの検査は落ちる。落ちないことが、合印がいせを
    運んでいる証拠。
    """
    d = marked()
    rows = d["ease_by_segment"]
    near_pit = [r for r in rows if "脇" in (r["from"], r["to"])]
    upper = [r for r in rows if r not in near_pit]
    ok = (near_pit and upper
          and all(abs(r["ease_cm"]) < 0.05 for r in near_pit)
          and all(r["ease_cm"] > 0.1 for r in upper))
    record("VN4_ease_is_not_spread_evenly", ok,
           {"underarm_segments": [{"seg": f"{r['from']}→{r['to']}",
                                   "ease_cm": r["ease_cm"]} for r in near_pit],
            "upper_segments": [{"seg": f"{r['from']}→{r['to']}",
                                "ease_cm": r["ease_cm"]} for r in upper],
            "total_ease_cm": round(sum(r["ease_cm"] for r in rows), 3)})


# ---------------------------------------------------------------- VN5
def vn5():
    """**縫い代は辺ごとに違い、インチの原典が併記される。裾は減らさない。**"""
    d = marked()
    segs = d["seam_allowance"]["前身頃"]["segment_allowance"]
    by = {s["edge"]: s for s in segs}
    ok = (by.get("肩線", {}).get("cm") == 1.27
          and by.get("袖ぐり", {}).get("cm") == 0.95
          and by.get("衿ぐり", {}).get("cm") == 0.64
          and by.get("裾", {}).get("cm") == 2.54
          and by.get("中心線", {}).get("cm") == 0.0
          and all(s["imperial"] for s in segs)
          # 全部が同じ値ではない = 辺ごとに変えている
          and len({s["cm"] for s in segs}) >= 4)
    record("VN5_allowance_varies_by_edge_with_imperial_source", ok,
           {"per_edge": {k: {"cm": v["cm"], "imperial": v["imperial"]}
                         for k, v in by.items()},
            "distinct_values": len({s["cm"] for s in segs})})


# ---------------------------------------------------------------- VN6
def vn6():
    """**出来上がり線は動かない。** 層14と層1を両方持つ。"""
    d = marked()
    base = draft(measures())
    by_name = {p["name"]: p for p in base["pieces"]}
    bad = []
    for name, off in d["seam_allowance"].items():
        if off["verdict"] != "ANSWER":
            continue
        want = [[round(x, 3), round(y, 3)] for x, y in by_name[name]["outline"]]
        if off["sew_line"] != want:
            bad.append(name)
        if off["cut_line"] == off["sew_line"]:
            bad.append(name + ":縫い代が0")
    ok = not bad
    record("VN6_the_sew_line_never_moves", ok,
           {"pieces_checked": list(d["seam_allowance"]),
            "mismatched": bad,
            "layers": d["seam_allowance"]["前身頃"]["layers"]})


# ---------------------------------------------------------------- VN7
def vn7():
    """**合印の深さ ≤ 縫い代の半分。超えたら通さない。**"""
    d = marked()
    ok_all = all(c["verdict"] == "ANSWER" for c in d["notch_depth_checks"])
    # わざと深くすると落ちること
    deep = [{"edge": "衿ぐり", "role": "試験", "depth_cm": 0.5}]
    bites = check_notch_depth(deep, {})["verdict"] != "ANSWER"
    ok = ok_all and bites
    record("VN7_notch_depth_bounded_by_allowance", ok,
           {"all_within": ok_all, "depth_cm": NOTCH_DEPTH_CM,
            "neckline_allowance_cm": SEAM_ALLOWANCE["衿ぐり"][0],
            "max_allowed_cm": round(SEAM_ALLOWANCE["衿ぐり"][0] / 2, 3),
            "gate_bites_on_too_deep": bites})


# ---------------------------------------------------------------- VN8
def vn8():
    """**縫い代を変えると裁ち切り線が動き、出来上がり線は動かない。**"""
    base = draft(measures())
    p = {x["name"]: x for x in base["pieces"]}["前身頃"]
    wide = offset_outline(p["outline"], p["edges"], {"肩線": 3.0})
    norm = offset_outline(p["outline"], p["edges"])
    ok = (wide["verdict"] == "ANSWER" and norm["verdict"] == "ANSWER"
          and wide["sew_line"] == norm["sew_line"]
          and wide["cut_line"] != norm["cut_line"])
    moved = max(math.dist(a, b) for a, b in
                zip(wide["cut_line"], norm["cut_line"]))
    record("VN8_changing_allowance_moves_only_the_cut_line", ok,
           {"sew_line_identical": wide["sew_line"] == norm["sew_line"],
            "cut_line_changed": wide["cut_line"] != norm["cut_line"],
            "max_cut_line_shift_cm": round(moved, 3)})


# ---------------------------------------------------------------- VN9
def vn9():
    """**布目線は一本の直線で、意味を持つのは向きだけ。**"""
    d = marked()
    ok = (len(d["grain"]) == len(d["pieces"])
          and all(len(g["line"]) == 2 for g in d["grain"])
          and all(g["angle_deg"] == 90.0 for g in d["grain"])
          and all(g["layer"] == 7 for g in d["grain"])
          # 毛並みが台帳に無いので、向きの扱いは「未記録」
          and all(g["orientation"] == "UNKNOWN_NAP_NOT_RECORDED"
                  for g in d["grain"]))
    record("VN9_grain_is_one_line_direction_only", ok,
           {"pieces": [g["piece"] for g in d["grain"]],
            "points_per_line": sorted({len(g["line"]) for g in d["grain"]}),
            "angle_deg": sorted({g["angle_deg"] for g in d["grain"]}),
            "orientation": sorted({g["orientation"] for g in d["grain"]}),
            "why_unknown": "毛並みは生地の性質で、台帳に記録がない"})


# --------------------------------------------------------------- VN10
def vn10():
    """**型紙を回すと布目線も回り、布目に対する角度が保存される。**"""
    d = marked()
    base = draft(measures())
    p = {x["name"]: x for x in base["pieces"]}["前身頃"]
    g = [x for x in d["grain"] if x["piece"] == "前身頃"][0]
    ns = d["notches"]["前身頃"]
    rot = rotate_piece(p, g, ns, 45.0)

    def ang(line):
        (x1, y1), (x2, y2) = line
        return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0

    turned = (ang(rot["grain"]["line"]) - ang(g["line"])) % 180.0
    ok = (abs(turned - 45.0) < 1e-3
          and abs(rot["grain"]["angle_deg"] - (90.0 + 45.0) % 180.0) < 1e-3
          # 合印は弧長なので回しても変わらない
          and [n["arc_cm"] for n in rot["notches"]] == [n["arc_cm"]
                                                        for n in ns])
    record("VN10_rotation_carries_the_grain", ok,
           {"grain_line_turned_deg": round(turned, 4),
            "angle_before": g["angle_deg"],
            "angle_after": rot["grain"]["angle_deg"],
            "notch_arcs_unchanged": [n["arc_cm"] for n in rot["notches"]]
            == [n["arc_cm"] for n in ns]})


# --------------------------------------------------------------- VN11
def vn11():
    """**引けない縫い代は「引けない」と言う。**"""
    base = draft(measures())
    p = {x["name"]: x for x in base["pieces"]}["前身頃"]
    # 身頃幅を超える縫い代を要求すれば、外にずらした線は自分と交わる
    huge = offset_outline(p["outline"], p["edges"],
                          {"肩線": 90.0, "袖ぐり": 90.0, "衿ぐり": 90.0})
    ok = (huge["verdict"] == "UNKNOWN_SEAM_ALLOWANCE_SELF_INTERSECTS"
          and "cut_line" not in huge
          and huge.get("how_to_close"))
    record("VN11_impossible_allowance_is_refused", ok,
           {"verdict": huge["verdict"],
            "returned_a_shape": "cut_line" in huge,
            "how_to_close": huge.get("how_to_close", "")})


# --------------------------------------------------------------- VN12
def vn12():
    """**合印で縫うと落ちる形が変わる。** これが崩れたら合印は絵。

    2026-08-23 追記: 目の位置に専用の頂点を置くようにしたので、比例配分
    と合印配分では**メッシュ自体も変わります**(目の位置が違うので)。
    それは実態に近い — 目がどこに落ちるかを決めているのは合印です。
    だから比較は**両方に共通する格子の頂点だけ**で取ります。そこは
    どちらの組み方でも同一なので、差は縫い目の対応から来ています。
    """
    d = draft(measures())
    mat = material()
    b_prop = build(d, marks=None)
    b_notch = build(d, marks=apply(d))
    grid = sum(v["vertices"] for v in b_prop["pieces"].values())
    grid_n = sum(v["vertices"] for v in b_notch["pieces"].values())
    same_grid = (grid == grid_n
                 and b_prop["points"][:grid] == b_notch["points"][:grid])
    a = sew_and_drape(b_prop, mat, iterations=800)["points"]
    c = sew_and_drape(b_notch, mat, iterations=800)["points"]
    worst = max(math.dist(a[i], c[i]) for i in range(grid))
    modes = {r["seam"]: r.get("correspondence") for r in b_notch["seams"]}
    ok = (same_grid and worst > 0.5
          and any(v == "notched" for v in modes.values()))
    record("VN12_notches_change_the_drape", ok,
           {"shared_grid_vertices": grid, "grid_identical": same_grid,
            "worst_difference_cm": round(worst, 3),
            "mean_difference_cm": round(
                sum(math.dist(a[i], c[i]) for i in range(grid)) / grid, 3),
            "stitch_vertices_proportional": len(b_prop["points"]) - grid,
            "stitch_vertices_notched": len(b_notch["points"]) - grid,
            "correspondence": modes,
            "meaning": "格子の頂点は両方で同一なので、そこの差は縫い目の"
                       "対応から来る。目の頂点は合印が決めるので別々"})


# --------------------------------------------------------------- VN13
def vn13():
    """**裁ち切り線は必ず出来上がり線を囲む。**

    2026-08-23 に見つけた欠陥: 外向きの符号が逆で、三枚とも縫い代が
    **内側**に付いていた。それでも VN5-VN8・VN11 は全部通っていた —
    どれも「向き」を見ていなかったから。図を描くまで気付かなかった。
    """
    from verantyx.garment_marks import _signed_area

    d = marked()
    rows, bad = [], []
    for name, off in d["seam_allowance"].items():
        if off["verdict"] != "ANSWER":
            bad.append(name)
            continue
        a_sew = abs(_signed_area(off["sew_line"]))
        a_cut = abs(_signed_area(off["cut_line"]))
        rows.append({"piece": name, "sew_cm2": round(a_sew, 1),
                     "cut_cm2": round(a_cut, 1)})
        if a_cut <= a_sew:
            bad.append(name)
        for q in off["sew_line"]:
            if not _inside(off["cut_line"], q):
                bad.append(f"{name}:頂点が外")
                break
    record("VN13_the_cut_line_encloses_the_sew_line", not bad,
           {"areas": rows, "failures": bad,
            "why": "向きの取り違えは、面積を見る検査だけが捕まえる"})


def _inside(poly, p):
    hit = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > p[1]) != (y2 > p[1]):
            t = (p[1] - y1) / (y2 - y1)
            if p[0] < x1 + t * (x2 - x1):
                hit = not hit
    return hit


# --------------------------------------------------------------- VN14
def vn14():
    """**尖った角で裁ち切り線が飛ばない。**

    袖山の先で留め継ぎの交点が伸び、裁ち切り線が y=243cm まで行っていた
    (出来上がりは 74cm)。留め継ぎに上限を置き、超えたら角を落とす。
    """
    from verantyx.garment_marks import MITRE_LIMIT

    d = marked()
    rows, bad = [], []
    for name, off in d["seam_allowance"].items():
        if off["verdict"] != "ANSWER":
            continue
        worst = max(min(math.dist(q, s) for s in off["sew_line"])
                    for q in off["cut_line"])
        widest = max(x["cm"] for x in off["segment_allowance"])
        rows.append({"piece": name, "worst_cm": round(worst, 3),
                     "widest_allowance_cm": widest,
                     "bevelled": off["bevelled_corners"]})
        if worst > MITRE_LIMIT * widest:
            bad.append(name)
    record("VN14_no_mitre_spike", not bad,
           {"per_piece": rows, "mitre_limit": MITRE_LIMIT, "failures": bad})


if __name__ == "__main__":
    for f in (vn1, vn2, vn3, vn4, vn5, vn6, vn7, vn8, vn9, vn10, vn11, vn12, vn13, vn14):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_marks.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
