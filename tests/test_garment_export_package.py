#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import hashlib
import json
import os
import tempfile
import unittest

from photoloset import garment_export_package as export
from photoloset import mcp


def manufacturing():
    return {
        "verdict": "ANSWER",
        "schema": "garment.manufacturing-preview-bundle.v1",
        "candidate_id": "candidate-anime-一",
        "candidate_state": "PROPOSED",
        "structure_digest": "structure-digest-a",
        "source_digest": "pattern-digest-a",
        "digest": "manufacturing-digest-a",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>',
        "dxf_compatible": True,
        "dxf_export": {
            "verdict": "ANSWER",
            "text": "999\n型紙\n0\nEOF\n",
            "encoding": "cp932",
            "dxf_version": "AC1009 (R12)",
        },
        "manufacturing_preview_ready": True,
        "manufacturing_ready": False,
        "remaining_gates": ["approve proposed seam allowance"],
        "seam_allowance_cm": {
            "body": {"state": "PROPOSED", "value_cm": 1.0}},
    }


def sewing():
    return {
        "schema": "garment.structure-sewing-plan.v1",
        "verdict": "REVIEW_MANUFACTURING_CHOICES_REQUIRED",
        "order_verdict": "ANSWER",
        "candidate_id": "candidate-anime-一",
        "candidate_state": "PROPOSED",
        "structure_digest": "structure-digest-a",
        "source_pattern_digest": "pattern-digest-a",
        "approval": None,
        "steps": [{"step_id": "seam:body", "action": "close_intrinsic_wrap"}],
        "reviews": [{
            "verdict": "REVIEW_CLOSURE_DETAIL_REQUIRED",
            "scope": "body",
            "why": "closure was not observed",
        }],
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "digest": "sewing-digest-a",
        "provenance": {"approval_digest": None},
    }


def engineering():
    return {
        "schema": "garment.engineering-review.v1",
        "verdict": "REVIEW_ENGINEERING_GATES_REQUIRED",
        "candidate_id": "candidate-anime-一",
        "pattern_digest": "pattern-digest-a",
        "structure_digest": "structure-digest-a",
        "gates": [{
            "gate": "material_and_strength",
            "verdict": "REVIEW_STRENGTH_CALIBRATION_REQUIRED",
            "why": "measured material limits are missing",
        }],
        "actionable_gates": ["material_and_strength"],
        "manufacturing_ready": False,
        "industrial_or_medical_certification": False,
        "digest": "engineering-digest-a",
    }


class GarmentExportPackageTests(unittest.TestCase):
    def test_builds_exact_in_memory_file_map_and_preserves_dxf_encoding(self):
        result = export.build(manufacturing(), engineering(), sewing())
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(set(result["files"]), {
            "pattern.svg", "pattern.dxf", "manifest.json",
            "sewing-plan.json", "engineering-review.json", "README",
        })
        self.assertIsInstance(result["files"]["pattern.svg"], str)
        self.assertIsInstance(result["files"]["pattern.dxf"], bytes)
        decoded_dxf = result["files"]["pattern.dxf"].decode("cp932")
        self.assertIn("型紙", decoded_dxf)
        self.assertIn("candidate_digest=", decoded_dxf)
        self.assertIn("structure_digest=structure-digest-a", decoded_dxf)
        self.assertIn("source_digest=pattern-digest-a", decoded_dxf)
        self.assertFalse(result["filesystem_writes_performed"])

    def test_every_artifact_is_bound_to_the_same_candidate_lineage(self):
        result = export.build(manufacturing(), engineering(), sewing())
        lineage = result["lineage"]
        self.assertEqual(lineage["candidate_digest_kind"],
                         "EXPORT_BINDING_NOT_APPROVAL")
        for filename in ("pattern.svg", "sewing-plan.json",
                         "engineering-review.json", "manifest.json", "README"):
            content = result["files"][filename]
            self.assertIn(lineage["candidate_digest"], content)
            self.assertIn("structure-digest-a", content)
            self.assertIn("pattern-digest-a", content)
        dxf = result["files"]["pattern.dxf"].decode("cp932")
        self.assertIn(lineage["candidate_digest"], dxf)
        manifest = json.loads(result["files"]["manifest.json"])
        self.assertEqual(manifest["lineage"], lineage)

    def test_manifest_hashes_match_the_non_manifest_payloads(self):
        result = export.build(manufacturing(), engineering(), sewing())
        manifest = json.loads(result["files"]["manifest.json"])
        for filename, record in manifest["files"].items():
            content = result["files"][filename]
            raw = content if isinstance(content, bytes) else content.encode("utf-8")
            self.assertEqual(record["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(record["bytes"], len(raw))

    def test_proposed_and_unfinished_gates_are_prominent_and_never_promoted(self):
        result = export.build(manufacturing(), engineering(), sewing())
        self.assertFalse(result["manufacturing_ready"])
        self.assertTrue(result["contains_proposed_or_inferred"])
        manifest = json.loads(result["files"]["manifest.json"])
        readme = result["files"]["README"]
        self.assertFalse(manifest["manufacturing_ready"])
        self.assertTrue(manifest["contains_proposed_or_inferred"])
        self.assertIn("approve proposed seam allowance",
                      "\n".join(manifest["remaining_gates"]))
        self.assertIn("REVIEW_STRENGTH_CALIBRATION_REQUIRED", readme)
        self.assertIn("NOT RELEASED FOR MANUFACTURING", readme)
        self.assertFalse(manifest["claims"]["manufacturing_readiness_synthesized"])

    def test_existing_approval_digest_is_preserved_not_replaced(self):
        plan = sewing()
        plan["approval"] = {"digest": "approved-candidate-digest", "by": "Reviewer"}
        plan["provenance"]["approval_digest"] = "approved-candidate-digest"
        result = export.build(manufacturing(), engineering(), plan)
        self.assertEqual(result["lineage"]["candidate_digest"],
                         "approved-candidate-digest")
        self.assertEqual(result["lineage"]["candidate_digest_kind"],
                         "SOURCE_CANDIDATE_OR_APPROVAL_DIGEST")

    def test_lineage_mismatch_and_dxf_refusal_fail_closed(self):
        bad_review = engineering()
        bad_review["pattern_digest"] = "different-pattern"
        mismatch = export.build(manufacturing(), bad_review, sewing())
        self.assertEqual(mismatch["verdict"],
                         "UNKNOWN_EXPORT_LINEAGE_MISMATCH")
        self.assertEqual(mismatch["files"], {})

        refused_bundle = manufacturing()
        refused_bundle["dxf_export"] = {
            "verdict": "UNKNOWN_NAME_NOT_ENCODABLE", "typed_refusal": True}
        refused = export.build(refused_bundle, engineering(), sewing())
        self.assertEqual(refused["verdict"],
                         "UNKNOWN_DXF_EXPORT_NOT_AVAILABLE")
        self.assertEqual(refused["files"], {})

    def test_path_traversal_absolute_paths_and_collisions_are_refused(self):
        for unsafe in ("../pattern.svg", "/tmp/pattern.svg",
                       "subdir/pattern.svg", "subdir\\pattern.svg", ".."):
            result = export.build(
                manufacturing(), engineering(), sewing(),
                filenames={"pattern_svg": unsafe})
            self.assertEqual(result["verdict"],
                             "UNKNOWN_EXPORT_PATH_TRAVERSAL")
            self.assertEqual(result["files"], {})
        collision = export.build(
            manufacturing(), engineering(), sewing(),
            filenames={"pattern_svg": "pattern.dxf"})
        self.assertEqual(collision["verdict"],
                         "UNKNOWN_EXPORT_FILENAME_COLLISION")

    def test_function_is_deterministic_and_performs_no_implicit_write(self):
        with tempfile.TemporaryDirectory() as directory:
            before = sorted(os.listdir(directory))
            previous = os.getcwd()
            try:
                os.chdir(directory)
                first = export.build(
                    copy.deepcopy(manufacturing()),
                    copy.deepcopy(engineering()), copy.deepcopy(sewing()))
                second = export.build(
                    copy.deepcopy(manufacturing()),
                    copy.deepcopy(engineering()), copy.deepcopy(sewing()))
            finally:
                os.chdir(previous)
            self.assertEqual(before, sorted(os.listdir(directory)))
        self.assertEqual(first, second)
        self.assertEqual(first["digest"], second["digest"])

    def test_even_unanimous_true_flags_are_not_called_a_certificate(self):
        bundle = manufacturing()
        bundle["manufacturing_ready"] = True
        review = engineering()
        review["manufacturing_ready"] = True
        plan = sewing()
        plan["manufacturing_ready"] = True
        result = export.build(bundle, review, plan)
        self.assertTrue(result["manufacturing_ready"])
        manifest = json.loads(result["files"]["manifest.json"])
        self.assertFalse(manifest["claims"]["industrial_certification"])
        self.assertIn("not an industrial", result["files"]["README"])

    def test_mcp_transport_keeps_text_readable_and_binary_exact(self):
        result = json.loads(mcp.TOOLS["garment_export_package"](json.dumps({
            "manufacturing_bundle": manufacturing(),
            "engineering_review": engineering(),
            "sewing_plan": sewing(),
        })))
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["files"]["pattern.svg"]["representation"],
                         "text")
        self.assertEqual(result["files"]["pattern.dxf"]["representation"],
                         "base64")
        decoded = __import__("base64").b64decode(
            result["files"]["pattern.dxf"]["data"])
        self.assertEqual(decoded,
                         export.build(manufacturing(), engineering(), sewing())
                         ["files"]["pattern.dxf"])


if __name__ == "__main__":
    unittest.main()
