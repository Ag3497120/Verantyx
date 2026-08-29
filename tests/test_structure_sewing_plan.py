#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import hashlib
import json
import unittest

from photoloset import structure_sewing_plan as planner


def seal(pattern):
    value = copy.deepcopy(pattern)
    value.pop("digest", None)
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    value["digest"] = hashlib.sha256(raw).hexdigest()
    return value


def piece(piece_id, primitive="BODY_SHELL", role="body_wrap", layer=0,
          cut_count=1, **attributes):
    return {"piece_id": piece_id, "primitive_kind": primitive, "role": role,
            "layer": layer, "cut_count": cut_count,
            "source_node_id": attributes.pop("source_node_id", piece_id),
            "attributes": attributes}


def seam(operation_id, kind, a, b, **detail):
    return {"operation_id": operation_id, "kind": kind,
            "a": {"piece_id": a, "edge": "e1"},
            "b": {"piece_id": b, "edge": "e3"}, **detail}


def compiled(pieces, seams=(), layers=(), transforms=(), features=()):
    return seal({
        "verdict": "ANSWER", "schema": "garment.compiled-pattern.v1",
        "candidate_id": "candidate-front-a", "candidate_state": "APPROVED",
        "structure_digest": "sha256:structure-a",
        "approval": {"by": "Reviewer", "digest": "sha256:candidate-a",
                     "approval_id": "approval-a"},
        "pieces": list(pieces), "seams": list(seams), "layers": list(layers),
        "transforms": list(transforms), "features": list(features),
        "seam_checks": [],
    })


class StructureSewingPlanTests(unittest.TestCase):
    def test_one_piece_intrinsic_closure_is_ordered_and_provenance_is_preserved(self):
        pattern = compiled(
            [piece("shell")],
            [seam("procedural-close-shell", "PROCEDURAL_CLOSURE",
                  "shell", "shell",
                  closure_detail={"type": "centre_back_zip", "state": "APPROVED"})])
        result = planner.plan(pattern)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["order_verdict"], "ANSWER")
        self.assertEqual([row["action"] for row in result["steps"]],
                         ["close_intrinsic_wrap"])
        self.assertEqual(result["source_pattern_digest"], pattern["digest"])
        self.assertEqual(result["provenance"]["approval_digest"],
                         "sha256:candidate-a")
        self.assertEqual(result["approval"], pattern["approval"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])
        self.assertFalse(result["claims"]["industrial_standard_conformance"])

    def test_separates_keep_independent_closures_without_inventing_a_join(self):
        pattern = compiled(
            [piece("top"), piece("skirt", "TUBE", "tube_wrap")],
            [seam("close-top", "PROCEDURAL_CLOSURE", "top", "top",
                  closure_detail="approved pullover topology"),
             seam("close-skirt", "PROCEDURAL_CLOSURE", "skirt", "skirt",
                  closure_detail="approved side zip")])
        result = planner.plan(pattern)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual({row["step_id"] for row in result["steps"]},
                         {"seam:close-top", "seam:close-skirt"})
        self.assertTrue(all(not row["depends_on"] for row in result["steps"]))
        self.assertNotIn("join_pieces", [row["action"] for row in result["steps"]])

    def test_layered_ruffle_forms_gather_attaches_layer_then_closes_base(self):
        pattern = compiled(
            [piece("base"), piece("ruffle", "BAND", "band", layer=1)],
            [seam("gather-ruffle", "GATHER", "ruffle", "base",
                  construction_method="reviewed gathered seam"),
             seam("close-base", "PROCEDURAL_CLOSURE", "base", "base",
                  closure_detail="approved centre back opening")],
            layers=[{"operation_id": "layer-ruffle", "kind": "LAYER",
                     "a": {"piece_id": "ruffle", "edge": "e0"},
                     "b": {"piece_id": "base", "edge": "e0"},
                     "construction_method": "reviewed permanent attachment"}],
            transforms=[{"operation_id": "gather-ruffle", "kind": "GATHER",
                         "address": "e0", "ratio": 1.8,
                         "finished_length_cm": 80.0}])
        result = planner.plan(pattern)
        self.assertEqual(result["verdict"], "ANSWER")
        positions = {row["step_id"]: row["step"] for row in result["steps"]}
        self.assertLess(positions["prepare:gather:gather-ruffle"],
                        positions["seam:gather-ruffle"])
        self.assertLess(positions["seam:gather-ruffle"],
                        positions["layer:layer-ruffle"])
        self.assertLess(positions["layer:layer-ruffle"],
                        positions["seam:close-base"])
        self.assertIn("seam:gather-ruffle",
                      result["dependency_graph"]["layer:layer-ruffle"])
        self.assertIn("layer:layer-ruffle",
                      result["dependency_graph"]["seam:close-base"])

    def test_missing_closure_detail_is_typed_review_not_a_guess(self):
        pattern = compiled(
            [piece("shell")],
            [seam("procedural-close-shell", "PROCEDURAL_CLOSURE",
                  "shell", "shell")])
        result = planner.plan(pattern)
        self.assertEqual(result["verdict"],
                         "REVIEW_MANUFACTURING_CHOICES_REQUIRED")
        self.assertEqual(result["order_verdict"], "ANSWER")
        self.assertEqual(result["steps"][0]["action"], "close_intrinsic_wrap")
        self.assertIn("REVIEW_CLOSURE_DETAIL_REQUIRED",
                      {row["verdict"] for row in result["reviews"]})
        self.assertNotIn("centre_back_zip", json.dumps(result))

    def test_sleeve_closure_precedes_attachment_and_hood_is_prepared_first(self):
        pattern = compiled(
            [piece("body"), piece("sleeve", "SLEEVE", "sleeve_wrap", cut_count=2),
             piece("hood", "HOOD", "hood_side", cut_count=2)],
            [seam("close-sleeve", "PROCEDURAL_CLOSURE", "sleeve", "sleeve",
                  closure_detail="approved underarm closure"),
             seam("set-sleeve", "JOIN", "sleeve", "body",
                  construction_method="reviewed sleeve seam"),
             seam("attach-hood", "JOIN", "hood", "body",
                  construction_method="reviewed neckline seam")])
        result = planner.plan(pattern)
        positions = {row["step_id"]: row["step"] for row in result["steps"]}
        for side in ("left", "right"):
            self.assertLess(positions[f"seam:close-sleeve:{side}"],
                            positions[f"seam:set-sleeve:{side}"])
            step = next(row for row in result["steps"]
                        if row["step_id"] == f"seam:set-sleeve:{side}")
            self.assertEqual(step["action"], "set_root_sleeve")
            self.assertEqual(step["detail"]["relation_side"], side)
            self.assertEqual(step["quantity"], 1)
        self.assertLess(positions["prepare:hood:hood"],
                        positions["seam:attach-hood"])
        self.assertIn("REVIEW_HOOD_CONSTRUCTION_REQUIRED",
                      {row["verdict"] for row in result["reviews"]})

    def test_layered_segmented_sleeves_are_side_specific_and_dependency_safe(self):
        pieces = [piece("body")]
        for side in ("left", "right"):
            pieces.extend([
                piece(f"upper:{side}", "SLEEVE", f"set_in_sleeve_{side}",
                      source_node_id="upper", derived_side=side,
                      attached_to="body"),
                piece(f"lower:{side}", "SLEEVE",
                      f"joined_sleeve_segment_{side}",
                      source_node_id="lower", derived_side=side,
                      attached_to="upper", sleeve_parent_relation="JOIN"),
                piece(f"outer:{side}", "SLEEVE", f"layered_sleeve_{side}",
                      layer=2, source_node_id="outer", derived_side=side,
                      attached_to="upper", sleeve_parent_relation="LAYER"),
            ])
        seams = []
        layers = []
        for side in ("left", "right"):
            seams.extend([
                seam(f"construct-upper:{side}", "JOIN",
                     f"upper:{side}", f"upper:{side}",
                     construction_role="SLEEVE_UNDERARM",
                     relation_side=side,
                     construction_method="reviewed underarm seam"),
                seam(f"construct-lower:{side}", "JOIN",
                     f"lower:{side}", f"lower:{side}",
                     construction_role="SLEEVE_UNDERARM",
                     relation_side=side,
                     construction_method="reviewed lower underarm seam"),
                seam(f"join-lower:{side}", "JOIN",
                     f"lower:{side}", f"upper:{side}",
                     construction_role="JOIN_SLEEVE_SEGMENTS",
                     relation_side=side,
                     construction_method="reviewed segment seam",
                     pattern_lineage={
                         "relation_kind": "JOIN", "side": side,
                         "source": {"piece_id": f"lower:{side}"},
                         "target": {"piece_id": f"upper:{side}"},
                     }),
                seam(f"set-root:{side}", "JOIN",
                     f"upper:{side}", "body",
                     construction_role="SET_IN_SLEEVE",
                     relation_side=side,
                     construction_method="reviewed armscye seam"),
            ])
            layers.append({
                "operation_id": f"layer-outer:{side}", "kind": "LAYER",
                "construction_role": "LAYER_SLEEVE_INSTANCE",
                "relation_side": side,
                "a": {"piece_id": f"outer:{side}", "edge": "e2"},
                "b": {"piece_id": f"upper:{side}", "edge": "e10"},
                "construction_method": "reviewed oversleeve anchor",
                "pattern_lineage": {
                    "relation_kind": "LAYER", "side": side,
                    "source": {"piece_id": f"outer:{side}"},
                    "target": {"piece_id": f"upper:{side}"},
                },
            })
        result = planner.plan(compiled(pieces, seams, layers))
        self.assertEqual(result["verdict"], "ANSWER", result)
        by_id = {row["step_id"]: row for row in result["steps"]}
        for side, other in (("left", "right"), ("right", "left")):
            construct_upper = f"seam:construct-upper:{side}"
            construct_lower = f"seam:construct-lower:{side}"
            join = f"seam:join-lower:{side}"
            layer = f"layer:layer-outer:{side}"
            root = f"seam:set-root:{side}"
            self.assertEqual(by_id[join]["action"], "join_sleeve_segments")
            self.assertEqual(by_id[layer]["action"], "attach_sleeve_layer")
            self.assertEqual(by_id[root]["action"], "set_root_sleeve")
            self.assertIn(construct_upper, by_id[join]["depends_on"])
            self.assertIn(construct_lower, by_id[join]["depends_on"])
            self.assertIn(join, by_id[layer]["depends_on"])
            self.assertIn(join, by_id[root]["depends_on"])
            self.assertIn(layer, by_id[root]["depends_on"])
            self.assertNotIn(f"seam:join-lower:{other}",
                             by_id[layer]["depends_on"])
            for step_id in (join, layer, root):
                self.assertEqual(by_id[step_id]["detail"]["relation_side"], side)
                self.assertEqual(by_id[step_id]["detail"]["planning_state"],
                                 "PROPOSED")
                self.assertFalse(by_id[step_id]["detail"][
                    "manufacturing_certified"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])

    def test_sleeve_relation_side_mismatch_and_unresolved_parent_fail_closed(self):
        upper = piece("upper:left", "SLEEVE", "set_in_sleeve_left",
                      source_node_id="upper", derived_side="left")
        lower = piece("lower:left", "SLEEVE", "joined_sleeve_segment_left",
                      source_node_id="lower", derived_side="left",
                      attached_to="upper", sleeve_parent_relation="JOIN")
        mismatched = compiled(
            [piece("body"), upper, lower],
            [seam("join-lower", "JOIN", "lower:left", "upper:left",
                  construction_role="JOIN_SLEEVE_SEGMENTS",
                  relation_side="right",
                  construction_method="reviewed seam",
                  pattern_lineage={
                      "relation_kind": "JOIN", "side": "right",
                      "source": {"piece_id": "lower:left"},
                      "target": {"piece_id": "upper:left"},
                  })])
        self.assertEqual(planner.plan(mismatched)["verdict"],
                         "UNKNOWN_SLEEVE_RELATION_SIDE_MISMATCH")

        no_parent = copy.deepcopy(lower)
        no_parent["attributes"].pop("attached_to")
        no_parent["attributes"].pop("sleeve_parent_relation")
        unresolved = compiled(
            [piece("body"), upper, no_parent],
            [seam("join-lower", "JOIN", "lower:left", "upper:left",
                  construction_role="JOIN_SLEEVE_SEGMENTS",
                  relation_side="left", construction_method="reviewed seam")])
        self.assertEqual(planner.plan(unresolved)["verdict"],
                         "UNKNOWN_SLEEVE_RELATION_PARENT_REQUIRED")

    def test_untyped_sleeve_relation_and_missing_method_are_not_guessed(self):
        upper = piece("upper:left", "SLEEVE", "set_in_sleeve_left",
                      source_node_id="upper", derived_side="left")
        lower = piece("lower:left", "SLEEVE", "joined_sleeve_segment_left",
                      source_node_id="lower", derived_side="left",
                      attached_to="upper", sleeve_parent_relation="JOIN")
        untyped = compiled(
            [piece("body"), upper, lower],
            [seam("join-lower", "JOIN", "lower:left", "upper:left",
                  relation_side="left", construction_method="reviewed seam")])
        self.assertEqual(planner.plan(untyped)["verdict"],
                         "UNKNOWN_SLEEVE_RELATION_UNRESOLVED")

        missing_method = compiled(
            [piece("body"), upper],
            [seam("set-root", "JOIN", "upper:left", "body",
                  construction_role="SET_IN_SLEEVE", relation_side="left")])
        result = planner.plan(missing_method)
        self.assertEqual(result["verdict"],
                         "REVIEW_MANUFACTURING_CHOICES_REQUIRED")
        self.assertEqual(result["order_verdict"], "ANSWER")
        self.assertIn("REVIEW_SLEEVE_CONSTRUCTION_METHOD_REQUIRED",
                      {row["verdict"] for row in result["reviews"]})
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])

    def test_ambiguous_sleeve_side_and_parent_cardinality_fail_closed(self):
        unaddressed = compiled([
            piece("body"),
            piece("single", "SLEEVE", "sleeve_wrap", cut_count=1),
        ], [seam("set-single", "JOIN", "single", "body",
                 construction_role="SET_IN_SLEEVE",
                 construction_method="reviewed seam")])
        self.assertEqual(planner.plan(unaddressed)["verdict"],
                         "UNKNOWN_SLEEVE_SIDE_AMBIGUOUS")

        upper = piece("upper:left", "SLEEVE", "set_in_sleeve_left",
                      source_node_id="upper", derived_side="left")
        lower = piece("lower:left", "SLEEVE", "joined_sleeve_segment_left",
                      source_node_id="lower", derived_side="left",
                      attached_to="upper", sleeve_parent_relation="JOIN")
        duplicate_parent = compiled(
            [piece("body"), upper, lower],
            [seam(operation_id, "JOIN", "lower:left", "upper:left",
                  construction_role="JOIN_SLEEVE_SEGMENTS",
                  relation_side="left", construction_method="reviewed seam",
                  pattern_lineage={
                      "relation_kind": "JOIN", "side": "left",
                      "source": {"piece_id": "lower:left"},
                      "target": {"piece_id": "upper:left"},
                  })
             for operation_id in ("join-lower-a", "join-lower-b")])
        self.assertEqual(planner.plan(duplicate_parent)["verdict"],
                         "UNKNOWN_SLEEVE_RELATION_CARDINALITY")

    def test_bad_edge_check_and_unknown_operation_fail_closed(self):
        bad = compiled([piece("a"), piece("b")],
                       [seam("join", "JOIN", "a", "b")])
        bad["seam_checks"] = [{"operation_id": "join",
                               "geometrically_sewable": False}]
        self.assertEqual(planner.plan(bad)["verdict"],
                         "UNKNOWN_GEOMETRIC_SEAM_MISMATCH")

        unsupported = compiled([piece("a"), piece("b")],
                               [seam("weld", "WELD", "a", "b")])
        self.assertEqual(planner.plan(unsupported)["verdict"],
                         "UNKNOWN_UNSUPPORTED_SEAM_KIND")

        broken_count = compiled([piece("a")])
        broken_count["pieces"][0]["cut_count"] = "two"
        self.assertEqual(planner.plan(broken_count)["verdict"],
                         "UNKNOWN_PATTERN_CUT_COUNT")


if __name__ == "__main__":
    unittest.main()
