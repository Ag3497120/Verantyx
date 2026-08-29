#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest

from photoloset import corpus_manifest as manifest


def fixture():
    return {
        "schema": manifest.SCHEMA,
        "name": "fixture",
        "version": "1",
        "license": {
            "spdx": "CC-BY-4.0",
            "url": "https://example.invalid/license",
            "rights": {"commercial_use": "allowed",
                       "derivatives": "allowed",
                       "redistribution": "allowed"},
        },
        "lineage": [{"source": "fixture-root", "generated": False}],
        "modalities": ["patterns_2d", "sewing_construction"],
        "record_format": {"units": "SI", "schema_url": "schema.json"},
    }


class CorpusManifestTests(unittest.TestCase):
    def test_commercial_manifest_is_digest_bound(self):
        src = fixture()
        before = copy.deepcopy(src)
        got = manifest.validate(src, purpose="sewing")
        self.assertEqual(got["verdict"], manifest.ANSWER)
        self.assertTrue(got["construction_bearing"])
        self.assertEqual(src, before)
        changed = fixture(); changed["version"] = "2"
        self.assertNotEqual(got["digest"], manifest.validate(changed)["digest"])

    def test_free_download_does_not_mean_commercial_permission(self):
        src = fixture()
        src["license"]["rights"]["commercial_use"] = "unknown"
        got = manifest.validate(src)
        self.assertEqual(got["verdict"], manifest.RIGHTS_UNKNOWN)
        self.assertTrue(got["legal_review_required"])

    def test_image_only_corpus_cannot_answer_sewing(self):
        src = fixture(); src["modalities"] = ["garment_images"]
        got = manifest.validate(src, purpose="sewing")
        self.assertEqual(got["verdict"], manifest.UNSUPPORTED_MODALITY)

    def test_lineage_and_units_are_required(self):
        src = fixture(); src["lineage"] = []
        self.assertEqual(manifest.validate(src)["verdict"],
                         manifest.LINEAGE_UNKNOWN)
        src = fixture(); src["record_format"]["units"] = "pixels maybe"
        self.assertEqual(manifest.validate(src)["verdict"],
                         manifest.BAD_MANIFEST)

    def test_expected_fields_are_typed(self):
        got = manifest.expected_record_fields("material_measurements")
        self.assertIn("uncertainty", got["required_fields"])
        self.assertEqual(manifest.expected_record_fields("embedding")["verdict"],
                         manifest.UNSUPPORTED_MODALITY)


if __name__ == "__main__":
    unittest.main()
