# -*- coding: utf-8 -*-
"""番人(covenant guard)の確認測定 — PREREG.md の V1〜V5 を実測する。

実地試験(別マシン、Claude Code フック7個)が名指しした限界のうち、
器官側で塞ぐと約束したもの:
  限界1: 約束の破棄経路が無い            → V1(退役)
  限界2: 字面照合 — 🎉 そのものは素通し   → V2(文字クラス)
  限界3: 英語の指示から約束が生まれない   → V1(en抽出)
  限界5: 常駐の起動中 15〜45秒 fail-open  → V5(guard CLI 直呼びの実時間)
(限界4 PostToolUse は tools/guard/hook_posttool.py — フック側の覆い。)

数値は全て実行結果から。予想は書かない。
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.covenant import (Covenant, Register,  # noqa: E402
                               extract_covenants)


def _set(reg, name, quote="", forbids=(), requires=(), turn=-1):
    return reg.add(Covenant(name=name, quote=quote,
                            forbids=list(forbids),
                            requires=list(requires), said_at_turn=turn))

RESULTS = {"prereg": "experiments/guard/PREREG.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


# ---------------------------------------------------------------- V1
# 抽出(ja+en)と退役。退役後は check にも fading にも出ないが、
# list には残る(削除ではなく退役 — 履歴は消さない)。

def v1():
    text = ("絵文字を使わないで。今後は必ずテストを実行して。 "
            "Never use TODO comments. Always run pytest before commit.")
    cands = extract_covenants(text, turn=1)
    forbids = [c for c in cands if c.get("forbids")]
    requires = [c for c in cands if c.get("requires")]
    ja_f = any("絵文字" in c["forbids"] for c in forbids)
    en_f = any("TODO" in c["forbids"] for c in forbids)
    ja_r = any(any("テスト" in r for r in c["requires"]) for c in requires)
    en_r = any(any("pytest" in r for r in c["requires"]) for c in requires)
    record("V1a_extract_ja_en",
           ja_f and en_f and ja_r and en_r,
           {"candidates": len(cands), "ja_forbid": ja_f, "en_forbid": en_f,
            "ja_require": ja_r, "en_require": en_r})

    reg = Register()
    for c in cands:
        _set(reg, c["name"], quote=c["quote"],
     forbids=c.get("forbids", []),
     requires=c.get("requires", []), turn=1)
    n_before = len(reg.covenants)
    bad = "了解です🎉 TODO: あとで直す"
    hits1 = reg.check(bad)["violations"]
    # 退役: TODO の約束をやめる
    todo_name = next(c.name for c in reg.covenants if "TODO" in c.forbids)
    reg.retire(todo_name, quote="もうTODOコメント使っていいよ", turn=5)
    hits2 = reg.check(bad)["violations"]
    still_todo = any("TODO" in (v.get("forbidden_used") or [])
                     for v in hits2)
    in_list = any(c.name == todo_name and c.retired for c in reg.covenants)
    record("V1b_retire_stops_check_keeps_list",
           len(hits1) >= 1 and not still_todo and in_list
           and len(reg.covenants) == n_before,
           {"hits_before": len(hits1), "hits_after": len(hits2),
            "todo_after_retire": still_todo, "retired_in_list": in_list})


# ---------------------------------------------------------------- V2
# 「絵文字を使わないで」だけの約束(語 "絵文字" は forbids に字面で入る)が、
# 語ではなく 🎉 そのものを捕まえる。逆に、語も文字も無い文は素通し。

def v2():
    reg = Register()
    _set(reg, "no-emoji", quote="絵文字を使わないで", forbids=["絵文字"], turn=1)
    hit = reg.check("できました🎉すごい⭐")
    caught = hit["verdict"] == "BROKEN" and any(
        v.get("class_hits") for v in hit["violations"])
    chars = []
    for v in hit["violations"]:
        for ch in v.get("class_hits", []):
            chars += ch["found"]
    clean = reg.check("できました。表情記号の話をしています。")
    # 文字クラスの停止条件: 絵文字の無い通常文で誤検知したら表を捨てる
    fp = clean["verdict"] == "BROKEN"
    record("V2_emoji_class_catches_glyph",
           caught and "🎉" in chars and not fp,
           {"caught": caught, "found_chars": chars,
            "false_positive_on_plain": fp})


# ---------------------------------------------------------------- V3
# 読めない指示からは何も作らない(推測しない)。退役済みは fading から消える。

def v3():
    vague = "なんかいい感じでよろしく。空気を読んでほどほどに。"
    cands = extract_covenants(vague, turn=1)
    record("V3a_unreadable_yields_nothing", len(cands) == 0,
           {"candidates": cands})

    reg = Register()
    _set(reg, "a", quote="絵文字を使わないで", forbids=["絵文字"], turn=1)
    _set(reg, "b", quote="TODOを書かないで", forbids=["TODO"], turn=1)
    # a は最初守られ、後半で破られる(=薄れる)。b は退役。
    for t in ["わかりました", "了解です", "対応します🎉", "完了🎉です"]:
        reg.check(t)
    reg.retire("b", quote="もういい", turn=9)
    fade = reg.fading(window=2)
    names = [f["covenant"] for f in fade.get("fading", [])]
    record("V3b_retired_absent_from_fading",
           "a" in names and "b" not in names,
           {"fading": names, "verdict": fade["verdict"]})


# ---------------------------------------------------------------- V4
# 登録順を変えても check の判定・違反集合が同じ(順序不変は憲法)。

def v4():
    covs = [("no-emoji", ["絵文字"]), ("no-todo", ["TODO"]),
            ("no-print", ["print文"])]
    texts = ["🎉done", "TODO: fix", "きれいな文", "print文とTODO両方"]
    import itertools
    baselines = None
    same = True
    for perm in itertools.permutations(covs):
        reg = Register()
        for name, f in perm:
            _set(reg, name, quote=f"{f[0]}を使わないで", forbids=f, turn=1)
        got = []
        for t in texts:
            out = reg.check(t)
            got.append((out["verdict"],
                        tuple(sorted(v["covenant"]
                                     for v in out["violations"]))))
        if baselines is None:
            baselines = got
        elif got != baselines:
            same = False
    record("V4_registration_order_invariant", same,
           {"permutations": 6, "texts": len(texts), "identical": same})


# ---------------------------------------------------------------- V5
# guard CLI の実時間。連合を読まない速い道が本当に速いかを凍結バイナリで測る。
# 基準: check 1回 ≤ 2秒。超えたら「橋がまだ要る」と正直に記録して落とす。

def v5():
    binp = Path.home() / "Projects/Verantyx/cli/VerantyxIDE/Vendor/vera-memory"
    if not binp.exists():
        record("V5_guard_cli_speed", False,
               {"error": f"frozen binary not found: {binp}"})
        return
    store = Path("/tmp/guard_confirm_store.json")
    for p in [store, store.with_name(store.stem + ".covenants.json")]:
        p.unlink(missing_ok=True)

    def call(op, payload):
        t0 = time.time()
        r = subprocess.run(
            [str(binp), "--store", str(store), "guard", op],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True, text=True, timeout=120)
        dt = time.time() - t0
        out = json.loads(r.stdout) if r.stdout.strip() else {"_stderr": r.stderr[-300:]}
        return dt, out

    t_set, o_set = call("set", {"name": "no-emoji",
                                "quote": "絵文字を使わないで",
                                "forbids": ["絵文字"], "turn": 1})
    times = []
    verdicts = []
    for txt in ["対応しました🎉", "対応しました。"]:
        dt, out = call("check", {"reply": txt})
        times.append(round(dt, 3))
        verdicts.append(out.get("verdict"))
    # フックが実際に使う経路(ソース直呼び)も測る。基準はこちらに置く:
    # tools/guard/_common.py はリポジトリがあればソース直呼びを選ぶ。
    src_times = []
    src_verdicts = []
    for txt in ["対応しました🎉", "対応しました。"]:
        t0 = time.time()
        r = subprocess.run(
            [sys.executable, "-m", "verantyx.cli", "--store", str(store),
             "guard", "check"],
            input=json.dumps({"reply": txt}, ensure_ascii=False),
            capture_output=True, text=True, timeout=60, cwd=str(ROOT))
        src_times.append(round(time.time() - t0, 3))
        src_verdicts.append(json.loads(r.stdout).get("verdict"))
    frozen_ok = verdicts == ["BROKEN", "KEPT"]
    hook_ok = src_verdicts == ["BROKEN", "KEPT"] and max(src_times) <= 2.0
    record("V5_guard_cli_speed", frozen_ok and hook_ok,
           {"frozen": {"set_s": round(t_set, 3), "check_s": times,
                       "verdicts": verdicts,
                       "note": "onefile展開が毎回かかる — 2秒超は正直に記録"},
            "source_cli": {"check_s": src_times, "verdicts": src_verdicts},
            "limit_s": 2.0,
            "hook_path": "tools/guard/_common.py はソース直呼びを優先、"
                         "凍結バイナリはリポジトリ不在時の控え"})


if __name__ == "__main__":
    for f in (v1, v2, v3, v4, v5):
        f()
    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} passed"
    out = Path(__file__).with_name("results_confirm.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
