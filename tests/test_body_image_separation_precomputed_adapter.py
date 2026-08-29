#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from photoloset.body_image_separation_precomputed_adapter import (
    REQUEST_SCHEMA,
    adapt_and_separate,
    build_provider_output,
    capability_probe,
)


def _authorities(value: object) -> list[str]:
    if isinstance(value, dict):
        result = ([str(value["authority"])] if "authority" in value else [])
        for child in value.values():
            result.extend(_authorities(child))
        return result
    if isinstance(value, list):
        result: list[str] = []
        for child in value:
            result.extend(_authorities(child))
        return result
    return []


def _request(**overrides: object) -> dict:
    request = {
        "schema": REQUEST_SCHEMA,
        "source": {
            "image_digest": "sha256:anonymous-source",
            "width": 8,
            "height": 8,
            "orientation": "UP",
        },
        "provider_id": "offline-semantic-stage",
        "provider_kind": "LOCAL_COREML_PRECOMPUTED",
        "camera": {"view": "FRONT"},
        "selection_mode": "HUMAN_APPROVAL",
    }
    request.update(overrides)
    return request


def _fake_pixels() -> list[int]:
    pixels = [0] * 64
    for y in range(0, 2):
        for x in range(3, 5):
            pixels[y * 8 + x] = 3  # hair proposal
    for y in range(2, 7):
        pixels[y * 8 + 1] = 1  # visible body proposal
    for y in range(2, 6):
        for x in range(2, 6):
            pixels[y * 8 + x] = 2  # garment proposal
    return pixels


class PrecomputedBodyImageSeparationAdapterTests(unittest.TestCase):
    maxDiff = None

    def test_capability_probe_is_offline_and_names_vision_semantic_gap(self) -> None:
        result = capability_probe()

        self.assertEqual(result["verdict"], "ANSWER")
        self.assertTrue(result["routes"]["typed_polygon_bundle"]["ready"])
        self.assertFalse(result["network_used"])
        self.assertFalse(result["model_download_attempted"])
        self.assertFalse(result["routes"]["macos_vision"]["direct_python_runtime"])
        self.assertIn(
            "GARMENT or HAIR",
            result["routes"]["macos_vision"]["semantic_gap"],
        )
        self.assertFalse(result["manufacturing_ready"])

    def test_import_has_no_model_or_network_stack_side_effects(self) -> None:
        code = """
import json, sys
import photoloset.body_image_separation_precomputed_adapter
print(json.dumps(sorted(name for name in sys.modules if name.split('.')[0] in {
    'PIL', 'torch', 'torchvision', 'transformers', 'open_clip', 'requests', 'urllib3'
})))
"""
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout), [])

    def test_fake_raster_and_bottom_left_pose_feed_existing_boundary(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png") as handle:
            request = _request(
                provenance={
                    "producer": "local-test-double",
                    "model_id": "offline-semantic-fixture",
                    "model_revision": "sha256:fixture-revision",
                    "source_artifact": "classes.png",
                },
                segmentation={
                    "path": handle.name,
                    "class_map": [
                        {"class": "BACKGROUND", "pixel": 0},
                        {"class": "BODY", "pixel": 1},
                        {"class": "GARMENT", "pixel": 2},
                        {"class": "HAIR", "pixel": 3},
                    ],
                    "min_component_pixels": 4,
                },
                pose={
                    "coordinate_space": "PIXELS",
                    "origin": "BOTTOM_LEFT",
                    "keypoints": {
                        "nose": {"x": 4, "y": 6, "confidence": 0.9},
                        "left_ankle": {"x": 3, "y": 1, "confidence": 0.7},
                    },
                },
            )

            result = adapt_and_separate(
                request,
                raster_loader=lambda _path: (8, 8, _fake_pixels()),
            )

        self.assertEqual(
            result["verdict"],
            "PROPOSED_BODY_GARMENT_SEPARATION_CANDIDATES",
        )
        self.assertEqual(len(result["separation"]["candidates"]), 3)
        provenance = result["adapter"]["provider_provenance"]
        self.assertEqual(provenance["producer"], "local-test-double")
        self.assertEqual(provenance["model_revision"], "sha256:fixture-revision")
        self.assertFalse(provenance["is_correctness_evidence"])
        availability = result["adapter"]["channel_availability"]
        self.assertTrue(all(availability[name]["available"] for name in (
            "BODY", "GARMENT", "HAIR", "BACKGROUND")))
        pose = {
            row["name"]: row
            for row in result["adapter"]["provider_output"]["pose_keypoints"]
        }
        self.assertEqual([pose["nose"]["x"], pose["nose"]["y"]], [0.5, 0.25])
        self.assertEqual(pose["nose"]["authority"], "MODEL_PROPOSED")
        self.assertTrue(all(
            row["mask_digest"]
            for row in result["adapter"]["provider_output"]["masks"]
        ))

    def test_body_pixels_never_become_body_measurements_or_manufacturing(self) -> None:
        request = _request(masks=[{
            "mask_id": "visible-body",
            "class": "BODY",
            "authority": "MEASURED",
            "outline": [[0.2, 0.1], [0.8, 0.1], [0.7, 0.9], [0.3, 0.9]],
        }])
        result = adapt_and_separate(request)
        candidate = result["separation"]["candidates"][0]

        self.assertNotIn("MEASURED", _authorities(result))
        self.assertEqual(candidate["body_shape"]["dimension_ranges_cm"], {})
        self.assertFalse(
            candidate["body_shape"]["clothed_silhouette_measured_as_body"])
        self.assertEqual(result["rear_state"], "UNKNOWN_UNOBSERVED")
        self.assertEqual(
            candidate["back_generation_conditioning"]["rear_state"],
            "UNKNOWN_UNOBSERVED",
        )
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])
        self.assertEqual(result["fact_promotions"], [])

    def test_missing_semantic_channel_is_explicit_unknown(self) -> None:
        result = build_provider_output(_request(masks=[{
            "mask_id": "garment-only",
            "class": "GARMENT",
            "mask_digest": "sha256:garment",
        }]))
        masks = {
            row["class"]: row for row in result["provider_output"]["masks"]
        }

        self.assertTrue(result["channel_availability"]["GARMENT"]["available"])
        self.assertFalse(result["channel_availability"]["HAIR"]["available"])
        self.assertEqual(masks["HAIR"]["authority"], "UNKNOWN")
        self.assertIsNone(masks["HAIR"]["mask_digest"])
        self.assertNotIn("outline", masks["HAIR"])

    def test_local_only_alignment_and_polygon_failures_stop_typed(self) -> None:
        remote = build_provider_output(_request(segmentation={
            "path": "https://example.invalid/mask.png",
            "class_map": [],
        }))
        self.assertEqual(remote["verdict"], "UNKNOWN_PRECOMPUTED_SEPARATION_LOCAL_ONLY")

        outside = build_provider_output(_request(masks=[{
            "class": "GARMENT",
            "outline": [[0.0, 0.0], [1.1, 0.0], [0.0, 1.0]],
        }]))
        self.assertEqual(outside["verdict"], "UNKNOWN_PRECOMPUTED_SEPARATION_MASK_RANGE")

        with tempfile.NamedTemporaryFile(suffix=".png") as handle:
            misaligned = build_provider_output(
                _request(segmentation={
                    "path": handle.name,
                    "class_map": [{"class": "GARMENT", "pixel": 1}],
                }),
                raster_loader=lambda _path: (4, 4, [1] * 16),
            )
        self.assertEqual(
            misaligned["verdict"],
            "UNKNOWN_PRECOMPUTED_SEPARATION_MASK_ALIGNMENT",
        )

    def test_explicit_ids_and_pose_names_make_order_deterministic(self) -> None:
        masks = [
            {
                "mask_id": "body",
                "class": "BODY",
                "outline": [[0.2, 0.1], [0.8, 0.1], [0.7, 0.9], [0.3, 0.9]],
            },
            {
                "mask_id": "garment",
                "class": "GARMENT",
                "outline": [[0.25, 0.2], [0.75, 0.2], [0.7, 0.8], [0.3, 0.8]],
            },
        ]
        pose = {
            "coordinate_space": "NORMALIZED",
            "origin": "TOP_LEFT",
            "keypoints": {
                "right_shoulder": {"x": 0.6, "y": 0.2},
                "left_shoulder": {"x": 0.4, "y": 0.2},
            },
        }
        first = _request(masks=masks, pose=pose)
        second = copy.deepcopy(first)
        second["masks"].reverse()
        second["pose"]["keypoints"] = dict(reversed(list(
            second["pose"]["keypoints"].items())))

        self.assertEqual(
            build_provider_output(first),
            build_provider_output(second),
        )

    def test_default_png_loader_consumes_indexed_local_mask(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is optional for polygon-only installations")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "classes.png"
            image = Image.new("L", (8, 8))
            image.putdata(_fake_pixels())
            image.save(path)
            result = build_provider_output(_request(segmentation={
                "path": str(path),
                "class_map": [
                    {"class": "BACKGROUND", "pixel": 0},
                    {"class": "BODY", "pixel": 1},
                    {"class": "GARMENT", "pixel": 2},
                    {"class": "HAIR", "pixel": 3},
                ],
                "min_component_pixels": 4,
            }))

        self.assertEqual(result["verdict"], "PROPOSED_PRECOMPUTED_PROVIDER_OUTPUT")
        self.assertFalse(result["network_used"])
        self.assertFalse(result["model_download_attempted"])
        self.assertTrue(all(
            row["available"] for row in result["channel_availability"].values()
        ))


if __name__ == "__main__":
    unittest.main()
