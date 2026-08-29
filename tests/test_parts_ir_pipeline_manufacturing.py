#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import json
import unittest
from unittest.mock import patch

from photoloset import parts_ir_pipeline as pipeline
from photoloset.parts_ir_completion import bounded_preview_profile


def _part(part_id, circumference):
    return {
        "part_id": part_id,
        "kind": "BODY_SHELL",
        "layer": 0,
        "placement": "front torso",
        "visible_basis": {
            "state": "PROPOSED",
            "basis": f"vision model proposed {part_id}",
            "breaks_when": f"another view rejects {part_id}",
        },
        "dimensions": {
            "height_cm": 44.0,
            "circumference_cm": circumference,
            "bottom_circumference_cm": circumference * 0.9,
        },
        "garment_unit": "look",
    }


def _source():
    return {
        "schema": "garment.parts-ir.v1",
        "state": "PROPOSED",
        "candidates": [
            {"candidate_id": "candidate-a",
             "parts": [_part("body-a", 84.0)]},
            {"candidate_id": "candidate-b",
             "parts": [_part("body-b", 102.0)]},
        ],
    }


def _run():
    return pipeline.run_parts_ir_pipeline(
        _source(), preview_profile=bounded_preview_profile())


class PartsIRPipelineManufacturingTests(unittest.TestCase):
    def test_success_candidates_include_compact_cutting_and_sewing_artifacts(self):
        result = _run()
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertTrue(result["claims"]["manufacturing_preview_ready"])
        self.assertTrue(result["claims"]["topology_sewing_order_derived"])
        self.assertFalse(result["claims"]["manufacturing_ready"])
        self.assertFalse(result["authority"]["approved"])

        for candidate, binding in zip(result["candidates"],
                                      result["candidate_bindings"]):
            with self.subTest(candidate_id=candidate["candidate_id"]):
                manufacturing = candidate["manufacturing_preview"]
                sewing = candidate["sewing_plan"]
                pattern = candidate["flat_pattern"]

                self.assertEqual(manufacturing["verdict"], "ANSWER")
                self.assertEqual(manufacturing["view"],
                                 "COMPACT_CUTTING_PREVIEW")
                self.assertTrue(manufacturing["compact"])
                self.assertNotIn("svg", manufacturing)
                self.assertNotIn("dxf_export", manufacturing)
                self.assertFalse(manufacturing["exports"]["svg"]["included"])
                self.assertTrue(manufacturing["exports"]["svg"]["available"])
                self.assertFalse(manufacturing["exports"]["dxf"]["included"])
                self.assertTrue(manufacturing["exports"]["dxf"]["available"])
                self.assertEqual(len(manufacturing["full_artifact_digest"]), 64)
                self.assertEqual(len(manufacturing["compact_digest"]), 64)
                self.assertEqual(manufacturing["source_pattern_digest"],
                                 pattern["digest"])
                self.assertEqual(manufacturing["structure_digest"],
                                 candidate["structure_digest"])
                self.assertTrue(manufacturing["remaining_gates"])
                self.assertFalse(manufacturing["manufacturing_ready"])
                self.assertFalse(manufacturing["manufacturing_certified"])
                self.assertEqual(manufacturing["authority"]["highest_state"],
                                 "PROPOSED")
                self.assertFalse(manufacturing["authority"]["approved"])

                self.assertTrue(manufacturing["pieces"])
                piece = manufacturing["pieces"][0]
                self.assertIn("sew_line", piece)
                self.assertIn("cut_line", piece)
                self.assertNotEqual(piece["sew_line"], piece["cut_line"])
                self.assertEqual(piece["seam_allowance_cm"]["state"],
                                 "PROPOSED")
                self.assertTrue(manufacturing["notches"][piece["piece_id"]])

                self.assertEqual(sewing["order_verdict"], "ANSWER")
                self.assertEqual(sewing["candidate_state"], "PROPOSED")
                self.assertEqual(sewing["source_pattern_digest"],
                                 pattern["digest"])
                self.assertEqual(sewing["structure_digest"],
                                 candidate["structure_digest"])
                self.assertTrue(sewing["steps"])
                self.assertTrue(all(
                    step["authority"] == "DERIVED_FROM_COMPILED_TOPOLOGY"
                    for step in sewing["steps"]
                ))
                self.assertFalse(sewing["manufacturing_ready"])
                self.assertFalse(sewing["manufacturing_certified"])

                artifact_binding = candidate["artifact_binding"]
                self.assertTrue(
                    artifact_binding["all_downstream_artifacts_bound"])
                self.assertEqual(
                    binding["manufacturing_artifact_digest"],
                    manufacturing["full_artifact_digest"])
                self.assertEqual(binding["sewing_plan_digest"],
                                 sewing["digest"])
                self.assertNotIn("<svg", json.dumps(
                    manufacturing, ensure_ascii=False))

    def test_manufacturing_refusal_is_attached_to_only_its_candidate(self):
        real_build = pipeline.pattern_manufacturing_bundle.build

        def selective_build(pattern, **kwargs):
            if pattern.get("candidate_id") == "candidate-b":
                return {
                    "verdict": "UNKNOWN_TEST_MANUFACTURING_REFUSAL",
                    "why": "candidate-b manufacturing preview failed",
                    "how_to_close": "repair candidate-b cutting geometry",
                }
            return real_build(pattern, **kwargs)

        with patch.object(pipeline.pattern_manufacturing_bundle, "build",
                          side_effect=selective_build):
            result = _run()

        self.assertEqual(result["verdict"], "UNRESOLVED")
        self.assertEqual(result["successful_candidate_count"], 1)
        self.assertEqual(result["failed_candidate_count"], 1)
        good, bad = result["candidates"]
        self.assertEqual(good["execution_status"], "SUCCEEDED")
        self.assertEqual(good["manufacturing_preview"]["verdict"], "ANSWER")
        self.assertEqual(bad["execution_status"], "REFUSED")
        self.assertEqual(bad["verdict"],
                         "UNKNOWN_TEST_MANUFACTURING_REFUSAL")
        self.assertEqual(bad["failures"][0]["stage"],
                         "pattern_manufacturing_bundle")
        self.assertEqual(bad["manufacturing_preview"]["verdict"],
                         "UNKNOWN_TEST_MANUFACTURING_REFUSAL")
        self.assertFalse(result["provenance"]["candidate_failures_hidden"])

    def test_sewing_plan_refusal_is_not_relabelled_as_a_review(self):
        real_plan = pipeline.structure_sewing_plan.plan

        def selective_plan(pattern):
            if pattern.get("candidate_id") == "candidate-b":
                return {
                    "verdict": "UNKNOWN_TEST_SEWING_PLAN_REFUSAL",
                    "order_verdict": "UNKNOWN_TEST_SEWING_PLAN_REFUSAL",
                    "why": "candidate-b sewing topology failed",
                    "how_to_close": "repair candidate-b seam topology",
                    "manufacturing_ready": False,
                    "manufacturing_certified": False,
                }
            return real_plan(pattern)

        with patch.object(pipeline.structure_sewing_plan, "plan",
                          side_effect=selective_plan):
            result = _run()

        good, bad = result["candidates"]
        self.assertEqual(good["execution_status"], "SUCCEEDED")
        self.assertEqual(bad["execution_status"], "REFUSED")
        self.assertEqual(bad["verdict"],
                         "UNKNOWN_TEST_SEWING_PLAN_REFUSAL")
        self.assertEqual(bad["failures"][0]["stage"],
                         "structure_sewing_plan")
        self.assertEqual(bad["sewing_plan"]["order_verdict"],
                         "UNKNOWN_TEST_SEWING_PLAN_REFUSAL")
        self.assertEqual(bad["manufacturing_preview"]["verdict"], "ANSWER")

    def test_downstream_authority_escalation_is_a_typed_candidate_failure(self):
        real_build = pipeline.pattern_manufacturing_bundle.build

        def escalated_build(pattern, **kwargs):
            result = copy.deepcopy(real_build(pattern, **kwargs))
            if pattern.get("candidate_id") == "candidate-b":
                result["manufacturing_ready"] = True
            return result

        with patch.object(pipeline.pattern_manufacturing_bundle, "build",
                          side_effect=escalated_build):
            result = _run()

        good, bad = result["candidates"]
        self.assertEqual(good["execution_status"], "SUCCEEDED")
        self.assertEqual(bad["execution_status"], "REFUSED")
        self.assertEqual(bad["verdict"],
                         "UNKNOWN_PARTS_IR_PIPELINE_AUTHORITY_ESCALATION")
        self.assertEqual(bad["failures"][0]["stage"],
                         "pattern_manufacturing_bundle")
        self.assertFalse(bad["manufacturing_preview"]["manufacturing_ready"])
        self.assertFalse(result["authority"]["approved"])


if __name__ == "__main__":
    unittest.main()
