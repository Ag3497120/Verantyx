from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

@dataclass
class CounterexampleDelta:
    add_assumption: str
    required_change: str           # e.g., "Add edge"
    edge: Optional[Tuple[int, int]] = None
    why_breaks: str                # Human explanation of why the CE is destroyed

def calculate_cex_deltas(
    formula: str,
    counterexample: Dict[str, Any],
    repair_suggestions: List[Dict[str, Any]]
) -> List[CounterexampleDelta]:
    """
    Analyzes how proposed repairs would structuraly change the counterexample.
    """
    deltas = []
    if not counterexample:
        return []

    n_worlds = counterexample.get("n_worlds", 1)
    edges = set(tuple(e) for e in counterexample.get("edges", []))
    
    for rs in repair_suggestions:
        for assumption in rs.get("add", []):
            if assumption == "assume:reflexive":
                # Find a world that violates reflexivity
                for w in range(n_worlds):
                    if (w, w) not in edges:
                        deltas.append(CounterexampleDelta(
                            add_assumption=assumption,
                            required_change="Add self-loop",
                            edge=(w, w),
                            why_breaks=f"Adding (w{w}, w{w}) satisfies reflexivity at world {w}. In this model, this makes the necessity operator look at the world itself, preventing it from being 'vacuously true' while the world's valuation is false."
                        ))
                        break # Just show one for brevity
            
            elif assumption == "assume:transitive":
                # Find a violation of transitivity: wRv, vRu but not wRu
                found = False
                for w in range(n_worlds):
                    for v in range(n_worlds):
                        if (w, v) in edges:
                            for u in range(n_worlds):
                                if (v, u) in edges and (w, u) not in edges:
                                    deltas.append(CounterexampleDelta(
                                        add_assumption=assumption,
                                        required_change="Add transitive edge",
                                        edge=(w, u),
                                        why_breaks=f"Adding (w{w}, w{u}) satisfies transitivity for the path w{w}->w{v}->w{u}. This forces the necessity operator at w{w} to account for the state at w{u}."
                                    ))
                                    found = True
                                    break
                        if found: break
                    if found: break

    return deltas