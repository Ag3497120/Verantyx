#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import math
import unittest

from photoloset.body_image_separation import separate_body_image


def _active_authorities(value: object) -> list[str]:
    if isinstance(value, dict):
        result = ([str(value["authority"])] if "authority" in value else [])
        for child in value.values():
            result.extend(_active_authorities(child))
        return result
    if isinstance(value, list):
        result: list[str] = []
        for child in value:
            result.extend(_active_authorities(child))
        return result
    return []


def _mask(
    mask_id: str, mask_class: str, *, unit: str | None = None,
    layer: int | None = None, authority: str = "PROPOSED",
) -> dict:
    row = {
        "mask_id": mask_id,
        "class": mask_class,
        "mask_digest": "sha256:" + mask_id,
        "confidence": 0.8,
        "authority": authority,
    }
    if unit is not None:
        row["garment_unit_id"] = unit
    if layer is not None:
        row["layer"] = layer
    return row


def _provider(
    provider_id: str, *, presentation: str, view: str,
    composition: str,
) -> dict:
    garments = (
        [
            _mask("g-upper", "GARMENT", unit="unit-upper", layer=0),
            _mask("g-lower", "GARMENT", unit="unit-lower", layer=0),
        ]
        if composition == "SEPARATES" else
        [
            _mask("g-base", "GARMENT", unit="unit-base", layer=0),
            _mask("g-overlay", "GARMENT", unit="unit-overlay", layer=1),
        ]
    )
    return {
        "provider_id": provider_id,
        "provider_kind": "EXTERNAL_PRECOMPUTED_VISION",
        "authority": "MODEL_PROPOSED",
        # Deliberately ignored by the contract: geometry is not selected from
        # a gender label or identity class.
        "subject_metadata": {"presentation": presentation},
        "pose_keypoints": {
            "left_shoulder": {
                "x": 0.39, "y": 0.22, "confidence": 0.91,
                "authority": "PROPOSED",
            },
            "right_shoulder": {
                "x": 0.61, "y": 0.23, "confidence": 0.9,
                "authority": "PROPOSED",
            },
            "left_ankle": {
                "x": 0.46, "y": 0.91, "confidence": 0.86,
                "authority": "UNKNOWN",
            },
        },
        "exposed_skin_contours": [{
            "contour_id": "skin-face",
            "body_region": "FACE",
            "points": [[0.46, 0.05], [0.54, 0.05], [0.55, 0.15]],
            "authority": "PROPOSED",
        }],
        "masks": [
            _mask("m-body", "BODY", authority="PROPOSED"),
            *garments,
            _mask("m-hair", "HAIR", authority="UNKNOWN"),
            _mask("m-background", "BACKGROUND", authority="OBSERVED"),
        ],
        "camera": {
            "view": view,
            "width_px": 1200,
            "height_px": 1800,
            "yaw_deg": 0 if view == "FRONT" else 27,
            "authority": "PROPOSED",
        },
        "occlusions": [{
            "occlusion_id": "occ-1",
            "occluder_mask_id": (
                "g-upper" if composition == "SEPARATES" else "g-overlay"),
            "occluded_mask_id": "m-body",
            "relation": "OCCLUDES",
            "authority": "PROPOSED",
        }],
        "body_shape": {
            "dimension_ranges_cm": {
                "chest_bust": {
                    "minimum": 84, "maximum": 96, "unit": "cm",
                    "authority": "MEASURED",
                },
                "waist": {
                    "minimum": 68, "maximum": 82, "unit": "cm",
                    "authority": "MODEL_PROPOSED",
                },
            },
            "shape_coefficients": {
                "values": [0.1, -0.2, 0.05],
                "authority": "MEASURED",
            },
        },
    }


def _request(provider: dict | None, mode: str = "HUMAN_APPROVAL") -> dict:
    request = {
        "schema": "garment.body-image-separation.request.v1",
        "source": {
            "image_digest": "sha256:anonymous-fixture",
            "width": 1200,
            "height": 1800,
            "orientation": "UP",
        },
        "selection_mode": mode,
    }
    if provider is not None:
        request["provider_outputs"] = [provider]
    return request


class BodyImageSeparationTests(unittest.TestCase):
    maxDiff = None

    def test_anonymous_feminine_front_separates_stays_proposed(self) -> None:
        provider = _provider(
            "provider-front", presentation="FEMININE",
            view="FRONT", composition="SEPARATES",
        )
        result = separate_body_image(_request(provider))

        self.assertEqual(
            result["verdict"],
            "PROPOSED_BODY_GARMENT_SEPARATION_CANDIDATES",
        )
        self.assertEqual(len(result["candidates"]), 3)
        self.assertEqual(result["rear_state"], "UNKNOWN_UNOBSERVED")
        self.assertFalse(result["provider_fallback_used"])
        self.assertEqual(
            result["selection"]["status"], "HUMAN_APPROVAL_REQUIRED")
        candidate = result["candidates"][0]
        self.assertEqual(
            candidate["state"], "PROPOSED_BODY_GARMENT_SEPARATION")
        garment_units = {
            row["garment_unit_id"]
            for row in candidate["masks"] if row["class"] == "GARMENT"
        }
        self.assertEqual(garment_units, {"unit-upper", "unit-lower"})
        self.assertFalse(candidate["manufacturing_ready"])
        self.assertEqual(candidate["fact_promotions"], [])

    def test_anonymous_masculine_oblique_layering_preserves_layers(self) -> None:
        provider = _provider(
            "provider-oblique", presentation="MASCULINE",
            view="OBLIQUE_LEFT", composition="LAYERED",
        )
        result = separate_body_image(_request(provider))
        candidate = result["candidates"][0]

        self.assertEqual(candidate["camera"]["view"], "OBLIQUE_LEFT")
        garment_masks = [
            row for row in candidate["masks"] if row["class"] == "GARMENT"
        ]
        self.assertEqual(
            [(row["garment_unit_id"], row["layer"]) for row in garment_masks],
            [("unit-base", 0), ("unit-overlay", 1)],
        )
        self.assertEqual(
            candidate["occlusions"][0]["occluder_mask_id"], "g-overlay")
        self.assertEqual(
            candidate["back_generation_conditioning"]["rear_state"],
            "UNKNOWN_UNOBSERVED",
        )

    def test_clothed_shape_ranges_and_coefficients_are_never_measured(self) -> None:
        provider = _provider(
            "provider-authority", presentation="FEMININE",
            view="FRONT", composition="SEPARATES",
        )
        result = separate_body_image(_request(provider))
        candidate = result["candidates"][0]
        ranges = candidate["body_shape"]["dimension_ranges_cm"]

        self.assertEqual(ranges["chest_bust"]["authority"], "INFERRED_RANGE")
        self.assertEqual(ranges["chest_bust"]["input_authority"], "INFERRED")
        self.assertFalse(ranges["chest_bust"]["measured_from_clothed_image"])
        coefficients = candidate["body_shape"]["shape_coefficients"]
        self.assertEqual(coefficients["authority"], "INFERRED")
        self.assertTrue(coefficients["not_body_measurements"])
        self.assertFalse(candidate["body_shape"]["clothed_silhouette_measured_as_body"])
        self.assertNotIn("MEASURED", _active_authorities(result))

    def test_input_authority_is_preserved_or_lowered_never_promoted(self) -> None:
        provider = _provider(
            "provider-boundary", presentation="MASCULINE",
            view="OBLIQUE_RIGHT", composition="LAYERED",
        )
        result = separate_body_image(_request(provider))
        masks = {
            row["mask_id"]: row
            for row in result["candidates"][0]["masks"]
        }
        self.assertEqual(masks["m-hair"]["authority"], "UNKNOWN")
        self.assertEqual(masks["m-body"]["authority"], "PROPOSED")
        self.assertEqual(masks["m-background"]["authority"], "OBSERVED")
        pose = {
            row["name"]: row
            for row in result["candidates"][0]["pose_keypoints"]
        }
        self.assertEqual(pose["left_ankle"]["authority"], "UNKNOWN")

    def test_provider_absent_fallback_has_four_unknown_mask_channels(self) -> None:
        request = _request(None)
        request["camera"] = {
            "view": "FRONT", "width_px": 1200, "height_px": 1800,
            "authority": "PROPOSED",
        }
        result = separate_body_image(request)
        candidate = result["candidates"][0]

        self.assertTrue(result["provider_fallback_used"])
        self.assertEqual(len(result["candidates"]), 3)
        self.assertEqual(
            {row["class"] for row in candidate["masks"]},
            {"BODY", "GARMENT", "HAIR", "BACKGROUND"},
        )
        self.assertTrue(all(
            row["authority"] == "UNKNOWN" and row["mask_digest"] is None
            for row in candidate["masks"]
        ))
        conditioning = candidate["back_generation_conditioning"]
        self.assertTrue(conditioning["requires_body_proxy_or_human_dimensions"])
        self.assertEqual(conditioning["body_dimension_ranges_cm"], {})
        review_codes = {row["code"] for row in result["review_items"]}
        self.assertIn("REVIEW_PROVIDER_ABSENT_TYPED_FALLBACK", review_codes)

    def test_auto_selection_remains_proposed_and_cannot_open_manufacturing(self) -> None:
        provider = _provider(
            "provider-auto", presentation="FEMININE",
            view="FRONT", composition="LAYERED",
        )
        result = separate_body_image(_request(provider, "AUTO_PROPOSED"))
        self.assertEqual(
            result["selection"]["selected_candidate_id"],
            result["candidates"][0]["candidate_id"],
        )
        self.assertEqual(result["selection"]["status"], "AUTO_PROPOSED_SELECTED")
        self.assertFalse(result["selection"]["may_open_manufacturing_gate"])
        self.assertTrue(result["selection"]["human_can_override"])
        self.assertFalse(result["manufacturing_certified"])

    def test_is_deterministic_across_provider_mask_and_mapping_order(self) -> None:
        first_provider = _provider(
            "provider-b", presentation="FEMININE",
            view="FRONT", composition="SEPARATES",
        )
        second_provider = _provider(
            "provider-a", presentation="MASCULINE",
            view="OBLIQUE_LEFT", composition="LAYERED",
        )
        request = _request(first_provider)
        request["provider_outputs"] = [first_provider, second_provider]
        reordered = copy.deepcopy(request)
        reordered["provider_outputs"].reverse()
        for provider in reordered["provider_outputs"]:
            provider["masks"].reverse()
            provider["pose_keypoints"] = dict(reversed(list(
                provider["pose_keypoints"].items())))
        self.assertEqual(
            separate_body_image(request), separate_body_image(reordered))

    def test_gender_metadata_alone_does_not_change_geometry_contract(self) -> None:
        first = _provider(
            "provider-neutral", presentation="FEMININE",
            view="FRONT", composition="SEPARATES",
        )
        second = copy.deepcopy(first)
        second["subject_metadata"]["presentation"] = "MASCULINE"
        self.assertEqual(
            separate_body_image(_request(first)),
            separate_body_image(_request(second)),
        )

    def test_non_finite_and_duplicate_masks_stop_typed(self) -> None:
        provider = _provider(
            "provider-invalid", presentation="FEMININE",
            view="FRONT", composition="SEPARATES",
        )
        provider["pose_keypoints"]["left_shoulder"]["x"] = math.nan
        self.assertEqual(
            separate_body_image(_request(provider))["verdict"],
            "UNKNOWN_BODY_IMAGE_SEPARATION_NON_FINITE",
        )
        duplicate = _provider(
            "provider-duplicate", presentation="MASCULINE",
            view="FRONT", composition="LAYERED",
        )
        duplicate["masks"].append(copy.deepcopy(duplicate["masks"][0]))
        self.assertEqual(
            separate_body_image(_request(duplicate))["verdict"],
            "UNKNOWN_BODY_IMAGE_SEPARATION_DUPLICATE_ID",
        )


if __name__ == "__main__":
    unittest.main()
