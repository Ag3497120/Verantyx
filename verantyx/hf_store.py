"""HuggingFace Hub — publish and auto-fetch the base store.

Vera has no weights; the shippable artifact is the poured store. We host it
as a Hub *dataset* repo. If a Vera instance starts without a local store and
a base repo is configured, it fetches the base store so the engine works out
of the box.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


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
