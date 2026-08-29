#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cross-image regression for the front-only reconstruction boundaries.

This test intentionally separates two responsibilities:

* fixture pixels supply only a geometry-derived outer outline to the target
  reconstruction fallback;
* typed garment parts supply candidate structure, preview 3-D, and pattern
  geometry after the vision boundary.

The same three byte-distinct images are crossed with three anonymous garment
structures.  That makes filename-conditioned branches, a single memorised
image digest, and candidate outputs which ignore structure visible without
claiming that the deterministic core performs semantic pixel recognition.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import struct
import unittest
import zlib

from photoloset import structure_preview
from photoloset.front_candidate_artifact_pipeline import (
    REQUEST_SCHEMA as ARTIFACT_REQUEST_SCHEMA,
    assemble,
    stable_digest as artifact_digest,
)
from photoloset.front_image_generation_contract import (
    REQUEST_SCHEMA as FRONT_REQUEST_SCHEMA,
    REQUIRED_WEARER_MEASUREMENTS,
)
from photoloset.target_reconstruction import (
    prepare_target_reconstruction,
    stable_digest as target_digest,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "generated"
FIXTURES = (
    "anime-garment-cape.png",
    "long-haired-emerald-dress.png",
    "layered-separates-overskirt.png",
)


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    diagonal_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= diagonal_distance:
        return left
    if above_distance <= diagonal_distance:
        return above
    return upper_left


def _read_rgb_png(path: Path) -> tuple[int, int, list[bytes]]:
    """Read the repository's 8-bit RGB fixtures without a test dependency."""
    payload = path.read_bytes()
    if payload[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"{path} is not a PNG")
    position = 8
    width = height = None
    compressed: list[bytes] = []
    while position < len(payload):
        length = struct.unpack(">I", payload[position:position + 4])[0]
        chunk_type = payload[position + 4:position + 8]
        chunk = payload[position + 8:position + 8 + length]
        position += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, colour_type, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", chunk)
            )
            if (bit_depth, colour_type, compression, filtering, interlace) != (
                    8, 2, 0, 0, 0):
                raise AssertionError(
                    "fixture must remain an 8-bit, non-interlaced RGB PNG")
        elif chunk_type == b"IDAT":
            compressed.append(chunk)
        elif chunk_type == b"IEND":
            break
    if width is None or height is None or not compressed:
        raise AssertionError(f"{path} has no usable PNG payload")

    raw = zlib.decompress(b"".join(compressed))
    bytes_per_pixel = 3
    stride = width * bytes_per_pixel
    rows: list[bytes] = []
    previous = bytearray(stride)
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        scanline = bytearray(raw[offset:offset + stride])
        offset += stride
        for index in range(stride):
            left = scanline[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            above = previous[index]
            upper_left = previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            if filter_type == 1:
                scanline[index] = (scanline[index] + left) & 0xFF
            elif filter_type == 2:
                scanline[index] = (scanline[index] + above) & 0xFF
            elif filter_type == 3:
                scanline[index] = (
                    scanline[index] + (left + above) // 2) & 0xFF
            elif filter_type == 4:
                scanline[index] = (
                    scanline[index] + _paeth(left, above, upper_left)) & 0xFF
            elif filter_type != 0:
                raise AssertionError(f"unsupported PNG filter {filter_type}")
        rows.append(bytes(scanline))
        previous = scanline
    if offset != len(raw):
        raise AssertionError("PNG scanline size does not match IHDR")
    return width, height, rows


def _pixel(row: bytes, x: int) -> tuple[int, int, int]:
    offset = x * 3
    return row[offset], row[offset + 1], row[offset + 2]


def _convex_hull(points: list[tuple[int, int]]) -> list[list[float]]:
    unique = sorted(set(points))
    if len(unique) < 3:
        raise AssertionError("foreground extraction produced fewer than 3 points")

    def cross(origin, first, second):
        return ((first[0] - origin[0]) * (second[1] - origin[1])
                - (first[1] - origin[1]) * (second[0] - origin[0]))

    lower: list[tuple[int, int]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[int, int]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return [[float(x), float(y)] for x, y in lower[:-1] + upper[:-1]]


def _pixel_derived_outline(path: Path) -> tuple[int, int, list[list[float]]]:
    """Extract a coarse studio-background silhouette for a test input only.

    The row-local border colour handles the fixtures' vertical background
    gradients.  This is deliberately not a product segmentation algorithm;
    it merely ensures the target regression consumes different image bytes
    and different pixel-derived geometry instead of three hand-written boxes.
    """
    width, height, rows = _read_rgb_png(path)
    sample_step = 8
    threshold_squared = 50 * 50
    foreground: list[tuple[int, int]] = []
    for y in range(0, height, sample_step):
        left = _pixel(rows[y], 0)
        right = _pixel(rows[y], width - 1)
        background = tuple((left[channel] + right[channel]) / 2.0
                           for channel in range(3))
        for x in range(sample_step, width - sample_step, sample_step):
            colour = _pixel(rows[y], x)
            distance_squared = sum(
                (colour[channel] - background[channel]) ** 2
                for channel in range(3)
            )
            if distance_squared > threshold_squared:
                foreground.append((x, y))
    if len(foreground) < 500:
        raise AssertionError(f"foreground extraction is too sparse for {path}")
    outline = _convex_hull(foreground)
    if len(outline) < 6:
        raise AssertionError(f"foreground hull is too small for {path}")
    return width, height, outline


def _fixture_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _target_request(path: Path) -> dict:
    width, height, outline = _pixel_derived_outline(path)
    return {
        "schema": "garment.target-reconstruction.request.v1",
        # Deliberately omit path, basename and project label.  The core gets
        # only content identity and geometry from the image boundary.
        "source": {"image_digest": _fixture_digest(path)},
        "camera_digest": "cross-image-fixed-front-camera",
        "base_avatar": {
            "avatar_id": "cross-image-avatar",
            "kind": "PARAMETRIC_GAME_AVATAR",
            "authority": "PROPOSED_PREVIEW",
            "geometry_digest": "cross-image-avatar-geometry-v1",
            "measurements_cm": {
                "height": 170.0,
                "chest_bust": 92.0,
                "waist": 76.0,
                "hip": 98.0,
            },
        },
        "reconstruction": {
            "fallback": {
                "silhouette_digest": target_digest(outline),
                "point_count": len(outline),
                "outline": copy.deepcopy(outline),
                "width_px": width,
                "height_px": height,
            },
        },
        "regions": [
            {"id": "r00", "class": "BACKGROUND", "state": "OBSERVED"},
            {
                "id": "r01", "class": "GARMENT", "state": "PROPOSED",
                "outline": copy.deepcopy(outline),
            },
        ],
        "edits": {"remove_region_ids": ["r00"]},
    }


def _visible_basis(part_id: str) -> dict:
    return {
        "state": "PROPOSED",
        "basis": f"human-corrected front region for {part_id}",
        "breaks_when": "another view or construction review rejects it",
    }


def _part(part_id: str, kind: str, dimensions: dict, placement: str,
          *, unit: str, layer: int = 0, **semantics) -> dict:
    result = {
        "part_id": part_id,
        "kind": kind,
        "dimensions": copy.deepcopy(dimensions),
        "placement": placement,
        "garment_unit": unit,
        "layer": layer,
        "visible_basis": _visible_basis(part_id),
    }
    result.update(copy.deepcopy(semantics))
    return result


def _candidate(parts: list[dict]) -> dict:
    return {
        "candidate_id": "candidate-000",
        "state": "PROPOSED",
        "parts": copy.deepcopy(parts),
        "rear_hypothesis": {
            "state": "PROPOSED",
            "value": "rear-alternative-000",
            "basis": "the rear is absent from a front-only image",
            "breaks_when": "a rear or side view is supplied",
        },
        "material_hypothesis": {
            "state": "PROPOSED",
            "value": "bounded-material-range-000",
            "basis": "appearance does not measure mechanics",
            "breaks_when": "a swatch or material test is supplied",
        },
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }


def _structure_cases() -> tuple[list[dict], ...]:
    one_piece = [
        _part("n00", "BODY_SHELL",
              {"height_cm": 43.0, "circumference_cm": 90.0},
              "upper body", unit="u00"),
        _part("n01", "FLARE",
              {"height_cm": 64.0, "top_circumference_cm": 76.0,
               "bottom_circumference_cm": 172.0},
              "lower body", unit="u00", attached_to="n00",
              attachment_relation="JOIN"),
        _part("n02", "SLEEVE",
              {"length_cm": 56.0, "upper_circumference_cm": 34.0,
               "cuff_circumference_cm": 20.0},
              "arms", unit="u00", attached_to="n00",
              side="bilateral", quantity=2),
    ]
    layered = [
        _part("n10", "BODY_SHELL",
              {"height_cm": 43.0, "circumference_cm": 88.0},
              "inner upper body", unit="u10", layer=0),
        _part("n11", "BODY_SHELL",
              {"height_cm": 45.0, "circumference_cm": 98.0},
              "outer upper body", unit="u11", layer=1),
        _part("n12", "SLEEVE",
              {"length_cm": 58.0, "upper_circumference_cm": 36.0,
               "cuff_circumference_cm": 21.0},
              "outer arms", unit="u11", layer=1, attached_to="n11",
              side="bilateral", quantity=2),
        _part("n13", "OVERLAY",
              {"height_cm": 66.0, "width_cm": 80.0},
              "outer draped surface", unit="u11", layer=2,
              attached_to="n11", attachment_relation="LAYER"),
    ]
    separates_with_overlay = [
        _part("n20", "BODY_SHELL",
              {"height_cm": 43.0, "circumference_cm": 90.0},
              "upper body", unit="u20"),
        _part("n21", "TUBE",
              {"length_cm": 99.0, "circumference_cm": 57.0},
              "left lower limb", unit="u21", side="left"),
        _part("n22", "TUBE",
              {"length_cm": 99.0, "circumference_cm": 57.0},
              "right lower limb", unit="u21", side="right"),
        _part("n23", "GUSSET",
              {"length_cm": 18.0, "width_cm": 8.0},
              "lower centre", unit="u21", attached_to=["n21", "n22"]),
        _part("n24", "GORE",
              {"length_cm": 70.0, "top_width_cm": 16.0,
               "bottom_width_cm": 52.0, "x_cm": 14.0},
              "asymmetric outer lower surface", unit="u21", layer=2,
              attached_to="n22", attachment_relation="LAYER",
              detail_role=["decorative", "asymmetric_overlay"]),
    ]
    return one_piece, layered, separates_with_overlay


def _artifact_request(image_digest: str, parts: list[dict]) -> dict:
    measurements = {
        name: {
            "value_cm": 82.0 + index,
            "authority": "USER_PROVIDED",
            "source": "cross-image named wearer",
        }
        for index, name in enumerate(REQUIRED_WEARER_MEASUREMENTS)
    }
    return {
        "schema": ARTIFACT_REQUEST_SCHEMA,
        "front_image_request": {
            "schema": FRONT_REQUEST_SCHEMA,
            "source": {"image_id": f"sha256:{image_digest}", "view": "front"},
            "vision": {
                "observations": [{
                    "claim_id": "visible-000",
                    "field": "front.structure",
                    "value": "human-corrected typed regions",
                    "authority": "OBSERVED",
                    "basis": "visible front geometry",
                }],
                "proposals": [{
                    "claim_id": "hidden-000",
                    "field": "rear.structure",
                    "value": "candidate dependent",
                    "authority": "PROPOSED",
                    "basis": "front-only image",
                }],
            },
            "wearer_measurements": measurements,
            "candidates": [_candidate(parts)],
            "artifacts": {},
            "approvals": {},
            "rounds": [],
            "max_rounds": 8,
        },
    }


class CrossImageGeneralizationTests(unittest.TestCase):
    maxDiff = None

    def test_three_byte_distinct_images_build_distinct_editable_targets(self):
        paths = [FIXTURE_ROOT / name for name in FIXTURES]
        self.assertTrue(all(path.is_file() for path in paths))
        source_digests = {_fixture_digest(path) for path in paths}
        self.assertEqual(len(source_digests), 3)

        geometry_digests = set()
        for path in paths:
            with self.subTest(fixture=path.name):
                request = _target_request(path)
                first = prepare_target_reconstruction(request)
                second = prepare_target_reconstruction(copy.deepcopy(request))
                self.assertEqual(first, second)
                self.assertEqual(first["verdict"],
                                 "PROPOSED_TARGET_RECONSTRUCTION", first)
                self.assertEqual(first["stage"], "CLEANED_TARGET_READY")
                self.assertTrue(first["sculpt_ready"])
                self.assertEqual(first["rear_state"], "UNKNOWN_OR_PROPOSED")
                self.assertFalse(first["manufacturing_ready"])
                self.assertFalse(first["manufacturing_certified"])

                surface = first["sculpt_surface"]
                self.assertEqual(surface["source"],
                                 "GEOMETRIC_FRONT_FALLBACK")
                self.assertEqual(surface["component_count"], 1)
                self.assertEqual(surface["component_region_ids"], ["r01"])
                self.assertEqual(len(surface["vertices_cm"]),
                                 len(surface["texture_coordinates"]))
                self.assertEqual(len(surface["faces"]),
                                 len(surface["face_region_ids"]))
                self.assertEqual(
                    set(surface["face_region_ids"]),
                    {"front-visible-surface", "rear-proposed-surface",
                     "edge-proposed-surface"},
                )
                self.assertTrue(all(
                    len(uv) == 2
                    and 0.0 <= uv[0] <= 1.0
                    and 0.0 <= uv[1] <= 1.0
                    for uv in surface["texture_coordinates"]
                ))
                geometry_digests.add(target_digest({
                    "vertices_cm": surface["vertices_cm"],
                    "faces": surface["faces"],
                }))

                # A basename can be present in this test harness but must not
                # be carried into the deterministic target artifact.
                serialised = json.dumps(first, sort_keys=True).lower()
                self.assertNotIn(path.stem.lower(), serialised)

        self.assertEqual(
            len(geometry_digests), 3,
            "three different pixel-derived silhouettes collapsed to one target",
        )

    def test_typed_candidate_geometry_is_filename_invariant_but_structure_specific(self):
        image_digests = [
            _fixture_digest(FIXTURE_ROOT / name) for name in FIXTURES
        ]
        cross_structure_preview_digests = set()
        cross_structure_pattern_digests = set()

        for case_index, parts in enumerate(_structure_cases()):
            with self.subTest(structure_case=case_index):
                structure_digests = set()
                preview_mesh_digests = set()
                pattern_geometry_digests = set()
                for image_digest in image_digests:
                    result = assemble(_artifact_request(image_digest, parts))
                    self.assertIn(result["verdict"], {"PROPOSED", "REVIEW"},
                                  result)
                    self.assertEqual(result["compiled_pattern_candidate_count"],
                                     1, result)
                    self.assertEqual(result["stopped_candidate_count"], 0,
                                     result)
                    source = result["source_candidates"][0]
                    self.assertEqual(len(source["structure_alternatives"]), 1)
                    alternative = source["structure_alternatives"][0]
                    pattern = alternative["pattern_candidate"]
                    self.assertEqual(pattern["verdict"], "ANSWER", pattern)
                    self.assertTrue(pattern["cuttable_geometric_prototype"])
                    self.assertFalse(pattern["manufacturing_ready"])
                    self.assertFalse(pattern["manufacturing_certified"])

                    graph = alternative["structure"]["structure_graph"]
                    preview = structure_preview.generate_preview(
                        graph, candidate_id=alternative["candidate_id"])
                    self.assertEqual(preview["verdict"], "ANSWER", preview)
                    self.assertTrue(preview["mesh"]["vertices"])
                    self.assertTrue(preview["mesh"]["faces"])
                    self.assertEqual(
                        {part["node_id"] for part in preview["parts"]},
                        {node["node_id"] for node in graph["nodes"]},
                    )
                    self.assertFalse(preview["claims"]["manufacturing_ready"])

                    structure_digests.add(alternative["structure_digest"])
                    preview_mesh_digests.add(
                        artifact_digest(preview["mesh"]))
                    pattern_geometry_digests.add(artifact_digest(
                        pattern["compiler_result"]["pieces"]))

                    serialised = json.dumps(result, sort_keys=True).lower()
                    for filename in FIXTURES:
                        self.assertNotIn(Path(filename).stem.lower(), serialised)

                # Swapping the image content identity cannot silently change
                # already typed geometry after the vision boundary.
                self.assertEqual(len(structure_digests), 1)
                self.assertEqual(len(preview_mesh_digests), 1)
                self.assertEqual(len(pattern_geometry_digests), 1)
                cross_structure_preview_digests.update(preview_mesh_digests)
                cross_structure_pattern_digests.update(pattern_geometry_digests)

        # Conversely, distinct one-piece, layered, and separated/overlay
        # structures must not collapse to one generic 3-D or flat pattern.
        self.assertEqual(len(cross_structure_preview_digests), 3)
        self.assertEqual(len(cross_structure_pattern_digests), 3)


if __name__ == "__main__":
    unittest.main()
