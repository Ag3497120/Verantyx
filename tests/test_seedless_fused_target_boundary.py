#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression boundary for seedless regions and fused CAD targets.

The automatic colour picker is allowed to propose a garment component.  It is
not allowed to silently promote that one component to the complete fused
person-and-garment cleanup target.  These tests use two byte-distinct,
structurally distinct synthetic front images so the contract is exercised
without a fixture basename, a memorised digest, or an external vision model.

The desired boundary is deliberately strict:

* ``FUSED_TARGET_READY`` has an explicit fused-person-and-garment role;
* target and region provenance identify foreground connected components and
  keep a seedless colour component merely proposed;
* fallback geometry covers every foreground component rather than only the
  selected colour island;
* a front image never observes the rear; and
* filenames and content digests bind a run but do not select geometry.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Callable, Iterable
import unittest

from photoloset.target_reconstruction import prepare_target_reconstruction


RGB = tuple[int, int, int]
Point = list[float]
Outline = list[Point]

BACKGROUND: RGB = (247, 247, 247)
SKIN: RGB = (197, 153, 128)
WHITE: RGB = (226, 222, 211)
GREEN: RGB = (28, 112, 80)
NAVY: RGB = (28, 39, 70)
RED: RGB = (161, 55, 43)
TEAL: RGB = (20, 123, 132)


@dataclass(frozen=True)
class SyntheticScene:
    name: str
    width: int
    height: int
    pixels: tuple[RGB, ...]
    foreground_outlines: tuple[Outline, ...]
    seedless_outline: Outline
    seedless_colour: RGB

    @property
    def image_bytes(self) -> bytes:
        header = f"P6\n{self.width} {self.height}\n255\n".encode("ascii")
        raster = bytes(channel for pixel in self.pixels for channel in pixel)
        return header + raster

    @property
    def image_digest(self) -> str:
        return hashlib.sha256(self.image_bytes).hexdigest()


def _blank(width: int, height: int) -> list[RGB]:
    return [BACKGROUND] * (width * height)


def _fill(
        pixels: list[RGB], width: int, height: int,
        rectangle: tuple[int, int, int, int], colour: RGB) -> None:
    left, top, right, bottom = rectangle
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise AssertionError(f"invalid synthetic rectangle {rectangle!r}")
    for y in range(top, bottom):
        for x in range(left, right):
            pixels[y * width + x] = colour


def _component_outlines(
        pixels: Iterable[RGB], width: int, height: int,
        predicate: Callable[[RGB], bool]) -> tuple[Outline, ...]:
    raster = tuple(pixels)
    remaining = {
        (x, y)
        for y in range(height)
        for x in range(width)
        if predicate(raster[y * width + x])
    }
    components: list[tuple[int, int, int, int, int]] = []
    while remaining:
        start = remaining.pop()
        stack = [start]
        xs = [start[0]]
        ys = [start[1]]
        count = 1
        while stack:
            x, y = stack.pop()
            for neighbour in ((x - 1, y), (x + 1, y),
                              (x, y - 1), (x, y + 1)):
                if neighbour not in remaining:
                    continue
                remaining.remove(neighbour)
                stack.append(neighbour)
                xs.append(neighbour[0])
                ys.append(neighbour[1])
                count += 1
        components.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1, count))

    # Pixel count first makes component numbering stable even when a hash or
    # filename changes.  Coordinates only break ties.
    components.sort(key=lambda row: (-row[4], row[1], row[0], row[3], row[2]))
    return tuple(
        [[float(left), float(top)], [float(right), float(top)],
         [float(right), float(bottom)], [float(left), float(bottom)]]
        for left, top, right, bottom, _ in components
    )


def _scene_one_piece() -> SyntheticScene:
    width, height = 96, 160
    pixels = _blank(width, height)
    _fill(pixels, width, height, (41, 7, 55, 26), SKIN)       # head
    _fill(pixels, width, height, (34, 23, 62, 72), WHITE)     # upper body
    _fill(pixels, width, height, (20, 35, 35, 91), WHITE)     # left sleeve
    _fill(pixels, width, height, (61, 35, 76, 91), WHITE)     # right sleeve
    _fill(pixels, width, height, (25, 69, 71, 147), GREEN)    # long dress
    foreground = _component_outlines(
        pixels, width, height, lambda colour: colour != BACKGROUND)
    seedless = _component_outlines(
        pixels, width, height, lambda colour: colour == GREEN)
    if len(foreground) != 1 or len(seedless) != 1:
        raise AssertionError("one-piece synthetic image topology changed")
    return SyntheticScene(
        "anonymous-one-piece", width, height, tuple(pixels),
        foreground, seedless[0], GREEN)


def _scene_layered_separates() -> SyntheticScene:
    width, height = 120, 170
    pixels = _blank(width, height)
    _fill(pixels, width, height, (53, 7, 67, 27), SKIN)       # head
    _fill(pixels, width, height, (45, 24, 75, 70), WHITE)     # blouse
    _fill(pixels, width, height, (29, 35, 46, 92), WHITE)     # left sleeve
    _fill(pixels, width, height, (74, 35, 91, 92), WHITE)     # right sleeve
    _fill(pixels, width, height, (40, 30, 80, 66), NAVY)      # cropped vest
    _fill(pixels, width, height, (38, 63, 82, 76), RED)       # trouser waist
    _fill(pixels, width, height, (38, 72, 56, 153), RED)      # left leg
    _fill(pixels, width, height, (64, 72, 82, 153), RED)      # right leg
    _fill(pixels, width, height, (76, 68, 102, 137), TEAL)    # overskirt
    _fill(pixels, width, height, (108, 82, 115, 104), TEAL)   # detached tie
    foreground = _component_outlines(
        pixels, width, height, lambda colour: colour != BACKGROUND)
    seedless = _component_outlines(
        pixels, width, height, lambda colour: colour == NAVY)
    if len(foreground) != 2 or len(seedless) != 1:
        raise AssertionError("layered-separates synthetic image topology changed")
    return SyntheticScene(
        "anonymous-layered-separates", width, height, tuple(pixels),
        foreground, seedless[0], NAVY)


SCENES = (_scene_one_piece(), _scene_layered_separates())


def _envelope(outlines: Iterable[Outline]) -> Outline:
    points = [point for outline in outlines for point in outline]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [
        [min(xs), min(ys)], [max(xs), min(ys)],
        [max(xs), max(ys)], [min(xs), max(ys)],
    ]


def _request(
        scene: SyntheticScene, *, digest: str | None = None,
        image_id: str | None = None) -> dict:
    fused_regions = [
        {
            "id": f"foreground-{index}",
            "class": "BODY" if index == 0 else "ACCESSORY",
            "state": "PROPOSED",
            "outline": copy.deepcopy(outline),
            "target_role": "FUSED_PERSON_AND_GARMENT_FOREGROUND_COMPONENT",
            "selection_mode": "FOREGROUND_CONNECTED_COMPONENT",
            "provenance": {
                "method": "SYNTHETIC_PIXEL_CONNECTED_COMPONENTS",
                "source_image_digest": digest or scene.image_digest,
                "component_index": index,
            },
        }
        for index, outline in enumerate(scene.foreground_outlines)
    ]
    source = {"image_digest": digest or scene.image_digest}
    if image_id is not None:
        source["image_id"] = image_id
    return {
        "schema": "garment.target-reconstruction.request.v1",
        "source": source,
        "camera_digest": "fixed-synthetic-front-camera",
        "base_avatar": {
            "avatar_id": "synthetic-regression-avatar",
            "kind": "PARAMETRIC_GAME_AVATAR",
            "authority": "PROPOSED_PREVIEW",
            "geometry_digest": "synthetic-avatar-geometry-v1",
            "measurements_cm": {
                "height": 170.0,
                "chest_bust": 92.0,
                "waist": 76.0,
                "hip": 98.0,
            },
        },
        "reconstruction": {
            "fallback": {
                "silhouette_digest": hashlib.sha256(
                    json.dumps(scene.foreground_outlines).encode("utf-8")
                ).hexdigest(),
                "point_count": sum(map(len, scene.foreground_outlines)),
                # The legacy field can only carry one loop.  Typed foreground
                # region loops above retain the actual connected components.
                "outline": _envelope(scene.foreground_outlines),
                "width_px": scene.width,
                "height_px": scene.height,
                "target_role": "FUSED_PERSON_AND_GARMENT_CAD_TARGET",
                "selection_mode": "FOREGROUND_CONNECTED_COMPONENTS",
            },
        },
        "regions": [
            {"id": "background", "class": "BACKGROUND", "state": "OBSERVED"},
            *fused_regions,
            {
                "id": "seedless-colour-component",
                "class": "GARMENT",
                "state": "PROPOSED",
                "outline": copy.deepcopy(scene.seedless_outline),
                "target_role": "GARMENT_COMPONENT_PROPOSAL",
                "selection_mode": "SEEDLESS_COLOR_COMPONENT",
                "provenance": {
                    "method": "SEEDLESS_COLOR_COMPONENT",
                    "source_image_digest": digest or scene.image_digest,
                    "colour_rgb": list(scene.seedless_colour),
                },
            },
        ],
        "edits": {"remove_region_ids": []},
    }


def _face_component_count(surface: dict) -> int:
    referenced = {vertex for face in surface["faces"] for vertex in face}
    adjacency = {vertex: set() for vertex in referenced}
    for face in surface["faces"]:
        for vertex in face:
            adjacency[vertex].update(other for other in face if other != vertex)
    unseen = set(referenced)
    components = 0
    while unseen:
        components += 1
        stack = [unseen.pop()]
        while stack:
            neighbours = adjacency[stack.pop()] & unseen
            unseen.difference_update(neighbours)
            stack.extend(neighbours)
    return components


def _xy_aspect_from_outlines(outlines: Iterable[Outline]) -> float:
    points = [point for outline in outlines for point in outline]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (max(xs) - min(xs)) / (max(ys) - min(ys))


def _xy_aspect_from_surface(surface: dict) -> float:
    xs = [point[0] for point in surface["vertices_cm"]]
    ys = [point[1] for point in surface["vertices_cm"]]
    return (max(xs) - min(xs)) / (max(ys) - min(ys))


class SeedlessFusedTargetBoundaryTests(unittest.TestCase):
    maxDiff = None

    def test_fused_ready_uses_an_explicit_fused_target_role(self) -> None:
        for scene in SCENES:
            with self.subTest(scene=scene.name):
                result = prepare_target_reconstruction(_request(scene))
                self.assertEqual(result["stage"], "FUSED_TARGET_READY", result)
                self.assertEqual(
                    result["target_role"],
                    "FUSED_PERSON_AND_GARMENT_CAD_TARGET",
                    "a generic visual target role cannot distinguish a full "
                    "fused cleanup target from one seedless garment proposal",
                )

    def test_fused_ready_has_target_level_foreground_provenance(self) -> None:
        for scene in SCENES:
            with self.subTest(scene=scene.name):
                result = prepare_target_reconstruction(_request(scene))
                provenance = result.get("target_provenance")
                self.assertIsInstance(
                    provenance, dict,
                    "FUSED_TARGET_READY needs target-level segmentation lineage",
                )
                self.assertEqual(
                    provenance.get("selection_mode"),
                    "FOREGROUND_CONNECTED_COMPONENTS",
                )
                self.assertEqual(
                    set(provenance.get("source_region_ids", [])),
                    {f"foreground-{index}"
                     for index in range(len(scene.foreground_outlines))},
                )

    def test_region_level_selection_provenance_survives_normalisation(self) -> None:
        for scene in SCENES:
            with self.subTest(scene=scene.name):
                result = prepare_target_reconstruction(_request(scene))
                returned_regions = {row["id"]: row for row in result["regions"]}
                self.assertEqual(
                    returned_regions["seedless-colour-component"].get(
                        "selection_mode"),
                    "SEEDLESS_COLOR_COMPONENT",
                )
                self.assertEqual(
                    returned_regions["seedless-colour-component"].get(
                        "target_role"),
                    "GARMENT_COMPONENT_PROPOSAL",
                )

    def test_fused_geometry_source_is_not_one_seedless_colour_component(self) -> None:
        for scene in SCENES:
            with self.subTest(scene=scene.name):
                result = prepare_target_reconstruction(_request(scene))
                self.assertTrue(result["sculpt_ready"], result)
                surface = result["sculpt_surface"]
                self.assertNotEqual(
                    surface.get("component_region_ids"),
                    ["seedless-colour-component"],
                    "one seedless colour island was silently promoted to the "
                    "complete fused person-and-garment CAD target",
                )

    def test_fused_geometry_preserves_foreground_components_and_extent(self) -> None:
        for scene in SCENES:
            with self.subTest(scene=scene.name):
                result = prepare_target_reconstruction(_request(scene))
                self.assertTrue(result["sculpt_ready"], result)
                surface = result["sculpt_surface"]
                self.assertEqual(
                    _face_component_count(surface),
                    len(scene.foreground_outlines),
                    "the editable target must preserve source foreground "
                    "connected components",
                )
                self.assertAlmostEqual(
                    _xy_aspect_from_surface(surface),
                    _xy_aspect_from_outlines(scene.foreground_outlines),
                    delta=0.03,
                    msg="the fused target extent collapsed to a selected colour component",
                )

    def test_front_only_target_keeps_every_rear_surface_unobserved(self) -> None:
        for scene in SCENES:
            with self.subTest(scene=scene.name):
                result = prepare_target_reconstruction(_request(scene))
                self.assertEqual(result["rear_state"], "UNKNOWN_OR_PROPOSED")
                self.assertEqual(result["state"], "PROPOSED")
                self.assertTrue(result["human_approval_required"])
                self.assertFalse(result["manufacturing_ready"])
                self.assertFalse(result["manufacturing_certified"])
                face_roles = set(result["sculpt_surface"]["face_region_ids"])
                self.assertIn("rear-proposed-surface", face_roles)
                self.assertFalse(any("observed" in role.lower()
                                     and "rear" in role.lower()
                                     for role in face_roles))

    def test_filenames_and_hashes_bind_runs_but_do_not_select_geometry(self) -> None:
        scene = SCENES[1]
        first = prepare_target_reconstruction(_request(
            scene,
            digest="1" * 64,
            image_id="memorise-this-layered-separates-name.png",
        ))
        second = prepare_target_reconstruction(_request(
            scene,
            digest="2" * 64,
            image_id="completely-unrelated-name.jpg",
        ))
        self.assertEqual(first["sculpt_surface"], second["sculpt_surface"])
        self.assertNotEqual(first["source_image_digest"],
                            second["source_image_digest"])
        self.assertNotEqual(first["target_digest"], second["target_digest"])
        serialised = json.dumps([first, second], sort_keys=True).lower()
        self.assertNotIn("memorise-this-layered-separates-name", serialised)
        self.assertNotIn("completely-unrelated-name", serialised)

        # Conversely, forcing the same content identity must not collapse two
        # different geometries into one memorised target.
        forced_digest = "f" * 64
        geometries = [
            prepare_target_reconstruction(
                _request(scene_case, digest=forced_digest)
            )["sculpt_surface"]
            for scene_case in SCENES
        ]
        self.assertNotEqual(geometries[0], geometries[1])


if __name__ == "__main__":
    unittest.main()
