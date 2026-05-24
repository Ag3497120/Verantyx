from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

@dataclass
class SynthTemplate:
    template_id: str
    pattern: str          # 正規表現（式の形）
    requires: List[str]   # 仮定タグ
    steps: List[str]      # proof sketch の雛形
    used_knowledge: List[str]

def _norm(s: str) -> str:
    return " ".join(s.strip().split())

def synth_templates_from_kb(knowledge_db: Dict[str, Any]) -> List[SynthTemplate]:
    """
    KB(correspondence)から「式パターン→説明ステップ」を合成する。
    まずは様相論理の correspondence を対象にする（他分野も同じ仕組みで拡張）。
    """
    out: List[SynthTemplate] = []
    corr = (knowledge_db.get("correspondence") or {})

    # 例：transitive -> K4 -> □P -> □□P
    if "assume:transitive" in corr:
        k = corr["assume:transitive"]
        # □X -> □□X 形を一般化（Xは任意命題）
        # Normalized formula uses [], ->, and p (or A)
        out.append(SynthTemplate(
            template_id="synth.modal.K4",
            pattern=r"^\[\](?P<P>.+?)\s*->\s*\[\]\[\](?P=P)$",
            requires=["assume:transitive"],
            steps=[
                "仮定: 到達関係 R は推移的（transitive）。",
                "推移性により、公理4（K4）: □P → □□P が妥当（対応定理）。",
                "よって与式は常に成り立つ（Pに任意命題を代入）。"
            ],
            used_knowledge=["correspondence.assume:transitive"]
        ))

    if "assume:reflexive" in corr:
        out.append(SynthTemplate(
            template_id="synth.modal.T",
            pattern=r"^\[\](?P<P>.+?)\s*->\s*(?P=P)$",
            requires=["assume:reflexive"],
            steps=[
                "仮定: 到達関係 R は反射的（reflexive）。",
                "反射性により、公理T: □P → P が妥当（対応定理）。",
                "よって与式は常に成り立つ。"
            ],
            used_knowledge=["correspondence.assume:reflexive"]
        ))

    return out

def match_synth_template(
    formula: str,
    assumptions: List[str],
    templates: List[SynthTemplate],
) -> Optional[Tuple[SynthTemplate, Dict[str, str]]]:
    f = _norm(formula)
    aset = set(assumptions)
    for t in templates:
        if not set(t.requires).issubset(aset):
            continue
        m = re.match(t.pattern, f)
        if m:
            return t, m.groupdict()
    return None