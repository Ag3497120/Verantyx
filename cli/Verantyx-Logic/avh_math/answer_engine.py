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

    def solve_stream(self, query: str):
        yield "Thinking: Analyzing logical structure..."
        yield "Thinking: Detecting domain and assumptions..."
        
        # Actual processing
        yield "Thinking: Searching knowledge base for relevant axioms..."
        
        try:
            # ReportBuilder.build is the core logic
            # We wrap it to track start
            yield "Thinking: Running formal solver (Kripke/Truth-Table)..."
            result = self.builder.build(query)
            
            yield "Thinking: Finalizing proof trace..."
            yield result
        except Exception as e:
            import traceback
            err = traceback.format_exc()
            yield f"Error during reasoning: {str(e)}\n{err}"
