#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Candidate-artifact cardinality audit for bilateral layered sleeves."""
import unittest
from unittest.mock import patch

from photoloset import garment_structure
from photoloset import parts_ir_pipeline as pipeline
from photoloset.parts_ir_completion import bounded_preview_profile


def _part(part_id, kind, dimensions, **semantics):
    row = {
        "part_id": part_id,
        "kind": kind,
        "layer": semantics.pop("layer", 0),
        "placement": semantics.pop("placement", "visible front"),
        "visible_basis": {
            "state": "PROPOSED",
            "basis": f"front image proposes {part_id}",
            "breaks_when": "another view or construction review contradicts it",
        },
        "dimensions": dimensions,
    }
    row.update(semantics)
    return row


def _candidate(candidate_id, circumference):
    return {
        "candidate_id": candidate_id,
        "state": "PROPOSED",
        "parts": [
            _part("body", "BODY_SHELL", {
                "height_cm": 44.0,
                "circumference_cm": circumference,
                "bottom_circumference_cm": circumference - 14.0,
            }, garment_unit="layered-look"),
            _part("inner-sleeve", "SLEEVE", {
                "length_cm": 44.0,
                "upper_circumference_cm": 34.0,
                "cuff_circumference_cm": 20.0,
            }, layer=1, placement="both arms", garment_unit="layered-look",
                  attached_to="body", side="bilateral", shape="set_in",
                  quantity=2),
            _part("outer-sleeve", "SLEEVE", {
                "length_cm": 32.0,
                "upper_circumference_cm": 40.0,
                "cuff_circumference_cm": 26.0,
            }, layer=2, placement="outer arm layer",
                  garment_unit="layered-look", attached_to="inner-sleeve",
                  side="bilateral", detail_role="oversleeve",
                  attachment_relation="LAYER", quantity=2),
        ],
    }


def _source():
    return {
        "schema": "garment.parts-ir.v1",
        "state": "PROPOSED",
        "candidates": [
            _candidate("layered-a", 92.0),
            _candidate("layered-b", 98.0),
        ],
    }


def _run():
    return pipeline.run_parts_ir_pipeline(
        _source(), preview_profile=bounded_preview_profile(),
        radial_segments=8)


def _reseal(value):
    value.pop("digest", None)
    value["digest"] = garment_structure.semantic_digest(value)
    return value


class PartsIRPipelineSleeveInstanceAuditTests(unittest.TestCase):
    maxDiff = None

    def test_every_candidate_preserves_bilateral_layer_instances_and_relations(self):
        first = _run()
        second = _run()
        self.assertEqual(first["verdict"], "PROPOSED", first["failures"])
        self.assertEqual(second["verdict"], "PROPOSED", second["failures"])

        expected_instances = {
            f"source_node_id={node}|side={side}|instance_id={node}:{side}"
            for node in ("inner-sleeve", "outer-sleeve")
            for side in ("left", "right")
        }
        expected_relations = {
            ("operation_id=layer-outer-sleeve-on-inner-sleeve|kind=LAYER|"
             f"side={side}|source=outer-sleeve:{side}|"
             f"target=inner-sleeve:{side}")
            for side in ("left", "right")
        }
        for before, after in zip(first["candidates"], second["candidates"]):
            audit = before["part_preservation"]["instance_preservation"]
            self.assertTrue(audit["required"])
            self.assertTrue(audit["all_required_artifacts_preserved"])
            self.assertEqual(
                {row["key"] for row in audit["expected_instances"]},
                expected_instances)
            self.assertEqual(
                {row["key"] for row in audit["expected_relations"]},
                expected_relations)
            for name, stage in audit["stages"].items():
                with self.subTest(candidate=before["candidate_id"], stage=name):
                    self.assertTrue(stage["preserved"], stage)
                    self.assertEqual(set(stage["represented_instance_keys"]),
                                     expected_instances)
                    if name in {"preview_3d", "flat_pattern", "sewing_plan"}:
                        self.assertEqual(set(stage["represented_relation_keys"]),
                                         expected_relations)
            compact = before["manufacturing_preview"]
            sleeve_pieces = [piece for piece in compact["pieces"]
                             if piece.get("source_node_id") in {
                                 "inner-sleeve", "outer-sleeve"}]
            self.assertEqual(
                {piece["instance_lineage"]["key"] for piece in sleeve_pieces},
                expected_instances)
            sewing = before["sewing_plan"]
            self.assertEqual(
                {row["key"] for row in sewing["instance_lineage_records"]},
                expected_instances)
            self.assertEqual(before["artifact_binding"][
                "instance_preservation_digest"], audit["digest"])
            self.assertEqual(audit["digest"], after["part_preservation"][
                "instance_preservation"]["digest"])

    def test_preview_source_node_set_cannot_hide_a_collapsed_right_instance(self):
        real_generate = pipeline.structure_preview.generate_preview

        def collapsed_preview(*args, **kwargs):
            result = real_generate(*args, **kwargs)
            for part in result.get("parts", []):
                if part.get("source_node_id") == "outer-sleeve":
                    part["instances"] = [row for row in part["instances"]
                                         if row.get("side") == "left"]
            result["sleeve_relation_coverage"] = [
                row for row in result.get("sleeve_relation_coverage", [])
                if not (row.get("source_node_id") == "outer-sleeve"
                        and row.get("side") == "right")]
            return result

        with patch.object(pipeline.structure_preview, "generate_preview",
                          side_effect=collapsed_preview):
            result = _run()
        self.assertEqual(result["verdict"], "UNRESOLVED")
        for row in result["candidates"]:
            self.assertEqual(
                row["verdict"],
                "UNKNOWN_PARTS_IR_PIPELINE_INSTANCE_LINEAGE_DROPPED")
            audit = row["part_preservation"]["instance_preservation"]
            self.assertFalse(audit["stages"]["preview_3d"]["preserved"])
            self.assertIn(
                "source_node_id=outer-sleeve|side=right|instance_id=outer-sleeve:right",
                audit["stages"]["preview_3d"]["missing_instance_keys"])
            self.assertTrue(row["part_preservation"]["source_node_set_preserved"])

    def test_cutting_and_sewing_must_keep_exact_right_layer_addresses(self):
        real_build = pipeline.pattern_manufacturing_bundle.build
        real_plan = pipeline.structure_sewing_plan.plan

        def collapsed_cutting(*args, **kwargs):
            result = real_build(*args, **kwargs)
            result["pieces"] = [
                piece for piece in result.get("pieces", [])
                if piece.get("piece_id") != "outer-sleeve:right"]
            return _reseal(result)

        def collapsed_sewing(*args, **kwargs):
            result = real_plan(*args, **kwargs)
            result["steps"] = [
                step for step in result.get("steps", [])
                if step.get("operation_id")
                != "layer-outer-sleeve-on-inner-sleeve:right"]
            return _reseal(result)

        with patch.object(pipeline.pattern_manufacturing_bundle, "build",
                          side_effect=collapsed_cutting):
            cutting = _run()
        for row in cutting["candidates"]:
            self.assertEqual(
                row["verdict"],
                "UNKNOWN_PARTS_IR_PIPELINE_INSTANCE_LINEAGE_DROPPED")
            stage = row["part_preservation"]["instance_preservation"][
                "stages"]["manufacturing_preview"]
            self.assertIn(
                "source_node_id=outer-sleeve|side=right|instance_id=outer-sleeve:right",
                stage["missing_instance_keys"])

        with patch.object(pipeline.structure_sewing_plan, "plan",
                          side_effect=collapsed_sewing):
            sewing = _run()
        for row in sewing["candidates"]:
            self.assertEqual(
                row["verdict"],
                "UNKNOWN_PARTS_IR_PIPELINE_INSTANCE_LINEAGE_DROPPED")
            stage = row["part_preservation"]["instance_preservation"][
                "stages"]["sewing_plan"]
            self.assertIn(
                ("operation_id=layer-outer-sleeve-on-inner-sleeve|kind=LAYER|"
                 "side=right|source=outer-sleeve:right|"
                 "target=inner-sleeve:right"),
                stage["missing_relation_keys"])


if __name__ == "__main__":
    unittest.main()
