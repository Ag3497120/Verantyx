#!/usr/bin/env python3
import unittest

from photoloset import garment_engineering_review as review
from photoloset import garment_factory


def pattern():
    return {
        "verdict": "ANSWER", "schema": "garment.compiled-pattern.v1",
        "candidate_id": "front-a", "candidate_state": "APPROVED",
        "structure_digest": "structure-a", "digest": "pattern-a",
        "approval": {"by": "Reviewer", "digest": "candidate-a"},
        "pieces": [{"piece_id": "body", "attributes": {}}],
        "seams": [], "layers": [],
        "seam_checks": [{"geometrically_sewable": True}],
    }


class GarmentEngineeringReviewTests(unittest.TestCase):
    def test_uncompiled_visible_part_is_an_actionable_gate(self):
        source = pattern()
        source["representation_complete"] = False
        source["uncompiled_visual_parts"] = [{
            "part_id": "wing", "model_kind": "WING",
            "state": "PROPOSED_UNCOMPILED",
        }]
        result = review.review(source)
        by_name = {row["gate"]: row for row in result["gates"]}
        self.assertEqual(by_name["visual_representation_coverage"]["verdict"],
                         "REVIEW_UNCOMPILED_VISUAL_PARTS")
        self.assertIn("visual_representation_coverage",
                      result["actionable_gates"])

    def test_disconnected_pieces_cannot_pass_as_one_finished_garment(self):
        source = pattern()
        source["pieces"].append({"piece_id": "sleeve", "attributes": {}})
        result = review.review(source, repair={"sewable": True})
        by_name = {row["gate"]: row for row in result["gates"]}
        self.assertEqual(by_name["assembly_connectivity"]["verdict"],
                         "REVIEW_DISCONNECTED_PATTERN_ASSEMBLY")
        self.assertIn("assembly_connectivity", result["actionable_gates"])

    def test_join_or_layer_connects_parts(self):
        for collection in ("seams", "layers"):
            with self.subTest(collection=collection):
                source = pattern()
                source["pieces"].append(
                    {"piece_id": "overlay", "attributes": {}})
                source[collection] = [{
                    "operation_id": "attach-overlay",
                    "a": {"piece_id": "body", "edge": "e0"},
                    "b": {"piece_id": "overlay", "edge": "e2"},
                }]
                self.assertEqual(review.assembly_connectivity(source)["verdict"],
                                 "ANSWER")

    def test_explicit_separates_are_independent_garment_units(self):
        source = pattern()
        source["pieces"] = [
            {"piece_id": "top", "attributes": {"garment_unit": "upper"}},
            {"piece_id": "trousers", "attributes": {"garment_unit": "lower"}},
        ]
        self.assertEqual(review.assembly_connectivity(source)["verdict"],
                         "ANSWER")

    def test_self_closure_does_not_attach_a_sleeve_to_a_body(self):
        source = pattern()
        source["pieces"].append({"piece_id": "sleeve", "attributes": {}})
        source["seams"] = [{
            "operation_id": "close-sleeve",
            "a": {"piece_id": "sleeve", "edge": "e1"},
            "b": {"piece_id": "sleeve", "edge": "e3"},
        }]
        result = review.assembly_connectivity(source)
        self.assertEqual(result["verdict"],
                         "REVIEW_DISCONNECTED_PATTERN_ASSEMBLY")

    def test_preview_and_xpbd_do_not_become_strength_or_comfort_passes(self):
        result = review.review(
            pattern(), repair={"sewable": True},
            sewing_plan={"order_verdict": "ANSWER", "reviews": []},
            manufacturing={"verdict": "ANSWER",
                           "manufacturing_preview_ready": True,
                           "manufacturing_ready": False,
                           "remaining_gates": ["material"]},
            simulation={"verdict": "ANSWER", "stages": {
                "xpbd": {"verdict": "ANSWER", "diagnostics": {"strain": {}}},
                "material_calibration": {"verdict": "SKIPPED_NOT_REQUESTED"},
                "ccd": {"verdict": "SKIPPED_NOT_REQUESTED"},
                "comfort": {"verdict": "SKIPPED_NOT_REQUESTED"},
            }})
        self.assertEqual(result["verdict"], "REVIEW_ENGINEERING_GATES_REQUIRED")
        by_name = {row["gate"]: row for row in result["gates"]}
        self.assertEqual(by_name["geometric_sewability"]["verdict"], "PASS")
        self.assertEqual(by_name["cloth_numerics"]["verdict"], "PASS")
        self.assertEqual(by_name["material_and_strength"]["verdict"],
                         "REVIEW_STRENGTH_CALIBRATION_REQUIRED")
        self.assertEqual(by_name["wearer_comfort"]["verdict"],
                         "REVIEW_COMFORT_OBSERVATIONS_REQUIRED")
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["industrial_or_medical_certification"])

    def test_missing_pattern_is_typed_unknown(self):
        result = review.review({"schema": "wrong"})
        self.assertEqual(result["verdict"], "UNKNOWN_COMPILED_PATTERN_REQUIRED")

    def test_same_inputs_have_same_digest(self):
        first = review.review(pattern())
        second = review.review(pattern())
        self.assertEqual(first, second)

    def test_factory_does_not_converge_while_review_has_actionable_gates(self):
        state = garment_factory.new_job("engineering-loop")
        state.update({
            "phase": "SEWING_CANDIDATES_READY",
            "pattern": pattern(),
            "repair": {"sewable": True},
            "simulation": {"verdict": "ANSWER", "engineering_review": {
                "actionable_gates": ["material_and_strength", "wearer_comfort"]}},
            "sewing": {"state": "PROPOSED"},
        })
        # Install a digest-valid approval without relying on a model proposal.
        candidate = {"candidate_id": "front-a", "digest": "candidate-a"}
        state["hypothesis_sheet"] = {
            "comparison_digest": "comparison-a", "candidates": [candidate]}
        approval = {"state": "APPROVED", "by": "Reviewer",
                    "candidate_id": "front-a", "candidate_digest": "candidate-a",
                    "comparison_digest": "comparison-a"}
        approval["approval_id"] = garment_factory._digest(approval)
        state["shape_approval"] = approval
        result = garment_factory.advance(state, {"type": "ITERATE"})
        self.assertEqual(result["verdict"], "CONTINUE")
        self.assertIn("engineering gate: material_and_strength", result["missing"])
        self.assertNotEqual(result["state"]["phase"], "CONVERGED_REVIEW")


if __name__ == "__main__":
    unittest.main()
