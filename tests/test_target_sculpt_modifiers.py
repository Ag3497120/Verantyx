# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import math
import unittest

from photoloset.target_sculpt_modifiers import (
    apply_target_sculpt_modifier,
    surface_digest,
)


def _surface() -> dict:
    vertices = [
        [0.0, 0.0, 0.0],
        [2.0, 0.0, 0.0],
        [2.0, 2.0, 0.0],
        [0.0, 2.0, 0.0],
    ]
    faces = [[0, 1, 2], [0, 2, 3]]
    revision = 3
    return {
        "schema": "garment.target-sculpt-surface.v1",
        "vertices_cm": vertices,
        "faces": faces,
        "revision": revision,
        "digest": surface_digest(vertices, faces, revision),
    }


def _request(modifier: dict) -> dict:
    return {
        "schema": "garment.target-sculpt-modifier.request.v1",
        "sculpt_surface": _surface(),
        "expected_revision": 3,
        "expected_digest": _surface()["digest"],
        "modifier": modifier,
    }


class TargetSculptModifierTests(unittest.TestCase):
    def test_pull_along_face_normals_is_immutable_and_undo_linked(self) -> None:
        request = _request({
            "kind": "PULL",
            "face_indices": [0],
            "distance_cm": 1.0,
            "direction": "LOCAL_NORMAL",
        })
        before = copy.deepcopy(request)

        result = apply_target_sculpt_modifier(request)

        self.assertEqual(result["verdict"], "PROPOSED_CAD_MODIFIER")
        self.assertEqual(result["authority"], "PROPOSED_CAD_MODIFIER")
        self.assertEqual(result["revision"], 4)
        self.assertEqual(result["undo_parent_digest"], before["sculpt_surface"]["digest"])
        self.assertEqual(result["digest"], result["sculpt_surface"]["digest"])
        self.assertEqual(result["moved_vertex_indices"], [0, 1, 2])
        self.assertEqual(result["sculpt_surface"]["vertices_cm"][0], [0.0, 0.0, 1.0])
        self.assertEqual(result["sculpt_surface"]["vertices_cm"][3], [0.0, 2.0, 0.0])
        self.assertEqual(request, before)
        self.assertFalse(result["manufacturing_ready"])
        self.assertEqual(result["fact_promotions"], [])

    def test_pull_supports_bounded_explicit_vector(self) -> None:
        modifier = {
            "kind": "PULL",
            "vertex_indices": [3, 1],
            "vector_cm": [0.25, -0.5, 0.75],
        }
        result = apply_target_sculpt_modifier(_request(modifier))
        reversed_selection = dict(modifier, vertex_indices=[1, 3])
        self.assertEqual(
            result, apply_target_sculpt_modifier(_request(reversed_selection)))
        self.assertEqual(result["moved_vertex_indices"], [1, 3])
        self.assertEqual(
            result["sculpt_surface"]["vertices_cm"][1],
            [2.25, -0.5, 0.75],
        )
        self.assertEqual(
            result["statistics"]["method"], "EXPLICIT_DISPLACEMENT_VECTOR")

    def test_stretch_scales_only_axis_component_from_anchor(self) -> None:
        result = apply_target_sculpt_modifier(_request({
            "kind": "STRETCH",
            "vertex_indices": [2, 1],
            "anchor_cm": [0.0, 0.0, 0.0],
            "axis_vector": [1.0, 0.0, 0.0],
            "scale_factor": 1.5,
        }))
        self.assertEqual(result["moved_vertex_indices"], [1, 2])
        self.assertEqual(result["sculpt_surface"]["vertices_cm"][1], [3.0, 0.0, 0.0])
        self.assertEqual(result["sculpt_surface"]["vertices_cm"][2], [3.0, 2.0, 0.0])
        self.assertEqual(result["sculpt_surface"]["vertices_cm"][3], [0.0, 2.0, 0.0])
        self.assertEqual(result["statistics"]["method"], "LOCAL_AXIAL_SCALE")

    def test_wind_preview_is_uniform_low_fidelity_and_can_fix_anchors(self) -> None:
        result = apply_target_sculpt_modifier(_request({
            "kind": "WIND_PREVIEW",
            "wind_vector_m_s": [2.0, 0.0, 0.0],
            "preview_gain_cm_per_m_s": 0.1,
            "anchor_vertex_indices": [0],
        }))
        self.assertEqual(result["moved_vertex_indices"], [1, 2, 3])
        self.assertEqual(result["sculpt_surface"]["vertices_cm"][0], [0.0, 0.0, 0.0])
        self.assertEqual(result["sculpt_surface"]["vertices_cm"][1], [2.2, 0.0, 0.0])
        self.assertIn("low-fidelity", " ".join(result["limitations"]))
        self.assertFalse(result["manufacturing_certified"])

    def test_chained_revision_is_accepted_and_deterministic(self) -> None:
        request = _request({
            "kind": "PULL", "vertex_indices": [0],
            "direction_vector": [0.0, 0.0, 2.0], "distance_cm": 0.5,
        })
        first = apply_target_sculpt_modifier(request)
        self.assertEqual(first, apply_target_sculpt_modifier(request))
        chained = {
            "schema": "garment.target-sculpt-modifier.request.v1",
            "sculpt_surface": first["sculpt_surface"],
            "expected_revision": first["revision"],
            "expected_digest": first["digest"],
            "modifier": {
                "kind": "STRETCH", "vertex_indices": [1],
                "anchor_vertex_index": 0, "axis": [1, 0, 0], "scale": 1.1,
            },
        }
        second = apply_target_sculpt_modifier(chained)
        self.assertEqual(second["revision"], 5)
        self.assertEqual(second["undo_parent_digest"], first["digest"])

    def test_stale_revision_and_digest_stop_typed(self) -> None:
        stale_revision = _request({
            "kind": "PULL", "vertex_indices": [0], "vector_cm": [0, 0, 1],
        })
        stale_revision["expected_revision"] = 2
        self.assertEqual(
            apply_target_sculpt_modifier(stale_revision)["verdict"],
            "UNKNOWN_TARGET_SCULPT_MODIFIER_STALE_REVISION",
        )
        stale_digest = _request({
            "kind": "PULL", "vertex_indices": [0], "vector_cm": [0, 0, 1],
        })
        stale_digest["expected_digest"] = "sha256:stale"
        self.assertEqual(
            apply_target_sculpt_modifier(stale_digest)["verdict"],
            "UNKNOWN_TARGET_SCULPT_MODIFIER_STALE_REVISION",
        )

    def test_bad_indices_non_finite_and_excessive_deformation_stop_typed(self) -> None:
        bad_vertex = _request({
            "kind": "PULL", "vertex_indices": [99], "vector_cm": [0, 0, 1],
        })
        self.assertEqual(
            apply_target_sculpt_modifier(bad_vertex)["verdict"],
            "UNKNOWN_TARGET_SCULPT_MODIFIER_VERTEX_OUT_OF_RANGE",
        )
        bad_face = _request({
            "kind": "PULL", "face_indices": [7], "distance_cm": 1,
        })
        self.assertEqual(
            apply_target_sculpt_modifier(bad_face)["verdict"],
            "UNKNOWN_TARGET_SCULPT_MODIFIER_FACE_OUT_OF_RANGE",
        )
        non_finite = _request({
            "kind": "STRETCH", "vertex_indices": [1],
            "anchor_cm": [0, 0, math.nan], "axis": [1, 0, 0], "scale": 1.1,
        })
        self.assertEqual(
            apply_target_sculpt_modifier(non_finite)["verdict"],
            "UNKNOWN_TARGET_SCULPT_MODIFIER_NON_FINITE",
        )
        excessive = _request({
            "kind": "PULL", "vertex_indices": [0], "vector_cm": [0, 0, 11],
        })
        self.assertEqual(
            apply_target_sculpt_modifier(excessive)["verdict"],
            "UNKNOWN_TARGET_SCULPT_MODIFIER_EXCESSIVE_DEFORMATION",
        )


if __name__ == "__main__":
    unittest.main()
