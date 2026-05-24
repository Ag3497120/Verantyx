from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ProofSketch:
    status: str  # "sketch_available" | "no_sketch"
    claim: str
    reasoning_steps: List[str]
    used_knowledge: List[str]
    audit: List[str]


def _norm_formula(f: str) -> str:
    # ここは必要なら正規化強化してOK（空白、全角記号など）
    return " ".join(f.strip().split())


from template_synth import synth_templates_from_kb, match_synth_template

def generate_proof_sketch(
    formula: str,
    assumptions: List[str],
    verify_status: str,  # "valid" | "invalid" | "unknown"
    knowledge_db: Dict[str, Any],
) -> ProofSketch:
    """
    Verantyx流:
      - 「証明器」ではなく「説明器」
      - 反例探索の結果と、対応知識DB（correspondence）を接続して
        “なぜ壊れなかったか/なぜ壊れたか” の骨格を出す。
    """
    audit: List[str] = []
    used: List[str] = []

    # Phase 6: Template Synthesis (Try this first for valid/unknown)
    if verify_status in ("valid", "unknown"):
        templates = synth_templates_from_kb(knowledge_db)
        hit = match_synth_template(formula, assumptions, templates)
        if hit:
            t, groups = hit
            audit.append(f"[SKETCH] synthesized template hit: {t.template_id}")
            return ProofSketch(
                status="sketch_available",
                claim=f"Valid under assumptions ({', '.join(t.requires)}): {_norm_formula(formula)}",
                reasoning_steps=t.steps,
                used_knowledge=t.used_knowledge,
                audit=audit,
            )

    f = _norm_formula(formula)
    corr = (knowledge_db.get("correspondence") or {})

    # まずは “超重要：反例があるなら、証明スケッチよりも「壊れ方」を説明する”
    if verify_status == "invalid":
        steps = [
            "反例モデルが存在するため、この式は与えられた仮定のもとで常に成り立つとは言えない。",
            "したがって、妥当性（validity）は否定される。",
        ]
        # よくある失敗理由を仮定から推定（最小）
        # Normalize f for comparison: remove all spaces, replace -> with ->
        f_tight = f.replace(" ", "").replace("→", "->")
        
        if "□" in f or "[]" in f or "<>" in f: # Modal formula check
             # T Axiom failure
             if "assume:reflexive" not in assumptions and f_tight in ["□A->A", "□P->P", "[]p->p", "[]A->A"]:
                note = (knowledge_db.get("counterexample_notes") or {}).get("missing_reflexive_breaks_T")
                if note:
                    steps.append(f"典型的な理由: {note.get('explain')}")
                    used.append("counterexample_notes.missing_reflexive_breaks_T")
        
        audit.append("[SKETCH] invalid -> explain by counterexample existence")
        return ProofSketch(
            status="sketch_available",
            claim=f"Invalid: {f}",
            reasoning_steps=steps,
            used_knowledge=used,
            audit=audit,
        )

    # valid / unknown の場合：対応定理で説明骨格を作る
    # 代表例：assume:transitive なら K4(□P→□□P) を根拠にできる
    # 今回は「□A -> □□A」パターンを最優先でスケッチ化
    f_tight = f.replace(" ", "").replace("→", "->")
    
    # 4 Axiom
    if f_tight in ["□A->□□A", "□P->□□P", "[]p->[][]p", "[]A->[][]A"]:
        if "assume:transitive" in assumptions and "assume:transitive" in corr:
            k = corr["assume:transitive"]
            used.append("correspondence.assume:transitive")
            audit.append("[SKETCH] use K4 correspondence for transitivity")

            steps = [
                "仮定: 到達関係 R は推移的（transitive）。",
                "推移性により、公理4（K4）: □P → □□P が妥当になる（対応定理）。",
                "与式は P=p の場合なので、□p → □□p は推移性のもとで常に成り立つ。",
            ]
            # unknown でも「反例が見つからなかった」結果と繋げる
            if verify_status == "unknown":
                steps.append("今回の小モデル探索でも反例が見つからなかったため、この説明と整合する。")

            return ProofSketch(
                status="sketch_available",
                claim=f"Valid under transitivity: {f}",
                reasoning_steps=steps,
                used_knowledge=used,
                audit=audit,
            )

    # T Axiom
    if f_tight in ["□A->A", "□P->P", "[]p->p", "[]A->A"]:
        if "assume:reflexive" in assumptions and "assume:reflexive" in corr:
            k = corr["assume:reflexive"]
            used.append("correspondence.assume:reflexive")
            audit.append("[SKETCH] use T correspondence for reflexivity")
            steps = [
                "仮定: 到達関係 R は反射的（reflexive）。",
                "反射性により、公理T: □P → P が妥当になる（対応定理）。",
                "与式は P=p の場合なので、□p → p は反射性のもとで常に成り立つ。",
            ]
            if verify_status == "unknown":
                steps.append("今回の探索でも反例が見つからなかったため、この説明と整合する。")
            return ProofSketch(
                status="sketch_available",
                claim=f"Valid under reflexivity: {f}",
                reasoning_steps=steps,
                used_knowledge=used,
                audit=audit,
            )

    # ここまで来たら “まだスケッチテンプレが無い”
    audit.append("[SKETCH] no template matched")
    return ProofSketch(
        status="no_sketch",
        claim=f"No sketch template for: {f}",
        reasoning_steps=[],
        used_knowledge=[],
        audit=audit,
    )