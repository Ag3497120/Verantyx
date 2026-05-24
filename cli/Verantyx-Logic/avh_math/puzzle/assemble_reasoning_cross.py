from typing import Any, List, Dict, Optional
import re
from avh_math.cross.cross_core import ReasoningCross
from avh_math.puzzle.status_types import ReasoningStatus
from avh_math.cross.cross_similarity import find_similar_crosses
from avh_math.puzzle.strategy_infer import infer_strategy
from avh_math.puzzle.formula_gate import select_core_formula, is_global_formula, is_well_formed_formula
from avh_math.text_cross.formula_extractor import extract_formula_candidates
from avh_math.text_cross.question_template_loader import load_question_templates, infer_task_from_text

# タスクテンプレートのロード
QUESTION_TEMPLATES = load_question_templates("avh_math/db/question_templates.jsonl")

from avh_math.text_cross.builder import build_text_cross
from avh_math.pipeline.problem_classifier import classify_and_prepare_cross
from avh_math.puzzle.axiom_assembler import extract_axiom_pieces, generate_composite_candidates
from avh_math.puzzle.formula_repair import repair_partial_formula, looks_like_formula
from avh_math.puzzle.natural_language_assumptions import detect_natural_language_assumptions

from avh_math.puzzle.mapping_manager import MappingManager

from avh_math.puzzle.crystallizer import Crystallizer

from avh_math.puzzle.meta_cross import MetaManager

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
    # 0. Text-Cross 分解（形状シグネチャの取得）
    from avh_math.shape_signature import shape_signature
    sig = shape_signature(text)
    
    text_cross = build_text_cross(text)
    shape_seq = [
        str(n.content.get("shape", ""))
        for n in text_cross.nodes.values()
        if isinstance(n.content, dict)
    ]
    
    # 0.1 知識の結晶（Crystal）の照会
    nl_assumptions = detect_natural_language_assumptions(text)
    crystal = crystallizer.query_crystal(shape_seq, nl_assumptions)
    
    if crystal and crystal["confidence"] >= 0.8:
        cross = ReasoningCross()
        cross.metadata["input_text"] = text
        cross.status = crystal["verdict"]
        cross.assumptions = nl_assumptions
        cross.domain = sig.domain_hint or "unknown"
        cross.metadata["crystal_applied"] = True
        cross.metadata["crystal_confidence"] = crystal["confidence"]
        cross.evidence.append({"kind": "cross_crystal", "source_signature": shape_seq})
        return cross

    # 0.2 メタ戦略の照会 (NEW: 推論戦術の決定)
    meta_strategy = meta_manager.find_strategy(shape_seq)

    # 1. 形状ベースのマッピング照会
    cross = ReasoningCross()
    cross.metadata["input_text"] = text
    cross.domain = sig.domain_hint or "unknown"
    
    if meta_strategy:
        cross.strategy = meta_strategy["strategy"]
        cross.metadata["meta_strategy_applied"] = True
        cross.metadata["meta_confidence"] = meta_strategy["confidence"]

    mapping = mapping_manager.find_mapping(shape_seq)
    cross.metadata["input_text"] = text
    
    mapping = mapping_manager.find_mapping(shape_seq)
    if mapping:
        template = mapping["reasoning_template"]
        cross.core_formula = template.get("core_formula_pattern")
        cross.assumptions = list(set(template.get("required_assumptions", []) + nl_assumptions))
        cross.domain = mapping.get("domain", "unknown")
        cross.status = ReasoningStatus.TENTATIVE_ANSWER 
        
        if cross.core_formula:
            cross.verified_formula = cross.core_formula
            cross.metadata["verified_formula_committed"] = True

        cross.metadata["mapping_applied"] = True
        cross.metadata["mapping_confidence"] = mapping.get("confidence", 0.0)
        cross.evidence.append({"kind": "text_reasoning_mapping", "source_signature": shape_seq})
        
        # 決定打：仮定がある場合は、ここで return せず後続の精密分類や類推情報の収集を継続する
        if not nl_assumptions:
            return cross

    # --- 以下、マッピングがない場合の通常組立ロジック ---
    # 1. 式候補の抽出
    raw_candidates = extract_formula_candidates(text)
    
    # [STEP 1] 式の強制修復
    candidates = []
    for c in raw_candidates:
        fixed = repair_partial_formula(c["normalized"])
        if fixed:
            # 情報を更新
            c_copy = dict(c)
            c_copy["normalized"] = fixed
            candidates.append(c_copy)
    
    # 2. タスクの推論
    task = infer_task_from_text(text, QUESTION_TEMPLATES)
    
    # 3. [STEP 2] 自然文仮定の抽出
    nl_assumptions = detect_natural_language_assumptions(text)
    
    # 4. 全体式判定と昇格
    core_candidate, formula_type = select_core_formula(candidates, text)
    
    # [決定打] 確定した式を使ってドメインを再判定
    from avh_math.shape_signature import shape_signature
    sig = shape_signature(text, core_formula=core_candidate["normalized"] if core_candidate else None)
    
    # [拡張ロジック] 全体式が見つからなくても、タスクと部分式があれば昇格を許可する
    if not core_candidate and task and candidates:
        if is_well_formed_formula(candidates[0]["normalized"]):
            core_candidate = candidates[0]
            formula_type = "promoted_by_task"

    # 5. 初期 Cross の作成
    cross = ReasoningCross()
    cross.metadata["input_text"] = text
    cross.task = task
    cross.domain = sig.domain_hint # 決定打：最新のシグネチャから反映
    # 既存の仮定と自然文仮定を統合
    cross.assumptions = list(set(nl_assumptions)) 
    
    if formula_type == "no_candidates":
        cross.status = ReasoningStatus.INSUFFICIENT_EVIDENCE
        cross.metadata["reason"] = "No valid logical formulas detected in input."
        return cross

    # 5. Embedding Axis (core, syntax, assumption)
    cross.core_formula = core_candidate["normalized"]
    cross.syntax_nodes = [c["normalized"] for c in candidates]
    cross.metadata["core_source"] = formula_type
    
    if formula_type == "fragment_only":
        fragment = core_candidate["normalized"]
        
        from avh_math.puzzle.formula_gate import is_well_formed_formula
        if is_well_formed_formula(fragment):
            cross.core_formula = fragment
            cross.verified_formula = fragment
            cross.status = ReasoningStatus.TENTATIVE_ANSWER
            cross.metadata["is_fragment_adoption"] = True
            cross.metadata["verified_formula_committed"] = True
            cross.metadata["core_source"] = "well_formed_fragment_adoption"
            cross.metadata["reason"] = "Core formula unconfirmed; proceeding with valid fragment."
        else:
            cross.status = ReasoningStatus.INSUFFICIENT_EVIDENCE
            cross.metadata["reason"] = "Extracted fragment is ill-formed or incomplete."
    else:
        # 決定打：検証用 formula の確定（昇格スイッチ）
        if task and candidates:
            cross.verified_formula = candidates[0]["normalized"]
            cross.status = ReasoningStatus.TENTATIVE_ANSWER
            cross.metadata["verified_formula_committed"] = True
        elif core_candidate and formula_type == "global":
            cross.verified_formula = core_candidate["normalized"]
            cross.status = ReasoningStatus.TENTATIVE_ANSWER
            cross.metadata["verified_formula_committed"] = True

    # 6. 問題パターンの分類 (形状による直接分類)
    text_cross = build_text_cross(text)
    shape_seq = [
        str(n.content.get("shape", ""))
        for n in text_cross.nodes.values()
        if isinstance(n.content, dict)
    ]
    cross = classify_and_prepare_cross(shape_seq, cross)

    # 7. 形状ベースの類推（過去の事例との類似度検索）
    similar = find_similar_crosses(cross, cross_db.find_all() if cross_db else [])
    
    # 決定打：低信頼度のエビデンスも排除せず、すべて記録する
    for s in similar:
        cross.evidence.append({
            "kind": "similar_case",
            "id": getattr(s, 'id', 'unknown'),
            "source": "reasoning_cross_db",
            "confidence": getattr(s, 'confidence', 0.15), # フィルタリングせず低スコアでも保持
            "role": "puzzle_piece",
            "status": "tentative",
            "core": s.core_formula
        })

    # 8. === 決定打：公理の合成 (Axiom Assembly) ===
    # 類似事例やKBから得られた「ピース」を組み合わせる
    pieces = extract_axiom_pieces(cross)
    if pieces:
        composites = generate_composite_candidates(pieces)
        for c in composites:
            # 合成された仮説を syntax ノードとして追加
            cross.syntax_nodes.append(c["formula"])
            # 特殊なメタデータを付与して Verifier に知らせる
            cross.metadata[f"composite_{c['id']}"] = c

    # 戦略決定
    strategy_info = infer_strategy(similar)
    if strategy_info["confidence"] > 0.5:
        cross.strategy = strategy_info["strategy"]
        cross.metadata["strategy_source"] = "case_similarity"

    # 直前候補の保存（沈黙回避）
    cross.metadata["last_candidate"] = {
        "formula": cross.core_formula,
        "assumptions": cross.assumptions,
        "candidates": cross.syntax_nodes
    }

    return cross