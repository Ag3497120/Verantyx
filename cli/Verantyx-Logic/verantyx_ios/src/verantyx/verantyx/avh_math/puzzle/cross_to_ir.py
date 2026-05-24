from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class ProgramIR:
    kind: str              # truth_table | kripke | sat
    formula: str
    atoms: List[str]
    assumptions: List[str]
    params: Dict[str, Any] = field(default_factory=dict)

def cross_to_ir(cross: Any) -> ProgramIR:
    """ReasoningCross を プログラム中間表現（IR）に変換する"""
    formula = getattr(cross, 'verified_formula', None) or getattr(cross, 'core_formula', '')
    atoms = getattr(cross, 'atoms', ['p'])
    assumptions = getattr(cross, 'assumptions', [])
    domain = getattr(cross, 'domain', 'unknown')

    if domain == "propositional_logic":
        return ProgramIR(
            kind="truth_table",
            formula=formula,
            atoms=atoms,
            assumptions=assumptions
        )
    elif domain == "modal_logic":
        return ProgramIR(
            kind="kripke",
            formula=formula,
            atoms=atoms,
            assumptions=assumptions,
            params={
                "transitive": any("transitive" in a for a in assumptions),
                "reflexive": any("reflexive" in a for a in assumptions),
                "symmetric": any("symmetric" in a for a in assumptions)
            }
        )
    
    # デフォルト
    return ProgramIR(kind="truth_table", formula=formula, atoms=atoms, assumptions=assumptions)
