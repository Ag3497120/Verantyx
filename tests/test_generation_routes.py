#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the explicit model-free/model-assisted route boundary."""
from __future__ import annotations

import copy
import unittest

from photoloset.generation_routes import (
    ANSWER,
    CONTESTED,
    CONVERGED,
    ESCALATE_HUMAN,
    ConvergenceBudget,
    Dependency,
    RoutePlanner,
    STAGE_DEFINITIONS,
    Stage,
)


def complete_callbacks(iteration=None):
    callbacks = {
        Stage.IMAGE_EVIDENCE: lambda ctx: {
            "verdict": ANSWER, "pixels": ctx["evidence"]["image"],
            "kind": "OBSERVED"},
        Stage.GEOMETRIC_CONSTRUCTION: lambda ctx: {
            "verdict": ANSWER, "mesh": "triangles"},
        Stage.MATERIAL_SIMULATION: lambda ctx: {
            "verdict": ANSWER, "strain": 0.02},
        Stage.HUMAN_REVIEW: lambda ctx: {
            "verdict": ANSWER, "approved_by": "tester"},
    }
    if iteration is not None:
        callbacks[Stage.AGENT_ITERATION] = iteration
    corpus = {Stage.SEAM_KNOWLEDGE: lambda ctx: {
        "verdict": ANSWER, "matches": ["set-in sleeve"]}}
    return callbacks, corpus


class GenerationRouteTests(unittest.TestCase):
    def test_stage_order_and_dependency_classification_are_explicit(self):
        self.assertEqual([item.stage for item in STAGE_DEFINITIONS], [
            Stage.IMAGE_EVIDENCE, Stage.GEOMETRIC_CONSTRUCTION,
            Stage.MATERIAL_SIMULATION, Stage.SEAM_KNOWLEDGE,
            Stage.HUMAN_REVIEW, Stage.AGENT_ITERATION])
        classified = {item.stage: item.dependency
                      for item in STAGE_DEFINITIONS}
        self.assertEqual(classified[Stage.SEAM_KNOWLEDGE],
                         Dependency.REQUIRES_EXTERNAL_CORPUS)
        self.assertEqual(classified[Stage.AGENT_ITERATION],
                         Dependency.OPTIONAL_MODEL)
        self.assertEqual(classified[Stage.GEOMETRIC_CONSTRUCTION],
                         Dependency.DETERMINISTIC)

    def test_model_free_route_executes_deterministic_callbacks(self):
        calls = []
        callbacks, corpus = complete_callbacks()
        for stage, callback in list(callbacks.items()):
            def record(ctx, stage=stage, callback=callback):
                calls.append(stage)
                return callback(ctx)
            callbacks[stage] = record

        result = RoutePlanner(callbacks, corpus_callbacks=corpus).run(
            {"image": "front.png"})
        self.assertEqual(result["terminal_verdict"], CONVERGED)
        self.assertFalse(result["model_used"])
        self.assertEqual(result["proposals"], [])
        self.assertEqual(calls, [Stage.IMAGE_EVIDENCE,
                                Stage.GEOMETRIC_CONSTRUCTION,
                                Stage.MATERIAL_SIMULATION,
                                Stage.HUMAN_REVIEW])
        self.assertIn(Stage.SEAM_KNOWLEDGE.value, result["artifacts"])

    def test_missing_corpus_is_an_explicit_terminal_blocker(self):
        callbacks, _ = complete_callbacks()
        result = RoutePlanner(callbacks).run({"image": "front.png"})
        self.assertEqual(result["terminal_verdict"], ESCALATE_HUMAN)
        self.assertIn({"stage": Stage.SEAM_KNOWLEDGE.value,
                       "reason": "BLOCKED_EXTERNAL_CORPUS"},
                      result["blockers"])
        self.assertEqual(result["trace"][-1]["status"], "NOT_RUN_BLOCKED")

    def test_model_can_only_add_sanitised_proposals(self):
        callbacks, corpus = complete_callbacks()
        evidence = {"image": "front.png", "waist_cm": 72.0}
        before = copy.deepcopy(evidence)

        def model(stage, context):
            context["evidence"]["waist_cm"] = 1.0
            return {"evidence": {"waist_cm": 1.0}, "kind": "OBSERVED",
                    "nested": {"state": "OBSERVED"},
                    "choice": "invented back panel"}

        result = RoutePlanner(callbacks, corpus_callbacks=corpus,
                              model_proposer=model).run(evidence,
                                                        use_model=True)
        self.assertEqual(evidence, before)
        self.assertEqual(result["evidence"], before)
        self.assertEqual(result["proposals"][0]["kind"], "PROPOSED")
        alternative = result["proposals"][0]["alternatives"]
        self.assertNotIn("evidence", alternative)
        self.assertIn("claimed_evidence", alternative)
        self.assertEqual(alternative["kind"], "PROPOSED")
        self.assertEqual(alternative["nested"]["state"], "PROPOSED")
        self.assertNotIn("agent iteration", result["artifacts"])

    def test_stagnation_closes_the_loop_and_escalates(self):
        def unchanged(ctx):
            return {"verdict": "CONTINUE", "state": {"fit_error": 4.2}}

        callbacks, corpus = complete_callbacks(unchanged)
        planner = RoutePlanner(
            callbacks, corpus_callbacks=corpus,
            budget=ConvergenceBudget(max_iterations=10,
                                     stagnation_limit=3,
                                     max_model_proposals=10))
        result = planner.run({"image": "front.png"})
        self.assertEqual(result["terminal_verdict"], ESCALATE_HUMAN)
        iterations = [row for row in result["trace"]
                      if row.get("iteration")]
        self.assertEqual(len(iterations), 3)
        self.assertIn("Vera closed the loop", result["why"])

    def test_iteration_budget_is_a_hard_terminal_limit(self):
        counter = {"n": 0}

        def moving(ctx):
            counter["n"] += 1
            return {"verdict": "CONTINUE", "state": {"n": counter["n"]}}

        callbacks, corpus = complete_callbacks(moving)
        result = RoutePlanner(
            callbacks, corpus_callbacks=corpus,
            budget=ConvergenceBudget(max_iterations=2,
                                     stagnation_limit=3,
                                     max_model_proposals=3)).run(
                                         {"image": "front.png"})
        self.assertEqual(result["terminal_verdict"], ESCALATE_HUMAN)
        self.assertIn("iteration budget 2 exhausted", result["why"])

    def test_contested_iteration_is_terminal(self):
        callbacks, corpus = complete_callbacks(
            lambda ctx: {"verdict": CONTESTED,
                         "why": "front and back constraints disagree"})
        result = RoutePlanner(callbacks, corpus_callbacks=corpus).run(
            {"image": "front.png"})
        self.assertEqual(result["terminal_verdict"], CONTESTED)
        self.assertIn("front and back", result["why"])

    def test_dependency_report_compares_same_deterministic_route(self):
        callbacks, corpus = complete_callbacks()
        planner = RoutePlanner(
            callbacks, corpus_callbacks=corpus,
            model_proposer=lambda stage, ctx: ["back A", "back B"])
        report = planner.dependency_report({"image": "front.png"})
        comparison = report["comparison"]
        self.assertTrue(comparison["same_evidence"])
        self.assertTrue(comparison["same_deterministic_artifacts"])
        self.assertEqual(comparison["dependency_difference"], "proposals only")
        self.assertEqual(comparison["assisted_proposal_count"], 1)
        self.assertEqual(report["model_free"]["proposals"], [])
        self.assertFalse(any(stage["model_can_promote_evidence"]
                             for stage in report["stages"]))

    def test_invalid_budgets_and_callback_results_fail_closed(self):
        with self.assertRaises(ValueError):
            ConvergenceBudget(max_iterations=0)
        callbacks, corpus = complete_callbacks()
        callbacks[Stage.GEOMETRIC_CONSTRUCTION] = lambda ctx: "not a mapping"
        with self.assertRaises(TypeError):
            RoutePlanner(callbacks, corpus_callbacks=corpus).run(
                {"image": "front.png"})


if __name__ == "__main__":
    unittest.main()
