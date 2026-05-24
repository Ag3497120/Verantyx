from __future__ import annotations
import os
import sys
import json
import traceback
import re
from typing import Optional
from datetime import datetime
from flask import Flask, render_template, request, jsonify

# Ensure current directory is in path for local imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine import MathEngine
from miner import KnowledgeMiner
from avh_math.text_cross.pipeline import prepare_query_with_hint

try:
    from avh_math.input_normalize import normalize_input as normalize_input_shared
except Exception:
    normalize_input_shared = None

_QUOTED_FORMULA_RE = re.compile(r'["“”]([^"“”]+)["“”]|「([^」]+)」|『([^』]+)』')

def _extract_quoted_formula(text: str) -> Optional[str]:
    for m in _QUOTED_FORMULA_RE.finditer(text or ""):
        frag = next((g for g in m.groups() if g), "")
        if any(op in frag for op in ("->", "<->", "&", "|", "~", "□", "◇", "[]", "<>")):
            return frag.strip()
    return None

def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    )
    
    db_dir = os.path.join(os.path.dirname(__file__), "db")
    engine = MathEngine(db_dir=db_dir)
    miner = KnowledgeMiner()
    
    KNOWLEDGE_DB_PATH = os.path.join(db_dir, "knowledge_db.json")
    PENDING_PATH = os.path.join(db_dir, "pending_knowledge.json")

    def _load_json(path: str, default):
        if not os.path.exists(path): return default
        with open(path, "r", encoding="utf-8") as f: return json.load(f)

    def _save_json(path: str, obj):
        with open(path, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=2)

    @app.get("/")
    def index():
        return render_template("math.html")

    @app.post("/api/math/solve")
    def api_math_solve():
        try:
            print("[API] Received solve request")
            data = request.get_json(force=True) or {}
            text = (data.get("text") or "").strip()
            max_worlds = int(data.get("max_worlds") or 3)
            print(f"[API] Text: {text[:50]}...")

            if not text:
                return jsonify({"ok": False, "error": "empty_input"}), 400

            # Phase 3: Engine uses internal tactics.json for search config.
            print("[API] Calling engine.solve()...")
            if normalize_input_shared:
                text = normalize_input_shared(text)
            text, text_cross_info = prepare_query_with_hint(text)
            quoted = _extract_quoted_formula(text) or text
            res = engine.solve(quoted)
            print(f"[API] Engine returned. OK: {res.ok}, Candidates: {len(res.ranked)}")

            candidates = []
            for i, c in enumerate(res.ranked):
                label = chr(65 + i)
                candidates.append({
                    "label": label,
                    "formula": c.formula,
                    "status": c.status,
                    "countermodel": c.counterexample,
                    "correspondence": "Unknown",
                    "audit": c.audit,
                    "proof_sketch": c.proof_sketch,
                    "cex_explain": c.cex_explain,
                    "explanation": c.explanation,
                    "repair_suggestions": c.repair_suggestions,
                    "counterexample_delta": c.counterexample_delta,
                    "counterexample_patch_proof": c.counterexample_patch_proof,
                    "minimal_patches": c.minimal_patches,
                    "minimal_assumption_sets": c.minimal_assumption_sets
                })

            # Extract unknown terms (Simple check against knowledge)
            unknown_terms = []
            # ... existing logic for unknown terms ...

            # Construct derived fields
            always_valid = (len(res.best_valid) == len(res.ranked)) if res.ranked else False
            verdict_summary = f"Verified {len(res.best_valid)}/{len(res.ranked)} candidates."

            out = {
                "ok": res.ok,
                "domain": "Modal Logic (AVH)",
                "assumptions": res.assumptions,
                "question": text,
                "always_valid": always_valid,
                "verdict_summary": verdict_summary,
                "audit_log": res.trace,
                "evidence_map": res.evidence_map,
                "candidates": candidates,
                "unknown_terms": unknown_terms,
                "text_cross": text_cross_info,
            }
            # Ensure JSON serializable payload
            safe_out = json.loads(json.dumps(out, default=str))
            return jsonify(safe_out)
        except Exception as e:
            traceback.print_exc()
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.errorhandler(500)
    def handle_500(e):
        return jsonify({"ok": False, "error": "internal_server_error"}), 500

    @app.post("/api/math/mine")
    def api_math_mine():
        try:
            data = request.get_json(force=True)
            term = data.get("term")
            if not term: return jsonify({"ok": False, "error": "No term"}), 400
            
            mined = miner.mine(term)
            mined_dict = miner.to_dict(mined)
            
            pending = _load_json(PENDING_PATH, {"items": []})
            item = {
                "id": f"pending:{int(datetime.utcnow().timestamp())}",
                "created_at": datetime.utcnow().isoformat(),
                "mined": mined_dict,
                "status": "pending"
            }
            pending["items"].append(item)
            _save_json(PENDING_PATH, pending)
            
            return jsonify({"ok": True, "pending_item": item})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.post("/api/math/approve")
    def api_math_approve():
        try:
            data = request.get_json(force=True)
            pending_id = data.get("pending_id")
            
            pending = _load_json(PENDING_PATH, {"items": []})
            target = next((x for x in pending["items"] if x["id"] == pending_id), None)
            if not target: return jsonify({"ok": False, "error": "Not found"}), 404
            
            mined = target["mined"]
            term = mined["term"]
            
            # Update Knowledge DB
            db = _load_json(KNOWLEDGE_DB_PATH, {})
            # Add to frame_properties or glossary?
            # Heuristic: if definition looks like a property...
            # For simplicity, add to "mined_concepts" section
            if "mined_concepts" not in db: db["mined_concepts"] = {}
            db["mined_concepts"][term] = mined
            
            _save_json(KNOWLEDGE_DB_PATH, db)
            
            target["status"] = "approved"
            _save_json(PENDING_PATH, pending)
            
            return jsonify({"ok": True, "approved_term": term})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5004, debug=False)
