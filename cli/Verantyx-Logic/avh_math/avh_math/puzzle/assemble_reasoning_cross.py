from typing import Any, List, Dict, Optional
import re
from avh_math.cross.cross_core import ReasoningCross
from avh_math.puzzle.status_types import ReasoningStatus
from avh_math.cross.cross_similarity import find_similar_crosses
from .strategy_infer import infer_strategy
from .formula_gate import select_core_formula, is_global_formula, is_well_formed_formula
from avh_math.text_cross.formula_extractor import extract_formula_candidates
from avh_math.text_cross.question_template_loader import load_question_templates, infer_task_from_text

# タスクテンプレートのロード
QUESTION_TEMPLATES = load_question_templates("avh_math/db/question_templates.jsonl")

from avh_math.text_cross.builder import build_text_cross
from avh_math.pipeline.problem_classifier import classify_and_prepare_cross
from .axiom_assembler import extract_axiom_pieces, generate_composite_candidates
from .formula_repair import repair_partial_formula, looks_like_formula
from .natural_language_assumptions import detect_natural_language_assumptions

from .mapping_manager import MappingManager
from .crystallizer import Crystallizer
from .meta_cross import MetaManager
from avh_math.shape_signature import shape_signature

# マッピング、結晶、メタDBのロード
MAPPING_DB_PATH = "avh_math/db/text_reasoning_mapping_kb.jsonl"
CRYSTAL_DB_PATH = "avh_math/db/cross_crystals.jsonl"
META_DB_PATH = "avh_math/db/meta_crosses.jsonl"

mapping_manager = MappingManager(MAPPING_DB_PATH)
crystallizer = Crystallizer(CRYSTAL_DB_PATH)
meta_manager = MetaManager(META_DB_PATH)

def assemble_reasoning_cross(text: str, cross_db: Any) -> ReasoningCross:
    """
    テキストから分解パズルを作成し、ReasoningCross を構築する。
    """
    # 0. 初期解析
    text_cross = build_text_cross(text)
    shape_seq = [
        str(n.content.get("shape", ""))
        for n in text_cross.nodes.values()
        if isinstance(n.content, dict)
    ]
    sig = shape_signature(text)
    nl_assumptions = detect_natural_language_assumptions(text)
    task = infer_task_from_text(text, QUESTION_TEMPLATES)

    # 1. Cross オブジェクトの初期化
    cross = ReasoningCross()
    cross.metadata["input_text"] = text
    cross.domain = sig.domain_hint or "unknown"
    cross.assumptions = nl_assumptions
    cross.task = task

    # 2. 知識の結晶（Crystal）の照会
    crystal = crystallizer.query_crystal(shape_seq, nl_assumptions)
    if crystal and crystal["confidence"] >= 0.8:
        cross.status = crystal["verdict"]
        cross.metadata["crystal_applied"] = True
        cross.metadata["crystal_confidence"] = crystal["confidence"]
        cross.evidence.append({"kind": "cross_crystal", "source_signature": shape_seq})
        return cross

    # 3. メタ戦略の照会
    meta_strategy = meta_manager.find_strategy(shape_seq)
    if meta_strategy:
        cross.strategy = meta_strategy["strategy"]
        cross.metadata["meta_strategy_applied"] = True
        cross.metadata["meta_confidence"] = meta_strategy["confidence"]

    # 4. 形状ベースのマッピング照会
    mapping = mapping_manager.find_mapping(shape_seq)
    if mapping:
        template = mapping["reasoning_template"]
        cross.core_formula = template.get("core_formula_pattern")
        cross.assumptions = list(set(cross.assumptions + template.get("required_assumptions", [])))
        cross.domain = mapping.get("domain", cross.domain)
        cross.status = ReasoningStatus.TENTATIVE_ANSWER
        
        if cross.core_formula:
            cross.verified_formula = cross.core_formula
            cross.metadata["verified_formula_committed"] = True
            cross.metadata["promotion_reason"] = "structure_mapping_match"

        cross.metadata["mapping_applied"] = True
        cross.metadata["mapping_confidence"] = mapping.get("confidence", 0.0)
        cross.evidence.append({"kind": "text_reasoning_mapping", "source_signature": shape_seq})
        
        if not nl_assumptions:
            return cross

    # 5. 通常組立ロジック（マッピングがない、または仮定の追加検証が必要な場合）
    raw_candidates = extract_formula_candidates(text)
    candidates = []
    for c in raw_candidates:
        fixed = repair_partial_formula(c["normalized"])
        if fixed:
            c_copy = dict(c)
            c_copy["normalized"] = fixed
            candidates.append(c_copy)
    
    core_candidate, formula_type = select_core_formula(candidates, text)
    
    # ドメインの再判定（式が確定したため精度向上）
    if core_candidate:
        sig = shape_signature(text, core_formula=core_candidate["normalized"])
        cross.domain = sig.domain_hint or cross.domain

    if formula_type == "fragment_only":
        # 断片の仮採用
        fragment = core_candidate["normalized"]
        if is_well_formed_formula(fragment):
            cross.core_formula = fragment
            cross.verified_formula = fragment
            cross.status = ReasoningStatus.TENTATIVE_ANSWER
            cross.metadata["is_fragment_adoption"] = True
            cross.metadata["verified_formula_committed"] = True
            cross.metadata["core_source"] = "well_formed_fragment_adoption"
        else:
            cross.status = ReasoningStatus.INSUFFICIENT_EVIDENCE
            cross.metadata["reason"] = "抽出された断片が式として不完全なため、推論を保留します。"
    elif formula_type == "no_candidates":
        if not cross.core_formula:
            cross.status = ReasoningStatus.INSUFFICIENT_EVIDENCE
            cross.metadata["reason"] = "有効な論理式が検出されませんでした。"
    else:
        # 正常な式抽出
        cross.core_formula = core_candidate["normalized"]
        cross.metadata["core_source"] = formula_type
        cross.verified_formula = cross.core_formula
        cross.status = ReasoningStatus.TENTATIVE_ANSWER
        cross.metadata["verified_formula_committed"] = True

    cross.syntax_nodes = [c["normalized"] for c in candidates]
    
    # 原子命題（変数）の抽出
    seen_atoms = set()
    for f in cross.syntax_nodes:
        for m in re.finditer(r"\b([A-Za-z])\b", f):
            seen_atoms.add(m.group(1))
    cross.atoms = sorted(list(seen_atoms))
    if not cross.atoms:
        cross.atoms = ["p"]

    # 6. 問題パターンの分類
    cross = classify_and_prepare_cross(shape_seq, cross)

    # 7. 形状ベースの類推
    similar = find_similar_crosses(cross, cross_db.find_all() if cross_db else [])
    for s in similar:
        cross.evidence.append({
            "kind": "similar_case",
            "id": getattr(s, 'id', 'unknown'),
            "source": "reasoning_cross_db",
            "confidence": getattr(s, 'confidence', 0.15),
            "role": "puzzle_piece",
            "status": "tentative",
            "core": s.core_formula
        })

    # 8. 公理の合成
    pieces = extract_axiom_pieces(cross)
    if pieces:
        composites = generate_composite_candidates(pieces)
        for c in composites:
            cross.syntax_nodes.append(c["formula"])
            cross.metadata[f"composite_{c['id']}"] = c

    # 戦略決定
    strategy_info = infer_strategy(similar)
    if strategy_info["confidence"] > 0.5:
        cross.strategy = strategy_info["strategy"]
        cross.metadata["strategy_source"] = "case_similarity"

    return cross
