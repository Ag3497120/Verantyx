#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
from pathlib import Path
from typing import Dict, Any

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    kb_path = Path(args.kb)
    out_path = Path(args.out)
    meta_path = out_path.with_name(out_path.stem + "_meta.json")

    offsets: Dict[str, int] = {}
    total_lines = 0

    with kb_path.open("rb") as f:
        while True:
            off = f.tell()
            line = f.readline()
            if not line:
                break
            total_lines += 1
            line_str = line.decode("utf-8", errors="ignore").strip()
            if not line_str:
                continue
            try:
                obj = json.loads(line_str)
            except Exception:
                continue
            eid = str(obj.get("id", "")).strip()
            if eid:
                offsets[eid] = off

    out_path.write_text(json.dumps(offsets, ensure_ascii=False), encoding="utf-8")

    meta: Dict[str, Any] = {
        "kb_path": str(kb_path),
        "offsets_path": str(out_path),
        "lines_scanned": total_lines,
        "ids_indexed": len(offsets),
        "kb_size_bytes": kb_path.stat().st_size,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] offsets: {out_path} (ids={len(offsets)})")
    print(f"[OK] meta   : {meta_path}")

if __name__ == "__main__":
    main()
