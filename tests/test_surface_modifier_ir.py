#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset import structure_sewing_plan
from photoloset import structure_to_pattern as compiler
from photoloset import surface_modifier_ir


def bodice_structure(operation=None):
    spec = {
        "schema": "garment.structure.v1",
        "nodes": [
            {
                "node_id": "shell",
                "kind": "BODY_SHELL",
                "dimensions": {
                    "height_cm": 42.0,
                    "circumference_cm": 96.0,
                    "bottom_circumference_cm": 80.0,
                },
                "attributes": {
                    "garment_unit": "dress",
                    "proposal_only": True,
                },
                "ports": [{
                    "port_id": "waist",
                    "length_cm": 80.0,
                    "interface": "waist",
                    "role": "loop",
                }],
            },
            {
                "node_id": "sleeves",
                "kind": "SLEEVE",
                "dimensions": {
                    "length_cm": 58.0,
                    "upper_circumference_cm": 34.0,
                    "cuff_circumference_cm": 20.0,
                },
                "attributes": {
                    "bilateral": True,
                    "proposal_only": True,
                },
            },
        ],
        "operations": [],
    }
    if operation is not None:
        spec["operations"] = [operation]
    return spec


def modifier(kind, parameters, target):
    return {
        "operation_id": f"surface-{kind.lower()}",
        "kind": kind,
        "source": {"node_id": "shell", "port_id": "waist"},
        "parameters": {
            **copy.deepcopy(parameters),
            "surface_target": copy.deepcopy(target),
        },
    }


class SurfaceModifierResolverTests(unittest.TestCase):
    def setUp(self):
        result = compiler.compile(bodice_structure())
        self.assertEqual(result["verdict"], "ANSWER")
        self.pieces = result["pieces"]

    def test_exact_piece_and_semantic_group_resolve_without_mutating_input(self):
        operation = modifier(
            "PLEAT", {"count": 1, "depth_cm": 1.0},
            {"piece_id": "shell:front",
             "semantic_edge_group": "waist:right",
             "state": "PROPOSED"})
        before_operation = copy.deepcopy(operation)
        before_pieces = copy.deepcopy(self.pieces)
        first = surface_modifier_ir.resolve(operation, self.pieces)
        second = surface_modifier_ir.resolve(operation, self.pieces)

        self.assertEqual(first["verdict"], "ANSWER")
        self.assertEqual(first["piece_id"], "shell:front")
        self.assertEqual(first["edge"], "e11")
        self.assertEqual(first["digest"], second["digest"])
        changed = copy.deepcopy(operation)
        changed["parameters"]["depth_cm"] = 1.5
        self.assertNotEqual(
            first["digest"],
            surface_modifier_ir.resolve(changed, self.pieces)["digest"])
        self.assertFalse(first["binding"]["resolution"][
            "primitive_port_edge_used"])
        self.assertEqual(operation, before_operation)
        self.assertEqual(self.pieces, before_pieces)

    def test_source_node_without_real_piece_selector_stops_for_review(self):
        operation = modifier(
            "DART", {"t": 0.5, "intake_cm": 1.0, "depth_cm": 5.0},
            {"semantic_edge_group": "waist:right", "state": "PROPOSED"})
        result = surface_modifier_ir.resolve(operation, self.pieces)
        self.assertEqual(result["verdict"],
                         "REVIEW_SURFACE_MODIFIER_PIECE_AMBIGUOUS")
        self.assertEqual(result["state"], "REVIEW")
        self.assertEqual(result["candidate_piece_ids"],
                         ["shell:back", "shell:front"])

    def test_role_selector_is_allowed_only_when_it_becomes_unique(self):
        operation = modifier(
            "DART", {"t": 0.5, "intake_cm": 1.0, "depth_cm": 5.0},
            {"source_node_id": "shell", "role": "front_bodice",
             "semantic_edge_group": "waist:left", "state": "PROPOSED"})
        result = surface_modifier_ir.resolve(operation, self.pieces)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["piece_id"], "shell:front")
        self.assertEqual(result["edge"], "e12")

    def test_multi_segment_group_requires_explicit_index(self):
        target = {
            "piece_id": "shell:front",
            "semantic_edge_group": "armhole:right",
            "state": "PROPOSED",
        }
        operation = modifier(
            "PLEAT", {"count": 1, "depth_cm": 0.05}, target)
        ambiguous = surface_modifier_ir.resolve(operation, self.pieces)
        self.assertEqual(ambiguous["verdict"],
                         "REVIEW_SURFACE_MODIFIER_EDGE_AMBIGUOUS")
        self.assertGreater(len(ambiguous["candidate_edges"]), 1)

        operation["parameters"]["surface_target"]["edge_index"] = 3
        resolved = surface_modifier_ir.resolve(operation, self.pieces)
        self.assertEqual(resolved["verdict"], "ANSWER")
        self.assertEqual(resolved["binding"]["target"]["edge_index"], 3)

    def test_raw_en_and_authority_promotion_are_refused(self):
        raw = modifier(
            "PLEAT", {"count": 1, "depth_cm": 1.0},
            {"piece_id": "shell:front", "semantic_edge_group": "waist:right",
             "edge": "e11", "state": "PROPOSED"})
        self.assertEqual(surface_modifier_ir.resolve(raw, self.pieces)["verdict"],
                         "UNKNOWN_SURFACE_MODIFIER_RAW_EDGE_FORBIDDEN")

        promoted = modifier(
            "PLEAT", {"count": 1, "depth_cm": 1.0},
            {"piece_id": "shell:front", "semantic_edge_group": "waist:right",
             "state": "OBSERVED"})
        self.assertEqual(
            surface_modifier_ir.resolve(promoted, self.pieces)["verdict"],
            "UNKNOWN_SURFACE_MODIFIER_AUTHORITY")


class SurfaceModifierCompilerTests(unittest.TestCase):
    def test_pleat_dart_and_fold_bind_to_the_expanded_real_piece(self):
        cases = (
            ("PLEAT", {"count": 1, "depth_cm": 1.0}),
            ("DART", {"t": 0.5, "intake_cm": 1.0, "depth_cm": 5.0}),
            ("FOLD", {"start": [-5.0, 15.0], "end": [5.0, 15.0],
                      "direction": "valley"}),
        )
        for kind, parameters in cases:
            with self.subTest(kind=kind):
                operation = modifier(
                    kind, parameters,
                    {"piece_id": "shell:front",
                     "semantic_edge_group": "waist:right",
                     "state": "PROPOSED"})
                result = compiler.compile(
                    bodice_structure(operation), candidate_id=f"candidate-{kind}")
                self.assertEqual(result["verdict"], "ANSWER")
                self.assertEqual(len(result["surface_modifiers"]), 1)
                transform = result["transforms"][0]
                self.assertEqual(transform["kind"], kind)
                self.assertEqual(transform["piece_id"], "shell:front")
                self.assertEqual(transform["state"], "PROPOSED")
                self.assertEqual(transform["surface_binding"]["target"][
                    "semantic_edge_group"], "waist:right")
                self.assertFalse(transform["surface_binding"]["resolution"][
                    "primitive_port_edge_used"])
                front = next(piece for piece in result["pieces"]
                             if piece["piece_id"] == "shell:front")
                self.assertEqual(front["transforms"][-1]["operation_id"],
                                 operation["operation_id"])

                sewing = structure_sewing_plan.plan(result)
                self.assertIn(sewing["verdict"], (
                    "ANSWER", "REVIEW_MANUFACTURING_CHOICES_REQUIRED"))
                task = next(row for row in sewing["steps"]
                            if row.get("operation_id") == operation["operation_id"])
                self.assertEqual(task["pieces"], ["shell:front"])

    def test_ambiguous_expanded_body_is_review_not_canonical_port_fallback(self):
        operation = modifier(
            "PLEAT", {"count": 1, "depth_cm": 1.0},
            {"semantic_edge_group": "waist:right", "state": "PROPOSED"})
        result = compiler.compile(bodice_structure(operation))
        self.assertEqual(result["verdict"],
                         "REVIEW_SURFACE_MODIFIER_PIECE_AMBIGUOUS")
        self.assertEqual(result["state"], "REVIEW")

    def test_candidate_approval_does_not_promote_surface_modifier(self):
        operation = modifier(
            "DART", {"t": 0.5, "intake_cm": 1.0, "depth_cm": 5.0},
            {"piece_id": "shell:back",
             "semantic_edge_group": "waist:left",
             "state": "PROPOSED"})
        result = compiler.compile(
            bodice_structure(operation), candidate_state="APPROVED",
            approval={"by": "Reviewer", "digest": "candidate-digest"})
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["candidate_state"], "APPROVED")
        self.assertEqual(result["surface_modifiers"][0]["state"], "PROPOSED")
        self.assertFalse(result["surface_modifiers"][0]["resolution"][
            "authority_promoted"])

    def test_unexpanded_body_without_semantic_groups_does_not_get_an_en_guess(self):
        spec = bodice_structure()
        spec["nodes"] = [spec["nodes"][0]]
        spec["operations"] = [modifier(
            "PLEAT", {"count": 1, "depth_cm": 1.0},
            {"piece_id": "shell", "semantic_edge_group": "waist",
             "state": "PROPOSED"})]
        result = compiler.compile(spec)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_SURFACE_MODIFIER_EDGE_GROUP")
        self.assertNotIn("edge", result)

    def test_untyped_body_modifier_cannot_fall_back_to_port_order(self):
        spec = bodice_structure()
        spec["nodes"] = [spec["nodes"][0]]
        spec["operations"] = [{
            "operation_id": "legacy-body-pleat",
            "kind": "PLEAT",
            "source": {"node_id": "shell", "port_id": "waist"},
            "parameters": {"count": 1, "depth_cm": 1.0},
        }]
        result = compiler.compile(spec)
        self.assertEqual(result["verdict"],
                         "REVIEW_SURFACE_MODIFIER_TARGET_REQUIRED")
        self.assertEqual(result["state"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
