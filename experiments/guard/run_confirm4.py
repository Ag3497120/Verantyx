# -*- coding: utf-8 -*-
"""番人 第四段の確認測定 — PREREG4.md の V19〜V24。

今日見つかった欠陥: 閉じた抽出規則が読んだ約束が**即座に執行(遮断)に
入る**。人が実際に書く指示20本のうち4本が間違った語を捕まえ、
`No new dependencies` → forbids=["new"] は返答「I added a new helper
function.」を BROKEN にした(本測定でも再現する)。

方針は規則を足すことではない(否定 645/661 が語彙の外、実測済み)。
規則が読んだものを執行に入れない — 隔離席は PREREG3 で既に器官にある。

数値は全て実行結果から。予想は書かない。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.covenant import (Covenant, Register,  # noqa: E402
                               extract_covenants)

RESULTS = {"prereg": "experiments/guard/PREREG4.md", "checks": {}}

#: 実地で誤読された指示(本日の実測。うち1本目が誤遮断を起こした)
DEFECTS = ["No new dependencies",
           "Always run the tests before committing",
           "Stop using console.log"]
#: 誤遮断された返答(実測済みの再現例)
REPLY = "I added a new helper function."

GUARD_DIR = ROOT / "tools" / "guard"


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def _quarantined(texts):
    """配線どおり — 規則が読んだ候補を隔離席へ置いた台帳。"""
    reg = Register()
    cands = []
    for t in texts:
        for c in extract_covenants(t, turn=1):
            cands.append(c)
            reg.propose(Covenant(
                name=c["name"], quote=c["quote"],
                forbids=list(c["forbids"]), requires=list(c["requires"]),
                origin=c["origin"]))
    return reg, cands


def _cli(store, op, payload):
    """ソース CLI を1回叩く(凍結バイナリは今日の変更を含まないので使わない)。"""
    r = subprocess.run(
        [sys.executable, "-m", "verantyx.cli", "--store", str(store),
         "guard", op],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True, text=True, timeout=120, cwd=str(ROOT))
    return json.loads(r.stdout) if r.stdout.strip() else {
        "_stderr": r.stderr[-400:]}


def _hook(script, store, payload):
    """フックを実プロセスで走らせ、標準出力の JSON を返す(無ければ {})。"""
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
           "VERA_GUARD_STORE": str(store), "HOME": str(Path.home())}
    r = subprocess.run(
        [sys.executable, str(GUARD_DIR / script)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True, text=True, timeout=180, env=env)
    if not r.stdout.strip():
        return {}
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"_raw": r.stdout[-400:], "_stderr": r.stderr[-400:]}


def _fresh(tag):
    store = Path(f"/tmp/guard_v4_{tag}.json")
    for p in (store, store.with_name(store.stem + ".covenants.json")):
        p.unlink(missing_ok=True)
    return store


# ---------------------------------------------------------------- V19
# 規則が読んだ約束は遮断しない。ただし shadow に出て見えなくなっていない。

def v19():
    # まず欠陥そのものを再現する(直ったことを言う前に、壊れていたことを測る)
    old = Register()
    for c in extract_covenants(DEFECTS[0], turn=1):
        old.add(Covenant(name=c["name"], quote=c["quote"],
                         forbids=list(c["forbids"]),
                         requires=list(c["requires"])))
    before_verdict = old.check(REPLY)["verdict"]

    # (a) 誤遮断を起こした1本だけの台帳 — shadow はちょうど1件
    one, _ = _quarantined([DEFECTS[0]])
    out = one.check(REPLY)
    shadow = out.get("shadow_violations", [])

    # (b) 欠陥3本を全部通して、執行に入った約束が0本
    reg, cands = _quarantined(DEFECTS)
    all_out = reg.check(REPLY)
    adopted = [c.name for c in reg.covenants if c.status == "adopted"]
    statuses = sorted({c.status for c in reg.covenants})

    ok = (before_verdict == "BROKEN"                 # 欠陥は実在した
          and out["verdict"] == "KEPT"               # もう遮断しない
          and out["violations"] == []
          and len(shadow) == 1                       # 黙って消えていない
          and shadow[0]["forbidden_used"] == ["new"]
          and shadow[0]["covenant"] == DEFECTS[0]
          and out["in_force"] == 0
          and all_out["verdict"] == "KEPT"
          and all_out["violations"] == []
          and adopted == []                          # 執行に入った約束は0
          and statuses == ["candidate"])
    record("V19_regex_read_rules_do_not_block", ok,
           {"before_fix": before_verdict, "after_fix": out["verdict"],
            "violations": len(out["violations"]),
            "shadow_one": [[v["covenant"], v.get("forbidden_used")]
                           for v in shadow],
            # 3本まとめた台帳の shadow。requires=["the"] の誤読は
            # forbidden_used が空 = 助言止まりで、フックは知らせない
            # (字面の required_missing は誤検知が多い、の既定の線)。
            "shadow_all_three": [[v["covenant"], v.get("forbidden_used"),
                                  v.get("required_missing")]
                                 for v in all_out.get(
                                     "shadow_violations", [])],
            "misreads": {c["name"]: {"forbids": c["forbids"],
                                     "requires": c["requires"]}
                         for c in cands},
            "adopted": adopted, "in_force_all": all_out["in_force"]})


# ---------------------------------------------------------------- V20
# 人が明示登録したものは今まで通り遮断する。利用者自身の行為を弱めない。

def v20():
    reg = Register()
    reg.add(Covenant(name="no-new-deps", quote="No new dependencies",
                     forbids=["new"]))
    out = reg.check(REPLY)

    # 実運用形(文字クラス)も今まで通り
    emo = Register()
    emo.add(Covenant(name="no-emoji", quote="絵文字を使わないで",
                     forbids=["絵文字"]))
    e = emo.check("対応しました🎉")
    clean = emo.check("対応しました。")

    ok = (out["verdict"] == "BROKEN" and len(out["violations"]) == 1
          and not out.get("shadow_violations")
          and out["in_force"] == 1
          and e["verdict"] == "BROKEN"
          and any(v.get("class_hits") for v in e["violations"])
          and clean["verdict"] == "KEPT")
    record("V20_explicit_registration_still_blocks", ok,
           {"explicit": [out["verdict"], len(out["violations"]),
                         out["in_force"]],
            "emoji_class": [e["verdict"], clean["verdict"]],
            "shadow_empty": not out.get("shadow_violations")})


# ---------------------------------------------------------------- V21
# 採用したら執行に入る。門を通って初めて。

def v21():
    reg, cands = _quarantined([DEFECTS[0]])
    before = reg.check(REPLY)
    reg.adopt(cands[0]["name"])
    after = reg.check(REPLY)
    origin_kept = [c.origin for c in reg.covenants]

    ok = (before["verdict"] == "KEPT" and before["in_force"] == 0
          and after["verdict"] == "BROKEN" and after["in_force"] == 1
          and len(after["violations"]) == 1
          and not after.get("shadow_violations")
          and origin_kept == ["regex"])      # 出所は採用後も台帳に残る
    record("V21_adoption_enters_enforcement", ok,
           {"before": [before["verdict"], before["in_force"]],
            "after": [after["verdict"], after["in_force"]],
            "violations_after": [v["forbidden_used"]
                                 for v in after["violations"]],
            "origin_after_adopt": origin_kept})


# ---------------------------------------------------------------- V22
# 登録順を変えても判定不変(adopted 1本 + candidate 2本を 3! 通り)。

def v22():
    import itertools

    rows = [("explicit", ["new"], ""),          # 人が明示 → 執行
            ("cand_a", ["new"], "regex"),       # 規則が読んだ → 隔離席
            ("cand_b", ["helper"], "regex")]
    base = None
    same = True
    for perm in itertools.permutations(rows):
        reg = Register()
        for name, forbids, origin in perm:
            c = Covenant(name=name, quote=name, forbids=list(forbids),
                         origin=origin)
            if origin == "regex":
                reg.propose(c)
            else:
                reg.add(c)
        out = reg.check(REPLY)
        key = (out["verdict"], out["in_force"],
               tuple(sorted((v["covenant"], tuple(v["forbidden_used"]))
                            for v in out["violations"])),
               tuple(sorted((v["covenant"], tuple(v["forbidden_used"]))
                            for v in out.get("shadow_violations", []))))
        if base is None:
            base = key
        elif key != base:
            same = False
    ok = same and base[0] == "BROKEN" and base[1] == 1 and len(base[3]) == 2
    record("V22_order_invariance", ok,
           {"permutations": 6, "identical": same, "verdict": base[0],
            "in_force": base[1],
            "violations": [list(x) for x in base[2]],
            "shadow": [list(x) for x in base[3]]})


# ---------------------------------------------------------------- V23
# 配管の端到端。フックを実プロセスで走らせ、台帳と標準出力を見る。

def v23():
    store = _fresh("hooks")
    cov = store.with_name(store.stem + ".covenants.json")

    _hook("hook_prompt.py", store, {"prompt": DEFECTS[0]})
    ledger = json.loads(cov.read_text(encoding="utf-8"))
    seats = ledger.get("covenants", [])
    statuses = [c.get("status", "adopted") for c in seats]
    adopted_n = statuses.count("adopted")

    stop1 = _hook("hook_stop.py", store, {"last_assistant_message": REPLY})
    blocked_1 = "decision" in stop1
    told = bool(stop1.get("systemMessage"))

    adopt_out = _cli(store, "adopt", {"name": DEFECTS[0]})
    stop2 = _hook("hook_stop.py", store, {"last_assistant_message": REPLY})

    # 戻り止め: 別の配管が set を呼んでも規則由来は隔離席へ
    store2 = _fresh("backstop")
    set_out = _cli(store2, "set", {"name": "x", "quote": "x",
                                   "forbids": ["new"], "origin": "regex"})
    listed = _cli(store2, "list", {})
    backstop_status = [c.get("status", "adopted")
                       for c in listed.get("covenants", [])]
    # 出所の無い set は今まで通り執行に入る(同じ台帳で対照)
    plain_out = _cli(store2, "set", {"name": "y", "quote": "y",
                                     "forbids": ["zzz"]})

    # 推薦は見せるだけ — 実績を積んだ候補で hook_prompt を走らせても
    # 採用はされない(自動採用は「過検出の番人は切られる」の罠そのもの)
    store3 = _fresh("promote")
    reg = Register()
    reg.propose(Covenant(name=DEFECTS[0], quote=DEFECTS[0],
                         forbids=["new"], origin="regex"))
    for t in ["ok", "fine", "done", "sure", "yes", "no", "maybe",
              "later", "a new file", "right"]:
        reg.check(t)
    reg.save(store3.with_name(store3.stem + ".covenants.json"))
    promo_hook = _hook("hook_prompt.py", store3, {"prompt": "続けて"})
    shown = (promo_hook.get("hookSpecificOutput", {})
             .get("additionalContext", ""))
    after_promo = json.loads(
        store3.with_name(store3.stem + ".covenants.json")
        .read_text(encoding="utf-8"))["covenants"]
    promo_statuses = [c.get("status", "adopted") for c in after_promo]

    ok = (len(seats) == 1 and adopted_n == 0
          and statuses == ["candidate"]
          and not blocked_1 and told                 # 遮断せず、知らせた
          and adopt_out.get("verdict") == "ANSWER"
          and stop2.get("decision") == "block"
          and set_out.get("routed_to_quarantine") is True
          and backstop_status == ["candidate"]
          and plain_out.get("covenant") is not None
          and plain_out.get("in_force") == 1
          and DEFECTS[0] in shown and "adopt" in shown
          and promo_statuses == ["candidate"])       # 自動採用はしない
    record("V23_hook_wiring_end_to_end", ok,
           {"after_prompt_hook": {"seats": len(seats),
                                  "statuses": statuses,
                                  "adopted": adopted_n},
            "stop_before_adopt": {"blocked": blocked_1, "told": told,
                                  "message": stop1.get("systemMessage")},
            "stop_after_adopt": {"decision": stop2.get("decision"),
                                 "reason": stop2.get("reason")},
            "backstop_set_with_origin": {
                "routed": set_out.get("routed_to_quarantine"),
                "statuses": backstop_status},
            "plain_set_still_enforces": plain_out.get("in_force"),
            "recommendation": {"shown": shown.strip(),
                               "statuses_after": promo_statuses}})


# ---------------------------------------------------------------- V24
# 回帰。既存4本と fork 全部が緑のまま。

def v24():
    scripts = {"run_confirm.py": "7/7", "run_confirm2.py": "5/5",
               "run_confirm3.py": "5/5", "run_confirm_lang.py": "3/3"}
    got = {}
    for s, expect in scripts.items():
        r = subprocess.run([sys.executable, str(Path(__file__).with_name(s))],
                           capture_output=True, text=True, timeout=900,
                           cwd=str(ROOT))
        j = Path(__file__).with_name(
            "results_" + s[len("run_"):].replace(".py", ".json"))
        try:
            # summary は "7/7 passed" — 比較は分数だけで行う
            got[s] = json.loads(
                j.read_text(encoding="utf-8"))["summary"].split()[0]
        except Exception:
            got[s] = f"_no_result_file ({r.returncode})"

    r = subprocess.run(
        [sys.executable, "-c",
         "from verantyx.cross_geometry_forks import all_cross_geometry_forks "
         "as f; import json; rs=f(); "
         "print(json.dumps({'n': len(rs), 'pass': sum(1 for x in rs "
         "if x['pass']), 'failed': [x['fork'] for x in rs "
         "if not x['pass']]}))"],
        capture_output=True, text=True, timeout=1800, cwd=str(ROOT))
    forks = json.loads(r.stdout.strip().splitlines()[-1])

    ok = (got == scripts and forks["pass"] == forks["n"]
          and forks["n"] == 89)
    record("V24_regression_all_green", ok,
           {"scripts": got, "expected": scripts,
            "forks": f"{forks['pass']}/{forks['n']}",
            "failed_forks": forks["failed"]})


if __name__ == "__main__":
    for f in (v19, v20, v21, v22, v23, v24):
        f()
    n = len(RESULTS["checks"])
    passed = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{passed}/{n} passed"
    out = Path(__file__).with_name("results_confirm4.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
