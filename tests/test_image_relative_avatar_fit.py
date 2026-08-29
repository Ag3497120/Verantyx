# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import unittest

from photoloset.target_reconstruction import prepare_target_reconstruction


def _request(height: float = 176.0) -> dict:
    return {
        "schema": "garment.target-reconstruction.request.v1",
        "source": {"image_digest": "fused-standing-subject"},
        "camera_digest": "front-camera",
        "base_avatar": {
            "avatar_id": "selected-body",
            "kind": "PARAMETRIC_GAME_AVATAR",
            "authority": "REQUESTED",
            "geometry_digest": "selected-body-geometry",
            "measurements_cm": {
                "height": height,
                "chest_bust": 94.0,
                "waist": 71.0,
                "hip": 101.0,
            },
        },
        "reconstruction": {
            "fallback": {
                "outline": [
                    [46, 4], [55, 5], [61, 16], [72, 23], [68, 40],
                    [84, 62], [78, 98], [58, 99], [52, 61], [46, 99],
                    [25, 97], [22, 58], [35, 38], [31, 22], [42, 15],
                ],
                "width_px": 100,
                "height_px": 104,
                "target_role": "FUSED_PERSON_AND_GARMENT_CAD_TARGET",
                "selection_mode": "FOREGROUND_SUBJECT_MASK",
            },
        },
        "regions": [
            {
                "id": "fused-subject",
                "class": "garment",
                "state": "PROPOSED",
                "target_role": "FUSED_PERSON_AND_GARMENT_CAD_TARGET",
                "outline": [
                    [46, 4], [55, 5], [61, 16], [72, 23], [68, 40],
                    [84, 62], [78, 98], [58, 99], [52, 61], [46, 99],
                    [25, 97], [22, 58], [35, 38], [31, 22], [42, 15],
                ],
            },
        ],
        "edits": {"remove_region_ids": []},
    }


class ImageRelativeAvatarFitTests(unittest.TestCase):
    def test_fused_subject_height_uses_selected_scale_without_measurement_claim(self) -> None:
        result = prepare_target_reconstruction(_request())
        surface = result["sculpt_surface"]
        fit = surface["image_proportion_fit"]

        self.assertEqual(fit["authority"], "PROPOSED_IMAGE_PROPORTION_FIT")
        self.assertEqual(fit["basis"],
                         "FUSED_SUBJECT_OUTLINE_AND_MESH_BOUNDS")
        self.assertEqual(fit["selected_avatar_inputs"]["state"], "SELECTED")
        self.assertEqual(fit["selected_avatar_inputs"]["authority"],
                         "REQUESTED_OR_SELECTED")
        self.assertEqual(fit["selected_avatar_inputs"]["height_cm"], 176.0)
        self.assertEqual(fit["selected_avatar_inputs"]["chest_bust_cm"], 94.0)
        self.assertEqual(fit["selected_avatar_inputs"]["waist_cm"], 71.0)
        self.assertEqual(fit["selected_avatar_inputs"]["hip_cm"], 101.0)
        self.assertTrue(fit["visual_fit_does_not_change_selected_measurements"])
        self.assertIn("actual wearer height", fit["does_not_observe"])
        self.assertAlmostEqual(
            fit["subject_mesh_bounds_cm"]["head_to_foot_height"], 176.0,
            places=5)

    def test_selected_height_changes_world_scale_not_image_evidence(self) -> None:
        first = prepare_target_reconstruction(_request(160.0))["sculpt_surface"]
        second = prepare_target_reconstruction(_request(184.0))["sculpt_surface"]

        self.assertEqual(first["image_proportion_fit"]["subject_bounds_px"],
                         second["image_proportion_fit"]["subject_bounds_px"])
        self.assertAlmostEqual(
            first["image_proportion_fit"]["subject_mesh_bounds_cm"]
            ["head_to_foot_height"], 160.0, places=5)
        self.assertAlmostEqual(
            second["image_proportion_fit"]["subject_mesh_bounds_cm"]
            ["head_to_foot_height"], 184.0, places=5)

    def test_uv_top_remains_v_zero_convention(self) -> None:
        surface = prepare_target_reconstruction(_request())["sculpt_surface"]
        half = len(surface["vertices_cm"]) // 2
        front = surface["vertices_cm"][:half]
        uv = surface["texture_coordinates"][:half]
        top = max(range(half), key=lambda index: front[index][1])
        bottom = min(range(half), key=lambda index: front[index][1])

        self.assertEqual(surface["image_proportion_fit"]["texture_convention"],
                         "IMAGE_TOP_IS_TEXTURE_V_0")
        self.assertLess(uv[top][1], uv[bottom][1])

    def test_non_fused_fallback_does_not_gain_image_body_fit_authority(self) -> None:
        request = copy.deepcopy(_request())
        request["reconstruction"]["fallback"].pop("target_role")
        request["regions"][0].pop("target_role")
        result = prepare_target_reconstruction(request)

        self.assertIsNone(result["sculpt_surface"]["image_proportion_fit"])


if __name__ == "__main__":
    unittest.main()
