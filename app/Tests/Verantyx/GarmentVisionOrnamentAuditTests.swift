import AppKit
import Foundation

#if !GARMENT_VISION_ORNAMENT_STANDALONE
import XCTest
@testable import Verantyx
#endif

/// Source and executable regression audit for front-image ornament proposals.
///
/// Build the standalone form together with
/// `GarmentFactoryReactController.swift`; it invokes the production parser and
/// the production `runVisionPartsPipeline` request bridge with an in-memory MCP
/// fixture. No duplicate parser exists in this test.
private enum GarmentVisionOrnamentAudit {
    static let fixture = #"""
    Model preface is allowed.
    {"candidates":[
      {"candidate_id":"ornate-front-a",
       "back_design":"OBSERVED closed rear with a proposed opening",
       "material_authority":"OBSERVED","manufacturing_ready":true,
       "assumptions":["rear is not visible"],"parts":[
        {"part_id":"body-a","kind":"BODY_SHELL","layer":0,
         "placement":"torso","garment_unit":"look-a",
         "attached_to":"none",
         "visible_basis":"visible fitted torso",
         "dimensions":{"height_cm":44,"circumference_cm":92}},
        {"part_id":"bow-a","kind":"BOW","layer":2,
         "placement":"center front","garment_unit":"look-a",
         "attached_to":"body-a","visible_basis":"two loops and a center knot",
         "dimensions":{"body_length_cm":24,"body_width_cm":8,
                       "knot_length_cm":7,"knot_width_cm":3}},
        {"part_id":"ruffle-a","kind":"RUFFLE","layer":2,
         "placement":"neckline","garment_unit":"look-a",
         "attached_to":"body-a","visible_basis":"gathered edge rhythm",
         "dimensions":{"length_cm":96,"width_cm":7}},
        {"part_id":"beads-a","kind":"BEADING","layer":3,
         "placement":"front neckline","garment_unit":"look-a",
         "attached_to":"body-a","visible_basis":"visible bead-like highlights",
         "dimensions":{"diameter_cm":0.5}}
       ],"pattern_operations":[
        {"operation_id":"gather-ratio-only","kind":"GATHER",
         "state":"OBSERVED","approved":true,
         "target":{"piece_id":"ruffle-a","semantic_edge":"hem"},
         "parameters":{"ratio":2},"basis":"visible gathered neckline"}
       ]},
      {"candidate_id":"ornate-front-b",
       "back_design":"ANSWER laced rear alternative",
       "manufacturing_certified":true,
       "assumptions":["rear and material remain proposals"],"parts":[
        {"part_id":"body-b","kind":"BODY_SHELL","layer":0,
         "placement":"torso","garment_unit":"look-b",
         "visible_basis":"visible torso boundary",
         "dimensions":{"height_cm":46,"circumference_cm":94}},
        {"part_id":"ribbon-b","kind":"RIBBON","layer":2,
         "placement":"waist","garment_unit":"look-b",
         "attached_to":"body-b","visible_basis":"long narrow strip",
         "dimensions":{"length_cm":52,"width_cm":4}},
        {"part_id":"rosette-b","kind":"ROSETTE","layer":3,
         "placement":"left chest","garment_unit":"look-b",
         "attached_to":"body-b","visible_basis":"circular gathered ornament",
         "dimensions":{"strip_length_cm":72,"strip_width_cm":4,
                       "finished_inner_length_cm":18}},
        {"part_id":"tie-b","kind":"TIE","layer":2,
         "placement":"neckline","garment_unit":"look-b",
         "attached_to":"body-b","visible_basis":"tapered hanging strip",
         "dimensions":{"length_cm":35,"top_width_cm":7,"tip_width_cm":2}},
        {"part_id":"flap-b","kind":"FLAP","layer":2,
         "placement":"front hip","garment_unit":"look-b",
         "attached_to":"body-b","visible_basis":"attached trapezoid flap",
         "dimensions":{"attachment_width_cm":12,"depth_cm":8,
                       "outer_width_cm":9}},
        {"part_id":"frill-b","kind":"FRILL","layer":2,
         "placement":"cuff","garment_unit":"look-b",
         "attached_to":"body-b","visible_basis":"repeated gathered cuff edge",
         "dimensions":{"length_cm":100,"width_cm":6}}
       ],"pattern_operations":[
        {"operation_id":"pleat-existing","kind":"PLEAT",
         "target":{"piece_id":"ribbon-b","semantic_edge":"hem"},
         "parameters":{"count":2,"depth_cm":1,"style":"knife"}},
        {"operation_id":"dart-existing","kind":"DART",
         "target":{"piece_id":"body-b","semantic_edge":"waist"},
         "parameters":{"t":0.5,"intake_cm":2,"depth_cm":10}},
        {"operation_id":"fold-existing","kind":"FOLD",
         "target":{"piece_id":"flap-b","semantic_edge":"e0"},
         "parameters":{"start":[0,0],"end":[0,5],"direction":"valley"}},
        {"operation_id":"gather-finished-only","kind":"GATHER",
         "target":{"piece_id":"frill-b","semantic_edge":"hem"},
         "parameters":{"finished_length_cm":10}},
        {"operation_id":"gather-both","kind":"GATHER",
         "target":{"piece_id":"ribbon-b","semantic_edge":"hem"},
         "parameters":{"finished_length_cm":10,"ratio":2}},
        {"operation_id":"gather-ratio-too-large","kind":"GATHER",
         "target":{"piece_id":"frill-b","semantic_edge":"hem"},
         "parameters":{"ratio":20}}
       ]}
    ]}
    trailing prose
    """#

    static let singleVisibleFixture = #"""
    {"candidates":[
      {"candidate_id":"qwen-visible-one",
       "back_design":"rear is not visible",
       "assumptions":["front image grounds one visible structure"],
       "parts":[
        {"part_id":"bodice-one","kind":"BODICE","layer":0,
         "placement":"torso","garment_unit":"dress-one",
         "visible_basis":"fitted front bodice boundary",
         "dimensions":{"height_cm":42,"circumference_cm":90}},
        {"part_id":"collar-one","kind":"COLLAR","layer":1,
         "placement":"neckline","garment_unit":"dress-one",
         "attached_to":"bodice-one","visible_basis":"high visible collar",
         "dimensions":{"length_cm":40,"width_cm":7}},
        {"part_id":"sleeve-left","kind":"SLEEVE","layer":1,
         "placement":"left arm","garment_unit":"dress-one",
         "attached_to":"bodice-one","visible_basis":"left sleeve outline",
         "dimensions":{"length_cm":58,"upper_circumference_cm":34,
                       "cuff_circumference_cm":19}},
        {"part_id":"sleeve-right","kind":"SLEEVE","layer":1,
         "placement":"right arm","garment_unit":"dress-one",
         "attached_to":"bodice-one","visible_basis":"right sleeve outline",
         "dimensions":{"length_cm":58,"upper_circumference_cm":34,
                       "cuff_circumference_cm":19}},
        {"part_id":"skirt-one","kind":"SKIRT","layer":0,
         "placement":"lower body","garment_unit":"dress-one",
         "attached_to":"bodice-one","visible_basis":"flared skirt silhouette",
         "dimensions":{"height_cm":68,"top_circumference_cm":72,
                       "bottom_circumference_cm":180}},
        {"part_id":"overlay-one","kind":"OVERLAY","layer":2,
         "placement":"front skirt","garment_unit":"dress-one",
         "attached_to":"skirt-one","visible_basis":"asymmetric front layer",
         "dimensions":{"height_cm":50,"width_cm":46}},
        {"part_id":"belt-one","kind":"BAND","layer":2,
         "placement":"waist","garment_unit":"dress-one",
         "attached_to":"bodice-one","visible_basis":"visible waist belt",
         "dimensions":{"length_cm":72,"width_cm":5}},
        {"part_id":"rosette-one","kind":"ROSETTE","layer":3,
         "placement":"left waist","garment_unit":"dress-one",
         "attached_to":"belt-one","visible_basis":"circular rosette detail",
         "dimensions":{}},
        {"part_id":"tie-one","kind":"TIE","layer":3,
         "placement":"front waist","garment_unit":"dress-one",
         "attached_to":"belt-one","visible_basis":"two hanging tie ends",
         "dimensions":{}},
        {"part_id":"legging-left","kind":"TUBE","layer":0,
         "placement":"left leg under skirt","garment_unit":"dress-one",
         "attached_to":"bodice-one","side":"left","shape":"trouser_leg",
         "visible_basis":"left fitted leg layer visible below skirt",
         "dimensions":{"length_cm":66,"circumference_cm":38}},
        {"part_id":"legging-right","kind":"TUBE","layer":0,
         "placement":"right leg under skirt","garment_unit":"dress-one",
         "attached_to":"bodice-one","side":"right","shape":"trouser_leg",
         "visible_basis":"right fitted leg layer visible below skirt",
         "dimensions":{"length_cm":66,"circumference_cm":38}},
        {"part_id":"boot-left","kind":"TUBE","layer":0,
         "placement":"left foot","garment_unit":"footwear",
         "visible_basis":"left boot in the source image",
         "dimensions":{"length_cm":40,"circumference_cm":30}},
        {"part_id":"boot-right","kind":"TUBE","layer":0,
         "placement":"right footwear boot","garment_unit":"dress-one",
         "visible_basis":"right boot in the source image",
         "dimensions":{"length_cm":40,"circumference_cm":30}}
       ],"pattern_operations":[
        {"operation_id":"single-gather","kind":"GATHER",
         "target":{"piece_id":"skirt-one","semantic_edge":"hem"},
         "parameters":{"ratio":2},"basis":"visible gathered skirt edge"}
       ]}
    ]}
    """#

    static let upperSleeveBandFixture = #"""
    {"candidates":[
      {"candidate_id":"upper-sleeve-band-front",
       "back_design":"rear is not visible",
       "assumptions":["front image grounds the visible sleeve band only"],
       "parts":[
        {"part_id":"body-band","kind":"BODY_SHELL","layer":0,
         "placement":"torso","garment_unit":"look-band",
         "visible_basis":"visible torso boundary",
         "dimensions":{"height_cm":44,"circumference_cm":92}},
        {"part_id":"sleeve-band-parent","kind":"SLEEVE","layer":1,
         "placement":"left arm","garment_unit":"look-band",
         "attached_to":"body-band","visible_basis":"visible sleeve outline",
         "dimensions":{"length_cm":58,"upper_circumference_cm":34,
                       "cuff_circumference_cm":20}},
        {"part_id":"upper-band","kind":"BAND","layer":2,
         "placement":"upper sleeve","shape":"arm band",
         "detail_role":"upper sleeve trim","garment_unit":"look-band",
         "attached_to":"sleeve-band-parent",
         "visible_basis":"visible trim around the upper sleeve",
         "dimensions":{}}
       ],"pattern_operations":[]}
    ]}
    """#

    static let ambiguousShortSleeveRuffleFixture = #"""
    {"candidates":[
      {"candidate_id":"ambiguous-short-sleeve-ruffle",
       "back_design":"rear is not visible",
       "assumptions":["the exact sleeve attachment boundary is not named"],
       "parts":[
        {"part_id":"ruffle-body","kind":"BODY_SHELL","layer":0,
         "placement":"torso","garment_unit":"ruffle-look",
         "visible_basis":"visible torso boundary",
         "dimensions":{"height_cm":44,"circumference_cm":92}},
        {"part_id":"ruffle-sleeve","kind":"SLEEVE","layer":1,
         "placement":"left arm","side":"left","garment_unit":"ruffle-look",
         "attached_to":"ruffle-body","visible_basis":"visible sleeve outline",
         "dimensions":{"length_cm":58,"upper_circumference_cm":34,
                       "cuff_circumference_cm":20}},
        {"part_id":"short-ruffle","kind":"RUFFLE","layer":2,
         "placement":"sleeve decoration","side":"left",
         "garment_unit":"ruffle-look","attached_to":"ruffle-sleeve",
         "visible_basis":"visible repeated gathered edge",
         "dimensions":{"finished_length_cm":18,"width_cm":6}}
       ],"pattern_operations":[]}
    ]}
    """#

    static let mismatchedStructuralWaistbandFixture = #"""
    {"candidates":[
      {"candidate_id":"structural-waistband-front",
       "back_design":"rear construction is not visible",
       "parts":[
        {"part_id":"p10_trouser_body","kind":"BODY_SHELL","layer":0,
         "placement":"trouser waist body","garment_unit":"trouser-set",
         "visible_basis":"visible upper trouser body",
         "dimensions":{"height_cm":22,"circumference_cm":74}},
        {"part_id":"p11_trouser_waistband","kind":"WAISTBAND","layer":1,
         "placement":"waist","detail_role":"structural_waistband",
         "garment_unit":"trouser-set","attached_to":"p10_trouser_body",
         "visible_basis":"visible sewn waistband",
         "dimensions":{"length_cm":92,"width_cm":5}}
       ]}
    ]}
    """#

    static let layeredSeparatesVisibleInventoryFixture = #"""
    {"candidates":[
      {"candidate_id":"layered-separates-front",
       "back_design":"rear is not visible",
       "parts":[
        {"part_id":"ivory-blouse","kind":"BODY_SHELL","layer":0,
         "semantic_role":"white blouse","visible_color":"ivory",
         "placement":"upper torso and arms","garment_unit":"blouse",
         "visible_basis":"ivory high-neck front and long sleeves",
         "dimensions":{}},
        {"part_id":"navy-vest","kind":"BODY_SHELL","layer":1,
         "semantic_role":"cropped sleeveless vest","visible_color":"navy",
         "placement":"upper torso over blouse","garment_unit":"vest",
         "visible_basis":"dark cropped lapelled layer with open front",
         "dimensions":{}},
        {"part_id":"red-trouser-left","kind":"TUBE","layer":0,
         "semantic_role":"left trouser leg","visible_color":"red",
         "side":"left","shape":"trouser_leg","placement":"left lower body",
         "garment_unit":"trousers","visible_basis":"separate straight left leg",
         "dimensions":{}},
        {"part_id":"red-trouser-right","kind":"TUBE","layer":0,
         "semantic_role":"right trouser leg","visible_color":"red",
         "side":"right","shape":"trouser_leg","placement":"right lower body",
         "garment_unit":"trousers","visible_basis":"separate straight right leg",
         "dimensions":{}},
        {"part_id":"teal-right-wrap","kind":"OVERLAY","layer":2,
         "semantic_role":"asymmetric sheer overskirt wrap",
         "visible_color":"translucent teal","placement":"right waist to calf",
         "garment_unit":"overlay-wrap",
         "visible_basis":"transparent pleated layer leaves red trousers visible",
         "dimensions":{}}
       ]}
    ]}
    """#

    static let standaloneTrouserFixture = #"""
    {"candidates":[
      {"candidate_id":"separate-top-and-leggings",
       "back_design":"rear is not visible",
       "assumptions":["the leggings are a separate visible underlayer"],
       "parts":[
        {"part_id":"separate-top","kind":"BODY_SHELL","layer":0,
         "placement":"torso","garment_unit":"top-unit",
         "visible_basis":"visible fitted top","dimensions":{}},
        {"part_id":"legging-left-only","kind":"TUBE","layer":0,
         "placement":"left leg","garment_unit":"legging-unit",
         "side":"left","shape":"trouser_leg",
         "visible_basis":"visible fitted left legging","dimensions":{}},
        {"part_id":"legging-right-only","kind":"TUBE","layer":0,
         "placement":"right leg","garment_unit":"legging-unit",
         "side":"right","shape":"trouser_leg",
         "visible_basis":"visible fitted right legging","dimensions":{}}
       ],"pattern_operations":[]}
    ]}
    """#

    static let directMultiCandidateTrouserFixture = #"""
    {"candidates":[
      {"candidate_id":"direct-trouser-a","back_design":"proposed back A",
       "assumptions":[],"parts":[
        {"part_id":"direct-a-left","kind":"TUBE","layer":0,
         "placement":"left legging","garment_unit":"direct-a-lower",
         "side":"left","shape":"trouser_leg","detail_role":"trouser_leg",
         "visible_basis":"visible left leg","dimensions":{}},
        {"part_id":"direct-a-right","kind":"TUBE","layer":0,
         "placement":"right legging","garment_unit":"direct-a-lower",
         "side":"right","shape":"trouser_leg","detail_role":"trouser_leg",
         "visible_basis":"visible right leg","dimensions":{}}
       ],"pattern_operations":[]},
      {"candidate_id":"direct-trouser-b","back_design":"proposed back B",
       "assumptions":[],"parts":[
        {"part_id":"direct-b-left","kind":"TUBE","layer":0,
         "placement":"left pants leg","garment_unit":"direct-b-lower",
         "side":"left","shape":"trouser_leg","detail_role":"trouser_leg",
         "visible_basis":"visible left leg","dimensions":{}},
        {"part_id":"direct-b-right","kind":"TUBE","layer":0,
         "placement":"right pants leg","garment_unit":"direct-b-lower",
         "side":"right","shape":"trouser_leg","detail_role":"trouser_leg",
         "visible_basis":"visible right leg","dimensions":{}}
       ],"pattern_operations":[]}
    ]}
    """#

    static let layeredTrouserUnitsFixture = #"""
    {"candidates":[
      {"candidate_id":"outer-trousers-over-leggings",
       "back_design":"rear construction is not visible",
       "assumptions":["the outer trousers and fitted leggings are separate physical layers"],
       "parts":[
        {"part_id":"outer-trouser-left","kind":"TUBE","layer":1,
         "placement":"left outer trouser leg","garment_unit":"outer-trouser-unit",
         "side":"left","shape":"trouser_leg","detail_role":"outer trouser leg",
         "visible_basis":"visible left outer trouser silhouette",
         "dimensions":{"length_cm":98,"circumference_cm":58}},
        {"part_id":"outer-trouser-right","kind":"TUBE","layer":1,
         "placement":"right outer trouser leg","garment_unit":"outer-trouser-unit",
         "side":"right","shape":"trouser_leg","detail_role":"outer trouser leg",
         "visible_basis":"visible right outer trouser silhouette",
         "dimensions":{"length_cm":98,"circumference_cm":58}},
        {"part_id":"outer-trouser-gusset","kind":"GUSSET","layer":1,
         "placement":"outer trouser center crotch","garment_unit":"outer-trouser-unit",
         "attached_to":["outer-trouser-left","outer-trouser-right"],
         "side":"center","shape":"trousers","detail_role":"trouser_gusset",
         "visible_basis":"AI-inferred hidden outer-trouser crotch construction",
         "dimensions":{"length_cm":15,"width_cm":11}},
        {"part_id":"legging-underlayer-left","kind":"TUBE","layer":0,
         "placement":"left fitted legging underlayer","garment_unit":"legging-underlayer-unit",
         "side":"left","shape":"trouser_leg","detail_role":"legging underlayer leg",
         "visible_basis":"visible fitted left underlayer at the lower leg",
         "dimensions":{"length_cm":94,"circumference_cm":38}},
        {"part_id":"legging-underlayer-right","kind":"TUBE","layer":0,
         "placement":"right fitted legging underlayer","garment_unit":"legging-underlayer-unit",
         "side":"right","shape":"trouser_leg","detail_role":"legging underlayer leg",
         "visible_basis":"visible fitted right underlayer at the lower leg",
         "dimensions":{"length_cm":94,"circumference_cm":38}},
        {"part_id":"legging-underlayer-gusset","kind":"GUSSET","layer":0,
         "placement":"legging center crotch","garment_unit":"legging-underlayer-unit",
         "attached_to":["legging-underlayer-left","legging-underlayer-right"],
         "side":"center","shape":"trousers","detail_role":"trouser_gusset",
         "visible_basis":"AI-inferred hidden legging crotch construction",
         "dimensions":{"length_cm":12,"width_cm":8}}
       ],"pattern_operations":[]}
    ]}
    """#

    static let sleeveCarrierFixture = #"""
    {"candidates":[
      {"candidate_id":"sleeve-on-visible-yoke",
       "back_design":"rear is not visible","assumptions":[],"parts":[
        {"part_id":"carrier-body","kind":"BODY_SHELL","layer":0,
         "placement":"torso","garment_unit":"carrier-look",
         "visible_basis":"visible torso","dimensions":{}},
        {"part_id":"visible-yoke","kind":"YOKE","layer":1,
         "placement":"shoulder yoke","garment_unit":"carrier-look",
         "attached_to":"carrier-body","visible_basis":"visible shoulder layer",
         "dimensions":{}},
        {"part_id":"carrier-sleeve","kind":"SLEEVE","layer":1,
         "placement":"arms","garment_unit":"carrier-look",
         "attached_to":"visible-yoke","side":"bilateral","quantity":2,
         "visible_basis":"sleeves appear to emerge under the yoke",
         "dimensions":{}}
       ],"pattern_operations":[]}
    ]}
    """#

    static let attachmentAliasFixture = #"""
    {"candidates":[
      {"candidate_id":"unit-alias-target","back_design":"rear unknown",
       "assumptions":[],"parts":[
        {"part_id":"alias-body","kind":"BODY_SHELL","layer":0,
         "placement":"torso","garment_unit":"bodice-unit-01",
         "visible_basis":"visible bodice","dimensions":{}},
        {"part_id":"alias-collar","kind":"COLLAR","layer":1,
         "placement":"neckline","garment_unit":"bodice-unit-01",
         "attached_to":"bodice-unit-01",
         "visible_basis":"visible high collar","dimensions":{}}
       ],"pattern_operations":[]}
    ]}
    """#

    /// Reproduces the compact vision-model address used by the live anime
    /// garment run. `skirt-unit-01` is a semantic label, not a node id. The
    /// overlay has exactly one compatible, lower-layer skirt carrier in its
    /// own garment unit, so the controller may re-address it as a PROPOSED
    /// normalization while retaining the original model token.
    static let uniqueSkirtSemanticAliasFixture = #"""
    {"candidates":[
      {"candidate_id":"unique-skirt-semantic-alias",
       "back_design":"rear construction is not visible",
       "assumptions":["front image grounds only the visible overlay"],
       "parts":[
        {"part_id":"semantic-alias-body","kind":"BODICE","layer":0,
         "placement":"fitted torso","garment_unit":"semantic-alias-look",
         "visible_basis":"visible fitted bodice boundary",
         "dimensions":{"height_cm":42,"circumference_cm":72}},
        {"part_id":"visible-skirt-carrier","kind":"SKIRT","layer":1,
         "placement":"lower flared skirt","garment_unit":"semantic-alias-look",
         "attached_to":"semantic-alias-body",
         "visible_basis":"visible primary skirt silhouette",
         "dimensions":{"height_cm":68,"top_circumference_cm":72,
                       "bottom_circumference_cm":168}},
        {"part_id":"front-skirt-overlay","kind":"OVERLAY","layer":2,
         "placement":"decorative front skirt overlay",
         "detail_role":"asymmetric decorative skirt overlay",
         "garment_unit":"semantic-alias-look",
         "attached_to":"skirt-unit-01",
         "visible_basis":"visible asymmetric front overlay",
         "dimensions":{"height_cm":54,"width_cm":48}}
       ],"pattern_operations":[]}
    ]}
    """#

    /// The same semantic token has two equally compatible lower-layer skirt
    /// carriers. A front image cannot establish which physical layer owns the
    /// overlay, so deterministic normalization must not pick either one.
    static let ambiguousSkirtSemanticAliasFixture = #"""
    {"candidates":[
      {"candidate_id":"ambiguous-skirt-semantic-alias",
       "back_design":"rear construction is not visible",
       "assumptions":["two visible skirt layers are equally plausible carriers"],
       "parts":[
        {"part_id":"ambiguous-alias-body","kind":"BODICE","layer":0,
         "placement":"fitted torso","garment_unit":"ambiguous-alias-look",
         "visible_basis":"visible fitted bodice boundary",
         "dimensions":{"height_cm":42,"circumference_cm":72}},
        {"part_id":"inner-skirt-carrier","kind":"SKIRT","layer":1,
         "placement":"inner lower skirt","detail_role":"inner skirt layer",
         "garment_unit":"ambiguous-alias-look",
         "attached_to":"ambiguous-alias-body",
         "visible_basis":"visible inner skirt layer",
         "dimensions":{"height_cm":64,"top_circumference_cm":72,
                       "bottom_circumference_cm":150}},
        {"part_id":"outer-skirt-carrier","kind":"SKIRT","layer":1,
         "placement":"outer lower skirt","detail_role":"outer skirt layer",
         "garment_unit":"ambiguous-alias-look",
         "attached_to":"ambiguous-alias-body",
         "visible_basis":"visible outer skirt layer",
         "dimensions":{"height_cm":64,"top_circumference_cm":72,
                       "bottom_circumference_cm":170}},
        {"part_id":"ambiguous-front-overlay","kind":"OVERLAY","layer":2,
         "placement":"decorative front skirt overlay",
         "detail_role":"asymmetric decorative skirt overlay",
         "garment_unit":"ambiguous-alias-look",
         "attached_to":"skirt-unit-01",
         "visible_basis":"visible overlay with an unobserved carrier",
         "dimensions":{"height_cm":54,"width_cm":48}}
       ],"pattern_operations":[]}
    ]}
    """#

    static let waistCarrierFixture = #"""
    {"candidates":[
      {"candidate_id":"waist-through-band","back_design":"rear unknown",
       "assumptions":[],"parts":[
        {"part_id":"carrier-waist-body","kind":"BODY_SHELL","layer":0,
         "placement":"torso","garment_unit":"waist-look",
         "visible_basis":"visible torso","dimensions":{}},
        {"part_id":"visible-waistband","kind":"BAND","layer":1,
         "placement":"waist","garment_unit":"waist-look",
         "attached_to":"carrier-waist-body",
         "visible_basis":"visible waistband","dimensions":{}},
        {"part_id":"skirt-through-waistband","kind":"FLARE","layer":1,
         "placement":"lower skirt","garment_unit":"waist-look",
         "attached_to":"visible-waistband",
         "visible_basis":"skirt begins below the waistband","dimensions":{}}
       ],"pattern_operations":[]}
    ]}
    """#

    static let gatheredWaistFixture = #"""
    {"candidates":[
      {"candidate_id":"explicit-gathered-waist","back_design":"rear unknown",
       "assumptions":[],"parts":[
        {"part_id":"gather-body","kind":"BODY_SHELL","layer":0,
         "placement":"torso","garment_unit":"gather-look",
         "visible_basis":"visible fitted torso",
         "dimensions":{"height_cm":42,"circumference_cm":72}},
        {"part_id":"gather-skirt","kind":"FLARE","layer":0,
         "placement":"lower flared skirt","garment_unit":"gather-look",
         "attached_to":"gather-body",
         "visible_basis":"visible fuller skirt begins at waist",
         "dimensions":{"height_cm":68,"top_circumference_cm":90,
                       "bottom_circumference_cm":180}}
       ],"pattern_operations":[]}
    ]}
    """#

    static let compactStraightSkirtTubeFixture = #"""
    {"candidates":[
      {"candidate_id":"compact-straight-skirt-tube",
       "back_design":"rear construction is not visible",
       "assumptions":["the compact image model represented a straight skirt with TUBE geometry"],
       "parts":[
        {"part_id":"straight-skirt-body","kind":"BODY_SHELL","layer":0,
         "placement":"fitted torso","garment_unit":"straight-skirt-dress",
         "visible_basis":"visible fitted torso boundary",
         "dimensions":{"height_cm":43,"circumference_cm":72}},
        {"part_id":"straight-skirt-tube","kind":"TUBE","layer":0,
         "placement":"straight skirt below waist",
         "shape":"straight_skirt","detail_role":"straight skirt",
         "garment_unit":"straight-skirt-dress",
         "attached_to":"straight-skirt-body",
         "visible_basis":"visible continuous straight skirt silhouette without separate legs",
         "dimensions":{"length_cm":68,"circumference_cm":96}}
       ],"pattern_operations":[]}
    ]}
    """#

    static let compactParallelWaistStackFixture = #"""
    {"candidates":[
      {"candidate_id":"compact-parallel-waist-stack",
       "back_design":"rear construction is not visible",
       "assumptions":["the compact image model proposed two visible lower layers on one waist"],
       "parts":[
        {"part_id":"stack-body","kind":"BODY_SHELL","layer":0,
         "placement":"fitted torso","garment_unit":"stacked-dress",
         "visible_basis":"visible fitted torso boundary",
         "dimensions":{"height_cm":43,"circumference_cm":72}},
        {"part_id":"stack-inner-flare","kind":"FLARE","layer":1,
         "placement":"inner skirt layer","detail_role":"inner skirt",
         "garment_unit":"stacked-dress","attached_to":"stack-body",
         "visible_basis":"visible inner flared lower layer",
         "dimensions":{"height_cm":58,"top_circumference_cm":72,
                       "bottom_circumference_cm":144}},
        {"part_id":"stack-outer-tube","kind":"TUBE","layer":2,
         "placement":"outer straight skirt layer","shape":"straight_skirt",
         "detail_role":"outer skirt","garment_unit":"stacked-dress",
         "attached_to":"stack-body",
         "visible_basis":"visible outer straight lower layer without leg separation",
         "dimensions":{"length_cm":66,"circumference_cm":96}}
       ],"pattern_operations":[]}
    ]}
    """#

    static let ambiguousLegUnitGarterFixture = #"""
    {"candidates":[
      {"candidate_id":"garter-unit-alias","back_design":"rear unknown",
       "assumptions":[],"parts":[
        {"part_id":"garter-top","kind":"BODY_SHELL","layer":0,
         "placement":"torso","garment_unit":"top-unit",
         "visible_basis":"visible top","dimensions":{}},
        {"part_id":"garter-leg-left","kind":"TUBE","layer":0,
         "placement":"left leg","garment_unit":"leggings-unit-01",
         "side":"left","shape":"trouser_leg",
         "visible_basis":"visible left legging","dimensions":{}},
        {"part_id":"garter-leg-right","kind":"TUBE","layer":0,
         "placement":"right leg","garment_unit":"leggings-unit-01",
         "side":"right","shape":"trouser_leg",
         "visible_basis":"visible right legging","dimensions":{}},
        {"part_id":"garter-01","kind":"BAND","layer":2,
         "placement":"left thigh garter strap",
         "garment_unit":"leggings-unit-01",
         "attached_to":"leggings-unit-01",
         "visible_basis":"visible narrow thigh strap","dimensions":{}}
       ],"pattern_operations":[]}
    ]}
    """#

    static let directBodyGarterFixture = #"""
    {"candidates":[
      {"candidate_id":"garter-direct-body","back_design":"rear unknown",
       "assumptions":[],"parts":[
        {"part_id":"direct-garter-body","kind":"BODY_SHELL","layer":0,
         "placement":"torso","garment_unit":"direct-garter-look",
         "visible_basis":"visible torso","dimensions":{}},
        {"part_id":"direct-thigh-garter","kind":"BAND","layer":2,
         "placement":"left thigh garter strap",
         "detail_role":"decorative thigh strap",
         "garment_unit":"direct-garter-look",
         "attached_to":"direct-garter-body",
         "visible_basis":"visible narrow thigh strap","dimensions":{}}
       ],"pattern_operations":[]}
    ]}
    """#

    static let boundedSleeveJoinFixture = #"""
    {"candidates":[
      {"candidate_id":"bounded-segmented-sleeve","back_design":"rear unknown",
       "assumptions":[],"parts":[
        {"part_id":"segmented-body","kind":"BODY_SHELL","layer":0,
         "placement":"torso","garment_unit":"segmented-look",
         "visible_basis":"visible torso","dimensions":{}},
        {"part_id":"upper-sleeve-segment","kind":"SLEEVE","layer":1,
         "placement":"left upper arm","side":"left",
         "garment_unit":"segmented-look","attached_to":"segmented-body",
         "visible_basis":"visible upper sleeve segment",
         "dimensions":{"length_cm":30,"upper_circumference_cm":34,
                       "cuff_circumference_cm":22}},
        {"part_id":"lower-sleeve-segment","kind":"SLEEVE","layer":1,
         "placement":"left lower arm","side":"left",
         "garment_unit":"segmented-look",
         "attached_to":"upper-sleeve-segment",
         "attachment_relation":"JOIN",
         "visible_basis":"visible lower sleeve extension",
         "dimensions":{"length_cm":28,"cuff_circumference_cm":16}}
       ],"pattern_operations":[]}
    ]}
    """#

    static let explicitMismatchedSleeveJoinFixture = #"""
    {"candidates":[
      {"candidate_id":"explicit-mismatched-sleeve","back_design":"rear unknown",
       "assumptions":[],"parts":[
        {"part_id":"explicit-body","kind":"BODY_SHELL","layer":0,
         "placement":"torso","garment_unit":"explicit-look",
         "visible_basis":"visible torso","dimensions":{}},
        {"part_id":"explicit-upper-sleeve","kind":"SLEEVE","layer":1,
         "placement":"left upper arm","side":"left",
         "garment_unit":"explicit-look","attached_to":"explicit-body",
         "visible_basis":"visible upper sleeve segment",
         "dimensions":{"length_cm":30,"upper_circumference_cm":34,
                       "cuff_circumference_cm":22}},
        {"part_id":"explicit-lower-sleeve","kind":"SLEEVE","layer":1,
         "placement":"left lower arm","side":"left",
         "garment_unit":"explicit-look","attached_to":"explicit-upper-sleeve",
         "attachment_relation":"JOIN",
         "visible_basis":"visible lower sleeve extension",
         "dimensions":{"length_cm":28,"upper_circumference_cm":36,
                       "cuff_circumference_cm":16}}
       ],"pattern_operations":[]}
    ]}
    """#

    static let shorterMismatchedSleeveJoinFixture = #"""
    {"candidates":[
      {"candidate_id":"shorter-mismatched-sleeve","back_design":"rear unknown",
       "assumptions":[],"parts":[
        {"part_id":"shorter-body","kind":"BODY_SHELL","layer":0,
         "placement":"torso","garment_unit":"shorter-look",
         "visible_basis":"visible torso","dimensions":{}},
        {"part_id":"shorter-upper-sleeve","kind":"SLEEVE","layer":1,
         "placement":"left upper arm","side":"left",
         "garment_unit":"shorter-look","attached_to":"shorter-body",
         "visible_basis":"visible upper sleeve segment",
         "dimensions":{"length_cm":30,"upper_circumference_cm":34,
                       "cuff_circumference_cm":22}},
        {"part_id":"shorter-lower-sleeve","kind":"SLEEVE","layer":1,
         "placement":"left lower sleeve extension","side":"left",
         "garment_unit":"shorter-look","attached_to":"shorter-upper-sleeve",
         "attachment_relation":"JOIN",
         "visible_basis":"visible narrower lower sleeve extension",
         "dimensions":{"length_cm":28,"upper_circumference_cm":18,
                       "cuff_circumference_cm":16}}
       ],"pattern_operations":[]}
    ]}
    """#

    static func callActualPartsPipeline(
        candidates: [[String: Any]]
    ) -> [String: Any]? {
        let request: [String: Any] = [
            "parts_ir": [
                "schema": "garment.parts-ir.v1",
                "state": "PROPOSED",
                "candidates": candidates,
            ],
            "use_bounded_preview_profile": true,
            "candidate_count": candidates.count,
        ]
        guard JSONSerialization.isValidJSONObject(request),
              let requestData = try? JSONSerialization.data(
                withJSONObject: request, options: [.sortedKeys]),
              let requestText = String(data: requestData, encoding: .utf8) else {
            return nil
        }
        let rpc: [String: Any] = [
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": [
                "name": "garment_parts_ir_pipeline",
                "arguments": ["json_text": requestText],
            ],
        ]
        guard let rpcData = try? JSONSerialization.data(withJSONObject: rpc),
              var rpcLine = String(data: rpcData, encoding: .utf8) else { return nil }
        rpcLine.append("\n")
        let testFile = URL(fileURLWithPath: #filePath)
        let repository = testFile.deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
        let temporary = FileManager.default.temporaryDirectory.appendingPathComponent(
            "garment-vision-ornament-\(UUID().uuidString)", isDirectory: true)
        try? FileManager.default.createDirectory(
            at: temporary, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporary) }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = ["python3", "-m", "photoloset.mcp"]
        process.currentDirectoryURL = repository
        var environment = ProcessInfo.processInfo.environment
        environment["PHOTOLOSET_HOME"] = temporary.path
        process.environment = environment
        let input = Pipe(), output = Pipe(), error = Pipe()
        process.standardInput = input
        process.standardOutput = output
        process.standardError = error
        do { try process.run() } catch { return nil }
        input.fileHandleForWriting.write(Data(rpcLine.utf8))
        try? input.fileHandleForWriting.close()
        let stdout = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard process.terminationStatus == 0,
              let text = String(data: stdout, encoding: .utf8),
              let line = text.split(separator: "\n").first,
              let responseData = String(line).data(using: .utf8),
              let response = try? JSONSerialization.jsonObject(with: responseData)
                as? [String: Any],
              let result = response["result"] as? [String: Any],
              let content = result["content"] as? [[String: Any]],
              let payloadText = content.first?["text"] as? String,
              let payloadData = payloadText.data(using: .utf8),
              let payload = try? JSONSerialization.jsonObject(with: payloadData)
                as? [String: Any] else { return nil }
        return payload
    }

    static func sourceFailures() -> [String] {
        let testFile = URL(fileURLWithPath: #filePath)
        let appRoot = testFile.deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let controllerURL = appRoot.appendingPathComponent(
            "Sources/Verantyx/Engine/GarmentFactoryReactController.swift")
        guard let source = try? String(contentsOf: controllerURL, encoding: .utf8)
        else { return ["CONTROLLER_SOURCE_UNREADABLE"] }
        var failures: [String] = []
        func require(_ condition: Bool, _ code: String) {
            if !condition { failures.append(code) }
        }
        for token in ["BOW", "RIBBON", "ROSETTE", "TIE", "FLAP",
                      "RUFFLE", "FRILL"] {
            require(source.contains("\"\(token)\""),
                    "VISION_KIND_\(token)_MISSING")
        }
        for mapping in [
            "\"BOW\": \"OVERLAY\"", "\"RIBBON\": \"BAND\"",
            "\"ROSETTE\": \"OVERLAY\"", "\"TIE\": \"BAND\"",
            "\"FLAP\": \"OVERLAY\"", "\"RUFFLE\": \"BAND\"",
            "\"FRILL\": \"BAND\"",
        ] {
            require(source.contains(mapping),
                    "PROPOSED_GEOMETRY_MAPPING_MISSING_\(mapping)")
        }
        require(source.contains("PROPOSED_NORMALIZATION") &&
                source.contains("PROPOSED_NORMALIZATION_FROM_MODEL_GEOMETRY"),
                "NORMALIZATION_AUTHORITY_BOUNDARY_MISSING")
        require(source.contains("uncompiled_visual_parts") &&
                source.contains("PROPOSED_UNCOMPILED") &&
                source.contains("representation_complete"),
                "UNSUPPORTED_VISUAL_PART_RETENTION_MISSING")
        require(source.contains("not_measured_from_image") &&
                source.contains("normalization_not_measurement"),
                "NORMALIZED_DIMENSIONS_CAN_MASQUERADE_AS_MEASUREMENTS")
        require(source.contains("\"rear_authority\": \"PROPOSED\"") &&
                source.contains("\"material_authority\": \"UNKNOWN\"") &&
                source.contains("\"manufacturing_ready\": false") &&
                source.contains("\"manufacturing_certified\": false"),
                "VISION_ORNAMENT_OUTPUT_CAN_CLAIM_HIDDEN_OR_MANUFACTURING_FACTS")
        require(source.contains("func runVisionPartsPipeline") &&
                source.contains("garment_parts_ir_pipeline") &&
                source.contains("var merged = hypothesis"),
                "ORNAMENT_STRUCTURE_DOES_NOT_REACH_PARTS_PIPELINE")
        require(source.contains("presentRoutedPreviewNodeIDs") &&
                source.contains(".intersection(structuralNodeIDs)") &&
                source.contains("nodes.count - presentRoutedPreviewNodeIDs.count"),
                "DIRECT_TYPED_ORNAMENT_ROUTE_SUBTRACTS_NONEXISTENT_ALIAS_NODE")
        require(source.contains("[\"PLEAT\", \"GATHER\", \"DART\", \"FOLD\"]") &&
                source.contains("finished_length_cm") &&
                source.contains("ratio > 1, ratio <= 8"),
                "TYPED_VISION_GATHER_PARAMETER_GATE_MISSING")
        require(source.contains("DERIVED_AFTER_EXACT_COMPILED_TARGET_RESOLUTION") &&
                source.contains("UNKNOWN_VISION_GATHER_TARGET_LENGTH") &&
                source.contains("garment_pattern_transform"),
                "RATIO_ONLY_GATHER_CAN_RUN_BEFORE_EXACT_TARGET_RESOLUTION")
        require(source.contains("canonical_pattern_mutated\": false"),
                "VISION_GATHER_CAN_MUTATE_CANONICAL_PATTERN")
        require(source.contains("expandSingleVisibleVisionCandidate") &&
                source.contains("DETERMINISTIC_FRONT_ONLY_EXPANSION") &&
                source.contains("center-back-opening") &&
                source.contains("side-opening-closed-back") &&
                source.contains("closed-back-stretch"),
                "SINGLE_VISIBLE_CANDIDATE_REAR_EXPANSION_MISSING")
        require(source.contains("PROPOSED_EXCLUDED_NON_GARMENT") &&
                source.contains("excluded_from_structure_nodes") &&
                source.contains("footwearTerms"),
                "EXPLICIT_FOOTWEAR_EXCLUSION_BOUNDARY_MISSING")
        require(source.contains("BILATERAL_SLEEVE_NORMALIZATION") &&
                source.contains("ASYMMETRIC_OR_UNRESOLVED_SLEEVE_PAIR") &&
                source.contains("source_part_ids") &&
                source.contains("remapped_child_addresses") &&
                source.contains("parent_instance_address"),
                "BILATERAL_SLEEVE_HARD_STOP_NORMALIZATION_MISSING")
        require(source.contains("LAYERED_WAIST_NORMALIZATION") &&
                source.contains("OUTER_BODY_SKIRT_PLUS_STANDALONE_UNDERLAYER") &&
                source.contains("TROUSER_GUSSET_COMPLETION"),
                "LAYERED_WAIST_HARD_STOP_NORMALIZATION_MISSING")
        require(source.contains("normalizeVisionSharedWaistStacks") &&
                source.contains("waist_stack_parent") &&
                source.contains("waist_stack_construction_mode") &&
                source.contains("order_rule\": \"layer_then_node_id") &&
                source.contains("PROPOSED_SHARED_WAIST_STACK_NORMALIZATION"),
                "PARALLEL_WAIST_STACK_CONTRACT_MISSING")
        require(source.contains("BELT_CONTACT_ACCESSORY") &&
                source.contains("dimensions_changed\": false") &&
                source.contains("join_created\": false"),
                "MISMATCHED_BELT_CONTACT_BOUNDARY_MISSING")
        require(source.contains("sibling_pipeline_reviews") &&
                source.contains("[\"PROPOSED\", \"UNRESOLVED\"]"),
                "PARTIAL_PIPELINE_SUCCESS_REVIEW_BOUNDARY_MISSING")
        require(source.contains("normalizeVisionAttachedGoreOverlays") &&
                source.contains("PROPOSED_ATTACHED_GORE_OVERLAY_NORMALIZATION") &&
                source.contains("PROPOSED_GORE_OVERLAY") &&
                source.contains("gore_overlay_normalization"),
                "ATTACHED_GORE_OVERLAY_TYPED_NORMALIZATION_MISSING")
        require(source.contains("PROPOSED_SLEEVE_GATHER_RELATION") &&
                source.contains("PROPOSED_SLEEVE_JOIN_PREVIEW_REDRAFT") &&
                source.contains("\"sleeve_join_mode\"") &&
                source.contains("\"sleeve_join_state\"") &&
                source.contains("\"sleeve_join_provenance\"") &&
                source.contains("\"GATHER\", \"PLEAT\", \"CUFF_YOKE\""),
                "SEGMENTED_SLEEVE_RELATION_REPAIR_CONTRACT_MISSING")
        require(source.contains(
                    "reconcileBoundedPreviewGatheredBandBoundaries") &&
                source.contains(
                    "PROPOSED_GATHERED_BAND_BOUNDARY_NORMALIZATION") &&
                source.contains("PROPOSED_TERMINAL_EDGE_ALTERNATIVE") &&
                source.contains("PROPOSED_GATHER_CUT_LENGTH_REDRAFT") &&
                source.contains("unselected_target_roles") &&
                source.contains("approval_required"),
                "GATHERED_BAND_PREVIEW_REPAIR_CONTRACT_MISSING")
        require(source.contains("PROPOSED_STRUCTURAL_BAND_SEAM_REDRAFT") &&
                source.contains("original_model_value_cm") &&
                source.contains("modelKind == \"WAISTBAND\"") &&
                source.contains(
                    "\"approval_required\": structuralAliasRedraft"),
                "STRUCTURAL_WAISTBAND_PREVIEW_REDRAFT_CONTRACT_MISSING")
        require(source.contains("visible_front_inventory") &&
                source.contains("PROPOSED_VISION_UNCONFIRMED") &&
                source.contains("semantic_role and visible_color are required") &&
                source.contains("same-camera 3D reprojection check") &&
                source.contains("must not replace either trouser TUBE"),
                "VISIBLE_FRONT_TARGET_INVENTORY_CONTRACT_MISSING")
        return failures
    }

    @MainActor
    static func parsedFixture() -> ([String: Any], [[String: Any]])? {
        guard let parsed = GarmentFactoryReactController.parseVisionProposal(fixture),
              let hypotheses = parsed["hypotheses"] as? [[String: Any]],
              hypotheses.count == 2 else { return nil }
        return (parsed, hypotheses)
    }

    @MainActor
    static func executionFailures() async -> [String] {
        var failures: [String] = []
        func require(_ condition: Bool, _ code: String) {
            if !condition { failures.append(code) }
        }

        let sameUnitMalformedBody = #"""
        {"candidates":[{"candidate_id":"layered-body","back_design":"rear not visible","parts":[
          {"part_id":"inner-body","kind":"BODY_SHELL","layer":0,"garment_unit":"look","dimensions":{"height_cm":42,"circumference_cm":92}},
          {"part_id":"inner-sleeve","kind":"SLEEVE","layer":1,"garment_unit":"look","attached_to":"inner-body","dimensions":{"length_cm":58,"upper_circumference_cm":34,"cuff_circumference_cm":20}},
          {"part_id":"outer-body","kind":"BODY_SHELL","layer":2,"garment_unit":"look","attached_to":"inner-sleeve","dimensions":{"height_cm":38,"circumference_cm":98}}
        ]}]}
        """#
        if let parsed = GarmentFactoryReactController.parseVisionProposal(
                sameUnitMalformedBody),
           let candidates = parsed["hypotheses"] as? [[String: Any]],
           let structure = candidates.first?["structure"] as? [String: Any],
           let nodes = structure["nodes"] as? [[String: Any]],
           let outer = nodes.first(where: {
               $0["node_id"] as? String == "outer-body"
           }),
           let attributes = outer["attributes"] as? [String: Any] {
            require(attributes["attached_to"] as? String == "inner-body",
                    "LAYERED_BODY_WAS_NOT_READDRESSED_TO_UNIQUE_LOWER_BODY")
            require(attributes["model_attached_to"] as? String ==
                        "inner-sleeve",
                    "LAYERED_BODY_DID_NOT_RETAIN_MODEL_TARGET_PROVENANCE")
            let normalization = attributes["body_layer_anchor_normalization"]
                as? [String: Any]
            require(normalization?["state"] as? String ==
                        "PROPOSED_NORMALIZATION" &&
                    normalization?["sewn_join_observed"] as? Bool == false,
                    "LAYERED_BODY_NORMALIZATION_CLAIMED_AN_OBSERVED_SEAM")
        } else {
            failures.append("LAYERED_BODY_NORMALIZATION_FIXTURE_WAS_REJECTED")
        }

        let crossUnitMalformedBody = #"""
        {"candidates":[{"candidate_id":"separate-vest","back_design":"rear not visible","parts":[
          {"part_id":"blouse-body","kind":"BODY_SHELL","layer":0,"garment_unit":"blouse","dimensions":{"height_cm":45,"circumference_cm":92}},
          {"part_id":"blouse-sleeve","kind":"SLEEVE","layer":1,"garment_unit":"blouse","attached_to":"blouse-body","dimensions":{"length_cm":58,"upper_circumference_cm":34,"cuff_circumference_cm":20}},
          {"part_id":"vest-body","kind":"BODY_SHELL","layer":2,"garment_unit":"vest","attached_to":"blouse-sleeve","dimensions":{"height_cm":34,"circumference_cm":98}}
        ]}]}
        """#
        if let parsed = GarmentFactoryReactController.parseVisionProposal(
                crossUnitMalformedBody),
           let candidates = parsed["hypotheses"] as? [[String: Any]],
           let structure = candidates.first?["structure"] as? [String: Any],
           let nodes = structure["nodes"] as? [[String: Any]],
           let vest = nodes.first(where: {
               $0["node_id"] as? String == "vest-body"
           }),
           let attributes = vest["attributes"] as? [String: Any] {
            require(attributes["attached_to"] == nil,
                    "INDEPENDENT_VEST_RETAINED_CROSS_GARMENT_ATTACHMENT")
            require(attributes["attachment_state"] as? String ==
                        "PROPOSED_SEPARATE_BODY_SHELL_ROOT",
                    "INDEPENDENT_VEST_WAS_NOT_KEPT_AS_PROPOSED_ROOT")
            let normalization = attributes["body_layer_anchor_normalization"]
                as? [String: Any]
            require(normalization?["sewn_join_created"] as? Bool == false,
                    "INDEPENDENT_VEST_NORMALIZATION_INVENTED_A_SEAM")
        } else {
            failures.append("INDEPENDENT_VEST_NORMALIZATION_FIXTURE_WAS_REJECTED")
        }

        guard let (_, hypotheses) = parsedFixture() else {
            return ["PRODUCTION_PARSE_VISION_PROPOSAL_REFUSED_TWO_CANDIDATES"]
        }
        let byID = Dictionary(uniqueKeysWithValues: hypotheses.compactMap {
            row -> (String, [String: Any])? in
            guard let id = row["candidate_id"] as? String else { return nil }
            return (id, row)
        })
        require(byID.count == 2, "PARSED_CANDIDATE_IDENTITIES_LOST")

        guard let inventoryParsed =
                GarmentFactoryReactController.parseVisionProposal(
                    layeredSeparatesVisibleInventoryFixture),
              let inventoryCandidates = inventoryParsed["hypotheses"]
                as? [[String: Any]], inventoryCandidates.count == 3,
              let inventory = inventoryCandidates.first?["visible_front_inventory"]
                as? [[String: Any]] else {
            failures.append("LAYERED_SEPARATES_VISIBLE_INVENTORY_WAS_REJECTED")
            return failures
        }
        let inventoryByID = Dictionary(uniqueKeysWithValues: inventory.compactMap {
            row -> (String, [String: Any])? in
            guard let id = row["inventory_part_id"] as? String else { return nil }
            return (id, row)
        })
        require(inventoryByID.count == 5 &&
                inventoryByID["ivory-blouse"]?["semantic_role"] as? String ==
                    "white blouse" &&
                inventoryByID["navy-vest"]?["garment_unit"] as? String ==
                    "vest" &&
                inventoryByID["red-trouser-left"]?["normalized_kind"]
                    as? String == "TUBE" &&
                inventoryByID["red-trouser-left"]?["side"] as? String ==
                    "left" &&
                inventoryByID["red-trouser-right"]?["side"] as? String ==
                    "right" &&
                inventoryByID["teal-right-wrap"]?["normalized_kind"]
                    as? String == "OVERLAY" &&
                inventoryByID["teal-right-wrap"]?["visible_color"] as? String ==
                    "translucent teal" &&
                inventoryByID.values.allSatisfy {
                    $0["state"] as? String ==
                        "PROPOSED_VISION_UNCONFIRMED" &&
                    $0["rear_observed"] as? Bool == false &&
                    $0["material_identity_observed"] as? Bool == false
                },
                "VISIBLE_INVENTORY_LOST_SEPARATE_TROUSERS_OR_OVERLAY")

        let layeredCandidate = inventoryCandidates.first ?? [:]
        let layeredStructure = layeredCandidate["structure"] as? [String: Any]
        let layeredNodes = layeredStructure?["nodes"] as? [[String: Any]] ?? []
        let rightWrap = layeredNodes.first {
            $0["node_id"] as? String == "teal-right-wrap"
        }
        let rightWrapAttributes = rightWrap?["attributes"] as? [String: Any]
        let rightWrapProvenance = rightWrapAttributes?["attachment_provenance"]
            as? [String: Any]
        require(
            rightWrapAttributes?["attached_to"] as? String ==
                "red-trouser-right" &&
            rightWrapAttributes?["attachment_state"] as? String ==
                "PROPOSED_VISIBLE_SIDE_CARRIER" &&
            rightWrapProvenance?["sewn_join_observed"] as? Bool == false &&
            rightWrapProvenance?["rear_construction_observed"] as? Bool ==
                false &&
            rightWrapProvenance?["requires_human_approval"] as? Bool == true,
            "VISIBLE_RIGHT_OVERLAY_DID_NOT_RESOLVE_TO_ONLY_RIGHT_CARRIER_AS_PROPOSAL")

        func node(_ id: String, in candidate: [String: Any]) -> [String: Any]? {
            guard let structure = candidate["structure"] as? [String: Any],
                  let nodes = structure["nodes"] as? [[String: Any]] else { return nil }
            return nodes.first { $0["node_id"] as? String == id }
        }
        func assertNormalized(_ partID: String, candidateID: String,
                              sourceKind: String, primitive: String,
                              dimensions expected: [String: Double]) {
            guard let candidate = byID[candidateID],
                  let part = node(partID, in: candidate),
                  let dimensions = part["dimensions"] as? [String: Double],
                  let attributes = part["attributes"] as? [String: Any] else {
                failures.append("NORMALIZED_PART_MISSING_\(partID)")
                return
            }
            require(part["kind"] as? String == primitive,
                    "NORMALIZED_PRIMITIVE_WRONG_\(partID)")
            require(attributes["model_kind"] as? String == sourceKind,
                    "SOURCE_VISUAL_KIND_LOST_\(partID)")
            require(attributes["primitive_alias"] as? String == primitive,
                    "PRIMITIVE_ALIAS_LOST_\(partID)")
            require(attributes["alias_state"] as? String == "PROPOSED_NORMALIZATION",
                    "NORMALIZATION_PROMOTED_\(partID)")
            require(attributes["normalization_not_measurement"] as? Bool == true,
                    "NORMALIZATION_BECAME_MEASUREMENT_\(partID)")
            for (name, value) in expected {
                require(abs((dimensions[name] ?? -1) - value) < 0.000_001,
                        "NORMALIZED_DIMENSION_WRONG_\(partID)_\(name)")
            }
            let provenance = attributes["dimension_provenance"]
                as? [String: [String: Any]] ?? [:]
            for name in expected.keys {
                require(provenance[name]?["state"] as? String == "PROPOSED",
                        "DIMENSION_AUTHORITY_WRONG_\(partID)_\(name)")
                require(provenance[name]?["not_measured_from_image"] as? Bool == true,
                        "IMAGE_MEASUREMENT_CLAIM_\(partID)_\(name)")
            }
        }

        assertNormalized("ruffle-a", candidateID: "ornate-front-a",
                         sourceKind: "RUFFLE", primitive: "BAND",
                         dimensions: ["length_cm": 96, "width_cm": 7])
        assertNormalized("frill-b", candidateID: "ornate-front-b",
                         sourceKind: "FRILL", primitive: "BAND",
                         dimensions: ["length_cm": 100, "width_cm": 6])
        let routedOrnamentIDs = Set(hypotheses.flatMap { candidate in
            (candidate["typed_ornament_proposals"] as? [[String: Any]] ?? [])
                .compactMap { row -> String? in
                    guard row["state"] as? String == "PROPOSED",
                          row["authority"] as? String == "PROPOSED" else {
                        return nil
                    }
                    return row["part_id"] as? String
                }
        })
        require(routedOrnamentIDs == Set([
            "bow-a", "ribbon-b", "rosette-b", "tie-b", "flap-b",
        ]), "DIRECT_TYPED_ORNAMENT_PROPOSALS_WERE_NOT_PRESERVED")

        let firstOperations = byID["ornate-front-a"]?["pattern_operation_proposals"]
            as? [[String: Any]] ?? []
        let secondOperations = byID["ornate-front-b"]?["pattern_operation_proposals"]
            as? [[String: Any]] ?? []
        let ratioOnly = firstOperations.first {
            $0["operation_id"] as? String == "gather-ratio-only"
        }
        let ratioOnlyParameters = ratioOnly?["parameters"] as? [String: Any]
        require(ratioOnly?["kind"] as? String == "GATHER" &&
                ratioOnly?["state"] as? String == "PROPOSED" &&
                ratioOnlyParameters?["ratio"] as? Double == 2 &&
                ratioOnlyParameters?["finished_length_cm"] == nil,
                "RATIO_ONLY_GATHER_NOT_ACCEPTED_AS_TYPED_PROPOSAL")
        for kind in ["PLEAT", "DART", "FOLD"] {
            let row = secondOperations.first { $0["kind"] as? String == kind }
            require(row?["state"] as? String == "PROPOSED" &&
                    (row?["review"] as? [String: Any])?["required"] as? Bool == false,
                    "EXISTING_\(kind)_REGRESSION")
        }
        let finishedOnly = secondOperations.first {
            $0["operation_id"] as? String == "gather-finished-only"
        }
        let finishedParameters = finishedOnly?["parameters"] as? [String: Any]
        require(finishedParameters?["finished_length_cm"] as? Double == 10 &&
                finishedParameters?["ratio"] == nil,
                "FINISHED_LENGTH_ONLY_GATHER_NOT_ACCEPTED")
        let both = secondOperations.first {
            $0["operation_id"] as? String == "gather-both"
        }
        let bothParameters = both?["parameters"] as? [String: Any]
        require(bothParameters?["finished_length_cm"] as? Double == 10 &&
                bothParameters?["ratio"] as? Double == 2,
                "GATHER_WITH_BOTH_PARAMETERS_NOT_ACCEPTED")
        let excessive = secondOperations.first {
            $0["operation_id"] as? String == "gather-ratio-too-large"
        }
        require((excessive?["review"] as? [String: Any])?["code"] as? String ==
                "UNKNOWN_VISION_OPERATION_PARAMETERS" &&
                (excessive?["execution"] as? [String: Any])?["status"] as? String ==
                "NOT_EXECUTED_REVIEW",
                "UNREASONABLE_GATHER_RATIO_DID_NOT_FAIL_CLOSED")

        if let first = byID["ornate-front-a"] {
            let unsupported = first["uncompiled_visual_parts"] as? [[String: Any]]
            require(unsupported?.count == 1, "UNSUPPORTED_PART_SILENTLY_DROPPED")
            require(unsupported?.first?["model_kind"] as? String == "BEADING",
                    "UNSUPPORTED_PART_KIND_LOST")
            require(unsupported?.first?["state"] as? String == "PROPOSED_UNCOMPILED",
                    "UNSUPPORTED_PART_AUTHORITY_ESCALATED")
            require(unsupported?.first?["manufacturing_ready"] as? Bool == false,
                    "UNSUPPORTED_PART_CLAIMS_MANUFACTURING_READY")
            require(first["representation_complete"] as? Bool == false,
                    "INCOMPLETE_REPRESENTATION_MARKED_COMPLETE")
        }
        for candidate in hypotheses {
            require(candidate["rear_authority"] as? String == "PROPOSED",
                    "REAR_PROPOSAL_PROMOTED")
            require(candidate["material_authority"] as? String == "UNKNOWN",
                    "MATERIAL_PROPOSAL_PROMOTED")
            require(candidate["requires_human_approval"] as? Bool == true,
                    "HUMAN_APPROVAL_GATE_MISSING")
            require(candidate["manufacturing_ready"] as? Bool == false,
                    "VISION_CANDIDATE_CLAIMS_MANUFACTURING_READY")
            require(candidate["manufacturing_certified"] as? Bool == false,
                    "VISION_CANDIDATE_CLAIMS_CERTIFICATION")
            let back = candidate["back_design"] as? String ?? ""
            require(!back.uppercased().contains("OBSERVED") &&
                    !back.uppercased().contains("ANSWER") &&
                    !back.uppercased().contains("CERTIFIED"),
                    "MODEL_BACK_AUTHORITY_VOCABULARY_ESCAPED")
        }

        final class Capture: @unchecked Sendable {
            var pipelineInput: [String: Any]?
            var pipelineReturned = false
            var transformBeforePipeline = false
            var transformInputs: [[String: Any]] = []
        }
        let capture = Capture()
        let controller = GarmentFactoryReactController(
            door: { _, _ in ["verdict": "UNKNOWN_UNUSED_TEST_DOOR"] },
            toolDoor: { tool, arguments in
                guard let text = arguments["json_text"] as? String,
                      let data = text.data(using: .utf8),
                      let request = try? JSONSerialization.jsonObject(with: data)
                        as? [String: Any]
                else { return ["verdict": "UNKNOWN_TEST_TOOL_INPUT"] }
                if tool == "garment_pattern_transform" {
                    if !capture.pipelineReturned { capture.transformBeforePipeline = true }
                    capture.transformInputs.append(request)
                    return ["verdict": "ANSWER", "after_digest": "test-transform-digest"]
                }
                guard tool == "garment_parts_ir_pipeline",
                      let partsIR = request["parts_ir"] as? [String: Any],
                      let candidates = partsIR["candidates"] as? [[String: Any]]
                else { return ["verdict": "UNKNOWN_TEST_PIPELINE_INPUT"] }
                capture.pipelineInput = request
                let outputs: [[String: Any]] = candidates.compactMap { candidate in
                    guard let id = candidate["candidate_id"] as? String,
                          let original = byID[id],
                          let structure = original["structure"] as? [String: Any],
                          let submittedParts = candidate["parts"] as? [[String: Any]]
                    else { return nil }
                    let pieces: [[String: Any]] = submittedParts.compactMap { part in
                        guard let nodeID = part["part_id"] as? String else { return nil }
                        return [
                            "piece_id": nodeID,
                            "node_id": nodeID,
                            "outline": [[0.0, 0.0], [20.0, 0.0],
                                        [20.0, 10.0], [0.0, 10.0]],
                            "edges": ["e0": ["length": 20.0],
                                      "e1": ["length": 10.0],
                                      "e2": ["length": 20.0],
                                      "e3": ["length": 10.0]],
                        ]
                    }
                    return [
                        "candidate_id": id,
                        "execution_status": "SUCCEEDED",
                        "structure": structure,
                        "flat_pattern": ["pieces": pieces],
                        "artifact_binding": ["same_structure_digest": true],
                    ]
                }
                capture.pipelineReturned = true
                return ["verdict": "PROPOSED", "candidates": outputs]
            })
        let compiled = await controller.runVisionPartsPipeline(hypotheses)
        require(compiled?.count == 2,
                "RUN_VISION_PARTS_PIPELINE_REJECTED_NORMALIZED_STRUCTURE")
        let sentPartsIR = capture.pipelineInput?["parts_ir"] as? [String: Any]
        let sentCandidates = sentPartsIR?["candidates"] as? [[String: Any]] ?? []
        let sentKinds = sentCandidates.flatMap {
            ($0["parts"] as? [[String: Any]] ?? []).compactMap {
                $0["kind"] as? String
            }
        }
        let supported = Set([
            "BODY_SHELL", "BAND", "OVERLAY",
            "BOW", "RIBBON", "ROSETTE", "TIE", "FLAP",
        ])
        require(Set(sentKinds).isSubset(of: supported),
                "RUN_PIPELINE_RECEIVED_UNSUPPORTED_OR_GARMENT_CLASS_KIND")
        let sentParts = sentCandidates.flatMap {
            $0["parts"] as? [[String: Any]] ?? []
        }
        require(!sentParts.contains {
            ($0["attached_to"] as? String)?.lowercased() == "none"
        }, "MODEL_NULL_ATTACHMENT_SENTINEL_BECAME_A_NODE_REFERENCE")
        let routedBow = sentParts.first { $0["part_id"] as? String == "bow-a" }
        let routedBowDimensions = routedBow?["dimensions"] as? [String: Any]
        let routedBowLength = routedBowDimensions?["body_length_cm"]
            as? [String: Any]
        let routedBowWidth = routedBowDimensions?["body_width_cm"]
            as? [String: Any]
        require(routedBow?["kind"] as? String == "BOW" &&
                (routedBowLength?["value_cm"] as? NSNumber)?.doubleValue == 24 &&
                (routedBowWidth?["value_cm"] as? NSNumber)?.doubleValue == 8 &&
                routedBowLength?["state"] as? String == "PROPOSED" &&
                routedBowLength?["not_measured_from_image"] as? Bool == true,
                "MCP_REQUEST_LOST_ORIGINAL_TYPED_ORNAMENT_GEOMETRY")
        require(compiled?.first(where: {
            $0["candidate_id"] as? String == "ornate-front-a"
        })?["uncompiled_visual_parts"] as? [[String: Any]] != nil,
                "RUN_PIPELINE_MERGE_DROPPED_UNSUPPORTED_PARTS")
        require(!capture.transformBeforePipeline,
                "GATHER_OR_EXISTING_OPERATION_RAN_BEFORE_PIPELINE_TARGET_RESOLUTION")
        require(capture.transformInputs.count == 6,
                "ELIGIBLE_PATTERN_OPERATION_MCP_CALL_COUNT_WRONG")
        let ratioOnlyTransform = capture.transformInputs.first { request in
            let operation = request["operation"] as? [String: Any]
            return operation?["kind"] as? String == "GATHER" &&
                operation?["finished_length_source"] as? String ==
                    "DERIVED_AFTER_EXACT_COMPILED_TARGET_RESOLUTION"
        }
        let resolvedGather = ratioOnlyTransform?["operation"] as? [String: Any]
        require(resolvedGather?["finished_length_cm"] as? Double == 10 &&
                resolvedGather?["ratio"] as? Double == 2 &&
                resolvedGather?["edge"] as? String == "e0",
                "RATIO_ONLY_GATHER_NOT_COMPLETED_FROM_RESOLVED_EDGE")
        let compiledOperations = compiled?.flatMap {
            $0["pattern_operation_proposals"] as? [[String: Any]] ?? []
        } ?? []
        let validatedKinds = Set(compiledOperations.compactMap { row -> String? in
            guard (row["execution"] as? [String: Any])?["status"] as? String ==
                    "MCP_VALIDATED_PROPOSAL" else { return nil }
            require((row["execution"] as? [String: Any])?["canonical_pattern_mutated"]
                    as? Bool == false,
                    "MCP_VALIDATED_OPERATION_MUTATED_CANONICAL_PATTERN")
            return row["kind"] as? String
        })
        require(validatedKinds.isSuperset(of: ["PLEAT", "GATHER", "DART", "FOLD"]),
                "EXISTING_OR_GATHER_OPERATION_DID_NOT_REACH_MCP_VALIDATION")

        guard let singleParsed = GarmentFactoryReactController.parseVisionProposal(
                singleVisibleFixture),
              let rearAlternatives = singleParsed["hypotheses"] as? [[String: Any]],
              rearAlternatives.count == 3 else {
            failures.append("SINGLE_PIXEL_GROUNDED_CANDIDATE_WAS_DISCARDED")
            return failures
        }
        let rearIDs = rearAlternatives.compactMap { $0["candidate_id"] as? String }
        let rearVariantIDs = rearAlternatives.compactMap {
            $0["rear_alternative_id"] as? String
        }
        require(Set(rearIDs).count == 3,
                "DETERMINISTIC_REAR_CANDIDATE_IDS_NOT_UNIQUE")
        require(Set(rearVariantIDs) == Set([
            "center-back-opening", "side-opening-closed-back",
            "closed-back-stretch",
        ]), "DETERMINISTIC_REAR_ALTERNATIVES_INCOMPLETE")

        func visibleFingerprint(_ candidate: [String: Any]) -> String? {
            guard let structure = candidate["structure"] as? [String: Any],
                  let nodes = structure["nodes"] as? [[String: Any]] else { return nil }
            let visible = nodes.map { node -> [String: Any] in
                let attributes = node["attributes"] as? [String: Any] ?? [:]
                return [
                    "node_id": node["node_id"] as? String ?? "",
                    "kind": node["kind"] as? String ?? "",
                    "dimensions": node["dimensions"] as? [String: Any] ?? [:],
                    "visible_basis": attributes["visible_basis"] as? String ?? "",
                ]
            }
            guard JSONSerialization.isValidJSONObject(visible),
                  let data = try? JSONSerialization.data(
                    withJSONObject: visible, options: [.sortedKeys]) else { return nil }
            return String(data: data, encoding: .utf8)
        }
        let visibleFingerprints = rearAlternatives.compactMap(visibleFingerprint)
        require(visibleFingerprints.count == 3 &&
                Set(visibleFingerprints).count == 1,
                "REAR_EXPANSION_CHANGED_PIXEL_GROUNDED_VISIBLE_STRUCTURE")

        let structureFingerprints = rearAlternatives.compactMap { candidate -> String? in
            guard let structure = candidate["structure"] as? [String: Any],
                  JSONSerialization.isValidJSONObject(structure),
                  let data = try? JSONSerialization.data(
                    withJSONObject: structure, options: [.sortedKeys]) else { return nil }
            return String(data: data, encoding: .utf8)
        }
        require(structureFingerprints.count == 3 &&
                Set(structureFingerprints).count == 3,
                "REAR_ALTERNATIVE_STRUCTURES_WOULD_SHARE_ONE_DIGEST")

        for alternative in rearAlternatives {
            let candidateID = alternative["candidate_id"] as? String
            let structure = alternative["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let nodeIDs = Set(nodes.compactMap { $0["node_id"] as? String })
            require(!nodeIDs.contains("boot-left") &&
                    !nodeIDs.contains("boot-right"),
                    "FOOTWEAR_WAS_COMPILED_AS_GARMENT_TUBE")
            let excluded = alternative["uncompiled_visual_parts"]
                as? [[String: Any]] ?? []
            let footwear = excluded.filter {
                $0["state"] as? String == "PROPOSED_EXCLUDED_NON_GARMENT"
            }
            require(footwear.count == 2,
                    "EXPLICIT_FOOTWEAR_WAS_SILENTLY_DROPPED")
            require(footwear.allSatisfy {
                $0["excluded_from_structure_nodes"] as? Bool == true &&
                $0["manufacturing_ready"] as? Bool == false
            }, "FOOTWEAR_EXCLUSION_BOUNDARY_ESCALATED")
            let sleeves = nodes.filter { $0["kind"] as? String == "SLEEVE" }
            let sleeveAttributes = sleeves.first?["attributes"] as? [String: Any]
            require(sleeves.count == 1 &&
                    sleeveAttributes?["side"] as? String == "bilateral" &&
                    sleeveAttributes?["quantity"] as? Int == 2,
                    "LEFT_RIGHT_SLEEVES_DID_NOT_NORMALIZE_TO_ONE_BILATERAL_NODE")
            let records = alternative["normalization_records"]
                as? [[String: Any]] ?? []
            let sleeveRecord = records.first {
                $0["kind"] as? String == "BILATERAL_SLEEVE_NORMALIZATION"
            }
            require(Set(sleeveRecord?["source_part_ids"] as? [String] ?? []) ==
                    Set(["sleeve-left", "sleeve-right"]),
                    "BILATERAL_SLEEVE_SOURCE_PROVENANCE_LOST")
            let gussets = nodes.filter { $0["kind"] as? String == "GUSSET" }
            let gussetAttributes = gussets.first?["attributes"] as? [String: Any]
            require(gussets.count == 1 &&
                    gussetAttributes?["side"] as? String == "center" &&
                    Set(gussetAttributes?["attached_to"] as? [String] ?? []) ==
                        Set(["legging-left", "legging-right"]),
                    "LAYERED_LEGS_DID_NOT_RECEIVE_TYPED_CENTER_GUSSET")
            let belt = nodes.first { $0["node_id"] as? String == "belt-one" }
            let beltAttributes = belt?["attributes"] as? [String: Any]
            let beltContact = records.first {
                $0["kind"] as? String == "BELT_CONTACT_ACCESSORY"
            }
            require(belt?["kind"] as? String == "BAND" &&
                    beltAttributes?["attached_to"] == nil &&
                    beltAttributes?["detail_role"] as? String == "standalone_belt" &&
                    beltAttributes?["garment_unit"] as? String ==
                        "standalone-belt-belt-one" &&
                    beltContact?["contact_target_id"] as? String == "bodice-one" &&
                    beltContact?["dimensions_changed"] as? Bool == false &&
                    beltContact?["join_created"] as? Bool == false,
                    "MISMATCHED_BELT_WAS_NOT_RETAINED_AS_STANDALONE_BAND")
            let legNodes = nodes.filter {
                ["legging-left", "legging-right"].contains(
                    $0["node_id"] as? String ?? "")
            }
            if alternative["rear_alternative_id"] as? String == "closed-back-stretch" {
                require(legNodes.allSatisfy {
                    (($0["attributes"] as? [String: Any])?["attached_to"]
                        as? String) == "bodice-one"
                }, "JUMPSUIT_ALTERNATIVE_LOST_TYPED_LEG_ATTACHMENTS")
            } else {
                require(legNodes.allSatisfy {
                    ($0["attributes"] as? [String: Any])?["attached_to"] == nil
                }, "STANDALONE_UNDERLAYER_RETAINED_THREE_WAIST_CHILDREN")
            }
            require(alternative["representation_complete"] as? Bool == true,
                    "EXCLUDED_FOOTWEAR_INVALIDATED_GARMENT_REPRESENTATION")
            require(alternative["rear_authority"] as? String == "PROPOSED" &&
                    alternative["material_authority"] as? String == "UNKNOWN" &&
                    alternative["requires_human_approval"] as? Bool == true &&
                    alternative["manufacturing_ready"] as? Bool == false,
                    "DETERMINISTIC_REAR_ALTERNATIVE_BYPASSED_AUTHORITY_GATE")
            let operations = alternative["pattern_operation_proposals"]
                as? [[String: Any]] ?? []
            require(operations.allSatisfy {
                $0["candidate_id"] as? String == candidateID
            }, "EXPANDED_PATTERN_OPERATION_RETAINED_SOURCE_CANDIDATE_ID")
        }

        final class RearPipelineCapture: @unchecked Sendable {
            var pipelineReturned = false
            var transformBeforePipeline = false
            var sentCandidates: [[String: Any]] = []
            var transformCount = 0
        }
        let rearCapture = RearPipelineCapture()
        let rearByID = Dictionary(uniqueKeysWithValues: rearAlternatives.compactMap {
            candidate -> (String, [String: Any])? in
            guard let id = candidate["candidate_id"] as? String else { return nil }
            return (id, candidate)
        })
        let rearController = GarmentFactoryReactController(
            door: { _, _ in ["verdict": "UNKNOWN_UNUSED_TEST_DOOR"] },
            toolDoor: { tool, arguments in
                guard let text = arguments["json_text"] as? String,
                      let data = text.data(using: .utf8),
                      let request = try? JSONSerialization.jsonObject(with: data)
                        as? [String: Any]
                else { return ["verdict": "UNKNOWN_TEST_TOOL_INPUT"] }
                if tool == "garment_pattern_transform" {
                    if !rearCapture.pipelineReturned {
                        rearCapture.transformBeforePipeline = true
                    }
                    rearCapture.transformCount += 1
                    return ["verdict": "ANSWER",
                            "after_digest": "rear-transform-digest"]
                }
                guard tool == "garment_parts_ir_pipeline",
                      let partsIR = request["parts_ir"] as? [String: Any],
                      let candidates = partsIR["candidates"] as? [[String: Any]]
                else { return ["verdict": "UNKNOWN_TEST_PIPELINE_INPUT"] }
                rearCapture.sentCandidates = candidates
                let outputs: [[String: Any]] = candidates.compactMap { candidate in
                    guard let id = candidate["candidate_id"] as? String,
                          let original = rearByID[id],
                          let structure = original["structure"] as? [String: Any],
                          let nodes = structure["nodes"] as? [[String: Any]]
                    else { return nil }
                    let pieces: [[String: Any]] = nodes.compactMap { node in
                        guard let nodeID = node["node_id"] as? String else { return nil }
                        return [
                            "piece_id": nodeID, "node_id": nodeID,
                            "outline": [[0.0, 0.0], [20.0, 0.0],
                                        [20.0, 10.0], [0.0, 10.0]],
                            "edges": ["e0": ["length": 20.0],
                                      "e1": ["length": 10.0],
                                      "e2": ["length": 20.0],
                                      "e3": ["length": 10.0]],
                        ]
                    }
                    return [
                        "candidate_id": id,
                        "execution_status": "SUCCEEDED",
                        "structure": structure,
                        "flat_pattern": ["pieces": pieces],
                        "artifact_binding": ["same_structure_digest": true],
                    ]
                }
                rearCapture.pipelineReturned = true
                return ["verdict": "PROPOSED", "candidates": outputs]
            })
        let compiledRearAlternatives = await rearController.runVisionPartsPipeline(
            rearAlternatives)
        require(compiledRearAlternatives?.count == 3,
                "EXPANDED_REAR_ALTERNATIVES_DID_NOT_REACH_PARTS_PIPELINE")
        require(!rearCapture.transformBeforePipeline &&
                rearCapture.transformCount == 3,
                "EXPANDED_GATHER_DID_NOT_WAIT_FOR_EACH_RESOLVED_STRUCTURE")
        let sentRearIDs = Set(rearCapture.sentCandidates.compactMap {
            $0["candidate_id"] as? String
        })
        require(sentRearIDs == Set(rearIDs),
                "PARTS_PIPELINE_LOST_EXPANDED_CANDIDATE_IDENTITIES")
        let sentPartIDs = rearCapture.sentCandidates.flatMap {
            ($0["parts"] as? [[String: Any]] ?? []).compactMap {
                $0["part_id"] as? String
            }
        }
        require(!sentPartIDs.contains("boot-left") &&
                !sentPartIDs.contains("boot-right"),
                "PARTS_PIPELINE_RECEIVED_EXCLUDED_FOOTWEAR")
        let sentRearParts = rearCapture.sentCandidates.flatMap {
            $0["parts"] as? [[String: Any]] ?? []
        }
        require(sentRearParts.contains {
            $0["part_id"] as? String == "belt-one" &&
            $0["kind"] as? String == "BAND" &&
            $0["attached_to"] == nil &&
            $0["detail_role"] as? String == "standalone_belt"
        }, "STANDALONE_BELT_DID_NOT_REACH_PARTS_PIPELINE")
        let sentTrueOrnaments = sentRearParts.filter {
            ["ROSETTE", "TIE"].contains($0["kind"] as? String ?? "")
        }
        require(Set(sentTrueOrnaments.compactMap { $0["kind"] as? String }) ==
                Set(["ROSETTE", "TIE"]),
                "TRUE_ORNAMENT_RECORDS_DID_NOT_REACH_PARTS_PIPELINE")
        guard let actualPipeline = callActualPartsPipeline(
                candidates: rearCapture.sentCandidates),
              let actualCandidates = actualPipeline["candidates"]
                as? [[String: Any]] else {
            failures.append("ACTUAL_STDIO_PARTS_PIPELINE_UNAVAILABLE")
            return failures
        }
        let actualSuccesses = actualCandidates.filter {
            $0["execution_status"] as? String == "SUCCEEDED"
        }
        require(!actualSuccesses.isEmpty,
                "REAL_MODEL_FIXTURE_HAS_NO_SUCCESSFUL_PARTS_PIPELINE_CANDIDATE")
        let actualFailureCodes = actualCandidates.flatMap {
            ($0["failures"] as? [[String: Any]] ?? []).compactMap {
                $0["code"] as? String
            }
        }
        require(!actualFailureCodes.contains("UNKNOWN_PARTS_TOPOLOGY_MULTIPLE_WAIST_CHILDREN"),
                "LAYERED_WAIST_HARD_STOP_REMAINED_AFTER_NORMALIZATION")
        require(!actualFailureCodes.contains("UNKNOWN_BODICE_SLEEVE_BRIDGE_CARDINALITY"),
                "BILATERAL_SLEEVE_HARD_STOP_REMAINED_AFTER_NORMALIZATION")
        require(actualSuccesses.contains {
            let structure = $0["structure"] as? [String: Any]
            let artifacts = structure?["ornament_artifacts"] as? [String: Any]
            let manifest = artifacts?["result_manifest"] as? [[String: Any]] ?? []
            return Set(manifest.compactMap { $0["kind"] as? String }) ==
                Set(["ROSETTE", "TIE"])
        }, "ACTUAL_PIPELINE_DID_NOT_EMIT_BOUND_TRUE_ORNAMENT_ARTIFACTS")

        guard let bandParsed = GarmentFactoryReactController.parseVisionProposal(
                upperSleeveBandFixture),
              let bandCandidates = bandParsed["hypotheses"] as? [[String: Any]],
              bandCandidates.count == 3 else {
            failures.append("UPPER_SLEEVE_BAND_FIXTURE_WAS_REJECTED")
            return failures
        }
        for bandCandidate in bandCandidates {
            guard let bandStructure = bandCandidate["structure"] as? [String: Any],
                  let bandNodes = bandStructure["nodes"] as? [[String: Any]],
                  let upperBand = bandNodes.first(where: {
                      $0["node_id"] as? String == "upper-band"
                  }),
                  let bandDimensions = upperBand["dimensions"] as? [String: Any],
                  let bandAttributes = upperBand["attributes"] as? [String: Any],
                  let dimensionProvenance = bandAttributes["dimension_provenance"]
                    as? [String: [String: Any]],
                  let lengthProvenance = dimensionProvenance["length_cm"]
            else {
                failures.append("UPPER_SLEEVE_BAND_NORMALIZED_NODE_MISSING")
                continue
            }
            require(abs(((bandDimensions["length_cm"] as? NSNumber)?.doubleValue
                         ?? -1) - 34) < 0.000_001,
                    "UPPER_SLEEVE_BAND_RETAINED_GENERIC_WAIST_LENGTH")
            require(lengthProvenance["state"] as? String == "PROPOSED" &&
                    lengthProvenance["dimension_source"] as? String ==
                        "PROPOSED_RELATION_DERIVED" &&
                    lengthProvenance["source_node_id"] as? String ==
                        "sleeve-band-parent" &&
                    lengthProvenance["target_role"] as? String == "upper-sleeve" &&
                    lengthProvenance["not_measured_from_image"] as? Bool == true,
                    "UPPER_SLEEVE_BAND_RELATION_PROVENANCE_ESCALATED")
            let records = bandCandidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(records.contains {
                $0["kind"] as? String == "BOUNDED_BAND_BOUNDARY_NORMALIZATION" &&
                $0["source_part_id"] as? String == "upper-band" &&
                $0["target_node_id"] as? String == "sleeve-band-parent" &&
                $0["resolved_preview_length_cm"] as? Double == 34 &&
                $0["not_measured_from_image"] as? Bool == true
            }, "UPPER_SLEEVE_BAND_NORMALIZATION_AUDIT_RECORD_MISSING")
        }

        guard let ruffleParsed =
                GarmentFactoryReactController.parseVisionProposal(
                    ambiguousShortSleeveRuffleFixture),
              let ruffleCandidates = ruffleParsed["hypotheses"]
                as? [[String: Any]], ruffleCandidates.count == 3 else {
            failures.append("AMBIGUOUS_SHORT_SLEEVE_RUFFLE_WAS_REJECTED")
            return failures
        }
        for ruffleCandidate in ruffleCandidates {
            let structure = ruffleCandidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let ruffle = nodes.first {
                $0["node_id"] as? String == "short-ruffle"
            }
            let dimensions = ruffle?["dimensions"] as? [String: Any]
            let attributes = ruffle?["attributes"] as? [String: Any]
            let provenance = attributes?["gather_boundary_provenance"]
                as? [String: Any]
            let dimensionProvenance = attributes?["dimension_provenance"]
                as? [String: [String: Any]]
            let lengthProvenance = dimensionProvenance?["length_cm"]
            let records = ruffleCandidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(
                abs(((dimensions?["length_cm"] as? NSNumber)?.doubleValue
                    ?? -1) - 35) < 0.000_001 &&
                attributes?["gather_target_role"] as? String == "cuff" &&
                attributes?["gather_boundary_state"] as? String ==
                    "PROPOSED" &&
                provenance?["selection_rule"] as? String ==
                    "PROPOSED_TERMINAL_EDGE_ALTERNATIVE" &&
                provenance?["approval_required"] as? Bool == true &&
                provenance?["observed"] as? Bool == false &&
                provenance?["approved"] as? Bool == false &&
                provenance?["unselected_target_roles"] as? [String] ==
                    ["upper-sleeve"] &&
                lengthProvenance?["dimension_source"] as? String ==
                    "PROPOSED_GATHER_CUT_LENGTH_REDRAFT" &&
                (lengthProvenance?["original_model_or_fallback_value_cm"]
                    as? NSNumber)?.doubleValue == 18,
                "AMBIGUOUS_SHORT_RUFFLE_WAS_NOT_TRUTH_BOUNDED_REDRAFTED")
            require(records.contains {
                $0["kind"] as? String ==
                    "PROPOSED_GATHERED_BAND_BOUNDARY_NORMALIZATION" &&
                $0["source_part_id"] as? String == "short-ruffle" &&
                $0["target_part_id"] as? String == "ruffle-sleeve" &&
                $0["target_role"] as? String == "cuff" &&
                $0["approval_required"] as? Bool == true &&
                $0["dimensions_changed"] as? Bool == true
            }, "AMBIGUOUS_SHORT_RUFFLE_NORMALIZATION_RECORD_MISSING")
        }
        if let rufflePipeline = callActualPartsPipeline(
                candidates: ruffleCandidates),
           let outputs = rufflePipeline["candidates"] as? [[String: Any]] {
            let failures = outputs.flatMap {
                ($0["failures"] as? [[String: Any]] ?? []).compactMap {
                    $0["code"] as? String
                }
            }
            require(!failures.contains(
                        "UNKNOWN_PARTS_TOPOLOGY_GATHER_TARGET_AMBIGUOUS") &&
                    !failures.contains(
                        "UNKNOWN_PARTS_TOPOLOGY_GATHER_NOT_LONGER"),
                    "AMBIGUOUS_SHORT_RUFFLE_STILL_STOPS_TYPED_PIPELINE")
        } else {
            failures.append("AMBIGUOUS_SHORT_RUFFLE_PIPELINE_UNAVAILABLE")
        }

        guard let waistbandParsed =
                GarmentFactoryReactController.parseVisionProposal(
                    mismatchedStructuralWaistbandFixture),
              let waistbandCandidates = waistbandParsed["hypotheses"]
                as? [[String: Any]], waistbandCandidates.count == 3 else {
            failures.append("MISMATCHED_STRUCTURAL_WAISTBAND_WAS_REJECTED")
            return failures
        }
        for candidate in waistbandCandidates {
            let structure = candidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let band = nodes.first {
                $0["node_id"] as? String == "p11_trouser_waistband"
            }
            let dimensions = band?["dimensions"] as? [String: Any]
            let attributes = band?["attributes"] as? [String: Any]
            let provenance = attributes?["dimension_provenance"]
                as? [String: [String: Any]]
            let length = provenance?["length_cm"]
            let records = candidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(
                (dimensions?["length_cm"] as? NSNumber)?.doubleValue == 74 &&
                length?["dimension_source"] as? String ==
                    "PROPOSED_STRUCTURAL_BAND_SEAM_REDRAFT" &&
                (length?["original_model_value_cm"] as? NSNumber)?
                    .doubleValue == 92 &&
                length?["approval_required"] as? Bool == true &&
                length?["not_measured_from_image"] as? Bool == true &&
                attributes?["model_kind"] as? String == "WAISTBAND" &&
                records.contains {
                    $0["kind"] as? String ==
                        "PROPOSED_STRUCTURAL_BAND_SEAM_REDRAFT" &&
                    $0["source_part_id"] as? String ==
                        "p11_trouser_waistband" &&
                    ($0["previous_preview_length_cm"] as? NSNumber)?
                        .doubleValue == 92 &&
                    ($0["resolved_preview_length_cm"] as? NSNumber)?
                        .doubleValue == 74 &&
                    $0["approval_required"] as? Bool == true
                },
                "STRUCTURAL_WAISTBAND_WAS_NOT_TRUTH_BOUNDED_REDRAFTED")
        }
        if let waistbandPipeline = callActualPartsPipeline(
                candidates: waistbandCandidates),
           let outputs = waistbandPipeline["candidates"] as? [[String: Any]] {
            let codes = outputs.flatMap {
                ($0["failures"] as? [[String: Any]] ?? []).compactMap {
                    $0["code"] as? String
                }
            }
            require(!codes.contains(
                        "UNKNOWN_PARTS_TOPOLOGY_JOIN_LENGTH_MISMATCH"),
                    "STRUCTURAL_WAISTBAND_STILL_STOPS_TYPED_PIPELINE")
        } else {
            failures.append("STRUCTURAL_WAISTBAND_PIPELINE_UNAVAILABLE")
        }

        guard let trouserParsed = GarmentFactoryReactController.parseVisionProposal(
                standaloneTrouserFixture),
              let trouserCandidates = trouserParsed["hypotheses"]
                as? [[String: Any]], trouserCandidates.count == 3 else {
            failures.append("STANDALONE_TROUSER_FIXTURE_WAS_REJECTED")
            return failures
        }
        for trouserCandidate in trouserCandidates {
            let structure = trouserCandidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let gussets = nodes.filter { $0["kind"] as? String == "GUSSET" }
            let attributes = gussets.first?["attributes"] as? [String: Any]
            require(gussets.count == 1 &&
                    attributes?["garment_unit"] as? String == "legging-unit" &&
                    Set(attributes?["attached_to"] as? [String] ?? []) == Set([
                        "legging-left-only", "legging-right-only",
                    ]) &&
                    attributes?["attachment_state"] as? String ==
                        "PROPOSED_NORMALIZATION" &&
                    attributes?["visible_basis"] as? String != nil,
                    "STANDALONE_TROUSER_GUSSET_WAS_NOT_EXACTLY_COMPLETED")
            let records = trouserCandidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(records.contains {
                $0["kind"] as? String ==
                    "STANDALONE_TROUSER_GUSSET_COMPLETION" &&
                Set($0["source_leg_ids"] as? [String] ?? []) == Set([
                    "legging-left-only", "legging-right-only",
                ]) &&
                $0["not_observed_from_front"] as? Bool == true
            }, "STANDALONE_TROUSER_GUSSET_PROVENANCE_MISSING")
        }

        guard let directTrouserParsed =
                GarmentFactoryReactController.parseVisionProposal(
                    directMultiCandidateTrouserFixture),
              let directTrouserCandidates = directTrouserParsed["hypotheses"]
                as? [[String: Any]], directTrouserCandidates.count == 2 else {
            failures.append("DIRECT_MULTI_CANDIDATE_TROUSERS_WERE_REJECTED")
            return failures
        }
        for directCandidate in directTrouserCandidates {
            let structure = directCandidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let legs = nodes.filter { $0["kind"] as? String == "TUBE" }
            let gussets = nodes.filter { $0["kind"] as? String == "GUSSET" }
            let legIDs = Set(legs.compactMap { $0["node_id"] as? String })
            let attributes = gussets.first?["attributes"] as? [String: Any]
            let records = directCandidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(legs.count == 2 && gussets.count == 1 &&
                    Set(attributes?["attached_to"] as? [String] ?? []) == legIDs &&
                    attributes?["visible_basis"] as? String != nil &&
                    records.contains {
                        $0["kind"] as? String ==
                            "STANDALONE_TROUSER_GUSSET_COMPLETION" &&
                        $0["not_observed_from_front"] as? Bool == true
                    },
                    "DIRECT_MULTI_CANDIDATE_TROUSER_GUSSET_WAS_NOT_COMPLETED")
        }

        guard let layeredTrouserParsed =
                GarmentFactoryReactController.parseVisionProposal(
                    layeredTrouserUnitsFixture),
              let layeredTrouserCandidates = layeredTrouserParsed["hypotheses"]
                as? [[String: Any]], layeredTrouserCandidates.count == 3 else {
            failures.append("LAYERED_TROUSER_UNITS_FIXTURE_WAS_REJECTED")
            return failures
        }
        let expectedTrouserGroups: [String: (layer: Int, legs: Set<String>,
                                               gusset: String)] = [
            "outer-trouser-unit": (
                1, Set(["outer-trouser-left", "outer-trouser-right"]),
                "outer-trouser-gusset"),
            "legging-underlayer-unit": (
                0, Set(["legging-underlayer-left", "legging-underlayer-right"]),
                "legging-underlayer-gusset"),
        ]
        func preservesLayeredTrouserGroups(_ candidate: [String: Any]) -> Bool {
            guard let structure = candidate["structure"] as? [String: Any],
                  let nodes = structure["nodes"] as? [[String: Any]],
                  nodes.filter({ $0["kind"] as? String == "TUBE" }).count == 4,
                  nodes.filter({ $0["kind"] as? String == "GUSSET" }).count == 2
            else { return false }
            for (unit, expected) in expectedTrouserGroups {
                let group = nodes.filter {
                    ($0["attributes"] as? [String: Any])?["garment_unit"]
                        as? String == unit
                }
                let legs = group.filter { $0["kind"] as? String == "TUBE" }
                let gussets = group.filter { $0["kind"] as? String == "GUSSET" }
                guard legs.count == 2, gussets.count == 1,
                      Set(legs.compactMap { $0["node_id"] as? String }) ==
                        expected.legs,
                      legs.allSatisfy({ ($0["layer"] as? Int) == expected.layer }),
                      gussets.first?["node_id"] as? String == expected.gusset,
                      gussets.first?["layer"] as? Int == expected.layer,
                      let attributes = gussets.first?["attributes"]
                        as? [String: Any],
                      Set(attributes["attached_to"] as? [String] ?? []) ==
                        expected.legs,
                      attributes["attachment_state"] as? String == "PROPOSED"
                else { return false }
            }
            return true
        }
        for candidate in layeredTrouserCandidates {
            require(preservesLayeredTrouserGroups(candidate),
                    "PRODUCTION_PARSER_MERGED_LAYERED_TROUSERS_INTO_FOUR_LEG_SET")
            require(candidate["rear_authority"] as? String == "PROPOSED" &&
                    candidate["requires_human_approval"] as? Bool == true &&
                    candidate["manufacturing_ready"] as? Bool == false &&
                    candidate["manufacturing_certified"] as? Bool == false,
                    "LAYERED_TROUSER_PARSER_AUTHORITY_ESCALATED")
        }

        final class LayeredTrouserCapture: @unchecked Sendable {
            var request: [String: Any]?
            var sentCandidates: [[String: Any]] = []
        }
        let layeredTrouserCapture = LayeredTrouserCapture()
        let layeredTrouserByID = Dictionary(uniqueKeysWithValues:
            layeredTrouserCandidates.compactMap { candidate ->
                (String, [String: Any])? in
                guard let id = candidate["candidate_id"] as? String else {
                    return nil
                }
                return (id, candidate)
            })
        let layeredTrouserController = GarmentFactoryReactController(
            door: { _, _ in ["verdict": "UNKNOWN_UNUSED_TEST_DOOR"] },
            toolDoor: { tool, arguments in
                guard tool == "garment_parts_ir_pipeline",
                      let text = arguments["json_text"] as? String,
                      let data = text.data(using: .utf8),
                      let request = try? JSONSerialization.jsonObject(with: data)
                        as? [String: Any],
                      let partsIR = request["parts_ir"] as? [String: Any],
                      let candidates = partsIR["candidates"] as? [[String: Any]]
                else { return ["verdict": "UNKNOWN_TEST_PIPELINE_INPUT"] }
                layeredTrouserCapture.request = request
                layeredTrouserCapture.sentCandidates = candidates
                let outputs: [[String: Any]] = candidates.compactMap { candidate in
                    guard let id = candidate["candidate_id"] as? String,
                          let original = layeredTrouserByID[id],
                          let structure = original["structure"] as? [String: Any]
                    else { return nil }
                    return [
                        "candidate_id": id,
                        "execution_status": "SUCCEEDED",
                        "structure": structure,
                        "artifact_binding": ["same_structure_digest": true],
                    ]
                }
                return ["verdict": "PROPOSED", "candidates": outputs]
            })
        let compiledLayeredTrousers = await layeredTrouserController
            .runVisionPartsPipeline(layeredTrouserCandidates)
        require(compiledLayeredTrousers?.count == 3,
                "RUN_PIPELINE_REJECTED_TWO_PHYSICAL_TROUSER_GROUPS")
        let layeredTrouserPartsIR = layeredTrouserCapture.request?["parts_ir"]
            as? [String: Any]
        require(layeredTrouserPartsIR?["state"] as? String == "PROPOSED" &&
                layeredTrouserCapture.sentCandidates.count == 3 &&
                layeredTrouserCapture.sentCandidates.allSatisfy {
                    $0["state"] as? String == "PROPOSED"
                }, "LAYERED_TROUSER_MCP_REQUEST_AUTHORITY_ESCALATED")
        for sentCandidate in layeredTrouserCapture.sentCandidates {
            let parts = sentCandidate["parts"] as? [[String: Any]] ?? []
            require(parts.filter { $0["kind"] as? String == "TUBE" }.count == 4 &&
                    parts.filter { $0["kind"] as? String == "GUSSET" }.count == 2,
                    "RUN_PIPELINE_MERGED_TWO_TROUSER_GROUPS_BEFORE_MCP")
            for (unit, expected) in expectedTrouserGroups {
                let group = parts.filter { $0["garment_unit"] as? String == unit }
                let legs = group.filter { $0["kind"] as? String == "TUBE" }
                let gussets = group.filter { $0["kind"] as? String == "GUSSET" }
                require(legs.count == 2 && gussets.count == 1 &&
                        Set(legs.compactMap { $0["part_id"] as? String }) ==
                            expected.legs &&
                        Set(gussets.first?["attached_to"] as? [String] ?? []) ==
                            expected.legs &&
                        group.allSatisfy { ($0["layer"] as? Int) == expected.layer } &&
                        group.allSatisfy {
                            ($0["visible_basis"] as? [String: Any])?["state"]
                                as? String == "PROPOSED"
                        }, "MCP_REQUEST_CROSSED_LAYERED_TROUSER_GROUP_BOUNDARY")
            }
        }
        for candidate in compiledLayeredTrousers ?? [] {
            require(preservesLayeredTrouserGroups(candidate),
                    "RUN_PIPELINE_MERGED_LAYERED_TROUSERS_IN_RETURNED_STRUCTURE")
            require(candidate["rear_authority"] as? String == "PROPOSED" &&
                    candidate["topology_state"] as? String == "PROPOSED" &&
                    candidate["pipeline_state"] as? String == "PROPOSED" &&
                    candidate["requires_human_approval"] as? Bool == true,
                    "RUN_PIPELINE_ESCALATED_LAYERED_TROUSER_AUTHORITY")
        }

        guard let carrierParsed = GarmentFactoryReactController.parseVisionProposal(
                sleeveCarrierFixture),
              let carrierCandidates = carrierParsed["hypotheses"]
                as? [[String: Any]], carrierCandidates.count == 3 else {
            failures.append("SLEEVE_CARRIER_FIXTURE_WAS_REJECTED")
            return failures
        }
        for carrierCandidate in carrierCandidates {
            let structure = carrierCandidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let sleeve = nodes.first {
                $0["node_id"] as? String == "carrier-sleeve"
            }
            let attributes = sleeve?["attributes"] as? [String: Any]
            let normalization = attributes?["sleeve_anchor_normalization"]
                as? [String: Any]
            require(attributes?["attached_to"] as? String == "carrier-body" &&
                    attributes?["model_attached_to"] as? String == "visible-yoke" &&
                    attributes?["attachment_state"] as? String ==
                        "PROPOSED_ARMHOLE_CARRIER_NORMALIZATION" &&
                    normalization?["model_target_kind"] as? String == "YOKE" &&
                    normalization?["not_observed_from_front"] as? Bool == true,
                    "SLEEVE_VISIBLE_CARRIER_WAS_NOT_READDRESSED_WITH_PROVENANCE")
            let records = carrierCandidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(records.contains {
                $0["kind"] as? String ==
                    "SLEEVE_ARMHOLE_CARRIER_NORMALIZATION" &&
                $0["source_part_id"] as? String == "carrier-sleeve" &&
                $0["model_target_id"] as? String == "visible-yoke" &&
                $0["resolved_body_shell_id"] as? String == "carrier-body"
            }, "SLEEVE_CARRIER_NORMALIZATION_RECORD_MISSING")
        }

        guard let aliasParsed = GarmentFactoryReactController.parseVisionProposal(
                attachmentAliasFixture),
              let aliasCandidates = aliasParsed["hypotheses"] as? [[String: Any]],
              aliasCandidates.count == 3 else {
            failures.append("ATTACHMENT_UNIT_ALIAS_FIXTURE_WAS_REJECTED")
            return failures
        }
        for aliasCandidate in aliasCandidates {
            let structure = aliasCandidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let collar = nodes.first {
                $0["node_id"] as? String == "alias-collar"
            }
            let attributes = collar?["attributes"] as? [String: Any]
            let normalization = attributes?["attachment_address_normalization"]
                as? [String: Any]
            require(attributes?["attached_to"] as? String == "alias-body" &&
                    attributes?["model_attached_to"] as? String ==
                        "bodice-unit-01" &&
                    normalization?["resolution_rule"] as? String ==
                        "unique BODY_SHELL garment_unit alias" &&
                    normalization?["not_observed_from_front"] as? Bool == true,
                    "ATTACHMENT_UNIT_ALIAS_WAS_NOT_UNIQUELY_RESOLVED")
            let records = aliasCandidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(records.contains {
                $0["kind"] as? String ==
                    "ATTACHMENT_UNIT_ALIAS_NORMALIZATION" &&
                $0["source_part_id"] as? String == "alias-collar" &&
                $0["resolved_node_id"] as? String == "alias-body"
            }, "ATTACHMENT_UNIT_ALIAS_AUDIT_RECORD_MISSING")
        }

        guard let semanticAliasParsed =
                GarmentFactoryReactController.parseVisionProposal(
                    uniqueSkirtSemanticAliasFixture),
              let semanticAliasCandidates = semanticAliasParsed["hypotheses"]
                as? [[String: Any]], semanticAliasCandidates.count == 3 else {
            failures.append("UNIQUE_SKIRT_SEMANTIC_ALIAS_FIXTURE_WAS_REJECTED")
            return failures
        }
        for candidate in semanticAliasCandidates {
            let structure = candidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let overlay = nodes.first {
                $0["node_id"] as? String == "front-skirt-overlay"
            }
            let attributes = overlay?["attributes"] as? [String: Any]
            let normalization = attributes?["attachment_address_normalization"]
                as? [String: Any]
            let resolutionRule = normalization?["resolution_rule"] as? String
                ?? ""
            require(attributes?["attached_to"] as? String ==
                        "visible-skirt-carrier" &&
                    attributes?["model_attached_to"] as? String ==
                        "skirt-unit-01" &&
                    attributes?["attachment_state"] as? String == "PROPOSED" &&
                    normalization?["state"] as? String ==
                        "PROPOSED_NORMALIZATION" &&
                    normalization?["model_target_token"] as? String ==
                        "skirt-unit-01" &&
                    normalization?["resolved_node_id"] as? String ==
                        "visible-skirt-carrier" &&
                    resolutionRule.lowercased().contains("semantic") &&
                    resolutionRule.lowercased().contains("unique") &&
                    normalization?["not_observed_from_front"] as? Bool == true &&
                    normalization?["observed"] as? Bool != true,
                    "UNIQUE_SKIRT_SEMANTIC_ALIAS_WAS_NOT_PROPOSED_AND_READDRESSED")
            let records = candidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(records.contains { record in
                let kind = (record["kind"] as? String ?? "").uppercased()
                return kind.contains("SEMANTIC") &&
                    kind.contains("NORMALIZATION") &&
                    record["state"] as? String == "PROPOSED_NORMALIZATION" &&
                    record["source_part_id"] as? String ==
                        "front-skirt-overlay" &&
                    record["model_target_token"] as? String ==
                        "skirt-unit-01" &&
                    record["resolved_node_id"] as? String ==
                        "visible-skirt-carrier" &&
                    record["not_observed_from_front"] as? Bool == true
            }, "UNIQUE_SKIRT_SEMANTIC_ALIAS_AUDIT_RECORD_MISSING")
            require(candidate["rear_authority"] as? String == "PROPOSED" &&
                    candidate["manufacturing_ready"] as? Bool == false &&
                    candidate["manufacturing_certified"] as? Bool == false,
                    "SKIRT_SEMANTIC_ALIAS_PROMOTED_IMAGE_OR_MANUFACTURING_AUTHORITY")
        }

        final class SemanticAliasPipelineCapture: @unchecked Sendable {
            var payload: [String: Any]?
            var submittedCandidates: [[String: Any]] = []
        }
        func actualPipelineController(
            capture: SemanticAliasPipelineCapture
        ) -> GarmentFactoryReactController {
            GarmentFactoryReactController(
                door: { _, _ in ["verdict": "UNKNOWN_UNUSED_TEST_DOOR"] },
                toolDoor: { tool, arguments in
                    guard tool == "garment_parts_ir_pipeline",
                          let text = arguments["json_text"] as? String,
                          let data = text.data(using: .utf8),
                          let request = try? JSONSerialization.jsonObject(
                            with: data) as? [String: Any],
                          let partsIR = request["parts_ir"] as? [String: Any],
                          let candidates = partsIR["candidates"]
                            as? [[String: Any]],
                          let payload = callActualPartsPipeline(
                            candidates: candidates) else {
                        return ["verdict": "UNKNOWN_ACTUAL_ALIAS_PIPELINE"]
                    }
                    capture.submittedCandidates = candidates
                    capture.payload = payload
                    return payload
                })
        }

        let uniqueAliasCapture = SemanticAliasPipelineCapture()
        _ = await actualPipelineController(
            capture: uniqueAliasCapture
        ).runVisionPartsPipeline(semanticAliasCandidates)
        let uniqueAliasRows = uniqueAliasCapture.payload?["candidates"]
            as? [[String: Any]] ?? []
        let uniqueAliasFailureSummary = uniqueAliasRows.map { row in
            let verdict = row["verdict"] as? String ?? "NO_VERDICT"
            let codes = (row["failures"] as? [[String: Any]] ?? []).compactMap {
                ($0["code"] as? String) ?? ($0["verdict"] as? String)
            }.joined(separator: ",")
            return "\(verdict)[\(codes)]"
        }.joined(separator: ";")
        require(uniqueAliasCapture.submittedCandidates.count == 3 &&
                uniqueAliasCapture.submittedCandidates.allSatisfy { candidate in
                    let parts = candidate["parts"] as? [[String: Any]] ?? []
                    let overlay = parts.first {
                        $0["part_id"] as? String == "front-skirt-overlay"
                    }
                    return overlay?["attached_to"] as? String ==
                        "visible-skirt-carrier"
                } &&
                uniqueAliasRows.count == 3 &&
                uniqueAliasRows.allSatisfy { row in
                    let rowVerdict = row["verdict"] as? String ?? ""
                    let failureCodes = (row["failures"] as? [[String: Any]] ?? [])
                        .compactMap {
                            ($0["code"] as? String) ?? ($0["verdict"] as? String)
                        }
                    return !rowVerdict.contains("TARGET_MISSING") &&
                        !failureCodes.contains { $0.contains("TARGET_MISSING") }
                },
                "SKIRT_SEMANTIC_ALIAS_STILL_FAILED_ACTUAL_PYTHON_TARGET_LOOKUP_\(uniqueAliasFailureSummary)")

        guard let ambiguousAliasParsed =
                GarmentFactoryReactController.parseVisionProposal(
                    ambiguousSkirtSemanticAliasFixture),
              let ambiguousAliasCandidates = ambiguousAliasParsed["hypotheses"]
                as? [[String: Any]], ambiguousAliasCandidates.count == 3 else {
            failures.append("AMBIGUOUS_SKIRT_SEMANTIC_ALIAS_FIXTURE_WAS_REJECTED")
            return failures
        }
        for candidate in ambiguousAliasCandidates {
            let structure = candidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let overlay = nodes.first {
                $0["node_id"] as? String == "ambiguous-front-overlay"
            }
            let attributes = overlay?["attributes"] as? [String: Any]
            let normalized = attributes?["attachment_address_normalization"]
                as? [String: Any]
            let records = candidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(attributes?["attached_to"] as? String == "skirt-unit-01" &&
                    normalized == nil &&
                    attributes?["attached_to"] as? String !=
                        "inner-skirt-carrier" &&
                    attributes?["attached_to"] as? String !=
                        "outer-skirt-carrier" &&
                    !records.contains { record in
                        record["source_part_id"] as? String ==
                            "ambiguous-front-overlay" &&
                        (record["resolved_node_id"] as? String ==
                            "inner-skirt-carrier" ||
                         record["resolved_node_id"] as? String ==
                            "outer-skirt-carrier")
                    } &&
                    candidate["manufacturing_ready"] as? Bool == false &&
                    candidate["manufacturing_certified"] as? Bool == false,
                    "AMBIGUOUS_SKIRT_SEMANTIC_ALIAS_DID_NOT_REMAIN_UNRESOLVED")
        }

        let ambiguousAliasCapture = SemanticAliasPipelineCapture()
        let ambiguousAliasCompiled = await actualPipelineController(
            capture: ambiguousAliasCapture
        ).runVisionPartsPipeline(ambiguousAliasCandidates)
        let ambiguousAliasRows = ambiguousAliasCapture.payload?["candidates"]
            as? [[String: Any]] ?? []
        require(ambiguousAliasCompiled == nil &&
                ambiguousAliasRows.count == 3 &&
                ambiguousAliasRows.allSatisfy {
                    $0["execution_status"] as? String == "REFUSED"
                } &&
                ambiguousAliasRows.allSatisfy { row in
                    let rowVerdict = row["verdict"] as? String ?? ""
                    let failureCodes = (row["failures"] as? [[String: Any]] ?? [])
                        .compactMap {
                            ($0["code"] as? String) ?? ($0["verdict"] as? String)
                        }
                    return rowVerdict.contains("TARGET_MISSING") ||
                        failureCodes.contains { $0.contains("TARGET_MISSING") }
                },
                "AMBIGUOUS_SKIRT_SEMANTIC_ALIAS_DID_NOT_FAIL_CLOSED")

        guard let waistParsed = GarmentFactoryReactController.parseVisionProposal(
                waistCarrierFixture),
              let waistCandidates = waistParsed["hypotheses"] as? [[String: Any]],
              waistCandidates.count == 3 else {
            failures.append("WAIST_CARRIER_FIXTURE_WAS_REJECTED")
            return failures
        }
        for waistCandidate in waistCandidates {
            let structure = waistCandidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let skirt = nodes.first {
                $0["node_id"] as? String == "skirt-through-waistband"
            }
            let attributes = skirt?["attributes"] as? [String: Any]
            let normalization = attributes?["waist_anchor_normalization"]
                as? [String: Any]
            require(attributes?["attached_to"] as? String ==
                        "carrier-waist-body" &&
                    attributes?["model_attached_to"] as? String ==
                        "visible-waistband" &&
                    attributes?["attachment_state"] as? String ==
                        "PROPOSED_WAIST_CARRIER_NORMALIZATION" &&
                    normalization?["not_observed_from_front"] as? Bool == true,
                    "WAIST_VISIBLE_CARRIER_WAS_NOT_READDRESSED_WITH_PROVENANCE")
            let records = waistCandidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(records.contains {
                $0["kind"] as? String == "WAIST_CARRIER_NORMALIZATION" &&
                $0["source_part_id"] as? String ==
                    "skirt-through-waistband" &&
                $0["model_target_id"] as? String == "visible-waistband" &&
                $0["resolved_body_shell_id"] as? String ==
                    "carrier-waist-body"
            }, "WAIST_CARRIER_NORMALIZATION_RECORD_MISSING")
        }

        guard let gatheredParsed = GarmentFactoryReactController.parseVisionProposal(
                gatheredWaistFixture),
              let gatheredCandidates = gatheredParsed["hypotheses"]
                as? [[String: Any]], gatheredCandidates.count == 3 else {
            failures.append("GATHERED_WAIST_FIXTURE_WAS_REJECTED")
            return failures
        }
        for gatheredCandidate in gatheredCandidates {
            let structure = gatheredCandidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let skirt = nodes.first {
                $0["node_id"] as? String == "gather-skirt"
            }
            let attributes = skirt?["attributes"] as? [String: Any]
            let provenance = attributes?["waist_join_provenance"]
                as? [String: Any]
            let dimensions = skirt?["dimensions"] as? [String: Any]
            require(attributes?["waist_join_mode"] as? String == "GATHER" &&
                    attributes?["waist_join_state"] as? String == "PROPOSED" &&
                    (dimensions?["top_circumference_cm"] as? NSNumber)?
                        .doubleValue == 90 &&
                    provenance?["source_length_cm"] as? Double == 90 &&
                    provenance?["target_length_cm"] as? Double == 72 &&
                    provenance?["dimensions_changed"] as? Bool == false,
                    "EXPLICIT_SKIRT_FULLNESS_WAS_RESIZED_OR_NOT_TYPED_AS_GATHER")
            let records = gatheredCandidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(records.contains {
                $0["kind"] as? String == "PROPOSED_WAIST_GATHER_RELATION" &&
                $0["source_part_id"] as? String == "gather-skirt" &&
                $0["dimensions_changed"] as? Bool == false
            }, "PROPOSED_WAIST_GATHER_RECORD_MISSING")
        }
        let gatheredPartsCandidates: [[String: Any]] = gatheredCandidates.compactMap {
            candidate in
            guard let candidateID = candidate["candidate_id"] as? String,
                  let structure = candidate["structure"] as? [String: Any],
                  let nodes = structure["nodes"] as? [[String: Any]] else {
                return nil
            }
            let parts: [[String: Any]] = nodes.compactMap { node in
                guard let partID = node["node_id"] as? String,
                      let kind = node["kind"] as? String,
                      let dimensions = node["dimensions"] as? [String: Any],
                      let attributes = node["attributes"] as? [String: Any]
                else { return nil }
                var part: [String: Any] = [
                    "part_id": partID, "kind": kind,
                    "layer": node["layer"] as? Int ?? 0,
                    "placement": attributes["placement"] as? String ?? "waist",
                    "visible_basis": [
                        "state": "PROPOSED",
                        "basis": attributes["visible_basis"] as? String
                            ?? "vision proposal",
                        "breaks_when": "review rejects this proposal",
                    ],
                    "dimensions": dimensions,
                ]
                for field in [
                    "garment_unit", "attached_to", "waist_join_mode",
                    "waist_join_state", "waist_join_provenance",
                ] where attributes[field] != nil {
                    part[field] = attributes[field]
                }
                return part
            }
            guard parts.count == nodes.count else { return nil }
            return ["candidate_id": candidateID, "state": "PROPOSED",
                    "parts": parts]
        }
        if let gatheredPipeline = callActualPartsPipeline(
                candidates: gatheredPartsCandidates),
           let rows = gatheredPipeline["candidates"] as? [[String: Any]] {
            require(rows.count == 3 && rows.allSatisfy {
                $0["execution_status"] as? String == "SUCCEEDED"
            }, "GATHERED_WAIST_DID_NOT_REACH_CANDIDATE_SPECIFIC_ARTIFACTS")
            for row in rows {
                let structure = row["structure"] as? [String: Any]
                let operations = structure?["operations"] as? [[String: Any]] ?? []
                require(operations.contains {
                    $0["kind"] as? String == "GATHER" &&
                    $0["operation_id"] as? String ==
                        "gather-waist-gather-skirt-to-gather-body"
                }, "GATHERED_WAIST_TYPED_OPERATION_MISSING")
            }
        } else {
            failures.append("GATHERED_WAIST_ACTUAL_PIPELINE_UNAVAILABLE")
        }

        guard let straightSkirtParsed =
                GarmentFactoryReactController.parseVisionProposal(
                    compactStraightSkirtTubeFixture),
              let straightSkirtCandidates = straightSkirtParsed["hypotheses"]
                as? [[String: Any]], straightSkirtCandidates.count == 3 else {
            failures.append("COMPACT_STRAIGHT_SKIRT_TUBE_FIXTURE_WAS_REJECTED")
            return failures
        }
        func straightSkirtTubeIsPreserved(_ candidate: [String: Any]) -> Bool {
            guard let structure = candidate["structure"] as? [String: Any],
                  let nodes = structure["nodes"] as? [[String: Any]],
                  nodes.filter({ $0["kind"] as? String == "TUBE" }).count == 1,
                  nodes.filter({ $0["kind"] as? String == "GUSSET" }).isEmpty,
                  let body = nodes.first(where: {
                      $0["node_id"] as? String == "straight-skirt-body"
                  }),
                  let skirt = nodes.first(where: {
                      $0["node_id"] as? String == "straight-skirt-tube"
                  }),
                  let bodyDimensions = body["dimensions"] as? [String: Any],
                  let skirtDimensions = skirt["dimensions"] as? [String: Any],
                  let attributes = skirt["attributes"] as? [String: Any],
                  let provenance = attributes["waist_join_provenance"]
                    as? [String: Any]
            else { return false }
            return (bodyDimensions["height_cm"] as? NSNumber)?.doubleValue == 43 &&
                (bodyDimensions["circumference_cm"] as? NSNumber)?.doubleValue == 72 &&
                (skirtDimensions["length_cm"] as? NSNumber)?.doubleValue == 68 &&
                (skirtDimensions["circumference_cm"] as? NSNumber)?.doubleValue == 96 &&
                attributes["attached_to"] as? String == "straight-skirt-body" &&
                attributes["side"] == nil &&
                attributes["shape"] as? String == "straight_skirt" &&
                attributes["detail_role"] as? String == "straight skirt" &&
                attributes["waist_join_mode"] as? String == "GATHER" &&
                attributes["waist_join_state"] as? String == "PROPOSED" &&
                provenance["state"] as? String == "PROPOSED" &&
                provenance["source_length_cm"] as? Double == 96 &&
                provenance["target_length_cm"] as? Double == 72 &&
                provenance["dimensions_changed"] as? Bool == false
        }
        for candidate in straightSkirtCandidates {
            require(straightSkirtTubeIsPreserved(candidate),
                    "STRAIGHT_SKIRT_TUBE_WAS_RESIZED_OR_MISTAKEN_FOR_TROUSERS")
            let records = candidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(records.contains {
                $0["kind"] as? String == "PROPOSED_WAIST_GATHER_RELATION" &&
                $0["source_part_id"] as? String == "straight-skirt-tube" &&
                $0["target_part_id"] as? String == "straight-skirt-body" &&
                $0["source_length_cm"] as? Double == 96 &&
                $0["target_length_cm"] as? Double == 72 &&
                $0["dimensions_changed"] as? Bool == false
            }, "STRAIGHT_SKIRT_TUBE_GATHER_AUDIT_RECORD_MISSING")
        }

        final class StraightSkirtTubeCapture: @unchecked Sendable {
            var sentCandidates: [[String: Any]] = []
        }
        let straightSkirtCapture = StraightSkirtTubeCapture()
        let straightSkirtByID = Dictionary(uniqueKeysWithValues:
            straightSkirtCandidates.compactMap { candidate ->
                (String, [String: Any])? in
                guard let id = candidate["candidate_id"] as? String else {
                    return nil
                }
                return (id, candidate)
            })
        let straightSkirtController = GarmentFactoryReactController(
            door: { _, _ in ["verdict": "UNKNOWN_UNUSED_TEST_DOOR"] },
            toolDoor: { tool, arguments in
                guard tool == "garment_parts_ir_pipeline",
                      let text = arguments["json_text"] as? String,
                      let data = text.data(using: .utf8),
                      let request = try? JSONSerialization.jsonObject(with: data)
                        as? [String: Any],
                      let partsIR = request["parts_ir"] as? [String: Any],
                      let candidates = partsIR["candidates"] as? [[String: Any]]
                else { return ["verdict": "UNKNOWN_TEST_PIPELINE_INPUT"] }
                straightSkirtCapture.sentCandidates = candidates
                let outputs: [[String: Any]] = candidates.compactMap { candidate in
                    guard let id = candidate["candidate_id"] as? String,
                          let original = straightSkirtByID[id],
                          let structure = original["structure"] as? [String: Any]
                    else { return nil }
                    return [
                        "candidate_id": id,
                        "execution_status": "SUCCEEDED",
                        "structure": structure,
                        "artifact_binding": ["same_structure_digest": true],
                    ]
                }
                return ["verdict": "PROPOSED", "candidates": outputs]
            })
        let compiledStraightSkirts = await straightSkirtController
            .runVisionPartsPipeline(straightSkirtCandidates)
        require(compiledStraightSkirts?.count == 3 &&
                straightSkirtCapture.sentCandidates.count == 3,
                "STRAIGHT_SKIRT_TUBE_DID_NOT_REACH_RUN_VISION_PARTS_PIPELINE")
        for sentCandidate in straightSkirtCapture.sentCandidates {
            let parts = sentCandidate["parts"] as? [[String: Any]] ?? []
            let body = parts.first {
                $0["part_id"] as? String == "straight-skirt-body"
            }
            let skirt = parts.first {
                $0["part_id"] as? String == "straight-skirt-tube"
            }
            let bodyDimensions = body?["dimensions"] as? [String: Any]
            let skirtDimensions = skirt?["dimensions"] as? [String: Any]
            let provenance = skirt?["waist_join_provenance"] as? [String: Any]
            require(parts.filter { $0["kind"] as? String == "TUBE" }.count == 1 &&
                    parts.filter { $0["kind"] as? String == "GUSSET" }.isEmpty &&
                    skirt?["side"] == nil &&
                    skirt?["shape"] as? String == "straight_skirt" &&
                    (bodyDimensions?["circumference_cm"] as? NSNumber)?
                        .doubleValue == 72 &&
                    (skirtDimensions?["circumference_cm"] as? NSNumber)?
                        .doubleValue == 96 &&
                    skirt?["waist_join_mode"] as? String == "GATHER" &&
                    skirt?["waist_join_state"] as? String == "PROPOSED" &&
                    provenance?["state"] as? String == "PROPOSED" &&
                    provenance?["dimensions_changed"] as? Bool == false,
                    "STRAIGHT_SKIRT_TUBE_GATHER_WAS_NOT_SUBMITTED_TO_PYTHON")
        }
        if let straightSkirtPipeline = callActualPartsPipeline(
                candidates: straightSkirtCapture.sentCandidates),
           let rows = straightSkirtPipeline["candidates"] as? [[String: Any]] {
            require(rows.count == 3 && rows.allSatisfy {
                $0["execution_status"] as? String == "SUCCEEDED"
            }, "STRAIGHT_SKIRT_TUBE_PYTHON_PIPELINE_FAILED")
            for row in rows {
                let structure = row["structure"] as? [String: Any]
                let nodes = structure?["nodes"] as? [[String: Any]] ?? []
                let operations = structure?["operations"] as? [[String: Any]] ?? []
                require(nodes.filter {
                    $0["kind"] as? String == "TUBE"
                }.count == 1 && nodes.filter {
                    $0["kind"] as? String == "GUSSET"
                }.isEmpty && operations.contains {
                    $0["kind"] as? String == "GATHER" &&
                    $0["operation_id"] as? String ==
                        "gather-waist-straight-skirt-tube-to-straight-skirt-body"
                }, "PYTHON_DID_NOT_COMPILE_STRAIGHT_SKIRT_TUBE_AS_WAIST_GATHER")
            }
        } else {
            failures.append("STRAIGHT_SKIRT_TUBE_ACTUAL_PIPELINE_UNAVAILABLE")
        }

        guard let waistStackParsed =
                GarmentFactoryReactController.parseVisionProposal(
                    compactParallelWaistStackFixture),
              let waistStackCandidates = waistStackParsed["hypotheses"]
                as? [[String: Any]], waistStackCandidates.count == 3 else {
            failures.append("COMPACT_PARALLEL_WAIST_STACK_FIXTURE_WAS_REJECTED")
            return failures
        }
        for candidate in waistStackCandidates {
            let structure = candidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let body = nodes.first {
                $0["node_id"] as? String == "stack-body"
            }
            let inner = nodes.first {
                $0["node_id"] as? String == "stack-inner-flare"
            }
            let outer = nodes.first {
                $0["node_id"] as? String == "stack-outer-tube"
            }
            let bodyDimensions = body?["dimensions"] as? [String: Any]
            let innerDimensions = inner?["dimensions"] as? [String: Any]
            let outerDimensions = outer?["dimensions"] as? [String: Any]
            let innerAttributes = inner?["attributes"] as? [String: Any]
            let outerAttributes = outer?["attributes"] as? [String: Any]
            let innerProvenance = innerAttributes?["waist_join_provenance"]
                as? [String: Any]
            let outerProvenance = outerAttributes?["waist_join_provenance"]
                as? [String: Any]
            require(
                (bodyDimensions?["circumference_cm"] as? NSNumber)?
                    .doubleValue == 72 &&
                (innerDimensions?["top_circumference_cm"] as? NSNumber)?
                    .doubleValue == 72 &&
                (outerDimensions?["circumference_cm"] as? NSNumber)?
                    .doubleValue == 96,
                "PARALLEL_WAIST_STACK_DIMENSIONS_CHANGED")
            require(
                innerAttributes?["attached_to"] as? String == "stack-body" &&
                outerAttributes?["attached_to"] as? String == "stack-body" &&
                innerAttributes?["garment_unit"] as? String == "stacked-dress" &&
                outerAttributes?["garment_unit"] as? String == "stacked-dress",
                "PARALLEL_WAIST_STACK_WAS_DETACHED_OR_REUNITED")
            require(
                innerAttributes?["waist_stack_state"] as? String == "PROPOSED" &&
                innerAttributes?["waist_stack_parent"] as? String == "stack-body" &&
                innerAttributes?["waist_stack_id"] as? String ==
                    "waist-stack-stack-body" &&
                innerAttributes?["waist_stack_order"] as? Int == 1 &&
                innerAttributes?["waist_stack_construction_mode"] as? String ==
                    "JOIN" &&
                innerAttributes?["waist_join_mode"] == nil &&
                innerProvenance?["waist_stack_parent"] as? String ==
                    "stack-body" &&
                innerProvenance?["waist_stack_order"] as? Int == 1 &&
                innerProvenance?["waist_stack_construction_mode"] as? String ==
                    "JOIN",
                "INNER_WAIST_STACK_CONTRACT_INVALID")
            require(
                outerAttributes?["waist_stack_state"] as? String == "PROPOSED" &&
                outerAttributes?["waist_stack_parent"] as? String == "stack-body" &&
                outerAttributes?["waist_stack_id"] as? String ==
                    "waist-stack-stack-body" &&
                outerAttributes?["waist_stack_order"] as? Int == 2 &&
                outerAttributes?["waist_stack_construction_mode"] as? String ==
                    "GATHER" &&
                outerAttributes?["waist_join_mode"] as? String == "GATHER" &&
                outerProvenance?["state"] as? String == "PROPOSED" &&
                outerProvenance?["waist_stack_order"] as? Int == 2 &&
                outerProvenance?["waist_stack_construction_mode"] as? String ==
                    "GATHER" &&
                outerProvenance?["source_length_cm"] as? Double == 96 &&
                outerProvenance?["target_length_cm"] as? Double == 72 &&
                outerProvenance?["dimensions_changed"] as? Bool == false,
                "OUTER_WAIST_STACK_GATHER_CONTRACT_INVALID")
            let records = candidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(records.contains {
                $0["kind"] as? String ==
                    "PROPOSED_SHARED_WAIST_STACK_NORMALIZATION" &&
                $0["waist_stack_parent"] as? String == "stack-body" &&
                $0["ordered_child_ids"] as? [String] == [
                    "stack-inner-flare", "stack-outer-tube",
                ] &&
                $0["dimensions_changed"] as? Bool == false &&
                $0["observed_authority_changed"] as? Bool == false
            }, "PARALLEL_WAIST_STACK_AUDIT_RECORD_MISSING")
        }

        final class ParallelWaistStackCapture: @unchecked Sendable {
            var sentCandidates: [[String: Any]] = []
        }
        let waistStackCapture = ParallelWaistStackCapture()
        let waistStackByID = Dictionary(uniqueKeysWithValues:
            waistStackCandidates.compactMap { candidate ->
                (String, [String: Any])? in
                guard let id = candidate["candidate_id"] as? String else {
                    return nil
                }
                return (id, candidate)
            })
        let waistStackController = GarmentFactoryReactController(
            door: { _, _ in ["verdict": "UNKNOWN_UNUSED_TEST_DOOR"] },
            toolDoor: { tool, arguments in
                guard tool == "garment_parts_ir_pipeline",
                      let text = arguments["json_text"] as? String,
                      let data = text.data(using: .utf8),
                      let request = try? JSONSerialization.jsonObject(with: data)
                        as? [String: Any],
                      let partsIR = request["parts_ir"] as? [String: Any],
                      let candidates = partsIR["candidates"] as? [[String: Any]]
                else { return ["verdict": "UNKNOWN_TEST_PIPELINE_INPUT"] }
                waistStackCapture.sentCandidates = candidates
                let outputs: [[String: Any]] = candidates.compactMap { candidate in
                    guard let id = candidate["candidate_id"] as? String,
                          let original = waistStackByID[id],
                          let structure = original["structure"] as? [String: Any]
                    else { return nil }
                    return [
                        "candidate_id": id,
                        "execution_status": "SUCCEEDED",
                        "structure": structure,
                        "artifact_binding": ["same_structure_digest": true],
                    ]
                }
                return ["verdict": "PROPOSED", "candidates": outputs]
            })
        let compiledWaistStacks = await waistStackController
            .runVisionPartsPipeline(waistStackCandidates)
        require(compiledWaistStacks?.count == 3 &&
                waistStackCapture.sentCandidates.count == 3,
                "PARALLEL_WAIST_STACK_DID_NOT_REACH_VISIBLE_PARTS_PIPELINE")
        for sentCandidate in waistStackCapture.sentCandidates {
            let parts = sentCandidate["parts"] as? [[String: Any]] ?? []
            let inner = parts.first {
                $0["part_id"] as? String == "stack-inner-flare"
            }
            let outer = parts.first {
                $0["part_id"] as? String == "stack-outer-tube"
            }
            let innerProvenance = inner?["waist_join_provenance"]
                as? [String: Any]
            let outerProvenance = outer?["waist_join_provenance"]
                as? [String: Any]
            require(
                inner?["attached_to"] as? String == "stack-body" &&
                outer?["attached_to"] as? String == "stack-body" &&
                inner?["garment_unit"] as? String == "stacked-dress" &&
                outer?["garment_unit"] as? String == "stacked-dress" &&
                inner?["waist_stack_order"] as? Int == 1 &&
                outer?["waist_stack_order"] as? Int == 2 &&
                inner?["waist_stack_construction_mode"] as? String == "JOIN" &&
                outer?["waist_stack_construction_mode"] as? String == "GATHER" &&
                innerProvenance?["waist_stack_parent"] as? String ==
                    "stack-body" &&
                outerProvenance?["waist_stack_parent"] as? String ==
                    "stack-body",
                "PARALLEL_WAIST_STACK_CONTRACT_WAS_NOT_SUBMITTED_TO_PYTHON")
        }
        if let waistStackPipeline = callActualPartsPipeline(
                candidates: waistStackCapture.sentCandidates),
           let rows = waistStackPipeline["candidates"] as? [[String: Any]] {
            let failureCodes = rows.flatMap {
                ($0["failures"] as? [[String: Any]] ?? []).compactMap {
                    $0["code"] as? String
                }
            }
            require(!failureCodes.contains(
                        "UNKNOWN_PARTS_TOPOLOGY_MULTIPLE_WAIST_CHILDREN"),
                    "REAL_PYTHON_REJECTED_TYPED_PARALLEL_WAIST_STACK")
            require(rows.count == 3 && rows.allSatisfy {
                $0["execution_status"] as? String == "SUCCEEDED"
            }, "PARALLEL_WAIST_STACK_PYTHON_PIPELINE_FAILED")
            for row in rows {
                let structure = row["structure"] as? [String: Any]
                let nodes = structure?["nodes"] as? [[String: Any]] ?? []
                let operations = structure?["operations"]
                    as? [[String: Any]] ?? []
                let inner = nodes.first {
                    $0["node_id"] as? String == "stack-inner-flare"
                }
                let outer = nodes.first {
                    $0["node_id"] as? String == "stack-outer-tube"
                }
                let innerDimensions = inner?["dimensions"] as? [String: Any]
                let outerDimensions = outer?["dimensions"] as? [String: Any]
                let outerAttributes = outer?["attributes"] as? [String: Any]
                let outerProvenance = outerAttributes?["waist_join_provenance"]
                    as? [String: Any]
                require(
                    structure?["state"] as? String == "PROPOSED" &&
                    (innerDimensions?["top_circumference_cm"] as? NSNumber)?
                        .doubleValue == 72 &&
                    (outerDimensions?["circumference_cm"] as? NSNumber)?
                        .doubleValue == 96 &&
                    outerProvenance?["state"] as? String == "PROPOSED" &&
                    outerProvenance?["dimensions_changed"] as? Bool == false &&
                    operations.contains {
                        $0["kind"] as? String == "JOIN" &&
                        $0["operation_id"] as? String ==
                            "join-waist-stack-body-stack-inner-flare"
                    } && operations.contains {
                        $0["kind"] as? String == "GATHER" &&
                        $0["operation_id"] as? String ==
                            "gather-waist-stack-outer-tube-to-stack-body"
                    },
                    "REAL_PYTHON_DID_NOT_PRESERVE_PARALLEL_WAIST_TRUTH")
            }
        } else {
            failures.append("PARALLEL_WAIST_STACK_ACTUAL_PIPELINE_UNAVAILABLE")
        }

        guard let garterParsed = GarmentFactoryReactController.parseVisionProposal(
                ambiguousLegUnitGarterFixture),
              let garterCandidates = garterParsed["hypotheses"]
                as? [[String: Any]], garterCandidates.count == 3 else {
            failures.append("AMBIGUOUS_LEG_UNIT_GARTER_FIXTURE_WAS_REJECTED")
            return failures
        }
        for garterCandidate in garterCandidates {
            let structure = garterCandidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let garter = nodes.first { $0["node_id"] as? String == "garter-01" }
            let attributes = garter?["attributes"] as? [String: Any]
            let contact = attributes?["contact_target_provenance"]
                as? [String: Any]
            require(attributes?["attached_to"] == nil &&
                    attributes?["model_attached_to"] as? String ==
                        "leggings-unit-01" &&
                    attributes?["detail_role"] as? String ==
                        "standalone_garter" &&
                    attributes?["attachment_state"] as? String ==
                        "PROPOSED_STANDALONE_CONTACT" &&
                    Set(contact?["possible_target_node_ids"] as? [String]
                        ?? []) == Set(["garter-leg-left", "garter-leg-right"]) &&
                    contact?["sewn_join_created"] as? Bool == false &&
                    contact?["not_observed_from_front"] as? Bool == true,
                    "AMBIGUOUS_GARTER_UNIT_ALIAS_WAS_SILENTLY_SEWN_TO_ONE_LEG")
            let records = garterCandidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(records.contains {
                $0["kind"] as? String == "AMBIGUOUS_UNIT_BAND_CONTACT" &&
                $0["source_part_id"] as? String == "garter-01" &&
                $0["join_created"] as? Bool == false
            }, "AMBIGUOUS_GARTER_CONTACT_RECORD_MISSING")
        }

        guard let directGarterParsed =
                GarmentFactoryReactController.parseVisionProposal(
                    directBodyGarterFixture),
              let directGarterCandidates = directGarterParsed["hypotheses"]
                as? [[String: Any]], directGarterCandidates.count == 3 else {
            failures.append("DIRECT_BODY_GARTER_FIXTURE_WAS_REJECTED")
            return failures
        }
        for directCandidate in directGarterCandidates {
            let structure = directCandidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let garter = nodes.first {
                $0["node_id"] as? String == "direct-thigh-garter"
            }
            let attributes = garter?["attributes"] as? [String: Any]
            let contact = attributes?["contact_target_provenance"]
                as? [String: Any]
            require(attributes?["attached_to"] == nil &&
                    attributes?["model_attached_to"] as? String ==
                        "direct-garter-body" &&
                    attributes?["detail_role"] as? String ==
                        "standalone_garter" &&
                    contact?["sewn_join_created"] as? Bool == false,
                    "DIRECT_BODY_GARTER_WAS_INVENTED_AS_A_SEWN_WAIST_JOIN")
            let records = directCandidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(records.contains {
                $0["kind"] as? String == "LIMB_BAND_CONTACT_ACCESSORY" &&
                $0["source_part_id"] as? String == "direct-thigh-garter" &&
                $0["join_created"] as? Bool == false
            }, "DIRECT_GARTER_CONTACT_RECORD_MISSING")
        }

        guard let boundedSleeveParsed =
                GarmentFactoryReactController.parseVisionProposal(
                    boundedSleeveJoinFixture),
              let boundedSleeveCandidates = boundedSleeveParsed["hypotheses"]
                as? [[String: Any]], boundedSleeveCandidates.count == 3 else {
            failures.append("BOUNDED_SLEEVE_JOIN_FIXTURE_WAS_REJECTED")
            return failures
        }
        for boundedCandidate in boundedSleeveCandidates {
            let structure = boundedCandidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            require(nodes.filter { $0["kind"] as? String == "SLEEVE" }.count == 2,
                    "TWO_SEGMENT_SLEEVE_WAS_REMOVED_AS_A_FAILED_BILATERAL_PAIR")
            let lower = nodes.first {
                $0["node_id"] as? String == "lower-sleeve-segment"
            }
            let dimensions = lower?["dimensions"] as? [String: Any]
            let attributes = lower?["attributes"] as? [String: Any]
            let provenance = attributes?["dimension_provenance"]
                as? [String: [String: Any]]
            require((dimensions?["upper_circumference_cm"] as? NSNumber)?
                        .doubleValue == 22 &&
                    provenance?["upper_circumference_cm"]?["dimension_source"]
                        as? String == "PROPOSED_RELATION_DERIVED" &&
                    provenance?["upper_circumference_cm"]?["model_supplied"]
                        as? Bool == false,
                    "PARSER_FALLBACK_SLEEVE_JOIN_BOUNDARY_WAS_NOT_RECONCILED")
            let records = boundedCandidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(records.contains {
                $0["kind"] as? String ==
                    "BOUNDED_SLEEVE_JOIN_BOUNDARY_NORMALIZATION" &&
                $0["target_part_id"] as? String == "lower-sleeve-segment" &&
                $0["model_values_changed"] as? Bool == false
            }, "BOUNDED_SLEEVE_JOIN_NORMALIZATION_RECORD_MISSING")
        }

        guard let explicitSleeveParsed =
                GarmentFactoryReactController.parseVisionProposal(
                    explicitMismatchedSleeveJoinFixture),
              let explicitSleeveCandidates = explicitSleeveParsed["hypotheses"]
                as? [[String: Any]], explicitSleeveCandidates.count == 3 else {
            failures.append("EXPLICIT_SLEEVE_JOIN_FIXTURE_WAS_REJECTED")
            return failures
        }
        for explicitCandidate in explicitSleeveCandidates {
            let explicitStructure = explicitCandidate["structure"]
                as? [String: Any]
            let explicitNodes = explicitStructure?["nodes"]
                as? [[String: Any]] ?? []
            let explicitLower = explicitNodes.first {
                $0["node_id"] as? String == "explicit-lower-sleeve"
            }
            let explicitDimensions = explicitLower?["dimensions"]
                as? [String: Any]
            let explicitAttributes = explicitLower?["attributes"]
                as? [String: Any]
            let joinProvenance = explicitAttributes?["sleeve_join_provenance"]
                as? [String: Any]
            let explicitRecords = explicitCandidate["normalization_records"]
                as? [[String: Any]] ?? []
            require((explicitDimensions?["upper_circumference_cm"] as? NSNumber)?
                        .doubleValue == 36 &&
                    explicitAttributes?["attachment_relation"] as? String ==
                        "GATHER" &&
                    explicitAttributes?["sleeve_join_mode"] as? String ==
                        "GATHER" &&
                    explicitAttributes?["sleeve_join_state"] as? String ==
                        "PROPOSED" &&
                    (joinProvenance?["source_length_cm"] as? NSNumber)?
                        .doubleValue == 36 &&
                    (joinProvenance?["target_length_cm"] as? NSNumber)?
                        .doubleValue == 22 &&
                    (joinProvenance?["ratio"] as? NSNumber)?.doubleValue ==
                        36.0 / 22.0 &&
                    joinProvenance?["dimensions_changed"] as? Bool == false &&
                    joinProvenance?["not_observed_from_front"] as? Bool == true,
                    "MODEL_SUPPLIED_LONGER_SLEEVE_WAS_NOT_TYPED_AS_GATHER")
            require(explicitRecords.contains {
                $0["kind"] as? String ==
                    "PROPOSED_SLEEVE_GATHER_RELATION" &&
                $0["source_part_id"] as? String == "explicit-lower-sleeve" &&
                $0["target_part_id"] as? String == "explicit-upper-sleeve" &&
                $0["dimensions_changed"] as? Bool == false
            }, "MODEL_SUPPLIED_SLEEVE_GATHER_AUDIT_RECORD_MISSING")
        }

        // Live image models commonly omit attachment_relation while naming a
        // part "lower sleeve". Python topology already derives an extension
        // from that placement, so Swift must apply the same boundary rule
        // before the candidate crosses the Parts IR boundary.
        let implicitMismatchedSleeveJoinFixture =
            explicitMismatchedSleeveJoinFixture.replacingOccurrences(
                of: "\"attachment_relation\":\"JOIN\",", with: "")
        guard let implicitSleeveParsed =
                GarmentFactoryReactController.parseVisionProposal(
                    implicitMismatchedSleeveJoinFixture),
              let implicitSleeveCandidates = implicitSleeveParsed["hypotheses"]
                as? [[String: Any]], implicitSleeveCandidates.count == 3 else {
            failures.append("IMPLICIT_SLEEVE_EXTENSION_FIXTURE_WAS_REJECTED")
            return failures
        }
        for implicitCandidate in implicitSleeveCandidates {
            let structure = implicitCandidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let lower = nodes.first {
                $0["node_id"] as? String == "explicit-lower-sleeve"
            }
            let attributes = lower?["attributes"] as? [String: Any]
            let dimensions = lower?["dimensions"] as? [String: Any]
            let records = implicitCandidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(
                attributes?["attachment_relation"] as? String == "GATHER" &&
                attributes?["sleeve_join_state"] as? String == "PROPOSED" &&
                (dimensions?["upper_circumference_cm"] as? NSNumber)?
                    .doubleValue == 36 &&
                records.contains {
                    $0["kind"] as? String ==
                        "PROPOSED_SLEEVE_EXTENSION_RELATION_DERIVED" &&
                    $0["dimensions_changed"] as? Bool == false
                } &&
                records.contains {
                    $0["kind"] as? String ==
                        "PROPOSED_SLEEVE_GATHER_RELATION" &&
                    $0["dimensions_changed"] as? Bool == false
                },
                "IMPLICIT_LOWER_SLEEVE_EXTENSION_DID_NOT_BECOME_GATHER")
        }

        final class SleeveGatherCapture: @unchecked Sendable {
            var sentCandidates: [[String: Any]] = []
        }
        let sleeveGatherCapture = SleeveGatherCapture()
        let explicitByID = Dictionary(uniqueKeysWithValues:
            explicitSleeveCandidates.compactMap { candidate ->
                (String, [String: Any])? in
                guard let id = candidate["candidate_id"] as? String else {
                    return nil
                }
                return (id, candidate)
            })
        let sleeveGatherController = GarmentFactoryReactController(
            door: { _, _ in ["verdict": "UNKNOWN_UNUSED_TEST_DOOR"] },
            toolDoor: { tool, arguments in
                guard tool == "garment_parts_ir_pipeline",
                      let text = arguments["json_text"] as? String,
                      let data = text.data(using: .utf8),
                      let request = try? JSONSerialization.jsonObject(with: data)
                        as? [String: Any],
                      let partsIR = request["parts_ir"] as? [String: Any],
                      let candidates = partsIR["candidates"]
                        as? [[String: Any]]
                else { return ["verdict": "UNKNOWN_TEST_PIPELINE_INPUT"] }
                sleeveGatherCapture.sentCandidates = candidates
                let outputs: [[String: Any]] = candidates.compactMap { candidate in
                    guard let id = candidate["candidate_id"] as? String,
                          let original = explicitByID[id],
                          let structure = original["structure"] as? [String: Any]
                    else { return nil }
                    return [
                        "candidate_id": id,
                        "execution_status": "SUCCEEDED",
                        "structure": structure,
                        "artifact_binding": ["same_structure_digest": true],
                    ]
                }
                return ["verdict": "PROPOSED", "candidates": outputs]
            })
        let compiledSleeveGather = await sleeveGatherController
            .runVisionPartsPipeline(explicitSleeveCandidates)
        require(compiledSleeveGather?.count == 3 &&
                sleeveGatherCapture.sentCandidates.count == 3,
                "SLEEVE_GATHER_DID_NOT_REACH_PARTS_IR_BOUNDARY")
        for sentCandidate in sleeveGatherCapture.sentCandidates {
            let parts = sentCandidate["parts"] as? [[String: Any]] ?? []
            let lower = parts.first {
                $0["part_id"] as? String == "explicit-lower-sleeve"
            }
            let dimensions = lower?["dimensions"] as? [String: Any]
            let provenance = lower?["sleeve_join_provenance"]
                as? [String: Any]
            require(lower?["attachment_relation"] as? String == "GATHER" &&
                    lower?["sleeve_join_mode"] as? String == "GATHER" &&
                    lower?["sleeve_join_state"] as? String == "PROPOSED" &&
                    (dimensions?["upper_circumference_cm"] as? NSNumber)?
                        .doubleValue == 36 &&
                    (provenance?["source_length_cm"] as? NSNumber)?
                        .doubleValue == 36 &&
                    (provenance?["target_length_cm"] as? NSNumber)?
                        .doubleValue == 22 &&
                    provenance?["dimensions_changed"] as? Bool == false,
                    "SLEEVE_GATHER_FIELDS_WERE_NOT_SERIALIZED_TO_PARTS_IR")
        }

        guard let shorterSleeveParsed =
                GarmentFactoryReactController.parseVisionProposal(
                    shorterMismatchedSleeveJoinFixture),
              let shorterSleeveCandidates = shorterSleeveParsed["hypotheses"]
                as? [[String: Any]], shorterSleeveCandidates.count == 3 else {
            failures.append("SHORTER_SLEEVE_JOIN_FIXTURE_WAS_REJECTED")
            return failures
        }
        for shorterCandidate in shorterSleeveCandidates {
            let structure = shorterCandidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let lower = nodes.first {
                $0["node_id"] as? String == "shorter-lower-sleeve"
            }
            let dimensions = lower?["dimensions"] as? [String: Any]
            let attributes = lower?["attributes"] as? [String: Any]
            let dimensionProvenance = attributes?["dimension_provenance"]
                as? [String: [String: Any]]
            let original = dimensionProvenance?["upper_circumference_cm"]?[
                "original_model_provenance"] as? [String: Any]
            let joinProvenance = attributes?["sleeve_join_provenance"]
                as? [String: Any]
            let alternatives = joinProvenance?[
                "construction_alternatives_unobserved"] as? [String] ?? []
            require((dimensions?["upper_circumference_cm"] as? NSNumber)?
                        .doubleValue == 22 &&
                    attributes?["attachment_relation"] as? String == "JOIN" &&
                    attributes?["sleeve_join_mode"] as? String ==
                        "PROPOSED_RELATION_DERIVED" &&
                    attributes?["sleeve_join_state"] as? String == "PROPOSED" &&
                    (dimensionProvenance?["upper_circumference_cm"]?[
                        "original_model_value_cm"] as? NSNumber)?.doubleValue == 18 &&
                    original?["dimension_source"] as? String ==
                        "MODEL_SUPPLIED_PROPOSAL" &&
                    joinProvenance?["dimensions_changed"] as? Bool == true &&
                    Set(alternatives) == Set(["GATHER", "PLEAT", "CUFF_YOKE"]),
                    "SHORTER_SLEEVE_PREVIEW_REDRAFT_LOST_MODEL_PROVENANCE")
            let records = shorterCandidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(records.contains {
                $0["kind"] as? String ==
                    "PROPOSED_SLEEVE_JOIN_PREVIEW_REDRAFT" &&
                ($0["original_source_length_cm"] as? NSNumber)?.doubleValue == 18 &&
                ($0["resolved_source_length_cm"] as? NSNumber)?.doubleValue == 22 &&
                $0["dimensions_changed"] as? Bool == true
            }, "SHORTER_SLEEVE_PREVIEW_REDRAFT_RECORD_MISSING")
        }

        let shorterPartsCandidates: [[String: Any]] =
            shorterSleeveCandidates.compactMap { candidate in
                guard let candidateID = candidate["candidate_id"] as? String,
                      let structure = candidate["structure"] as? [String: Any],
                      let nodes = structure["nodes"] as? [[String: Any]]
                else { return nil }
                let parts: [[String: Any]] = nodes.compactMap { node in
                    guard let partID = node["node_id"] as? String,
                          let kind = node["kind"] as? String,
                          let dimensions = node["dimensions"] as? [String: Any],
                          let attributes = node["attributes"] as? [String: Any]
                    else { return nil }
                    var part: [String: Any] = [
                        "part_id": partID, "kind": kind,
                        "layer": node["layer"] as? Int ?? 0,
                        "placement": attributes["placement"] as? String
                            ?? "segmented sleeve",
                        "visible_basis": [
                            "state": "PROPOSED",
                            "basis": attributes["visible_basis"] as? String
                                ?? "vision proposal",
                            "breaks_when": "review rejects this proposal",
                        ],
                        "dimensions": dimensions,
                    ]
                    for field in [
                        "garment_unit", "attached_to", "side", "shape",
                        "detail_role", "attachment_relation", "quantity",
                        "sleeve_join_mode", "sleeve_join_state",
                        "sleeve_join_provenance",
                    ] where attributes[field] != nil {
                        part[field] = attributes[field]
                    }
                    return part
                }
                guard parts.count == nodes.count else { return nil }
                return ["candidate_id": candidateID, "state": "PROPOSED",
                        "parts": parts]
            }
        if let shorterPipeline = callActualPartsPipeline(
                candidates: shorterPartsCandidates),
           let rows = shorterPipeline["candidates"] as? [[String: Any]] {
            require(rows.count == 3 && rows.allSatisfy {
                $0["execution_status"] as? String == "SUCCEEDED"
            }, "SHORTER_SLEEVE_REDRAFT_DID_NOT_REACH_ACTUAL_PYTHON_ARTIFACTS")
        } else {
            failures.append("SHORTER_SLEEVE_ACTUAL_PIPELINE_UNAVAILABLE")
        }

        var asymmetricFixture = singleVisibleFixture
        if let sleeveStart = asymmetricFixture.range(
                of: "\"part_id\":\"sleeve-right\"")?.lowerBound,
           let lengthRange = asymmetricFixture.range(
                of: "\"length_cm\":58",
                range: sleeveStart..<asymmetricFixture.endIndex) {
            asymmetricFixture.replaceSubrange(lengthRange, with: "\"length_cm\":72")
        }
        require(asymmetricFixture != singleVisibleFixture,
                "ASYMMETRIC_SLEEVE_FIXTURE_MUTATION_FAILED")
        if let asymmetricParsed = GarmentFactoryReactController.parseVisionProposal(
                asymmetricFixture),
           let asymmetricCandidates = asymmetricParsed["hypotheses"]
                as? [[String: Any]],
           let firstAsymmetric = asymmetricCandidates.first,
           let asymmetricStructure = firstAsymmetric["structure"] as? [String: Any],
           let asymmetricNodes = asymmetricStructure["nodes"] as? [[String: Any]] {
            require(!asymmetricNodes.contains { $0["kind"] as? String == "SLEEVE" },
                    "ASYMMETRIC_SLEEVES_WERE_COLLAPSED_AS_BILATERAL")
            let reviewedSleeves = (firstAsymmetric["uncompiled_visual_parts"]
                as? [[String: Any]] ?? []).filter {
                    $0["review_code"] as? String ==
                        "ASYMMETRIC_OR_UNRESOLVED_SLEEVE_PAIR"
                }
            require(reviewedSleeves.count == 2 &&
                    reviewedSleeves.allSatisfy {
                        $0["state"] as? String == "PROPOSED_UNCOMPILED"
                    }, "ASYMMETRIC_SLEEVE_REVIEW_PROVENANCE_WAS_LOST")
        } else {
            failures.append("ASYMMETRIC_SLEEVE_REVIEW_FIXTURE_WAS_REJECTED")
        }

        let sideSpecificSleeveChildFixture = #"""
        {"candidates":[{"candidate_id":"side-child-front",
          "back_design":"PROPOSED rear not visible",
          "assumptions":["rear and construction are unknown"],"parts":[
          {"part_id":"body","kind":"BODY_SHELL","layer":0,
           "placement":"torso","garment_unit":"upper-unit",
           "attached_to":null,"visible_basis":"visible upper shell",
           "dimensions":{"height_cm":44,"circumference_cm":94}},
          {"part_id":"sleeve-left","kind":"SLEEVE","layer":1,
           "placement":"left arm","garment_unit":"upper-unit",
           "attached_to":"body","side":"left","quantity":1,
           "visible_basis":"visible left sleeve",
           "dimensions":{"length_cm":58,"upper_circumference_cm":34,
                         "cuff_circumference_cm":20}},
          {"part_id":"sleeve-right","kind":"SLEEVE","layer":1,
           "placement":"right arm","garment_unit":"upper-unit",
           "attached_to":"body","side":"right","quantity":1,
           "visible_basis":"visible right sleeve",
           "dimensions":{"length_cm":58,"upper_circumference_cm":34,
                         "cuff_circumference_cm":20}},
          {"part_id":"ruffle-left","kind":"RUFFLE","layer":2,
           "placement":"left cuff lower edge","garment_unit":"upper-unit",
           "attached_to":"sleeve-left","side":"left","quantity":1,
           "visible_basis":"visible gathered strip at the left cuff",
           "dimensions":{"length_cm":48,"width_cm":7}}
        ]}]}
        """#
        guard let sideChildParsed =
                GarmentFactoryReactController.parseVisionProposal(
                    sideSpecificSleeveChildFixture),
              let sideChildCandidates = sideChildParsed["hypotheses"]
                as? [[String: Any]], sideChildCandidates.count == 3 else {
            failures.append("SIDE_SPECIFIC_SLEEVE_CHILD_FIXTURE_WAS_REJECTED")
            return failures
        }
        for candidate in sideChildCandidates {
            let structure = candidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let sleeves = nodes.filter { $0["kind"] as? String == "SLEEVE" }
            let mergedID = sleeves.first?["node_id"] as? String
            let ruffle = nodes.first { $0["node_id"] as? String == "ruffle-left" }
            let ruffleAttributes = ruffle?["attributes"] as? [String: Any]
            let address = ruffleAttributes?["parent_instance_address"]
                as? [String: Any]
            require(sleeves.count == 1 && mergedID != nil,
                    "SIDE_SPECIFIC_CHILD_SLEEVE_PAIR_WAS_NOT_NORMALIZED")
            require(ruffleAttributes?["attached_to"] as? String == mergedID &&
                    ruffleAttributes?["model_attached_to"] as? String ==
                        "sleeve-left" &&
                    address?["physical_instance_side"] as? String == "left" &&
                    address?["state"] as? String == "PROPOSED_NORMALIZATION",
                    "SIDE_SPECIFIC_CHILD_PARENT_ADDRESS_WAS_NOT_REMAPPED")
            let nodeIDs = Set(nodes.compactMap { $0["node_id"] as? String })
            let dangling = nodes.contains { node in
                guard let attributes = node["attributes"] as? [String: Any],
                      let parent = attributes["attached_to"] as? String else {
                    return false
                }
                return !nodeIDs.contains(parent)
            }
            require(!dangling,
                    "BILATERAL_SLEEVE_NORMALIZATION_LEFT_A_DANGLING_CHILD")
            let records = candidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(records.contains { record in
                guard record["kind"] as? String ==
                        "BILATERAL_SLEEVE_NORMALIZATION",
                      let remapped = record["remapped_child_addresses"]
                        as? [[String: Any]] else { return false }
                return remapped.contains {
                    $0["child_part_id"] as? String == "ruffle-left" &&
                    $0["physical_instance_side"] as? String == "left"
                }
            }, "SIDE_SPECIFIC_CHILD_REMAP_PROVENANCE_MISSING")
        }

        let sideChildPartsCandidates: [[String: Any]] =
            sideChildCandidates.compactMap { candidate in
                guard let candidateID = candidate["candidate_id"] as? String,
                      let structure = candidate["structure"] as? [String: Any],
                      let nodes = structure["nodes"] as? [[String: Any]]
                else { return nil }
                let parts: [[String: Any]] = nodes.compactMap { node in
                    guard let partID = node["node_id"] as? String,
                          let kind = node["kind"] as? String,
                          let dimensions = node["dimensions"] as? [String: Any],
                          let attributes = node["attributes"] as? [String: Any]
                    else { return nil }
                    var part: [String: Any] = [
                        "part_id": partID, "kind": kind,
                        "layer": node["layer"] as? Int ?? 0,
                        "placement": attributes["placement"] as? String
                            ?? "visible garment region",
                        "visible_basis": [
                            "state": "PROPOSED",
                            "basis": attributes["visible_basis"] as? String
                                ?? "vision proposal",
                            "breaks_when": "review rejects this proposal",
                        ],
                        "dimensions": dimensions,
                    ]
                    for field in [
                        "garment_unit", "attached_to", "side", "shape",
                        "detail_role", "attachment_relation", "quantity",
                    ] where attributes[field] != nil {
                        part[field] = attributes[field]
                    }
                    return part
                }
                guard parts.count == nodes.count else { return nil }
                return ["candidate_id": candidateID, "state": "PROPOSED",
                        "parts": parts]
            }
        if let sideChildPipeline = callActualPartsPipeline(
                candidates: sideChildPartsCandidates),
           let rows = sideChildPipeline["candidates"] as? [[String: Any]] {
            require(rows.count == 3 && rows.allSatisfy {
                $0["execution_status"] as? String == "SUCCEEDED"
            }, "SIDE_SPECIFIC_SLEEVE_CHILD_DID_NOT_REACH_BOUND_ARTIFACTS")
        } else {
            failures.append("SIDE_SPECIFIC_SLEEVE_CHILD_PIPELINE_UNAVAILABLE")
        }

        let sideSpecificGoreFixture = #"""
        {"candidates":[{"candidate_id":"side-gore-front",
          "back_design":"PROPOSED rear not visible",
          "assumptions":["rear extent and sewing topology are unknown"],"parts":[
          {"part_id":"gore-body","kind":"BODY_SHELL","layer":0,
           "placement":"torso","garment_unit":"gore-look",
           "visible_basis":"visible fitted upper shell",
           "dimensions":{"height_cm":44,"circumference_cm":94}},
          {"part_id":"gore-skirt","kind":"FLARE","layer":0,
           "placement":"lower body","garment_unit":"gore-look",
           "attached_to":"gore-body","visible_basis":"visible base skirt",
           "dimensions":{"height_cm":64,"top_circumference_cm":76,
                         "bottom_circumference_cm":168}},
          {"part_id":"gore-left","kind":"GORE","layer":2,
           "placement":"left pleated sheer skirt surface",
           "garment_unit":"gore-look","attached_to":"gore-skirt",
           "side":"left","quantity":1,
           "detail_role":"model pleated panel",
           "visible_basis":"visible asymmetric translucent surface",
           "dimensions":{"length_cm":56,"top_width_cm":12,
                         "bottom_width_cm":42}}
        ]}]}
        """#
        guard let goreParsed = GarmentFactoryReactController.parseVisionProposal(
                sideSpecificGoreFixture),
              let goreCandidates = goreParsed["hypotheses"] as? [[String: Any]],
              goreCandidates.count == 3 else {
            failures.append("SIDE_SPECIFIC_GORE_FIXTURE_WAS_REJECTED")
            return failures
        }
        for candidate in goreCandidates {
            let structure = candidate["structure"] as? [String: Any]
            let nodes = structure?["nodes"] as? [[String: Any]] ?? []
            let gore = nodes.first { $0["node_id"] as? String == "gore-left" }
            let attributes = gore?["attributes"] as? [String: Any]
            let normalization = attributes?["gore_overlay_normalization"]
                as? [String: Any]
            require(attributes?["detail_role"] as? String == "gore_overlay" &&
                    attributes?["model_detail_role"] as? String ==
                        "model pleated panel" &&
                    attributes?["construction_role"] as? String ==
                        "PROPOSED_GORE_OVERLAY" &&
                    attributes?["attachment_relation"] as? String == "LAYER" &&
                    normalization?["physical_instance_side"] as? String ==
                        "left" &&
                    normalization?["seam_join_created"] as? Bool == false,
                    "SIDE_SPECIFIC_GORE_WAS_NOT_TYPED_AS_PROPOSED_OVERLAY")
            let records = candidate["normalization_records"]
                as? [[String: Any]] ?? []
            require(records.contains { record in
                record["kind"] as? String ==
                    "PROPOSED_ATTACHED_GORE_OVERLAY_NORMALIZATION" &&
                record["source_part_id"] as? String == "gore-left" &&
                record["target_part_id"] as? String == "gore-skirt" &&
                record["physical_instance_side"] as? String == "left" &&
                record["not_observed_from_front"] as? Bool == true
            }, "SIDE_SPECIFIC_GORE_NORMALIZATION_PROVENANCE_MISSING")
        }
        return failures
    }
}

#if !GARMENT_VISION_ORNAMENT_STANDALONE
final class GarmentVisionOrnamentAuditTests: XCTestCase {
    func testVisionPromptAndParserSourceBoundaries() {
        let failures = GarmentVisionOrnamentAudit.sourceFailures()
        XCTAssertTrue(failures.isEmpty, failures.joined(separator: "\n"))
    }

    @MainActor
    func testTwoOrnamentCandidatesParseAndReachPartsPipeline() async {
        let failures = await GarmentVisionOrnamentAudit.executionFailures()
        XCTAssertTrue(failures.isEmpty, failures.joined(separator: "\n"))
    }
}
#else

// Minimal app-boundary stubs used only when compiling the production
// controller as a standalone executable audit.
@MainActor
final class MCPEngine {
    static let shared = MCPEngine()
    func callTool(serverName: String, toolName: String,
                  arguments: [String: Any]) async -> String { "{}" }
}

@MainActor
final class GarmentGenerationJob {
    static let shared = GarmentGenerationJob()
    let jobID = "standalone-ornament-audit"
}

enum AtelierAnalyst {
    enum Pick {
        case vera
        case ollama(String)
        case jgen(String)
        case lmStudio(String)
        case cloud(String, String)

        var sourceName: String {
            switch self {
            case .vera: return "Vera"
            case .ollama(let model): return "Ollama: \(model)"
            case .jgen(let model): return "JGen: \(model)"
            case .lmStudio(let model): return "LM Studio: \(model)"
            case .cloud(let provider, let model):
                return "\(provider): \(model)"
            }
        }
    }
}

@MainActor
final class OllamaClient {
    static let shared = OllamaClient()
    func generate(model: String, prompt: String, maxTokens: Int,
                  temperature: Double) async -> String? { nil }
    func generateConversation(model: String, messages: [(String, String)],
                              imagesForLastUserMessage: [String],
                              allowImageFallback: Bool, maxTokens: Int,
                              temperature: Double) async -> String? { nil }
}

actor JCrossChatManager {
    static let shared = JCrossChatManager()
    var loadedModelName: String? { nil }
    func load(modelFileName: String) async throws {}
    func generate(conversation: [(String, String)], maxTokens: Int,
                  keepThinking: Bool) async throws -> String { "" }
}

@MainActor
final class LMStudioClient {
    static let shared = LMStudioClient()
    func generateCompleteConversation(model: String,
                                      messages: [(String, String)],
                                      maxTokens: Int,
                                      temperature: Double,
                                      responseFormat: [String: Any]? = nil) async -> String? { nil }
    func generateWithImage(model: String, systemPrompt: String,
                           userText: String, imageBase64: String,
                           mimeType: String, temperature: Double,
                           maxTokens: Int) async -> String? { nil }
}

private enum StandaloneCloudError: Error { case unavailable }

@MainActor
final class CloudAPIClient {
    static let shared = CloudAPIClient()
    func send(systemPrompt: String, userMessage: String,
              imageBase64: String? = nil, provider: String,
              modelOverride: String) async -> Result<String, Error> {
        .failure(StandaloneCloudError.unavailable)
    }
}

@main
private struct GarmentVisionOrnamentStandaloneRunner {
    static func main() async {
        let failures = GarmentVisionOrnamentAudit.sourceFailures()
            + (await GarmentVisionOrnamentAudit.executionFailures())
        if failures.isEmpty {
            print("PASS garment vision ornament parser and pipeline audit")
            exit(0)
        }
        for failure in failures { print("FAIL \(failure)") }
        exit(1)
    }
}
#endif
