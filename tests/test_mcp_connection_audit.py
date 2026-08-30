#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import unittest

from photoloset import front_geometry_cues
from photoloset import mcp
from photoloset import mcp_server


STATUSES = {
    "CONNECTED", "OPTIONAL_PROVIDER", "HUMAN_RESOLUTION", "TYPED_STOP",
}


def call(name: str, payload: dict | None = None) -> dict:
    return json.loads(mcp.TOOLS[name](
        json.dumps(payload or {}, ensure_ascii=False)))


def compiled_pattern() -> dict:
    return {
        "verdict": "ANSWER",
        "schema": "garment.compiled-pattern.v1",
        "digest": "pattern-digest",
        "structure_digest": "structure-digest",
        "candidate_id": "candidate-a",
        "candidate_state": "APPROVED",
        "approval": {
            "by": "MCP audit reviewer",
            "digest": "candidate-digest",
            "approval_id": "approval-a",
        },
        "pieces": [{
            "piece_id": "body",
            "name": "body",
            "outline": [[0.0, 0.0], [40.0, 0.0],
                        [40.0, 60.0], [0.0, 60.0]],
            "cut_count": 1,
            "layer": 0,
            "role": "body_wrap",
            "primitive_kind": "BODY_SHELL",
            "grain": {
                "direction": "parallel_to_height",
                "state": "PROPOSED",
            },
            "attributes": {},
        }],
        "seams": [],
        "layers": [],
        "transforms": [],
        "features": [],
        "seam_checks": [{"geometrically_sewable": True}],
        "representation_complete": True,
        "uncompiled_visual_parts": [],
    }


class MCPConnectionAuditTests(unittest.TestCase):
    maxDiff = None

    def test_audit_has_only_four_statuses_and_no_plain_dead_end(self):
        result = call("garment_connection_audit")

        self.assertEqual(result["schema"], "garment.connection-audit.v1")
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(set(result["statuses"]), STATUSES)
        self.assertEqual(result["summary"]["plain_dead_end_count"], 0)
        self.assertEqual(result["summary"]["provider_imports_performed"], 0)
        self.assertTrue(result["components"])
        for row in result["components"]:
            with self.subTest(component=row["component"]):
                self.assertIn(row["status"], STATUSES)
                self.assertTrue(row["accepted_evidence"])
                self.assertTrue(row["next_action"])
                self.assertIsInstance(row["tools_available"], list)
                self.assertIsInstance(row["tools_missing"], list)

    def test_public_inventory_compares_symbols_tools_factory_and_components(self):
        result = call("garment_connection_audit", {"include_inventory": True})
        rows = {row["module"]: row
                for row in result["public_module_inventory"]}

        manufacturing = rows["photoloset.pattern_manufacturing_bundle"]
        self.assertIn("build", manufacturing["public_symbols"])
        self.assertIn("manufacturing preview bundle",
                      manufacturing["registered_components"])
        factory = rows["photoloset.garment_factory"]
        self.assertIn("new_job", factory["public_symbols"])
        self.assertIn("advance", factory["public_symbols"])
        self.assertTrue(factory["registered_components"])
        self.assertIn("unconnected_public_modules", result)

    def test_optional_component_registration_never_imports_missing_module(self):
        module_name = "photoloset._future_cross_harness_for_audit_test"
        self.assertNotIn(module_name, sys.modules)
        key = mcp.register_connection_component(
            "future audit-only Cross harness",
            stage="CROSS_HARNESS",
            status=mcp.OPTIONAL_PROVIDER,
            module=module_name,
            tools=(),
            factory_events=(),
            accepted_evidence=("typed future harness result",),
            next_action="install and explicitly register the future harness",
        )
        self.addCleanup(mcp._CONNECTION_COMPONENTS.pop, key, None)

        result = call("garment_connection_audit", {
            "component": "future audit-only Cross harness",
        })
        self.assertEqual(len(result["components"]), 1)
        row = result["components"][0]
        self.assertEqual(row["status"], "OPTIONAL_PROVIDER")
        self.assertFalse(row["module_available"])
        self.assertNotIn(module_name, sys.modules)

    def test_mcp_extension_and_new_direct_tools_are_published(self):
        expected = {
            "garment_connection_audit",
            "garment_structure_sewing_plan",
            "garment_manufacturing_preview",
            "garment_engineering_review",
            "garment_decorative_pattern",
            "garment_front_cutout_alternative",
            mcp_server.TOOL_NAME,
        }
        self.assertTrue(expected.issubset(mcp_server.TOOLS))
        listing = mcp_server.handle({"method": "tools/list"})
        names = {row["name"] for row in listing["tools"]}
        self.assertTrue(expected.issubset(names))

        audit = call("garment_connection_audit", {
            "component": "front candidate Pareto evaluator",
        })
        self.assertEqual(audit["components"][0]["status"], "CONNECTED")
        self.assertIn(mcp_server.TOOL_NAME,
                      audit["components"][0]["tools_available"])

    def test_direct_pattern_stage_tools_preserve_existing_authority(self):
        pattern = compiled_pattern()
        sewing = call("garment_structure_sewing_plan", {"pattern": pattern})
        self.assertEqual(sewing["order_verdict"], "ANSWER")
        self.assertFalse(sewing["manufacturing_ready"])

        refused = call("garment_manufacturing_preview", {"pattern": pattern})
        self.assertEqual(refused["verdict"],
                         "UNKNOWN_SEAM_ALLOWANCE_MISSING")
        self.assertEqual(refused["connection_resolution"]["status"],
                         "TYPED_STOP")

        manufacturing = call("garment_manufacturing_preview", {
            "pattern": pattern,
            "seam_allowance_cm": 1.0,
        })
        self.assertEqual(manufacturing["verdict"], "ANSWER")
        self.assertTrue(manufacturing["manufacturing_preview_ready"])
        self.assertFalse(manufacturing["manufacturing_ready"])
        self.assertFalse(manufacturing["manufacturing_certified"])

        review = call("garment_engineering_review", {
            "pattern": pattern,
            "manufacturing": manufacturing,
            "sewing_plan": sewing,
        })
        self.assertEqual(review["schema"], "garment.engineering-review.v1")
        self.assertFalse(review["manufacturing_ready"])
        self.assertTrue(review["actionable_gates"])

    def test_decorative_and_cutout_adapters_expose_existing_geometry(self):
        decoration = call("garment_decorative_pattern", {
            "kind": "RUFFLE",
            "piece_id": "hem-ruffle",
            "finished_length_cm": 20.0,
            "depth_cm": 5.0,
            "gather_ratio": 2.0,
            "seam_allowance_cm": 1.0,
            "layer": 1,
        })
        self.assertEqual(decoration["verdict"], "ANSWER")
        self.assertFalse(decoration["provenance"]["corpus_used"])

        outline = {
            "outline": [[0, 0], [100, 0], [100, 200], [0, 200]],
            "internal_boundaries": [
                [[40, 40], [60, 40], [60, 65], [40, 65]],
            ],
            "provenance": {"kind": "OBSERVED", "source": "fixture"},
        }
        # Build the candidates without internal geometry first.  The regular
        # high-level hypothesis helper already applies this adapter when an
        # internal boundary is present; feeding those results back would test
        # duplicate-port rejection instead of this MCP connection.
        hypotheses = front_geometry_cues.hypothesize({
            "outline": outline["outline"],
            "provenance": outline["provenance"],
        })["hypotheses"]
        result = call("garment_front_cutout_alternative", {
            "outline": outline,
            "candidates": hypotheses,
        })
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(result["audit"]["state"], "PROPOSED")
        self.assertFalse(result["audit"]["semantics_observed"])
        self.assertEqual(len(result["candidates"]), len(hypotheses))


if __name__ == "__main__":
    unittest.main()
