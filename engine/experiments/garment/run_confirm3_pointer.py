# -*- coding: utf-8 -*-
"""出典ポインタの確認測定 — PREREG3_SOURCE_POINTER.md の V71〜V75。

測るのは「確かめられる、が見かけだけになっていないこと」。
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.garment import (Ledger, REF_MISSING, REF_NONE,  # noqa: E402
                              REF_OK, ref_status)

RESULTS = {"prereg": "experiments/garment/PREREG3_SOURCE_POINTER.md",
           "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


# ---------------------------------------------------------------- V71
def v71():
    """確定欄の全行が「再確認できるか」を伴う。"""
    with tempfile.TemporaryDirectory() as d:
        film = Path(d) / "film.mp4"
        film.write_bytes(b"x")
        led = Ledger()
        led.observe("collar", "shape", "ノッチ", "frame 182",
                    ref_path=str(film), ref_mark="f182")
        led.observe("body", "silhouette", "Aライン", "手で見た")  # 参照なし
        spec = led.spec()
        rows = spec["confirmed"]
        ok = (len(rows) == 2
              and all("verifiable" in r for r in rows)
              and spec["counts"]["verifiable"] == 1
              and any(r["verifiable"] for r in rows)
              and any(not r["verifiable"] for r in rows))
        record("V71_every_confirmed_row_says_if_it_can_be_rechecked", ok,
               {"confirmed": len(rows),
                "verifiable_count": spec["counts"]["verifiable"],
                "reasons": [r.get("unverifiable_reason", "") for r in rows]})


# ---------------------------------------------------------------- V72
def v72():
    """参照先が手元に無いことは「無い」ではない。"""
    with tempfile.TemporaryDirectory() as d:
        here = Path(d) / "a.mp4"
        here.write_bytes(b"x")
        led = Ledger()
        a = led.observe("collar", "shape", "ノッチ", "s", ref_path=str(here))
        b = led.observe("sleeve", "cuff", "折返し", "s",
                        ref_path=str(Path(d) / "gone.mp4"))
        c = led.observe("body", "dart", "有り", "s")
        u = led.observe("pocket", "type", "箱", "s",
                        ref_url="https://example.invalid/x")
        ok = (ref_status(a) == REF_OK and ref_status(b) == REF_MISSING
              and ref_status(c) == REF_NONE and ref_status(u) == REF_OK)
        record("V72_missing_here_is_not_missing_everywhere", ok,
               {"present": ref_status(a), "unplugged": ref_status(b),
                "no_ref": ref_status(c), "url": ref_status(u)})


# ---------------------------------------------------------------- V73
def v73():
    """同じコマを二度読んでも証拠は一つ。"""
    with tempfile.TemporaryDirectory() as d:
        film = Path(d) / "film.mp4"
        film.write_bytes(b"x")
        led = Ledger()
        led.observe("collar", "shape", "ノッチ", "1回目",
                    ref_path=str(film), ref_mark="f182")
        led.observe("collar", "shape", "ノッチ", "2回目",
                    ref_path=str(film), ref_mark="f182")
        twice = led.state("collar", "shape")
        led.observe("collar", "shape", "ノッチ", "別コマ",
                    ref_path=str(film), ref_mark="f231")
        after = led.state("collar", "shape")
        ok = (twice["agreed"] == 1 and twice["entries"] == 2
              and after["agreed"] == 2)
        record("V73_independence_is_counted_by_reference", ok,
               {"same_frame_twice": twice["agreed"],
                "entries": twice["entries"],
                "after_a_second_frame": after["agreed"]})


# ---------------------------------------------------------------- V74
def v74():
    """採用しても書き出しても、参照は消えない。"""
    with tempfile.TemporaryDirectory() as d:
        film = Path(d) / "film.mp4"
        film.write_bytes(b"x")
        store = Path(d) / "ledger.json"
        led = Ledger()
        led.propose("fabric", "kind", "ウール", "視覚モデルv2")
        led.observe("collar", "shape", "ノッチ", "frame 182",
                    ref_path=str(film), ref_mark="f182")
        led.adopt("fabric", "kind", "ウール", "担当:西小田")
        led.save(store)
        back = Ledger.load(store)
        e = next(x for x in back.entries if x.part == "collar")
        adopted = next(x for x in back.entries if x.part == "fabric")
        ok = (e.ref_path == str(film) and e.ref_mark == "f182"
              and adopted.adopted_by == "担当:西小田"
              and adopted.source == "視覚モデルv2")
        record("V74_references_survive_adoption_and_saving", ok,
               {"ref_path_kept": e.ref_path == str(film),
                "mark_kept": e.ref_mark, "origin_kept": adopted.source})


# ---------------------------------------------------------------- V75
def v75():
    """入れる順で agreed は変わらない。"""
    with tempfile.TemporaryDirectory() as d:
        film = Path(d) / "film.mp4"
        film.write_bytes(b"x")
        marks = ["f182", "f231", "f182", "f300"]

        def build(order):
            led = Ledger()
            for mk in order:
                led.observe("collar", "shape", "ノッチ", f"src-{mk}",
                            ref_path=str(film), ref_mark=mk)
            s = led.state("collar", "shape")
            return (s["agreed"], s["verifiable"])

        a = build(marks)
        b = build(list(reversed(marks)))
        c = build([marks[2], marks[0], marks[3], marks[1]])
        ok = (a == b == c and a[0] == 3)
        record("V75_order_does_not_change_the_count", ok,
               {"same": a == b == c, "agreed": a[0]})


if __name__ == "__main__":
    for f in (v71, v72, v73, v74, v75):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_pointer.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
