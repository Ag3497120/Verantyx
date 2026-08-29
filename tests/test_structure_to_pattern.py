#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import json
import unittest

from photoloset import structure_to_pattern as compiler


def dress(back="center_back_zip"):
    return {
        "schema": "garment.structure.v1",
        "nodes": [
            {"node_id": "bodice", "kind": "BODY_SHELL",
             "dimensions": {"height_cm": 40.0, "circumference_cm": 80.0},
             "attributes": {"back_design": back},
             "ports": [{"port_id": "waist_bottom", "length_cm": 80.0,
                         "interface": "waist", "role": "loop"}]},
            {"node_id": "skirt", "kind": "FLARE",
             "dimensions": {"height_cm": 70.0,
                            "top_circumference_cm": 80.0,
                            "bottom_circumference_cm": 220.0},
             "ports": [{"port_id": "waist_top", "length_cm": 80.0,
                         "interface": "waist", "role": "loop"}]},
        ],
        "operations": [{"operation_id": "waist", "kind": "JOIN",
                        "source": {"node_id": "bodice", "port_id": "waist_bottom"},
                        "target": {"node_id": "skirt", "port_id": "waist_top"}}],
    }


class StructureToPatternTests(unittest.TestCase):
    def test_body_and_flare_compile_to_candidate_specific_cuttable_baseline(self):
        result = compiler.compile(dress(), candidate_id="back-a")
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual([p["piece_id"] for p in result["pieces"]],
                         ["bodice", "skirt"])
        self.assertTrue(result["cuttable_geometric_prototype"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertEqual(result["candidate_state"], "PROPOSED")
        waist = next(s for s in result["seams"] if s["operation_id"] == "waist")
        self.assertEqual((waist["a"]["edge"], waist["b"]["edge"]), ("e0", "e2"))
        self.assertTrue(next(c for c in result["seam_checks"]
                             if c["operation_id"] == "waist")["geometrically_sewable"])
        json.dumps(result, allow_nan=False)

    def test_back_hypothesis_changes_artifact_but_never_becomes_observed(self):
        a = compiler.compile(dress("center_back_zip"), candidate_id="a")
        b = compiler.compile(dress("closed_stretch_back"), candidate_id="b")
        self.assertNotEqual(a["digest"], b["digest"])
        self.assertEqual(a["pieces"][0]["construction_features"][0]["state"],
                         "PROPOSED")
        self.assertFalse(a["provenance"]["front_only_unknowns_promoted"])
        self.assertFalse(a["manufacturing_ready"])

    def test_layers_and_sleeves_preserve_quantity_and_relation(self):
        spec = dress()
        spec["nodes"] += [
            {"node_id": "sleeve", "kind": "SLEEVE", "layer": 0,
             "dimensions": {"length_cm": 58.0,
                            "upper_circumference_cm": 36.0,
                            "cuff_circumference_cm": 22.0}},
            {"node_id": "cape", "kind": "OVERLAY", "layer": 1,
             "dimensions": {"height_cm": 65.0, "width_cm": 120.0},
             "ports": [{"port_id": "anchor", "length_cm": 10.0,
                         "interface": "layer_anchor"}]},
            {"node_id": "bodice-anchor", "kind": "BAND", "layer": 0,
             "dimensions": {"length_cm": 10.0, "width_cm": 2.0},
             "ports": [{"port_id": "anchor", "length_cm": 10.0,
                         "interface": "layer_anchor"}]},
        ]
        spec["operations"].append({
            "operation_id": "cape-layer", "kind": "LAYER",
            "source": {"node_id": "cape", "port_id": "anchor"},
            "target": {"node_id": "bodice-anchor", "port_id": "anchor"},
        })
        result = compiler.compile(spec)
        self.assertEqual(result["verdict"], "ANSWER")
        sleeve_pieces = [p for p in result["pieces"]
                         if p["primitive_kind"] == "SLEEVE"]
        self.assertEqual([p["piece_id"] for p in sleeve_pieces],
                         ["sleeve:left", "sleeve:right"])
        self.assertTrue(all(p["cut_count"] == 1 for p in sleeve_pieces))
        self.assertEqual(result["candidate_specific_expansions"][0]["kind"],
                         "BODICE_SET_IN_SLEEVE_BRIDGE")
        self.assertEqual(result["layers"][0]["operation_id"], "cape-layer")

    def test_gather_is_an_addressed_transform_not_a_label(self):
        spec = {
            "schema": "garment.structure.v1",
            "nodes": [
                {"node_id": "ruffle", "kind": "BAND",
                 "dimensions": {"length_cm": 150.0, "width_cm": 12.0},
                 "ports": [{"port_id": "long", "length_cm": 150.0,
                             "interface": "ruffle_join"}]},
                {"node_id": "hem", "kind": "BAND",
                 "dimensions": {"length_cm": 100.0, "width_cm": 2.0},
                 "ports": [{"port_id": "join", "length_cm": 100.0,
                             "interface": "ruffle_join"}]},
            ],
            "operations": [{
                "operation_id": "gather-ruffle", "kind": "GATHER",
                "source": {"node_id": "ruffle", "port_id": "long"},
                "target": {"node_id": "hem", "port_id": "join"},
                "parameters": {"ratio": 1.5},
            }],
        }
        result = compiler.compile(spec)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["transforms"][0]["kind"], "GATHER")
        self.assertEqual(result["transforms"][0]["ratio"], 1.5)

    def test_invalid_and_unimplemented_geometry_fail_closed(self):
        missing = dress()
        del missing["nodes"][1]["dimensions"]["height_cm"]
        self.assertEqual(compiler.compile(missing)["verdict"],
                         "UNKNOWN_PRIMITIVE_DIMENSION_MISSING")
        unsupported = dress()
        unsupported["operations"] = [{
            "operation_id": "cut", "kind": "CUTOUT",
            "source": {"node_id": "bodice", "port_id": "waist_bottom"},
        }]
        self.assertEqual(compiler.compile(unsupported)["verdict"],
                         "UNKNOWN_CUTOUT_POLYGON")

    def test_approval_does_not_skip_manufacturing_gates(self):
        result = compiler.compile(
            dress(), candidate_state="APPROVED", candidate_id="a",
            approval={"by": "Pattern reviewer", "digest": "sha256:candidate"})
        self.assertEqual(result["candidate_state"], "APPROVED")
        self.assertIsNotNone(result["approval"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertGreaterEqual(len(result["remaining_gates"]), 4)

    def test_approved_state_without_human_digest_is_refused(self):
        result = compiler.compile(dress(), candidate_state="APPROVED")
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PATTERN_APPROVAL_REQUIRED")


if __name__ == "__main__":
    unittest.main()
