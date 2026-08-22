# -*- coding: utf-8 -*-
"""映像→コマ→視覚モデル→設計図 の確認測定 — PREREG4_PIPELINE.md V76〜V82。

測るのは「この流れが出所を溶かさないこと」。
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.garment import (Intake, Ledger, PARTS,          # noqa: E402
                              is_generated, mark_generated)

RESULTS = {"prereg": "experiments/garment/PREREG4_PIPELINE.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def scene(d):
    """映像1本を3コマに割った状態を作る。"""
    film = Path(d) / "movie.mp4"
    film.write_bytes(b"x" * 100)
    ink = Intake()
    ink.register(film, "video", at="2026-08-22T15:40")
    frames = []
    for mark, sec in (("f182", 7.58), ("f231", 9.62), ("f300", 12.5)):
        f = Path(d) / f"{mark}.jpg"
        f.write_bytes(b"x")
        ink.add_clip(film, f, mark, sec)
        frames.append((f, mark))
    return film, ink, frames


# ---------------------------------------------------------------- V76
def v76():
    """描かせた絵から観測はできない。"""
    with tempfile.TemporaryDirectory() as d:
        _, _, frames = scene(d)
        drawn = Path(d) / "technical_flat.png"
        drawn.write_bytes(b"x")
        mark_generated(drawn)
        led = Ledger()
        led.observe("collar", "shape", "ノッチ", "frame 182",
                    ref_path=str(frames[0][0]), ref_mark="f182")
        before = len(led.entries)
        refused = False
        try:
            led.observe("back", "structure", "背中心切替あり", "描いた設計図",
                        ref_path=str(drawn))
        except ValueError as e:
            refused = "UNKNOWN_GENERATED_NOT_EVIDENCE" in str(e)
        ok = (refused and len(led.entries) == before
              and is_generated(drawn) and not is_generated(frames[0][0]))
        record("V76_a_drawing_cannot_become_evidence", ok,
               {"refused": refused, "ledger_unchanged": len(led.entries) == before,
                "frame_is_not_generated": not is_generated(frames[0][0])})


# ---------------------------------------------------------------- V77
def v77():
    """モデルが断定しても提案の欄に入る。Vera は文面を読まない。"""
    with tempfile.TemporaryDirectory() as d:
        _, _, frames = scene(d)
        led = Ledger()
        led.propose("fabric", "kind", "確実にメルトンウールです",
                    "qwen3.8:27b", note="信頼度 0.98 断定",
                    ref_path=str(frames[0][0]), ref_mark="f182")
        st = led.state("fabric", "kind")
        spec = led.spec()
        in_confirmed = any(r["part"] == "fabric" and r["aspect"] == "kind"
                           for r in spec["confirmed"])
        ok = (st["state"] == "PROPOSED" and not in_confirmed
              and spec["counts"]["confirmed"] == 0)
        record("V77_a_confident_model_still_only_proposes", ok,
               {"state": st["state"], "in_confirmed": in_confirmed,
                "confirmed_count": spec["counts"]["confirmed"]})


# ---------------------------------------------------------------- V78
def v78():
    """コマから出た提案は、そのコマを参照に持つ。"""
    with tempfile.TemporaryDirectory() as d:
        film, ink, frames = scene(d)
        led = Ledger()
        led.propose("collar", "material", "ウール", "qwen3.8:27b",
                    ref_path=str(frames[1][0]), ref_mark="f231")
        pr = led.state("collar", "material")["proposals"][0]
        origin = ink.origin_of(frames[1][0])
        ok = (pr["ref"]["status"] == "VERIFIABLE"
              and pr["ref"]["mark"] == "f231"
              and origin is not None and origin["source"] == str(film))
        record("V78_a_proposal_from_a_frame_can_be_reopened", ok,
               {"ref": pr["ref"]["mark"], "status": pr["ref"]["status"],
                "traces_back_to": Path(origin["source"]).name if origin else None})


# ---------------------------------------------------------------- V79
def v79():
    """同じコマを同じモデルに二度読ませても積まない。"""
    with tempfile.TemporaryDirectory() as d:
        _, _, frames = scene(d)
        led = Ledger()
        for _ in range(5):
            led.propose("collar", "material", "ウール", "qwen3.8:27b",
                        ref_path=str(frames[0][0]), ref_mark="f182")
        same = len(led.state("collar", "material")["proposals"])
        led.propose("collar", "material", "ウール", "qwen3.8:27b",
                    ref_path=str(frames[1][0]), ref_mark="f231")
        other_frame = len(led.state("collar", "material")["proposals"])
        led.propose("collar", "material", "ウール", "別モデル",
                    ref_path=str(frames[0][0]), ref_mark="f182")
        other_model = len(led.state("collar", "material")["proposals"])
        ok = (same == 1 and other_frame == 2 and other_model == 3)
        record("V79_rereading_the_same_frame_adds_nothing", ok,
               {"five_reads_same_frame": same, "after_second_frame": other_frame,
                "after_second_model": other_model})


# ---------------------------------------------------------------- V80
def v80():
    """類似は由来ではない。人が採用するまで実例の申し立てにならない。"""
    from verantyx.garment_rights import RightsLedger, SPECIFIC, UNCHECKED

    with tempfile.TemporaryDirectory() as d:
        _, _, frames = scene(d)
        led = Ledger()
        rights = RightsLedger()
        # 類似検索が当てた: 提案として入る。距離は注記。
        led.propose("collar", "shape", "ノッチドラペル",
                    "類似検索 image-featureprint",
                    note="距離 0.14 — 出所の申告であって布の性質ではない",
                    ref_path=str(frames[0][0]), ref_mark="f182")
        before = rights.state("collar", "shape")["state"]
        # 人が見て「確かにあの作品だ」と採用したときだけ実例になる
        led.adopt("collar", "shape", "ノッチドラペル", "担当:西小田")
        rights.specific("collar", "shape", "映画X 公式衣装資料 p.12")
        after = rights.state("collar", "shape")["state"]
        ok = (before == UNCHECKED and after == SPECIFIC)
        record("V80_similarity_is_not_derivation", ok,
               {"before_human": before, "after_human": after})


# ---------------------------------------------------------------- V81
def v81():
    """割った跡が残る。コマだけが残らない。"""
    with tempfile.TemporaryDirectory() as d:
        film, ink, frames = scene(d)
        store = Path(d) / "intake.json"
        ink.save(store)
        back = Intake.load(store)
        o = back.origin_of(frames[2][0])
        rep = back.report()
        orphan = back.origin_of(Path(d) / "not_from_here.jpg")
        ok = (o is not None and o["source"] == str(film)
              and o["mark"] == "f300" and o["seconds"] == 12.5
              and rep["counts"] == {"sources": 1, "clips": 3}
              and orphan is None)
        record("V81_the_cut_keeps_its_origin", ok,
               {"origin": o, "counts": rep["counts"],
                "unregistered_clip_is_unknown": orphan is None})


# ---------------------------------------------------------------- V82
def v82():
    """コマを読ませる順は結論を動かさない。"""
    with tempfile.TemporaryDirectory() as d:
        _, _, frames = scene(d)
        reads = [
            ("collar", "shape", "ノッチ", frames[0]),
            ("collar", "shape", "ノッチ", frames[1]),
            ("detail", "button", "2つ", frames[0]),
            ("detail", "button", "3つ", frames[2]),
        ]

        def build(order):
            led = Ledger()
            for part, aspect, value, (f, mk) in order:
                led.observe(part, aspect, value, f"read {mk}",
                            ref_path=str(f), ref_mark=mk)
            sp = led.spec()
            return (sorted((r["part"], r["aspect"], r["value"], r["agreed"])
                           for r in sp["confirmed"]),
                    sorted((r["part"], r["aspect"]) for r in sp["contested"]),
                    sp["counts"])

        a = build(reads)
        b = build(list(reversed(reads)))
        c = build([reads[3], reads[0], reads[2], reads[1]])
        ok = (a == b == c and ("detail", "button") in a[1])
        record("V82_the_order_frames_are_read_does_not_matter", ok,
               {"same": a == b == c, "confirmed": a[0], "contested": a[1]})


if __name__ == "__main__":
    for f in (v76, v77, v78, v79, v80, v81, v82):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_pipeline.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
