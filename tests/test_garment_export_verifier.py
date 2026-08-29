#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import base64
import copy
import json
import unittest

from photoloset import garment_export_package as export
from photoloset import garment_export_verifier as verifier
from photoloset import mcp as mcp_server
from tests.test_garment_export_package import engineering, manufacturing, sewing


def built():
    return export.build(manufacturing(), engineering(), sewing())


def transported(package):
    value = copy.deepcopy(package)
    value["files"] = {
        name: ({"representation": "base64",
                "data": base64.b64encode(content).decode("ascii"),
                "bytes": len(content)}
               if isinstance(content, bytes) else
               {"representation": "text", "text": content,
                "bytes": len(content.encode("utf-8"))})
        for name, content in value["files"].items()
    }
    return value


class GarmentExportVerifierTests(unittest.TestCase):
    def test_verifies_raw_and_mcp_transport_without_certifying_manufacture(self):
        raw = verifier.verify(built())
        transported_result = verifier.verify(transported(built()))
        self.assertEqual(raw["verdict"], "ANSWER")
        self.assertEqual(raw, transported_result)
        self.assertTrue(raw["verified"])
        self.assertFalse(raw["manufacturing_ready"])
        self.assertFalse(raw["manufacturing_certified"])
        self.assertEqual(raw["file_count"], 6)

    def test_public_mcp_verifier_checks_the_json_safe_package(self):
        result = json.loads(mcp_server.TOOLS["garment_verify_export_package"](
            json.dumps(transported(built()), ensure_ascii=False)))
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertTrue(result["verified"])
        self.assertFalse(result["manufacturing_certified"])

    def test_changed_svg_or_dxf_is_refused_by_filename(self):
        svg = built()
        svg["files"]["pattern.svg"] += "<!-- replaced -->"
        result = verifier.verify(svg)
        self.assertEqual(result["verdict"], "UNKNOWN_EXPORT_FILE_DIGEST")
        self.assertEqual(result["filename"], "pattern.svg")

        dxf = transported(built())
        dxf["files"]["pattern.dxf"]["data"] = base64.b64encode(
            b"0\nEOF\n").decode("ascii")
        dxf["files"]["pattern.dxf"]["bytes"] = len(b"0\nEOF\n")
        result = verifier.verify(dxf)
        self.assertEqual(result["verdict"], "UNKNOWN_EXPORT_FILE_DIGEST")
        self.assertEqual(result["filename"], "pattern.dxf")

    def test_bad_base64_and_transport_length_are_typed_refusals(self):
        bad = transported(built())
        bad["files"]["pattern.dxf"]["data"] = "%%%not-base64%%%"
        self.assertEqual(verifier.verify(bad)["verdict"],
                         "UNKNOWN_EXPORT_BASE64")
        short = transported(built())
        short["files"]["pattern.svg"]["bytes"] -= 1
        self.assertEqual(verifier.verify(short)["verdict"],
                         "UNKNOWN_EXPORT_TRANSPORT_LENGTH")

    def test_manifest_lineage_and_digest_cannot_be_rewritten(self):
        value = built()
        manifest = json.loads(value["files"]["manifest.json"])
        manifest["lineage"]["candidate_id"] = "different"
        value["files"]["manifest.json"] = json.dumps(manifest)
        result = verifier.verify(value)
        self.assertEqual(result["verdict"], "UNKNOWN_EXPORT_PACKAGE_LINEAGE")

        value = built()
        manifest = json.loads(value["files"]["manifest.json"])
        manifest["remaining_gates"].append("silently changed")
        value["files"]["manifest.json"] = json.dumps(manifest)
        result = verifier.verify(value)
        self.assertEqual(result["verdict"], "UNKNOWN_EXPORT_MANIFEST_DIGEST")

    def test_missing_extra_and_traversal_files_are_refused(self):
        missing = built()
        del missing["files"]["pattern.svg"]
        self.assertEqual(verifier.verify(missing)["verdict"],
                         "UNKNOWN_EXPORT_FILE_SET")
        extra = built()
        extra["files"]["extra.txt"] = "x"
        self.assertEqual(verifier.verify(extra)["verdict"],
                         "UNKNOWN_EXPORT_FILE_SET")
        traversal = built()
        traversal["files"]["../pattern.svg"] = traversal["files"].pop(
            "pattern.svg")
        self.assertEqual(verifier.verify(traversal)["verdict"],
                         "UNKNOWN_EXPORT_PATH_TRAVERSAL")

    def test_wrapper_digest_and_metadata_must_match_decoded_payloads(self):
        value = built()
        value["digest"] = "forged"
        self.assertEqual(verifier.verify(value)["verdict"],
                         "UNKNOWN_EXPORT_PACKAGE_DIGEST")
        value = built()
        value["file_metadata"]["pattern.svg"]["bytes"] += 1
        self.assertEqual(verifier.verify(value)["verdict"],
                         "UNKNOWN_EXPORT_WRAPPER_METADATA")
        value = built()
        value["manufacturing_ready"] = True
        self.assertEqual(verifier.verify(value)["verdict"],
                         "UNKNOWN_EXPORT_WRAPPER_STATE")

    def test_filename_overrides_do_not_bypass_embedded_lineage_checks(self):
        value = export.build(
            manufacturing(), engineering(), sewing(), filenames={
                "pattern_svg": "drawing.payload",
                "pattern_dxf": "machine.payload",
                "sewing_plan": "steps.payload",
                "engineering_review": "review.payload",
            })
        self.assertEqual(verifier.verify(value)["verdict"], "ANSWER")
        # Re-hash every outer table as an attacker might, while leaving the
        # embedded DXF candidate metadata inconsistent. The inner check must
        # still reject it rather than trusting only wrapper hashes.
        raw = value["files"]["machine.payload"].replace(
            b"structure_digest=structure-digest-a",
            b"structure_digest=structure-digest-b")
        value["files"]["machine.payload"] = raw
        manifest = json.loads(value["files"]["manifest.json"])
        import hashlib
        manifest["files"]["machine.payload"]["sha256"] = hashlib.sha256(raw).hexdigest()
        manifest["digest"] = verifier._digest({
            key: row for key, row in manifest.items() if key != "digest"})
        value["files"]["manifest.json"] = json.dumps(
            manifest, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
        value["file_metadata"] = {
            name: {"sha256": hashlib.sha256(
                content if isinstance(content, bytes) else content.encode("utf-8")).hexdigest(),
                   "bytes": len(content if isinstance(content, bytes)
                                else content.encode("utf-8")),
                   "representation": "bytes" if isinstance(content, bytes) else "text"}
            for name, content in sorted(value["files"].items())
        }
        value["digest"] = verifier._digest({
            "schema": "garment.export-package.v1",
            "lineage": value["lineage"],
            "files": value["file_metadata"],
        })
        result = verifier.verify(value)
        self.assertEqual(result["verdict"], "UNKNOWN_EXPORT_ARTIFACT_LINEAGE")
        self.assertEqual(result["filename"], "machine.payload")


if __name__ == "__main__":
    unittest.main()
