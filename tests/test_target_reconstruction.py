# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from photoloset import structure_preview
from photoloset.target_reconstruction import (
    TARGET_BOUND_PREVIEW_REQUEST_SCHEMA,
    build_target_bound_candidate_preview,
    prepare_target_reconstruction,
)


def _request() -> dict:
    return {
        "schema": "garment.target-reconstruction.request.v1",
        "source": {"image_digest": "image-123"},
        "camera_digest": "camera-123",
        "base_avatar": {
            "avatar_id": "balanced-170",
            "kind": "PARAMETRIC_GAME_AVATAR",
            "authority": "PROPOSED_PREVIEW",
            "geometry_digest": "avatar-geometry-123",
            "measurements_cm": {
                "height": 170, "chest_bust": 90, "waist": 72, "hip": 96,
            },
            "render_lod": "HIGH",
        },
        "reconstruction": {
            "fallback": {"silhouette_digest": "silhouette-123", "point_count": 64},
        },
        "regions": [
            {"id": "background", "class": "background", "state": "OBSERVED"},
            {"id": "hair", "class": "hair", "state": "OBSERVED",
             "occludes_garment": True, "overlap_part_ids": ["navy-vest"]},
            {"id": "body", "class": "body", "state": "PROPOSED"},
            {"id": "navy-vest", "class": "garment", "state": "PROPOSED"},
        ],
        "edits": {"remove_region_ids": []},
    }


class TargetReconstructionTests(unittest.TestCase):
    def test_background_removal_does_not_make_a_hole(self) -> None:
        request = _request()
        request["edits"]["remove_region_ids"] = ["background"]
        result = prepare_target_reconstruction(request)
        self.assertEqual(result["stage"], "CLEANED_TARGET_READY")
        self.assertEqual(result["occlusion_holes"], [])
        self.assertEqual(result["completion_proposals"], [])
        self.assertIn("background", result["removed_region_ids"])

    def test_hair_removal_keeps_the_hidden_surface_proposed(self) -> None:
        request = _request()
        request["edits"]["remove_region_ids"] = ["hair"]
        result = prepare_target_reconstruction(request)
        self.assertEqual(result["stage"], "REVIEW_OCCLUSION_COMPLETION")
        self.assertEqual(
            result["occlusion_holes"][0]["state"], "UNKNOWN_OCCLUDED_SURFACE")
        self.assertEqual(
            result["completion_proposals"][0]["state"],
            "PROPOSED_OCCLUSION_BACKFILL")
        self.assertFalse(result["completion_proposals"][0]["observed"])
        self.assertEqual(result["fact_promotions"], [])

    def test_body_removal_is_display_only_without_boundary(self) -> None:
        request = _request()
        request["edits"]["remove_region_ids"] = ["body"]
        result = prepare_target_reconstruction(request)
        self.assertEqual(result["stage"], "REVIEW_BODY_GARMENT_BOUNDARY")
        self.assertFalse(result["garment_extraction_ready"])
        self.assertEqual(
            result["review_items"][0]["code"],
            "REVIEW_BODY_GARMENT_BOUNDARY_REQUIRED")

    def test_unknown_region_refuses_and_does_not_guess(self) -> None:
        request = _request()
        request["edits"]["remove_region_ids"] = ["not-bound"]
        result = prepare_target_reconstruction(request)
        self.assertEqual(
            result["verdict"], "UNKNOWN_TARGET_RECONSTRUCTION_REGION_ID")
        self.assertEqual(result["fact_promotions"], [])

    def test_external_mesh_is_provider_neutral_and_deterministic(self) -> None:
        request = _request()
        request["reconstruction"] = {
            "provider": "replaceable-single-view-provider",
            "mesh": {
                "artifact_digest": "mesh-123", "format": "glb",
                "vertex_count": 2000, "face_count": 3900,
            },
        }
        first = prepare_target_reconstruction(request)
        second = prepare_target_reconstruction(request)
        self.assertEqual(
            first["reconstruction"]["source_kind"], "EXTERNAL_SINGLE_VIEW_3D")
        self.assertTrue(first["reconstruction"]["provider_connected"])
        self.assertEqual(first["target_digest"], second["target_digest"])
        self.assertFalse(first["manufacturing_ready"])

    def test_front_fallback_builds_an_editable_avatar_bound_sculpt_surface(self) -> None:
        request = _request()
        request["reconstruction"]["fallback"].update({
            "outline": [[20, 10], [80, 10], [90, 90], [10, 90]],
            "width_px": 100,
            "height_px": 100,
        })

        result = prepare_target_reconstruction(request)

        self.assertTrue(result["sculpt_ready"])
        surface = result["sculpt_surface"]
        self.assertEqual(surface["schema"],
                         "garment.target-sculpt-surface.v1")
        self.assertEqual(surface["authority"], "PROPOSED_PREVIEW")
        self.assertTrue(surface["avatar_inside"])
        self.assertGreaterEqual(surface["editable_face_count"], 180)
        self.assertEqual(len(surface["faces"]),
                         len(surface["face_region_ids"]))
        self.assertEqual(len(surface["texture_coordinates"]),
                         len(surface["vertices_cm"]))
        self.assertTrue(all(
            len(uv) == 2 and 0.0 <= uv[0] <= 1.0 and 0.0 <= uv[1] <= 1.0
            for uv in surface["texture_coordinates"]
        ))
        front_limit = len(surface["vertices_cm"]) // 2
        front_faces = [
            face for face, region in zip(
                surface["faces"], surface["face_region_ids"])
            if region == "front-visible-surface"
        ]
        self.assertTrue(front_faces)
        self.assertTrue(all(max(face) < front_limit for face in front_faces))
        self.assertIn("rear-proposed-surface",
                      set(surface["face_region_ids"]))
        chest_radius = 90.0 / (2.0 * 3.141592653589793)
        front_z = [point[2] for point in surface["vertices_cm"]
                   if point[2] > 0]
        self.assertTrue(front_z)
        self.assertGreater(min(front_z), chest_radius)
        self.assertFalse(result["manufacturing_ready"])

    def test_disconnected_garment_components_remain_separate_sculpt_solids(self) -> None:
        request = _request()
        request["reconstruction"]["fallback"].update({
            # This historical union spans the empty center.  Component-local
            # regions below must take precedence for the editable target.
            "outline": [[10, 10], [90, 10], [90, 95], [10, 95]],
            "width_px": 100,
            "height_px": 100,
        })
        request["regions"].extend([
            {"id": "left-leg", "class": "garment", "state": "PROPOSED",
             "outline": [[18, 45], [40, 45], [38, 96], [20, 96]]},
            {"id": "right-leg", "class": "garment", "state": "PROPOSED",
             "outline": [[60, 45], [82, 45], [80, 96], [62, 96]]},
            {"id": "cropped-top", "class": "garment", "state": "PROPOSED",
             "outline": [[28, 12], [72, 12], [68, 40], [32, 40]]},
        ])

        result = prepare_target_reconstruction(request)

        surface = result["sculpt_surface"]
        self.assertEqual(3, surface["component_count"])
        self.assertEqual(
            {"left-leg", "right-leg", "cropped-top"},
            set(surface["component_region_ids"]))
        # Three disconnected closed solids produce three face components;
        # they are no longer joined by a made-up minX/maxX waist envelope.
        adjacency = {index: set() for index in range(len(surface["vertices_cm"]))}
        for face in surface["faces"]:
            for vertex in face:
                adjacency[vertex].update(other for other in face
                                         if other != vertex)
        unseen = set(adjacency)
        components = 0
        while unseen:
            components += 1
            stack = [unseen.pop()]
            while stack:
                current = stack.pop()
                neighbors = adjacency[current] & unseen
                unseen.difference_update(neighbors)
                stack.extend(neighbors)
        self.assertEqual(3, components)

    def test_fused_foreground_target_uses_complete_thin_front_shell(self) -> None:
        request = _request()
        request["reconstruction"]["fallback"].update({
            "outline": [[22, 4], [70, 8], [88, 45], [78, 98],
                        [55, 94], [48, 60], [40, 98], [14, 92], [8, 42]],
            "width_px": 100,
            "height_px": 100,
            "target_role": "FUSED_PERSON_AND_CLOTHING_FOREGROUND",
            "authority": "PROPOSED",
        })
        # Seedless clothing ranking found only a narrow colour island.  It is
        # still useful downstream evidence, but must not replace the complete
        # foreground used for the human cleanup target.
        request["regions"].append({
            "id": "seedless-colour-component", "class": "garment",
            "state": "PROPOSED",
            "outline": [[60, 20], [72, 20], [70, 86], [62, 86]],
        })

        result = prepare_target_reconstruction(request)

        surface = result["sculpt_surface"]
        self.assertEqual("FRONT_CONFORMAL_SHELL", surface["surface_mode"])
        self.assertEqual(
            "FUSED_PERSON_AND_CLOTHING_FOREGROUND", surface["target_role"])
        self.assertEqual(
            ["fused-person-and-garment-foreground"],
            surface["component_region_ids"])
        self.assertFalse(surface["avatar_inside"])
        half = len(surface["vertices_cm"]) // 2
        self.assertGreater(half, 0)
        self.assertTrue(all(
            0.0 < surface["vertices_cm"][index][2]
            - surface["vertices_cm"][index + half][2] <= 0.12000001
            for index in range(half)
        ))
        self.assertTrue(any(
            "no rear geometry" in item for item in surface["limitations"]))

        # The image-space top must remain the texture top.  SceneKit receives
        # NSImage-backed UVs with V=0 at that top edge; reversing V here would
        # put the photographed face at the mannequin's feet.
        front_vertices = surface["vertices_cm"][:half]
        front_uv = surface["texture_coordinates"][:half]
        top_index = max(range(half), key=lambda index: front_vertices[index][1])
        bottom_index = min(
            range(half), key=lambda index: front_vertices[index][1])
        self.assertLess(front_uv[top_index][1], front_uv[bottom_index][1])

    def test_fused_foreground_front_faces_keep_camera_facing_winding(self) -> None:
        request = _request()
        request["reconstruction"]["fallback"].update({
            "outline": [[22, 4], [70, 8], [88, 45], [78, 98],
                        [55, 94], [48, 60], [40, 98], [14, 92], [8, 42]],
            "width_px": 100,
            "height_px": 100,
            "target_role": "FUSED_PERSON_AND_GARMENT_CAD_TARGET",
            "authority": "PROPOSED",
        })

        surface = prepare_target_reconstruction(request)["sculpt_surface"]
        vertices = surface["vertices_cm"]

        def normal_z(face: list[int]) -> float:
            a, b, c = (vertices[index] for index in face)
            return ((b[0] - a[0]) * (c[1] - a[1])
                    - (b[1] - a[1]) * (c[0] - a[0]))

        front_face = next(
            face for face, region in zip(
                surface["faces"], surface["face_region_ids"])
            if region == "front-visible-surface")
        rear_face = next(
            face for face, region in zip(
                surface["faces"], surface["face_region_ids"])
            if region == "rear-proposed-surface")

        self.assertGreater(normal_z(front_face), 0.0)
        self.assertLess(normal_z(rear_face), 0.0)

    def test_fused_target_keeps_image_specific_layered_garment_components(self) -> None:
        request = _request()
        request["reconstruction"]["fallback"].update({
            "outline": [[8, 2], [92, 2], [96, 98], [4, 98]],
            "width_px": 100,
            "height_px": 100,
            "target_role": "FUSED_PERSON_AND_GARMENT_CAD_TARGET",
        })
        request["regions"].extend([
            {"id": "upper-panel", "class": "GARMENT", "state": "PROPOSED",
             "outline": [[25, 18], [75, 18], [70, 43], [30, 43]],
             "garment_unit": "upper", "layer": 0},
            {"id": "lower-left", "class": "GARMENT", "state": "PROPOSED",
             "outline": [[25, 47], [48, 47], [45, 96], [22, 96]],
             "garment_unit": "lower", "side": "left", "layer": 0},
            {"id": "lower-right", "class": "GARMENT", "state": "PROPOSED",
             "outline": [[52, 47], [75, 47], [78, 96], [55, 96]],
             "garment_unit": "lower", "side": "right", "layer": 0},
            {"id": "right-overlay", "class": "GARMENT", "state": "PROPOSED",
             "outline": [[53, 48], [88, 56], [78, 83], [58, 76]],
             "garment_unit": "outer", "side": "right", "layer": 2},
        ])

        result = prepare_target_reconstruction(request)
        surface = result["garment_component_surface"]

        self.assertTrue(result["garment_component_surface_ready"])
        self.assertEqual(surface["surface_mode"],
                         "GARMENT_COMPONENT_FRONT_SHELL")
        self.assertEqual(surface["component_count"], 4)
        self.assertEqual(set(surface["component_region_ids"]), {
            "upper-panel", "lower-left", "lower-right", "right-overlay",
        })
        records = {row["component_id"]: row
                   for row in surface["component_records"]}
        self.assertEqual(records["lower-left"]["side"], "left")
        self.assertEqual(records["lower-right"]["side"], "right")
        self.assertEqual(records["right-overlay"]["layer"], 2)
        self.assertEqual(records["upper-panel"]["garment_unit"], "upper")
        self.assertEqual(len(surface["face_region_ids"]), len(surface["faces"]))
        self.assertEqual(len(surface["face_component_ids"]), len(surface["faces"]))

        def component_front_mean_y(component_id: str) -> float:
            vertex_ids = {
                vertex
                for face, region, component in zip(
                    surface["faces"], surface["face_region_ids"],
                    surface["face_component_ids"])
                if region == "front-visible-surface"
                and component == component_id
                for vertex in face
            }
            return sum(surface["vertices_cm"][index][1]
                       for index in vertex_ids) / len(vertex_ids)

        # Cropped and separated parts retain source-image body placement; the
        # component-only surface is not independently stretched head-to-foot.
        self.assertGreater(component_front_mean_y("upper-panel"),
                           component_front_mean_y("lower-left"))
        self.assertFalse(surface["avatar_inside"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertEqual(result["fact_promotions"], [])

    def test_target_bound_candidates_share_exact_front_but_vary_typed_rear(self) -> None:
        request = _request()
        request["reconstruction"]["fallback"].update({
            "outline": [[8, 2], [92, 2], [96, 98], [4, 98]],
            "width_px": 100,
            "height_px": 100,
            "target_role": "FUSED_PERSON_AND_GARMENT_CAD_TARGET",
        })
        request["regions"].extend([
            {"id": "upper", "class": "GARMENT", "state": "PROPOSED",
             "outline": [[24, 17], [76, 17], [70, 44], [30, 44]]},
            {"id": "left-lower", "class": "GARMENT", "state": "PROPOSED",
             "outline": [[23, 48], [48, 48], [44, 96], [20, 96]],
             "side": "left"},
            {"id": "right-lower", "class": "GARMENT", "state": "PROPOSED",
             "outline": [[52, 48], [77, 48], [80, 96], [56, 96]],
             "side": "right"},
            {"id": "side-layer", "class": "GARMENT", "state": "PROPOSED",
             "outline": [[54, 47], [88, 56], [77, 84], [59, 76]],
             "side": "right", "layer": 2},
        ])
        target_result = prepare_target_reconstruction(request)
        front_target = target_result["garment_component_surface"]
        avatar = target_result["base_avatar"]
        split_structure = {
            "schema": "garment.structure.v1",
            "nodes": [
                {"node_id": "upper-shell", "kind": "BODY_SHELL", "layer": 0,
                 "dimensions": {"height_cm": 45, "circumference_cm": 90}},
                {"node_id": "left-tube", "kind": "TUBE", "layer": 0,
                 "dimensions": {"length_cm": 96, "circumference_cm": 56,
                                "x_cm": -15}},
                {"node_id": "right-tube", "kind": "TUBE", "layer": 0,
                 "dimensions": {"length_cm": 96, "circumference_cm": 56,
                                "x_cm": 15}},
                {"node_id": "outer-sheet", "kind": "OVERLAY", "layer": 2,
                 "dimensions": {"height_cm": 68, "width_cm": 34,
                                "x_cm": 18}},
            ],
            "operations": [],
        }
        flared_structure = {
            "schema": "garment.structure.v1",
            "nodes": [
                {"node_id": "upper-shell", "kind": "BODY_SHELL", "layer": 0,
                 "dimensions": {"height_cm": 45, "circumference_cm": 90}},
                {"node_id": "lower-flare", "kind": "FLARE", "layer": 0,
                 "dimensions": {"height_cm": 96,
                                "top_circumference_cm": 76,
                                "bottom_circumference_cm": 180}},
                {"node_id": "outer-sheet", "kind": "OVERLAY", "layer": 1,
                 "dimensions": {"height_cm": 54, "width_cm": 62,
                                "x_cm": -12}},
            ],
            "operations": [],
        }

        def bind(candidate_id: str, structure: dict) -> dict:
            preview = structure_preview.generate_preview(
                structure, candidate_id=candidate_id)
            self.assertEqual(preview["verdict"], "ANSWER", preview)
            return build_target_bound_candidate_preview({
                "schema": TARGET_BOUND_PREVIEW_REQUEST_SCHEMA,
                "candidate_id": candidate_id,
                "front_target": front_target,
                "candidate_preview": preview,
                "base_avatar": avatar,
            })

        split = bind("split-option", split_structure)
        flared = bind("flared-option", flared_structure)
        renamed = bind("renamed-split-option", split_structure)

        self.assertEqual(split["verdict"], "ANSWER", split)
        self.assertEqual(flared["verdict"], "ANSWER", flared)
        self.assertEqual(split["mesh"], renamed["mesh"])
        self.assertNotEqual(split["mesh"], flared["mesh"])

        source_front_faces = [
            index for index, region in enumerate(front_target["face_region_ids"])
            if region == "front-visible-surface"
        ]
        source_vertex_ids = sorted({
            vertex for index in source_front_faces
            for vertex in front_target["faces"][index]
        })
        remap = {source: index for index, source in enumerate(source_vertex_ids)}
        expected_vertices = [front_target["vertices_cm"][index]
                             for index in source_vertex_ids]
        expected_faces = [
            [remap[vertex] for vertex in front_target["faces"][index]]
            for index in source_front_faces
        ]
        actual_front_faces = [
            face for face, region in zip(
                split["mesh"]["faces"], split["mesh"]["face_region_ids"])
            if region == "front-visible-surface"
        ]
        self.assertEqual(split["mesh"]["vertices"][:len(expected_vertices)],
                         expected_vertices)
        self.assertEqual(actual_front_faces, expected_faces)
        self.assertEqual(split["preservation"]["front_component_count"], 4)
        self.assertEqual(split["authority"]["rear"], "PROPOSED")
        self.assertEqual(split["authority"]["material"], "UNKNOWN")
        self.assertFalse(split["manufacturing_ready"])
        self.assertFalse(split["manufacturing_certified"])
        self.assertEqual(split["fact_promotions"], [])

    def test_camera_is_mandatory(self) -> None:
        request = _request()
        request.pop("camera_digest")
        result = prepare_target_reconstruction(request)
        self.assertEqual(
            result["verdict"], "UNKNOWN_TARGET_RECONSTRUCTION_CAMERA_REQUIRED")

    def test_avatar_is_mandatory_and_locked_to_the_loop(self) -> None:
        missing = _request()
        missing.pop("base_avatar")
        refused = prepare_target_reconstruction(missing)
        self.assertEqual(
            refused["verdict"], "UNKNOWN_TARGET_RECONSTRUCTION_AVATAR_REQUIRED")
        accepted = prepare_target_reconstruction(_request())
        self.assertTrue(accepted["base_avatar_locked_for_loop"])
        self.assertEqual(
            accepted["composition_order"][0], "SELECT_BASE_AVATAR")
        self.assertTrue(
            accepted["base_avatar"]["not_inferred_from_garment_photo"])


if __name__ == "__main__":
    unittest.main()
