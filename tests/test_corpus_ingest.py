import copy
import json
from pathlib import Path
import tempfile
import unittest

from photoloset import corpus_ingest


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "corpora" / "candidate-catalog.json"


class CorpusIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = corpus_ingest.load_catalog(CATALOG)
        cls.records = cls.catalog["records"]

    def test_public_capabilities_are_fail_closed_and_offline(self):
        caps = corpus_ingest.capabilities()
        self.assertFalse(caps["network_fetch"])
        self.assertFalse(caps["payload_ingest"])
        self.assertFalse(caps["code_license_applies_to_data"])
        self.assertEqual(caps["commercial_rights_gate"], "fail_closed")

    def test_bundled_candidates_pass_rights_gate_but_install_no_payload(self):
        for record in self.records:
            checked = corpus_ingest.validate_candidate(record)
            self.assertEqual(checked["verdict"], corpus_ingest.ANSWER)
            self.assertFalse(checked["payload_bundled"])

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = corpus_ingest.ingest(self.catalog, temporary)
            self.assertEqual(len(result["admitted"]), 3)
            self.assertEqual(result["writes"], 0)
            self.assertFalse(Path(temporary, "index.json").exists())

    def test_commit_is_content_addressed_and_second_run_is_duplicate(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = corpus_ingest.ingest(self.catalog, temporary, commit=True)
            self.assertEqual(first["writes"], 3)
            self.assertEqual(first["payloads_installed"], 0)
            index = json.loads(Path(temporary, "index.json").read_text())
            self.assertEqual(index["schema"], corpus_ingest.INDEX_SCHEMA)
            for digest in index["entries"].values():
                self.assertTrue(Path(temporary, "objects", digest + ".json").is_file())
            second = corpus_ingest.ingest(self.catalog, temporary, commit=True)
            self.assertEqual(second["writes"], 0)
            self.assertEqual(len(second["duplicates"]), 3)

    def test_tampered_record_hash_is_refused(self):
        record = copy.deepcopy(self.records[0])
        record["manifest"]["name"] = "tampered"
        with tempfile.TemporaryDirectory() as temporary:
            result = corpus_ingest.ingest(
                {"verdict": "ANSWER", "records": [record]}, temporary,
                commit=True)
            self.assertEqual(result["refused"][0]["verdict"],
                             corpus_ingest.HASH_MISMATCH)
            self.assertFalse(Path(temporary, "index.json").exists())

    def test_unknown_commercial_rights_are_refused(self):
        record = copy.deepcopy(self.records[0])
        record["manifest"]["license"]["rights"]["commercial_use"] = "unknown"
        record["record_sha256"] = corpus_ingest.candidate_digest(record)
        with tempfile.TemporaryDirectory() as temporary:
            result = corpus_ingest.ingest(
                {"verdict": "ANSWER", "records": [record]}, temporary,
                commit=True)
            self.assertEqual(result["refused"][0]["verdict"],
                             "UNKNOWN_CORPUS_COMMERCIAL_RIGHTS")

    def test_mixed_catalog_commits_only_records_that_pass_the_gate(self):
        rejected = copy.deepcopy(self.records[0])
        rejected["candidate_id"] = "rights-unknown"
        rejected["manifest"]["license"]["rights"]["commercial_use"] = "unknown"
        rejected["record_sha256"] = corpus_ingest.candidate_digest(rejected)
        catalog = {"verdict": "ANSWER",
                   "records": [self.records[1], rejected]}
        with tempfile.TemporaryDirectory() as temporary:
            result = corpus_ingest.ingest(catalog, temporary, commit=True)
            self.assertEqual([item["candidate_id"] for item in result["admitted"]],
                             ["garmentcode-source-code"])
            self.assertEqual(len(result["refused"]), 1)
            index = json.loads(Path(temporary, "index.json").read_text())
            self.assertEqual(list(index["entries"]),
                             ["garmentcode-source-code"])

    def test_code_licence_cannot_be_reused_for_data(self):
        record = copy.deepcopy(self.records[0])
        record["manifest"]["modalities"] = ["patterns_2d"]
        record["record_sha256"] = corpus_ingest.candidate_digest(record)
        checked = corpus_ingest.validate_candidate(record)
        self.assertEqual(checked["verdict"], corpus_ingest.SCOPE_MISMATCH)


if __name__ == "__main__":
    unittest.main()
