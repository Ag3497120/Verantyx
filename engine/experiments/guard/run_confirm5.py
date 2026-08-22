# -*- coding: utf-8 -*-
"""凍結の確認測定 — PREREG5_FREEZE.md の V25〜V27。

提出に向けて要るのは新機能ではなく、**他人のマシンで保証が今この場で
成り立つことを示せる**こと。だから測るのは doctor が正直かどうか
(通るだけの自己検査は自己申告と同じ)。数値は実行結果のみ。
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from verantyx.covenant import Covenant, Register, self_check  # noqa: E402

RESULTS = {"prereg": "experiments/guard/PREREG5_FREEZE.md", "checks": {}}


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


# ---------------------------------------------------------------- V25
# 壊した台帳で BROKEN を返すか。嘘をつく自己検査は無いより悪いので、
# 保証ごとに「その保証だけを壊した台帳」を作って名指しできるか測る。

def v25():
    class SilentGuard(Register):
        """何も捕まえない番人(G1が壊れた状態)。"""
        def check(self, text, asked="", store=None):
            return {"verdict": "KEPT", "in_force": 0, "violations": []}

    class EagerGuard(Register):
        """候補をいきなり執行に入れる番人(G2が壊れた状態)。"""
        def propose(self, c):
            c.status = "adopted"
            return self.add(c)

    class DeletingGuard(Register):
        """退役を削除として実装した番人(G4が壊れた状態)。"""
        def retire(self, name, quote="", turn=-1):
            for i, c in enumerate(self.covenants):
                if c.name == name:
                    self.covenants.pop(i)
                    return {"name": name}
            return None

    healthy = self_check()
    silent = self_check(register_cls=SilentGuard)
    eager = self_check(register_cls=EagerGuard)
    deleting = self_check(register_cls=DeletingGuard)

    ok = (healthy["verdict"] == "OK"
          and silent["verdict"] == "BROKEN"
          and "G1_registered_covenant_blocks" in silent["failed"]
          and eager["verdict"] == "BROKEN"
          and "G2_regex_read_never_blocks" in eager["failed"]
          and deleting["verdict"] == "BROKEN"
          and "G4_retire_is_an_entry_not_a_deletion" in deleting["failed"]
          # 壊していない保証まで巻き添えで落ちていないか(名指しの精度)
          and "G3_deterministic_order_invariant" not in deleting["failed"])
    record("V25_doctor_reports_broken_when_broken", ok,
           {"healthy": healthy["verdict"],
            "silent_guard": [silent["verdict"], silent["failed"]],
            "eager_guard": [eager["verdict"], eager["failed"]],
            "deleting_guard": [deleting["verdict"], deleting["failed"]]})


# ---------------------------------------------------------------- V26
# doctor は利用者の台帳を変更しない(導入直後に安心して叩けること)。

def v26():
    tmp = Path(tempfile.mkdtemp())
    store = tmp / "vera_store.json"
    sidecar = store.with_name(store.stem + ".covenants.json")

    def run(op, payload):
        return subprocess.run(
            [sys.executable, "-m", "verantyx.cli", "--store", str(store),
             "guard", op],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True, text=True, cwd=str(ROOT), timeout=300)

    run("set", {"name": "no-emoji", "quote": "絵文字を使わないで",
                "forbids": ["絵文字"]})
    before = hashlib.sha256(sidecar.read_bytes()).hexdigest()
    r = run("doctor", {})
    after = hashlib.sha256(sidecar.read_bytes()).hexdigest()
    out = json.loads(r.stdout)

    # 台帳がまだ無いマシン(導入直後)でも動くこと
    tmp2 = Path(tempfile.mkdtemp())
    r2 = subprocess.run(
        [sys.executable, "-m", "verantyx.cli", "--store",
         str(tmp2 / "vera_store.json"), "guard", "doctor"],
        input="{}", capture_output=True, text=True, cwd=str(ROOT),
        timeout=300)
    fresh = json.loads(r2.stdout)

    ok = (before == after and out["verdict"] == "OK"
          and out["environment"]["covenants_in_force"] == 1
          and fresh["verdict"] == "OK"
          and fresh["environment"]["ledger_exists"] is False
          and r.returncode == 0 and r2.returncode == 0)
    record("V26_doctor_never_touches_the_ledger", ok,
           {"sha_unchanged": before == after,
            "verdict_with_ledger": out["verdict"],
            "in_force_seen": out["environment"]["covenants_in_force"],
            "verdict_fresh_machine": fresh["verdict"],
            "exit_codes": [r.returncode, r2.returncode]})


# ---------------------------------------------------------------- V27
# 証拠の一括再現が「赤いものを緑と言わない」こと。落ちる治具を差し込み、
# 終了コード1と名指しが出ることを測る(合計だけ出す要約は証拠を隠す)。

def v27():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "verify_all", Path(__file__).with_name("verify_all.py"))
    va = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(va)

    tmp = Path(tempfile.mkdtemp())
    failing = tmp / "run_fake_failing.py"
    failing.write_text(
        "print('[FAIL] deliberately_failing_check: {}')\n"
        "print('1/2 passed')\n", encoding="utf-8")
    passing = tmp / "run_fake_passing.py"
    passing.write_text("print('2/2 passed')\n", encoding="utf-8")

    va.HERE = tmp
    va.CONFIRMATIONS = ["run_fake_passing.py"]
    rc_green = va.main()
    green = json.loads((tmp / "verify_all_result.json").read_text())

    va.CONFIRMATIONS = ["run_fake_passing.py", "run_fake_failing.py"]
    rc_red = va.main()
    red = json.loads((tmp / "verify_all_result.json").read_text())

    ok = (rc_green == 0 and green["all_green"] is True
          and rc_red == 1 and red["all_green"] is False
          and any("deliberately_failing_check" in f
                  for f in red["failures"])
          and red["measurements"] == "3/4")
    record("V27_verification_does_not_call_red_green", ok,
           {"green_run": [rc_green, green["measurements"]],
            "red_run": [rc_red, red["measurements"]],
            "named_failure": red["failures"][:1]})


if __name__ == "__main__":
    for f in (v25, v26, v27):
        f()
    n = len(RESULTS["checks"])
    passed = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{passed}/{n} passed"
    out = Path(__file__).with_name("results_confirm5.json")
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out}")
