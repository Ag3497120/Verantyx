#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Front-image contract matrix across structurally different garments.

The generated PNGs are source-identity fixtures.  Pixel interpretation is an
upstream responsibility; this matrix starts at the typed vision boundary and
checks that the deterministic contract cannot lose a declared front element
while carrying each proposal through candidate-specific 3-D, pattern, and
manufacturing-review artifacts.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import unittest

from photoloset.front_image_generation_contract import (
    REQUEST_SCHEMA,
    REQUIRED_WEARER_MEASUREMENTS,
    orchestrate,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "generated"


GARMENT_MATRIX = (
    {
        "name": "fantasy_one_piece_with_ornaments",
        "fixture": "anime-garment-emerald.png",
        "observed": ("body-shell", "sleeve-pair", "flared-lower"),
        "proposed": ("bow", "ribbon", "rosette"),
    },
    {
        "name": "separated_top_and_bottom",
        "fixture": "anime-garment-emerald-retest.png",
        "observed": ("upper-shell", "lower-skirt", "waist-separation"),
        "proposed": ("waist-opening",),
    },
    {
        "name": "layered_overlay",
        "fixture": "anime-garment-cape.png",
        "observed": ("body-shell", "outer-silhouette"),
        "proposed": ("underlayer", "overlay", "overlay-attachment"),
    },
    {
        "name": "skirt_silhouette",
        "fixture": "long-haired-emerald-dress.png",
        "observed": ("body-shell", "skirt-flare", "hem"),
        "proposed": ("waist-seam",),
    },
    {
        "name": "trouser_silhouette",
        "fixture": "anime-garment-emerald-retest.png",
        "observed": ("upper-shell", "split-lower", "leg-pair"),
        "proposed": ("crotch-gusset", "waist-opening"),
    },
    {
        "name": "asymmetry_and_cutout",
        "fixture": "anime-garment-cape.png",
        "observed": ("body-shell", "asymmetric-outline"),
        "proposed": ("nested-cutout", "cutout-facing"),
    },
)


def _measurements() -> dict:
    values = (88.0, 72.0, 96.0, 43.0)
    return {
        name: {
            "value_cm": values[index],
            "authority": "USER_PROVIDED",
            "source": "named matrix wearer",
        }
        for index, name in enumerate(REQUIRED_WEARER_MEASUREMENTS)
    }


def _claims(case: dict) -> dict:
    observations = []
    proposals = []
    for authority, elements, destination in (
        ("OBSERVED", case["observed"], observations),
        ("PROPOSED", case["proposed"], proposals),
    ):
        for element_id in elements:
            destination.append({
                "claim_id": f"{authority.lower()}:{element_id}",
                "field": f"front.structure.{element_id}",
                "value": {"present": True},
                "authority": authority,
                "basis": (
                    "visible front evidence"
                    if authority == "OBSERVED"
                    else "front-only structural interpretation requiring review"
                ),
                "structural_element_id": element_id,
            })
    return {"observations": observations, "proposals": proposals}


def _candidate(case: dict, candidate_id: str, rear: str, material: str) -> dict:
    observed = set(case["observed"])
    all_elements = sorted(observed | set(case["proposed"]))
    return {
        "candidate_id": candidate_id,
        "state": "PROPOSED",
        "structure": {
            "nodes": [
                {
                    "node_id": element_id,
                    "authority": (
                        "OBSERVED" if element_id in observed else "PROPOSED"
                    ),
                }
                for element_id in all_elements
            ],
            "operations": [],
            "preserved_element_ids": all_elements,
        },
        "rear_hypothesis": {
            "state": "PROPOSED",
            "value": rear,
            "basis": "the rear is absent and this is one falsifiable alternative",
        },
        "material_hypothesis": {
            "state": "PROPOSED",
            "value": material,
            "basis": "appearance only bounds a material alternative; test a swatch",
        },
        "manufacturing_certified": False,
    }


def _artifact(candidate_id: str, kind: str, element_ids: list[str]) -> dict:
    coverage_key = {
        "preview_3d": "rendered_element_ids",
        "pattern": "piece_element_ids",
        "manufacturing": "reviewed_element_ids",
    }[kind]
    row = {
        "candidate_id": candidate_id,
        "kind": kind,
        "state": "REVIEW" if kind == "manufacturing" else "PROPOSED",
        "payload": {coverage_key: element_ids},
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }
    if kind == "manufacturing":
        row["blocking_issues"] = []
    return row


def _request(case: dict, *, measurements: bool = True) -> dict:
    fixture = FIXTURE_ROOT / case["fixture"]
    image_digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    candidates = [
        _candidate(case, f"{case['name']}:back-opening",
                   "center_back_opening", "woven_candidate"),
        _candidate(case, f"{case['name']}:closed-back",
                   "closed_back_side_opening", "knit_candidate"),
    ]
    element_ids = sorted(set(case["observed"]) | set(case["proposed"]))
    artifacts = {
        candidate["candidate_id"]: {
            kind: _artifact(candidate["candidate_id"], kind, element_ids)
            for kind in ("preview_3d", "pattern", "manufacturing")
        }
        for candidate in candidates
    }
    return {
        "schema": REQUEST_SCHEMA,
        "source": {
            "image_id": f"sha256:{image_digest}",
            "fixture": str(fixture),
            "view": "front",
        },
        "vision": _claims(case),
        "wearer_measurements": _measurements() if measurements else {},
        "candidates": candidates,
        "artifacts": artifacts,
        "approvals": {},
        "rounds": [],
        "max_rounds": 8,
    }


def _approve(request: dict, gate: str, candidate_id: str,
             target_digest: str) -> dict:
    updated = copy.deepcopy(request)
    updated["approvals"][gate] = {
        "decision": "APPROVE",
        "actor_type": "HUMAN",
        "by": "front matrix reviewer",
        "candidate_id": candidate_id,
        "target_digest": target_digest,
    }
    return updated


class FrontImageE2EMatrixTests(unittest.TestCase):
    maxDiff = None

    def test_structural_matrix_preserves_lineage_and_truth_boundaries(self):
        for case in GARMENT_MATRIX:
            with self.subTest(garment=case["name"]):
                fixture = FIXTURE_ROOT / case["fixture"]
                self.assertTrue(fixture.is_file())

                missing_measurements = orchestrate(
                    _request(case, measurements=False))
                self.assertEqual(
                    missing_measurements["reason_code"],
                    "STOP_WEARER_MEASUREMENTS_REQUIRED",
                )
                self.assertFalse(missing_measurements["manufacturing_ready"])
                self.assertFalse(
                    missing_measurements["manufacturing_certified"])

                request = _request(case)
                candidate_gate = orchestrate(request)
                self.assertEqual(
                    candidate_gate["reason_code"],
                    "STOP_HUMAN_CANDIDATE_APPROVAL_REQUIRED",
                )
                expected_elements = (
                    set(case["observed"]) | set(case["proposed"])
                )
                candidate_digests = {
                    row["candidate_id"]: row["candidate_digest"]
                    for row in candidate_gate["candidates"]
                }
                self.assertEqual(len(candidate_digests), 2)

                for candidate in candidate_gate["candidates"]:
                    self.assertEqual(candidate["state"], "PROPOSED")
                    self.assertEqual(
                        set(candidate["structure"]["preserved_element_ids"]),
                        expected_elements,
                    )
                    self.assertEqual(
                        candidate["rear_hypothesis"]["state"], "PROPOSED")
                    self.assertEqual(
                        candidate["material_hypothesis"]["state"], "PROPOSED")
                    bundle = candidate_gate["artifacts"][
                        candidate["candidate_id"]]
                    self.assertEqual(set(bundle), {
                        "preview_3d", "pattern", "manufacturing"})
                    self.assertEqual(
                        len({row["binding_digest"]
                             for row in bundle.values()}), 3)
                    for artifact in bundle.values():
                        self.assertEqual(
                            artifact["candidate_id"], candidate["candidate_id"])
                        self.assertEqual(
                            artifact["candidate_digest"],
                            candidate["candidate_digest"],
                        )
                        self.assertFalse(artifact["manufacturing_ready"])
                        self.assertFalse(artifact["manufacturing_certified"])

                selected_id = sorted(candidate_digests)[0]
                request = _approve(
                    request, "candidate", selected_id,
                    candidate_gate["approval_targets"][selected_id])
                pattern_gate = orchestrate(request)
                self.assertEqual(
                    pattern_gate["reason_code"],
                    "STOP_HUMAN_PATTERN_APPROVAL_REQUIRED",
                )
                request = _approve(
                    request, "pattern", selected_id,
                    pattern_gate["approval_target_digest"])
                manufacturing_gate = orchestrate(request)
                self.assertEqual(
                    manufacturing_gate["reason_code"],
                    "STOP_HUMAN_MANUFACTURING_REVIEW_REQUIRED",
                )
                request = _approve(
                    request, "manufacturing_review", selected_id,
                    manufacturing_gate["approval_target_digest"])
                final = orchestrate(request)
                self.assertEqual(
                    final["reason_code"],
                    "STOP_READY_FOR_PHYSICAL_PROTOTYPE_REVIEW",
                )
                self.assertFalse(final["manufacturing_ready"])
                self.assertFalse(final["manufacturing_certified"])
                self.assertEqual(final["rear_authority"], "PROPOSED")
                self.assertEqual(final["material_authority"], "PROPOSED")

    def test_contract_rejects_a_candidate_that_drops_a_typed_front_element(self):
        case = GARMENT_MATRIX[0]
        request = _request(case)
        request["candidates"][1]["structure"][
            "preserved_element_ids"].remove("rosette")

        result = orchestrate(request)

        self.assertEqual(result["decision"], "STOP")
        self.assertEqual(
            result["reason_code"],
            "UNKNOWN_CANDIDATE_STRUCTURE_ELEMENT_DROPPED",
        )
        self.assertEqual(result["missing_element_ids"], ["rosette"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])

    def test_artifact_cannot_reuse_an_identity_from_another_candidate_revision(self):
        case = GARMENT_MATRIX[2]
        request = _request(case)
        candidate_id = request["candidates"][0]["candidate_id"]
        request["artifacts"][candidate_id]["pattern"][
            "candidate_digest"] = "sha256:stale-candidate-revision"

        result = orchestrate(request)

        self.assertEqual(result["decision"], "STOP")
        self.assertEqual(
            result["reason_code"],
            "UNKNOWN_ARTIFACT_CANDIDATE_DIGEST_MISMATCH",
        )
        self.assertEqual(result["candidate_id"], candidate_id)
        self.assertEqual(result["kind"], "pattern")
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])


if __name__ == "__main__":
    unittest.main()
