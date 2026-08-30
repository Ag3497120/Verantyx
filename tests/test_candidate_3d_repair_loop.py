#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import unittest

from photoloset.candidate_3d_repair_loop import (
    ANSWER,
    EVIDENCE_CROSS_SCHEMA,
    PHYSICAL_CROSS_SCHEMA,
    REAR_HYPOTHESIS_AXES,
    REQUEST_SCHEMA,
    run,
)


CAMERA = {
    "projection": "orthographic",
    "view": "front",
    "position": [0.0, 0.0, 5.0],
    "target": [0.0, 0.0, 0.0],
    "scale": 1.0,
}


def _rect_mask(left=2, top=2, right=10, bottom=10, size=12):
    return [[int(left <= column < right and top <= row < bottom)
             for column in range(size)] for row in range(size)]


def _target():
    mask = _rect_mask()
    return {
        "camera": copy.deepcopy(CAMERA),
        "reference_authority": "OBSERVED",
        "silhouette_mask": {"mask": copy.deepcopy(mask),
                            "state": "OBSERVED"},
        "typed_part_masks": {
            "body": {"mask": copy.deepcopy(mask),
                     "state": "OBSERVED", "layer": 0},
            # Rear information remains explicitly outside the scored front.
            "rear": {"mask": copy.deepcopy(mask), "state": "UNKNOWN",
                     "visibility": "REAR", "layer": 1},
        },
        "occlusion_unknown_mask": [[0] * 12 for _ in range(12)],
    }


def _candidate(candidate_id="candidate-a", *, width=2.0, depth=0.0,
               authority="PROPOSED", rear_profile=None,
               input_kind="unclassified"):
    profile = dict(rear_profile or {
        "closure": "CLOSED_OR_UNSEEN",
        "back_volume": "FITTED_CONTINUATION",
        "layer_continuation": "CONTINUE_EACH_VISIBLE_LAYER",
        "attachment_topology": "MATCHING_BOUNDARY_SEAM",
    })
    return {
        "candidate_id": candidate_id,
        "candidate_digest": "digest-%s" % candidate_id,
        "domain": "BACK_STRUCTURE",
        "input_kind_for_test_only": input_kind,
        "authority": {"rear": authority, "material": "PROPOSED"},
        "rear_hypothesis": {
            "schema": "garment.typed-rear-hypothesis.v1",
            "state": "PROPOSED",
            "observation_state": "UNKNOWN_UNOBSERVED",
            "axis_values": profile,
            "axes_are_independent": True,
            "conflicts_are_not_averaged": True,
        },
        "mesh": {
            "units": "cm",
            "vertices": [
                [-width / 2.0, -2.0, depth],
                [width / 2.0, -2.0, depth],
                [width / 2.0, 2.0, depth],
                [-width / 2.0, 2.0, depth],
            ],
            "faces": [[0, 1, 2], [0, 2, 3]],
            "face_node_ids": ["body", "body"],
            "face_layers": [0, 0],
        },
        "pattern_handoff": {
            "candidate_id": candidate_id,
            "state": "PROPOSED",
            "pieces": [{"piece_id": "body-front"}],
            "sewing_order": ["body-front"],
        },
    }


def _request(*candidates, max_rounds=3, repair_gain=1.0):
    return {
        "schema": REQUEST_SCHEMA,
        "target_front": _target(),
        "candidates": list(candidates),
        "config": {"max_rounds": max_rounds,
                   "repair_gain": repair_gain},
        "projection_config": {
            "min_silhouette_iou": 0.95,
            "min_part_iou": 0.95,
            "max_edge_chamfer_normalized": 0.01,
            "min_render_known_coverage": 0.95,
        },
    }


def _only(result):
    if len(result["candidates"]) != 1:
        raise AssertionError(result)
    return result["candidates"][0]


class Candidate3DRepairLoopTests(unittest.TestCase):
    def test_structural_candidates_keep_distinct_geometry_not_generic_fallback(self):
        first = _candidate("rear-flat", depth=0.0)
        second = _candidate("rear-deep", depth=1.5)

        result = run(_request(second, first))

        self.assertEqual(result["distinct_geometry_check"]["verdict"], ANSWER)
        self.assertFalse(result["distinct_geometry_check"]["generic_fallback_used"])
        rows = {row["candidate_id"]: row for row in result["candidates"]}
        self.assertEqual(set(rows), {"rear-flat", "rear-deep"})
        self.assertNotEqual(rows["rear-flat"]["before_shape_digest"],
                            rows["rear-deep"]["before_shape_digest"])
        self.assertTrue(all(row["candidate_geometry"]["source"]
                            ["candidate_specific"] for row in rows.values()))
        self.assertTrue(all(not row["candidate_geometry"]["source"]
                            ["generic_fallback_used"] for row in rows.values()))

    def test_identical_structural_geometry_stops_instead_of_renaming_fallback(self):
        result = run(_request(_candidate("a"), _candidate("b")))

        self.assertEqual(
            result["distinct_geometry_check"]["verdict"],
            "UNKNOWN_CANDIDATE_GEOMETRY_NOT_DISTINCT")
        self.assertEqual(
            {row["verdict"] for row in result["candidates"]},
            {"UNKNOWN_CANDIDATE_GEOMETRY_NOT_DISTINCT"})
        self.assertTrue(all(row["pattern_handoff"] is None
                            for row in result["candidates"]))

    def test_same_camera_axes_improve_in_a_bounded_repair_round(self):
        result = run(_request(_candidate(), max_rounds=3))
        row = _only(result)

        self.assertEqual(row["verdict"], "HUMAN_REVIEW_REQUIRED")
        self.assertEqual(row["final_evaluation"]["convergence"]["status"],
                         "CONVERGED")
        self.assertEqual(row["rounds"], 2)
        self.assertNotEqual(row["before_geometry_digest"],
                            row["after_geometry_digest"])
        first_cross = row["repair_transcript"][0]["evidence_cross"]
        self.assertEqual(first_cross["schema"], EVIDENCE_CROSS_SCHEMA)
        self.assertEqual(set(first_cross["arms"]), {
            "support+", "support-", "cause+", "cause-", "kind+", "kind-",
        })
        before_iou = 1.0 - next(
            item["value"] for item in first_cross["arms"]["support+"]
            if item["path"] == "front/silhouette/iou_loss")
        after_iou = row["final_evaluation"]["axes"]["silhouette"]["iou"]
        self.assertLess(before_iou, after_iou)
        self.assertEqual(after_iou, 1.0)
        self.assertEqual(row["physical_cross"]["schema"],
                         PHYSICAL_CROSS_SCHEMA)
        self.assertEqual(set(row["physical_cross"]["arms"]), {
            "warp+", "warp-", "weft+", "weft-", "normal+", "normal-",
        })
        self.assertEqual(row["proof_cross"]["verdict"], ANSWER)
        self.assertIsNone(row["pattern_handoff"])

    def test_repairs_are_candidate_specific_and_preserve_typed_rear_axes(self):
        flat = _candidate("rear-flat", depth=0.0, rear_profile={
            "closure": "CENTER_BACK_JOIN",
            "back_volume": "FITTED_CONTINUATION",
            "layer_continuation": "CONTINUE_EACH_VISIBLE_LAYER",
            "attachment_topology": "MATCHING_BOUNDARY_SEAM",
        })
        deep = _candidate("rear-deep", depth=1.5, rear_profile={
            "closure": "SIDE_OPENING",
            "back_volume": "EASED_VOLUME",
            "layer_continuation": "INDEPENDENT_REAR_LAYER",
            "attachment_topology": "WAIST_ANCHORED",
        })

        rows = {row["candidate_id"]: row
                for row in run(_request(flat, deep))["candidates"]}
        proposal_ids = []
        for row in rows.values():
            self.assertEqual(
                set(REAR_HYPOTHESIS_AXES),
                {item["axis"] for item in row["rear_axis_constraints"]})
            self.assertTrue(all(
                item["operation"] == "PRESERVE_TYPED_REAR_AXIS"
                and not item["applied_from_front_evidence"]
                for item in row["rear_axis_constraints"]))
            contract = row["comparison_contract"]
            self.assertTrue(contract["same_camera_required"])
            self.assertTrue(contract["no_aggregate_similarity_score"])
            self.assertTrue(all(
                value["present"]
                for value in contract["independent_comparisons"].values()))
            first = row["repair_transcript"][0]
            self.assertEqual(first["rear_axis_constraints"],
                             row["rear_axis_constraints"])
            proposals = first["candidate_specific_proposals"]
            self.assertTrue(proposals)
            self.assertTrue(all(
                proposal["candidate_id"] == row["candidate_id"]
                and proposal["mutation_domain"] == "VISIBLE_FRONT_ONLY"
                and proposal["preserve_unobserved_rear_hypothesis"]
                for proposal in proposals))
            proposal_ids.extend(proposal["proposal_id"]
                                for proposal in proposals)
        self.assertEqual(len(proposal_ids), len(set(proposal_ids)))

    def test_non_improving_attempt_is_rolled_back_and_stops(self):
        row = _only(run(_request(
            _candidate(), max_rounds=4, repair_gain=0.001)))

        self.assertEqual(row["verdict"],
                         "HUMAN_REVIEW_NON_IMPROVEMENT")
        self.assertEqual(row["rounds"], 2)
        self.assertEqual(row["before_geometry_digest"],
                         row["after_geometry_digest"])
        stop = row["non_improvement_stop"]
        self.assertEqual(stop["status"], "STALLED_TIE")
        self.assertNotEqual(stop["attempted_geometry_digest"],
                            stop["restored_geometry_digest"])
        self.assertEqual(stop["restored_geometry_digest"],
                         row["after_geometry_digest"])
        self.assertTrue(stop["stopped_without_applying_more_repairs"])
        last = row["repair_transcript"][-1]
        self.assertTrue(last["non_improvement_stop"])
        self.assertEqual(last["rollback"], stop)
        self.assertIsNone(row["pattern_handoff"])

    def test_rear_alternatives_must_preserve_shared_front_contract(self):
        result = run(_request(
            _candidate("narrow", width=2.0, depth=0.0),
            _candidate("wide", width=3.0, depth=1.0),
        ))

        self.assertEqual(
            result["front_preservation_check"]["verdict"],
            "UNKNOWN_CANDIDATE_FRONT_NOT_PRESERVED")
        self.assertEqual(
            result["front_preservation_check"]["method"],
            "COMPUTED_FRONT_XY_TOPOLOGY_CONTRACT")
        self.assertEqual(
            {row["verdict"] for row in result["candidates"]},
            {"UNKNOWN_CANDIDATE_FRONT_NOT_PRESERVED"})
        self.assertTrue(all(row["pattern_handoff"] is None
                            for row in result["candidates"]))

    def test_non_convergence_is_an_explicit_human_stop_at_budget(self):
        row = _only(run(_request(_candidate(), max_rounds=1)))

        self.assertEqual(row["verdict"], "HUMAN_REVIEW_NON_CONVERGENCE")
        self.assertEqual(row["stop"]["kind"], "HUMAN_REVIEW")
        self.assertEqual(row["rounds"], 1)
        self.assertEqual(row["final_evaluation"]["convergence"]["status"],
                         "MAX_ROUNDS_REACHED")
        self.assertIsNone(row["pattern_handoff"])

    def test_unobserved_rear_and_material_never_gain_observed_authority(self):
        row = _only(run(_request(_candidate())))

        self.assertEqual(row["state"], "PROPOSED")
        self.assertEqual(row["authority"]["rear"], "PROPOSED")
        self.assertEqual(row["authority"]["material"], "UNKNOWN")
        self.assertFalse(row["rear_observed"])
        self.assertFalse(row["material_measured"])
        self.assertEqual(row["fact_promotions"], [])
        kind_minus = row["evidence_cross"]["arms"]["kind-"]
        self.assertEqual({item["path"] for item in kind_minus},
                         {"kind/rear", "kind/material"})
        self.assertTrue(all(item["authority"] in {"PROPOSED", "UNKNOWN"}
                            for item in kind_minus))

        promoted = _only(run(_request(
            _candidate("bad-authority", authority="OBSERVED"))))
        self.assertEqual(promoted["verdict"],
                         "UNKNOWN_UNOBSERVED_AUTHORITY_PROMOTION")
        self.assertIsNone(promoted["pattern_handoff"])

    def test_pattern_handoff_requires_exact_final_digest_and_named_approval(self):
        candidate = _candidate()
        first = _only(run(_request(candidate)))
        self.assertIsNone(first["pattern_handoff"])

        approved = _candidate()
        approved["human_approval"] = {
            "candidate_id": "candidate-a",
            "candidate_digest": "digest-candidate-a",
            "final_geometry_digest": first["after_geometry_digest"],
            "decision": "APPROVE",
            "by": "pattern reviewer",
        }
        second = _only(run(_request(approved)))

        self.assertEqual(second["verdict"], ANSWER)
        self.assertIsNotNone(second["pattern_handoff"])
        self.assertEqual(second["pattern_handoff"]["final_geometry_digest"],
                         second["after_geometry_digest"])
        self.assertEqual(second["pattern_handoff"]["authority"]["rear"],
                         "PROPOSED")
        self.assertFalse(second["pattern_handoff"]["manufacturing_certified"])

        stale_approval = copy.deepcopy(approved)
        stale_approval["human_approval"]["candidate_digest"] = "stale"
        rejected = _only(run(_request(stale_approval)))
        self.assertEqual(rejected["verdict"],
                         "HUMAN_REVIEW_STALE_OR_INCOMPLETE")
        self.assertIsNone(rejected["pattern_handoff"])

        stale = copy.deepcopy(approved)
        stale["pattern_handoff"]["candidate_id"] = "another-candidate"
        stopped = _only(run(_request(stale)))
        self.assertEqual(stopped["verdict"],
                         "UNKNOWN_PATTERN_CANDIDATE_BINDING")
        self.assertIsNone(stopped["pattern_handoff"])

    def test_optional_wind_material_scenario_is_never_a_measurement(self):
        request = _request(_candidate())
        request["scenarios"] = [{
            "scenario_id": "light-wind",
            "candidate_id": "candidate-a",
            "steps": 2,
            "material": {
                "areal_density_kg_m2": 0.2,
                "warp_stiffness_n_m": 100.0,
                "weft_stiffness_n_m": 80.0,
                "shear_stiffness_n_m": 20.0,
                "bending_stiffness_n_m": 0.01,
                "damping_ratio": 0.1,
                "drag_coefficient": 1.0,
                "lift_coefficient": 0.0,
            },
            "environment": {
                "gravity_m_s2": [0.0, -9.81, 0.0],
                "wind_velocity_m_s": [1.0, 0.0, 0.0],
            },
        }]

        row = _only(run(request))
        scenario = row["scenario_results"][0]
        self.assertEqual(scenario["verdict"], ANSWER)
        self.assertEqual(scenario["authority"], "PROPOSED_SIMULATION")
        self.assertTrue(scenario["not_measurement"])
        self.assertTrue(scenario["does_not_update_candidate_material"])
        self.assertFalse(row["physical_cross"]
                         ["scenario_values_are_measurements"])
        self.assertEqual(row["authority"]["material"], "UNKNOWN")

    def test_class_independent_contract_holds_for_non_overfit_input_matrix(self):
        cases = [
            ("skirt", {
                "closure": "SIDE_OPENING",
                "back_volume": "FLARED_VOLUME",
                "layer_continuation": "CONTINUE_EACH_VISIBLE_LAYER",
                "attachment_topology": "WAIST_ANCHORED",
            }),
            ("trousers", {
                "closure": "CENTER_BACK_JOIN",
                "back_volume": "FITTED_CONTINUATION",
                "layer_continuation": "CONTINUE_EACH_VISIBLE_LAYER",
                "attachment_topology": "MATCHING_BOUNDARY_SEAM",
            }),
            ("layered-asymmetric", {
                "closure": "OVERLAPPED_WRAP_CLOSURE",
                "back_volume": "ASYMMETRIC_DRAPED_VOLUME",
                "layer_continuation": "INDEPENDENT_REAR_LAYER",
                "attachment_topology": "WAIST_ANCHORED",
            }),
            ("anime-like", {
                "closure": "CLOSED_OR_UNSEEN",
                "back_volume": "EASED_VOLUME",
                "layer_continuation": "ASYMMETRIC_REAR_CONTINUATION",
                "attachment_topology": "SHOULDER_OR_YOKE_ANCHORED",
            }),
        ]

        for index, (kind, profile) in enumerate(cases):
            with self.subTest(kind=kind):
                row = _only(run(_request(_candidate(
                    "case-%d" % index, depth=index * 0.1,
                    rear_profile=profile, input_kind=kind))))
                self.assertFalse(row["candidate_geometry"]["source"]
                                 ["generic_fallback_used"])
                self.assertEqual(
                    profile, row["rear_hypothesis"]["axis_values"])
                self.assertEqual(
                    set(REAR_HYPOTHESIS_AXES),
                    {item["axis"] for item in row["rear_axis_constraints"]})
                self.assertTrue(row["comparison_contract"]
                                ["no_aggregate_similarity_score"])
                self.assertNotEqual(row["verdict"],
                                    "UNKNOWN_CANDIDATE_SPECIFIC_GEOMETRY_REQUIRED")

    def test_output_is_deterministic_and_candidate_input_order_independent(self):
        request = _request(_candidate("z", depth=1.0),
                           _candidate("a", depth=0.0))
        first = run(request)
        second = run(copy.deepcopy(request))
        reversed_request = copy.deepcopy(request)
        reversed_request["candidates"].reverse()
        third = run(reversed_request)

        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual([row["candidate_id"] for row in first["candidates"]],
                         ["a", "z"])
        json.dumps(first, sort_keys=True, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
