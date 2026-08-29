#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E contract for selecting one layered bodice as a root sleeve parent.

The structure is proposal-only.  Selecting the explicitly addressed bodice
preserves graph lineage; it does not establish wearer fit, manufacturing
fitness, or a certified construction method.
"""
from __future__ import annotations

import copy
import unittest

from photoloset import structure_preview
from photoloset import structure_to_pattern


CANDIDATE_ID = "layered-bodice-sleeve-a"
GARMENT_UNIT = "layered-bodice-look"


def _body(node_id: str, *, layer: int, circumference_cm: float,
          garment_unit: str = GARMENT_UNIT) -> dict:
    return {
        "node_id": node_id,
        "kind": "BODY_SHELL",
        "layer": layer,
        "dimensions": {
            "height_cm": 43.0,
            "circumference_cm": circumference_cm,
            "bottom_circumference_cm": 80.0,
        },
        "attributes": {
            "garment_unit": garment_unit,
            "proposal_only": True,
            "layer_role": "inner" if layer == 0 else "outer",
        },
        "ports": [],
    }


def _root_sleeve(*, attached_to=..., layer: int = 2,
                 garment_unit: str = GARMENT_UNIT,
                 node_id: str = "root-sleeve") -> dict:
    attributes = {
        "garment_unit": garment_unit,
        "proposal_only": True,
        "side": "bilateral",
        "quantity": 2,
        "shape": "set_in",
    }
    if attached_to is not ...:
        attributes["attached_to"] = attached_to
    return {
        "node_id": node_id,
        "kind": "SLEEVE",
        "layer": layer,
        "dimensions": {
            "length_cm": 58.0,
            "upper_circumference_cm": 36.0,
            "cuff_circumference_cm": 21.0,
        },
        "attributes": attributes,
        "ports": [],
    }


def layered_structure() -> dict:
    return {
        "schema": "garment.structure.v1",
        "nodes": [
            _body("inner-body", layer=0, circumference_cm=88.0),
            _body("outer-body", layer=2, circumference_cm=98.0),
            _root_sleeve(attached_to="outer-body"),
        ],
        "operations": [],
    }


class LayeredBodiceSleeveSelectionTests(unittest.TestCase):
    maxDiff = None

    def test_01_explicit_body_parent_selects_only_outer_bodice_for_expansion(self):
        spec = layered_structure()
        pattern = structure_to_pattern.compile(
            spec, candidate_id=CANDIDATE_ID)
        preview = structure_preview.generate_preview(
            spec, candidate_id=CANDIDATE_ID, radial_segments=8)

        self.assertEqual(pattern["verdict"], "ANSWER", pattern)
        self.assertEqual(pattern["candidate_id"], CANDIDATE_ID)
        pieces = {row["piece_id"]: row for row in pattern["pieces"]}
        self.assertEqual(set(pieces), {
            "inner-body",
            "outer-body:front",
            "outer-body:back",
            "root-sleeve:left",
            "root-sleeve:right",
        })
        self.assertNotIn("outer-body", pieces)
        self.assertEqual(pieces["inner-body"]["source_node_id"],
                         "inner-body")
        self.assertEqual(pieces["inner-body"]["primitive_kind"],
                         "BODY_SHELL")
        self.assertEqual(pieces["inner-body"]["layer"], 0)
        self.assertEqual(
            {row["source_node_id"] for row in pieces.values()},
            {"inner-body", "outer-body", "root-sleeve"},
        )

        expansions = [
            row for row in pattern["candidate_specific_expansions"]
            if row["kind"] == "BODICE_SET_IN_SLEEVE_BRIDGE"
        ]
        self.assertEqual(len(expansions), 1)
        expansion = expansions[0]
        self.assertEqual(expansion["source_nodes"],
                         ["outer-body", "root-sleeve"])
        self.assertNotIn("inner-body", expansion["source_nodes"])
        self.assertEqual(expansion["garment_unit"], GARMENT_UNIT)
        self.assertEqual(
            {row["target"] for row in expansion["lineage"]},
            {
                "outer-body:front",
                "outer-body:back",
                "root-sleeve:left",
                "root-sleeve:right",
            },
        )

        self.assertEqual(preview["verdict"], "ANSWER", preview)
        self.assertEqual(preview["candidate_id"], CANDIDATE_ID)
        self.assertEqual(preview["structure_digest"],
                         pattern["structure_digest"])
        self.assertTrue(preview["provenance"]["candidate_specific"])
        preview_parts = {row["node_id"]: row for row in preview["parts"]}
        self.assertEqual(set(preview_parts),
                         {"inner-body", "outer-body", "root-sleeve"})
        self.assertTrue(all(
            node_id == row["source_node_id"]
            for node_id, row in preview_parts.items()
        ))
        instances = preview_parts["root-sleeve"]["instances"]
        self.assertEqual([row["side"] for row in instances],
                         ["left", "right"])
        self.assertTrue(all(
            row["source_node_id"] == "root-sleeve"
            and row["attached_to_node_id"] == "outer-body"
            and row["relation_kind"] == "BODY_ATTACHMENT"
            for row in instances
        ))
        self.assertTrue(all(
            row["lineage"]["source_node_id"] == "root-sleeve"
            for row in instances
        ))

        self.assertFalse(pattern["manufacturing_ready"])
        self.assertFalse(pattern["manufacturing_certified"])
        self.assertFalse(preview["claims"]["manufacturing_ready"])
        self.assertIsNot(
            preview["claims"].get("manufacturing_certified"), True)
        self.assertFalse(preview["claims"]["mannequin_certified"])

    def test_02_missing_parent_with_two_same_unit_layer_bodies_is_ambiguous(self):
        spec = layered_structure()
        inner = next(row for row in spec["nodes"]
                     if row["node_id"] == "inner-body")
        inner["layer"] = 2
        sleeve = next(row for row in spec["nodes"]
                      if row["node_id"] == "root-sleeve")
        sleeve["attributes"].pop("attached_to")

        result = structure_to_pattern.compile(spec)

        self.assertEqual(
            result["verdict"],
            "UNKNOWN_BODICE_SLEEVE_BODY_PARENT_AMBIGUOUS",
            result,
        )
        self.assertEqual(result["root_sleeve_nodes"], ["root-sleeve"])
        self.assertEqual(result["candidate_body_nodes"],
                         ["inner-body", "outer-body"])

    def test_03_unknown_explicit_body_parent_is_typed_refusal(self):
        spec = layered_structure()
        sleeve = next(row for row in spec["nodes"]
                      if row["node_id"] == "root-sleeve")
        sleeve["attributes"]["attached_to"] = "missing-body"

        result = structure_to_pattern.compile(spec)

        self.assertEqual(
            result["verdict"],
            "UNKNOWN_BODICE_SLEEVE_BODY_PARENT_UNKNOWN",
            result,
        )
        self.assertEqual(result["unknown_parent_addresses"], [{
            "sleeve_node_id": "root-sleeve",
            "parent_node_id": "missing-body",
        }])

    def test_04_explicit_parent_must_match_sleeve_unit_and_layer(self):
        unit_mismatch = layered_structure()
        sleeve = next(row for row in unit_mismatch["nodes"]
                      if row["node_id"] == "root-sleeve")
        sleeve["attributes"]["garment_unit"] = "other-garment-unit"
        result = structure_to_pattern.compile(unit_mismatch)
        self.assertEqual(
            result["verdict"],
            "UNKNOWN_BODICE_SLEEVE_GARMENT_UNIT_MISMATCH",
            result,
        )
        layer_mismatch = layered_structure()
        sleeve = next(row for row in layer_mismatch["nodes"]
                      if row["node_id"] == "root-sleeve")
        sleeve["layer"] = 3
        result = structure_to_pattern.compile(layer_mismatch)
        self.assertEqual(
            result["verdict"],
            "UNKNOWN_BODICE_SLEEVE_BODY_LAYER_MISMATCH",
            result,
        )
        self.assertEqual(result["body_layer"], 2)
        self.assertEqual(result["sleeve_layer"], 3)

    def test_05_multiple_root_sleeves_remain_ambiguous(self):
        spec = layered_structure()
        spec["nodes"].append(_root_sleeve(
            attached_to="outer-body", node_id="second-root-sleeve"))

        result = structure_to_pattern.compile(spec)

        self.assertEqual(
            result["verdict"],
            "UNKNOWN_BODICE_SLEEVE_BRIDGE_CARDINALITY",
            result,
        )
        self.assertEqual(result["root_sleeve_nodes"],
                         ["root-sleeve", "second-root-sleeve"])


if __name__ == "__main__":
    unittest.main()
