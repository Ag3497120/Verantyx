#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import json
import unittest

from photoloset import ornament_primitives


def source(state="PROPOSED"):
    return {
        "origin": "IMAGE_INTERPRETATION",
        "state": state,
        "basis": "front image suggests this ornament geometry",
        "breaks_when": "rear, side or inside construction contradicts it",
    }


def base(kind, dimensions, **overrides):
    value = {
        "ornament_id": f"ornament-{kind.lower()}",
        "kind": kind,
        "state": "PROPOSED",
        "dimensions": dimensions,
        "quantity": 1,
        "layer": 2,
        "grain_direction": "BIAS_45",
        "seam_allowance_cm": 0.8,
        "attachment": {
            "target_piece_id": "bodice-front",
            "target_port_id": "center-front",
            "state": "PROPOSED",
        },
        "source": source(),
    }
    value.update(overrides)
    return value


class OrnamentPrimitiveTests(unittest.TestCase):
    def assert_pattern_artifacts(self, result):
        self.assertEqual(result["verdict"], "PROPOSED", result)
        self.assertEqual(result["state"], "PROPOSED")
        self.assertTrue(result["pattern_pieces"])
        self.assertTrue(result["attachment_ports"])
        self.assertTrue(result["seam_intents"])
        self.assertEqual(
            result["construction_order"],
            [row["intent_id"] for row in result["seam_intents"]],
        )
        for piece in result["pattern_pieces"]:
            self.assertEqual(piece["state"], "PROPOSED")
            self.assertGreater(piece["cut_area_cm2"], piece["sew_area_cm2"])
            self.assertNotEqual(piece["cut_line"], piece["sew_line"])
            self.assertEqual(piece["boundary_layers"], {
                "sew_line": 14, "cut_line": 1,
            })
            self.assertTrue(all(edge["state"] == "PROPOSED"
                                for edge in piece["edges"]))
        self.assertTrue(all(port["state"] == "PROPOSED"
                            and not port["observed"]
                            for port in result["attachment_ports"]))
        self.assertTrue(all(row["state"] == "PROPOSED"
                            for row in result["seam_intents"]))
        self.assertEqual(result["geometry_validation"]["verdict"], "ANSWER")
        self.assertFalse(result["geometry_validation"]["authority_granted"])
        self.assertFalse(result["authority"]["observed"])
        self.assertFalse(result["authority"]["image_promoted_to_observed"])
        self.assertFalse(result["provenance"]["corpus_used"])
        self.assertFalse(result["provenance"]["garment_class_added"])
        json.dumps(result, allow_nan=False)

    def test_bow_expands_to_body_knot_port_and_ordered_seam_intents(self):
        spec = base("BOW", {
            "body_length_cm": 24.0,
            "body_width_cm": 8.0,
            "knot_length_cm": 7.0,
            "knot_width_cm": 3.0,
        })
        result = ornament_primitives.expand(spec)
        self.assert_pattern_artifacts(result)
        self.assertEqual(
            {piece["role"] for piece in result["pattern_pieces"]},
            {"bow_body", "bow_center_wrap"},
        )
        self.assertEqual(len(result["attachment_ports"]), 1)
        self.assertEqual(result["attachment_ports"][0]["geometry"]["kind"],
                         "POINT")
        self.assertEqual(result["attachment_ports"][0]["target"], {
            "target_piece_id": "bodice-front",
            "target_port_id": "center-front",
            "state": "PROPOSED",
            "observed": False,
        })
        self.assertEqual(
            [row["kind"] for row in result["seam_intents"]],
            ["JOIN", "JOIN", "FOLD_AND_TACK", "WRAP", "JOIN",
             "ATTACH_TO_GARMENT"],
        )

    def test_ribbon_rosette_tie_and_flap_each_expand_as_geometry(self):
        cases = [
            base("RIBBON", {"length_cm": 60.0, "width_cm": 4.0},
                 attachment_mode="END", grain_direction="LENGTHWISE"),
            base("ROSETTE", {
                "strip_length_cm": 90.0,
                "strip_width_cm": 5.0,
                "finished_inner_length_cm": 18.0,
            }),
            base("TIE", {
                "length_cm": 35.0, "top_width_cm": 7.0,
                "tip_width_cm": 2.0,
            }, quantity=2),
            base("FLAP", {
                "attachment_width_cm": 12.0, "depth_cm": 8.0,
                "outer_width_cm": 9.0,
            }, grain_direction="CROSSWISE"),
        ]
        for spec in cases:
            with self.subTest(kind=spec["kind"]):
                result = ornament_primitives.expand(spec)
                self.assert_pattern_artifacts(result)
                expected = 2 if spec["kind"] == "TIE" else 1
                self.assertEqual(len(result["pattern_pieces"]), expected)
        rosette = ornament_primitives.expand(cases[1])
        gather = rosette["seam_intents"][0]
        self.assertEqual(gather["kind"], "GATHER")
        self.assertEqual(gather["parameters"]["ratio"], 5.0)
        tie = ornament_primitives.expand(cases[2])
        self.assertEqual(
            [piece["piece_id"] for piece in tie["pattern_pieces"]],
            ["ornament-tie:1", "ornament-tie:2"],
        )

    def test_missing_dimensions_and_implicit_quantity_fail_closed(self):
        missing_dimension = base("FLAP", {
            "attachment_width_cm": 12.0, "depth_cm": 8.0,
        })
        missing_quantity = base("TIE", {
            "length_cm": 35.0, "top_width_cm": 7.0,
            "tip_width_cm": 2.0,
        })
        missing_quantity.pop("quantity")
        first = ornament_primitives.expand(missing_dimension)
        second = ornament_primitives.expand(missing_quantity)
        self.assertEqual(first["verdict"],
                         "UNKNOWN_ORNAMENT_DIMENSIONS_MISSING")
        self.assertEqual(first["missing"], ["outer_width_cm"])
        self.assertEqual(second["verdict"],
                         "UNKNOWN_ORNAMENT_QUANTITY_REQUIRED")
        self.assertNotIn("pattern_pieces", first)
        self.assertNotIn("pattern_pieces", second)

    def test_ambiguous_construction_returns_review_instead_of_guessing(self):
        ribbon = base("RIBBON", {"length_cm": 50.0, "width_cm": 4.0})
        result = ornament_primitives.expand(ribbon)
        self.assertEqual(result["verdict"],
                         "REVIEW_ORNAMENT_CONSTRUCTION_REQUIRED")
        self.assertEqual(result["state"], "REVIEW")
        self.assertEqual(result["choices"], ["CENTER", "END", "LONG_EDGE"])

    def test_unknown_attachment_keeps_local_pattern_but_does_not_bind_it(self):
        spec = base("FLAP", {
            "attachment_width_cm": 12.0, "depth_cm": 8.0,
            "outer_width_cm": 9.0,
        }, attachment=None)
        result = ornament_primitives.expand(spec)
        self.assertEqual(result["verdict"],
                         "REVIEW_ORNAMENT_ATTACHMENT_REQUIRED")
        self.assertEqual(result["state"], "REVIEW")
        self.assertEqual(len(result["pattern_pieces"]), 1)
        self.assertIsNone(result["attachment_ports"][0]["target"])
        self.assertIsNone(result["seam_intents"][-1]["target"])
        self.assertEqual(result["geometry_validation"]["verdict"], "ANSWER")

    def test_image_derived_claims_cannot_be_promoted_to_observed(self):
        dimensions = {
            "length_cm": 35.0, "top_width_cm": 7.0, "tip_width_cm": 2.0,
        }
        promoted_source = base("TIE", dimensions, source=source("OBSERVED"))
        promoted_dimension = base("TIE", {
            "length_cm": {
                "value_cm": 35.0, "state": "OBSERVED",
                "basis": "pixels", "breaks_when": "another view differs",
            },
            "top_width_cm": 7.0,
            "tip_width_cm": 2.0,
        })
        self.assertEqual(
            ornament_primitives.expand(promoted_source)["verdict"],
            "UNKNOWN_ORNAMENT_AUTHORITY_ESCALATION",
        )
        self.assertEqual(
            ornament_primitives.expand(promoted_dimension)["verdict"],
            "UNKNOWN_ORNAMENT_AUTHORITY_ESCALATION",
        )

    def test_expansion_is_pure_and_digest_is_deterministic(self):
        spec = base("ROSETTE", {
            "strip_length_cm": 72.0,
            "strip_width_cm": 4.0,
            "finished_inner_length_cm": 18.0,
        })
        frozen = copy.deepcopy(spec)
        first = ornament_primitives.expand(spec)
        second = ornament_primitives.expand(spec)
        self.assertEqual(spec, frozen)
        self.assertEqual(first, second)
        self.assertEqual(first["digest"], second["digest"])

    def test_parts_ir_router_extracts_ornaments_and_never_drops_other_parts(self):
        bow = base("BOW", {
            "body_length_cm": 24.0,
            "body_width_cm": 8.0,
            "knot_length_cm": 7.0,
            "knot_width_cm": 3.0,
        })
        raw_bow = {
            "part_id": "front-bow",
            "kind": "BOW",
            "dimensions": bow["dimensions"],
            "quantity": bow["quantity"],
            "layer": bow["layer"],
            "grain_direction": bow["grain_direction"],
            "seam_allowance_cm": bow["seam_allowance_cm"],
            "attached_to": "bodice",
            "target_port_id": "neck-center",
            "visible_basis": {
                "state": "PROPOSED",
                "basis": "front image suggests a bow",
                "breaks_when": "a close view contradicts it",
            },
        }
        raw = {
            "schema": "garment.parts-ir.v1",
            "state": "PROPOSED",
            "parts": [
                {"part_id": "bodice", "kind": "BODY_SHELL"},
                raw_bow,
                {"part_id": "unknown-trim", "kind": "JEWEL_CLUSTER"},
            ],
        }
        frozen = copy.deepcopy(raw)
        result = ornament_primitives.route_parts_ir(raw)
        self.assertEqual(result["verdict"], "PROPOSED", result)
        candidate = result["candidates"][0]
        self.assertTrue(candidate["all_parts_preserved"])
        self.assertEqual(
            [part["part_id"] for part in candidate["passthrough_parts"]],
            ["bodice", "unknown-trim"],
        )
        self.assertEqual(candidate["ornament_results"][0]["verdict"],
                         "PROPOSED")
        self.assertEqual(
            candidate["ornament_results"][0]["attachment_ports"][0]["target"]
            ["target_piece_id"],
            "bodice",
        )
        self.assertEqual(raw, frozen)
        self.assertEqual(candidate["input_part_count"],
                         candidate["preserved_part_count"])
        self.assertFalse(result["provenance"]["primitive_kind_enum_modified"])


if __name__ == "__main__":
    unittest.main()
