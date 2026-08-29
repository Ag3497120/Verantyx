# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset.construction_regime import (
    ConstructionRegime,
    ManufacturingRepresentation,
    route_construction,
    select_construction_regime,
)


def node(node_id, method, cut="UNKNOWN", fit="UNKNOWN", *, layer=0,
         dimensions=None, shaping=None, knit=None, state="PROPOSED"):
    return {
        "node_id": node_id,
        "primitive_kind": "BODY_SHELL",
        "layer": layer,
        "state": state,
        "dimensions_cm": dimensions or {},
        "construction": {
            "method": method,
            "cut_geometry": cut,
            "fit": fit,
            "shaping": shaping or [],
            "knit": knit or {},
        },
    }


def relation(relation_id, source, target=None, *, connection="UNKNOWN",
             kind="JOIN", parameters=None):
    return {
        "relation_id": relation_id,
        "kind": kind,
        "connection": connection,
        "source": source,
        "target": target,
        "parameters": parameters or {},
        "state": "PROPOSED",
    }


def graph(nodes, relations=(), *, name="display name", proposal=None,
          source_kind="MODEL_PROPOSAL", front_only=True, rear=None,
          **claims):
    result = {
        "schema": "garment.instance-graph.v1",
        "graph_id": "instance-1",
        "garment_name": name,
        "source": {"kind": source_kind, "front_only": front_only},
        "nodes": list(nodes),
        "relations": list(relations),
        "rear": rear or {"state": "UNKNOWN"},
        **claims,
    }
    if proposal is not None:
        result["proposed_construction_regime"] = proposal
    return result


class ConstructionRegimeTests(unittest.TestCase):
    def test_sewn_fitted_routes_to_pattern_pieces_without_promotion(self):
        result = route_construction(graph([
            node("shell", "SEWN", "FITTED_PANEL", "FITTED",
                 dimensions={"height": 62, "width": 48}, shaping=["DART"]),
        ], proposal="SEWN_FITTED", rear={"state": "PROPOSED"}))

        self.assertEqual("ANSWER", result["verdict"])
        self.assertEqual("SEWN_FITTED", result["construction_regime"]["value"])
        self.assertEqual("PROPOSED", result["construction_regime"]["state"])
        self.assertEqual("MATCH", result["construction_regime"]["proposal_alignment"])
        self.assertEqual("PATTERN_PIECES",
                         result["manufacturing_representation"]["kind"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])
        self.assertEqual([], result["fact_promotions"])

    def test_sewn_rectilinear_emits_only_explicit_rectangles(self):
        result = route_construction(graph([
            node("panel-a", "SEWN", "RECTANGLE", "LOOSE",
                 dimensions={"width": 80, "length": 120}),
            node("panel-b", "SEWN", "RECTANGLE", "LOOSE",
                 dimensions={"width": 80, "length": 120}),
        ], [relation("seam", "panel-a", "panel-b", connection="SEAM")]))

        manufacturing = result["manufacturing_representation"]
        self.assertEqual("SEWN_RECTILINEAR",
                         result["construction_regime"]["value"])
        self.assertEqual("RECTANGULAR_CUT_PLAN", manufacturing["kind"])
        self.assertEqual(2, len(manufacturing["rectangles"]))
        self.assertEqual("EXPLICIT_RECTANGLES_ONLY", manufacturing["current_support"])
        self.assertTrue(all(row["cut_count"] is None
                            for row in manufacturing["rectangles"]))

    def test_rectilinear_route_does_not_invent_missing_dimensions(self):
        result = route_construction(graph([
            node("panel", "SEWN", "RECTANGLE", "LOOSE",
                 dimensions={"width": 70}),
        ]))
        manufacturing = result["manufacturing_representation"]
        self.assertEqual([], manufacturing["rectangles"])
        self.assertIn("REVIEW_RECTANGLE_DIMENSIONS_REQUIRED",
                      {row["code"] for row in result["review_items"]})

    def test_draped_unstitched_routes_to_drape_plan(self):
        result = route_construction(graph([
            node("cloth", "DRAPED", "FREEFORM_PANEL", "BODY_INDEPENDENT"),
        ], [relation("shoulder-anchor", "cloth", connection="DRAPE_ANCHOR",
                     kind="FOLD", parameters={"target_zone": "shoulder"})]))
        manufacturing = result["manufacturing_representation"]
        self.assertEqual("DRAPED_UNSTITCHED",
                         result["construction_regime"]["value"])
        self.assertEqual("DRAPE_PLAN", manufacturing["kind"])
        self.assertEqual("UNSTITCHED_DRAPE_PLAN", manufacturing["plan_subtype"])
        self.assertEqual(1, len(manufacturing["anchors"]))

    def test_wrapped_routes_to_wrap_subtype_not_pattern_pieces(self):
        result = route_construction(graph([
            node("wrap-surface", "WRAPPED", "RECTANGLE", "LOOSE",
                 dimensions={"width": 110, "length": 75}),
        ], [relation("overlap", "wrap-surface", connection="WRAP_OVERLAP",
                     kind="OVERLAP", parameters={"overlap_cm": 18})]))
        manufacturing = result["manufacturing_representation"]
        self.assertEqual("WRAPPED", result["construction_regime"]["value"])
        self.assertEqual("DRAPE_PLAN", manufacturing["kind"])
        self.assertEqual("WRAP_PLAN", manufacturing["plan_subtype"])
        self.assertEqual(1, len(manufacturing["overlaps"]))

    def test_knitted_preserves_specification_but_computes_no_stitches(self):
        result = route_construction(graph([
            node("knit-field", "KNITTED", "NO_CUT", "FITTED",
                 knit={"gauge": "22 stitches / 10 cm", "yarn": "declared-yarn",
                       "stitch_count": 176}),
        ]))
        manufacturing = result["manufacturing_representation"]
        self.assertEqual("KNITTED", result["construction_regime"]["value"])
        self.assertEqual("KNIT_SPECIFICATION", manufacturing["kind"])
        self.assertFalse(manufacturing["specifications"][0]["computed_stitch_counts"])
        self.assertEqual(176, manufacturing["specifications"][0]
                         ["specification"]["stitch_count"])

    def test_modular_layered_routes_component_regimes_to_hybrid(self):
        result = route_construction(graph([
            node("fitted-base", "SEWN", "FITTED_PANEL", "FITTED", layer=0),
            node("wrap-overlay", "WRAPPED", "RECTANGLE", "LOOSE", layer=1,
                 dimensions={"width": 90, "length": 80}),
        ], [
            relation("layer", "wrap-overlay", "fitted-base",
                     connection="LAYER", kind="LAYER"),
            relation("overlap", "wrap-overlay", connection="WRAP_OVERLAP",
                     kind="OVERLAP"),
        ]))
        manufacturing = result["manufacturing_representation"]
        self.assertEqual("MODULAR_LAYERED",
                         result["construction_regime"]["value"])
        self.assertEqual("HYBRID", manufacturing["kind"])
        component_kinds = {
            row["representation"]["kind"] for row in manufacturing["components"]
        }
        self.assertEqual({"PATTERN_PIECES", "DRAPE_PLAN"}, component_kinds)
        self.assertFalse(manufacturing["manufacturing_ready"])

    def test_name_is_metadata_and_does_not_change_construction_digest(self):
        base = graph([
            node("p", "SEWN", "RECTANGLE", "LOOSE",
                 dimensions={"width": 40, "length": 100}),
        ], name="robe")
        renamed = copy.deepcopy(base)
        renamed["garment_name"] = "unclassifiable anime object"
        first, second = route_construction(base), route_construction(renamed)
        self.assertEqual(first["construction_digest"], second["construction_digest"])
        self.assertEqual(first["construction_regime"], second["construction_regime"])
        self.assertFalse(first["identity"]["garment_name_used_for_routing"])

    def test_model_regime_label_cannot_override_typed_selection(self):
        result = route_construction(graph([
            node("p", "SEWN", "RECTANGLE", "LOOSE",
                 dimensions={"width": 40, "length": 100}),
        ], proposal="KNITTED"))
        self.assertEqual("SEWN_RECTILINEAR",
                         result["construction_regime"]["value"])
        self.assertEqual("PROPOSED",
                         result["construction_regime"]["model_proposal"]["state"])
        self.assertEqual("CONTESTED",
                         result["construction_regime"]["proposal_alignment"])
        self.assertIn("REVIEW_MODEL_REGIME_CONTESTED",
                      {row["code"] for row in result["review_items"]})

    def test_front_only_model_rear_and_manufacturing_claims_are_scrubbed(self):
        result = route_construction(graph([
            node("p", "SEWN", "FITTED_PANEL", "FITTED"),
        ], rear={"state": "OBSERVED"}, manufacturing_ready=True,
           manufacturing_certified=True))
        self.assertEqual("PROPOSED", result["authority"]["rear"]["state"])
        self.assertFalse(result["authority"]["rear"]["observed"])
        self.assertFalse(result["authority"]["manufacturing"]["ready"])
        self.assertFalse(result["authority"]["manufacturing"]["certified"])
        codes = {row["code"] for row in result["review_items"]}
        self.assertIn("REVIEW_MODEL_REAR_AUTHORITY_REJECTED", codes)
        self.assertIn("REVIEW_MANUFACTURING_AUTHORITY_NOT_GRANTED", codes)

    def test_model_cannot_promote_local_node_or_relation_authority(self):
        proposed = graph([
            node("a", "SEWN", "RECTANGLE", "LOOSE",
                 dimensions={"width": 30, "length": 40}, state="OBSERVED"),
            node("b", "SEWN", "RECTANGLE", "LOOSE",
                 dimensions={"width": 30, "length": 40}, state="MEASURED"),
        ], [relation("seam", "a", "b", connection="SEAM")])
        proposed["relations"][0]["state"] = "HUMAN_CONFIRMED"

        result = route_construction(proposed)

        rectangles = result["manufacturing_representation"]["rectangles"]
        seams = result["manufacturing_representation"]["seams"]
        self.assertEqual({"PROPOSED"}, {row["state"] for row in rectangles})
        self.assertEqual("PROPOSED", seams[0]["state"])
        rejected = [row for row in result["review_items"]
                    if row["code"] == "REVIEW_MODEL_LOCAL_AUTHORITY_REJECTED"]
        self.assertEqual(3, len(rejected))
        self.assertEqual([], result["fact_promotions"])

    def test_join_word_without_explicit_seam_does_not_choose_sewn_regime(self):
        result = route_construction(graph([
            node("a", "UNKNOWN", "RECTANGLE", "LOOSE",
                 dimensions={"width": 30, "length": 40}),
            node("b", "UNKNOWN", "RECTANGLE", "LOOSE",
                 dimensions={"width": 30, "length": 40}),
        ], [relation("join-looking", "a", "b", kind="JOIN")]))
        self.assertEqual("UNKNOWN_CONSTRUCTION", result["verdict"])
        self.assertEqual("UNKNOWN_CONSTRUCTION",
                         result["construction_regime"]["value"])
        self.assertEqual("UNKNOWN_MANUFACTURING_REPRESENTATION",
                         result["manufacturing_representation"]["kind"])

    def test_explicit_seam_plus_rectilinear_geometry_can_route_unknown_method(self):
        result = route_construction(graph([
            node("a", "UNKNOWN", "RECTANGLE", "LOOSE",
                 dimensions={"width": 30, "length": 40}),
            node("b", "UNKNOWN", "RECTANGLE", "LOOSE",
                 dimensions={"width": 30, "length": 40}),
        ], [relation("seam", "a", "b", connection="SEAM")]))
        # A seam is explicit, but the node construction method remains unknown;
        # the router refuses to convert cut shape alone into a manufacturing fact.
        self.assertEqual("UNKNOWN_CONSTRUCTION", result["verdict"])

    def test_unstitched_drape_with_explicit_seam_becomes_unknown(self):
        result = route_construction(graph([
            node("cloth", "DRAPED", "FREEFORM_PANEL", "BODY_INDEPENDENT"),
            node("band", "DRAPED", "FREEFORM_PANEL", "BODY_INDEPENDENT"),
        ], [relation("seam", "cloth", "band", connection="SEAM")]))
        self.assertEqual("UNKNOWN_CONSTRUCTION", result["verdict"])
        self.assertIn("REVIEW_UNSTITCHED_CONSTRUCTION_HAS_SEAM",
                      {row["code"] for row in result["review_items"]})

    def test_human_confirmed_rear_is_preserved_but_not_promoted(self):
        result = route_construction(graph([
            node("p", "SEWN", "FITTED_PANEL", "FITTED",
                 state="HUMAN_CONFIRMED"),
        ], source_kind="HUMAN_INPUT", rear={"state": "HUMAN_CONFIRMED"}))
        self.assertEqual("HUMAN_CONFIRMED", result["authority"]["rear"]["state"])
        self.assertFalse(result["authority"]["rear"]["promoted"])
        self.assertEqual([], result["authority"]["fact_promotions"])
        self.assertEqual("DERIVED", result["construction_regime"]["state"])

    def test_select_api_returns_authority_bound_regime_only(self):
        result = select_construction_regime(graph([
            node("knit", "KNITTED", "NO_CUT", "FITTED",
                 knit={"gauge": "20/10cm", "yarn": "declared"}),
        ]))
        self.assertEqual("KNITTED", result["construction_regime"]["value"])
        self.assertNotIn("manufacturing_representation", result)
        self.assertEqual([], result["fact_promotions"])

    def test_invalid_node_reference_is_typed_refusal(self):
        result = route_construction(graph([
            node("a", "SEWN", "RECTANGLE", "LOOSE"),
        ], [relation("bad", "a", "missing", connection="SEAM")]))
        self.assertEqual("UNKNOWN_CONSTRUCTION_GRAPH", result["verdict"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertEqual([], result["fact_promotions"])

    def test_all_requested_regime_values_are_stable(self):
        self.assertEqual({
            "SEWN_FITTED", "SEWN_RECTILINEAR", "DRAPED_UNSTITCHED",
            "WRAPPED", "KNITTED", "MODULAR_LAYERED",
            "UNKNOWN_CONSTRUCTION",
        }, {item.value for item in ConstructionRegime})
        self.assertEqual({
            "PATTERN_PIECES", "RECTANGULAR_CUT_PLAN", "DRAPE_PLAN",
            "KNIT_SPECIFICATION", "HYBRID",
            "UNKNOWN_MANUFACTURING_REPRESENTATION",
        }, {item.value for item in ManufacturingRepresentation})


if __name__ == "__main__":
    unittest.main()
