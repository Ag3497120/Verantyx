import re
from typing import List

def translate_to_formula(text: str) -> List[str]:
    """
    Translates natural language text into logical formula candidates using 
    structural patterns and keyword mapping.
    This serves as the 'Universal Translation Layer' for dynamic axiom generation.
    """
    formulas = []
    text_lower = text.lower()

    # 1. Known Logic Patterns (Domain Specific Heuristics)
    # Modal Logic
    if "transitive" in text_lower:
        formulas.append("([]p -> [][]p)")
    if "reflexive" in text_lower:
        formulas.append("([]p -> p)")
    if "symmetric" in text_lower:
        formulas.append("(p -> []<>p)")
    if "euclidean" in text_lower:
        formulas.append("(<>p -> []<>p)")
    if "serial" in text_lower:
        formulas.append("([]p -> <>p)")
    
    # System K (Base)
    if "kripke" in text_lower or "modal" in text_lower:
        formulas.append("([](p->q) -> ([]p -> []q))")

    # 2. Structural Patterns (Syntactic Translation)
    # "If P then Q" -> "P -> Q"
    # Capture simple sentences avoiding nested clauses for now
    if_then_matches = re.findall(r"if\s+([a-z0-9\(\)\s]+)\s+then\s+([a-z0-9\(\)\s]+)", text_lower)
    for p, q in if_then_matches:
        # Basic cleanup
        p = p.strip()
        q = q.strip()
        if len(p) < 50 and len(q) < 50: # Avoid capturing too much text
            formulas.append(f"({p}) -> ({q})")

    # "A implies B"
    implies_matches = re.findall(r"([a-z0-9\(\)\s]+)\s+implies\s+([a-z0-9\(\)\s]+)", text_lower)
    for p, q in implies_matches:
        formulas.append(f"({p}) -> ({q})")

    return list(set(formulas))
