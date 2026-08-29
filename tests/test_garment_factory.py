#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression contract for the integrated garment-factory loop.

The factory is an orchestration boundary over existing retrieval hypotheses,
digest-bound candidate approval, generation jobs, and deterministic runners.
These tests intentionally leave artifact placement flexible (top-level or
inside ``artifacts``), while fixing the authority rules that must not drift.

Event vocabulary reused from the factory implementation:

``CONFIRM_IMAGE``
    Records immutable image/view evidence.
``SUBMIT_RETRIEVAL``
    Adds retrieval alternatives.  Every result remains ``PROPOSED``.
``SUBMIT_HYPOTHESES``
    Adds inspectable geometry alternatives; front-only evidence requires two
    distinct named back candidates.
``APPROVE_HYPOTHESIS``
    Requires a named human and the exact candidate digest.
``REJECT_HYPOTHESIS`` / ``UNDO_HYPOTHESIS_DECISION``
    Keep candidate decisions digest-bound, append-only, and reversible before
    another exact candidate is approved.
``GENERATE_PATTERN`` / ``REPAIR_PATTERN`` / ``SIMULATE``
    May call deterministic runners only after the required approvals.
``SUBMIT_SEWING_METHODS``
    May not attach sewing candidates before shape approval and pattern output.
``USE_PROCEDURAL_SEWING_PLAN``
    May continue from approved pattern topology without claiming corpus evidence.
"""
from __future__ import annotations

import copy
import unittest

from photoloset import garment_factory


def _artifact(state, name):
    """Read one public artifact without prescribing state layout details."""
    artifacts = state.get("artifacts", {})
    if isinstance(artifacts, dict) and name in artifacts:
        return artifacts[name]
    if name == "search_results":
        return [hit for batch in state.get("retrieval_batches", [])
                for hit in batch.get("hits", [])]
    if name in {"back_candidates", "structure_candidates"}:
        sheet = state.get("hypothesis_sheet")
        return sheet.get("candidates") if isinstance(sheet, dict) else None
    if name == "structure_approval":
        return state.get("shape_approval")
    return state.get(name)


def _rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        for key in ("candidates", "results", "proposals", "items"):
            if isinstance(value.get(key), (list, tuple)):
                return list(value[key])
    return []


def _step(state, event, **runners):
    response = garment_factory.advance(state, event, **runners)
    testcase_state = response.get("state")
    if not isinstance(testcase_state, dict):
        raise AssertionError("advance must return a persistable state mapping")
    return testcase_state, response


def _candidate_digest(candidate):
    for key in ("digest", "geometry_digest", "candidate_digest"):
        value = candidate.get(key)
        if isinstance(value, str) and value:
            return value
    raise AssertionError("factory candidate must expose a digest for approval")


def _candidate_id(candidate):
    for key in ("candidate_id", "hypothesis_id", "id"):
        value = candidate.get(key)
        if isinstance(value, str) and value:
            return value
    raise AssertionError("factory candidate must expose a stable id")


def _assert_no_authoritative_llm_claim(testcase, value, path="proposal"):
    """Reject ANSWER/OBSERVED in authoritative state fields recursively.

    Original model wording may be retained under an explicitly ``claimed_*``
    field for audit, but it cannot occupy ``verdict``, ``state``, or ``kind``.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            location = f"{path}.{key}"
            if key in {"verdict", "state", "kind"}:
                testcase.assertNotEqual(item, "ANSWER", location)
                testcase.assertNotEqual(item, "OBSERVED", location)
            if not key.startswith("claimed_"):
                _assert_no_authoritative_llm_claim(testcase, item, location)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_no_authoritative_llm_claim(testcase, item,
                                                f"{path}[{index}]")


def _image_event():
    return {
        "type": "CONFIRM_IMAGE",
        "outline": {"verdict": "ANSWER", "digest": "sha256:outline",
                    "outline": [[0, 0], [10, 0], [10, 20], [0, 20]]},
        "regions": [{"region_id": "r-bodice", "part_id": "bodice"}],
        "source": {"image_digest": "sha256:front-image", "frame_id": "front"},
        "front_only": True,
    }


def _search_event():
    # Deliberately hostile authority labels: the factory must overwrite them,
    # not trust a retrieval adapter's or model's vocabulary.
    return {
        "type": "SUBMIT_RETRIEVAL",
        "source": {"name": "fixture:visual-search", "modality": "region_embedding",
                   "license": "fixture permissive", "lineage": ["fixture-root"],
                   "rights": {"commercial": True, "derivatives": True}},
        "hits": [
            {"part_id": "bodice", "region_id": "r-bodice",
             "reference": "look-a", "score": 0.94, "state": "ANSWER",
             "kind": "OBSERVED", "visual_cues": {"neck": "high"}},
            {"part_id": "bodice", "region_id": "r-bodice",
             "reference": "look-b", "score": 0.87, "verdict": "ANSWER",
             "state": "OBSERVED", "visual_cues": {"hem": "flared"}},
        ],
    }


def _back_candidates(count=2):
    def structure(back):
        return {"schema": "garment.structure.v1", "nodes": [{
            "node_id": "shell-"+back, "kind": "BODY_SHELL",
            "dimensions": {"height_cm": 90.0, "circumference_cm": 96.0},
            "attributes": {"back_design": back},
        }], "operations": []}

    rows = [
        {"candidate_id": "zipper-back",
         "back_design": "zipper-back",
         "structure": structure("zipper-back"),
         "assumptions": ["the back is not visible"]},
        {"candidate_id": "cape-back",
         "back_design": "cape-back",
         "structure": structure("cape-back"),
         "assumptions": ["the back is not visible"]},
    ]
    return rows[:count]


def _structure_event(count=2):
    return {"type": "SUBMIT_HYPOTHESES", "front_only": True,
            "hypotheses": _back_candidates(count)}


def _front_job(candidate_count=2):
    state = garment_factory.new_job("factory-regression", max_iterations=8)
    state, _ = _step(state, _image_event())
    state, _ = _step(state, _search_event())
    return _step(state, _structure_event(candidate_count))


class RunnerSpies:
    def __init__(self):
        self.calls = {"pattern": [], "repair": [], "simulation": []}

    def pattern(self, state, event):
        self.calls["pattern"].append(copy.deepcopy({"state": state, "event": event}))
        return {"verdict": "ANSWER", "pattern": {"pieces": ["front", "back"]}}

    def repair(self, state, event):
        self.calls["repair"].append(copy.deepcopy({"state": state, "event": event}))
        return {"verdict": "ANSWER", "sewable": True,
                "repair": {"steps": ["join side seams"]}}

    def simulation(self, state, event):
        self.calls["simulation"].append(copy.deepcopy({"state": state, "event": event}))
        return {"verdict": "ANSWER", "simulation": {"stable": True}}

    def kwargs(self):
        return {"pattern_runner": self.pattern,
                "repair_runner": self.repair,
                "simulation_runner": self.simulation}


class GarmentFactoryRegressionTests(unittest.TestCase):
    def test_nested_construction_claim_and_non_finite_score_are_rejected(self):
        state, _ = _step(garment_factory.new_job("bad-search"), _image_event())
        nested = _search_event()
        nested["hits"][0]["visual_cues"]["details"] = {
            "seams": ["invented by embedding"]}
        unchanged, refused = _step(state, nested)
        self.assertEqual(refused["verdict"],
                         "UNKNOWN_RETRIEVAL_CONSTRUCTION_CLAIM")
        self.assertEqual(_artifact(unchanged, "search_results"), [])

        non_finite = _search_event()
        non_finite["hits"][0]["score"] = float("nan")
        unchanged, refused = _step(state, non_finite)
        self.assertEqual(refused["verdict"], "UNKNOWN_RETRIEVAL_HIT")
        self.assertEqual(_artifact(unchanged, "search_results"), [])

    def test_search_results_are_always_proposed(self):
        original = garment_factory.new_job("search-proposals")
        state, _ = _step(original, _image_event())
        state, response = _step(state, _search_event())
        self.assertEqual(response["verdict"], "ANSWER")
        rows = _rows(_artifact(state, "search_results"))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row.get("state") == "PROPOSED" for row in rows))
        self.assertTrue(all(row.get("verdict", "PROPOSED") == "PROPOSED"
                            for row in rows))
        self.assertTrue(all(row.get("kind", "PROPOSED") != "OBSERVED"
                            for row in rows))
        # Functional API: no call mutates its input state or event.
        self.assertEqual(_artifact(original, "search_results"), [])

    def test_front_only_requires_two_distinct_back_candidates(self):
        refused, refusal = _front_job(candidate_count=1)
        self.assertTrue(str(refusal["verdict"]).startswith("UNKNOWN_"))
        self.assertIsNone(_artifact(refused, "structure_approval"))

        accepted, accepted_result = _front_job(candidate_count=2)
        self.assertEqual(accepted_result["verdict"], "PROPOSED")
        candidates = _rows(_artifact(accepted, "back_candidates") or
                           _artifact(accepted, "structure_candidates"))
        self.assertEqual(len(candidates), 2)
        self.assertEqual(len({_candidate_id(row) for row in candidates}), 2)
        self.assertTrue(all(row.get("state") == "PROPOSED"
                            for row in candidates))
        self.assertTrue(all(row.get("front_only", True) is True
                            for row in candidates))

    def test_reject_then_approve_another_candidate_is_deterministic(self):
        state, _ = _front_job()
        first, second = state["hypothesis_sheet"]["candidates"]
        rejection_event = {
            "type": "REJECT_HYPOTHESIS",
            "candidate_id": first["candidate_id"],
            "digest": first["digest"],
            "by": "Mina",
            "reason": "the inferred back is not the intended design",
        }

        rejected, result = _step(state, rejection_event)

        self.assertEqual(result["verdict"], "REJECTED")
        self.assertEqual(rejected["phase"], "BACK_CANDIDATES_READY")
        self.assertIsNone(rejected["shape_approval"])
        self.assertEqual(result["rejection"]["candidate_id"],
                         first["candidate_id"])
        self.assertEqual(result["rejection"]["candidate_digest"],
                         first["digest"])
        self.assertEqual(result["rejection"]["by"], "Mina")

        # An exact UI re-delivery does not append another decision/event.
        event_count = len(rejected["events"])
        decision_count = len(rejected["shape_decisions"])
        repeated, repeated_result = _step(rejected, rejection_event)
        self.assertEqual(repeated_result["verdict"], "REJECTED")
        self.assertTrue(repeated_result["idempotent"])
        self.assertEqual(len(repeated["events"]), event_count)
        self.assertEqual(len(repeated["shape_decisions"]), decision_count)

        # Rejection is active until explicitly undone, so the rejected digest
        # cannot accidentally cross the runner gate.
        _, blocked = _step(rejected, {
            "type": "APPROVE_HYPOTHESIS",
            "candidate_id": first["candidate_id"],
            "digest": first["digest"], "by": "Mina"})
        self.assertEqual(blocked["verdict"], "UNKNOWN_CANDIDATE_REJECTED")

        approved, approval = _step(rejected, {
            "type": "APPROVE_HYPOTHESIS",
            "candidate_id": second["candidate_id"],
            "digest": second["digest"], "by": "Mina"})
        self.assertEqual(approval["verdict"], "APPROVED")
        self.assertEqual(approved["shape_approval"]["candidate_id"],
                         second["candidate_id"])
        self.assertEqual(approved["shape_approval"]["candidate_digest"],
                         second["digest"])

        spies = RunnerSpies()
        patterned, pattern_result = _step(
            approved, {"type": "GENERATE_PATTERN"}, **spies.kwargs())
        self.assertEqual(pattern_result["verdict"], "ANSWER")
        self.assertEqual(patterned["phase"], "PATTERN_READY")
        self.assertEqual(spies.calls["pattern"][0]["state"]
                         ["shape_approval"]["candidate_id"],
                         second["candidate_id"])

    def test_pattern_records_exact_cad_revision_without_claiming_inverse(self):
        state, _ = _front_job()
        selected = state["hypothesis_sheet"]["candidates"][0]
        approved, _ = _step(state, {
            "type": "APPROVE_HYPOTHESIS",
            "candidate_id": selected["candidate_id"],
            "digest": selected["digest"],
            "by": "Mina",
        })
        approved["foreground_cleanup"] = {
            "state": "APPROVED",
            "authority": "HUMAN_APPROVED_FOR_FRONT_COMPARISON",
            "target_digest": "sha256:cad-target-r7",
            "target_revision": 7,
            "cleanup_digest": "sha256:cleanup-r7",
            "supersedes_cleanup_digest": "sha256:cleanup-r6",
            "audit_digest": "sha256:front-audit",
        }
        approved["front_compilation"] = {
            "compiled_front_digest": "sha256:compiled-front-r7",
        }

        patterned, result = _step(
            approved, {"type": "GENERATE_PATTERN"},
            **RunnerSpies().kwargs())

        self.assertEqual(result["verdict"], "ANSWER")
        binding = patterned["pattern"]["cad_target_iteration"]
        self.assertEqual(binding["target_revision"], 7)
        self.assertEqual(binding["target_digest"],
                         "sha256:cad-target-r7")
        self.assertEqual(binding["front_compilation_digest"],
                         "sha256:compiled-front-r7")
        self.assertFalse(binding["target_geometry_compiled_into_pattern"])
        self.assertEqual(binding["inverse_flattening"]["verdict"],
                         "UNKNOWN_NOT_PROVEN")
        self.assertFalse(binding["inverse_flattening"]
                         ["manufacturing_certified"])
        self.assertTrue(binding["binding_digest"])

    def test_undo_approval_then_reapprove_is_append_only_and_idempotent(self):
        state, _ = _front_job()
        selected = state["hypothesis_sheet"]["candidates"][0]
        approved, first_approval = _step(state, {
            "type": "APPROVE_HYPOTHESIS",
            "candidate_id": selected["candidate_id"],
            "digest": selected["digest"], "by": "Mina"})
        self.assertEqual(first_approval["verdict"], "APPROVED")
        first_approval_id = approved["shape_approval"]["approval_id"]
        first_decision_id = approved["shape_decisions"][-1]["decision_id"]

        spies = RunnerSpies()
        patterned, pattern_result = _step(
            approved, {"type": "GENERATE_PATTERN"}, **spies.kwargs())
        self.assertEqual(pattern_result["verdict"], "ANSWER")
        self.assertIsNotNone(patterned["pattern"])

        undo_event = {
            "type": "UNDO_HYPOTHESIS_DECISION",
            "command_id": "undo-shape-1",
            "by": "Mina",
        }
        undone, undo_result = _step(patterned, undo_event)

        self.assertEqual(undo_result["verdict"], "ANSWER")
        self.assertEqual(undo_result["undone_decision_id"], first_decision_id)
        self.assertIsNone(undone["shape_approval"])
        self.assertIsNone(undone["pattern"])
        self.assertIsNone(undone["repair"])
        self.assertIsNone(undone["simulation"])
        self.assertEqual(undone["phase"], "BACK_CANDIDATES_READY")
        self.assertEqual(undone["shape_decisions"][-1]["action"], "UNDO")
        self.assertEqual(undone["shape_decisions"][-1]
                         ["compensates_decision_id"], first_decision_id)

        # A retried Undo command must not walk farther back through history.
        event_count = len(undone["events"])
        decision_count = len(undone["shape_decisions"])
        same, repeated_undo = _step(undone, undo_event)
        self.assertEqual(repeated_undo["verdict"], "ANSWER")
        self.assertTrue(repeated_undo["idempotent"])
        self.assertEqual(len(same["events"]), event_count)
        self.assertEqual(len(same["shape_decisions"]), decision_count)

        reapproved, second_approval = _step(undone, {
            "type": "APPROVE_HYPOTHESIS",
            "candidate_id": selected["candidate_id"],
            "digest": selected["digest"], "by": "Mina"})
        self.assertEqual(second_approval["verdict"], "APPROVED")
        self.assertEqual(reapproved["shape_approval"]["approval_id"],
                         first_approval_id)
        self.assertNotEqual(reapproved["shape_decisions"][-1]["decision_id"],
                            first_decision_id)
        self.assertEqual(reapproved["shape_decisions"][-1]["action"],
                         "APPROVE")

        rerun, rerun_result = _step(
            reapproved, {"type": "GENERATE_PATTERN"}, **spies.kwargs())
        self.assertEqual(rerun_result["verdict"], "ANSWER")
        self.assertEqual(rerun["phase"], "PATTERN_READY")
        self.assertEqual(len(spies.calls["pattern"]), 2)

    def test_runners_are_hard_blocked_before_named_digest_approval(self):
        state, _ = _front_job()
        candidates = _rows(_artifact(state, "back_candidates") or
                           _artifact(state, "structure_candidates"))
        selected = candidates[0]
        spies = RunnerSpies()

        # Merely asking to continue cannot invoke pattern, physics, or sewing.
        _, blocked = _step(
            state, {"type": "GENERATE_PATTERN"}, **spies.kwargs())
        self.assertTrue(str(blocked["verdict"]).startswith("UNKNOWN_"))
        _, repair_blocked = _step(
            state, {"type": "REPAIR_PATTERN"}, **spies.kwargs())
        self.assertTrue(str(repair_blocked["verdict"]).startswith("UNKNOWN_"))
        _, simulation_blocked = _step(
            state, {"type": "SIMULATE"}, **spies.kwargs())
        self.assertTrue(str(simulation_blocked["verdict"]).startswith("UNKNOWN_"))
        sewing_state, sewing_blocked = _step(state, {
            "type": "SUBMIT_SEWING_METHODS", "manifest": {},
            "methods": [{"steps": ["untrusted"]}]})
        self.assertTrue(str(sewing_blocked["verdict"]).startswith("UNKNOWN_"))
        self.assertIsNone(sewing_state.get("sewing"))
        self.assertEqual(spies.calls, {"pattern": [], "repair": [],
                                      "simulation": []})

        unnamed_state, unnamed = _step(state, {
            "type": "APPROVE_HYPOTHESIS", "candidate_id": _candidate_id(selected),
            "digest": _candidate_digest(selected), "by": ""})
        self.assertTrue(str(unnamed["verdict"]).startswith("UNKNOWN_"))
        _step(unnamed_state, {"type": "GENERATE_PATTERN"}, **spies.kwargs())
        self.assertEqual(spies.calls, {"pattern": [], "repair": [],
                                      "simulation": []})

        stale_state, stale = _step(state, {
            "type": "APPROVE_HYPOTHESIS", "candidate_id": _candidate_id(selected),
            "digest": "sha256:wrong", "by": "Mina"})
        self.assertTrue(str(stale["verdict"]).startswith("UNKNOWN_"))
        _step(stale_state, {"type": "GENERATE_PATTERN"}, **spies.kwargs())
        self.assertEqual(spies.calls, {"pattern": [], "repair": [],
                                      "simulation": []})

    def test_named_digest_approval_is_the_only_runner_gate(self):
        state, _ = _front_job()
        candidates = _rows(_artifact(state, "back_candidates") or
                           _artifact(state, "structure_candidates"))
        selected = candidates[0]
        approved, approval_result = _step(state, {
            "type": "APPROVE_HYPOTHESIS", "candidate_id": _candidate_id(selected),
            "digest": _candidate_digest(selected), "by": "Mina"})
        self.assertEqual(approval_result["verdict"], "APPROVED")
        approval = _artifact(approved, "structure_approval")
        self.assertIsInstance(approval, dict)
        self.assertEqual(approval.get("by"), "Mina")
        self.assertEqual(approval.get("candidate_digest"),
                         _candidate_digest(selected))
        # Approval is a separate record; the candidate remains a proposal.
        approved_rows = _rows(_artifact(approved, "back_candidates") or
                              _artifact(approved, "structure_candidates"))
        self.assertTrue(all(row.get("state") == "PROPOSED"
                            for row in approved_rows))

        # Re-delivery of the same human click is idempotent: no second event
        # and no downstream restart are permitted.
        event_count = len(approved["events"])
        repeated, repeated_result = _step(approved, {
            "type": "APPROVE_HYPOTHESIS",
            "candidate_id": _candidate_id(selected),
            "digest": _candidate_digest(selected), "by": "Mina"})
        self.assertEqual(repeated_result["verdict"], "APPROVED")
        self.assertTrue(repeated_result["idempotent"])
        self.assertEqual(len(repeated["events"]), event_count)

        spies = RunnerSpies()
        pattern_state, pattern_result = _step(
            approved, {"type": "GENERATE_PATTERN"}, **spies.kwargs())
        self.assertEqual(pattern_result["verdict"], "ANSWER")
        repaired_state, repair_result = _step(
            pattern_state, {"type": "REPAIR_PATTERN"}, **spies.kwargs())
        self.assertEqual(repair_result["verdict"], "ANSWER")
        material_state, material_result = _step(repaired_state, {
            "type": "SUBMIT_MATERIAL_CANDIDATES", "candidates": [
                {"candidate_id": "cotton", "drape": 0.3},
                {"candidate_id": "jersey", "drape": 0.8},
            ]})
        self.assertEqual(material_result["verdict"], "PROPOSED")
        material = material_state["material_sheet"]["candidates"][0]
        material_state, material_approval = _step(material_state, {
            "type": "APPROVE_MATERIAL", "candidate_id": material["candidate_id"],
            "digest": material["digest"], "by": "Mina"})
        self.assertEqual(material_approval["verdict"], "APPROVED")
        completed, simulation_result = _step(
            material_state, {"type": "SIMULATE"}, **spies.kwargs())
        self.assertEqual({name: len(calls) for name, calls in spies.calls.items()},
                         {"pattern": 1, "repair": 1, "simulation": 1})
        self.assertFalse(str(simulation_result["verdict"]).startswith("UNKNOWN_"))
        for calls in spies.calls.values():
            self.assertEqual(calls[0]["state"]["shape_approval"]["by"], "Mina")
            self.assertEqual(calls[0]["state"]["shape_approval"]["candidate_digest"],
                             _candidate_digest(selected))

    def test_procedural_sewing_plan_continues_without_claiming_a_corpus(self):
        state, _ = _front_job()
        selected = state["hypothesis_sheet"]["candidates"][0]
        state, approved = _step(state, {
            "type": "APPROVE_HYPOTHESIS",
            "candidate_id": selected["candidate_id"],
            "digest": selected["digest"], "by": "Mina"})
        self.assertEqual(approved["verdict"], "APPROVED")
        plan = {
            "verdict": "REVIEW_MANUFACTURING_CHOICES_REQUIRED",
            "order_verdict": "ANSWER",
            "candidate_id": selected["candidate_id"],
            "source_pattern_digest": "sha256:pattern",
            "steps": [{"step": 1, "step_id": "seam:close-shell",
                       "action": "close_intrinsic_wrap", "pieces": ["shell"]}],
            "reviews": [{"verdict": "REVIEW_SEAM_METHOD_REQUIRED"}],
        }
        state["pattern"] = {"verdict": "ANSWER", "digest": "sha256:pattern",
                            "topology_sewing_plan": plan}

        continued, result = _step(
            state, {"type": "USE_PROCEDURAL_SEWING_PLAN"})

        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(continued["phase"], "SEWING_CANDIDATES_READY")
        sewing = continued["sewing"]
        self.assertEqual(sewing["route"], "PROCEDURAL_TOPOLOGY")
        self.assertFalse(sewing["corpus_used"])
        self.assertFalse(sewing["corpus_evidence"])
        self.assertEqual(sewing["corpus_gap"], "UNKNOWN_NO_SEWING_CORPUS")
        self.assertFalse(sewing["manufacturing_ready"])
        self.assertFalse(sewing["manufacturing_certified"])
        self.assertEqual(sewing["shape_approval_id"],
                         state["shape_approval"]["approval_id"])

        wrong = copy.deepcopy(plan)
        wrong["candidate_id"] = "another-candidate"
        refused_state = copy.deepcopy(state)
        refused_state["pattern"]["topology_sewing_plan"] = wrong
        unchanged, refused = _step(
            refused_state, {"type": "USE_PROCEDURAL_SEWING_PLAN"})
        self.assertEqual(refused["verdict"],
                         "UNKNOWN_SEWING_APPROVAL_BINDING")
        self.assertIsNone(unchanged["sewing"])

        malformed = copy.deepcopy(state)
        malformed["pattern"] = "not-a-pattern"
        _, refused = _step(
            malformed, {"type": "USE_PROCEDURAL_SEWING_PLAN", "plan": plan})
        self.assertEqual(refused["verdict"],
                         "UNKNOWN_APPROVED_PATTERN_REQUIRED")

    def test_persisted_approval_tampering_closes_the_runner_gate(self):
        state, _ = _front_job()
        selected = state["hypothesis_sheet"]["candidates"][0]
        approved, result = _step(state, {
            "type": "APPROVE_HYPOTHESIS",
            "candidate_id": selected["candidate_id"],
            "digest": selected["digest"], "by": "Mina"})
        self.assertEqual(result["verdict"], "APPROVED")
        tampered = copy.deepcopy(approved)
        tampered["shape_approval"]["by"] = "model"
        spies = RunnerSpies()
        _, refused = _step(tampered, {"type": "GENERATE_PATTERN"},
                           **spies.kwargs())
        self.assertEqual(refused["verdict"], "UNKNOWN_SHAPE_APPROVAL_REQUIRED")
        self.assertEqual(spies.calls["pattern"], [])

    def test_llm_answer_and_observed_are_recursively_demoted(self):
        state, _ = _step(garment_factory.new_job("llm-authority"), _image_event())
        before_evidence = copy.deepcopy(_artifact(state, "image_evidence") or
                                        _artifact(state, "evidence"))
        malicious = _search_event()
        malicious["source"]["name"] = "fixture:llm-adapter"
        malicious["hits"] = [{
            "part_id": "bodice", "region_id": "r-bodice",
            "reference": "llm-look", "score": 0.99,
            "verdict": "ANSWER", "kind": "OBSERVED", "state": "OBSERVED",
            "visual_cues": {"verdict": "ANSWER", "state": "OBSERVED",
                            "evidence": {"back": "invented"}},
        }]
        frozen_event = copy.deepcopy(malicious)
        proposed, response = _step(state, malicious)
        self.assertEqual(response["verdict"], "ANSWER")
        proposals = _rows(_artifact(proposed, "search_results"))
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].get("state"), "PROPOSED")
        _assert_no_authoritative_llm_claim(self, proposals[0])
        self.assertEqual(_artifact(proposed, "image_evidence") or
                         _artifact(proposed, "evidence"), before_evidence)
        self.assertIsNone(_artifact(proposed, "structure_approval"))
        self.assertEqual(malicious, frozen_event)

    def test_job_and_events_are_append_only_and_iteration_budget_is_recorded(self):
        state = garment_factory.new_job("factory-contract", max_iterations=3)
        before = copy.deepcopy(state)
        advanced, response = _step(state, _image_event())
        self.assertEqual(response["verdict"], "ANSWER")
        self.assertEqual(state, before)
        self.assertEqual(advanced.get("job_id"), "factory-contract")
        self.assertEqual(advanced.get("max_iterations"), 3)
        self.assertGreater(len(advanced.get("events", advanced.get("history", []))),
                           len(state.get("events", state.get("history", []))))


if __name__ == "__main__":
    unittest.main()
