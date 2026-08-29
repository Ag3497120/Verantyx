# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import unittest

from photoloset import mcp


TOOL_NAME = "garment_construction_route"


def _node(*, state: str = "PROPOSED") -> dict:
    return {
        "node_id": "front-panel",
        "primitive_kind": "BODY_SHELL",
        "layer": 0,
        "state": state,
        "dimensions_cm": {"width": 48, "length": 72},
        "construction": {
            "method": "SEWN",
            "cut_geometry": "RECTANGLE",
            "fit": "LOOSE",
            "shaping": [],
            "knit": {},
        },
    }


def _graph(*, name: str = "display name",
           source_kind: str = "MODEL_PROPOSAL",
           node_state: str = "PROPOSED",
           rear_state: str = "UNKNOWN") -> dict:
    return {
        "schema": "garment.instance-graph.v1",
        "graph_id": "mcp-construction-route-fixture",
        "garment_name": name,
        "source": {"kind": source_kind, "front_only": True},
        "nodes": [_node(state=node_state)],
        "relations": [],
        "rear": {"state": rear_state},
    }


def _call(value) -> dict:
    json_text = value if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False, allow_nan=False)
    response = mcp.handle({
        "method": "tools/call",
        "params": {
            "name": TOOL_NAME,
            "arguments": {"json_text": json_text},
        },
    })
    return json.loads(response["content"][0]["text"])


class ConstructionRegimeMCPTests(unittest.TestCase):
    maxDiff = None

    def test_tool_is_listed_with_one_bounded_json_text_input(self):
        listing = mcp.handle({"method": "tools/list"})
        tools = {row["name"]: row for row in listing["tools"]}

        self.assertIn(TOOL_NAME, tools)
        self.assertEqual(tools[TOOL_NAME]["inputSchema"], {
            "type": "object",
            "properties": {
                "json_text": {"type": "string", "default": ""},
            },
            "required": [],
        })

    def test_bad_json_and_non_object_are_typed_refusals(self):
        malformed = _call("{not-json")
        non_object = _call(["garment.instance-graph.v1"])

        self.assertEqual("UNKNOWN_BAD_ARGUMENTS", malformed["verdict"])
        self.assertIn("garment.instance-graph.v1", malformed["why"])
        self.assertEqual("UNKNOWN_BAD_ARGUMENTS", non_object["verdict"])
        self.assertIn("must be", non_object["why"])

    def test_model_claims_are_bounded_and_cannot_choose_the_regime(self):
        request = _graph(node_state="OBSERVED", rear_state="OBSERVED")
        request["garment_name"] = "knitted dress"
        request["proposed_construction_regime"] = "KNITTED"
        request["manufacturing_ready"] = True
        request["manufacturing_certified"] = True

        result = _call(request)

        self.assertEqual("ANSWER", result["verdict"])
        self.assertEqual(
            "SEWN_RECTILINEAR", result["construction_regime"]["value"])
        self.assertEqual(
            "PROPOSED", result["construction_regime"]["state"])
        self.assertEqual(
            "CONTESTED", result["construction_regime"]["proposal_alignment"])
        self.assertEqual(
            "PROPOSED",
            result["manufacturing_representation"]["rectangles"][0]["state"],
        )
        self.assertEqual("PROPOSED", result["authority"]["rear"]["state"])
        self.assertFalse(result["authority"]["rear"]["observed"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])
        self.assertEqual([], result["fact_promotions"])

    def test_observed_front_and_unknown_rear_keep_separate_authority(self):
        result = _call(_graph(
            source_kind="OBSERVED_EXTRACTION",
            node_state="OBSERVED",
            rear_state="UNKNOWN",
        ))

        self.assertEqual("DERIVED", result["construction_regime"]["state"])
        self.assertEqual(
            "OBSERVED",
            result["manufacturing_representation"]["rectangles"][0]["state"],
        )
        self.assertEqual("UNKNOWN", result["authority"]["rear"]["state"])
        self.assertFalse(result["authority"]["rear"]["observed"])
        self.assertEqual([], result["authority"]["fact_promotions"])

    def test_garment_name_is_metadata_not_construction_evidence(self):
        first_request = _graph(name="robe")
        second_request = copy.deepcopy(first_request)
        second_request["garment_name"] = "anime sari knitted kimono"

        first = _call(first_request)
        second = _call(second_request)

        self.assertEqual(
            first["construction_digest"], second["construction_digest"])
        self.assertEqual(
            first["construction_regime"], second["construction_regime"])
        self.assertFalse(first["identity"]["garment_name_used_for_routing"])
        self.assertFalse(second["identity"]["garment_name_used_for_routing"])

    def test_unknown_typed_construction_stays_unknown(self):
        request = _graph()
        request["nodes"][0]["construction"].update({
            "method": "UNKNOWN",
            "cut_geometry": "UNKNOWN",
            "fit": "UNKNOWN",
        })

        result = _call(request)

        self.assertEqual("UNKNOWN_CONSTRUCTION", result["verdict"])
        self.assertEqual("UNKNOWN", result["state"])
        self.assertEqual(
            "UNKNOWN_CONSTRUCTION", result["construction_regime"]["value"])
        self.assertEqual(
            "UNKNOWN_MANUFACTURING_REPRESENTATION",
            result["manufacturing_representation"]["kind"],
        )
        self.assertEqual([], result["fact_promotions"])


if __name__ == "__main__":
    unittest.main()
