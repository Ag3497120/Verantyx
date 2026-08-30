#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import unittest

from photoloset.body_avatar_fit import (
    PREVIEW_AVATAR_PROFILES,
    REQUEST_SCHEMA,
    fit_body_avatar,
)
from photoloset.same_camera_projection import prepare_same_camera_projection


def _mask(
    mask_id: str, mask_class: str, outline: list[list[float]], *,
    authority: str = "OBSERVED", unit: str | None = None,
    layer: int | None = None,
) -> dict:
    return {
        "mask_id": mask_id,
        "class": mask_class,
        "outline": outline,
        "mask_digest": "sha256:" + mask_id,
        "confidence": 0.91,
        "authority": authority,
        "garment_unit_id": unit,
        "layer": layer,
    }


def _pose() -> list[dict]:
    return [
        {"name": "nose", "point": [0.50, 0.08], "confidence": 0.94,
         "authority": "PROPOSED"},
        {"name": "left_shoulder", "point": [0.38, 0.24],
         "confidence": 0.93, "authority": "PROPOSED"},
        {"name": "right_shoulder", "point": [0.62, 0.24],
         "confidence": 0.92, "authority": "PROPOSED"},
        {"name": "left_hip", "point": [0.44, 0.54], "confidence": 0.89,
         "authority": "PROPOSED"},
        {"name": "right_hip", "point": [0.56, 0.54], "confidence": 0.89,
         "authority": "PROPOSED"},
        {"name": "left_ankle", "point": [0.46, 0.93],
         "confidence": 0.86, "authority": "PROPOSED"},
        {"name": "right_ankle", "point": [0.54, 0.93],
         "confidence": 0.86, "authority": "PROPOSED"},
    ]


def _separation(*, view: str = "FRONT", layered: bool = False) -> dict:
    masks = [
        _mask(
            "visible-subject", "BODY",
            [[0.43, 0.06], [0.57, 0.06], [0.68, 0.28],
             [0.62, 0.94], [0.38, 0.94], [0.32, 0.28]],
            authority="PROPOSED",
        ),
    ]
    if layered:
        masks.extend([
            _mask(
                "blouse", "GARMENT",
                [[0.34, 0.20], [0.66, 0.20], [0.64, 0.55], [0.36, 0.55]],
                unit="blouse", layer=0,
            ),
            _mask(
                "trousers", "GARMENT",
                [[0.38, 0.52], [0.62, 0.52], [0.59, 0.94], [0.41, 0.94]],
                unit="trousers", layer=0,
            ),
            _mask(
                "sheer-overlay", "GARMENT",
                [[0.50, 0.52], [0.70, 0.56], [0.66, 0.88], [0.49, 0.73]],
                unit="overlay", layer=1,
            ),
        ])
    else:
        masks.append(_mask(
            "dress", "GARMENT",
            [[0.35, 0.22], [0.65, 0.22], [0.72, 0.89], [0.28, 0.89]],
            unit="dress", layer=0,
        ))
    yaw = 0.0 if view == "FRONT" else -27.0
    candidate = {
        "schema": "garment.body-image-separation-candidate.v1",
        "candidate_id": "separation:front-fixture",
        "candidate_digest": "sha256:separation-candidate",
        "provider_id": "offline-vision-fixture",
        "provider_result_digest": "sha256:provider-result",
        "policy_rank": 1,
        "pose_keypoints": _pose(),
        "masks": masks,
        "camera": {
            "view": view,
            "yaw_deg": yaw,
            "width_px": 1000,
            "height_px": 1600,
            "camera_digest": "camera:" + view.lower(),
            "authority": "PROPOSED",
        },
        "back_generation_conditioning": {
            "rear_state": "UNKNOWN_UNOBSERVED",
        },
    }
    return {
        "schema": "garment.body-image-separation.v1",
        "verdict": "PROPOSED_BODY_GARMENT_SEPARATION_CANDIDATES",
        "contract_digest": "sha256:separation-contract",
        "source": {
            "image_digest": "sha256:portrait-source",
            "width": 1000,
            "height": 1600,
            "orientation": "UP",
        },
        "candidates": [candidate],
        "selection": {
            "selected_candidate_id": candidate["candidate_id"],
        },
        "rear_state": "UNKNOWN_UNOBSERVED",
    }


def _request(**updates: object) -> dict:
    request = {
        "schema": REQUEST_SCHEMA,
        "separation": _separation(),
    }
    request.update(updates)
    return request


class BodyAvatarFitTests(unittest.TestCase):
    maxDiff = None

    def test_portrait_fit_uses_requested_height_and_feeds_same_camera(self) -> None:
        request = _request(
            requested_measurements={
                "height": {
                    "value": 176.0, "unit": "cm", "authority": "REQUESTED",
                    "source": {"kind": "USER_REQUEST", "reference": "brief"},
                },
                "waist": {
                    "value": 73.5, "unit": "cm", "authority": "REQUESTED",
                    "source": {"kind": "USER_REQUEST", "reference": "brief"},
                },
            },
            interpolation={
                "method": "LINEAR_BOUNDED",
                "allowed_dimensions": ["height"],
            },
        )

        result = fit_body_avatar(request)

        self.assertEqual(
            result["verdict"], "PROPOSED_IMAGE_RELATIVE_BODY_AVATAR_FIT")
        self.assertEqual(result["source"]["aspect"], "PORTRAIT")
        self.assertEqual(len(PREVIEW_AVATAR_PROFILES), 10)
        self.assertEqual(result["profile_catalog"]["count"], 10)
        avatar = result["selected_avatar"]
        self.assertEqual(avatar["dimensions_cm"]["height"], 176.0)
        self.assertNotEqual(avatar["dimensions_cm"]["waist"], 73.5)
        self.assertEqual(
            [row["dimension"] for row in result["interpolation"]["operations"]],
            ["height"],
        )
        self.assertEqual(
            result["interpolation"]["unapplied_requested_dimensions"],
            ["waist"],
        )
        fit = result["image_relative_fit"]
        self.assertGreater(
            fit["world_to_image"]["uniform_scale_px_per_preview_cm"], 0.0)
        self.assertFalse(fit["pixel_fit_changes_avatar_measurements"])
        self.assertTrue(result["front_projection_ready"])

        comparison_request = copy.deepcopy(result["front_projection_contract"])
        comparison_request["candidate"] = {
            "candidate_id": "garment-mesh",
            "vertices": [
                [-1.0, 1.0, 0.0], [1.0, 1.0, 0.0],
                [1.0, -1.0, 0.0], [-1.0, -1.0, 0.0],
            ],
            "faces": [[0, 1, 2], [0, 2, 3]],
        }
        comparison = prepare_same_camera_projection(comparison_request)
        self.assertEqual(
            comparison["verdict"], "PROPOSED_SAME_CAMERA_COMPARISON")
        self.assertEqual(
            comparison["base_avatar"]["geometry_digest"],
            avatar["geometry_digest"],
        )

    def test_oblique_fit_keeps_rotation_proposed_and_rear_unknown(self) -> None:
        result = fit_body_avatar({
            "schema": REQUEST_SCHEMA,
            "separation": _separation(view="OBLIQUE_LEFT"),
        })

        rotation = result["image_relative_fit"]["preview_rotation"]
        self.assertEqual(rotation["view"], "OBLIQUE_LEFT")
        self.assertEqual(rotation["yaw_deg"], -27.0)
        self.assertEqual(rotation["basis"], "TYPED_CAMERA_YAW")
        self.assertTrue(rotation["does_not_observe_rear"])
        self.assertEqual(result["rear"]["body_state"], "UNKNOWN_UNOBSERVED")
        self.assertEqual(result["rear"]["garment_state"], "UNKNOWN_UNOBSERVED")
        self.assertEqual(
            result["rear"]["preview_avatar_rear_state"],
            "PROPOSED_PARAMETRIC",
        )
        self.assertFalse(result["claims"]["rear_observed"])

    def test_layered_clothing_preserves_component_targets_and_layers(self) -> None:
        result = fit_body_avatar({
            "schema": REQUEST_SCHEMA,
            "separation": _separation(layered=True),
        })

        targets = result["garment_projection_targets"]
        self.assertEqual(len(targets), 3)
        self.assertEqual(
            [(row["garment_unit_id"], row["layer"]) for row in targets],
            [("blouse", 0), ("trousers", 0), ("overlay", 1)],
        )
        aggregate = result["front_projection_contract"]["target"]
        self.assertEqual(
            aggregate["component_mask_ids"],
            ["blouse", "trousers", "sheer-overlay"],
        )
        self.assertTrue(aggregate["convex_envelope_is_not_part_segmentation"])
        self.assertEqual(aggregate["state"], "OBSERVED")
        self.assertFalse(result["manufacturing_ready"])

    def test_missing_front_geometry_stops_typed_even_with_requested_height(self) -> None:
        separation = _separation()
        candidate = separation["candidates"][0]
        candidate["pose_keypoints"] = []
        for mask in candidate["masks"]:
            mask["outline"] = []

        result = fit_body_avatar({
            "schema": REQUEST_SCHEMA,
            "separation": separation,
            "requested_height_cm": 170.0,
        })

        self.assertEqual(
            result["verdict"], "UNKNOWN_BODY_AVATAR_FIT_EVIDENCE_REQUIRED")
        self.assertEqual(result["state"], "UNKNOWN")
        self.assertEqual(result["rear_state"], "UNKNOWN_UNOBSERVED")
        self.assertFalse(result["claims"]["body_measurements_inferred_from_pixels"])
        self.assertFalse(result["manufacturing_ready"])

    def test_reordering_pose_masks_and_requested_mapping_is_deterministic(self) -> None:
        first = _request(
            separation=_separation(layered=True),
            requested_measurements={
                "height": {"value": 174.0, "unit": "cm",
                           "authority": "REQUESTED"},
                "hip": {"value": 101.0, "unit": "cm",
                        "authority": "REQUESTED"},
            },
            interpolation={
                "method": "LINEAR_BOUNDED",
                "allowed_dimensions": ["height"],
            },
        )
        second = copy.deepcopy(first)
        second["separation"]["candidates"][0]["pose_keypoints"].reverse()
        second["separation"]["candidates"][0]["masks"].reverse()
        second["requested_measurements"] = dict(reversed(list(
            second["requested_measurements"].items())))

        self.assertEqual(fit_body_avatar(first), fit_body_avatar(second))

    def test_pixel_shape_cannot_be_submitted_as_measured_dimension(self) -> None:
        request = _request(requested_measurements={
            "waist": {
                "value": 76.0,
                "unit": "cm",
                "authority": "MEASURED",
                "source": {
                    "kind": "FRONT_IMAGE_ESTIMATE",
                    "reference": "segmentation-width",
                },
            },
        })

        result = fit_body_avatar(request)

        self.assertEqual(
            result["verdict"],
            "UNKNOWN_BODY_AVATAR_FIT_PIXEL_MEASUREMENT_REFUSED",
        )
        self.assertFalse(result["claims"]["body_measurements_inferred_from_pixels"])


if __name__ == "__main__":
    unittest.main()
