#!/usr/bin/env python3
import json
import unittest

from photoloset import garment_structure as structure


def valid_spec():
    return {
        "schema": "garment.structure.v1",
        "nodes": [
            {"node_id": "bodice", "kind": "BODY_SHELL",
             "dimensions": {"height_cm": 40.0, "circumference_cm": 80.0},
             "ports": [{"port_id": "waist", "length_cm": 80.0,
                        "interface": "waist", "role": "loop"}]},
            {"node_id": "skirt", "kind": "FRUSTUM",
             "dimensions": {"height_cm": 60.0, "top_circumference_cm": 80.0,
                            "bottom_circumference_cm": 180.0},
             "ports": [{"port_id": "waist", "length_cm": 80.0,
                        "interface": "waist", "role": "loop"}]},
        ],
        "operations": [{"operation_id": "waist_join", "kind": "JOIN",
                        "source": {"node_id": "bodice", "port_id": "waist"},
                        "target": {"node_id": "skirt", "port_id": "waist"}}],
    }


class GarmentStructureTests(unittest.TestCase):
    def test_public_build_and_validate_are_json(self):
        built = structure.build(valid_spec())
        self.assertEqual(built["verdict"], "ANSWER")
        self.assertEqual(built["schema"], "garment.structure.v1")
        self.assertEqual(built["digest"], structure.validate(built["graph"])["digest"])
        json.dumps(built, allow_nan=False)

    def test_missing_geometry_fails_closed(self):
        spec = valid_spec()
        del spec["nodes"][1]["dimensions"]["height_cm"]
        result = structure.build(spec)
        self.assertEqual(result["verdict"], "UNKNOWN_PRIMITIVE_DIMENSION_MISSING")
        self.assertNotIn("graph", result)

    def test_join_length_and_interface_are_measured(self):
        spec = valid_spec()
        spec["nodes"][1]["ports"][0]["length_cm"] = 81.0
        self.assertEqual(structure.build(spec)["verdict"], "UNKNOWN_JOIN_LENGTH_MISMATCH")
        spec = valid_spec()
        spec["nodes"][1]["ports"][0]["interface"] = "neck"
        self.assertEqual(structure.build(spec)["verdict"], "UNKNOWN_INTERFACE_MISMATCH")

    def test_unknown_primitive_is_not_coerced(self):
        spec = valid_spec()
        spec["nodes"][0]["kind"] = "DRESS"
        self.assertEqual(structure.build(spec)["verdict"], "UNKNOWN_MALFORMED_STRUCTURE")


if __name__ == "__main__":
    unittest.main()
