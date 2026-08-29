#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset import garment_engineering_review
from photoloset import structure_to_pattern as compiler
from photoloset.parts_ir_completion import complete_parts_ir
from photoloset.parts_ir_topology import apply_parts_ir_topology


def _part(part_id, kind, dimensions, **semantics):
    row = {
        "part_id": part_id,
        "kind": kind,
        "layer": semantics.pop("layer", 0),
        "placement": semantics.pop("placement", "front view proposal"),
        "visible_basis": {
            "state": "PROPOSED",
            "basis": f"vision model proposed {part_id}",
            "breaks_when": f"another view rejects {part_id}",
        },
        "dimensions": dimensions,
    }
    row.update(semantics)
    return row


def _trouser_parts():
    return [
        _part(
            "body", "BODY_SHELL",
            {"height_cm": 42.0, "circumference_cm": 90.0,
             "bottom_circumference_cm": 80.0},
            garment_unit="jumpsuit", quantity=1,
        ),
        _part(
            "leg-left", "TUBE",
            {"length_cm": 100.0, "circumference_cm": 40.0},
            placement="lower left", garment_unit="jumpsuit",
            attached_to="body", side="left", shape="trouser_leg",
            quantity=1,
        ),
        _part(
            "leg-right", "TUBE",
            {"length_cm": 100.0, "circumference_cm": 40.0},
            placement="lower right", garment_unit="jumpsuit",
            attached_to="body", side="right", shape="trouser_leg",
            quantity=1,
        ),
        _part(
            "crotch", "GUSSET",
            {"length_cm": 18.0, "width_cm": 8.0},
            placement="crotch", garment_unit="jumpsuit",
            attached_to=["leg-left", "leg-right"], side="center",
            detail_role="trouser_gusset", quantity=1,
        ),
    ]


def _completed_topology():
    parts = _trouser_parts()
    completion = complete_parts_ir({
        "candidates": [
            {"candidate_id": "trouser-a", "state": "PROPOSED",
             "parts": copy.deepcopy(parts)},
            {"candidate_id": "trouser-b", "state": "PROPOSED",
             "parts": copy.deepcopy(parts)},
        ],
    })
    topology = apply_parts_ir_topology(completion)
    return completion, topology


def _assert_exact_seams(testcase, result):
    pieces = {piece["piece_id"]: piece for piece in result["pieces"]}
    testcase.assertEqual(len(pieces), len(result["pieces"]))
    testcase.assertEqual(len(result["seam_checks"]), len(result["seams"]))
    for seam, check in zip(result["seams"], result["seam_checks"]):
        testcase.assertEqual(check["operation_id"], seam["operation_id"])
        a, b = seam["a"], seam["b"]
        testcase.assertIn(a["piece_id"], pieces)
        testcase.assertIn(b["piece_id"], pieces)
        testcase.assertIn(a["edge"], pieces[a["piece_id"]]["edges"])
        testcase.assertIn(b["edge"], pieces[b["piece_id"]]["edges"])
        a_length = pieces[a["piece_id"]]["edges"][a["edge"]]["length"]
        b_length = pieces[b["piece_id"]]["edges"][b["edge"]]["length"]
        testcase.assertLessEqual(abs(a_length - b_length), 1.0e-5)
        testcase.assertLessEqual(abs(check["difference_cm"]), 1.0e-5)
        testcase.assertTrue(check["geometrically_sewable"])


class StructureToPatternTrouserBridgeTests(unittest.TestCase):
    def test_completion_topology_compile_expands_real_connected_trousers(self):
        completion, topology = _completed_topology()
        self.assertEqual(completion["verdict"], "PROPOSED")
        self.assertEqual(topology["verdict"], "PROPOSED")
        self.assertEqual(topology["candidate_count"], 2)

        for candidate in topology["candidates"]:
            with self.subTest(candidate_id=candidate["candidate_id"]):
                declared_operations = {
                    operation["operation_id"]
                    for operation in candidate["operations"]
                }
                self.assertEqual(len(declared_operations), 4)
                result = compiler.compile(
                    candidate, candidate_id=candidate["candidate_id"])
                self.assertEqual(result["verdict"], "ANSWER")
                self.assertEqual(result["candidate_state"], "PROPOSED")
                self.assertEqual(result["candidate_id"],
                                 candidate["candidate_id"])
                self.assertEqual(result["structure_digest"],
                                 candidate["structure_digest"])

                expected_pieces = {
                    "body:trouser-waist", "leg-left:front",
                    "leg-left:back", "leg-right:front",
                    "leg-right:back", "crotch",
                }
                actual_pieces = {
                    piece["piece_id"] for piece in result["pieces"]
                }
                self.assertEqual(actual_pieces, expected_pieces)
                self.assertFalse(any(
                    piece["role"] == "tube_wrap" for piece in result["pieces"]
                ))
                self.assertFalse(any(
                    seam["operation_id"].startswith("procedural-close-leg-")
                    for seam in result["seams"]
                ))
                self.assertEqual(len(result["seams"]), 15)
                roles = [seam["construction_role"]
                         for seam in result["seams"]]
                self.assertEqual(roles.count("BODY_CLOSURE"), 1)
                self.assertEqual(roles.count("WAIST_JOIN"), 4)
                self.assertEqual(roles.count("LEG_OUTSEAM"), 2)
                self.assertEqual(roles.count("LEG_INSEAM"), 2)
                self.assertEqual(roles.count("CENTRE_FRONT_RISE"), 1)
                self.assertEqual(roles.count("CENTRE_BACK_RISE"), 1)
                self.assertEqual(roles.count("CROTCH_GUSSET"), 4)
                self.assertTrue(all(
                    seam["operation_id"] not in declared_operations
                    for seam in result["seams"]
                ))

                expansion = result["candidate_specific_expansions"][0]
                self.assertEqual(expansion["kind"], "TROUSER_BLOCK_BRIDGE")
                self.assertEqual(expansion["state"], "PROPOSED")
                self.assertEqual(
                    set(expansion["consumed_structure_operations"]),
                    declared_operations,
                )
                self.assertFalse(expansion["target_wearer_measurements_used"])
                self.assertFalse(expansion["manufacturing_guarantee"])
                self.assertTrue(all(
                    piece["attributes"]["state"] == "PROPOSED"
                    for piece in result["pieces"]
                ))

                _assert_exact_seams(self, result)
                connectivity = garment_engineering_review.assembly_connectivity(
                    result)
                self.assertEqual(connectivity["verdict"], "ANSWER")
                self.assertTrue(connectivity["connected"])
                self.assertEqual(len(connectivity["components"]), 1)
                self.assertEqual(set(connectivity["components"][0]),
                                 expected_pieces)

                repeated = compiler.compile(
                    candidate, candidate_id=candidate["candidate_id"])
                self.assertEqual(repeated["digest"], result["digest"])

    def test_garment_unit_mismatch_fails_closed(self):
        _, topology = _completed_topology()
        candidate = copy.deepcopy(topology["candidates"][0])
        body = next(node for node in candidate["nodes"]
                    if node["node_id"] == "body")
        body["attributes"]["garment_unit"] = "other-unit"
        result = compiler.compile(candidate)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_TROUSER_BRIDGE_GARMENT_UNIT")

    def test_standalone_trousers_compile_without_a_fake_body_shell(self):
        parts = copy.deepcopy(_trouser_parts()[1:])
        for leg in parts[:2]:
            leg.pop("attached_to")
            leg["garment_unit"] = "separate-trousers"
        parts[2]["garment_unit"] = "separate-trousers"
        completed = complete_parts_ir({
            "candidates": [
                {"candidate_id": "standalone-a", "state": "PROPOSED",
                 "parts": copy.deepcopy(parts)},
                {"candidate_id": "standalone-b", "state": "PROPOSED",
                 "parts": copy.deepcopy(parts)},
            ],
        })
        topology = apply_parts_ir_topology(completed)
        self.assertEqual(topology["verdict"], "PROPOSED")
        for candidate in topology["candidates"]:
            result = compiler.compile(candidate)
            self.assertEqual(result["verdict"], "ANSWER")
            self.assertFalse(any(piece["primitive_kind"] == "BODY_SHELL"
                                 for piece in result["pieces"]))
            self.assertEqual(len(result["pieces"]), 5)
            self.assertEqual(len(result["seams"]), 10)
            self.assertFalse(any(seam.get("construction_role") == "WAIST_JOIN"
                                 for seam in result["seams"]))
            self.assertTrue(all(check["geometrically_sewable"]
                                for check in result["seam_checks"]))
            connectivity = garment_engineering_review.assembly_connectivity(result)
            self.assertEqual(connectivity["verdict"], "ANSWER")
            self.assertEqual(len(connectivity["components"]), 1)
            expansion = result["candidate_specific_expansions"][0]
            self.assertIn("standalone open waist", expansion["method"])

    def test_two_layered_trouser_units_compile_to_independent_cuttable_blocks(self):
        parts = []
        for unit, layer, circumference in (
                ("outer-pants", 1, 44.0),
                ("legging-underlayer", 0, 38.0)):
            left_id, right_id = f"{unit}-left", f"{unit}-right"
            parts.extend([
                _part(
                    left_id, "TUBE",
                    {"length_cm": 90.0,
                     "circumference_cm": circumference},
                    layer=layer, placement="left leg", garment_unit=unit,
                    side="left", shape="trouser_leg",
                    detail_role="trouser_leg", quantity=1),
                _part(
                    right_id, "TUBE",
                    {"length_cm": 90.0,
                     "circumference_cm": circumference},
                    layer=layer, placement="right leg", garment_unit=unit,
                    side="right", shape="trouser_leg",
                    detail_role="trouser_leg", quantity=1),
                _part(
                    f"{unit}-gusset", "GUSSET",
                    {"length_cm": 16.0, "width_cm": 8.0},
                    layer=layer, placement="centre crotch",
                    garment_unit=unit, attached_to=[left_id, right_id],
                    side="center", shape="trousers",
                    detail_role="trouser_gusset", quantity=1),
            ])
        completed = complete_parts_ir({
            "candidates": [
                {"candidate_id": "layered-a", "state": "PROPOSED",
                 "parts": copy.deepcopy(parts)},
                {"candidate_id": "layered-b", "state": "PROPOSED",
                 "parts": copy.deepcopy(parts)},
            ],
        })
        topology = apply_parts_ir_topology(completed)
        self.assertEqual("PROPOSED", topology["verdict"])
        for candidate in topology["candidates"]:
            result = compiler.compile(candidate)
            self.assertEqual("ANSWER", result["verdict"], result)
            self.assertEqual(10, len(result["pieces"]))
            self.assertEqual(20, len(result["seams"]))
            self.assertEqual(20, len({
                seam["operation_id"] for seam in result["seams"]}))
            by_unit = {
                unit: [piece for piece in result["pieces"]
                       if piece.get("attributes", {}).get("garment_unit")
                       == unit]
                for unit in ("outer-pants", "legging-underlayer")
            }
            self.assertTrue(all(piece["layer"] == 1
                                for piece in by_unit["outer-pants"]))
            self.assertTrue(all(piece["layer"] == 0
                                for piece in by_unit["legging-underlayer"]))
            expansions = result["candidate_specific_expansions"]
            self.assertEqual("MULTI_TROUSER_BLOCK_BRIDGE",
                             expansions[0]["kind"])
            self.assertEqual(2, expansions[0]["physical_group_count"])
            self.assertEqual(2, sum(
                expansion["kind"] == "TROUSER_BLOCK_BRIDGE"
                for expansion in expansions))
            connectivity = garment_engineering_review.assembly_connectivity(
                result)
            self.assertEqual("ANSWER", connectivity["verdict"])
            self.assertEqual(2, len(connectivity["components"]))
            _assert_exact_seams(self, result)

    def test_sleeved_jumpsuit_combines_bodice_and_trouser_bridges(self):
        parts = _trouser_parts()
        parts.append(_part(
            "sleeve", "SLEEVE",
            {"length_cm": 58.0, "upper_circumference_cm": 34.0,
             "cuff_circumference_cm": 20.0},
            placement="arms", garment_unit="jumpsuit", attached_to="body",
            side="bilateral", shape="set_in", quantity=2,
        ))
        completed = complete_parts_ir({
            "candidates": [
                {"candidate_id": "jumpsuit-a", "state": "PROPOSED",
                 "parts": copy.deepcopy(parts)},
                {"candidate_id": "jumpsuit-b", "state": "PROPOSED",
                 "parts": copy.deepcopy(parts)},
            ],
        })
        topology = apply_parts_ir_topology(completed)
        self.assertEqual(topology["verdict"], "PROPOSED")
        for candidate in topology["candidates"]:
            result = compiler.compile(candidate)
            self.assertEqual(result["verdict"], "ANSWER")
            roles = {piece["role"] for piece in result["pieces"]}
            self.assertIn("front_bodice", roles)
            self.assertIn("back_bodice", roles)
            self.assertIn("set_in_sleeve_left", roles)
            self.assertIn("left_front_leg_panel", roles)
            self.assertFalse(any(piece["role"] == "body_wrap"
                                 for piece in result["pieces"]))
            self.assertTrue(all(check["geometrically_sewable"]
                                for check in result["seam_checks"]))
            self.assertEqual(
                garment_engineering_review.assembly_connectivity(result)["verdict"],
                "ANSWER")
            kinds = {row["kind"] for row in result["candidate_specific_expansions"]}
            self.assertEqual(kinds, {
                "BODICE_SET_IN_SLEEVE_BRIDGE", "TROUSER_BLOCK_BRIDGE",
                "COMBINED_BODICE_SLEEVE_TROUSER_BRIDGE",
            })

    def test_missing_leg_fails_with_typed_refusal(self):
        _, topology = _completed_topology()
        candidate = copy.deepcopy(topology["candidates"][0])
        candidate["nodes"] = [
            node for node in candidate["nodes"]
            if node["node_id"] != "leg-right"
        ]
        candidate["operations"] = [
            operation for operation in candidate["operations"]
            if operation["source"]["node_id"] != "leg-right"
            and operation.get("target", {}).get("node_id") != "leg-right"
        ]
        result = compiler.compile(candidate)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_TROUSER_TOPOLOGY_CARDINALITY")

    def test_missing_or_ambiguous_primitive_operation_fails_closed(self):
        _, topology = _completed_topology()
        missing = copy.deepcopy(topology["candidates"][0])
        missing["operations"] = missing["operations"][:-1]
        result = compiler.compile(missing)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_TROUSER_BRIDGE_JOIN_UNRESOLVED")

        ambiguous = copy.deepcopy(topology["candidates"][0])
        left = next(node for node in ambiguous["nodes"]
                    if node["node_id"] == "leg-left")
        ambiguous["operations"].append({
            "operation_id": "ambiguous-leg-mirror",
            "kind": "MIRROR",
            "source": {
                "node_id": "leg-left",
                "port_id": left["ports"][0]["port_id"],
            },
            "parameters": {},
            "prerequisites": [],
        })
        result = compiler.compile(ambiguous)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_TROUSER_BRIDGE_OPERATION_CONFLICT")
        self.assertEqual(result["operation_id"], "ambiguous-leg-mirror")

    def test_untyped_generic_tube_keeps_one_legacy_closure(self):
        structure = {
            "schema": "garment.structure.v1",
            "nodes": [{
                "node_id": "generic-tube",
                "kind": "TUBE",
                "dimensions": {"length_cm": 60.0,
                               "circumference_cm": 80.0},
                "attributes": {"garment_unit": "separate"},
                "ports": [],
            }],
            "operations": [],
        }
        result = compiler.compile(structure)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual([piece["role"] for piece in result["pieces"]],
                         ["tube_wrap"])
        closures = [seam for seam in result["seams"]
                    if seam["operation_id"].startswith("procedural-close-")]
        self.assertEqual(len(closures), 1)
        self.assertEqual(result["candidate_specific_expansions"], [])
        _assert_exact_seams(self, result)

    def test_untyped_decorative_gusset_does_not_start_trouser_bridge(self):
        structure = {
            "schema": "garment.structure.v1",
            "nodes": [{
                "node_id": "underarm-gusset",
                "kind": "GUSSET",
                "dimensions": {"length_cm": 12.0, "width_cm": 7.0},
                "attributes": {"garment_unit": "shirt",
                               "detail_role": "underarm_reinforcement"},
                "ports": [],
            }],
            "operations": [],
        }
        result = compiler.compile(structure)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual([piece["piece_id"] for piece in result["pieces"]],
                         ["underarm-gusset"])
        self.assertEqual(result["candidate_specific_expansions"], [])


if __name__ == "__main__":
    unittest.main()
