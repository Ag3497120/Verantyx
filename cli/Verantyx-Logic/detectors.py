from __future__ import annotations
import re
import os
import json
from typing import List, Dict, Tuple, Any

class MathDetector:
    """
    AVH-Math Decomposer (Sensor Layer)
    - Detects domain, assumptions, goals, and unknown terms.
    - Implements Axis Ver1 logic.
    """
    
    def __init__(self, db_dir: str = "avh_math/db"):
        self.db_dir = db_dir
        # Load known definitions to detect unknown terms
        self.known_concepts = self._load_known_concepts()

    def _load_known_concepts(self) -> Set[str]:
        # In a real system, this loads from schemas.json and knowledge_db.json
        # For MVP, we use a basic list of modal logic terms
        return {
            "kripke", "frame", "transitive", "reflexive", "euclidean", 
            "symmetric", "box", "diamond", "modal", "valid", "satisfiable",
            "P", "NP", "polynomial", "reduction", "coNP"
        }

    def detect_all(self, text: str) -> List[str]:
        props = []
        
        # 1. Domain Detection
        domain = self.detect_domain(text)
        if domain: props.append(f"domain:{domain}")
        
        # 2. Goal Detection
        goal = self.detect_goal(text)
        if goal: props.append(f"goal:{goal}")
        
        # 3. Assumption Extraction
        assumptions = self.detect_assumptions(text)
        for a in assumptions:
            props.append(f"assume:{a}")
            
        # 4. Unknown Term Detection (Axis Ver1 Strength)
        unknowns = self.detect_unknowns(text)
        if unknowns:
            props.append("evidence:unknown_term")
            # In a real system, specific unknowns would be stored in a context object
            
        # 5. Object Detection
        if "kripke" in text.lower() or "frame" in text.lower():
            props.append("obj:kripke_frame")
        if "□" in text or "box" in text.lower():
            props.append("obj:box_operator")
            
        return props

    def detect_domain(self, text: str) -> Optional[str]:
        t = text.lower()
        if any(x in t for x in ["modal", "kripke", "□", "◇"]):
            return "modal_logic"
        if any(x in t for x in ["p = np", "p vs np", "complexity", "reduction"]):
            return "complexity"
        if any(x in t for x in ["proof", "sequent", "deduction"]):
            return "proof_theory"
        return "logic"

    def detect_goal(self, text: str) -> Optional[str]:
        t = text.lower()
        if any(x in t for x in ["prove", "show that", "is it valid", "証明"]):
            return "prove_valid"
        if any(x in t for x in ["refute", "counterexample", "反例"]):
            return "find_countermodel"
        if any(x in t for x in ["compute", "value of", "計算"]):
            return "compute_value"
        return "decide_truth"

    def detect_assumptions(self, text: str) -> List[str]:
        assumes = []
        t = text.lower()
        if "transitive" in t or "推移" in t: assumes.append("frame_transitive")
        if "reflexive" in t or "反射" in t: assumes.append("frame_reflexive")
        if "symmetric" in t or "対称" in t: assumes.append("frame_symmetric")
        if "euclidean" in t or "ユークリッド" in t: assumes.append("frame_euclidean")
        
        # Negative detection
        if "not reflexive" in t or "反射的ではない" in t: assumes.append("not_reflexive")
        
        return assumes

    def detect_unknowns(self, text: str) -> List[str]:
        """
        Axis Ver1: Identify nouns or symbols not in DB.
        """
        # Simple heuristic: look for capitalized words or quoted terms not in known_concepts
        # (This would be more complex with proper NLP)
        words = re.findall(r'[A-Z][a-z]+|"[^"]+"', text)
        unknowns = []
        for w in words:
            if w.lower() not in self.known_concepts:
                unknowns.append(w)
        return unknowns
