# -*- coding: utf-8 -*-
"""設計図の確認測定 — PREREG7_DRAW.md の VW1〜VW5。

測るのは「台帳に無い線を引かないこと」。縫製師が読む図に、誰も観測して
いない形が入るのが、この段で一番危ない。
"""
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.garment import Ledger, is_generated                # noqa: E402
from verantyx.garment_draw import DRAWABLE, draw, save           # noqa: E402
from verantyx.garment_measure import Measures                    # noqa: E402

RESULTS = {"prereg": "experiments/garment/PREREG7_DRAW.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def fixture() -> Ledger:
    led = Ledger(title="映画X のコート")
    led.observe("collar", "shape", "ノッチドラペル", "cut 0:12:05")
    led.observe("body", "silhouette", "Aライン", "cut 0:12:07")
    # 推論と提案は確定ではない。図に出てはいけない。
    led.infer("sleeve", "construction", "二枚袖", "袖山の皺から")
    led.propose("pocket", "existence", "箱ポケット", "視覚モデルv2")
    return led


def parts_in_svg(svg: str):
    return set(re.findall(r'data-part="([a-z]+)"', svg))


# ---------------------------------------------------------------- VW1
def vw1():
    """**台帳に無い線を引かない。** 推論も提案も図には出ない。"""
    led = fixture()
    out = draw(led)
    drawn = parts_in_svg(out["svg"])
    ok = (drawn == {"collar", "body"}
          and "sleeve" not in drawn        # 推論しかない
          and "pocket" not in drawn        # 提案しかない
          and set(out["drawn"]) == drawn)
    record("VW1_no_line_without_a_confirmed_aspect", ok,
           {"drawn": sorted(drawn),
            "skipped": [s["part"] for s in out["skipped"]]})


# ---------------------------------------------------------------- VW2
def vw2():
    """同じ台帳からは同じ図。**作図であって生成ではない。**"""
    led = fixture()
    m = Measures()
    m.measured("body_length", 96.0, "cm", source="採寸", by="担当")
    a = draw(led, m)["svg"]
    b = draw(led, m)["svg"]
    c = draw(fixture(), m)["svg"]
    ok = (a == b == c)
    record("VW2_the_same_ledger_always_draws_the_same_figure", ok,
           {"identical": a == b == c, "bytes": len(a)})


# ---------------------------------------------------------------- VW3
def vw3():
    """欠けが図の上で見える。**空白で消えない。**"""
    led = fixture()
    out = draw(led)
    svg = out["svg"]
    named = [s["part"] for s in out["skipped"]]
    ok = ("未確定のため描いていない" in svg
          and all(p in svg for p in named)
          and set(named) == set(DRAWABLE) - {"collar", "body"})
    record("VW3_what_was_not_drawn_is_written_on_the_figure", ok,
           {"named_on_figure": named})


# ---------------------------------------------------------------- VW4
def vw4():
    """書き出した図は生成物。**その図から観測はできない。**"""
    with tempfile.TemporaryDirectory() as d:
        led = fixture()
        p = Path(d) / "flat.svg"
        info = save(led, p)
        marked = is_generated(p)
        refused = False
        try:
            led.observe("back", "structure", "背中心切替あり", "描いた図",
                        ref_path=str(p))
        except ValueError as e:
            refused = "UNKNOWN_GENERATED_NOT_EVIDENCE" in str(e)
        ok = (marked and refused and Path(info["stamp"]).exists())
        record("VW4_the_drawing_cannot_be_read_back_as_evidence", ok,
               {"marked": marked, "observe_refused": refused})


# ---------------------------------------------------------------- VW5
def vw5():
    """寸法が入ると図が変わる。無ければ既定で描き、**既定だと図に書く**。"""
    led = fixture()
    without = draw(led)
    m = Measures()
    m.measured("body_length", 96.0, "cm", source="採寸", by="担当")
    with_dim = draw(led, m)
    ok = (without["dimensions"]["body_length"] == 100.0
          and "body_length" in without["defaulted"]
          and "（既定の比率）" in without["svg"]
          and with_dim["dimensions"]["body_length"] == 96.0
          and "body_length" not in with_dim["defaulted"]
          and "（既定の比率）" not in with_dim["svg"]
          and without["svg"] != with_dim["svg"])
    record("VW5_measurements_change_the_figure_and_defaults_are_labelled", ok,
           {"without": without["dimensions"]["body_length"],
            "with": with_dim["dimensions"]["body_length"],
            "defaulted_without": without["defaulted"][:3]})


if __name__ == "__main__":
    for f in (vw1, vw2, vw3, vw4, vw5):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_draw.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
