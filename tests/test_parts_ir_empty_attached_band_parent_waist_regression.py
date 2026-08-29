#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression for the live UNKNOWN_REQUIREMENT_BAND_NODE_ADDRESS refusal.

The app-level refusal is emitted before this public Python boundary.  This
test starts at the nearest public Parts IR contract: an explicitly attached
waist-belt BAND and its BODY_SHELL parent both have empty dimensions.  The
bounded preview profile may propose dimensions, but it must not turn them into
observations.  The child must resolve to the named parent's waist boundary,
not to an independently sized primitive-level BAND.
"""
import copy
import json
import unittest

from photoloset.parts_ir_completion import bounded_preview_profile
from photoloset.parts_ir_pipeline import run_parts_ir_pipeline


def _proposed_visible_basis(label):
    return {
        "state": "PROPOSED",
        "basis": f"front image model proposed the visible {label}",
        "breaks_when": "another view or a reviewer contradicts it",
    }


def _request():
    parts = [
        {
            "part_id": "bodice",
            "kind": "BODY_SHELL",
            "layer": 0,
            "placement": "torso",
            "garment_unit": "look",
            "visible_basis": _proposed_visible_basis("bodice"),
            "dimensions": {},
        },
        {
            "part_id": "waist-belt",
            "kind": "BAND",
            "layer": 1,
            "placement": "front accessory",
            "shape": "waist_belt",
            "garment_unit": "look",
            "attached_to": "bodice",
            "visible_basis": _proposed_visible_basis("waist belt"),
            "dimensions": {},
        },
    ]
    return {
        "schema": "garment.parts-ir.v1",
        "state": "PROPOSED",
        "candidates": [
            {"candidate_id": "rear-a", "parts": copy.deepcopy(parts)},
            {"candidate_id": "rear-b", "parts": copy.deepcopy(parts)},
        ],
    }


def _failure_report(result):
    failures = [
        {
            "stage": row.get("stage"),
            "code": row.get("code"),
            "why": row.get("why"),
            "engine_result": row.get("engine_result"),
        }
        for row in result.get("failures", [])
    ]
    return json.dumps({
        "public_call_path": [
            "parts_ir_pipeline.run_parts_ir_pipeline",
            "parts_ir_pipeline._run_candidate",
            "parts_ir_pipeline._isolated_topology",
            "parts_ir_topology.apply_parts_ir_topology",
            "parts_ir_topology._candidate_topology",
            "parts_ir_topology._band_target",
            "parts_ir_topology._Refusal(UNKNOWN_PARTS_TOPOLOGY_BAND_TARGET_AMBIGUOUS)",
        ],
        "verdict": result.get("verdict"),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True)


class EmptyAttachedBandParentWaistRegressionTests(unittest.TestCase):
    def test_empty_attached_band_resolves_to_named_body_waist_as_proposed(self):
        result = run_parts_ir_pipeline(
            _request(), preview_profile=bounded_preview_profile())

        # Dimension completion already keeps the preview authority boundary.
        completion = result["completion"]
        self.assertEqual(completion["verdict"], "PROPOSED")
        self.assertFalse(completion["authority"]["observed"])
        for candidate in completion["candidates"]:
            nodes = {node["node_id"]: node for node in candidate["nodes"]}
            belt = nodes["waist-belt"]
            self.assertEqual(
                belt["attributes"]["attached_to"], "bodice")
            self.assertEqual(belt["attributes"]["state"], "PROPOSED")
            self.assertTrue(belt["attributes"]["not_measured_from_image"])
            for evidence in belt["attributes"]["dimension_evidence"].values():
                self.assertEqual(evidence["state"], "PROPOSED")
                self.assertNotEqual(evidence["state"], "OBSERVED")
                self.assertTrue(evidence["not_measured_from_image"])
                self.assertFalse(any(
                    source.get("source_measurement_was_observed") is True
                    for source in evidence["source_measurements"]
                ))

        # Intended regression behavior: attached_to plus belt semantics select
        # the BODY_SHELL waist, and the same proposed length is used on both
        # sides of one candidate-bound JOIN.
        self.assertEqual(result["verdict"], "PROPOSED",
                         _failure_report(result))
        self.assertEqual(result["successful_candidate_count"], 2)
        self.assertFalse(result["authority"]["observed"])
        for candidate in result["candidates"]:
            self.assertEqual(candidate["execution_status"], "SUCCEEDED")
            joins = [
                operation for operation in candidate["structure"]["operations"]
                if operation["kind"] == "JOIN"
                and {operation["source"]["node_id"],
                     operation["target"]["node_id"]}
                == {"bodice", "waist-belt"}
            ]
            self.assertEqual(len(joins), 1)
            join = joins[0]
            nodes = {
                node["node_id"]: node
                for node in candidate["structure"]["nodes"]
            }
            belt_length = nodes["waist-belt"]["dimensions"]["length_cm"]
            source_port = next(
                port for port in nodes[join["source"]["node_id"]]["ports"]
                if port["port_id"] == join["source"]["port_id"])
            target_port = next(
                port for port in nodes[join["target"]["node_id"]]["ports"]
                if port["port_id"] == join["target"]["port_id"])
            self.assertAlmostEqual(source_port["length_cm"], belt_length)
            self.assertAlmostEqual(target_port["length_cm"], belt_length)
            self.assertEqual(join["parameters"]["state"], "PROPOSED")


if __name__ == "__main__":
    unittest.main()
