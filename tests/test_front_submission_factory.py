#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-front submission regression through the persisted MCP factory.

The fixture proves that a front-only observation can reach inspectable 3-D,
flat-pattern, repair, simulation and procedural sewing artifacts.  It also
fixes the more important negative contract: an invisible back, preview body,
unmeasured material and unresolved engineering gates never become observed or
manufacturing-certified merely because the loop completed its numerical work.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from photoloset import mcp


class FrontSubmissionFactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.mcp_patch = patch.multiple(
            mcp, HOME=root, PROJECTS=root / "projects",
            CURRENT=root / "current_project")
        self.mcp_patch.start()

    def tearDown(self) -> None:
        self.mcp_patch.stop()
        self.temporary.cleanup()

    @staticmethod
    def _factory(action: str, event_or_request: dict) -> dict:
        return json.loads(mcp.TOOLS["garment_factory"](
            json.dumps(event_or_request), action))

    def test_front_only_reaches_artifacts_without_promoting_unknowns(self):
        started = self._factory("start", {
            "job_id": "front-submission-regression", "max_iterations": 8})
        self.assertEqual(started["verdict"], "ANSWER")

        # The transverse line is front evidence only.  It may affect proposed
        # topology, but its meaning and the back are deliberately unobserved.
        outline = {
            "outline": [[40, 0], [60, 0], [90, 100], [10, 100]],
            "internal_lines": [[[15, 48], [85, 48]]],
            "provenance": {"kind": "OBSERVED"},
        }
        confirmed = self._factory("advance", {"event": {
            "type": "CONFIRM_IMAGE", "outline": outline,
            "regions": [{"region_id": "clothing", "part_id": "garment",
                         "state": "OBSERVED"}],
            "front_only": True, "evidence_state": "OBSERVED",
        }})
        self.assertEqual(confirmed["state"]["phase"], "REGIONS_CONFIRMED")

        retrieved = self._factory("advance", {"event": {
            "type": "HYBRID_RETRIEVE",
            "request": {"request": "この正面画像から服を作って"},
        }})
        self.assertEqual(retrieved["verdict"], "PROPOSED")
        self.assertEqual(retrieved["state"]["phase"], "BACK_CANDIDATES_READY")
        candidates = retrieved["state"]["hypothesis_sheet"]["candidates"]
        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(len({row["back_design"] for row in candidates}),
                         len(candidates))
        self.assertTrue(all(row["state"] == "PROPOSED" for row in candidates))

        selected = candidates[-1]
        approved = self._factory("advance", {"event": {
            "type": "APPROVE_HYPOTHESIS",
            "candidate_id": selected["candidate_id"],
            "digest": selected["digest"], "by": "Submission Reviewer",
        }})
        self.assertEqual(approved["verdict"], "APPROVED")

        generated = self._factory("advance", {"event": {
            "type": "GENERATE_PATTERN", "preview_mannequin": True,
        }})
        pattern = generated["state"]["pattern"]
        self.assertEqual(generated["verdict"], "ANSWER")
        self.assertEqual(pattern["candidate_id"], selected["candidate_id"])
        self.assertEqual(pattern["candidate_preview"]["candidate_id"],
                         selected["candidate_id"])
        self.assertTrue(pattern["pieces"])
        self.assertTrue(pattern["garment_surface"]["verts"])
        self.assertFalse(pattern["manufacturing_preview"]["manufacturing_ready"])
        self.assertTrue(pattern["export_verification"]["verified"])
        self.assertFalse(pattern["export_verification"]
                         ["manufacturing_certified"])
        self.assertTrue(pattern["preview_mannequin"]
                        ["must_be_replaced_before_manufacturing"])

        repaired = self._factory("advance", {"event": {
            "type": "REPAIR_PATTERN", "budget": 8,
        }})
        self.assertEqual(repaired["verdict"], "ANSWER")
        self.assertTrue(repaired["state"]["repair"]["sewable"])

        materials = [
            {"candidate_id": "jersey-preview", "xpbd": {
                "areal_density_kg_m2": 0.20,
                "warp_stiffness_n_m": 420.0,
                "weft_stiffness_n_m": 360.0,
                "shear_stiffness_n_m": 65.0,
                "bending_stiffness_n_m": 0.01,
                "damping_ratio": 0.045,
            }},
            {"candidate_id": "woven-preview", "xpbd": {
                "areal_density_kg_m2": 0.30,
                "warp_stiffness_n_m": 900.0,
                "weft_stiffness_n_m": 700.0,
                "shear_stiffness_n_m": 120.0,
                "bending_stiffness_n_m": 0.04,
                "damping_ratio": 0.06,
            }},
        ]
        proposed_materials = self._factory("advance", {"event": {
            "type": "SUBMIT_MATERIAL_CANDIDATES",
            "candidates": materials,
        }})
        material = proposed_materials["state"]["material_sheet"]["candidates"][0]
        material_approved = self._factory("advance", {"event": {
            "type": "APPROVE_MATERIAL",
            "candidate_id": material["candidate_id"],
            "digest": material["digest"], "by": "Submission Reviewer",
        }})
        self.assertEqual(material_approved["verdict"], "APPROVED")

        surface = material_approved["state"]["pattern"]["garment_surface"]
        rest_positions = [[coordinate / 100.0 for coordinate in point]
                          for point in surface["verts"]]
        triangles = []
        for face in surface["faces"]:
            triangles.extend(
                [face[0], face[index], face[index + 1]]
                for index in range(1, len(face) - 1))
        material_profile = materials[0]["xpbd"]
        simulation = self._factory("advance", {"event": {
            "type": "SIMULATE", "input": {
                "schema": "garment.industrial-cloth-step.v1",
                "rest_positions": rest_positions,
                "faces": triangles,
                "face_material_ids": ["jersey-preview"] * len(triangles),
                "materials": {"xpbd": {
                    "jersey-preview": material_profile}},
                "time_step_s": 1.0 / 60.0,
                "fixed_vertices": [0, 1],
                "xpbd": {"steps": 2, "solver_iterations": 4},
            },
        }})
        self.assertEqual(simulation["verdict"], "ANSWER")
        self.assertEqual(simulation["state"]["phase"], "SIMULATION_READY")

        sewing = self._factory("advance", {"event": {
            "type": "USE_PROCEDURAL_SEWING_PLAN",
        }})
        self.assertEqual(sewing["verdict"], "PROPOSED")
        self.assertEqual(sewing["state"]["sewing"]["route"],
                         "PROCEDURAL_TOPOLOGY")
        self.assertFalse(sewing["state"]["sewing"]["corpus_used"])
        self.assertEqual(sewing["state"]["sewing"]["corpus_gap"],
                         "UNKNOWN_NO_SEWING_CORPUS")

        iteration = self._factory("advance", {"event": {"type": "ITERATE"}})
        self.assertEqual(iteration["verdict"], "CONTINUE")
        self.assertEqual(iteration["state"]["phase"], "ITERATING")
        self.assertTrue(all(str(item).startswith("engineering gate:")
                            for item in iteration["missing"]))
        self.assertIn("engineering gate: wearer_comfort", iteration["missing"])


if __name__ == "__main__":
    unittest.main()
