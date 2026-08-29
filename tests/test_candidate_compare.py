#!/usr/bin/env python3
import copy
import json
import unittest

from photoloset import candidate_compare


def back_rows():
    return [
        {"candidate_id": "center-zip", "payload": {"opening": "center_zip"},
         "constraints": [{"name": "front silhouette unchanged", "satisfied": True}],
         "assumptions": ["the back is not visible"],
         "source_evidence": [{"image_id": "front-1", "view": "front"}]},
        {"candidate_id": "side-zip", "payload": {"opening": "side_zip"},
         "constraints": [{"name": "front silhouette unchanged", "satisfied": True}],
         "assumptions": ["the side seam is not occluded"],
         "source_evidence": [{"image_id": "front-1", "view": "front"}]},
    ]


class CandidateCompareTests(unittest.TestCase):
    def test_sheet_preserves_proposals_and_has_no_winner(self):
        sheet = candidate_compare.propose("back", {"image_digest": "abc"}, back_rows())
        self.assertEqual(sheet["verdict"], "PROPOSED")
        self.assertIsNone(sheet["selected_candidate"])
        self.assertTrue(all(row["state"] == "PROPOSED" for row in sheet["candidates"]))
        self.assertEqual(len({row["digest"] for row in sheet["candidates"]}), 2)
        json.dumps(sheet, allow_nan=False)

    def test_named_digest_approval_does_not_promote_candidate(self):
        sheet = candidate_compare.propose("back", {"image_digest": "abc"}, back_rows())
        selected = sheet["candidates"][0]
        result = candidate_compare.approve(sheet, selected["digest"], "Mina")
        self.assertEqual(result["verdict"], "APPROVED")
        self.assertEqual(result["candidate"]["state"], "PROPOSED")
        self.assertEqual(result["approval"]["candidate_digest"], selected["digest"])

    def test_stale_or_edited_sheet_is_refused(self):
        sheet = candidate_compare.propose("material", {"motion_digest": "m1"}, [
            dict(back_rows()[0], payload={"warp_stiffness": [10, 20]}),
            dict(back_rows()[1], payload={"warp_stiffness": [30, 40]}),
        ])
        self.assertEqual(candidate_compare.approve(sheet, "old", "Mina")["verdict"],
                         "UNKNOWN_CANDIDATE_APPROVAL_STALE")
        edited = copy.deepcopy(sheet)
        digest = edited["candidates"][0]["digest"]
        edited["candidates"][0]["payload"]["warp_stiffness"] = [1, 2]
        self.assertEqual(candidate_compare.approve(edited, digest, "Mina")["verdict"],
                         "UNKNOWN_CANDIDATE_APPROVAL_STALE")
        edited_other = copy.deepcopy(sheet)
        digest = edited_other["candidates"][0]["digest"]
        edited_other["candidates"][1]["payload"]["warp_stiffness"] = [1, 2]
        self.assertEqual(candidate_compare.approve(edited_other, digest, "Mina")["verdict"],
                         "UNKNOWN_CANDIDATE_APPROVAL_STALE")

    def test_evidence_and_multiple_candidates_are_required(self):
        self.assertEqual(candidate_compare.propose("back", {}, back_rows())["verdict"],
                         "UNKNOWN_COMPARISON_EVIDENCE")
        self.assertEqual(candidate_compare.propose("back", {"x": 1}, back_rows()[:1])["verdict"],
                         "UNKNOWN_INSUFFICIENT_CANDIDATES")


if __name__ == "__main__":
    unittest.main()
