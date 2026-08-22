# -*- coding: utf-8 -*-
"""言語対称の確認 — 番人の全経路が ja+en の両方で立つか(V11〜V13)。

抽出・解除・文字クラスは閉じた表(covenant.py)に一元化されている。
証人監査・隔離席・焼き込みは字面照合なので言語を選ばない — それも
en の実データで確認する。数値は全て実行結果から。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.covenant import (Covenant, Register,  # noqa: E402
                               extract_covenants, extract_releases)

RESULTS = {"prereg": "experiments/guard/PREREG2.md (言語対称の追補)",
           "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


# ---------------------------------------------------------------- V11
# 抽出の対称: 同じ意味の指示が ja でも en でも候補になる。
# 読めない文は両言語とも候補0(推測しない)。

def v11():
    pairs = [
        ("絵文字を使わないで", "Never use emojis"),
        ("TODOを書かないで", "Stop using TODO"),
        ("必ずテストを実行して", "Always run pytest"),
    ]
    rows = []
    ok = True
    for ja, en in pairs:
        ja_c = extract_covenants(ja)
        en_c = extract_covenants(en)
        both = len(ja_c) == 1 and len(en_c) == 1
        ok = ok and both
        rows.append({"ja": [ja, len(ja_c)], "en": [en, len(en_c)]})
    vague_ja = extract_covenants("なんかいい感じで")
    vague_en = extract_covenants("just be nice about it")
    ok = ok and not vague_ja and not vague_en
    record("V11_extract_symmetry", ok,
           {"pairs": rows, "vague": [len(vague_ja), len(vague_en)]})


# ---------------------------------------------------------------- V12
# 解除の対称: ja「もう絵文字使っていいよ」/ en "you can use emojis again"
# の両方が対象語を返し、退役まで通る。読めない解除は解除しない。

def v12():
    ja = extract_releases("もう絵文字使っていいよ")
    en = extract_releases("you can use emojis again")
    en2 = extract_releases("TODO is fine now")
    en3 = extract_releases("go ahead and use print")
    none = extract_releases("それはそれとして")
    none_en = extract_releases("maybe we could relax things")

    reg = Register()
    reg.add(Covenant(name="no-emoji", quote="Never use emojis",
                     forbids=["emojis"]))
    hit_before = reg.check("Done 🎉")["verdict"]
    for term in en:
        for c in reg.covenants:
            if not c.retired and term in c.forbids:
                reg.retire(c.name, quote="you can use emojis again")
    hit_after = reg.check("Done 🎉")["verdict"]

    ok = (ja == ["絵文字"] and en == ["emojis"] and en2 == ["TODO"]
          and en3 == ["print"] and none == [] and none_en == []
          and hit_before == "BROKEN" and hit_after == "KEPT")
    record("V12_release_symmetry", ok,
           {"ja": ja, "en": en, "en_fine_now": en2, "en_go_ahead": en3,
            "unreadable": [none, none_en],
            "retire_path": [hit_before, hit_after]})


# ---------------------------------------------------------------- V13
# 執行の言語中立: en の約束("emoji" クラス)が 🎉 を捕まえ、en の
# requires が en の証人で WITNESSED になり、en 候補の隔離席も動く。

def v13():
    reg = Register()
    reg.add(Covenant(name="no-emoji", quote="Never use emojis",
                     forbids=["emojis"]))
    hit = reg.check("Shipped! 🎉")
    glyph = any(v.get("class_hits") for v in hit["violations"])

    reg2 = Register()
    reg2.add(Covenant(name="must-lint", quote="Always run eslint",
                      requires=["eslint"]))
    a0 = reg2.audit()["verdict"]
    reg2.witness("Bash", detail="npx eslint src/ --fix", ok=True)
    a1 = reg2.audit()["verdict"]

    reg3 = Register()
    reg3.propose(Covenant(name="no-exclaim", quote="tone it down",
                          forbids=["!!"]))
    sh = reg3.check("Great!! Done!!")
    reg3.adopt("no-exclaim")
    en_broken = reg3.check("Great!! Done!!")["verdict"]

    ok = (hit["verdict"] == "BROKEN" and glyph
          and a0 == "REQUIRED_UNWITNESSED" and a1 == "REQUIRED_WITNESSED"
          and sh["verdict"] == "KEPT"
          and len(sh.get("shadow_violations", [])) == 1
          and en_broken == "BROKEN")
    record("V13_enforcement_language_neutral", ok,
           {"emoji_class_en": [hit["verdict"], glyph],
            "witness_en": [a0, a1],
            "quarantine_en": [sh["verdict"], en_broken]})


if __name__ == "__main__":
    for f in (v11, v12, v13):
        f()
    n = len(RESULTS["checks"])
    passed = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{passed}/{n} passed"
    out = Path(__file__).with_name("results_confirm_lang.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
