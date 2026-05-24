#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AVH-Math System Manager
Integrates all phases (1-33) into a single command interface.
"""

import argparse
import os
import sys
import subprocess
import json
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.parent.resolve()
DB_DIR = BASE_DIR / "avh_math" / "db"
TOOLS_DIR = BASE_DIR / "tools"
STATIC_DIR = BASE_DIR / "phase17_static"

# Core Files
KB_FILE = DB_DIR / "foundation_kb.jsonl"
OFFSETS_FILE = DB_DIR / "kb_offsets.json"
INDEX_FILE = DB_DIR / "kb_index.json"
GRAPH_FILE = DB_DIR / "boundary_graph.json"
META_FILE = DB_DIR / "kb_meta.json"
PROOF_FILE = DB_DIR / "proof_library.jsonl"

def check_files():
    """Check if essential files exist."""
    missing = []
    if not KB_FILE.exists(): missing.append(str(KB_FILE))
    if not STATIC_DIR.exists(): missing.append(str(STATIC_DIR))
    
    if missing:
        print(f"[ERROR] Missing core files: {', '.join(missing)}")
        print("Please ensure foundation_kb.jsonl is present in avh_math/db/")
        sys.exit(1)

def run_init():
    """Initialize indexes and graphs (Phase 15-17)."""
    print("[INIT] Building indexes and graphs...")
    
    # 1. Build Offsets (Phase 17)
    # Using a simple inline script logic if the tool script isn't handy, 
    # but let's assume we use the existing retrieval tools or build new ones.
    # For robustness, I'll generate the offsets here directly.
    print(f"  -> Generating offsets for {KB_FILE.name}...")
    offsets = {}
    meta = {}
    with KB_FILE.open("rb") as f:
        offset = 0
        for line in f:
            try:
                entry = json.loads(line)
                eid = entry.get("id")
                if eid:
                    offsets[eid] = offset
                    meta[eid] = {
                        "domain": entry.get("domain", "unknown"),
                        "kind": entry.get("kind", "unknown"),
                        "title": entry.get("title", "")
                    }
            except:
                pass
            offset += len(line)
    
    with OFFSETS_FILE.open("w", encoding="utf-8") as f:
        json.dump(offsets, f)
    with META_FILE.open("w", encoding="utf-8") as f:
        json.dump(meta, f)
        
    # 2. Build BM25 Index (Phase 16/32)
    print(f"  -> Building BM25 index...")
    # Call the existing tool if available, or use the library
    try:
        from avh_math.retrieval_bm25 import build_kb_index_from_jsonl
        build_kb_index_from_jsonl(str(KB_FILE), str(INDEX_FILE))
    except ImportError:
        print("[WARN] avh_math.retrieval_bm25 not found. Skipping BM25 index.")

    # 3. Build/Check Boundary Graph (Phase 15)
    if not GRAPH_FILE.exists():
        print(f"  -> Boundary graph not found. Creating empty placeholder at {GRAPH_FILE.name}")
        with GRAPH_FILE.open("w", encoding="utf-8") as f:
            json.dump({"nodes": [], "edges": [], "clusters": {}, "hotspots": []}, f)

    print("[INIT] Complete.")

def run_server(port=8787):
    """Start the Phase 17+ UI Server."""
    print(f"[SERVER] Starting UI on http://127.0.0.1:{port}")
    
    cmd = [
        sys.executable,
        "phase17_ui_server.py",
        "--kb", str(KB_FILE),
        "--offsets", str(OFFSETS_FILE),
        "--index", str(INDEX_FILE),
        "--graph", str(GRAPH_FILE),
        "--meta", str(META_FILE),
        "--static-dir", str(STATIC_DIR),
        "--port", str(port)
    ]
    
    try:
        subprocess.run(cmd, check=True, cwd=BASE_DIR)
    except KeyboardInterrupt:
        print("\n[SERVER] Stopped.")

def run_loop():
    """Run the Phase 27 Verification Loop."""
    print("[LOOP] Starting Verification Loop (Phase 27)...")
    loop_script = TOOLS_DIR / "phase27_loop.sh"
    if not loop_script.exists():
        print(f"[ERROR] Loop script not found: {loop_script}")
        return

    try:
        subprocess.run(["bash", str(loop_script)], check=True, cwd=BASE_DIR)
    except Exception as e:
        print(f"[ERROR] Loop failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="AVH-Math Integrated Manager")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # init
    subparsers.add_parser("init", help="Initialize indexes and metadata")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start the UI server")
    serve_parser.add_argument("--port", type=int, default=8787, help="Port number")

    # loop
    subparsers.add_parser("loop", help="Run one iteration of the verification loop")

    # full-auto (init + serve)
    subparsers.add_parser("start", help="Initialize if needed and start server")

    args = parser.parse_args()

    if args.command == "init":
        check_files()
        run_init()
    elif args.command == "serve":
        check_files()
        # Check if indexes exist, if not warn
        if not OFFSETS_FILE.exists():
            print("[WARN] Indexes missing. Running init first...")
            run_init()
        run_server(args.port)
    elif args.command == "loop":
        check_files()
        run_loop()
    elif args.command == "start":
        check_files()
        if not OFFSETS_FILE.exists():
            run_init()
        run_server()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
