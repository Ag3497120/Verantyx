#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import hashlib
import json
import math
import unittest

from photoloset import garment_export_package
from photoloset import garment_export_verifier
from photoloset import pattern_manufacturing_bundle
from photoloset import structure_sewing_plan
from photoloset import structure_to_pattern


def structure(*operations):
    return {
        "schema": "garment.structure.v1",
        "nodes": [{
            "node_id": "front-panel",
            "kind": "BAND",
            "dimensions": {"length_cm": 10.0, "width_cm": 8.0},
            "ports": [{
                "port_id": "face",
                "length_cm": 8.0,
                "interface": "side",
                "role": "edge",
            }],
        }],
        "operations": list(operations),
    }


def cut(operation_id, contour_id, points, clearance=0.5,
        source_front_boundary_digest=None):
    return {
        "operation_id": operation_id,
        "kind": "CUTOUT",
        "source": {"node_id": "front-panel", "port_id": "face"},
        "parameters": {
            "contour_id": contour_id,
            "closed_polygon": points,
            "minimum_clearance_cm": clearance,
            **({"source_front_boundary_digest": source_front_boundary_digest}
               if source_front_boundary_digest is not None else {}),
        },
    }


def engineering(compiled):
    return {
        "schema": "garment.engineering-review.v1",
        "verdict": "REVIEW_ENGINEERING_GATES_REQUIRED",
        "candidate_id": compiled["candidate_id"],
        "pattern_digest": compiled["digest"],
        "structure_digest": compiled["structure_digest"],
        "gates": [{"gate": "cutout_finish", "verdict": "REVIEW",
                   "why": "edge finish and reinforcement are not validated"}],
        "actionable_gates": ["cutout_finish"],
        "manufacturing_ready": False,
        "digest": "engineering-cutout-review",
    }


def pipeline(*operations, approved=False):
    approval = ({"by": "human-pattern-reviewer",
                 "digest": "sha256:approved-candidate"}
                if approved else None)
    compiled = structure_to_pattern.compile(
        structure(*operations), candidate_id="candidate-cutout",
        candidate_state="APPROVED" if approved else "PROPOSED",
        approval=approval)
    if compiled.get("verdict") != "ANSWER":
        return compiled, None, None
    manufacturing = pattern_manufacturing_bundle.build(
        compiled, seam_allowance_cm=1.0)
    sewing = structure_sewing_plan.plan(compiled)
    package = garment_export_package.build(
        manufacturing, engineering(compiled), sewing)
    return compiled, manufacturing, package


def rehash_package(package):
    manifest = json.loads(package["files"]["manifest.json"])
    for name, record in manifest["files"].items():
        content = package["files"][name]
        raw = content if isinstance(content, bytes) else content.encode("utf-8")
        record["sha256"] = hashlib.sha256(raw).hexdigest()
        record["bytes"] = len(raw)
    manifest["digest"] = garment_export_verifier._digest({
        key: value for key, value in manifest.items() if key != "digest"})
    package["files"]["manifest.json"] = json.dumps(
        manifest, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    package["file_metadata"] = {
        name: {
            "sha256": hashlib.sha256(
                content if isinstance(content, bytes)
                else content.encode("utf-8")).hexdigest(),
            "bytes": len(content if isinstance(content, bytes)
                         else content.encode("utf-8")),
            "representation": "bytes" if isinstance(content, bytes) else "text",
        }
        for name, content in sorted(package["files"].items())
    }
    package["digest"] = garment_export_verifier._digest({
        "schema": "garment.export-package.v1",
        "lineage": package["lineage"],
        "files": package["file_metadata"],
    })


class CutoutNestedContourPipelineTests(unittest.TestCase):
    def test_structure_to_svg_dxf_manifest_and_verifier_preserve_inner_cut(self):
        compiled, manufacturing, package = pipeline(cut(
            "neck-window", "window-a",
            [[-2.0, 2.0], [2.0, 2.0], [2.0, 4.0], [-2.0, 4.0]],
            source_front_boundary_digest="front-boundary-digest-a"))
        self.assertEqual(compiled["verdict"], "ANSWER")
        contour = compiled["pieces"][0]["inner_cutouts"][0]
        self.assertEqual(contour["state"], "PROPOSED")
        self.assertLess(sum(contour["points"][i][0]
                            * contour["points"][(i + 1) % 4][1]
                            - contour["points"][(i + 1) % 4][0]
                            * contour["points"][i][1]
                            for i in range(4)), 0.0)
        self.assertFalse(compiled["manufacturing_ready"])
        self.assertEqual(contour["source_front_boundary_digest"],
                         "front-boundary-digest-a")
        self.assertEqual(contour["source_front_boundary_digest_state"],
                         "PROPOSED_LINEAGE_ONLY")
        self.assertFalse(contour["source_front_boundary_semantics_observed"])

        self.assertEqual(manufacturing["verdict"], "ANSWER")
        self.assertFalse(manufacturing["manufacturing_ready"])
        self.assertFalse(manufacturing["manufacturing_certified"])
        self.assertIn('data-layer="INNER_CUT"', manufacturing["svg"])
        self.assertIn('data-source-front-boundary-digest="front-boundary-digest-a"',
                      manufacturing["svg"])
        self.assertIn("\n2\nINNER_CUT\n", manufacturing["dxf_export"]["text"])
        self.assertIn("\n8\nINNER_CUT\n", manufacturing["dxf_export"]["text"])
        self.assertIn("inner_cut_record_b64=",
                      manufacturing["dxf_export"]["text"])
        self.assertEqual(manufacturing["cut_manifest"][0]["inner_cut_count"], 1)

        self.assertEqual(package["verdict"], "ANSWER")
        manifest = json.loads(package["files"]["manifest.json"])
        self.assertEqual(len(manifest["inner_cut_manifest"]), 1)
        self.assertEqual(manifest["inner_cut_digest"],
                         manufacturing["inner_cut_digest"])
        self.assertEqual(manifest["inner_cut_manifest"][0][
            "source_front_boundary_digest"], "front-boundary-digest-a")
        verified = garment_export_verifier.verify(package)
        self.assertEqual(verified["verdict"], "ANSWER")
        self.assertEqual(verified["inner_cut_count"], 1)
        self.assertFalse(verified["manufacturing_certified"])

    def test_approved_candidate_does_not_promote_inferred_cutout(self):
        compiled, manufacturing, package = pipeline(cut(
            "window", "window-a",
            [[-1.0, 2.0], [1.0, 2.0], [1.0, 4.0], [-1.0, 4.0]]),
            approved=True)
        contour = compiled["pieces"][0]["inner_cutouts"][0]
        self.assertEqual(contour["state"], "PROPOSED")
        self.assertEqual(contour["approval_binding"]["approval_digest"],
                         "sha256:approved-candidate")
        self.assertEqual(manufacturing["candidate_digest"],
                         "sha256:approved-candidate")
        self.assertFalse(package["manufacturing_ready"])

    def test_invalid_finite_inside_intersection_and_clearance_cases_fail_closed(self):
        cases = [
            (cut("self", "a", [[-2, 1], [2, 3], [-2, 3], [2, 1]]),
             "UNKNOWN_CUTOUT_SELF_INTERSECTION"),
            (cut("outside", "a", [[4.8, 1], [5.5, 1], [5.5, 2], [4.8, 2]]),
             "UNKNOWN_CUTOUT_NOT_STRICTLY_INSIDE"),
            (cut("clearance", "a", [[4.4, 1], [4.8, 1], [4.8, 2], [4.4, 2]], 0.5),
             "UNKNOWN_CUTOUT_OUTER_CLEARANCE"),
            (cut("nan", "a", [[-1, 1], [math.nan, 1], [0, 2]]),
             "UNKNOWN_MALFORMED_STRUCTURE"),
        ]
        for operation, verdict in cases:
            with self.subTest(verdict=verdict):
                self.assertEqual(structure_to_pattern.compile(
                    structure(operation))["verdict"], verdict)

        first = cut("first", "a", [[-2, 1], [0, 1], [0, 3], [-2, 3]])
        overlap = cut("overlap", "b", [[-1, 2], [1, 2], [1, 3.5], [-1, 3.5]])
        self.assertEqual(structure_to_pattern.compile(
            structure(first, overlap))["verdict"],
            "UNKNOWN_CUTOUT_CONTOUR_INTERSECTION")

    def test_self_consistent_outer_rehash_cannot_hide_changed_svg_inner_geometry(self):
        _compiled, manufacturing, package = pipeline(cut(
            "window", "window-a",
            [[-1.0, 2.0], [1.0, 2.0], [1.0, 4.0], [-1.0, 4.0]]))
        row = manufacturing["inner_cut_manifest"][0]
        x, y = row["svg_points"][0]
        original = f'{x:.6f},{y:.6f}'
        changed = f'{x + 0.25:.6f},{y:.6f}'
        package["files"]["pattern.svg"] = package["files"]["pattern.svg"].replace(
            original, changed, 1)
        rehash_package(package)
        result = garment_export_verifier.verify(package)
        self.assertEqual(result["verdict"], "UNKNOWN_EXPORT_INNER_CUT_SVG")

    def test_self_consistent_outer_rehash_cannot_hide_changed_dxf_inner_geometry(self):
        _compiled, manufacturing, package = pipeline(cut(
            "window", "window-a",
            [[-1.0, 2.0], [1.0, 2.0], [1.0, 4.0], [-1.0, 4.0]]))
        row = manufacturing["inner_cut_manifest"][0]
        x, y = row["dxf_points"][0]
        text = package["files"]["pattern.dxf"].decode("cp932")
        needle = f"10\n{x:.4f}\n20\n{y:.4f}"
        replacement = f"10\n{x + 0.25:.4f}\n20\n{y:.4f}"
        self.assertIn(needle, text)
        package["files"]["pattern.dxf"] = text.replace(
            needle, replacement, 1).encode("cp932")
        rehash_package(package)
        result = garment_export_verifier.verify(package)
        self.assertEqual(result["verdict"], "UNKNOWN_EXPORT_INNER_CUT_DXF")


if __name__ == "__main__":
    unittest.main()
