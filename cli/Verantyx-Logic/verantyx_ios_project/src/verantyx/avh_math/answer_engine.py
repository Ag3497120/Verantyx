# avh_math/answer_engine.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict
import os

from avh_math.report_builder import ReportBuilder

@dataclass
class Budgets:
    time_ms: int = 120_000
    max_worlds: int = 4
    max_depth: int = 5
    max_steps: int = 20_000

class AnswerEngine:
    def __init__(self, kb_path: str, budgets: Budgets | None = None):
        self.kb_path = kb_path
        self.budgets = budgets or Budgets()
        self.builder = ReportBuilder(
            kb_path=kb_path,
            budgets={
                "time_ms": self.budgets.time_ms,
                "max_worlds": self.budgets.max_worlds,
                "max_depth": self.budgets.max_depth,
                "max_steps": self.budgets.max_steps,
            }
        )

    def solve(self, query: str) -> Dict[str, Any]:
        return self.builder.build(query)
