#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, json, re
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists(): return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def write_jsonl(path: Path, rows: List[Dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")

def extract_field(text: str, key: str) -> str:
    # Safely match multi-line field content until next key or end
    pattern = rf"(?m)^{re.escape(key)}\s*(.*?)(?=\n[A-Za-z ]+:|\Z)"
    m = re.search(pattern, text, flags=re.DOTALL)
    return (m.group(1).strip() if m else "").strip()

def get_fingerprint(text: str) -> str:
    # 数学的な記号のみを抽出して正規化
    symbols = re.findall(r"[∈⊨¬∧∨→↔∀∃=\[\]{{}}<>(),]", text)
    return hashlib.md5("".join(symbols).encode()).hexdigest()[:8]

def infer_witness(domain: str, dropped: str) -> Optional[str]:
    d, dr = domain.lower(), dropped.lower()
    if "modal" in d:
        if "reflex" in dr: return "[]p->p"
        if "transit" in dr: return "[]p->[][]p"
    if "prop" in d:
        if "middle" in dr: return "p|~p"
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--patches-out", required=True)
    ap.add_argument("--report-out", required=True)
    args = ap.parse_args()

    kb = read_jsonl(Path(args.kb))
    patches = []
    report = {"processed": 0, "sigs_added": 0, "witness_added": 0}

    for e in kb:
        if e.get("kind") != "counterexample_schema": continue
        
        ref = str(e.get("refutation", ""))
        domain = e.get("domain", "unknown")
        dropped = extract_field(ref, "Dropped Assumption:")
        structure = extract_field(ref, "Structure:")
        
        # 署名生成
        fp = get_fingerprint(structure)
        sig = f"{domain}:{dropped.replace(' ', '_').lower()}:{fp}"
        
        # パッチ構築
        new_patterns = set(e.get("patterns", []))
        new_patterns.add(f"sig:{sig}")
        new_patterns.add(f"fp:{fp}")
        
        witness = infer_witness(domain, dropped)
        if witness:
            new_patterns.add(f"witness:{witness}")
            report["witness_added"] += 1
            
        patches.append({
            "id": e["id"], "op": "set_field", "path": "/patterns", "value": sorted(list(new_patterns)),
            "reason": "phase23:structurize"
        })
        
        report["processed"] += 1
        report["sigs_added"] += 1

    write_jsonl(Path(args.patches_out), patches)
    Path(args.report_out).write_text(json.dumps(report, indent=2))
    print(f"[OK] Structurized {report['processed']} entries.")

if __name__ == "__main__":
    main()
