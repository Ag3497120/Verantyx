#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import json
import unittest

from photoloset.parts_ir_completion import bounded_preview_profile
from photoloset.parts_ir_pipeline import run_parts_ir_pipeline


def part(part_id, kind, dimensions=None, **semantics):
    row = {
        "part_id": part_id,
        "kind": kind,
        "layer": semantics.pop("layer", 0),
        "placement": semantics.pop("placement", "front torso"),
        "visible_basis": {
            "state": "PROPOSED",
            "basis": f"image model proposed {part_id} from the front view",
            "breaks_when": f"another view or reviewer rejects {part_id}",
        },
    }
    if dimensions is not None:
        row["dimensions"] = dimensions
    row.update(semantics)
    return row


def body(part_id, circumference):
    return part(part_id, "BODY_SHELL", {
        "height_cm": 44.0,
        "circumference_cm": circumference,
        "bottom_circumference_cm": circumference * 0.9,
    }, garment_unit="look")


def two_body_candidates():
    return {
        "schema": "garment.parts-ir.v1",
        "state": "PROPOSED",
        "candidates": [
            {"candidate_id": "close-back", "parts": [body("body-a", 84.0)]},
            {"candidate_id": "relaxed-back", "parts": [body("body-b", 102.0)]},
        ],
    }


class PartsIRPipelineTests(unittest.TestCase):
    def test_runs_two_candidates_with_bound_3d_and_flat_pattern(self):
        source = two_body_candidates()
        result = run_parts_ir_pipeline(
            source, preview_profile=bounded_preview_profile())

        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(result["state"], "PROPOSED")
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["successful_candidate_count"], 2)
        self.assertEqual(result["failed_candidate_count"], 0)
        self.assertTrue(result["claims"]["all_candidates_resolved"])
        self.assertFalse(result["claims"]["manufacturing_ready"])
        self.assertFalse(result["authority"]["approved"])
        self.assertFalse(result["authority"]["answer"])

        ids = [row["candidate_id"] for row in result["candidates"]]
        self.assertEqual(ids, ["close-back", "relaxed-back"])
        self.assertEqual(
            [row["candidate_id"] for row in result["candidate_bindings"]], ids)
        self.assertEqual(len({row["candidate_digest"]
                              for row in result["candidates"]}), 2)
        self.assertEqual(len({row["structure_digest"]
                              for row in result["candidates"]}), 2)

        for row, binding in zip(result["candidates"],
                                result["candidate_bindings"]):
            self.assertEqual(row["execution_status"], "SUCCEEDED")
            self.assertEqual(row["verdict"], "PROPOSED")
            self.assertEqual(row["preview"]["verdict"], "ANSWER")
            self.assertEqual(row["preview"]["state"], "PROPOSED")
            self.assertEqual(row["flat_pattern"]["verdict"], "ANSWER")
            self.assertEqual(row["flat_pattern"]["candidate_state"],
                             "PROPOSED")
            self.assertFalse(row["flat_pattern"]["manufacturing_ready"])
            self.assertTrue(row["artifact_binding"]["same_structure_digest"])
            self.assertTrue(row["artifact_binding"][
                "all_downstream_artifacts_bound"])
            self.assertEqual(row["structure_digest"],
                             row["preview"]["structure_digest"])
            self.assertEqual(row["structure_digest"],
                             row["flat_pattern"]["structure_digest"])
            self.assertEqual(binding["candidate_digest"],
                             row["candidate_digest"])
            self.assertEqual(binding["preview_structure_digest"],
                             binding["pattern_structure_digest"])
            manufacturing = row["manufacturing_preview"]
            self.assertEqual(manufacturing["view"],
                             "COMPACT_CUTTING_PREVIEW")
            self.assertTrue(manufacturing["manufacturing_preview_ready"])
            self.assertFalse(manufacturing["manufacturing_ready"])
            self.assertFalse(manufacturing["manufacturing_certified"])
            self.assertTrue(manufacturing["pieces"])
            self.assertTrue(all(piece["sew_line"] and piece["cut_line"]
                                for piece in manufacturing["pieces"]))
            self.assertFalse(manufacturing["exports"]["svg"]["included"])
            self.assertTrue(manufacturing["exports"]["svg"]["available"])
            self.assertNotIn("svg", manufacturing)
            sewing = row["sewing_plan"]
            self.assertEqual(sewing["order_verdict"], "ANSWER")
            self.assertFalse(sewing["manufacturing_ready"])
            self.assertEqual(
                manufacturing["source_pattern_digest"],
                row["flat_pattern"]["digest"])
            self.assertEqual(
                sewing["source_pattern_digest"],
                row["flat_pattern"]["digest"])
        self.assertTrue(result["claims"]["manufacturing_preview_ready"])
        self.assertTrue(result["claims"]["topology_sewing_order_derived"])
        json.dumps(result, ensure_ascii=False, allow_nan=False)

    def test_one_typed_topology_refusal_keeps_success_but_aggregate_unresolved(self):
        source = two_body_candidates()
        source["candidates"][1]["parts"].append(part(
            "detached-sleeves", "SLEEVE", {
                "length_cm": 55.0,
                "upper_circumference_cm": 34.0,
                "cuff_circumference_cm": 20.0,
            }, placement="arms", garment_unit="look", attached_to="body-b",
            side="bilateral", shape="detached", quantity=2))

        result = run_parts_ir_pipeline(
            source, preview_profile=bounded_preview_profile())

        self.assertEqual(result["verdict"], "UNRESOLVED")
        self.assertEqual(result["state"], "UNRESOLVED")
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["successful_candidate_count"], 1)
        self.assertEqual(result["failed_candidate_count"], 1)
        self.assertFalse(result["claims"]["all_candidates_resolved"])
        self.assertFalse(result["provenance"]["candidate_failures_hidden"])

        good, bad = result["candidates"]
        self.assertEqual(good["candidate_id"], "close-back")
        self.assertEqual(good["execution_status"], "SUCCEEDED")
        self.assertEqual(good["preview"]["verdict"], "ANSWER")
        self.assertEqual(good["flat_pattern"]["verdict"], "ANSWER")
        self.assertEqual(bad["candidate_id"], "relaxed-back")
        self.assertEqual(bad["execution_status"], "REFUSED")
        self.assertEqual(
            bad["verdict"],
            "UNKNOWN_PARTS_TOPOLOGY_DETACHED_SLEEVE_UNRESOLVED")
        self.assertEqual(bad["failures"][0]["stage"], "parts_ir_topology")
        self.assertIsNone(bad["preview"])
        self.assertIsNone(bad["flat_pattern"])
        self.assertEqual(result["failures"][0]["code"], bad["verdict"])
        self.assertEqual(
            [row["execution_status"] for row in result["candidate_bindings"]],
            ["SUCCEEDED", "REFUSED"])

    def test_one_completion_refusal_does_not_hide_other_candidate_success(self):
        source = two_body_candidates()
        source["candidates"][1]["parts"][0]["dimensions"][
            "circumference_cm"] = -1.0

        result = run_parts_ir_pipeline(
            source, preview_profile=bounded_preview_profile())

        self.assertEqual(result["verdict"], "UNRESOLVED")
        self.assertEqual(result["successful_candidate_count"], 1)
        self.assertEqual(result["failed_candidate_count"], 1)
        good, bad = result["candidates"]
        self.assertEqual(good["candidate_id"], "close-back")
        self.assertEqual(good["execution_status"], "SUCCEEDED")
        self.assertTrue(good["completion_execution"][
            "isolated_with_non_design_shadows"])
        self.assertEqual(good["preview"]["verdict"], "ANSWER")
        self.assertEqual(good["flat_pattern"]["verdict"], "ANSWER")
        self.assertEqual(bad["candidate_id"], "relaxed-back")
        self.assertEqual(bad["execution_status"], "REFUSED")
        self.assertEqual(bad["verdict"],
                         "UNKNOWN_PARTS_IR_INVALID_DIMENSION")
        self.assertEqual(bad["failures"][0]["stage"],
                         "parts_ir_completion")
        self.assertFalse(result["provenance"]["candidate_failures_hidden"])

    def test_input_is_immutable_and_whole_result_is_deterministic(self):
        source = two_body_candidates()
        before = copy.deepcopy(source)
        profile = bounded_preview_profile()
        profile_before = copy.deepcopy(profile)

        first = run_parts_ir_pipeline(source, preview_profile=profile)
        second = run_parts_ir_pipeline(source, preview_profile=profile)

        self.assertEqual(first, second)
        self.assertEqual(source, before)
        self.assertEqual(profile, profile_before)
        self.assertFalse(first["provenance"]["input_mutated"])

    def test_target_measurements_complete_missing_dimensions_without_preview(self):
        source = {
            "schema": "garment.parts-ir.v1",
            "parts": [part("body", "BODY_SHELL")],
            "candidate_count": 2,
        }
        target = {
            "source_id": "target-form-a",
            "upper_height_cm": 46.0,
            "body_circumference_cm": 91.0,
        }
        target_before = copy.deepcopy(target)
        result = run_parts_ir_pipeline(source, target_measurements=target)
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(target, target_before)
        self.assertEqual(result["provenance"]["measurement_source"],
                         "TARGET_MEASUREMENTS")
        for candidate in result["completion"]["candidates"]:
            evidence = candidate["nodes"][0]["attributes"][
                "dimension_evidence"]
            self.assertEqual(
                evidence["height_cm"]["dimension_source"],
                "TARGET_MANNEQUIN_DERIVED_PROPOSAL")
            self.assertEqual(evidence["height_cm"]["state"], "PROPOSED")

    def test_requires_explicit_measurement_source_and_at_least_two_candidates(self):
        no_source = run_parts_ir_pipeline(two_body_candidates())
        self.assertEqual(no_source["verdict"], "UNRESOLVED")
        self.assertEqual(
            no_source["failures"][0]["code"],
            "UNKNOWN_PARTS_IR_PIPELINE_MEASUREMENT_SOURCE_REQUIRED")

        one = {
            "schema": "garment.parts-ir.v1",
            "candidates": [{
                "candidate_id": "only",
                "parts": [body("body", 90.0)],
            }],
        }
        insufficient = run_parts_ir_pipeline(
            one, preview_profile=bounded_preview_profile())
        self.assertEqual(insufficient["verdict"], "UNRESOLVED")
        self.assertEqual(
            insufficient["failures"][0]["code"],
            "UNKNOWN_PARTS_IR_CANDIDATES_INSUFFICIENT")
        self.assertEqual(insufficient["candidate_count"], 0)

        duplicate = two_body_candidates()
        duplicate["candidates"][1]["candidate_id"] = "close-back"
        ambiguous = run_parts_ir_pipeline(
            duplicate, preview_profile=bounded_preview_profile())
        self.assertEqual(ambiguous["verdict"], "UNRESOLVED")
        self.assertEqual(ambiguous["failures"][0]["code"],
                         "UNKNOWN_PARTS_IR_DUPLICATE_CANDIDATE")
        self.assertEqual(ambiguous["candidate_bindings"], [])


if __name__ == "__main__":
    unittest.main()
