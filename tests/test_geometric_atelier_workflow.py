#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from photoloset import candidate_3d_repair_loop
from photoloset.geometric_atelier_workflow import REQUEST_SCHEMA, run
from tests.test_cross_image_generalization import (
    FIXTURE_ROOT,
    _fixture_digest,
    _pixel_derived_outline,
)


def _mask(mask_id, mask_class, outline, *, unit=None, layer=0,
          authority="PROPOSED"):
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


def _separation(*, authority="PROPOSED", layered=True, oblique=False):
    masks = [_mask(
        "subject", "BODY",
        [[0.40, 0.05], [0.60, 0.05], [0.68, 0.25],
         [0.62, 0.94], [0.38, 0.94], [0.32, 0.25]],
        authority="PROPOSED",
    )]
    if layered:
        masks.extend([
            _mask("upper", "GARMENT",
                  [[0.33, 0.20], [0.67, 0.20], [0.63, 0.56], [0.37, 0.56]],
                  unit="upper-unit", authority=authority),
            _mask("lower", "GARMENT",
                  [[0.37, 0.53], [0.63, 0.53], [0.61, 0.94], [0.39, 0.94]],
                  unit="lower-unit", authority=authority),
            _mask("overlay", "GARMENT",
                  [[0.50, 0.51], [0.72, 0.55], [0.67, 0.87], [0.50, 0.72]],
                  unit="overlay-unit", layer=1, authority=authority),
        ])
    else:
        masks.append(_mask(
            "single", "GARMENT",
            [[0.34, 0.20], [0.66, 0.20], [0.70, 0.89], [0.30, 0.89]],
            unit="single-unit", authority=authority,
        ))
    pose = [
        {"name": "nose", "point": [0.50, 0.06], "confidence": 0.94,
         "authority": "PROPOSED"},
        {"name": "left_shoulder", "point": [0.36, 0.22], "confidence": 0.92,
         "authority": "PROPOSED"},
        {"name": "right_shoulder", "point": [0.64, 0.22], "confidence": 0.92,
         "authority": "PROPOSED"},
        {"name": "left_hip", "point": [0.44, 0.52], "confidence": 0.89,
         "authority": "PROPOSED"},
        {"name": "right_hip", "point": [0.56, 0.52], "confidence": 0.89,
         "authority": "PROPOSED"},
        {"name": "left_ankle", "point": [0.44, 0.94], "confidence": 0.86,
         "authority": "PROPOSED"},
        {"name": "right_ankle", "point": [0.56, 0.94], "confidence": 0.86,
         "authority": "PROPOSED"},
    ]
    candidate = {
        "schema": "garment.body-image-separation-candidate.v1",
        "candidate_id": "fixture-separation",
        "candidate_digest": "sha256:fixture-separation",
        "provider_id": "fixture-provider",
        "provider_result_digest": "sha256:fixture-provider-result",
        "policy_rank": 1,
        "pose_keypoints": pose,
        "masks": masks,
        "camera": {
            "view": "OBLIQUE_LEFT" if oblique else "FRONT",
            "yaw_deg": -28.0 if oblique else 0.0,
            "width_px": 1000,
            "height_px": 1600,
            "camera_digest": "camera:fixture",
            "authority": "PROPOSED",
        },
        "back_generation_conditioning": {"rear_state": "UNKNOWN_UNOBSERVED"},
    }
    return {
        "schema": "garment.body-image-separation.v1",
        "verdict": "PROPOSED_BODY_GARMENT_SEPARATION_CANDIDATES",
        "contract_digest": "sha256:separation-contract",
        "source": {
            "image_digest": "sha256:source-image",
            "width": 1000,
            "height": 1600,
            "orientation": "UP",
        },
        "candidates": [candidate],
        "selection": {"selected_candidate_id": candidate["candidate_id"]},
        "rear_state": "UNKNOWN_UNOBSERVED",
    }


def _layered_graph():
    return {
        "graph_id": "layered-separates",
        "parts": [
            {"part_id": "upper", "kind": "MYSTERY_UPPER",
             "garment_unit": "upper-unit", "layer": 0,
             "outline": [[0.33, 0.20], [0.67, 0.20],
                         [0.63, 0.56], [0.37, 0.56]]},
            {"part_id": "lower", "kind": "UNKNOWN_LOWER",
             "garment_unit": "lower-unit", "layer": 0,
             "independent_component_count": 2,
             "outline": [[0.37, 0.53], [0.63, 0.53],
                         [0.61, 0.94], [0.39, 0.94]]},
            {"part_id": "overlay", "kind": "UNCLASSIFIED_FIN",
             "garment_unit": "overlay-unit", "layer": 1, "side": "right",
             "outline": [[0.50, 0.51], [0.72, 0.55],
                         [0.67, 0.87], [0.50, 0.72]]},
        ],
        "relations": [
            {
                "relation_id": "typed-waist-join",
                "kind": "JOIN",
                "parent_id": "upper",
                "child_id": "lower",
                "attachment_port": "waist-interface",
                "attachment_side": "FULL",
                "state": "PROPOSED",
            },
            {
                "relation_id": "typed-right-overlay",
                "kind": "LAYER",
                "parent_id": "lower",
                "child_id": "overlay",
                "attachment_port": "right-waist-overlay-anchor",
                "attachment_side": "RIGHT",
                "state": "PROPOSED",
            },
        ],
    }


def _request(**updates):
    request = {
        "schema": REQUEST_SCHEMA,
        "separation": _separation(),
        "visible_part_graph": _layered_graph(),
        "audit_mode": "AUTO_PROPOSED",
        "resolution": {"angular_segments": 8, "height_steps": 4},
    }
    request.update(updates)
    return request


def _human_confirmed_fixture_request():
    """Build a real-pixel confirmation fixture without a product bypass.

    The ACCEPT decision and edit digest are deliberately confined to this
    test request.  Production still receives them only from the human audit
    gate; this helper merely measures the post-gate repair path.
    """
    path = FIXTURE_ROOT / "layered-separates-overskirt.png"
    width, height, outline_px = _pixel_derived_outline(path)
    outline = [[x / width, y / height] for x, y in outline_px]
    fixture_digest = _fixture_digest(path)
    separation = _separation(authority="OBSERVED", layered=False)
    separation["source"] = {
        "image_digest": "sha256:" + fixture_digest,
        "image_path": str(path.resolve()),
        "width": width,
        "height": height,
        "orientation": "UP",
    }
    candidate = separation["candidates"][0]
    candidate["camera"].update({
        "width_px": width,
        "height_px": height,
        "camera_digest": "camera:fixture-pixel-derived-front",
    })
    for mask in candidate["masks"]:
        if mask["class"] != "GARMENT":
            continue
        mask.update({
            "outline": copy.deepcopy(outline),
            "authority": "OBSERVED",
            "mask_digest": "sha256:" + fixture_digest + ":front-hull",
            "garment_unit_id": "fixture-visible-unit",
            "mask_id": "fixture-visible-garment",
        })
    graph = {
        "graph_id": "fixture-pixel-derived-visible-front",
        "parts": [{
            "part_id": "fixture-visible-garment",
            "kind": "UNKNOWN_VISIBLE_GARMENT",
            "garment_unit": "fixture-visible-unit",
            "layer": 0,
            "outline": copy.deepcopy(outline),
            "coordinate_space": "NORMALIZED",
        }],
        "relations": [],
    }
    request = _request(
        separation=separation,
        visible_part_graph=graph,
        audit_mode="HUMAN_AUDIT",
        front_audit={"decision": "ACCEPT", "reviewer": "fixture-human"},
        human_edit_digest=(
            "sha256:test-only-human-confirmed-" + fixture_digest
        ),
        repair_config={"max_rounds": 3, "repair_gain": 1.0},
    )
    return path, outline_px, request


def _human_confirmed_multi_region_fixture_request():
    """Represent four reviewer-drawn regions without garment-name semantics.

    The polygons are test-only pixel selections on the same real fixture used
    by ``_human_confirmed_fixture_request``.  Region ids are deliberately
    opaque.  Only the two rear-to-front edges explicitly recorded by the
    reviewer receive an OBSERVED source state; the downstream ownership and
    second-skin relations remain PROPOSED.
    """
    path, _, request = _human_confirmed_fixture_request()
    parts = [
        {
            "part_id": "human-part:region-0",
            "kind": "HUMAN_OBSERVED_VISIBLE_REGION",
            "garment_unit": "human-visible-unit:region-0",
            "layer": 0,
            "side": "CENTER",
            "state": "OBSERVED",
            "coordinate_space": "PIXELS",
            "outline": [
                [340, 245], [684, 245], [748, 675], [640, 735],
                [600, 575], [424, 575], [384, 735], [276, 675],
            ],
        },
        {
            "part_id": "human-part:region-1",
            "kind": "HUMAN_OBSERVED_VISIBLE_REGION",
            "garment_unit": "human-visible-unit:region-1",
            "layer": 1,
            "side": "CENTER",
            "state": "OBSERVED",
            "coordinate_space": "PIXELS",
            "outline": [
                [346, 285], [678, 285], [704, 545], [612, 570],
                [560, 470], [468, 470], [414, 570], [326, 545],
            ],
        },
        {
            "part_id": "human-part:region-2",
            "kind": "HUMAN_OBSERVED_VISIBLE_REGION",
            "garment_unit": "human-visible-unit:region-2",
            "layer": 0,
            "side": "CENTER",
            "state": "OBSERVED",
            "coordinate_space": "PIXELS",
            "outline": [
                [336, 525], [670, 525], [690, 1450], [535, 1450],
                [512, 755], [489, 1450], [335, 1450],
            ],
        },
        {
            "part_id": "human-part:region-3",
            "kind": "HUMAN_OBSERVED_VISIBLE_REGION",
            "garment_unit": "human-visible-unit:region-3",
            "layer": 1,
            "side": "CENTER",
            "state": "OBSERVED",
            "coordinate_space": "PIXELS",
            "outline": [
                [505, 535], [715, 575], [730, 1215], [600, 1190],
                [515, 900],
            ],
        },
    ]
    relations = [
        {
            "relation_id": "human-layer:region-0->region-1",
            "kind": "LAYER",
            "parent_id": "human-part:region-0",
            "child_id": "human-part:region-1",
            "attachment_port": "human-visible-order:region-0->region-1",
            "attachment_side": "CENTER",
            "state": "PROPOSED",
            "source_state": "OBSERVED",
            "source": "HUMAN_EXPLICIT_FRONT_ORDER",
        },
        {
            "relation_id": "human-layer:region-2->region-3",
            "kind": "LAYER",
            "parent_id": "human-part:region-2",
            "child_id": "human-part:region-3",
            "attachment_port": "human-visible-order:region-2->region-3",
            "attachment_side": "CENTER",
            "state": "PROPOSED",
            "source_state": "OBSERVED",
            "source": "HUMAN_EXPLICIT_FRONT_ORDER",
        },
    ]
    request["visible_part_graph"] = {
        "graph_id": "test-only-human-multi-region-front",
        "parts": parts,
        "relations": relations,
    }
    return path, request


class GeometricAtelierWorkflowTests(unittest.TestCase):
    maxDiff = None

    def test_human_mode_stops_at_audit_but_prepares_candidate_specific_previews(self):
        result = run(_request(audit_mode="HUMAN_AUDIT"))

        self.assertEqual(result["phase"], "HUMAN_GARMENT_AUDIT_REQUIRED")
        self.assertFalse(result["front_confirmed"])
        self.assertEqual(result["body_avatar_fit"]["profile_catalog"]["count"], 10)
        self.assertGreaterEqual(result["rear_ensemble"]["candidate_count"], 2)
        self.assertTrue(result["candidate_front_invariant"]
                        ["all_candidates_preserve_identical_front"])
        self.assertEqual(result["pattern_handoffs"], [])
        self.assertFalse(result["manufacturing_certified"])

    def test_layered_second_skin_has_two_lower_components_and_explicit_owner(self):
        result = run(_request())
        topology = result["second_skin"]["topology"]
        surfaces = {row["surface_id"]: row for row in topology["surfaces"]}
        self.assertEqual(len(surfaces["lower"]["components"]), 2)
        relation = next(row for row in topology["relations"]
                        if row["child_id"] == "overlay")
        self.assertEqual(relation["kind"], "LAYER")
        self.assertEqual(relation["relation_id"], "typed-right-overlay")
        self.assertEqual(relation["attachment_port"],
                         "right-waist-overlay-anchor")
        self.assertEqual(relation["attachment_side"], "RIGHT")
        self.assertEqual(relation["ownership"]["owner_id"], relation["parent_id"])
        self.assertEqual(relation["child_layer"], 1)
        self.assertFalse(topology["name_based_branching"])

    def test_rear_candidates_change_only_rear_before_repair(self):
        result = run(_request())
        candidates = result["candidate_inputs"]
        self.assertGreaterEqual(len(candidates), 2)
        self.assertTrue(result["candidate_front_invariant"]
                        ["all_candidates_preserve_identical_front"])
        self.assertNotEqual(candidates[0]["mesh"]["vertices"],
                            candidates[1]["mesh"]["vertices"])
        states = result["second_skin"]["vertex_states"]
        front = [index for index, row in enumerate(states)
                 if row["front_hemisphere"]]
        rear = [index for index, row in enumerate(states)
                if not row["front_hemisphere"]]
        self.assertTrue(all(
            candidates[0]["mesh"]["vertices"][index]
            == candidates[1]["mesh"]["vertices"][index]
            for index in front
        ))
        self.assertTrue(any(
            candidates[0]["mesh"]["vertices"][index]
            != candidates[1]["mesh"]["vertices"][index]
            for index in rear
        ))
        source_contract = result["second_skin"]["source_front_contract"]
        self.assertTrue(result["candidate_front_invariant"]
                        ["source_front_contract_verified"])
        self.assertEqual(source_contract["digest"],
                         result["candidate_front_invariant"]
                         ["source_front_contract_digest"])
        self.assertTrue(all(not row["generic_cape_fallback"]
                            for row in candidates))
        self.assertTrue(all(row["mesh"]["geometry_source"]
                            == "SECOND_SKIN_PLUS_CANDIDATE_REAR_PROPOSAL"
                            for row in candidates))
        interfaces = [row["pattern_interface"] for row in candidates]
        self.assertEqual(len({row["digest"] for row in interfaces}),
                         len(interfaces))
        self.assertTrue(all(row["candidate_specific"] for row in interfaces))
        self.assertTrue(all(not row["generic_cape_fallback"]
                            for row in interfaces))
        self.assertTrue(all(row["source_front_digest"]
                            == source_contract["digest"]
                            for row in interfaces))
        self.assertTrue(all(
            boundary["candidate_id"] == interface["candidate_id"]
            and boundary["candidate_vertices_cm"]
            for interface in interfaces
            for boundary in interface["pattern_boundary_candidates"]
        ))
        self.assertTrue(all(
            {row["surface_id"] for row in interface["component_mesh_bindings"]}
            == {"upper", "lower", "overlay"}
            for interface in interfaces
        ))
        self.assertTrue(all(
            len([row for row in interface["component_mesh_bindings"]
                 if row["surface_id"] == "lower"]) == 2
            for interface in interfaces
        ))
        for interface in interfaces:
            overlay_attachment = next(
                row for row in interface["attachment_boundary_candidates"]
                if row["relation_id"] == "typed-right-overlay")
            self.assertTrue(overlay_attachment["parent_candidate_loops"])
            self.assertTrue(overlay_attachment["child_candidate_loops"])
            self.assertTrue(all(not row["closed_loop"]
                                for row in overlay_attachment
                                ["child_candidate_loops"]))
        from photoloset.geometric_atelier_workflow import _candidate_payloads
        corrupted = copy.deepcopy(result["second_skin"])
        corrupted["source_front_contract"]["digest"] = "tampered-front"
        with self.assertRaisesRegex(ValueError, "source-front contract digest"):
            _candidate_payloads(corrupted, result["rear_ensemble"], {})

    def test_front_geometry_distinguishes_skirt_shell_from_two_leg_tubes(self):
        skirt_graph = {
            "graph_id": "continuous-lower-front",
            "parts": [{
                "part_id": "shape-alpha",
                "kind": "UNTRANSLATABLE_SHAPE_ALPHA",
                "display_name": "not a generator token",
                "garment_unit": "unit-alpha",
                "layer": 0,
                "outline": [[0.36, 0.50], [0.64, 0.50],
                            [0.69, 0.94], [0.31, 0.94]],
            }],
        }
        trouser_graph = {
            "graph_id": "split-lower-front",
            "parts": [{
                "part_id": "shape-beta",
                "kind": "UNTRANSLATABLE_SHAPE_BETA",
                "display_name": "also not a generator token",
                "garment_unit": "unit-beta",
                "layer": 0,
                # One concave front ledger. The centre notch, rather than a
                # name or a fixture constant, creates two radial domains.
                "outline": [[0.31, 0.50], [0.69, 0.50],
                            [0.69, 0.94], [0.54, 0.94],
                            [0.54, 0.69], [0.46, 0.69],
                            [0.46, 0.94], [0.31, 0.94]],
            }],
        }

        skirt = run(_request(
            separation=_separation(layered=False),
            visible_part_graph=skirt_graph,
        ))
        trousers = run(_request(
            separation=_separation(layered=False),
            visible_part_graph=trouser_graph,
        ))
        skirt_surface = skirt["second_skin"]["topology"]["surfaces"][0]
        trouser_surface = trousers["second_skin"]["topology"]["surfaces"][0]
        self.assertEqual(1, len(skirt_surface["components"]))
        self.assertEqual("CONTINUOUS_FRONT_BOUNDARY",
                         skirt_surface["component_basis"])
        self.assertEqual(2, len(trouser_surface["components"]))
        self.assertEqual("SCALE_FREE_CENTRE_NOTCH_TWO_DOMAINS",
                         trouser_surface["component_basis"])
        self.assertEqual(2, trousers["second_skin"]["topology"]
                         ["topological_component_count"])
        self.assertFalse(skirt["surface_plan"]["name_based_branching"])
        self.assertFalse(trousers["surface_plan"]["name_based_branching"])

    def test_component_topology_is_affine_scale_invariant_not_fixture_specific(self):
        from photoloset.geometric_atelier_workflow import (
            _component_plan, _outline_component_count,
        )

        canonical = [[-13.0, 60.0], [13.0, 60.0], [13.0, 0.0],
                     [3.0, 0.0], [3.0, 38.0], [-3.0, 38.0],
                     [-3.0, 0.0], [-13.0, 0.0]]
        transformed = [[x * 7.25 + 431.0, y * 2.5 - 917.0]
                       for x, y in canonical]
        reversed_order = list(reversed(transformed))
        upper_cutout = [[-13.0, 0.0], [13.0, 0.0], [13.0, 60.0],
                        [3.0, 60.0], [3.0, 38.0], [-3.0, 38.0],
                        [-3.0, 60.0], [-13.0, 60.0]]
        self.assertEqual(
            (2, "SCALE_FREE_CENTRE_NOTCH_TWO_DOMAINS"),
            _outline_component_count(canonical),
        )
        self.assertEqual(_outline_component_count(canonical),
                         _outline_component_count(reversed_order))
        self.assertEqual((1, "CONTINUOUS_FRONT_BOUNDARY"),
                         _outline_component_count(upper_cutout))
        components, basis = _component_plan(
            {"part_id": "three-domain-ledger", "side": "CENTER",
             "topology": {"independent_component_count": 3}},
            unit_size=1, layer=0, world_outline=canonical,
        )
        self.assertEqual("TYPED_LEDGER_COMPONENT_COUNT", basis)
        self.assertEqual(3, len(components))
        self.assertEqual(
            [-round(2.0 / 3.0, 8), 0.0, round(2.0 / 3.0, 8)],
            [row["center_ratio"][0] for row in components],
        )

    def test_asymmetric_anime_like_part_uses_triangle_support_not_name_dispatch(self):
        graph = _layered_graph()
        for index, part in enumerate(graph["parts"]):
            part["kind"] = "ANIME_UNCLASSIFIED_%d" % index
            part["display_name"] = "架空部品-%d" % index
        result = run(_request(visible_part_graph=graph))
        overlay = next(row for row in result["second_skin"]["topology"]["surfaces"]
                       if row["surface_id"] == "overlay")
        projection = next(
            row for row in result["second_skin"]["front_cue_projections"]
            if row["surface_id"] == "overlay")
        relation = next(
            row for row in result["second_skin"]["topology"]["relations"]
            if row["child_id"] == "overlay")
        self.assertEqual([0.0, 90.0],
                         overlay["components"][0]["angular_coverage_deg"])
        self.assertGreater(projection["support_triangle_count"], 0)
        self.assertGreater(projection["matched_front_vertex_count"], 0)
        self.assertGreater(len(projection["matched_triangle_ids"]), 0)
        self.assertEqual("right-waist-overlay-anchor",
                         relation["attachment_port"])
        self.assertEqual("NONE", result["second_skin"]["jacobi_reduction"]
                         ["front_silhouette_axis_observed"])
        self.assertEqual(["PROPOSED"], result["second_skin"]
                         ["source_front_contract"]
                         ["silhouette_support_states"])
        self.assertFalse(result["second_skin"]["provenance"]
                         ["raw_garment_name_consumed"])

    def test_unknown_names_do_not_change_second_skin_geometry(self):
        first = run(_request())
        renamed = _layered_graph()
        for index, part in enumerate(renamed["parts"]):
            part["kind"] = "ANIME_UNKNOWN_%d" % index
            part["display_name"] = "new invented label %d" % index
        second = run(_request(visible_part_graph=renamed))

        self.assertEqual(first["second_skin"]["provenance"]["mesh_digest"],
                         second["second_skin"]["provenance"]["mesh_digest"])
        self.assertFalse(second["surface_plan"]["name_based_branching"])
        self.assertTrue(second["model_policy"]["unknown_garment_names_supported"])

    def test_requested_measurements_change_only_explicitly_allowed_controls(self):
        result = run(_request(
            requested_measurements={
                "height": {"value": 178.0, "unit": "cm",
                           "authority": "REQUESTED",
                           "source": {"kind": "USER_REQUEST"}},
                "waist": {"value": 61.0, "unit": "cm",
                          "authority": "REQUESTED",
                          "source": {"kind": "USER_REQUEST"}},
            },
            interpolation={"method": "LINEAR_BOUNDED",
                           "allowed_dimensions": ["height"]},
        ))
        avatar = result["body_avatar_fit"]["selected_avatar"]
        self.assertEqual(avatar["dimensions_cm"]["height"], 178.0)
        self.assertNotEqual(avatar["dimensions_cm"]["waist"], 61.0)
        self.assertFalse(result["body_avatar_fit"]["claims"]
                         ["body_measurements_inferred_from_pixels"])

    def test_siglip_and_multimodal_disagreement_remains_contested(self):
        fashion = {"matches": [{
            "item_id": "retrieved-a", "score": 0.98,
            "rear_structure": {"configuration": "center back opening"},
            "parts": ["rear layers"], "seam_topology": ["center seam"],
            "material": {"family": "woven"},
        }]}
        multimodal = {"proposals": [{
            "proposal_id": "model-b", "model_id": "fixture-vlm",
            "rear_structure": {"configuration": "closed side opening"},
            "parts": ["continuous rear"], "seams": ["side seam"],
            "material": {"family": "knit"},
        }]}
        result = run(_request(
            fashion_siglip_hits=fashion,
            multimodal_proposals=multimodal,
        ))
        rear = result["rear_ensemble"]
        self.assertTrue(rear["provider_status"]["fashion_siglip"]["available"])
        self.assertTrue(rear["provider_status"]["multimodal"]["available"])
        self.assertTrue(rear["contested"])
        self.assertFalse(rear["ranking"]["single_embedding_winner"])
        self.assertIsNone(rear["selected_candidate_id"])

    def test_human_confirmed_front_runs_bounded_same_camera_loop(self):
        result = run(_request(
            separation=_separation(authority="OBSERVED"),
            audit_mode="HUMAN_AUDIT",
            front_audit={"decision": "ACCEPT", "reviewer": "fixture-human"},
            human_edit_digest="sha256:human-clean-front",
            repair_config={"max_rounds": 2, "repair_gain": 1.0},
        ))
        self.assertTrue(result["front_confirmed"])
        self.assertNotEqual(
            result["candidate_3d_repair"]["verdict"],
            "PROPOSED_FRONT_AUDIT_REQUIRED_FOR_COMPARISON",
        )
        self.assertTrue(all(row["repair_transcript"]
                            for row in result["candidate_3d_repair"]["candidates"]
                            if "repair_transcript" in row))
        self.assertEqual(set(result["evidence_cross"]["arms"]), {
            "support+", "support-", "cause+", "cause-", "kind+", "kind-",
        })
        self.assertEqual(result["authority"]["rear"], "PROPOSED")
        self.assertEqual(result["authority"]["material"], "UNKNOWN")
        self.assertFalse(result["manufacturing_ready"])
        self.assertEqual(result["pattern_handoff_ready"],
                         bool(result["pattern_handoffs"]))

    def test_real_fixture_human_confirmation_invokes_repair_and_improves_iou(self):
        path, outline_px, request = _human_confirmed_fixture_request()
        with patch(
            "photoloset.geometric_atelier_workflow."
            "candidate_3d_repair_loop.run",
            wraps=candidate_3d_repair_loop.run,
        ) as repair_run:
            result = run(request)

        self.assertTrue(path.is_file())
        self.assertEqual(len(outline_px), 20)
        self.assertTrue(result["front_confirmed"])
        self.assertEqual(repair_run.call_count, 1)
        repair_request = repair_run.call_args.args[0]
        self.assertEqual(
            repair_request["target_front"]["reference_authority"],
            "HUMAN_CONFIRMED_TARGET",
        )
        self.assertTrue(
            repair_request["target_front"]["human_edit_digest"].startswith(
                "sha256:test-only-human-confirmed-"
            )
        )
        self.assertEqual(result["rear_ensemble"]["candidate_count"], 2)
        self.assertEqual(len(result["second_skin"]["mesh"]["vertices_cm"]), 40)
        self.assertEqual(len(result["second_skin"]["mesh"]["triangles"]), 64)

        measurements = []
        for candidate in result["candidate_3d_repair"]["candidates"]:
            support = candidate["repair_transcript"][0]["evidence_cross"][
                "arms"]["support+"]
            loss = next(
                row["value"] for row in support
                if row["path"] == "front/silhouette/iou_loss"
            )
            initial_iou = 1.0 - float(loss)
            final_iou = float(candidate["final_evaluation"]["axes"][
                "silhouette"]["iou"])
            measurements.append((initial_iou, final_iou))
            self.assertGreater(final_iou, initial_iou)
            self.assertEqual(
                candidate["final_evaluation"]["convergence"]["status"],
                "CONVERGED",
            )
            self.assertEqual(
                candidate["final_evaluation"]["convergence"]["unmet_bounds"],
                [],
            )
            self.assertIsNone(candidate["non_improvement_stop"])
            self.assertEqual(
                candidate["verdict"], "HUMAN_REVIEW_REQUIRED")
            self.assertEqual(
                candidate["human_approval_gate"]["verdict"],
                "HUMAN_REVIEW_REQUIRED",
            )
            self.assertIsNone(candidate["pattern_handoff"])

        self.assertEqual(len(measurements), 2)
        for initial_iou, final_iou in measurements:
            self.assertAlmostEqual(initial_iou, 0.6562841530054645, places=12)
            self.assertAlmostEqual(final_iou, 0.9297676931388439, places=12)
        self.assertFalse(result["pattern_handoff_ready"])
        self.assertEqual(result["pattern_handoffs"], [])

    def test_real_fixture_multiple_human_regions_preserve_parts_and_layer_order(self):
        path, request = _human_confirmed_multi_region_fixture_request()
        with patch(
            "photoloset.geometric_atelier_workflow."
            "candidate_3d_repair_loop.run",
            wraps=candidate_3d_repair_loop.run,
        ) as repair_run:
            result = run(request)

        self.assertTrue(path.is_file())
        self.assertTrue(result["front_confirmed"])
        self.assertEqual(repair_run.call_count, 1)
        repair_target = repair_run.call_args.args[0]["target_front"]
        self.assertEqual(
            repair_target["reference_authority"],
            "HUMAN_CONFIRMED_TARGET",
        )
        self.assertEqual(len(repair_target["typed_part_masks"]), 4)
        self.assertEqual(len(repair_target["observed_layer_relations"]), 2)
        self.assertTrue(all(
            row["state"] == "OBSERVED"
            and row["source"] == "HUMAN_EXPLICIT_FRONT_ORDER"
            for row in repair_target["observed_layer_relations"]
        ))
        self.assertEqual(len(result["visible_part_graph"]["parts"]), 4)
        self.assertEqual(len(result["second_skin"]["topology"]["surfaces"]), 4)
        self.assertEqual(len(result["second_skin"]["mesh"]["vertices_cm"]), 285)
        self.assertEqual(len(result["second_skin"]["mesh"]["triangles"]), 448)

        measurements = []
        for candidate in result["candidate_3d_repair"]["candidates"]:
            support = candidate["repair_transcript"][0]["evidence_cross"][
                "arms"]["support+"]
            loss = next(
                row["value"] for row in support
                if row["path"] == "front/silhouette/iou_loss"
            )
            initial_iou = 1.0 - float(loss)
            final = candidate["final_evaluation"]
            final_iou = float(final["axes"]["silhouette"]["iou"])
            layer = final["axes"]["layer_occlusion"]
            measurements.append((initial_iou, final_iou))
            self.assertGreater(final_iou, initial_iou)
            self.assertEqual(layer["status"], "SCORED")
            self.assertEqual(layer["relation_authority"],
                             "HUMAN_EXPLICIT_FRONT_ORDER")
            self.assertEqual(len(layer["observation_relations"]), 2)
            self.assertEqual(layer["missing_observed_relations"], [])
            self.assertEqual(layer["reversed_observed_relations"], [])
            self.assertEqual(candidate["verdict"],
                             "HUMAN_REVIEW_REPAIR_UNAVAILABLE")

        self.assertEqual(len(measurements), 2)
        self.assertAlmostEqual(measurements[0][0], 0.6320132013201321,
                               places=12)
        self.assertAlmostEqual(measurements[1][0], 0.6311881188118812,
                               places=12)
        self.assertTrue(all(
            abs(final_iou - 0.9228896103896104) < 1.0e-12
            for _, final_iou in measurements
        ))
        self.assertFalse(result["pattern_handoff_ready"])
        self.assertEqual(result["pattern_handoffs"], [])

    def test_single_audited_mask_can_scaffold_unsegmented_vlm_parts(self):
        graph = {
            "graph_id": "vlm-ledger-before-part-segmentation",
            "parts": [
                {"part_id": "model-upper", "garment_unit": "unit-upper",
                 "kind": "MODEL_PROPOSED_UPPER", "layer": 0},
                {"part_id": "model-overlay", "garment_unit": "unit-overlay",
                 "kind": "MODEL_PROPOSED_OVERLAY", "layer": 1,
                 "side": "RIGHT"},
            ],
        }
        result = run(_request(
            separation=_separation(layered=False),
            visible_part_graph=graph,
        ))

        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(
            {row["outline_binding"] for row in result["visible_part_graph"]["parts"]},
            {"SHARED_AGGREGATE_FRONT_MASK_PROPOSAL"},
        )
        self.assertTrue(all(
            row["part_boundary_observed"] is False
            for row in result["visible_part_graph"]["parts"]
        ))
        self.assertEqual(result["phase"], "AUTO_PROPOSED_3D_PREVIEW_READY")

    def test_input_order_is_deterministic(self):
        first = run(_request())
        graph = _layered_graph()
        graph["parts"].reverse()
        second = run(_request(visible_part_graph=graph))
        self.assertEqual(first["digest"], second["digest"])
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
