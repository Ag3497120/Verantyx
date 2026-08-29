# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

from scripts import evaluate_fashion_crops_20 as evaluator


RGB = tuple[int, int, int]


def _write_png(path: Path, width: int, height: int, predicate,
               *, background: RGB = (238, 238, 238),
               foreground: RGB = (54, 93, 131)) -> None:
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            row.extend(foreground if predicate(x, y) else background)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind)
        checksum = zlib.crc32(payload, checksum) & 0xFFFFFFFF
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", checksum))

    payload = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(payload)


def _portrait(x: int, y: int) -> bool:
    return 23 <= x <= 40 and 12 <= y <= 114


def _landscape(x: int, y: int) -> bool:
    return 12 <= x <= 114 and 23 <= y <= 40


def _diagonal(x: int, y: int) -> bool:
    return 10 <= x <= 85 and abs(y - x) <= 7


def _walk_values(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)
    else:
        yield value


class FashionCrops20EvaluationTests(unittest.TestCase):
    maxDiff = None

    def test_portrait_landscape_and_diagonal_geometry_are_aggregated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_png(root / "first.png", 64, 128, _portrait)
            _write_png(root / "second.png", 128, 64, _landscape)
            _write_png(root / "third.png", 96, 96, _diagonal)

            report = evaluator.evaluate_directory(root)

        self.assertEqual("ANSWER", report["verdict"])
        summary = report["summary"]
        self.assertEqual(3, summary["input_count"])
        self.assertEqual(3, summary["readable_input_count"])
        self.assertEqual({
            "DIAGONAL": 1, "HORIZONTAL": 1, "VERTICAL": 1,
        }, summary["foreground_axis_counts"])
        self.assertEqual(3, summary["items_reaching_3d_and_pattern_count"])
        self.assertGreaterEqual(summary["foreground_candidate_count"], 3)
        self.assertGreaterEqual(summary["geometric_part_candidate_count"], 3)
        self.assertGreaterEqual(summary["candidate_3d_success_count"], 6)
        self.assertEqual(summary["candidate_3d_success_count"],
                         summary["pattern_success_count"])

    def test_filename_labels_are_not_semantic_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "female_red_skirt.png"
            second = root / "male_blue_shirt.png"
            _write_png(first, 64, 128, _portrait)
            second.write_bytes(first.read_bytes())

            left = evaluator.evaluate_image(first, source_slot=0)
            right = evaluator.evaluate_image(second, source_slot=0)

        self.assertEqual(left, right)
        serialised = json.dumps(left, ensure_ascii=False).lower()
        for token in ("female_red_skirt", "male_blue_shirt"):
            self.assertNotIn(token, serialised)
        self.assertFalse(left["source_filename_used_for_inference"])

    def test_named_colours_and_class_rules_do_not_control_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "one.png"
            second = root / "two.png"
            _write_png(
                first, 64, 128, _portrait,
                background=(248, 232, 216), foreground=(48, 82, 126),
            )
            _write_png(
                second, 64, 128, _portrait,
                background=(24, 39, 57), foreground=(221, 187, 142),
            )
            report = evaluator.evaluate_directory(root)

        self.assertFalse(report["policy"]["named_colour_rules"])
        self.assertFalse(report["policy"]["garment_class_rules"])
        self.assertEqual({"VERTICAL": 2},
                         report["summary"]["foreground_axis_counts"])
        shapes = []
        for item in report["items"]:
            foreground = item["foreground"]
            shapes.append((
                foreground["candidate_count"],
                tuple(row["role"] for row in foreground["candidates"]),
                tuple(run["part_candidates"]["candidate_count"]
                      for run in item["candidate_runs"]),
                tuple(run["structure_artifacts"]["candidate_count"]
                      for run in item["candidate_runs"]),
            ))
        self.assertEqual(shapes[0], shapes[1])

    def test_every_structure_candidate_has_distinct_3d_and_pattern_or_typed_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "anonymous.png"
            _write_png(path, 64, 128, _portrait)
            item = evaluator.evaluate_image(path)

        self.assertEqual("PROPOSED_3D_AND_PATTERN_CANDIDATES",
                         item["terminal"]["state"])
        for run in item["candidate_runs"]:
            self.assertIn(run["target_3d"]["verdict"], {
                "PROPOSED_TARGET_3D", "UNKNOWN_TARGET_3D",
            })
            artifacts = run["structure_artifacts"]["candidates"]
            self.assertGreaterEqual(len(artifacts), 2)
            preview_digests = set()
            pattern_digests = set()
            for artifact in artifacts:
                preview = artifact["candidate_3d"]
                pattern = artifact["pattern"]
                self.assertTrue(
                    preview.get("verdict") == "ANSWER"
                    or preview.get("typed_stop") is True)
                self.assertTrue(
                    pattern.get("verdict") == "ANSWER"
                    or pattern.get("typed_stop") is True)
                if preview.get("verdict") == "ANSWER":
                    preview_digests.add(preview["preview_digest"])
                if pattern.get("verdict") == "ANSWER":
                    pattern_digests.add(pattern["pattern_digest"])
            self.assertEqual(len(preview_digests), len([
                row for row in artifacts
                if row["candidate_3d"].get("verdict") == "ANSWER"
            ]))
            self.assertEqual(len(pattern_digests), len([
                row for row in artifacts
                if row["pattern"].get("verdict") == "ANSWER"
            ]))

    def test_appearance_never_asserts_gender_or_person_attributes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ambiguous-person-label.png"
            _write_png(path, 64, 128, _portrait)
            item = evaluator.evaluate_image(path)

        self.assertEqual("NOT_PERFORMED", item["gender_inference"])
        self.assertEqual("NOT_PERFORMED", item["person_attribute_inference"])
        string_values = {value.lower() for value in _walk_values(item)
                         if isinstance(value, str)}
        self.assertFalse({"female", "male", "woman", "man"} & string_values)
        self.assertFalse(item["rear_observed"])
        self.assertFalse(item["material_observed"])

    def test_unreadable_input_is_counted_as_a_typed_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "broken.png").write_bytes(b"not a png")
            report = evaluator.evaluate_directory(root)

        self.assertEqual("ANSWER_WITH_TYPED_STOPS", report["verdict"])
        self.assertEqual(1, report["summary"]["input_count"])
        self.assertEqual(1, report["summary"]["typed_input_stop_count"])
        item = report["items"][0]
        self.assertTrue(item["input"]["typed_stop"])
        self.assertEqual("UNKNOWN_INPUT_FORMAT", item["input"]["verdict"])
        self.assertEqual(["UNKNOWN_INPUT_FORMAT"],
                         item["terminal"]["typed_stop_codes"])

    def test_small_image_is_bounded_to_proposal_or_typed_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "small.png"
            _write_png(path, 12, 18,
                       lambda x, y: 4 <= x <= 7 and 3 <= y <= 15)
            item = evaluator.evaluate_image(path)
        self.assertEqual("ANSWER_READABLE_IMAGE", item["input"]["verdict"])
        self.assertIn(item["terminal"]["state"], {
            "PROPOSED_3D_AND_PATTERN_CANDIDATES", "TYPED_STOP",
        })

    def test_runtime_imports_no_network_or_model_packages(self):
        code = (
            "import json, sys; "
            "import scripts.evaluate_fashion_crops_20; "
            "print(json.dumps({name: (name in sys.modules) for name in "
            "['requests','urllib.request','transformers','open_clip']}))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code], check=True, text=True,
            capture_output=True,
        )
        self.assertEqual({
            "requests": False,
            "urllib.request": False,
            "transformers": False,
            "open_clip": False,
        }, json.loads(completed.stdout))

    def test_evaluation_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_png(root / "a.png", 64, 128, _portrait)
            _write_png(root / "b.png", 96, 96, _diagonal)
            first = evaluator.evaluate_directory(root)
            second = evaluator.evaluate_directory(root)
        self.assertEqual(first, second)


MANIFEST_PATH = Path(__file__).parent / "fixtures/fashion_crops_20_manifest.json"
DATASET_ROOT = Path("/Users/motonishikoudai/Desktop/vera_fashion_crops_20")


class FashionCrops20ManifestTests(unittest.TestCase):
    def test_manifest_enumerates_exactly_twenty_provided_group_records(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        rows = manifest["images"]
        expected = {
            *(f"female_{index:02d}.png" for index in range(1, 11)),
            *(f"male_{index:02d}.png" for index in range(1, 11)),
        }
        self.assertEqual(20, len(rows))
        self.assertEqual(expected, {row["file"] for row in rows})
        counts = {}
        for row in rows:
            counts[row["provided_file_group"]] = (
                counts.get(row["provided_file_group"], 0) + 1)
        self.assertEqual({"female": 10, "male": 10}, counts)
        self.assertEqual(
            "DATASET_FILENAME_METADATA_NOT_APPEARANCE_INFERENCE",
            manifest["group_authority"],
        )


@unittest.skipUnless(DATASET_ROOT.is_dir(), "20-crop evaluation set is not installed")
class InstalledFashionCrops20EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = sorted(DATASET_ROOT.glob("*.png"))
        cls.report = evaluator.evaluate_paths(cls.paths)
        cls.item_by_digest = {
            row["input"]["content_digest"]: row
            for row in cls.report["items"]
        }

    @classmethod
    def _cached_eval(cls, path, *, source_slot=0):
        digest = evaluator._digest(Path(path).read_bytes())
        result = copy.deepcopy(cls.item_by_digest[digest])
        result["source_slot"] = source_slot
        return result

    def test_all_twenty_are_enumerated_and_groups_are_external_metadata(self):
        self.assertEqual(20, len(self.paths))
        self.assertEqual(20, self.report["summary"]["input_count"])
        self.assertEqual(20, len(self.report["enumerated_inputs"]))
        self.assertEqual(
            {"female": 10, "male": 10},
            self.report["summary"]["provided_file_group_counts"],
        )
        self.assertTrue(self.report["summary"][
            "provided_file_groups_are_not_appearance_inference"])
        self.assertTrue(all(
            row["used_for_inference"] is False
            for row in self.report["enumerated_inputs"]
        ))
        self.assertTrue(all(
            row["gender_inference"] == "NOT_PERFORMED"
            for row in self.report["items"]
        ))

    def test_dual_modes_view_proxy_and_authority_boundaries_are_reported(self):
        self.assertEqual(
            20,
            self.report["summary"]["mode_typed_stop_counts"][
                "UNKNOWN_HUMAN_AUDIT_CONFIRMATION_REQUIRED"],
        )
        self.assertEqual(
            {"FRONT_LIKE", "OBLIQUE_LIKE"},
            set(self.report["summary"]["front_or_oblique_proxy_counts"]),
        )
        for row in self.report["items"]:
            modes = row["evaluation_modes"]
            self.assertIn("AUTO_PROPOSED", modes)
            self.assertIn("HUMAN_AUDIT", modes)
            self.assertTrue(modes["HUMAN_AUDIT"]["typed_stop"])
            self.assertFalse(row["front_or_oblique_proxy"][
                "camera_viewpoint_observed"])
            self.assertFalse(row["authority_audit"]["rear_observed"])

    def test_existing_stages_run_and_failures_remain_visible(self):
        summary = self.report["summary"]
        self.assertEqual(20, summary["items_reaching_3d_and_pattern_count"])
        self.assertGreater(summary["foreground_candidate_count"], 0)
        self.assertGreater(summary["geometric_part_candidate_count"], 0)
        self.assertGreater(summary["target_3d_proposal_count"], 0)
        self.assertEqual(summary["candidate_3d_success_count"],
                         summary["pattern_success_count"])
        self.assertTrue(summary["parts_ir_pipeline_verdict_counts"])
        self.assertEqual(
            {"PROPOSED"}, set(summary["front_region_pipeline_verdict_counts"]),
        )
        self.assertIn("UNRESOLVED", summary["parts_ir_pipeline_verdict_counts"])
        self.assertEqual(0, summary["manufacturing_ready_overclaim_item_count"])
        self.assertIn("generic_trapezoid_fallback_item_count", summary)
        self.assertTrue(summary["rear_authority_counts"])
        self.assertNotIn("OBSERVED", summary["rear_authority_counts"])

    def test_structure_diversity_is_classified_without_filename_rules(self):
        summary = self.report["summary"]
        self.assertGreaterEqual(summary["structure_family_count"], 2)
        self.assertGreaterEqual(len(summary["construction_regime_counts"]), 1)
        self.assertFalse(self.report["policy"]["filename_used_for_inference"])
        self.assertFalse(self.report["policy"]["named_colour_rules"])
        self.assertFalse(self.report["policy"]["garment_class_rules"])

    def test_digest_is_order_independent_for_the_twenty_inputs(self):
        with mock.patch.object(
                evaluator, "evaluate_image", side_effect=self._cached_eval):
            forward = evaluator.evaluate_paths(self.paths)
            reverse = evaluator.evaluate_paths(list(reversed(self.paths)))
        self.assertEqual(forward["evaluation_digest"],
                         reverse["evaluation_digest"])
        self.assertEqual(forward["summary"], reverse["summary"])

    def test_removing_any_one_record_does_not_change_common_semantics(self):
        removed = self.paths[len(self.paths) // 2]
        reduced_paths = [path for path in self.paths if path != removed]
        removed_digest = evaluator._digest(removed.read_bytes())
        with mock.patch.object(
                evaluator, "evaluate_image", side_effect=self._cached_eval):
            reduced = evaluator.evaluate_paths(reduced_paths)
        self.assertEqual(19, reduced["summary"]["input_count"])
        self.assertEqual(19, len(reduced["enumerated_inputs"]))
        expected = {
            row["semantic_digest"] for digest, row in self.item_by_digest.items()
            if digest != removed_digest
        }
        self.assertEqual(expected, {
            row["semantic_digest"] for row in reduced["items"]
        })
        self.assertGreaterEqual(reduced["summary"]["structure_family_count"], 2)


if __name__ == "__main__":
    unittest.main()
