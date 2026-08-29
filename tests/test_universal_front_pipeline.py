#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adversarial front-only regression for the universal garment pipeline.

These fixtures are confirmed *outer clothing boundaries*, not hidden rear
observations.  The test deliberately follows the same authority boundary as
the product: dimensionless front geometry opens three proposed structures;
each proposal gets its own 3D preview and pattern; the repair catalogue may
then measure or alter the geometric prototype.  A green repair measurement
must never be confused with a manufacturing-ready pattern.
"""
from __future__ import annotations

import unittest
from typing import Any, Dict, Iterable, List, Tuple

from photoloset import front_geometry_cues
from photoloset import repairs
from photoloset import structure_preview
from photoloset import structure_to_pattern


Point = Tuple[float, float]


def _symmetric_outline(widths: Iterable[float]) -> List[Point]:
    """Build a clockwise outline with samples in every geometry-cue band."""
    ys = (0.0, 10.0, 25.0, 40.0, 55.0, 70.0, 85.0, 100.0)
    rows = list(zip(widths, ys))
    if len(rows) != len(ys):
        raise ValueError("a fixture needs exactly eight widths")
    left = [(-width / 2.0, y) for width, y in rows]
    right = [(width / 2.0, y) for width, y in reversed(rows)]
    return left + right


FRONT_FIXTURES: Dict[str, List[Point]] = {
    # Extreme lower expansion; the geometry boundary must preserve it as an
    # anime-exaggerated proposal rather than silently normalising the hem.
    "anime_exaggerated": _symmetric_outline(
        (32.0, 34.0, 30.0, 24.0, 30.0, 54.0, 72.0, 84.0)),
    # A plain near-column outline.  One generated alternative must still test
    # an ordinary separated upper/two-leg lower construction.
    "ordinary_separates": _symmetric_outline(
        (34.0, 36.0, 34.0, 32.0, 32.0, 34.0, 36.0, 36.0)),
    # Broad upper and lower extrema exercise the explicit overlay/layer path.
    # A front outline cannot prove that this is specifically a cape.
    "layered_or_cape": _symmetric_outline(
        (54.0, 58.0, 52.0, 40.0, 46.0, 56.0, 62.0, 66.0)),
    # Alternating widths imitate a frilled outer contour.  The third proposal
    # must express the interpretation as BAND + GATHER, not as an observation.
    "ruffle_or_frill": _symmetric_outline(
        (34.0, 42.0, 30.0, 36.0, 28.0, 48.0, 38.0, 56.0)),
}


def _walk(value: Any, path: Tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, path + (str(key),))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _walk(child, path + (str(index),))
    else:
        yield path, value


def _kinds(candidate: Dict[str, Any]) -> List[str]:
    return [node["kind"] for node in candidate["structure"]["nodes"]]


class UniversalFrontPipelineTests(unittest.TestCase):
    maxDiff = None

    def _run_fixture(self, name: str) -> Dict[str, Any]:
        front = front_geometry_cues.hypothesize(
            {
                "outline": FRONT_FIXTURES[name],
                "provenance": {
                    "kind": "OBSERVED",
                    "source": f"confirmed test outline: {name}",
                },
            },
            source_id=name,
        )
        self.assertEqual(front["verdict"], "PROPOSED")
        self.assertEqual(front["outline_state"], "OBSERVED")
        self.assertFalse(front["claims"]["back_observed"])
        self.assertFalse(front["claims"]["depth_observed"])
        self.assertEqual(len(front["hypotheses"]), 3)

        previews = []
        patterns = []
        measurements = []
        repaired = []
        for candidate in front["hypotheses"]:
            self.assertEqual(candidate["state"], "PROPOSED")
            self.assertEqual(candidate["unobserved"]["back"], "PROPOSED")
            self.assertTrue(candidate["assumptions"])
            for path, value in _walk(candidate):
                if any("back" in part.lower() for part in path):
                    self.assertNotEqual(
                        value, "OBSERVED",
                        msg=f"front-only back authority leak at {'/'.join(path)}")

            preview = structure_preview.generate_candidate_preview(candidate)
            self.assertEqual(preview["verdict"], "ANSWER")
            self.assertEqual(preview["state"], "PROPOSED")
            self.assertTrue(preview["mesh"]["vertices"])
            self.assertTrue(preview["mesh"]["faces"])
            self.assertFalse(preview["claims"]["manufacturing_ready"])

            pattern = structure_to_pattern.compile(
                candidate["structure"],
                candidate_state="PROPOSED",
                candidate_id=candidate["candidate_id"],
            )
            self.assertEqual(pattern["verdict"], "ANSWER")
            self.assertTrue(pattern["pieces"])
            self.assertTrue(pattern["seam_checks"])
            self.assertTrue(all(
                piece["outline"] and piece["edges"]
                for piece in pattern["pieces"]))
            self.assertFalse(pattern["manufacturing_ready"])
            self.assertEqual(pattern["candidate_state"], "PROPOSED")
            self.assertGreaterEqual(len(pattern["remaining_gates"]), 4)

            measured = repairs.measure_sewable(pattern)
            fixed = repairs.make_sewable(pattern, budget=2)
            self.assertTrue(fixed["sewable"])
            self.assertFalse(fixed["pattern"]["manufacturing_ready"])
            self.assertEqual(fixed["pattern"]["candidate_state"], "PROPOSED")

            previews.append(preview)
            patterns.append(pattern)
            measurements.append(measured)
            repaired.append(fixed)

        # Candidate identity must materially change both outputs.  Merely
        # changing a label while returning one mannequin/pattern would fail.
        self.assertEqual(len({row["structure_digest"] for row in previews}), 3)
        self.assertEqual(len({row["preview_digest"] for row in previews}), 3)
        self.assertEqual(len({row["digest"] for row in patterns}), 3)
        self.assertEqual(len({
            repr(row["mesh"]["vertices"]) for row in previews
        }), 3)

        # The unsegmented flare remains deliberately wider than the exact,
        # typed 150 cm marker boundary.  Expanded lower and ruffle candidates
        # are now drafted as real seam-connected panels, so they no longer
        # inherit the old monolithic-width failure.
        for index in (0,):
            marker = measurements[index]["checks"]["marker.lay"]
            self.assertFalse(marker["ok"])
            self.assertEqual(
                marker["verdict"], "UNKNOWN_PIECE_WIDER_THAN_FABRIC")
            self.assertEqual(
                repaired[index]["transcript"][0]["problem"],
                "UNKNOWN_PIECE_WIDER_THAN_FABRIC")
            self.assertTrue(repaired[index]["transcript"][0]["applied"])
            # The current split is intentionally not silently blessed: it
            # reports the named boundary edges it could not preserve.
            self.assertTrue(
                repaired[index]["transcript"][0]["cost"]["dropped_edges"])
        self.assertTrue(measurements[2]["checks"]["marker.lay"]["ok"])
        self.assertTrue(measurements[1]["sewable"])

        return {
            "front": front,
            "previews": previews,
            "patterns": patterns,
            "measurements": measurements,
            "repaired": repaired,
        }

    def test_anime_exaggerated_front_runs_all_three_candidates(self):
        run = self._run_fixture("anime_exaggerated")
        self.assertEqual(
            run["front"]["typed_cues"]["silhouette"]["value"],
            "anime_exaggerated")
        hems = [
            next(node for node in candidate["structure"]["nodes"]
                 if node["kind"] == "FLARE")["dimensions"][
                     "bottom_circumference_cm"]
            for candidate in run["front"]["hypotheses"]
            if "FLARE" in _kinds(candidate)
        ]
        self.assertEqual(hems, [202.8])

    def test_ordinary_front_includes_separates_candidate(self):
        run = self._run_fixture("ordinary_separates")
        candidate = run["front"]["hypotheses"][1]
        self.assertEqual(_kinds(candidate).count("TUBE"), 2)
        self.assertIn("GUSSET", _kinds(candidate))
        upper = next(node for node in candidate["structure"]["nodes"]
                     if node["node_id"] == "upper-shell")
        self.assertEqual(upper["attributes"]["garment_unit"], "upper")

    def test_layered_cape_front_stays_overlay_proposal(self):
        run = self._run_fixture("layered_or_cape")
        candidate = run["front"]["hypotheses"][1]
        overlay = next(node for node in candidate["structure"]["nodes"]
                       if node["kind"] == "OVERLAY")
        self.assertGreater(overlay["layer"], 0)
        self.assertEqual(overlay["attributes"]["geometry_state"], "PROPOSED")
        self.assertIn("overlay", overlay["attributes"]["detail_roles"])
        self.assertNotIn("cape", overlay["attributes"]["detail_roles"])

    def test_ruffle_front_includes_addressed_gather_candidate(self):
        run = self._run_fixture("ruffle_or_frill")
        candidate = run["front"]["hypotheses"][2]
        self.assertIn("BAND", _kinds(candidate))
        gathers = [operation for operation in candidate["structure"]["operations"]
                   if operation["kind"] == "GATHER"]
        self.assertEqual(len(gathers), 1)
        pattern = run["patterns"][2]
        self.assertTrue(any(
            row.get("kind") == "SEGMENTED_GATHER_ATTACHMENT"
            for row in pattern["candidate_specific_expansions"]))
        self.assertEqual(
            len([row for row in pattern["seams"]
                 if row.get("kind") == "GATHER"]),
            4)

    def test_invalid_front_is_a_typed_unknown_not_an_empty_success(self):
        result = front_geometry_cues.hypothesize(
            {"outline": [(0.0, 0.0), (1.0, 1.0)],
             "provenance": {"kind": "OBSERVED"}},
            source_id="degenerate-front",
        )
        self.assertEqual(result["verdict"], "UNKNOWN_FRONT_OUTLINE")
        self.assertIn("how_to_close", result)
        self.assertNotIn("hypotheses", result)


if __name__ == "__main__":
    unittest.main()
