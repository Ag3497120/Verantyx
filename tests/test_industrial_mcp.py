# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from pathlib import Path

from photoloset import mcp
from tests.test_industrial_solver import request


def decoded(value):
    return json.loads(value)


class IndustrialMCPTests(unittest.TestCase):
    def test_integrated_capability_and_simulation_doors(self):
        capability = decoded(mcp.industrial_cloth_capabilities())
        self.assertEqual(capability["verdict"], "ANSWER")
        self.assertFalse(capability["industrial_completion"])
        result = decoded(mcp.industrial_cloth_simulate(json.dumps(request())))
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["stages"]["xpbd"]["verdict"], "ANSWER")

    def test_calibration_and_comfort_refuse_empty_records(self):
        calibration = decoded(mcp.material_calibrate("{}"))
        comfort = decoded(mcp.comfort_evaluate("{}"))
        self.assertTrue(calibration["verdict"].startswith("UNKNOWN_"))
        self.assertTrue(comfort["verdict"].startswith("UNKNOWN_"))

    def test_default_candidate_catalog_can_commit_metadata_only(self):
        with tempfile.TemporaryDirectory() as directory:
            result = decoded(mcp.corpus_catalog_ingest(
                index_path=directory, commit=True))
            self.assertEqual(result["verdict"], "ANSWER")
            self.assertEqual(result["payloads_installed"], 0)
            self.assertEqual(result["writes"], 3)
            self.assertTrue((Path(directory) / "index.json").exists())


if __name__ == "__main__":
    unittest.main()
