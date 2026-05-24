from __future__ import annotations

from typing import Any, Dict, List

from avh_math.puzzle.shape_graph import build_shape_graph
from avh_math.puzzle.assembler import assemble_and_solve


class PuzzleMathEngine:
    def solve(self, text: str) -> Dict[str, Any]:
        g = build_shape_graph(text)
        if any("broken_arrow_detected" in n for n in g.notes):
            return {
                "status": "unsupported",
                "answer_text": "式が壊れています（矢印の右辺が欠損）。\"A -> B\" の形で入力してください。",
                "evidence": {"parse_notes": g.notes, "core_formula": g.core_formula},
                "payload": {"decomp": g.__dict__},
                "next_actions": ["式を \"...\" で囲い、-> の右側が必ずあることを確認してください。"],
            }

        out = assemble_and_solve(g)
        return {
            "status": out.status,
            "answer_text": out.answer_text,
            "evidence": out.evidence,
            "payload": {"decomp": out.decomp},
            "next_actions": self._next(out.status),
        }

    def _next(self, status: str) -> List[str]:
        if status == "proved":
            return ["Proof Libraryへ保存"]
        if status == "disproved":
            return ["反例として登録", "Assumptionを変更して再試行"]
        if status == "likely_true":
            return ["探索範囲(max_worlds)を増やす", "仮定(reflexive/transitive等)を明示"]
        return ["入力ルールを確認", "式を\"...\"で囲う"]
