#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end refusal contract for the MCP garment factory.

The factory is allowed to stop.  It is not allowed to leave a caller with an
untyped, unactionable dead end.  This test inventories refusal literals from
the factory source independently of the implementation under test, then
checks the MCP control-plane contract and two real persisted transitions.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from photoloset import mcp


ACTIONABLE = {mcp.HUMAN_RESOLUTION, mcp.OPTIONAL_PROVIDER}
FACTORY_PATH = Path(__file__).resolve().parents[1] / "photoloset" / "garment_factory.py"
REQUIRED_LIMITATIONS = {
    "rear-not-observed-from-front",
    "material-properties-not-measured-from-image",
    "wearer-body-not-measured-from-image",
    "arbitrary-garment-fidelity-not-guaranteed",
    "finished-pattern-not-guaranteed",
    "seam-finishes-undetermined",
    "real-cloth-error-not-calibrated",
    "wind-tunnel-validation-not-connected",
    "fashion-siglip-index-not-connected",
    "sewing-corpus-not-connected",
}


def call_audit(payload: dict | None = None) -> dict:
    return json.loads(mcp.TOOLS["garment_connection_audit"](
        json.dumps(payload or {}, ensure_ascii=False)))


def factory_refusal_literals() -> set[str]:
    """Discover factory verdicts without calling the audit's own scanner."""
    tree = ast.parse(FACTORY_PATH.read_text(encoding="utf-8"),
                     filename=str(FACTORY_PATH))
    return {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith(("UNKNOWN_", "CONTESTED_", "ESCALATE_"))
    }


class UnknownResolutionE2ETests(unittest.TestCase):
    maxDiff = None

    def isolated_store(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        stack = patch.multiple(
            mcp, HOME=root, PROJECTS=root / "projects",
            CURRENT=root / "current_project")
        stack.start()
        self.addCleanup(stack.stop)
        self.addCleanup(temporary.cleanup)

    def test_every_factory_refusal_is_actionable_or_a_typed_terminal_stop(self):
        independently_discovered = factory_refusal_literals()
        audit = call_audit()
        by_verdict = {
            row["verdict"]: row
            for row in audit["factory_unknown_resolutions"]
        }

        self.assertTrue(independently_discovered)
        self.assertEqual(independently_discovered, set(by_verdict))
        for verdict in sorted(independently_discovered):
            row = by_verdict[verdict]
            with self.subTest(verdict=verdict):
                self.assertTrue(row["accepted_evidence"])
                self.assertTrue(row["next_action"])
                self.assertNotEqual(row["status"], mcp.CONNECTED)
                if row["status"] in ACTIONABLE:
                    self.assertTrue(row["actionable"])
                    self.assertFalse(row["terminal"])
                else:
                    self.assertEqual(row["status"], mcp.TYPED_STOP)
                    self.assertFalse(row["actionable"])
                    self.assertTrue(row["terminal"])

        self.assertEqual(audit["summary"]["plain_dead_end_count"], 0)
        self.assertEqual(audit["summary"]["factory_unknown_count"],
                         len(independently_discovered))

    def test_llm_is_only_an_explicit_proposed_provider_route(self):
        audit = call_audit()
        rows = audit["factory_unknown_resolutions"]
        optional = [row for row in rows
                    if row["status"] == mcp.OPTIONAL_PROVIDER]
        human = [row for row in rows
                 if row["status"] == mcp.HUMAN_RESOLUTION]
        terminal = [row for row in rows
                    if row["status"] == mcp.TYPED_STOP]

        self.assertTrue(optional)
        self.assertTrue(human)
        self.assertTrue(terminal)
        for row in optional:
            policy = row["llm_policy"]
            self.assertTrue(policy["allowed"])
            self.assertTrue(policy["requires_explicit_consent"])
            self.assertEqual(policy["output_state"], "PROPOSED")
            self.assertTrue(policy["cannot_claim"])
        for row in human + terminal:
            self.assertFalse(row["llm_policy"]["allowed"])

    def test_unknown_dynamic_stage_code_fails_closed(self):
        policy = call_audit()["dynamic_factory_verdict_policy"]
        self.assertEqual(policy["verdict"], "UNKNOWN_DYNAMIC_STAGE_VERDICT")
        self.assertEqual(policy["status"], mcp.TYPED_STOP)
        self.assertTrue(policy["terminal"])
        self.assertFalse(policy["actionable"])
        self.assertTrue(policy["accepted_evidence"])
        self.assertTrue(policy["next_action"])

    def test_known_limits_have_mcp_retrieval_and_factory_resume_routes(self):
        # Exercise the JSON-RPC boundary, not the Python helper directly.
        listed = mcp.handle({"method": "tools/list"})
        advertised = {row["name"] for row in listed["tools"]}
        response = mcp.handle({
            "method": "tools/call",
            "params": {
                "name": "garment_connection_audit",
                "arguments": {"json_text": "{}"},
            },
        })
        audit = json.loads(response["content"][0]["text"])
        by_id = {row["limitation_id"]: row
                 for row in audit["known_limitations"]}

        self.assertEqual(set(by_id), REQUIRED_LIMITATIONS)
        self.assertEqual(
            audit["summary"]["limitation_plain_dead_end_count"], 0)
        for limitation_id in sorted(REQUIRED_LIMITATIONS):
            row = by_id[limitation_id]
            route = row["resolution_route"]
            with self.subTest(limitation_id=limitation_id):
                self.assertIn(row["status"], {
                    mcp.OPTIONAL_PROVIDER,
                    mcp.HUMAN_RESOLUTION,
                    mcp.TYPED_STOP,
                })
                self.assertTrue(row["accepted_evidence"])
                self.assertTrue(row["next_action"])
                self.assertTrue(row["terminal_claim"])
                self.assertFalse(row["tools_missing"])
                self.assertTrue(route["retrievable"])
                self.assertTrue(route["resumable"])
                self.assertEqual(route["discover_with"],
                                 "garment_connection_audit")
                self.assertEqual(route["resume_with"], "garment_factory")
                self.assertEqual(route["action"], "advance")
                self.assertTrue(route["event_types"])
                self.assertTrue(set(row["mcp_tools"]).issubset(advertised))
                self.assertTrue(set(route["acquire_with"])
                                .issubset(advertised))
                self.assertIn(route["resume_with"], advertised)

    def test_real_factory_stops_are_typed_and_the_job_remains_resumable(self):
        self.isolated_store()
        job_id = "unknown-resolution-e2e"
        started = json.loads(mcp.TOOLS["garment_factory"](
            json.dumps({"job_id": job_id}), "start"))
        self.assertEqual(started["verdict"], "ANSWER")
        initial_phase = started["state"]["phase"]

        malformed = json.loads(mcp.TOOLS["garment_factory"](
            json.dumps({"job_id": job_id, "event": {}}), "advance"))
        self.assertEqual(malformed["verdict"], "UNKNOWN_FACTORY_EVENT")
        self.assertEqual(malformed["connection_resolution"]["status"],
                         mcp.TYPED_STOP)
        self.assertTrue(malformed["connection_resolution"]["terminal"])
        self.assertEqual(malformed["state"]["phase"], initial_phase)

        missing_image = json.loads(mcp.TOOLS["garment_factory"](
            json.dumps({
                "job_id": job_id,
                "event": {"type": "HYBRID_RETRIEVE"},
            }), "advance"))
        self.assertEqual(missing_image["verdict"],
                         "UNKNOWN_IMAGE_CONFIRMATION_REQUIRED")
        resolution = missing_image["connection_resolution"]
        self.assertEqual(resolution["status"], mcp.HUMAN_RESOLUTION)
        self.assertTrue(resolution["actionable"])
        self.assertFalse(resolution["terminal"])

        inspected = json.loads(mcp.TOOLS["garment_factory"](
            json.dumps({"job_id": job_id}), "inspect"))
        self.assertEqual(inspected["verdict"], "ANSWER")
        self.assertEqual(inspected["state"]["job_id"], job_id)
        self.assertEqual(inspected["state"]["phase"], initial_phase)


if __name__ == "__main__":
    unittest.main()
