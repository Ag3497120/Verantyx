#!/usr/bin/env python3
import copy
import json
import unittest

from photoloset import pattern_transforms


def rectangle():
    return {"piece_id": "front", "outline": [[0, 0], [10, 0], [10, 20], [0, 20]]}


class PatternTransformTests(unittest.TestCase):
    def test_pleat_is_measured_and_preserves_outline_addresses(self):
        before = rectangle()
        result = pattern_transforms.apply(before, {
            "kind": "PLEAT", "edge": "e0", "count": 2, "depth_cm": 1.0,
            "finished_length_cm": 6.0,
        })
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["transform"]["take_up_cm"], 4.0)
        self.assertEqual(result["after"]["outline"], before["outline"])
        self.assertNotEqual(result["before_digest"], result["after_digest"])
        json.dumps(result, allow_nan=False)

    def test_gather_ratio_is_not_guessed(self):
        ok = pattern_transforms.apply(rectangle(), {
            "kind": "GATHER", "edge": 0, "finished_length_cm": 5.0, "ratio": 2.0})
        self.assertEqual(ok["verdict"], "ANSWER")
        bad = pattern_transforms.apply(rectangle(), {
            "kind": "GATHER", "edge": 0, "finished_length_cm": 5.0, "ratio": 1.5})
        self.assertEqual(bad["verdict"], "UNKNOWN_GATHER_RATIO_MISMATCH")

    def test_dart_uses_existing_geometry_and_does_not_edit_outline(self):
        before = rectangle()
        result = pattern_transforms.apply(before, {
            "kind": "DART", "edge": "e0", "t": 0.5,
            "intake_cm": 2.0, "depth_cm": 5.0})
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertFalse(result["transform"]["geometry"]["developable"])
        self.assertEqual(result["after"]["outline"], before["outline"])

    def test_fold_outside_and_impossible_pleat_fail_closed(self):
        fold = pattern_transforms.apply(rectangle(), {
            "kind": "FOLD", "start": [2, 2], "end": [12, 2], "direction": "valley"})
        self.assertEqual(fold["verdict"], "UNKNOWN_FOLD_OUTSIDE_PANEL")
        pleat = pattern_transforms.apply(rectangle(), {
            "kind": "PLEAT", "edge": "e0", "count": 2, "depth_cm": 3})
        self.assertEqual(pleat["verdict"], "UNKNOWN_PLEAT_EXCEEDS_EDGE")

    def test_input_is_immutable_and_unknown_operation_refused(self):
        before = rectangle()
        frozen = copy.deepcopy(before)
        result = pattern_transforms.apply(before, {"kind": "SHIRR", "edge": "e0"})
        self.assertEqual(result["verdict"], "UNKNOWN_PATTERN_OPERATION")
        self.assertEqual(before, frozen)


if __name__ == "__main__":
    unittest.main()
