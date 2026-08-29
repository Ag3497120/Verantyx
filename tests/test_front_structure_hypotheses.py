#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import unittest

from photoloset import garment_structure
from photoloset.front_structure_hypotheses import (
    CueState,
    FrontStructureCues,
    TypedCue,
    hypothesize_front_structure,
)


def observed(value, name="front annotation"):
    return TypedCue(
        value, CueState.OBSERVED,
        f"typed {name} placed on the visible front",
        f"the visible front annotation for {name} is corrected or found occluded",
    )


def proposed(value, name="interpretation"):
    return TypedCue(
        value, CueState.PROPOSED,
        f"bounded {name} proposed from the visible front",
        f"another view or reviewer rejects the {name}",
    )


def simple_cues():
    return FrontStructureCues(
        source_id="fixture:simple-front",
        composition=observed("one_piece", "continuous waist region"),
        silhouette=observed("flared", "outer silhouette"),
        lower_shape=observed("flare", "lower outline"),
        sleeve_shape=observed("long", "sleeve extent"),
        layer_count=observed(1, "visible layer count"),
        details=observed((), "visible details"),
    )


class FrontStructureHypothesisTests(unittest.TestCase):
    def test_simple_front_returns_two_deterministic_valid_candidates(self):
        first = hypothesize_front_structure(simple_cues())
        second = hypothesize_front_structure(simple_cues())
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        self.assertEqual(len({row["candidate_id"] for row in first}), 2)
        for candidate in first:
            self.assertEqual(candidate["schema"], "garment.structure.v1")
            self.assertEqual(candidate["state"], "PROPOSED")
            self.assertEqual(
                garment_structure.validate(candidate)["verdict"], "ANSWER")
            json.dumps(candidate, allow_nan=False)

    def test_observed_front_never_promotes_back_to_observed_truth(self):
        candidates = hypothesize_front_structure(simple_cues())
        for candidate in candidates:
            self.assertEqual(
                candidate["front_cues"]["silhouette"]["state"], "OBSERVED")
            back = candidate["back_alternative"]
            self.assertEqual(back["state"], "PROPOSED")
            self.assertTrue(back["basis"])
            self.assertTrue(back["breaks_when"])
            self.assertEqual(candidate["unobserved"]["back"], "PROPOSED")
            back_nodes = [node for node in candidate["nodes"]
                          if node["node_id"] == "back-opening"]
            self.assertTrue(all(node["attributes"]["state"] == "PROPOSED"
                                for node in back_nodes))

    def test_separates_layers_and_anime_geometry_return_three_candidates(self):
        cues = FrontStructureCues(
            source_id="fixture:anime-layered-front",
            composition=observed("separates", "visible waist separation"),
            silhouette=proposed("anime_exaggerated", "silhouette reading"),
            lower_shape=observed("split", "two lower volumes"),
            sleeve_shape=observed("detached", "detached sleeves"),
            layer_count=observed(3, "visible layer ordering"),
            details=observed(("cape", "ruffle", "asymmetry"),
                             "decorative front regions"),
        )
        candidates = hypothesize_front_structure(cues)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(
            {row["back_alternative"]["alternative_id"] for row in candidates},
            {"center_back_opening", "side_opening_closed_back",
             "closed_back_stretch"},
        )
        for candidate in candidates:
            kinds = [node["kind"] for node in candidate["nodes"]]
            operation_kinds = [row["kind"] for row in candidate["operations"]]
            self.assertGreaterEqual(kinds.count("TUBE"), 2)
            self.assertGreaterEqual(kinds.count("OVERLAY"), 2)
            self.assertIn("BAND", kinds)
            self.assertIn("LAYER", operation_kinds)
            self.assertIn("GATHER", operation_kinds)
            self.assertEqual(
                garment_structure.validate(candidate)["verdict"], "ANSWER")

    def test_ambiguous_front_varies_composition_and_lower_geometry(self):
        cues = FrontStructureCues(
            source_id="fixture:ambiguous-front",
            composition=proposed("ambiguous", "waist continuity"),
            silhouette=observed("straight", "outer silhouette"),
            lower_shape=proposed("ambiguous", "occluded lower structure"),
            sleeve_shape=observed("none", "arm boundary"),
            layer_count=observed(1, "visible layer count"),
            details=observed((), "visible details"),
        )
        candidates = hypothesize_front_structure(cues)
        node_sets = [{node["node_id"] for node in row["nodes"]}
                     for row in candidates]
        self.assertIn("lower-flare", node_sets[0])
        self.assertIn("lower-left", node_sets[1])
        self.assertIn("lower-tube", node_sets[2])
        self.assertIn("join-upper-lower",
                      {op["operation_id"] for op in candidates[0]["operations"]})
        self.assertNotIn("join-upper-lower",
                         {op["operation_id"] for op in candidates[1]["operations"]})

    def test_proposed_front_separation_never_promotes_construction_or_back(self):
        cues = FrontStructureCues(
            source_id="fixture:internal-boundary-separation",
            composition=proposed("separates", "transverse internal boundary"),
            silhouette=observed("flared", "outer silhouette"),
            lower_shape=proposed("flare", "lower volume"),
            sleeve_shape=proposed("puff", "arm-region outline"),
            layer_count=proposed(2, "stacked internal boundaries"),
            details=proposed(("overlay", "ruffle"), "oscillating boundary"),
        )
        candidates = hypothesize_front_structure(cues)
        for candidate in candidates:
            self.assertEqual(candidate["front_cues"]["composition"]["state"],
                             "PROPOSED")
            self.assertEqual(candidate["back_alternative"]["state"], "PROPOSED")
            self.assertEqual(candidate["unobserved"]["internal_construction"],
                             "PROPOSED")
            self.assertNotIn(
                "join-upper-lower",
                {row["operation_id"] for row in candidate["operations"]},
            )
            units = {node["attributes"].get("garment_unit")
                     for node in candidate["nodes"]}
            self.assertTrue({"upper", "lower"}.issubset(units))
            self.assertEqual(garment_structure.validate(candidate)["verdict"],
                             "ANSWER")

    def test_raw_or_unfalsifiable_cues_are_rejected(self):
        with self.assertRaises(TypeError):
            hypothesize_front_structure({"silhouette": "flared"})
        with self.assertRaises(ValueError):
            TypedCue("flared", CueState.PROPOSED, "", "rear view differs")
        with self.assertRaises(TypeError):
            FrontStructureCues(
                source_id="fixture:raw",
                composition="one_piece",  # type: ignore[arg-type]
                silhouette=observed("flared"),
                lower_shape=observed("flare"),
                sleeve_shape=observed("none"),
                layer_count=observed(1),
                details=observed(()),
            )


if __name__ == "__main__":
    unittest.main()
