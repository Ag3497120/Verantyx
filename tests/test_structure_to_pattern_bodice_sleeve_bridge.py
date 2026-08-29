#!/usr/bin/env python3
import copy
import unittest

from photoloset import garment_engineering_review
from photoloset import pattern_manufacturing_bundle
from photoloset import structure_to_pattern as compiler


def structure():
    return {
        "schema": "garment.structure.v1",
        "nodes": [
            {
                "node_id": "shell",
                "kind": "BODY_SHELL",
                "dimensions": {
                    "height_cm": 42.0,
                    "circumference_cm": 96.0,
                    "bottom_circumference_cm": 80.0,
                },
                "attributes": {
                    "garment_unit": "dress",
                    "proposal_only": True,
                    "back_design": "unobserved_center_back_opening",
                },
                "ports": [{
                    "port_id": "waist",
                    "length_cm": 80.0,
                    "interface": "waist",
                    "role": "loop",
                }],
            },
            {
                "node_id": "sleeves",
                "kind": "SLEEVE",
                "dimensions": {
                    "length_cm": 58.0,
                    "upper_circumference_cm": 34.0,
                    "cuff_circumference_cm": 20.0,
                },
                "attributes": {"bilateral": True, "proposal_only": True},
            },
        ],
        "operations": [],
    }


def multi_sleeve_structure():
    spec = structure()
    root = spec["nodes"][1]
    root["node_id"] = "upper-sleeve"
    root["attributes"].update({
        "side": "bilateral", "quantity": 2,
        "attached_to": "shell", "garment_unit": "dress",
    })
    root["ports"] = [
        {"port_id": "cuff-to-lower", "length_cm": 20.0,
         "interface": "sleeve-extension", "role": "edge"},
        {"port_id": "layer-from-outer", "length_cm": 1.0,
         "interface": "sleeve-layer-anchor", "role": "point"},
    ]
    spec["nodes"].extend([
        {
            "node_id": "lower-sleeve",
            "kind": "SLEEVE",
            "dimensions": {
                "length_cm": 28.0,
                "upper_circumference_cm": 20.0,
                "cuff_circumference_cm": 16.0,
            },
            "attributes": {
                "side": "bilateral", "quantity": 2,
                "attached_to": "upper-sleeve", "garment_unit": "dress",
                "placement": "lower sleeve extension",
            },
            "ports": [{
                "port_id": "upper-to-upper-sleeve", "length_cm": 20.0,
                "interface": "sleeve-extension", "role": "edge",
            }],
        },
        {
            "node_id": "outer-sleeve",
            "kind": "SLEEVE",
            "layer": 2,
            "dimensions": {
                "length_cm": 48.0,
                "upper_circumference_cm": 40.0,
                "cuff_circumference_cm": 28.0,
            },
            "attributes": {
                "side": "bilateral", "quantity": 2,
                "attached_to": "upper-sleeve", "garment_unit": "dress",
                "detail_role": "oversleeve",
            },
            "ports": [{
                "port_id": "layer-to-upper-sleeve", "length_cm": 1.0,
                "interface": "sleeve-layer-anchor", "role": "point",
            }],
        },
    ])
    spec["operations"] = [
        {
            "operation_id": "join-lower-to-upper",
            "kind": "JOIN",
            "source": {"node_id": "lower-sleeve",
                       "port_id": "upper-to-upper-sleeve"},
            "target": {"node_id": "upper-sleeve",
                       "port_id": "cuff-to-lower"},
            "parameters": {},
        },
        {
            "operation_id": "layer-outer-on-upper",
            "kind": "LAYER",
            "source": {"node_id": "outer-sleeve",
                       "port_id": "layer-to-upper-sleeve"},
            "target": {"node_id": "upper-sleeve",
                       "port_id": "layer-from-outer"},
            "parameters": {"seam_join_created": False},
        },
    ]
    return spec


class BodiceSleeveBridgeTests(unittest.TestCase):
    def test_expands_to_connected_front_back_and_bilateral_sleeves(self):
        result = compiler.compile(structure(), candidate_id="front-only-a")
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual([piece["piece_id"] for piece in result["pieces"]], [
            "shell:front", "shell:back", "sleeves:left", "sleeves:right",
        ])
        self.assertEqual([piece["role"] for piece in result["pieces"]], [
            "front_bodice", "back_bodice",
            "set_in_sleeve_left", "set_in_sleeve_right",
        ])
        self.assertTrue(all(piece["attributes"]["garment_unit"] == "dress"
                            for piece in result["pieces"]))

        connectivity = garment_engineering_review.assembly_connectivity(result)
        self.assertEqual(connectivity["verdict"], "ANSWER")
        self.assertEqual(connectivity["components"], [[
            "shell:back", "shell:front", "sleeves:left", "sleeves:right",
        ]])
        roles = {row["construction_role"] for row in result["seams"]}
        self.assertEqual(roles, {
            "SHOULDER", "SIDE_SEAM", "SLEEVE_UNDERARM", "SET_IN_SLEEVE",
        })
        self.assertEqual(len([row for row in result["seams"]
                              if row["construction_role"] == "SET_IN_SLEEVE"]),
                         32)
        self.assertTrue(all(check["geometrically_sewable"]
                            for check in result["seam_checks"]))
        self.assertTrue(all(
            endpoint["edge"].startswith("e")
            and endpoint["edge"] in next(
                piece for piece in result["pieces"]
                if piece["piece_id"] == endpoint["piece_id"])["edges"]
            for seam in result["seams"]
            for endpoint in (seam["a"], seam["b"])))
        self.assertFalse(result["manufacturing_ready"])

        manufacturing = pattern_manufacturing_bundle.build(
            result, allow_proposed_default=True)
        self.assertEqual(manufacturing["verdict"], "ANSWER")
        self.assertTrue(manufacturing["manufacturing_preview_ready"])
        self.assertFalse(manufacturing["manufacturing_ready"])

    def test_cap_armhole_balance_is_explicit_and_not_a_guarantee(self):
        result = compiler.compile(structure())
        self.assertEqual(len(result["sleeve_balance_checks"]), 2)
        for check in result["sleeve_balance_checks"]:
            self.assertGreater(check["difference_cm"], 0.0)
            self.assertLess(abs(check["difference_from_intended_ease_cm"]), 0.25)
            self.assertEqual(check["state"], "PROPOSED")
            self.assertFalse(check["manufacturing_guarantee"])

        expansion = result["candidate_specific_expansions"][0]
        self.assertEqual(expansion["method"],
                         "garment_parts.draft_bodice + garment_parts.draft_sleeve")
        self.assertEqual(expansion["armhole_segmentation"]["segments_per_half"], 8)
        self.assertFalse(expansion["target_wearer_measurements_used"])
        self.assertFalse(expansion["manufacturing_guarantee"])
        self.assertTrue(all(
            row["state"] == "PROPOSED_PREVIEW_MANNEQUIN"
            for row in expansion["preview_dimensions"].values()))

    def test_human_candidate_approval_does_not_promote_preview_dimensions(self):
        result = compiler.compile(
            structure(), candidate_state="APPROVED", candidate_id="approved-a",
            approval={"by": "Reviewer", "digest": "candidate-digest"})
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["candidate_state"], "APPROVED")
        expansion = result["candidate_specific_expansions"][0]
        self.assertEqual(expansion["state"], "PROPOSED")
        self.assertEqual(expansion["candidate_state_does_not_promote_dimensions"],
                         "APPROVED")
        self.assertTrue(all(
            piece["attributes"]["target_wearer_measurement"] is False
            for piece in result["pieces"]))

    def test_ambiguous_geometric_operation_on_expanded_node_is_typed_refusal(self):
        for kind in ("SPLIT", "MIRROR", "ASYMMETRY", "CUTOUT",
                     "PLEAT", "DART", "FOLD", "GATHER"):
            with self.subTest(kind=kind):
                spec = structure()
                operation = {
                    "operation_id": "ambiguous-edit",
                    "kind": kind,
                    "source": {"node_id": "shell", "port_id": "waist"},
                    "parameters": {},
                }
                if kind == "GATHER":
                    spec["nodes"].append({
                        "node_id": "target", "kind": "BAND",
                        "dimensions": {"length_cm": 40.0, "width_cm": 2.0},
                        "ports": [{"port_id": "join", "length_cm": 40.0,
                                   "interface": "waist"}],
                    })
                    operation["target"] = {
                        "node_id": "target", "port_id": "join"}
                    operation["parameters"] = {"ratio": 2.0}
                spec["operations"] = [operation]
                result = compiler.compile(spec)
                self.assertEqual(
                    result["verdict"],
                    "UNKNOWN_BODICE_SLEEVE_BRIDGE_OPERATION_CONFLICT")
                self.assertEqual(result["operation_kind"], kind)

    def test_detached_and_cross_unit_sleeves_fail_closed(self):
        detached = structure()
        detached["nodes"][1]["attributes"]["shape"] = "detached"
        self.assertEqual(
            compiler.compile(detached)["verdict"],
            "UNKNOWN_BODICE_SLEEVE_BRIDGE_DETACHED")

        other_unit = structure()
        other_unit["nodes"][1]["attributes"]["garment_unit"] = "accessory"
        self.assertEqual(
            compiler.compile(other_unit)["verdict"],
            "UNKNOWN_BODICE_SLEEVE_GARMENT_UNIT_MISMATCH")

    def test_unrelated_cutout_keeps_its_nested_contour_lineage(self):
        spec = structure()
        spec["nodes"].append({
            "node_id": "badge", "kind": "BAND",
            "dimensions": {"length_cm": 20.0, "width_cm": 20.0},
            "ports": [{"port_id": "surface", "length_cm": 20.0,
                       "interface": "decoration"}],
        })
        spec["operations"] = [{
            "operation_id": "badge-window", "kind": "CUTOUT",
            "source": {"node_id": "badge", "port_id": "surface"},
            "parameters": {
                "contour_id": "window",
                "closed_polygon": [[-3.0, 7.0], [3.0, 7.0],
                                   [3.0, 13.0], [-3.0, 13.0]],
                "minimum_clearance_cm": 1.0,
                "source_front_boundary_digest": "front-boundary-a",
            },
        }]
        result = compiler.compile(spec)
        self.assertEqual(result["verdict"], "ANSWER")
        record = result["geometry_operations"][0]
        self.assertEqual(record["operation_id"], "badge-window")
        self.assertEqual(record["source_front_boundary_digest"],
                         "front-boundary-a")
        self.assertEqual(record["source_front_boundary_digest_state"],
                         "PROPOSED_LINEAGE_ONLY")
        self.assertFalse(record["source_front_boundary_semantics_observed"])
        self.assertEqual(len(record["contour_edge_lineage"]), 4)

    def test_whole_circumference_gather_defers_bridge_without_hiding_it(self):
        spec = structure()
        spec["nodes"].append({
            "node_id": "ruffle", "kind": "BAND",
            "dimensions": {"length_cm": 120.0, "width_cm": 8.0},
            "ports": [{"port_id": "join", "length_cm": 120.0,
                       "interface": "waist"}],
        })
        spec["operations"] = [{
            "operation_id": "gather-around-waist", "kind": "GATHER",
            "source": {"node_id": "ruffle", "port_id": "join"},
            "target": {"node_id": "shell", "port_id": "waist"},
            "parameters": {"ratio": 1.5},
        }]
        result = compiler.compile(spec)
        self.assertEqual(result["verdict"], "ANSWER")
        review = result["candidate_specific_expansions"][0]
        self.assertEqual(review["state"], "REVIEW_DEFERRED")
        self.assertEqual(review["blocking_operations"],
                         ["gather-around-waist"])
        self.assertTrue(review["legacy_wrap_compiler_used"])
        self.assertEqual(review["generated_pieces"], [])
        self.assertFalse(review["manufacturing_guarantee"])

    def test_multi_sleeve_join_and_layer_expand_to_matching_side_instances(self):
        result = compiler.compile(multi_sleeve_structure())
        self.assertEqual(result["verdict"], "ANSWER", result)
        self.assertEqual([piece["piece_id"] for piece in result["pieces"]], [
            "shell:front", "shell:back",
            "upper-sleeve:left", "upper-sleeve:right",
            "lower-sleeve:left", "lower-sleeve:right",
            "outer-sleeve:left", "outer-sleeve:right",
        ])
        sleeve_pieces = [piece for piece in result["pieces"]
                         if piece["primitive_kind"] == "SLEEVE"]
        self.assertTrue(all(piece["cut_count"] == 1
                            for piece in sleeve_pieces))
        self.assertEqual(
            {(piece["source_node_id"], piece["attributes"]["derived_side"])
             for piece in sleeve_pieces},
            {(node_id, side)
             for node_id in ("upper-sleeve", "lower-sleeve", "outer-sleeve")
             for side in ("left", "right")})

        joins = [row for row in result["seams"]
                 if row.get("source_operation_id") == "join-lower-to-upper"]
        self.assertEqual({row["relation_side"] for row in joins},
                         {"left", "right"})
        self.assertEqual(len(joins), 2)
        for row in joins:
            side = row["relation_side"]
            self.assertEqual(row["a"]["piece_id"], f"lower-sleeve:{side}")
            self.assertEqual(row["b"]["piece_id"], f"upper-sleeve:{side}")
            self.assertEqual(row["pattern_lineage"]["source"]["piece_id"],
                             row["a"]["piece_id"])
            self.assertEqual(row["pattern_lineage"]["target"]["piece_id"],
                             row["b"]["piece_id"])
            self.assertTrue(next(piece for piece in result["pieces"]
                                 if piece["piece_id"] == row["a"]["piece_id"])[
                                     "edges"].get(row["a"]["edge"]))
            self.assertTrue(next(piece for piece in result["pieces"]
                                 if piece["piece_id"] == row["b"]["piece_id"])[
                                     "edges"].get(row["b"]["edge"]))
            lower_piece = next(piece for piece in result["pieces"]
                               if piece["piece_id"] == row["a"]["piece_id"])
            upper_piece = next(piece for piece in result["pieces"]
                               if piece["piece_id"] == row["b"]["piece_id"])
            self.assertEqual([row["a"]["edge"]],
                             lower_piece["boundary_edge_groups"]["upper"])
            self.assertEqual([row["b"]["edge"]],
                             upper_piece["boundary_edge_groups"]["cuff"])
            self.assertAlmostEqual(
                lower_piece["edges"][row["a"]["edge"]]["length"], 20.0)
            self.assertAlmostEqual(
                upper_piece["edges"][row["b"]["edge"]]["length"], 20.0)
        join_checks = [row for row in result["seam_checks"]
                       if row["operation_id"].startswith(
                           "join-lower-to-upper:")]
        self.assertEqual(len(join_checks), 2)
        self.assertTrue(all(row["geometrically_sewable"]
                            for row in join_checks))

        layers = [row for row in result["layers"]
                  if row.get("source_operation_id") == "layer-outer-on-upper"]
        self.assertEqual({row["relation_side"] for row in layers},
                         {"left", "right"})
        self.assertEqual(len(layers), 2)
        for row in layers:
            side = row["relation_side"]
            self.assertEqual(row["a"]["piece_id"], f"outer-sleeve:{side}")
            self.assertEqual(row["b"]["piece_id"], f"upper-sleeve:{side}")
            self.assertFalse(row["seam_join_created"])

        expansion = result["candidate_specific_expansions"][0]
        relation_lineage = expansion["sleeve_relation_lineage"]
        self.assertEqual(len(relation_lineage), 4)
        self.assertEqual(
            {(row["source_operation_id"], row["side"])
             for row in relation_lineage},
            {("join-lower-to-upper", "left"),
             ("join-lower-to-upper", "right"),
             ("layer-outer-on-upper", "left"),
             ("layer-outer-on-upper", "right")})

    def test_unilateral_descendant_relation_stays_on_declared_side(self):
        spec = multi_sleeve_structure()
        spec["nodes"] = [node for node in spec["nodes"]
                         if node["node_id"] != "outer-sleeve"]
        spec["operations"] = [spec["operations"][0]]
        root = next(node for node in spec["nodes"]
                    if node["node_id"] == "upper-sleeve")
        root["ports"] = [root["ports"][0]]
        lower = next(node for node in spec["nodes"]
                     if node["node_id"] == "lower-sleeve")
        lower["attributes"].update({"side": "left", "quantity": 1})

        result = compiler.compile(spec)
        self.assertEqual(result["verdict"], "ANSWER", result)
        self.assertIn("lower-sleeve:left",
                      [piece["piece_id"] for piece in result["pieces"]])
        self.assertNotIn("lower-sleeve:right",
                         [piece["piece_id"] for piece in result["pieces"]])
        rows = [row for row in result["seams"]
                if row.get("source_operation_id") == "join-lower-to-upper"]
        self.assertEqual([(row["relation_side"], row["a"]["piece_id"],
                           row["b"]["piece_id"]) for row in rows], [
            ("left", "lower-sleeve:left", "upper-sleeve:left")])

    def test_descendant_side_absent_from_parent_is_refused(self):
        spec = multi_sleeve_structure()
        spec["nodes"] = [node for node in spec["nodes"]
                         if node["node_id"] != "outer-sleeve"]
        spec["operations"] = [spec["operations"][0]]
        root = next(node for node in spec["nodes"]
                    if node["node_id"] == "upper-sleeve")
        root["attributes"].update({"side": "left", "quantity": 1,
                                   "bilateral": False})
        root["ports"] = [root["ports"][0]]

        result = compiler.compile(spec)
        self.assertEqual(
            result["verdict"],
            "UNKNOWN_BODICE_SLEEVE_RELATION_SIDE_MISMATCH")
        self.assertEqual(result["missing_sides"], ["right"])

    def test_multiple_root_sleeves_are_not_silently_selected(self):
        spec = structure()
        extra = copy.deepcopy(spec["nodes"][1])
        extra["node_id"] = "second-root"
        spec["nodes"].append(extra)
        result = compiler.compile(spec)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_BODICE_SLEEVE_BRIDGE_CARDINALITY")
        self.assertEqual(result["root_sleeve_nodes"],
                         ["second-root", "sleeves"])

    def test_single_quantity_without_left_or_right_is_ambiguous(self):
        spec = structure()
        spec["nodes"][1]["attributes"] = {
            "quantity": 1, "proposal_only": True,
        }
        result = compiler.compile(spec)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_BODICE_SLEEVE_SIDE_AMBIGUOUS")
        self.assertEqual(result["node_id"], "sleeves")


if __name__ == "__main__":
    unittest.main()
