#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import unittest
from typing import Any, Dict, Iterable

from photoloset.front_candidate_evaluator import AXES, evaluate_candidates
from photoloset.front_structure_hypotheses import (
    CueState,
    FrontStructureCues,
    TypedCue,
    hypothesize_front_structure,
)
from photoloset import structure_preview
from photoloset import structure_to_pattern


def _cue(value: Any, *, state: CueState = CueState.OBSERVED) -> TypedCue:
    return TypedCue(
        value, state,
        "typed visible-front fixture evidence",
        "a corrected front annotation or another view contradicts it",
    )


def _candidates():
    cues = FrontStructureCues(
        source_id="fixture:evaluator-front",
        composition=_cue("one_piece"),
        silhouette=_cue("flared"),
        lower_shape=_cue("flare"),
        sleeve_shape=_cue("long"),
        layer_count=_cue(1),
        details=_cue(()),
    )
    return cues, hypothesize_front_structure(cues)


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


class FrontCandidateEvaluatorTests(unittest.TestCase):
    maxDiff = None

    def test_reports_seven_independent_axes_without_aggregate_or_certification(self):
        cues, candidates = _candidates()
        first = evaluate_candidates(candidates, front_evidence=cues.as_dict())
        second = evaluate_candidates(list(reversed(candidates)),
                                     front_evidence=cues.as_dict())

        self.assertEqual(first, second)
        self.assertEqual(first["axes"], list(AXES))
        self.assertEqual(len(first["candidates"]), 2)
        self.assertFalse(first["manufacturing_ready"])
        self.assertFalse(first["manufacturing_certified"])
        self.assertFalse(first["claims"]["single_aggregate_used"])
        self.assertIsNone(first["selected_candidate_id"])
        self.assertEqual(first["rear_authority"], "PROPOSED")
        self.assertEqual(first["material_authority"], "PROPOSED")
        self.assertFalse(any("score" in key.lower()
                             for key in _walk_keys(first)))

        for report in first["candidates"]:
            self.assertEqual(set(report["axes"]), set(AXES))
            self.assertEqual(report["verdict"],
                             "REVIEW_FRONT_CANDIDATE_APPROVAL_REQUIRED")
            self.assertEqual(
                report["axes"]["front_silhouette_consistency"]["disposition"],
                "SATISFIED")
            self.assertEqual(
                report["axes"]["layer_order_consistency"]["disposition"],
                "SATISFIED")
            self.assertEqual(
                report["axes"]["topology_validity"]["disposition"],
                "SATISFIED")
            self.assertEqual(
                report["axes"]["closure_donning_plausibility"]["disposition"],
                "REVIEW")
            self.assertEqual(
                report["axes"]["pattern_lowerability"]["disposition"],
                "SATISFIED")
            self.assertEqual(
                report["axes"]["candidate_specific_3d_availability"]["disposition"],
                "SATISFIED")
            self.assertEqual(
                report["axes"]["evidence_authority"]["disposition"],
                "SATISFIED")
            reason_codes = {row["verdict"] for row in report["review_reasons"]}
            self.assertIn("REVIEW_REAR_STRUCTURE_PROPOSED", reason_codes)
            self.assertIn("REVIEW_MATERIAL_PROPOSED", reason_codes)
            self.assertIn("REVIEW_MANUFACTURING_CERTIFICATION_NOT_CREATED",
                          reason_codes)
            self.assertFalse(report["manufacturing_ready"])
            self.assertFalse(report["manufacturing_certified"])

        json.dumps(first, sort_keys=True, allow_nan=False)

    def test_pareto_dominance_uses_axis_dispositions_and_keeps_review(self):
        cues, candidates = _candidates()
        stronger = copy.deepcopy(candidates[0])
        weaker = copy.deepcopy(candidates[0])
        stronger["candidate_id"] = "candidate-consistent"
        weaker["candidate_id"] = "candidate-front-conflict"
        for node in weaker["nodes"]:
            attributes = node.get("attributes", {})
            if "front_silhouette" in attributes:
                attributes["front_silhouette"] = "straight"

        result = evaluate_candidates(
            [weaker, stronger], front_evidence=cues.as_dict())
        self.assertEqual(result["pareto_frontier"], ["candidate-consistent"])
        self.assertEqual(result["verdict"],
                         "REVIEW_FRONT_CANDIDATE_APPROVAL_REQUIRED")
        self.assertEqual(result["dominance"], [{
            "dominant_candidate_id": "candidate-consistent",
            "dominated_candidate_id": "candidate-front-conflict",
            "strictly_better_axes": ["front_silhouette_consistency"],
            "equal_or_better_on_all_axes": True,
        }])
        reports = {row["candidate_id"]: row for row in result["candidates"]}
        self.assertEqual(
            reports["candidate-front-conflict"]["axes"]
            ["front_silhouette_consistency"]["verdict"],
            "UNKNOWN_FRONT_SILHOUETTE_CONFLICT")
        self.assertIsNone(result["selected_candidate_id"])

    def test_tradeoffs_remain_on_pareto_frontier_instead_of_being_summed(self):
        cues, candidates = _candidates()
        first = copy.deepcopy(candidates[0])
        second = copy.deepcopy(candidates[0])
        first["candidate_id"] = "candidate-front-review"
        second["candidate_id"] = "candidate-preview-review"
        for node in first["nodes"]:
            node.get("attributes", {}).pop("front_silhouette", None)

        preview = structure_preview.generate_preview(
            {key: second[key] for key in ("schema", "nodes", "operations")},
            candidate_id=second["candidate_id"])
        preview["verdict"] = "REVIEW_CANDIDATE_3D_REFINEMENT_REQUIRED"
        preview["why"] = "fixture keeps candidate-specific 3D under review"

        result = evaluate_candidates(
            [first, second], front_evidence=cues.as_dict(),
            previews={second["candidate_id"]: preview})
        self.assertEqual(
            result["pareto_frontier"],
            ["candidate-front-review", "candidate-preview-review"])
        self.assertEqual(result["dominance"], [])
        self.assertEqual(result["verdict"],
                         "REVIEW_FRONT_CANDIDATE_SELECTION_REQUIRED")

    def test_tampered_rear_or_material_authority_is_rejected(self):
        cues, candidates = _candidates()
        candidate = copy.deepcopy(candidates[0])
        candidate["candidate_id"] = "candidate-authority-leak"
        candidate["back_alternative"]["state"] = "OBSERVED"
        candidate["material_candidate"] = {
            "state": "APPROVED", "value": "melton",
        }

        result = evaluate_candidates([candidate],
                                     front_evidence=cues.as_dict())
        report = result["candidates"][0]
        authority = report["axes"]["evidence_authority"]
        self.assertEqual(authority["disposition"], "UNSATISFIED")
        self.assertEqual(authority["verdict"],
                         "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION")
        paths = {row["path"] for row in authority["observations"]["violations"]}
        self.assertIn("back_alternative/state", paths)
        self.assertIn("material_candidate/state", paths)
        self.assertEqual(report["rear_authority"], "PROPOSED")
        self.assertEqual(report["material_authority"], "PROPOSED")
        self.assertFalse(report["manufacturing_certified"])

    def test_candidate_artifacts_are_bound_by_id(self):
        cues, candidates = _candidates()
        candidate = copy.deepcopy(candidates[0])
        candidate["candidate_id"] = "candidate-a"
        structure = {key: candidate[key]
                     for key in ("schema", "nodes", "operations")}
        pattern = structure_to_pattern.compile(
            structure, candidate_state="PROPOSED", candidate_id="candidate-b")
        preview = structure_preview.generate_preview(
            structure, candidate_id="candidate-b")

        result = evaluate_candidates(
            [candidate], front_evidence=cues.as_dict(),
            patterns={"candidate-a": pattern},
            previews={"candidate-a": preview})
        axes = result["candidates"][0]["axes"]
        self.assertEqual(axes["pattern_lowerability"]["verdict"],
                         "UNKNOWN_PATTERN_CANDIDATE_ID_MISMATCH")
        self.assertEqual(axes["candidate_specific_3d_availability"]["verdict"],
                         "UNKNOWN_CANDIDATE_3D_ID_MISMATCH")
        self.assertFalse(result["manufacturing_certified"])


if __name__ == "__main__":
    unittest.main()
