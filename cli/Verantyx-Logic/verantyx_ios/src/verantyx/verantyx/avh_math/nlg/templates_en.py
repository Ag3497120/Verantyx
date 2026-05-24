from typing import Dict, List

# Template Schema:
# {
#   "id": "unique_id",
#   "text": "Template string with {placeholders}",
#   "required_slots": ["list", "of", "keys"],
#   "condition": "Condition description (for human reference)"
# }

TEMPLATES_EN = {
    # --- PROVED ---
    "proved_axiom": {
        "text": "The formula {formula} is **valid** (PROVED). It matches the known axiom {axiom_id}: {axiom_desc చ.",
        "required_slots": ["formula", "axiom_id", "axiom_desc"]
    },
    "proved_simulation": {
        "text": "The formula {formula} is **valid** (PROVED). It was verified in all checked models (up to {max_worlds} worlds) under the assumption(s): {assumptions}.",
        "required_slots": ["formula", "max_worlds", "assumptions"]
    },
    "proved_truth_table": {
        "text": "The formula {formula} is a **tautology** (PROVED). Verified by exhaustive truth table analysis ({assignments} assignments checked).",
        "required_slots": ["formula", "assignments"]
    },
    "proved_algebra": {
        "text": "The equation {formula} holds true (PROVED). Verified by algebraic evaluation.",
        "required_slots": ["formula"]
    },

    # --- DISPROVED ---
    "disproved_counterexample": {
        "text": "The formula {formula} is **invalid** (DISPROVED). A counterexample was found in a frame with {worlds_count} world(s).",
        "required_slots": ["formula", "worlds_count"]
    },
    "disproved_counterexample_detail": {
        "text": "Counterexample Details:\n- Failed World: {failed_world}\n- Valuation: {valuation}\n- Relations: {relations}",
        "required_slots": ["failed_world", "valuation", "relations"]
    },
    "disproved_truth_table": {
        "text": "The formula {formula} is **invalid** (DISPROVED). It evaluates to false when: {assignment}.",
        "required_slots": ["formula", "assignment"]
    },
    
    # --- UNKNOWN / TENTATIVE ---
    "unknown_insufficient": {
        "text": "The validity of {formula} could not be determined (**UNKNOWN**). The system lacks sufficient evidence or axioms to prove or disprove it.",
        "required_slots": ["formula"]
    },
    "unknown_tentative": {
        "text": "The formula {formula} is **tentatively** categorized based on structural similarity, but no rigorous proof was found.",
        "required_slots": ["formula"]
    },
    "unknown_missing_assumptions": {
        "text": "Reasoning stalled. Missing assumptions detected: {missing}. Please clarify if these properties hold.",
        "required_slots": ["missing"]
    },

    # --- ERROR ---
    "error_parse": {
        "text": "Could not parse the input as a logical formula. Please check the syntax.",
        "required_slots": []
    },
    "error_domain": {
        "text": "The domain '{domain}' is not fully supported for rigorous verification yet.",
        "required_slots": ["domain"]
    }
}
