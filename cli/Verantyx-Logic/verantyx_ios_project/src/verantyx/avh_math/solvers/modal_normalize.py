# avh_math/solvers/modal_normalize.py
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

@dataclass
class ModalParse:
    ok: bool
    formula: str
    mapping: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff]")

def _strip(s: str) -> str:
    s = (s or "").strip()
    s = _ZERO_WIDTH.sub("", s)
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _basic_symbol_norm(s: str) -> str:
    s = s.replace("→", "->").replace("⇒", "->")
    s = s.replace("¬", "~").replace("∧", "&").replace("∨", "|")
    s = s.replace("□", "box ").replace("◇", "diamond ")
    return s

def _canonical_modal_keywords(s: str) -> str:
    s = re.sub(r"\bbox\b", "box", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdiamond\b", "diamond", s, flags=re.IGNORECASE)
    return s

def _map_atoms(s: str, prefer_pqr: bool = True) -> Tuple[str, Dict[str, str]]:
    mapping: Dict[str, str] = {}
    if not prefer_pqr:
        return s, mapping
    
    # Exclude operators and modal keywords
    keywords = {"box", "diamond", "true", "false", "and", "or", "not"}
    atoms = sorted(set(re.findall(r"\b([A-Za-z])\b", s)))
    pool = list("pqrstuvwxyzabcdefghijklmno")
    
    for a in atoms:
        if a.lower() in keywords: continue
        if a.lower() in ("p","q","r"):
            mapping[a] = a.lower()
        else:
            if pool:
                dst = pool.pop(0)
                while dst in ("p", "q", "r") and pool:
                    dst = pool.pop(0)
                mapping[a] = dst
            else:
                mapping[a] = a.lower()

    for src, dst in mapping.items():
        s = re.sub(rf"\b{re.escape(src)}\b", dst, s)
    return s, mapping

def _rewrite_box_diamond(s: str) -> str:
    s = re.sub(r"\bbox\s*", "[]", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdiamond\s*", "<>", s, flags=re.IGNORECASE)
    return s

def _tighten_ops(s: str) -> str:
    s = s.replace(" ", "")
    # Minimal canonical formatting
    s = s.replace("<->", " <-> ").replace("->", " -> ")
    s = s.replace("&", " & ").replace("|", " | ")
    return re.sub(r"\s+", " ", s).strip()

def _sanity_checks(s: str) -> List[str]:
    errs = []
    if s.endswith(("->", "&", "|", "<->")):
        errs.append("dangling_operator")
    if s.count("(") != s.count(")"):
        errs.append("unbalanced_parentheses")
    if not any(op in s for op in ("->", "&", "|", "[]", "<>", "<->")):
        errs.append("no_connective_or_modal")
    return errs

def normalize_modal_formula(formula: str, map_atoms: bool = True) -> ModalParse:
    try:
        s = _strip(formula)
        s = _basic_symbol_norm(s)
        s = _canonical_modal_keywords(s)
        
        # Remove trailing junk from natural language leakage
        s = re.sub(r"\b(a|an|the|tautology|valid|satisfiable)\b\s*$", "", s, flags=re.IGNORECASE).strip()

        atom_map = {}
        if map_atoms:
            s, atom_map = _map_atoms(s)
        
        s = _rewrite_box_diamond(s)
        s = _tighten_ops(s)
        
        errs = _sanity_checks(s)
        return ModalParse(ok=(len(errs) == 0), formula=s, mapping=atom_map, errors=errs)
    except Exception as e:
        return ModalParse(ok=False, formula=formula, errors=[str(e)])