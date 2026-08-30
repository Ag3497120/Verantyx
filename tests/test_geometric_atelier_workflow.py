#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import unittest

from photoloset.geometric_atelier_workflow import REQUEST_SCHEMA, run


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
