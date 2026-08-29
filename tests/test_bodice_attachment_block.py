#!/usr/bin/env python3
import copy
import unittest

from photoloset import bodice_attachment_block
from photoloset import structure_to_pattern


def base_graph():
    return {
        "schema": "garment.structure.v1",
        "nodes": [
            {
                "node_id": "body", "kind": "BODY_SHELL",
                "dimensions": {"height_cm": 42.0, "circumference_cm": 80.0,
                               "neck_circumference_cm": 38.0},
                "attributes": {"garment_unit": "dress"},
                "ports": [
                    {"port_id": "waist", "length_cm": 80.0,
                     "interface": "waist"},
                    {"port_id": "neck", "length_cm": 38.0,
                     "interface": "neck"},
                ],
            },
            {
                "node_id": "sleeve", "kind": "SLEEVE",
                "dimensions": {"length_cm": 58.0,
                               "upper_circumference_cm": 34.0,
                               "cuff_circumference_cm": 20.0},
                "attributes": {"garment_unit": "dress", "side": "bilateral"},
                "ports": [],
            },
            {
                "node_id": "skirt", "kind": "FLARE",
                "dimensions": {"height_cm": 65.0,
                               "top_circumference_cm": 80.0,
                               "bottom_circumference_cm": 140.0},
                "attributes": {"garment_unit": "dress"},
                "ports": [{"port_id": "waist", "length_cm": 80.0,
                           "interface": "waist"}],
            },
            {
                "node_id": "collar", "kind": "COLLAR",
                "dimensions": {"length_cm": 38.0, "width_cm": 7.0},
                "attributes": {"garment_unit": "dress"},
                "ports": [{"port_id": "neck", "length_cm": 38.0,
                           "interface": "neck"}],
            },
        ],
        "operations": [
            {"operation_id": "join-waist", "kind": "JOIN",
             "source": {"node_id": "skirt", "port_id": "waist"},
             "target": {"node_id": "body", "port_id": "waist"}},
            {"operation_id": "join-neck", "kind": "JOIN",
             "source": {"node_id": "collar", "port_id": "neck"},
             "target": {"node_id": "body", "port_id": "neck"}},
        ],
    }


def body_bridge(graph):
    body = graph["nodes"][0]
    sleeve = graph["nodes"][1]
    bridge, error = structure_to_pattern._bodice_sleeve_bridge(
        body, sleeve, candidate_state="PROPOSED")
    assert error is None and bridge is not None
    return bridge


class BodiceAttachmentBlockTests(unittest.TestCase):
    def test_waist_and_neck_loops_expand_to_real_equal_edges(self):
        graph = base_graph()
        result = bodice_attachment_block.expand(graph, body_bridge(graph))
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(set(result["consumed_operation_ids"]),
                         {"join-waist", "join-neck"})
        self.assertEqual(len(result["pieces_by_node"]["skirt"]), 4)
        self.assertEqual(len(result["pieces_by_node"]["collar"]), 4)
        self.assertEqual(len(result["expansions"]), 2)

        body_pieces = body_bridge(graph)["pieces_by_node"]["body"]
        all_pieces = {piece["piece_id"]: piece for piece in body_pieces}
        for pieces in result["pieces_by_node"].values():
            all_pieces.update({piece["piece_id"]: piece for piece in pieces})
        for seam in result["seams"]:
            a = all_pieces[seam["a"]["piece_id"]]["edges"][seam["a"]["edge"]]["length"]
            b = all_pieces[seam["b"]["piece_id"]]["edges"][seam["b"]["edge"]]["length"]
            self.assertAlmostEqual(a, b, places=5, msg=seam["operation_id"])

        collar = next(row for row in result["expansions"]
                      if row["kind"] == "BODICE_NECK_ATTACHMENT")
        self.assertEqual(collar["centre_back_opening"]["state"], "PROPOSED")
        self.assertTrue(collar["adjustments"][0]["requires_human_approval"])
        self.assertFalse(result["authority"]["manufacturing_validated"])

    def test_input_is_unchanged_and_output_is_deterministic(self):
        graph = base_graph()
        bridge = body_bridge(graph)
        graph_before, bridge_before = copy.deepcopy(graph), copy.deepcopy(bridge)
        first = bodice_attachment_block.expand(graph, bridge)
        second = bodice_attachment_block.expand(graph, bridge)
        self.assertEqual(first, second)
        self.assertEqual(graph, graph_before)
        self.assertEqual(bridge, bridge_before)

    def test_ruffle_is_segmented_with_the_lower_hem(self):
        graph = base_graph()
        graph["nodes"].append({
            "node_id": "ruffle", "kind": "BAND",
            "dimensions": {"length_cm": 210.0, "width_cm": 10.0},
            "attributes": {"garment_unit": "dress", "detail_role": "ruffle"},
            "ports": [{"port_id": "gather", "length_cm": 210.0,
                       "interface": "gather-skirt"}],
        })
        graph["nodes"][2]["ports"].append({
            "port_id": "hem-gather", "length_cm": 140.0,
            "interface": "gather-skirt",
        })
        graph["operations"].append({
            "operation_id": "gather-hem", "kind": "GATHER",
            "source": {"node_id": "ruffle", "port_id": "gather"},
            "target": {"node_id": "skirt", "port_id": "hem-gather"},
            "parameters": {"ratio": 1.5},
        })
        result = bodice_attachment_block.expand(graph, body_bridge(graph))
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(len(result["pieces_by_node"]["ruffle"]), 4)
        gathers = [row for row in result["seams"] if row["kind"] == "GATHER"]
        self.assertEqual(len(gathers), 4)
        all_pieces = {
            piece["piece_id"]: piece
            for pieces in result["pieces_by_node"].values()
            for piece in pieces
        }
        for seam in gathers:
            a = all_pieces[seam["a"]["piece_id"]]["edges"][seam["a"]["edge"]]["length"]
            b = all_pieces[seam["b"]["piece_id"]]["edges"][seam["b"]["edge"]]["length"]
            self.assertAlmostEqual(a / b, 1.5, places=5)
        record = next(row for row in result["expansions"]
                      if row["kind"] == "SEGMENTED_GATHER_ATTACHMENT")
        self.assertFalse(record["adjustments"][0]["requires_human_approval"])

    def test_mismatched_units_and_duplicate_waist_children_fail_closed(self):
        graph = base_graph()
        graph["nodes"][2]["attributes"]["garment_unit"] = "separate"
        result = bodice_attachment_block.expand(graph, body_bridge(graph))
        self.assertEqual(result["verdict"],
                         "UNKNOWN_BODICE_ATTACHMENT_GARMENT_UNIT")

        graph = base_graph()
        second_skirt = copy.deepcopy(graph["nodes"][2])
        second_skirt["node_id"] = "skirt-2"
        graph["nodes"].append(second_skirt)
        graph["operations"].append({
            "operation_id": "join-waist-2", "kind": "JOIN",
            "source": {"node_id": "skirt-2", "port_id": "waist"},
            "target": {"node_id": "body", "port_id": "waist"},
        })
        result = bodice_attachment_block.expand(graph, body_bridge(graph))
        self.assertEqual(result["verdict"],
                         "UNKNOWN_BODICE_ATTACHMENT_MULTIPLE_CHILDREN")


if __name__ == "__main__":
    unittest.main()
