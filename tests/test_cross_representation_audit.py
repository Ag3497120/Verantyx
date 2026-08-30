#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Executable falsification tests for the Cross representation metaphor."""
from __future__ import annotations

import json
import unittest

from photoloset import cross
from photoloset import cross_representation_audit as audit
from photoloset import mcp


class CauseAxisAuditTests(unittest.TestCase):
    maxDiff = None

    def test_cause_axis_changes_metadata_not_value_selection(self):
        result = audit.audit_cause_axis()
        self.assertTrue(result["answer_selection_equal"])
        self.assertTrue(result["contested_selection_equal"])
        self.assertFalse(result["metadata_equal"])
        self.assertEqual([], result["resolve_cause_literals"])
        self.assertEqual("cause+", result["metadata"]["derived"]["arm"])
        self.assertEqual("cause-", result["metadata"]["feeds"]["arm"])


class TaggedRepresentationTests(unittest.TestCase):
    maxDiff = None

    def test_answer_value_and_provenance_survive_mapping(self):
        store = cross.CrossStore()
        store.put("garment", "bending", 0.004, "measured", "lab-a")
        store.put("garment", "bending", 0.004, "measured", "lab-b")
        store.put("garment", "bending", 0.004, "derived", "solver")

        tagged = audit.cross_to_tagged_records(store)
        resolved = audit.resolve_tagged_records(tagged, "garment", "bending")
        original = store.resolve("garment", "bending")

        self.assertEqual("ANSWER", resolved["verdict"])
        self.assertEqual(original["value"], resolved["value"])
        self.assertEqual(original["weight"], resolved["weight"])
        self.assertEqual(original["weight_by_kind"],
                         resolved["weight_by_kind"])
        self.assertEqual(original["sources_by_kind"],
                         resolved["sources_by_kind"])
        self.assertEqual({"lab-a", "lab-b", "solver"},
                         {source for row in resolved["provenance"]
                          for source in row["sources"]})

    def test_disagreement_and_both_sources_survive_mapping(self):
        store = cross.CrossStore()
        store.put("garment", "material", "jersey", "specific", "maker")
        store.put("garment", "material", "melton", "cited", "catalogue")

        tagged = audit.cross_to_tagged_records(store)
        resolved = audit.resolve_tagged_records(tagged, "garment", "material")

        self.assertEqual(cross.CONTESTED_IN_CROSS, resolved["verdict"])
        self.assertEqual({"jersey", "melton"},
                         {side["value"] for side in resolved["sides"]})
        self.assertEqual({"maker", "catalogue"},
                         {source for side in resolved["sides"]
                          for source in side["sources"]})
        self.assertTrue(audit.audit_tagged_equivalence()["all_equal"])
        self.assertTrue(
            audit.audit_tagged_equivalence()["provenance_preserved"])

    def test_mapping_does_not_alias_mutable_values(self):
        value = {"warp": [1, 2]}
        store = cross.CrossStore()
        store.put("garment", "material", value, "specific", "maker")
        tagged = audit.cross_to_tagged_records(store)
        tagged["records"][0]["value"]["warp"].append(3)
        self.assertEqual({"warp": [1, 2]},
                         store.resolve("garment", "material")["value"])


class OrderAndSchemaTests(unittest.TestCase):
    maxDiff = None

    def test_order_is_invariant_or_explicitly_unknown(self):
        result = audit.audit_order_behavior()
        self.assertEqual("ANSWER", result["stable"]["verdict"])
        self.assertEqual([], result["stable"]["differences"])
        self.assertEqual(cross.ORDER_DEPENDENT,
                         result["shared_address"]["verdict"])
        self.assertGreater(
            result["shared_address"]["budget_arm_differences"], 0)
        self.assertTrue(result["explicit"])

    def test_evidence_and_physical_cross_are_separate_schemas(self):
        result = audit.audit_schema_separation()
        self.assertTrue(result["schema_names_differ"])
        self.assertEqual("ANSWER",
                         result["evidence_accepts_evidence"]["verdict"])
        self.assertEqual("ANSWER",
                         result["physical_accepts_physical"]["verdict"])
        self.assertEqual("UNKNOWN_EVIDENCE_SCHEMA_MISMATCH",
                         result["evidence_rejects_physical"]["verdict"])
        self.assertEqual("UNKNOWN_PHYSICAL_SCHEMA_MISMATCH",
                         result["physical_rejects_evidence"]["verdict"])


class ReportAndCostTests(unittest.TestCase):
    maxDiff = None

    def test_deterministic_report_digest_excludes_volatile_timing(self):
        first = audit.build_audit_report(benchmark_rounds=2,
                                         benchmark_iterations=5)
        second = audit.build_audit_report(benchmark_rounds=2,
                                          benchmark_iterations=5)
        self.assertEqual(first["deterministic"], second["deterministic"])
        self.assertEqual(first["deterministic_digest"],
                         second["deterministic_digest"])
        self.assertEqual(
            "NAME_AND_GEOMETRIC_METAPHOR_NOT_REQUIRED_FOR_MEASURED_SEMANTICS",
            first["deterministic"]["verdict"],
        )

    def test_costs_are_raw_observations_not_a_superiority_claim(self):
        result = audit.measure_representation_costs(rounds=2, iterations=5)
        self.assertEqual(audit.NO_SUPERIORITY_CLAIM,
                         result["comparative_conclusion"])
        self.assertGreater(result["memory_bytes"]["cross"], 0)
        self.assertGreater(result["memory_bytes"]["ordinary_tagged"], 0)
        speed = result["nanoseconds_per_iteration"]
        self.assertEqual(2, len(speed["cross_samples"]))
        self.assertEqual(2, len(speed["ordinary_tagged_samples"]))
        self.assertGreater(speed["cross_median"], 0)
        self.assertGreater(speed["ordinary_tagged_median"], 0)
        self.assertTrue(any("excluded" in item
                            for item in result["limits"]))


class MCPAuditBoundaryTests(unittest.TestCase):
    def test_mcp_report_states_the_partial_falsification(self):
        result = json.loads(mcp.TOOLS[
            "cross_representation_falsification_audit"
        ](json.dumps({
            "benchmark_rounds": 1,
            "benchmark_iterations": 2,
        })))
        deterministic = result["deterministic"]
        self.assertEqual(
            "NAME_AND_GEOMETRIC_METAPHOR_NOT_REQUIRED_FOR_MEASURED_SEMANTICS",
            deterministic["verdict"],
        )
        self.assertTrue(
            deterministic["cause_axis"]["answer_selection_equal"])
        self.assertTrue(
            deterministic["tagged_equivalence"]["all_equal"])
        self.assertEqual(
            audit.NO_SUPERIORITY_CLAIM,
            result["performance_observation"]["comparative_conclusion"],
        )

    def test_mcp_report_rejects_unbounded_or_unknown_input(self):
        too_large = json.loads(mcp.TOOLS[
            "cross_representation_falsification_audit"
        ]('{"benchmark_rounds": 21}'))
        self.assertEqual("UNKNOWN_BAD_ARGUMENTS", too_large["verdict"])
        unknown = json.loads(mcp.TOOLS[
            "cross_representation_falsification_audit"
        ]('{"claim_superiority": true}'))
        self.assertEqual("UNKNOWN_BAD_ARGUMENTS", unknown["verdict"])


if __name__ == "__main__":
    unittest.main()
