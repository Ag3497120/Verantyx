from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .cross import VerantyxCross


def default_cross_path(db_dir: str) -> Path:
    return Path(db_dir) / "cross_store.jsonl"


def append_cross(db_dir: str, cross: VerantyxCross) -> None:
    path = default_cross_path(db_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = cross.to_dict()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_cross_by_id(db_dir: str, cross_id: str, limit_scan: int = 200000) -> Optional[Dict[str, Any]]:
    path = default_cross_path(db_dir)
    if not path.exists():
        return None
    found = None
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i > limit_scan:
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("cross_id") == cross_id:
                found = obj
    return found


def append_audit(db_dir: str, cross_id: str, stage: str, payload: Dict[str, Any]) -> None:
    path = Path(db_dir) / "cross_audit.jsonl"
    rec = {
        "ts": int(time.time() * 1000),
        "cross_id": cross_id,
        "stage": stage,
        "payload": payload,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def append_patch(db_dir: str, cross_id: str, patch: Dict[str, Any]) -> None:
    path = Path(db_dir) / "cross_patches.jsonl"
    rec = {
        "ts": int(time.time() * 1000),
        "cross_id": cross_id,
        "patch": patch,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def piece_cache_get(db_dir: str, key: str) -> Optional[Dict[str, Any]]:
    path = Path(db_dir) / "cross_piece_cache.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get(key)
    except Exception:
        return None


def piece_cache_put(db_dir: str, key: str, value: Dict[str, Any]) -> None:
    path = Path(db_dir) / "cross_piece_cache.json"
    data: Dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[key] = value
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
