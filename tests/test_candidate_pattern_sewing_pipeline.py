#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import unittest
from unittest import mock

from photoloset import candidate_pattern_sewing_pipeline as pipeline
from photoloset.candidate_pattern_sewing_pipeline import (
    REQUEST_SCHEMA,
    assemble,
    bind,
    stable_digest,
)
from photoloset.front_candidate_artifact_pipeline import assemble as front_assemble
from photoloset.front_image_generation_contract import (
    REQUEST_SCHEMA as FRONT_REQUEST_SCHEMA,
    REQUIRED_WEARER_MEASUREMENTS,
)


def _part(part_id, kind, dimensions, placement, *, unit="look", layer=0,
          **extra):
    row = {
        "part_id": part_id,
        "kind": kind,
        "dimensions": copy.deepcopy(dimensions),
        "placement": placement,
        "garment_unit": unit,
        "layer": layer,
        "visible_basis": {
            "state": "PROPOSED",
            "basis": f"front geometry supports {part_id} as a proposal",
            "breaks_when": "another view or human review contradicts it",
        },
    }
    row.update(extra)
    return row


def _body(*, circumference=90.0, unit="look", part_id="body", layer=0):
    return _part(
        part_id, "BODY_SHELL",
        {"height_cm": 43.0, "circumference_cm": circumference},
        "front torso", unit=unit, layer=layer,
    )


def _skirt(*, circumference=76.0, unit="look", **extra):
    return _part(
        "skirt", "FLARE",
        {"height_cm": 64.0, "top_circumference_cm": circumference,
         "bottom_circumference_cm": 172.0},
        "lower body", unit=unit, **extra,
    )


def _candidate(candidate_id, parts):
    return {
        "candidate_id": candidate_id,
        "state": "PROPOSED",
        "parts": copy.deepcopy(parts),
        "rear_hypothesis": {
            "state": "PROPOSED",
            "value": "unknown rear construction alternative",
            "basis": "the rear is absent from the front image",
            "breaks_when": "a rear or side view is supplied",
        },
        "material_hypothesis": {
            "state": "PROPOSED",
            "value": "bounded material alternative",
            "basis": "appearance does not measure material mechanics",
            "breaks_when": "a swatch or material test is supplied",
        },
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }


def _measurements():
    return {
        name: {
            "value_cm": 82.0 + index,
            "authority": "USER_PROVIDED",
            "source": "named target wearer",
        }
        for index, name in enumerate(REQUIRED_WEARER_MEASUREMENTS)
    }


def _request(candidate):
    return {
        "schema": REQUEST_SCHEMA,
        "front_image_request": {
            "schema": FRONT_REQUEST_SCHEMA,
            "source": {"image_id": "sha256:cut-sew-front", "view": "front"},
            "vision": {
                "observations": [{
                    "claim_id": "front-outline",
                    "field": "front.silhouette",
                    "value": "candidate geometry supplied below",
                    "authority": "OBSERVED",
                    "basis": "corrected visible front boundary",
                }],
                "proposals": [{
                    "claim_id": "front-depth",
                    "field": "front.depth_interpretation",
                    "value": "candidate dependent",
                    "authority": "PROPOSED",
                    "basis": "one front image does not observe depth",
                }],
            },
            "wearer_measurements": _measurements(),
            "candidates": [candidate],
            "artifacts": {},
            "approvals": {},
            "rounds": [],
            "max_rounds": 8,
        },
    }


def _only(result):
    if len(result["candidates"]) != 1:
        raise AssertionError(result)
    return result["candidates"][0]


def _two_candidate_request():
    request = _request(_candidate("narrow", [
        _body(circumference=82.0, unit="upper"),
        _skirt(circumference=70.0, unit="lower"),
    ]))
    request["front_image_request"]["candidates"].append(_candidate("wide", [
        _body(circumference=100.0, unit="upper"),
        _skirt(circumference=88.0, unit="lower"),
    ]))
    return request


def _reseal(row, digest_field):
    payload = {key: copy.deepcopy(value) for key, value in row.items()
               if key != digest_field}
    row[digest_field] = stable_digest(payload)


class CandidatePatternSewingPipelineTests(unittest.TestCase):
    maxDiff = None

    def assert_bound_review(self, result):
        candidate = _only(result)
        self.assertEqual(candidate["state"], "REVIEW", candidate)
        self.assertIsNone(candidate["typed_stop"])
        digest = candidate["candidate_digest"]
        self.assertEqual(candidate["pattern_candidate"]["candidate_digest"],
                         digest)
        self.assertEqual(candidate["cutting_pattern"]["candidate_digest"],
                         digest)
        self.assertEqual(candidate["sewing_plan"]["candidate_digest"], digest)
        binding = candidate["artifact_binding"]
        self.assertEqual(binding["candidate_digest"], digest)
        self.assertTrue(binding["same_candidate_digest"])
        self.assertTrue(binding["all_downstream_artifacts_bound"])
        self.assertEqual(binding["compiled_pattern_digest"],
                         binding["cutting_source_pattern_digest"])
        self.assertEqual(binding["compiled_pattern_digest"],
                         binding["sewing_source_pattern_digest"])
        for row in (result, candidate, candidate["cutting_pattern"],
                    candidate["sewing_plan"]):
            self.assertFalse(row["manufacturing_ready"])
            self.assertFalse(row["manufacturing_certified"])
            self.assertFalse(row["corpus_used"])
        self.assertIsNone(result["human_choice"]["selected_candidate_id"])
        self.assertFalse(result["claims"]["candidate_auto_selected"])
        return candidate

    def test_separated_top_and_bottom_keep_independent_closure_order(self):
        result = assemble(_request(_candidate("separates", [
            _body(unit="upper"),
            _skirt(unit="lower"),
        ])))
        candidate = self.assert_bound_review(result)
        plan = candidate["sewing_plan"]
        self.assertEqual(len(candidate["cutting_pattern"]["pieces"]), 2)
        self.assertEqual(len(plan["unresolved_closures"]), 2)
        self.assertEqual({row["kind"] for row in plan["seam_manifest"]},
                         {"PROCEDURAL_CLOSURE"})
        self.assertNotIn("join_pieces",
                         [row["action"] for row in plan["sewing_order"]])

    def test_one_piece_join_precedes_unresolved_closures(self):
        result = assemble(_request(_candidate("one-piece", [
            _body(circumference=76.0),
            _skirt(attached_to="body", attachment_relation="JOIN"),
        ])))
        candidate = self.assert_bound_review(result)
        plan = candidate["sewing_plan"]
        join = next(row for row in plan["sewing_order"]
                    if row["action"] == "join_pieces")
        closures = [row for row in plan["sewing_order"]
                    if row["kind"] == "PROCEDURAL_CLOSURE"]
        self.assertTrue(closures)
        self.assertTrue(all(join["step_id"] in row["prerequisite_step_ids"]
                            for row in closures))
        self.assertTrue(any(row["kind"] == "JOIN"
                            for row in plan["seam_manifest"]))
        self.assertTrue(plan["unresolved_closures"])

    def test_two_legs_and_gusset_have_addressed_topology_without_a_class_enum(self):
        result = assemble(_request(_candidate("trouser-geometry", [
            _body(unit="upper"),
            _part("leg-left", "TUBE",
                  {"length_cm": 99.0, "circumference_cm": 57.0},
                  "left lower leg", unit="lower", side="left"),
            _part("leg-right", "TUBE",
                  {"length_cm": 99.0, "circumference_cm": 57.0},
                  "right lower leg", unit="lower", side="right"),
            _part("crotch-gusset", "GUSSET",
                  # The two joined gusset edges intentionally match each
                  # 57 cm leg opening; a mismatched value is covered by the
                  # candidate-specific STOP regression below.
                  {"length_cm": 57.0, "width_cm": 8.0},
                  "crotch", unit="lower"),
        ])))
        candidate = self.assert_bound_review(result)
        plan = candidate["sewing_plan"]
        piece_ids = {row["piece_id"] for row in plan["piece_manifest"]}
        self.assertTrue({"leg-left", "leg-right", "crotch-gusset"}
                        <= piece_ids)
        gusset_joins = [row for row in plan["seam_manifest"]
                         if "gusset" in str(row["seam_id"])]
        self.assertEqual(len(gusset_joins), 2)
        self.assertTrue(all(row["a"]["piece_id"] in piece_ids
                            and row["b"]["piece_id"] in piece_ids
                            for row in plan["seam_manifest"]))
        self.assertNotIn("TROUSER", json.dumps(result, ensure_ascii=False))

    def test_overlay_is_layered_before_base_closure_and_method_stays_review(self):
        result = assemble(_request(_candidate("layered", [
            _body(part_id="underlayer", layer=0),
            _part("outer-panel", "OVERLAY",
                  {"height_cm": 46.0, "width_cm": 55.0},
                  "front torso overlay", layer=1,
                  attached_to="underlayer"),
        ])))
        candidate = self.assert_bound_review(result)
        plan = candidate["sewing_plan"]
        layer = next(row for row in plan["sewing_order"]
                     if row["kind"] == "LAYER")
        closure = next(row for row in plan["sewing_order"]
                       if row["kind"] == "PROCEDURAL_CLOSURE")
        self.assertIn(layer["step_id"], closure["prerequisite_step_ids"])
        review_codes = {row["verdict"] for row in plan["reviews"]}
        self.assertIn("REVIEW_LAYER_ATTACHMENT_REQUIRED", review_codes)
        self.assertFalse(plan["actual_sewing_method_confirmed"])

    def test_one_candidate_topology_failure_is_a_digest_bound_stop(self):
        source = _candidate("mismatch", [
            _body(circumference=90.0),
            _skirt(circumference=76.0, attached_to="body",
                   attachment_relation="JOIN"),
        ])
        upstream = front_assemble(_request(source))
        result = bind(upstream)
        candidate = _only(result)
        self.assertEqual(candidate["state"], "STOPPED")
        self.assertEqual(candidate["typed_stop"]["stage"],
                         "SEWING_TOPOLOGY")
        self.assertEqual(candidate["reason_code"],
                         "UNKNOWN_GEOMETRIC_SEAM_MISMATCH")
        self.assertEqual(candidate["candidate_digest"],
                         candidate["pattern_candidate"]["candidate_digest"])
        self.assertIsNotNone(candidate["cutting_pattern"])
        self.assertFalse(candidate["manufacturing_ready"])
        self.assertFalse(candidate["corpus_used"])

    def test_stale_structure_candidate_digest_is_rejected_before_cutting(self):
        upstream = front_assemble(_request(_candidate("stale", [
            _body(unit="upper"), _skirt(unit="lower"),
        ])))
        alternative = upstream["source_candidates"][0][
            "structure_alternatives"][0]
        forged = "f" * 64
        alternative["candidate_digest"] = forged
        alternative["structure"]["candidate_digest"] = forged
        alternative["pattern_candidate"]["candidate_digest"] = forged
        result = bind(upstream)
        candidate = _only(result)
        self.assertEqual(candidate["state"], "STOPPED")
        self.assertEqual(candidate["reason_code"],
                         "UNKNOWN_STRUCTURE_CANDIDATE_DIGEST_MISMATCH")
        self.assertEqual(candidate["typed_stop"]["stage"],
                         "CANDIDATE_BINDING")
        self.assertIsNone(candidate["cutting_pattern"])
        self.assertIsNone(candidate["sewing_plan"])
        self.assertFalse(result["claims"]["candidate_specific_cutting_patterns"])
        self.assertFalse(result["claims"]["topology_derived_sewing_order"])

    def test_two_candidates_have_distinct_end_to_end_lineage(self):
        result = assemble(_two_candidate_request())
        self.assertEqual(len(result["candidates"]), 2, result)
        self.assertEqual({row["state"] for row in result["candidates"]},
                         {"REVIEW"})

        compiled_digests = set()
        cutting_digests = set()
        sewing_digests = set()
        for candidate in result["candidates"]:
            binding = candidate["artifact_binding"]
            compiled_digests.add(binding["compiled_pattern_digest"])
            cutting_digests.add(binding["cutting_pattern_digest"])
            sewing_digests.add(binding["sewing_plan_digest"])
            for artifact, producer_digest_key in (
                (candidate["cutting_pattern"],
                 "source_cutting_artifact_digest"),
                (candidate["sewing_plan"],
                 "source_topology_plan_digest"),
            ):
                self.assertEqual(artifact["candidate_id"],
                                 candidate["candidate_id"])
                self.assertEqual(artifact["candidate_digest"],
                                 candidate["candidate_digest"])
                self.assertEqual(artifact["structure_digest"],
                                 candidate["structure_digest"])
                self.assertEqual(artifact["source_pattern_digest"],
                                 binding["compiled_pattern_digest"])
                lineage = artifact["provenance"]["lineage"]
                self.assertEqual(lineage["candidate_id"],
                                 candidate["candidate_id"])
                self.assertEqual(lineage["candidate_digest"],
                                 candidate["candidate_digest"])
                self.assertEqual(lineage["structure_digest"],
                                 candidate["structure_digest"])
                self.assertEqual(lineage["source_pattern_digest"],
                                 binding["compiled_pattern_digest"])
                lineage_payload = dict(lineage)
                lineage_digest = lineage_payload.pop("binding_digest")
                self.assertEqual(lineage_digest,
                                 stable_digest(lineage_payload))
                self.assertEqual(lineage["producer_artifact_digest"],
                                 artifact[producer_digest_key])

        self.assertEqual(len(compiled_digests), 2)
        self.assertEqual(len(cutting_digests), 2)
        self.assertEqual(len(sewing_digests), 2)

    def test_relabelled_compiled_pattern_from_sibling_is_rejected(self):
        upstream = front_assemble(_two_candidate_request())
        alternatives = [source["structure_alternatives"][0]
                        for source in upstream["source_candidates"]]
        first, second = alternatives
        stolen = copy.deepcopy(
            first["pattern_candidate"]["compiler_result"])
        stolen["candidate_id"] = second["candidate_id"]
        stolen["structure_digest"] = second["structure_digest"]
        # Keep the first candidate's compiled digest.  Re-seal only the outer
        # envelopes to prove the compiled geometry seal is independently
        # checked rather than trusted through labels.
        second["pattern_candidate"]["compiler_result"] = stolen
        _reseal(second["pattern_candidate"], "artifact_digest")
        _reseal(second, "artifact_digest")

        result = bind(upstream)
        rows = {row["source_candidate_id"]: row
                for row in result["candidates"]}
        self.assertEqual(rows["narrow"]["state"], "REVIEW")
        self.assertEqual(rows["wide"]["state"], "STOPPED")
        self.assertEqual(rows["wide"]["reason_code"],
                         "UNKNOWN_COMPILED_PATTERN_DIGEST_MISMATCH")
        self.assertEqual(rows["wide"]["typed_stop"]["stage"],
                         "ARTIFACT_BINDING")
        self.assertIsNone(rows["wide"]["cutting_pattern"])
        self.assertIsNone(rows["wide"]["sewing_plan"])

    def test_structure_artifact_from_sibling_is_rejected_before_pattern(self):
        upstream = front_assemble(_two_candidate_request())
        alternatives = [source["structure_alternatives"][0]
                        for source in upstream["source_candidates"]]
        first, second = alternatives
        second["structure"] = copy.deepcopy(first["structure"])
        _reseal(second, "artifact_digest")

        result = bind(upstream)
        rows = {row["source_candidate_id"]: row
                for row in result["candidates"]}
        self.assertEqual(rows["narrow"]["state"], "REVIEW")
        self.assertEqual(rows["wide"]["state"], "STOPPED")
        self.assertEqual(rows["wide"]["reason_code"],
                         "UNKNOWN_STRUCTURE_CANDIDATE_DIGEST_MISMATCH")
        self.assertEqual(rows["wide"]["typed_stop"]["stage"],
                         "CANDIDATE_BINDING")
        self.assertIsNone(rows["wide"]["cutting_pattern"])
        self.assertIsNone(rows["wide"]["sewing_plan"])

    def test_relabelled_cutting_artifact_from_sibling_is_rejected(self):
        real_build = pipeline._cutting.build
        first_result = None

        def cross_candidate_build(compiled, **kwargs):
            nonlocal first_result
            if first_result is None:
                first_result = real_build(compiled, **kwargs)
                return first_result
            stolen = copy.deepcopy(first_result)
            stolen["candidate_id"] = compiled["candidate_id"]
            stolen["structure_digest"] = compiled["structure_digest"]
            stolen["source_digest"] = compiled["digest"]
            stolen["provenance"]["source_digest"] = compiled["digest"]
            # The producer digest deliberately remains the first candidate's.
            return stolen

        with mock.patch.object(pipeline._cutting, "build",
                               side_effect=cross_candidate_build):
            result = assemble(_two_candidate_request())
        rows = {row["source_candidate_id"]: row
                for row in result["candidates"]}
        self.assertEqual(rows["narrow"]["state"], "REVIEW")
        self.assertEqual(rows["wide"]["state"], "STOPPED")
        self.assertEqual(rows["wide"]["reason_code"],
                         "UNKNOWN_CUTTING_ARTIFACT_DIGEST_MISMATCH")
        self.assertIsNone(rows["wide"]["cutting_pattern"])

    def test_relabelled_sewing_plan_from_sibling_is_rejected(self):
        real_plan = pipeline._sewing.plan
        first_result = None

        def cross_candidate_plan(compiled):
            nonlocal first_result
            if first_result is None:
                first_result = real_plan(compiled)
                return first_result
            stolen = copy.deepcopy(first_result)
            stolen["candidate_id"] = compiled["candidate_id"]
            stolen["structure_digest"] = compiled["structure_digest"]
            stolen["source_pattern_digest"] = compiled["digest"]
            stolen["provenance"]["candidate_id"] = compiled["candidate_id"]
            stolen["provenance"]["structure_digest"] = compiled[
                "structure_digest"]
            stolen["provenance"]["source_pattern_digest"] = compiled[
                "digest"]
            # The producer digest deliberately remains the first candidate's.
            return stolen

        with mock.patch.object(pipeline._sewing, "plan",
                               side_effect=cross_candidate_plan):
            result = assemble(_two_candidate_request())
        rows = {row["source_candidate_id"]: row
                for row in result["candidates"]}
        self.assertEqual(rows["narrow"]["state"], "REVIEW")
        self.assertEqual(rows["wide"]["state"], "STOPPED")
        self.assertEqual(rows["wide"]["reason_code"],
                         "UNKNOWN_SEWING_ARTIFACT_DIGEST_MISMATCH")
        self.assertIsNone(rows["wide"]["cutting_pattern"])
        self.assertIsNone(rows["wide"]["sewing_plan"])

    def test_duplicate_candidate_id_fails_closed_for_both_envelopes(self):
        upstream = front_assemble(_request(_candidate("duplicate", [
            _body(unit="upper"), _skirt(unit="lower"),
        ])))
        alternatives = upstream["source_candidates"][0][
            "structure_alternatives"]
        alternatives.append(copy.deepcopy(alternatives[0]))

        result = bind(upstream)
        self.assertEqual(len(result["candidates"]), 2)
        self.assertEqual({row["state"] for row in result["candidates"]},
                         {"STOPPED"})
        self.assertEqual({row["reason_code"] for row in result["candidates"]},
                         {"UNKNOWN_DUPLICATE_CANDIDATE_ID"})
        self.assertFalse(result["claims"][
            "candidate_specific_cutting_patterns"])
        self.assertFalse(result["claims"]["topology_derived_sewing_order"])


if __name__ == "__main__":
    unittest.main()
