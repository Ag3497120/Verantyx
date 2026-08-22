"""HuggingFace Hub — publish and auto-fetch the base store.

Vera has no weights; the shippable artifact is the poured store. We host it
as a Hub *dataset* repo. If a Vera instance starts without a local store and
a base repo is configured, it fetches the base store so the engine works out
of the box.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

#: 既定の配布元。設定を持たない新規クローンでも取りに行ける場所が要る
#: (2026-08-22)。環境変数 VERA_BASE_REPO と設定 hf_store_repo が優先。
#: **黙って 208MB を落とさない** — 取りに行くのは `vera fetch-store` を
#: 打った人の行為で、不在は不在として型で答える(この装置の線)。
DEFAULT_BASE_REPO = "kofdai/Verantyx-Vera-base-store"


def default_base_repo() -> str:
    """配布元の解決順: 環境変数 → 設定 → 同梱の既定。"""
    env = os.environ.get("VERA_BASE_REPO", "").strip()
    if env:
        return env
    try:
        from .config import VeraConfig

        cfg = getattr(VeraConfig.load(), "hf_store_repo", "") or ""
        if cfg.strip():
            return cfg.strip()
    except Exception:
        pass
    return DEFAULT_BASE_REPO


def upload_store(
    store_path: str, repo_id: str, *, private: bool = False
) -> Dict[str, Any]:
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return {"ok": False, "error": "pip install huggingface_hub"}
    api = HfApi()
    try:
        api.create_repo(repo_id, repo_type="dataset", private=private,
                        exist_ok=True)
        api.upload_file(
            path_or_fileobj=store_path,
            path_in_repo="vera_store.json",
            repo_id=repo_id,
            repo_type="dataset",
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "repo": repo_id,
            "url": f"https://huggingface.co/datasets/{repo_id}"}


def fetch_store(
    repo_id: str, dest: str, *, filename: str = "vera_store.json"
) -> Dict[str, Any]:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        return {"ok": False, "error": "pip install huggingface_hub"}
    try:
        path = hf_hub_download(
            repo_id=repo_id, filename=filename, repo_type="dataset"
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    import shutil

    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(path, dest)
    return {"ok": True, "repo": repo_id, "dest": dest}


def ensure_store(
    store_path: str, base_repo: Optional[str] = None
) -> Dict[str, Any]:
    """If the local store is missing and a base repo is set, fetch it."""
    if Path(store_path).is_file():
        return {"ok": True, "source": "local", "path": store_path}
    if not base_repo:
        return {"ok": False, "source": "none",
                "note": "no local store and no base repo configured"}
    return {"source": "hub", **fetch_store(base_repo, store_path)}


def store_status(store_path: str) -> Dict[str, Any]:
    """店が在るか、無いなら**どうすれば手に入るか**を型で答える。

    黙って落とさないので、代わりに次の一手を名指しする。不在を不在と
    言い、閉じ方を添える — 欠けの扱いはこの装置全体で同じ形。
    """
    p = Path(store_path)
    if p.is_file():
        return {"verdict": "ANSWER", "source": "local", "path": str(p),
                "bytes": p.stat().st_size}
    repo = default_base_repo()
    return {
        "verdict": "UNKNOWN_NO_STORE",
        "path": str(p),
        "base_repo": repo,
        "how_to_close": f"vera fetch-store --repo {repo}",
        "alternative": "vera documents <あなたの文書>  # 自分で注ぐ",
        "url": f"https://huggingface.co/datasets/{repo}",
    }
