#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from photoloset import body_proxy, mcp


TOOL_NAME = "garment_body_proxy_propose"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _dimension(value: float, authority: str, source_kind: str) -> dict:
    return {
        "value": value,
        "unit": "cm",
        "authority": authority,
        "source": {"kind": source_kind, "reference": "test-input"},
    }


def _request(selection_mode: str = "HUMAN_APPROVAL") -> dict:
    return {
        "schema": "garment.body-proxy.request.v1",
        "source": {
            "image_digest": "sha256:clothed-front-image",
            "width": 1200,
            "height": 1800,
            "orientation": "UP",
        },
        "selection_mode": selection_mode,
        "dimensions": {
            "height": _dimension(168, "MEASURED", "TAPE_MEASURE"),
            "chest": _dimension(94, "REQUESTED", "USER_REQUEST"),
            "waist": _dimension(74, "MEASURED", "CLOTHED_PHOTO"),
            "hip": _dimension(99, "MEASURED", "BODY_SCAN"),
        },
        "pose_keypoints_2d": {
            "left_shoulder": {
                "x": 0.39, "y": 0.22, "confidence": 0.91,
                "state": "PROPOSED",
            },
            "right_shoulder": {
                "x": 0.61, "y": 0.22, "confidence": 0.9,
                "state": "PROPOSED",
            },
            "left_ankle": {
                "x": 0.45, "y": 0.91, "confidence": 0.88,
                "state": "PROPOSED",
            },
        },
        "exposed_skin_contours": [{
            "contour_id": "face-outline",
            "body_region": "FACE",
            "points": [[0.46, 0.05], [0.54, 0.05], [0.55, 0.15]],
            "state": "HUMAN_CONFIRMED",
        }],
        "mask_candidates": [
            {
                "candidate_id": "garment-mask-a", "kind": "GARMENT",
                "mask_digest": "sha256:garment-mask", "confidence": 0.87,
                "state": "HUMAN_CONFIRMED",
            },
            {
                "candidate_id": "body-mask-a", "kind": "BODY",
                "mask_digest": "sha256:body-mask", "confidence": 0.72,
                "state": "PROPOSED",
            },
        ],
        "camera": {
            "width_px": 1200, "height_px": 1800,
            "scale_cm_per_px": 0.1,
            "orientation": "UP", "authority": "OBSERVED",
        },
    }


def _rpc(method: str, request_id: int, params: dict | None = None) -> dict:
    row = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        row["params"] = params
    return row


def _stdio(*messages: dict) -> list[dict]:
    with tempfile.TemporaryDirectory() as temp_home:
        environment = os.environ.copy()
        environment["PHOTOLOSET_HOME"] = temp_home
        completed = subprocess.run(
            [sys.executable, "-m", "photoloset.mcp"],
            cwd=REPO_ROOT,
            env=environment,
            input="".join(json.dumps(message) + "\n" for message in messages),
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    if completed.returncode:
        raise AssertionError(completed.stderr)
    return [json.loads(line) for line in completed.stdout.splitlines() if line]


class BodyProxyTests(unittest.TestCase):
    maxDiff = None

    def test_returns_multiple_typed_candidates_and_separates_authorities(self) -> None:
        result = body_proxy.propose_body_proxy(_request())

        self.assertEqual(result["verdict"], "PROPOSED_BODY_PROXY_CANDIDATES")
        self.assertEqual(len(result["candidates"]), 3)
        self.assertTrue(result["provider"]["fallback_used"])
        self.assertFalse(result["provider"]["external_model_used"])
        measured = {
            row["dimension"] for row in result["claim_partitions"]["MEASURED"]
        }
        requested = {
            row["dimension"] for row in result["claim_partitions"]["REQUESTED"]
        }
        inferred = {
            row.get("dimension") for row in result["claim_partitions"]["INFERRED"]
        }
        self.assertEqual(measured, {"height", "hip"})
        self.assertEqual(requested, {"chest_bust"})
        self.assertIn("waist", inferred)
        self.assertNotIn("waist", measured)
        self.assertIn(
            "REVIEW_CLOTHED_DIMENSION_DOWNGRADED",
            {row["code"] for row in result["review_items"]},
        )
        self.assertIsNone(result["selection"]["selected_candidate_id"])
        self.assertEqual(result["selection"]["status"], "HUMAN_APPROVAL_REQUIRED")
        self.assertTrue(result["human_approval_required"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertEqual(result["fact_promotions"], [])

    def test_rear_ranges_and_avatar_binding_remain_proposed(self) -> None:
        result = body_proxy.propose_body_proxy(_request())
        depths = set()
        for candidate in result["candidates"]:
            self.assertEqual(candidate["state"], "PROPOSED_BODY_PROXY")
            rear = candidate["rear_generation_constraints"]
            self.assertFalse(rear["rear_surface_observed"])
            self.assertIn("chest_bust", rear["dimensions_cm"])
            self.assertIn("waist", rear["dimensions_cm"])
            avatar = candidate["avatar_binding"]
            self.assertEqual(avatar["authority"], "PROPOSED_PREVIEW")
            self.assertEqual(avatar["kind"], "PARAMETRIC_GAME_AVATAR")
            self.assertTrue(avatar["geometry_digest"])
            self.assertTrue(avatar["not_a_target_wearer_measurement"])
            self.assertFalse(candidate["manufacturing_certified"])
            depths.add(rear["rear_depth_share"])
        self.assertEqual(depths, {0.46, 0.5, 0.54})

    def test_auto_selection_is_only_proposed_and_never_manufacturing_approval(self) -> None:
        result = body_proxy.propose_body_proxy(_request("AUTO_PROPOSED"))
        self.assertEqual(result["selection"]["status"], "AUTO_PROPOSED_SELECTED")
        self.assertEqual(
            result["selection"]["selected_candidate_id"],
            result["candidates"][0]["candidate_id"],
        )
        self.assertEqual(result["selection"]["authority"], "PROPOSED_BODY_PROXY")
        self.assertFalse(result["selection"]["may_open_manufacturing_gate"])
        self.assertTrue(result["selection"]["human_can_override"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["human_approval_required"])

    def test_no_optional_evidence_still_returns_typed_bounded_fallback(self) -> None:
        result = body_proxy.propose_body_proxy({
            "schema": "garment.body-proxy.request.v1",
            "source": {"image_digest": "sha256:fallback-only"},
        })
        self.assertEqual(len(result["candidates"]), 3)
        self.assertEqual(result["camera"]["state"], "UNKNOWN")
        self.assertEqual(
            result["dimension_ranges_cm"]["waist"]["authority"], "INFERRED")
        inferred_dimensions = {
            row.get("dimension")
            for row in result["claim_partitions"]["INFERRED"]
        }
        self.assertEqual(inferred_dimensions, {
            "height", "chest_bust", "waist", "hip", "shoulder",
            "body_length", "inseam",
        })
        review_codes = {row["code"] for row in result["review_items"]}
        self.assertIn("REVIEW_BODY_MASK_REQUIRED", review_codes)
        self.assertIn("REVIEW_GARMENT_MASK_REQUIRED", review_codes)

    def test_is_deterministic_and_input_order_stable(self) -> None:
        request = _request()
        reordered = copy.deepcopy(request)
        reordered["dimensions"] = dict(reversed(list(
            reordered["dimensions"].items())))
        reordered["pose_keypoints_2d"] = dict(reversed(list(
            reordered["pose_keypoints_2d"].items())))
        reordered["mask_candidates"].reverse()
        self.assertEqual(
            body_proxy.propose_body_proxy(request),
            body_proxy.propose_body_proxy(reordered),
        )

    def test_invalid_values_and_false_measurement_sources_stop_typed(self) -> None:
        non_finite = _request()
        non_finite["pose_keypoints_2d"]["left_shoulder"]["x"] = math.nan
        self.assertEqual(
            body_proxy.propose_body_proxy(non_finite)["verdict"],
            "UNKNOWN_BODY_PROXY_NON_FINITE",
        )
        false_measurement = _request()
        false_measurement["dimensions"]["height"]["source"]["kind"] = "UNKNOWN_MODEL"
        self.assertEqual(
            body_proxy.propose_body_proxy(false_measurement)["verdict"],
            "UNKNOWN_BODY_PROXY_MEASUREMENT_SOURCE",
        )
        invalid_schema = _request()
        invalid_schema["schema"] = "wrong"
        self.assertEqual(
            body_proxy.propose_body_proxy(invalid_schema)["verdict"],
            "UNKNOWN_BODY_PROXY_SCHEMA",
        )

    def test_mcp_stdio_initialize_list_and_call(self) -> None:
        self.assertIn(TOOL_NAME, mcp.TOOLS)
        responses = _stdio(
            _rpc("initialize", 1),
            _rpc("tools/list", 2),
            _rpc("tools/call", 3, {
                "name": TOOL_NAME,
                "arguments": {"json_text": json.dumps(_request())},
            }),
        )
        self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "photoloset")
        names = {row["name"] for row in responses[1]["result"]["tools"]}
        self.assertIn(TOOL_NAME, names)
        result = json.loads(responses[2]["result"]["content"][0]["text"])
        self.assertEqual(result["verdict"], "PROPOSED_BODY_PROXY_CANDIDATES")
        self.assertEqual(result["mcp_request_schema"],
                         "garment.body-proxy.request.v1")
        self.assertFalse(result["manufacturing_ready"])


if __name__ == "__main__":
    unittest.main()
