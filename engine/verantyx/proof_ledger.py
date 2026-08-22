"""証明の台帳 — 補題・試行・未証明目標を、器官に永続で刻む。

cross_energy_prover(2026-08-20)は補題の発明まで動いたが、発明した補題も
失敗した目標も実験JSONにしか残らず、エンジンの記憶のどこにも刻まれて
いなかった — このセッション自身が「実装済み未到達」をやった形。この
モジュールがその配線で、**MCPを経由しない**(扉は薄い束縛であって器官の
唯一の写しではない、という mathlib_witness と同じ線)。

三つの記憶、それぞれ既存の型に載せる:

  補題       証人つきの行(lean の verdict と tactic を named witness として
             持つ — mathlib 証人と同じ「検証済:lean4」の座席。votes 無し)
  試行台帳   (lhs, rhs) → proved/failed。プロセスを跨いで
             「二度目は探索でなく参照」を成立させる
  未証明目標  gap_graph.GapNode(既存器官)。failure_type が敗因を、
             acquisition_methods が「何が届けば閉じるか」を運ぶ

票は一切持たない。連邦には入れない。読む者は台帳を検査できる。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .gap_graph import GapGraph, gap_graph_path
from .paths import corpus_root


def default_path() -> Path:
    return corpus_root() / "build" / "proof_ledger.json"


class ProofLedger:
    """証明活動の永続記憶。ファイル一つ + gap 台帳一つ。"""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else default_path()
        self.gap_path = self.path.with_name(self.path.stem + ".gaps.json")
        self.lemmas: List[Dict[str, Any]] = []
        self.trials: Dict[str, str] = {}
        if self.path.exists():
            d = json.loads(self.path.read_text(encoding="utf-8"))
            self.lemmas = d.get("lemmas", [])
            self.trials = d.get("trials", {})
        self.gaps = (GapGraph.load(self.gap_path) if self.gap_path.exists()
                     else GapGraph())

    # -- 補題(証人つき) ----------------------------------------------------
    def add_lemma(self, lhs: str, rhs: str, *, how: str, origin_goal: str,
                  ground_passed: int, lean_verdict: Optional[str] = None,
                  lean_tactic: Optional[str] = None,
                  cited: Optional[List[str]] = None) -> Dict[str, Any]:
        for row in self.lemmas:
            if row["lhs"] == lhs and row["rhs"] == rhs:
                if lean_verdict and not row.get("lean_verdict"):
                    row["lean_verdict"] = lean_verdict
                    row["lean_tactic"] = lean_tactic
                return row
        row = {"lhs": lhs, "rhs": rhs, "how": how,
               "origin_goal": origin_goal, "ground_passed": ground_passed,
               "lean_verdict": lean_verdict, "lean_tactic": lean_tactic,
               "ts": time.time()}
        if cited:
            # mathlib 由来の引用 — 参照が発明に先行した証拠を台帳に残す
            row["cited"] = list(cited)
        self.lemmas.append(row)
        return row

    # -- 試行台帳 ------------------------------------------------------------
    def trial_key(self, lhs: str, rhs: str) -> str:
        return f"{lhs} = {rhs}"

    def record_trial(self, lhs: str, rhs: str, status: str) -> None:
        # proved は failed を上書きしてよい(後に届いた)。逆は上書きしない。
        k = self.trial_key(lhs, rhs)
        if self.trials.get(k) != "proved":
            self.trials[k] = status

    def known(self, lhs: str, rhs: str) -> Optional[str]:
        return self.trials.get(self.trial_key(lhs, rhs))

    # -- 未証明目標(gap 台帳) ------------------------------------------------
    def open_goal(self, name: str, lhs: str, rhs: str, *,
                  failure_type: str, needs: List[str]) -> str:
        node = self.gaps.create(
            gap_type="UNPROVED_GOAL",
            subject=f"{lhs} = {rhs}",
            scope=f"math:goal:{name}",
            severity="QUALITY",
            failure_type=failure_type,
            acquisition_methods=list(needs),
            required_for=["math_track"],
        )
        return node.gap_id

    def close_goal(self, name: str, lhs: str, rhs: str, *, how: str) -> None:
        node = self.gaps.find_by_scope_subject(f"math:goal:{name}",
                                               f"{lhs} = {rhs}")
        if node is not None and node.status != "RESOLVED":
            self.gaps.set_status(node.gap_id, "RESOLVED", resolution=how)

    # -- 永続化 ---------------------------------------------------------------
    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(
            {"votes": "none", "note": "proof lemmas + trials; not federation",
             "lemmas": self.lemmas, "trials": self.trials},
            ensure_ascii=False, indent=1), encoding="utf-8")
        self.gaps.save(self.gap_path)

    def summary(self) -> Dict[str, Any]:
        open_goals = [n for n in self.gaps.nodes.values()
                      if n.status != "RESOLVED"]
        return {"lemmas": len(self.lemmas),
                "lemmas_lean_verified": sum(
                    1 for x in self.lemmas
                    if x.get("lean_verdict") == "VERIFIED"),
                "trials": len(self.trials),
                "open_goals": len(open_goals),
                "resolved_goals": sum(
                    1 for n in self.gaps.nodes.values()
                    if n.status == "RESOLVED")}
