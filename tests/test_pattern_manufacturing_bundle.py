#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import json
import unittest

from photoloset import pattern_manufacturing_bundle as bundle


def rectangle(piece_id, width, height, *, cut_count=1, layer=0,
              role="panel", grain_state="PROPOSED"):
    return {
        "piece_id": piece_id,
        "name": piece_id,
        "outline": [[0.0, 0.0], [width, 0.0],
                    [width, height], [0.0, height]],
        "cut_count": cut_count,
        "layer": layer,
        "role": role,
        "primitive_kind": "BAND" if role == "frill" else "OVERLAY",
        "grain": {"direction": "parallel_to_height", "state": grain_state},
        "provenance": {"method": "test explicit geometry"},
    }


def compiled(pieces=None, seams=None):
    pieces = pieces or [rectangle("body", 80.0, 60.0)]
    return {
        "verdict": "ANSWER",
        "schema": "garment.compiled-pattern.v1",
        "digest": "source-pattern-digest",
        "structure_digest": "source-structure-digest",
        "candidate_id": "candidate-a",
        "candidate_state": "PROPOSED",
        "pieces": pieces,
        "seams": seams or [],
        "layers": [],
        "manufacturing_ready": False,
        "remaining_gates": ["construction validation"],
        "provenance": {"method": "test compiler", "corpus_used": False},
        "not_a_published_system": "test geometric baseline",
        "note": "front-only back remains proposed",
    }


class PatternManufacturingBundleTests(unittest.TestCase):
    def test_sleeve_is_cut_twice_and_has_distinct_boundaries_and_seam_end_notches(self):
        pieces = [rectangle("sleeve", 36.0, 58.0, cut_count=2,
                            role="sleeve_wrap")]
        seams = [{
            "operation_id": "close-sleeve", "kind": "PROCEDURAL_CLOSURE",
            "a": {"piece_id": "sleeve", "edge": "e1"},
            "b": {"piece_id": "sleeve", "edge": "e3"},
            "state": "PROPOSED",
        }]
        result = bundle.build(compiled(pieces, seams), seam_allowance_cm=1.0)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["cut_manifest"],
                         [{"piece_id": "sleeve", "cut_count": 2}])
        sleeve = result["pieces"][0]
        self.assertEqual(sleeve["cut_count"], 2)
        self.assertNotEqual(sleeve["sew_line"], sleeve["cut_line"])
        self.assertGreater(sleeve["cut_area_cm2"], sleeve["area_cm2"])
        roles = {n["role"] for n in result["notches"]["sleeve"]}
        self.assertEqual(roles, {"close-sleeve:start", "close-sleeve:end"})
        # Both addressed seam edges carry both endpoint roles.
        self.assertEqual(len(result["notches"]["sleeve"]), 4)
        self.assertTrue(result["dxf_compatible"])

    def test_layered_overlay_and_frill_are_preserved_in_order(self):
        pieces = [
            rectangle("base", 80.0, 50.0, layer=0, role="body_wrap"),
            rectangle("overlay", 90.0, 45.0, layer=1, role="overlay"),
            {**rectangle("frill", 150.0, 12.0, layer=2, role="frill"),
             "transforms": [{"kind": "GATHER", "ratio": 1.5}]},
        ]
        result = bundle.build(compiled(pieces), seam_allowance_cm=0.8)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual([row["piece_id"] for row in result["layer_order"]],
                         ["base", "overlay", "frill"])
        frill = next(piece for piece in result["pieces"]
                     if piece["piece_id"] == "frill")
        self.assertEqual(frill["role"], "frill")
        self.assertEqual(frill["transforms"][0]["kind"], "GATHER")
        self.assertIn('<svg xmlns="http://www.w3.org/2000/svg"', result["svg"])
        self.assertTrue(any(record["layer"] == "CUT_LINE"
                            and record["piece_id"] == "frill"
                            for record in result["dxf_layer_records"]))

    def test_missing_seam_allowance_fails_closed(self):
        result = bundle.build(compiled())
        self.assertEqual(result["verdict"], "UNKNOWN_SEAM_ALLOWANCE_MISSING")
        self.assertNotIn("pieces", result)
        self.assertIn("no cut line", result["why"])

    def test_proposed_default_requires_opt_in_and_stays_proposed(self):
        result = bundle.build(compiled(), allow_proposed_default=True,
                              proposed_default_cm=1.1)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["seam_allowance_cm"]["body"]["state"],
                         "PROPOSED")
        for edge in result["seam_allowance_cm"]["body"]["edges"].values():
            self.assertEqual(edge["state"], "PROPOSED")
            self.assertTrue(edge["basis"])
            self.assertTrue(edge["assumption_breaks_when"])
        self.assertTrue(result["manufacturing_preview_ready"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertIn("approve or measure every proposed seam allowance",
                      result["remaining_gates"])

    def test_unexplained_proposed_value_is_refused(self):
        result = bundle.build(
            compiled(), seam_allowance_cm={"value_cm": 1.0,
                                           "state": "PROPOSED"})
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PROPOSED_SEAM_ALLOWANCE_UNEXPLAINED")

    def test_output_is_deterministic_and_preserves_source_lineage(self):
        source = compiled()
        first = bundle.build(copy.deepcopy(source), seam_allowance_cm=1.0)
        second = bundle.build(copy.deepcopy(source), seam_allowance_cm=1.0)
        self.assertEqual(first, second)
        self.assertEqual(first["digest"], second["digest"])
        self.assertEqual(first["source_digest"], "source-pattern-digest")
        self.assertEqual(first["structure_digest"], "source-structure-digest")
        self.assertEqual(first["provenance"]["source_provenance"],
                         source["provenance"])
        json.dumps(first, sort_keys=True, ensure_ascii=False, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
