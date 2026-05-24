#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[一-龥ぁ-んァ-ヴー]+")

def tokenize(text: str) -> List[str]:
    text = (text or "").lower()
    text = re.sub(r"\s+", " ", text).strip()
    toks = _TOKEN_RE.findall(text)
    stop = {"the","a","an","of","and","or","in","on","to","is","are","for","with"}
    return [t for t in toks if t not in stop and len(t) >= 2]

class KBCache:
    def __init__(self, kb_path: Path, offsets: Dict[str, int]):
        self.kb_path = kb_path
        self.offsets = offsets

    def get_entry(self, eid: str) -> Dict[str, Any]:
        off = self.offsets.get(eid)
        if off is None: raise KeyError(eid)
        with self.kb_path.open("rb") as f:
            f.seek(off)
            line = f.readline().decode("utf-8", errors="ignore").strip()
            return json.loads(line)

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def append_jsonl(path: Path, obj: Dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def run_phase15(script: Path, kb: Path, query: str) -> Dict[str, Any]:
    cmd = ["python3", str(script), "--kb", str(kb), "--query", query]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0: return {"ok": False, "stderr": p.stderr}
    try:
        return {"ok": True, "result": json.loads(p.stdout)}
    except:
        return {"ok": True, "raw": p.stdout}

def build_app(kb, offsets_path, index_path, graph_path, static_dir, phase15_script, feedback_path, audit_path):
    offsets = load_json(offsets_path)
    index = load_json(index_path)
    graph_obj = load_json(graph_path) if graph_path.exists() else None
    
    # Process graph for cytoscape
    nodes = []
    edges = []
    if graph_obj and "canonical_clusters" in graph_obj:
        for cid, info in graph_obj["canonical_clusters"].items():
            nodes.append({"id": cid, "label": cid, "size": len(info.get("members", []))})
    
    kb_cache = KBCache(kb, offsets)
    app = FastAPI(title="AVH-Math Phase18 UI")
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def root():
        return HTMLResponse((static_dir / "index.html").read_text(encoding="utf-8"))

    @app.get("/api/stats")
    def stats():
        return {"kb_ids": len(offsets), "graph_nodes": len(nodes)}

    @app.get("/api/entry/{eid}")
    def entry(eid: str):
        try:
            return kb_cache.get_entry(eid)
        except KeyError:
            raise HTTPException(status_code=404)

    @app.get("/api/search")
    def search(q: str, topk: int = 200):
        toks = tokenize(q)
        freq = {}
        for t in toks:
            for eid in index.get(t, []): freq[eid] = freq.get(eid, 0) + 1
        ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:topk]
        return {"candidates": ranked}

    @app.get("/api/graph")
    def get_graph():
        return {"nodes": nodes, "edges": edges}

    @app.get("/api/navigate")
    def navigate(q: str):
        return run_phase15(phase15_script, kb, q)

    @app.post("/api/feedback")
    async def feedback(payload: Dict[str, Any]):
        payload["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        append_jsonl(feedback_path, payload)
        return {"ok": True}

    return app

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--offsets", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--static-dir", required=True)
    ap.add_argument("--phase15-script", required=True)
    ap.add_argument("--feedback", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()

    app = build_app(Path(args.kb), Path(args.offsets), Path(args.index), Path(args.graph), Path(args.static_dir), Path(args.phase15_script), Path(args.feedback), Path(args.audit))
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port)

if __name__ == "__main__":
    main()
