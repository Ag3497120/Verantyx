# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import unittest

from photoloset import mcp


class TargetReconstructionMCPTests(unittest.TestCase):
    def test_tool_is_registered_and_authority_is_bounded(self) -> None:
        self.assertIn("garment_target_reconstruction_prepare", mcp.TOOLS)
        request = {
            "schema": "garment.target-reconstruction.request.v1",
            "source": {"image_digest": "image-a"},
            "camera_digest": "camera-a",
            "base_avatar": {
                "avatar_id": "balanced-170",
                "kind": "PARAMETRIC_GAME_AVATAR",
                "authority": "PROPOSED_PREVIEW",
                "geometry_digest": "avatar-a",
                "measurements_cm": {
                    "height": 170, "chest_bust": 90,
                    "waist": 72, "hip": 96,
                },
            },
            "reconstruction": {"fallback": {"silhouette_digest": "outline-a"}},
            "regions": [
                {"id": "background", "class": "BACKGROUND", "state": "OBSERVED"},
                {"id": "hair", "class": "HAIR", "state": "OBSERVED",
                 "occludes_garment": True, "overlap_part_ids": ["blouse"]},
                {"id": "blouse", "class": "GARMENT", "state": "PROPOSED"},
            ],
            "edits": {"remove_region_ids": ["background", "hair"]},
        }
        result = json.loads(mcp.TOOLS["garment_target_reconstruction_prepare"](
            json.dumps(request)))
        self.assertEqual(result["verdict"], "PROPOSED_TARGET_RECONSTRUCTION")
        self.assertEqual(
            result["completion_proposals"][0]["state"],
            "PROPOSED_OCCLUSION_BACKFILL")
        self.assertTrue(result["human_approval_required"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertEqual(result["fact_promotions"], [])

    def test_target_bound_candidate_tool_preserves_front_authority(self) -> None:
        self.assertIn("garment_target_bound_candidate_preview", mcp.TOOLS)
        structure_request = {
            "candidate_id": "typed-option",
            "structure": {
                "schema": "garment.structure.v1",
                "nodes": [{
                    "node_id": "surface-shell", "kind": "BODY_SHELL",
                    "layer": 0,
                    "dimensions": {
                        "height_cm": 62.0, "circumference_cm": 90.0,
                    },
                }],
                "operations": [],
            },
            "candidate_state": "PROPOSED",
        }
        preview = json.loads(mcp.TOOLS["garment_structure_preview"](
            json.dumps(structure_request)))
        request = {
            "schema": "garment.target-bound-candidate-preview.request.v1",
            "candidate_id": "typed-option",
            "front_target": {
                "vertices_cm": [[-10, 20, 12], [10, 20, 12],
                                [8, -20, 13], [-9, -20, 13]],
                "faces": [[0, 2, 1], [0, 3, 2]],
                "face_region_ids": ["front-visible-surface"] * 2,
                "face_component_ids": ["visible-front"] * 2,
                "authority": "HUMAN_APPROVED_FOR_FRONT_COMPARISON",
                "digest": "approved-front-a",
            },
            "candidate_preview": preview,
            "base_avatar": {
                "avatar_id": "balanced-170",
                "kind": "PARAMETRIC_GAME_AVATAR",
                "authority": "PROPOSED_PREVIEW",
                "geometry_digest": "avatar-a",
                "measurements_cm": {
                    "height": 170, "chest_bust": 90,
                    "waist": 72, "hip": 96,
                },
            },
        }
        result = json.loads(mcp.TOOLS[
            "garment_target_bound_candidate_preview"](json.dumps(request)))
        self.assertEqual(result["verdict"], "ANSWER", result)
        self.assertEqual(result["authority"]["front"],
                         "HUMAN_APPROVED_FOR_FRONT_COMPARISON")
        self.assertEqual(result["authority"]["rear"], "PROPOSED")
        self.assertTrue(result["binding"]["front_fixed"])
        self.assertTrue(result["human_approval_required"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])
        self.assertEqual(result["fact_promotions"], [])


if __name__ == "__main__":
    unittest.main()
