#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import json
import unittest

from photoloset import front_region_structure_cues
from photoloset import garment_structure


class FrontRegionStructureCueTests(unittest.TestCase):
    def outline(self):
        return {
            "outline": [[42, 0], [58, 0], [68, 34], [96, 100],
                        [4, 100], [32, 34]],
            "provenance": {"kind": "OBSERVED", "source": "human-confirmed mask"},
        }

    def complex_regions(self):
        return [
            {"id": "top", "label": "bodice", "confidence": .96,
             "polygon": [[34, 8], [66, 8], [65, 45], [35, 45]],
             "provenance": {"kind": "OBSERVED"}},
            {"id": "waist", "label": "waist seam", "confidence": .91,
             "polygon": [[31, 43], [69, 43], [69, 47], [31, 47]],
             "provenance": {"kind": "OBSERVED"}},
            {"id": "leg-l", "labels": ["pants", "left leg"], "confidence": .88,
             "polygon": [[31, 47], [49, 47], [47, 97], [26, 97]]},
            {"id": "leg-r", "labels": ["right leg", "pants"], "confidence": .88,
             "polygon": [[51, 47], [69, 47], [74, 97], [53, 97]]},
            {"id": "sleeve-l", "label": "long sleeve", "confidence": .93,
             "polygon": [[24, 12], [35, 14], [31, 58], [17, 56]]},
            {"id": "sleeve-r", "label": "long sleeve", "confidence": .93,
             "polygon": [[65, 14], [76, 12], [83, 56], [69, 58]]},
            {"id": "front-layer", "labels": ["overlay", "frill"], "confidence": .84,
             "polygon": [[37, 20], [63, 20], [72, 70], [28, 70]]},
        ]

    def test_regions_open_separates_split_sleeve_layer_and_frill_structures(self):
        result = front_region_structure_cues.hypothesize(
            self.outline(), self.complex_regions(), source_id="anime-front")
        self.assertEqual(result["verdict"], "PROPOSED")
        cues = result["typed_cues"]
        self.assertEqual(cues["composition"]["value"], "separates")
        self.assertEqual(cues["lower_shape"]["value"], "split")
        self.assertEqual(cues["sleeve_shape"]["value"], "long")
        self.assertGreaterEqual(cues["layer_count"]["value"], 2)
        self.assertIn("overlay", cues["details"]["value"])
        self.assertIn("ruffle", cues["details"]["value"])
        self.assertEqual(len(result["hypotheses"]), 3)
        for candidate in result["hypotheses"]:
            self.assertEqual(candidate["state"], "PROPOSED")
            self.assertEqual(garment_structure.validate(candidate)["verdict"], "ANSWER")
            kinds = {node["kind"] for node in candidate["nodes"]}
            self.assertIn("GUSSET", kinds)
            self.assertIn("SLEEVE", kinds)
            self.assertIn("OVERLAY", kinds)
            self.assertIn("BAND", kinds)

    def test_missing_labels_stays_ambiguous_and_returns_diverse_candidates(self):
        unlabeled = [
            {"polygon": [[12, 14], [31, 16], [28, 56], [5, 54]]},
            {"polygon": [[69, 16], [88, 14], [95, 54], [72, 56]]},
            {"polygon": [[34, 18], [66, 18], [70, 82], [30, 82]]},
        ]
        result = front_region_structure_cues.hypothesize(self.outline(), unlabeled)
        cues = result["typed_cues"]
        self.assertEqual(cues["composition"]["value"], "ambiguous")
        self.assertEqual(cues["lower_shape"]["value"], "ambiguous")
        self.assertIn(cues["sleeve_shape"]["value"], {"long", "short", "ambiguous"})
        self.assertIn("decorative_ambiguous", cues["details"]["value"])
        self.assertEqual(len(result["hypotheses"]), 3)
        node_sets = [{node["kind"] for node in row["nodes"]}
                     for row in result["hypotheses"]]
        self.assertTrue(any("FLARE" in kinds for kinds in node_sets))
        self.assertTrue(any("GUSSET" in kinds for kinds in node_sets))
        self.assertTrue(any("OVERLAY" in kinds and "BAND" in kinds
                            for kinds in node_sets))

    def test_weak_contradictory_labels_do_not_become_observed_truth(self):
        regions = [
            {"id": "uncertain-dress", "label": "dress", "confidence": .2,
             "polygon": [[30, 5], [70, 5], [72, 95], [28, 95]],
             "provenance": {"kind": "OBSERVED"}},
            {"id": "uncertain-waist", "label": "waist seam", "confidence": "low",
             "polygon": [[25, 45], [75, 45], [75, 48], [25, 48]]},
        ]
        result = front_region_structure_cues.hypothesize(self.outline(), regions)
        self.assertEqual(result["typed_cues"]["composition"]["value"], "ambiguous")
        for cue in result["typed_cues"].values():
            if isinstance(cue, dict) and "state" in cue:
                self.assertEqual(cue["state"], "PROPOSED")
        self.assertFalse(result["claims"]["back_observed"])
        self.assertFalse(result["claims"]["material_observed"])
        self.assertFalse(result["claims"]["sewing_observed"])
        self.assertFalse(result["claims"]["detector_confidence_is_fact"])
        for candidate in result["hypotheses"]:
            self.assertEqual(candidate["back_alternative"]["state"], "PROPOSED")
            self.assertFalse(candidate["candidate_claims"]["back_observed"])
            self.assertFalse(candidate["candidate_claims"]["material_observed"])
            self.assertFalse(candidate["candidate_claims"]["sewing_observed"])

    def test_deterministic_digest_and_evidence_ignore_region_input_order(self):
        regions = self.complex_regions()
        first = front_region_structure_cues.hypothesize(
            self.outline(), regions, source_id="stable")
        second = front_region_structure_cues.hypothesize(
            copy.deepcopy(self.outline()), list(reversed(copy.deepcopy(regions))),
            source_id="stable")
        self.assertEqual(first, second)
        self.assertEqual(first["digest"], second["digest"])
        self.assertEqual(first["source_digest"], second["source_digest"])
        self.assertTrue(first["cue_evidence"]["composition_region_ids"])
        self.assertTrue(first["cue_evidence"]["sleeve_region_ids"])
        json.dumps(first, ensure_ascii=False, allow_nan=False)

    def test_open_internal_line_changes_region_evidence_lineage(self):
        baseline_outline = self.outline()
        with_line = self.outline()
        with_line["internal_lines"] = [[[18, 50], [82, 50]]]

        baseline = front_region_structure_cues.hypothesize(
            baseline_outline, self.complex_regions(), source_id="lineage")
        changed = front_region_structure_cues.hypothesize(
            with_line, self.complex_regions(), source_id="lineage")

        self.assertNotEqual(baseline["front_geometry_digest"],
                            changed["front_geometry_digest"])
        self.assertNotEqual(baseline["source_digest"],
                            changed["source_digest"])
        self.assertFalse(changed["claims"]["internal_line_semantics_observed"])
        for candidate in changed["hypotheses"]:
            self.assertEqual(candidate["front_geometry_digest"],
                             changed["front_geometry_digest"])
            self.assertEqual(candidate["front_region_evidence_digest"],
                             changed["source_digest"])

    def test_embedded_regions_normalized_space_and_bad_rows(self):
        payload = self.outline()
        payload["regions"] = [
            {"id": "cape", "label": "cape", "normalized": True,
             "polygon": [[.2, .1], [.8, .1], [.9, .8], [.1, .8]]},
            {"id": "bad", "label": "ruffle", "polygon": [[1, 1], [1, 1]]},
        ]
        result = front_region_structure_cues.hypothesize(payload)
        self.assertEqual(result["rejected_region_count"], 1)
        self.assertEqual(len(result["regions"]), 1)
        self.assertEqual(result["regions"][0]["coordinate_interpretation"], "normalized")
        self.assertIn("cape", result["typed_cues"]["details"]["value"])
        self.assertFalse(result["claims"]["measurements_from_pixels"])

    def test_parallel_polygon_label_confidence_wire_form(self):
        polygons = [row["polygon"] for row in self.complex_regions()]
        labels = [row.get("labels", row.get("label"))
                  for row in self.complex_regions()]
        confidences = [row["confidence"] for row in self.complex_regions()]
        result = front_region_structure_cues.hypothesize(
            self.outline(), region_polygons=polygons, labels=labels,
            confidences=confidences, source_id="parallel-wire")
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(len(result["regions"]), len(polygons))
        self.assertEqual(result["typed_cues"]["composition"]["value"], "separates")
        self.assertEqual(result["typed_cues"]["lower_shape"]["value"], "split")
        self.assertIn("ruffle", result["typed_cues"]["details"]["value"])
        self.assertEqual(len(result["hypotheses"]), 3)

    def test_bad_outline_fails_closed(self):
        result = front_region_structure_cues.hypothesize(
            {"outline": [[0, 0], [0, 0]]}, self.complex_regions())
        self.assertTrue(result["verdict"].startswith("UNKNOWN_"))
        self.assertNotIn("hypotheses", result)


if __name__ == "__main__":
    unittest.main()
