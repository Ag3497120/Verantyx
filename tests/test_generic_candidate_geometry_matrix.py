#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generic candidate-geometry regression matrix.

The fixtures deliberately use anonymous node ids and garment units.  They
exercise typed structure rather than any one reference image, garment name,
or project-specific visual token.
"""
from __future__ import annotations

import copy
import unittest
from typing import Any, Callable, Dict, List, Mapping, Optional

from photoloset import garment_structure
from photoloset.parts_ir_completion import complete_parts_ir
from photoloset.parts_ir_topology import apply_parts_ir_topology


def _part(node_id: str, kind: str, dimensions: Mapping[str, float],
          *, layer: int = 0, placement: str = "region",
          unit: Optional[str] = "unit-0", **semantics: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "part_id": node_id,
        "kind": kind,
        "layer": layer,
        "placement": placement,
        "visible_basis": {
            "state": "PROPOSED",
            "basis": f"front input proposes anonymous region {node_id}",
            "breaks_when": "another view or construction review rejects it",
        },
        "dimensions": dict(dimensions),
    }
    if unit is not None:
        result["garment_unit"] = unit
    result.update(semantics)
    return result


def _complete(parts_a: List[Dict[str, Any]],
              parts_b: Optional[List[Dict[str, Any]]] = None
              ) -> Dict[str, Any]:
    if parts_b is None:
        parts_b = copy.deepcopy(parts_a)
    result = complete_parts_ir({
        "schema": "garment.parts-ir.v1",
        "state": "PROPOSED",
        "candidates": [
            {"candidate_id": "candidate-0", "state": "PROPOSED",
             "parts": copy.deepcopy(parts_a)},
            {"candidate_id": "candidate-1", "state": "PROPOSED",
             "parts": copy.deepcopy(parts_b)},
        ],
    })
    if result.get("verdict") != "PROPOSED":
        raise AssertionError(result)
    return result


def _replace_second_structure_with_first(
        completed: Dict[str, Any],
        mutate: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        *, keep_second_ornaments: bool = False) -> None:
    """Remove completion's A/B rear-hypothesis difference from one test axis."""
    first, second = completed["candidates"]
    second_ornaments = copy.deepcopy(second.get("ornament_artifacts"))
    nodes = copy.deepcopy(first["nodes"])
    if mutate is not None:
        mutate(nodes)
    checked = garment_structure.validate({
        "schema": garment_structure.SCHEMA,
        "nodes": nodes,
        "operations": [],
    })
    if checked.get("verdict") != "ANSWER":
        raise AssertionError(checked)
    second["nodes"] = copy.deepcopy(checked["graph"]["nodes"])
    second["structure_digest"] = checked["digest"]
    if keep_second_ornaments and second_ornaments is not None:
        second["ornament_artifacts"] = second_ornaments
        second["ornament_artifacts"]["source_structure_digest"] = (
            checked["digest"])
    elif "ornament_artifacts" in first:
        second["ornament_artifacts"] = copy.deepcopy(
            first["ornament_artifacts"])
        second["ornament_artifacts"]["source_structure_digest"] = (
            checked["digest"])


def _body_overlay_parts(*, ornament_quantity: Optional[int] = None
                        ) -> List[Dict[str, Any]]:
    parts = [
        _part("p-00", "BODY_SHELL",
              {"height_cm": 42.0, "circumference_cm": 84.0},
              unit="unit-0", quantity=1),
        _part("p-01", "OVERLAY",
              {"height_cm": 38.0, "width_cm": 70.0},
              layer=2, placement="front left", unit="unit-0",
              attached_to="p-00", side="left", shape="surface overlay",
              detail_role="overlay", quantity=1),
    ]
    if ornament_quantity is not None:
        parts.append(_part(
            "p-02", "ROSETTE",
            {"strip_length_cm": 68.0, "strip_width_cm": 4.0,
             "finished_inner_length_cm": 17.0},
            layer=3, placement="front surface", unit="unit-0",
            attached_to="p-01", target_port_id="surface-anchor",
            quantity=ornament_quantity, grain_direction="BIAS_45",
            seam_allowance_cm=0.8,
        ))
    return parts


def _trouser_units() -> List[Dict[str, Any]]:
    parts: List[Dict[str, Any]] = []
    for index, (unit, layer, circumference) in enumerate((
            ("unit-1", 1, 42.0),
            ("unit-2", 3, 48.0),
    )):
        left_id = f"p-{10 + index * 3}"
        right_id = f"p-{11 + index * 3}"
        center_id = f"p-{12 + index * 3}"
        parts.extend([
            _part(left_id, "TUBE",
                  {"length_cm": 92.0, "circumference_cm": circumference},
                  layer=layer, placement="lower left", unit=unit,
                  side="left", shape="trouser_leg",
                  detail_role="trouser_leg", quantity=1),
            _part(right_id, "TUBE",
                  {"length_cm": 92.0, "circumference_cm": circumference},
                  layer=layer, placement="lower right", unit=unit,
                  side="right", shape="trouser_leg",
                  detail_role="trouser_leg", quantity=1),
            _part(center_id, "GUSSET",
                  {"length_cm": 16.0, "width_cm": 8.0},
                  layer=layer, placement="lower center", unit=unit,
                  attached_to=[left_id, right_id], side="center",
                  shape="trousers", detail_role="trouser_gusset",
                  quantity=1),
        ])
    return parts


class GenericCandidateGeometryMatrixTests(unittest.TestCase):
    def test_multilayer_shell_selects_the_explicit_outer_sleeve_parent(self):
        parts = [
            _part("p-20", "BODY_SHELL",
                  {"height_cm": 41.0, "circumference_cm": 82.0},
                  layer=0, unit="unit-3", quantity=1),
            _part("p-21", "BODY_SHELL",
                  {"height_cm": 44.0, "circumference_cm": 90.0},
                  layer=2, unit="unit-3", quantity=1),
            _part("p-22", "SLEEVE",
                  {"length_cm": 57.0, "upper_circumference_cm": 36.0,
                   "cuff_circumference_cm": 22.0},
                  layer=2, placement="outer arm", unit="unit-3",
                  attached_to="p-21", side="bilateral", shape="set_in",
                  quantity=2),
        ]
        result = apply_parts_ir_topology(_complete(parts))
        self.assertEqual("PROPOSED", result["verdict"], result)
        for candidate in result["candidates"]:
            delegated = [
                relation for relation in candidate["topology"][
                    "delegated_relations"]
                if relation["node_id"] == "p-22"
            ]
            self.assertEqual(1, len(delegated))
            self.assertEqual("p-21", delegated[0]["target_node_id"])
            self.assertNotEqual("p-20", delegated[0]["target_node_id"])
            self.assertEqual(
                "DELEGATED_BODICE_SET_IN_SLEEVE_BRIDGE",
                delegated[0]["rule"],
            )

    def test_candidate_geometry_digest_changes_for_each_generic_axis(self):
        cases = []

        def change_layer(nodes: List[Dict[str, Any]]) -> None:
            next(node for node in nodes if node["node_id"] == "p-01")[
                "layer"] = 4

        def change_overlay_geometry(nodes: List[Dict[str, Any]]) -> None:
            next(node for node in nodes if node["node_id"] == "p-01")[
                "dimensions"]["width_cm"] = 76.0

        def change_asymmetry(nodes: List[Dict[str, Any]]) -> None:
            node = next(node for node in nodes if node["node_id"] == "p-01")
            node["attributes"]["side"] = "asymmetric"
            node["attributes"]["shape"] = "asymmetric"

        for label, mutate in (
                ("layer", change_layer),
                ("overlay-geometry", change_overlay_geometry),
                ("asymmetric-attachment", change_asymmetry)):
            completed = _complete(_body_overlay_parts())
            _replace_second_structure_with_first(completed, mutate)
            cases.append((label, apply_parts_ir_topology(completed)))

        repeated = _complete(
            _body_overlay_parts(ornament_quantity=2),
            _body_overlay_parts(ornament_quantity=3),
        )
        _replace_second_structure_with_first(
            repeated, keep_second_ornaments=True)
        cases.append(("repeated-decoration",
                      apply_parts_ir_topology(repeated)))

        for label, result in cases:
            with self.subTest(axis=label):
                self.assertEqual("PROPOSED", result["verdict"], result)
                first, second = result["candidates"]
                self.assertNotEqual(first["candidate_geometry_digest"],
                                    second["candidate_geometry_digest"])
                self.assertEqual("PROPOSED",
                                 first["candidate_geometry"]["state"])
                self.assertEqual("PROPOSED",
                                 second["candidate_geometry"]["state"])
                self.assertFalse(first["candidate_geometry"][
                    "formed_3d_geometry_claimed"])
                self.assertFalse(second["candidate_geometry"][
                    "authority_granted"])

        asymmetric = dict(cases)["asymmetric-attachment"]["candidates"][1]
        self.assertEqual(
            ["p-01"],
            asymmetric["candidate_geometry"][
                "asymmetric_attachment_node_ids"],
        )
        repeated_candidates = dict(cases)["repeated-decoration"]["candidates"]
        self.assertEqual(
            [2, 3],
            [len(candidate["candidate_geometry"][
                "decorative_surface_instances"])
             for candidate in repeated_candidates],
        )

    def test_two_trouser_units_and_layers_compile_as_independent_pairs(self):
        result = apply_parts_ir_topology(_complete(_trouser_units()))
        self.assertEqual("PROPOSED", result["verdict"], result)
        expected_pairs = {
            frozenset(("p-10", "p-12")),
            frozenset(("p-11", "p-12")),
            frozenset(("p-13", "p-15")),
            frozenset(("p-14", "p-15")),
        }
        for candidate in result["candidates"]:
            joins = [operation for operation in candidate["operations"]
                     if operation["kind"] == "JOIN"]
            self.assertEqual(expected_pairs, {
                frozenset((operation["source"]["node_id"],
                           operation["target"]["node_id"]))
                for operation in joins
            })
            nodes = {node["node_id"]: node for node in candidate["nodes"]}
            self.assertEqual("unit-1", nodes["p-10"]["attributes"][
                "garment_unit"])
            self.assertEqual(1, nodes["p-10"]["layer"])
            self.assertEqual("unit-2", nodes["p-13"]["attributes"][
                "garment_unit"])
            self.assertEqual(3, nodes["p-13"]["layer"])

    def test_incomplete_and_ambiguous_relation_matrix_stays_unknown(self):
        incomplete = _trouser_units()
        incomplete = [part for part in incomplete
                      if part["part_id"] != "p-11"]

        ambiguous = [
            _part("p-30", "BODY_SHELL",
                  {"height_cm": 40.0, "circumference_cm": 80.0},
                  layer=0, unit="unit-4", quantity=1),
            _part("p-31", "BODY_SHELL",
                  {"height_cm": 43.0, "circumference_cm": 88.0},
                  layer=2, unit="unit-4", quantity=1),
            _part("p-32", "OVERLAY",
                  {"height_cm": 36.0, "width_cm": 68.0},
                  layer=3, unit="unit-4",
                  attached_to=["p-30", "p-31"],
                  shape="surface overlay", detail_role="overlay",
                  quantity=1),
        ]

        cases = (
            ("incomplete-trouser", incomplete,
             "UNKNOWN_PARTS_TOPOLOGY_TROUSERS_INCOMPLETE"),
            ("ambiguous-parent", ambiguous,
             "UNKNOWN_PARTS_TOPOLOGY_PARENT_AMBIGUOUS"),
        )
        for label, parts, expected in cases:
            with self.subTest(case=label):
                result = apply_parts_ir_topology(_complete(parts))
                self.assertEqual(expected, result["verdict"], result)
                self.assertEqual("UNRESOLVED", result["state"])


if __name__ == "__main__":
    unittest.main()
