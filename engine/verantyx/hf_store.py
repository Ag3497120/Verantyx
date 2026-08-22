"""HuggingFace Hub — publish and auto-fetch the base store.

Vera has no weights; the shippable artifact is the poured store. We host it
as a Hub *dataset* repo. If a Vera instance starts without a local store and
a base repo is configured, it fetches the base store so the engine works out
of the box.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

#: 既定の配布元。設定を持たない新規クローンでも取りに行ける場所が要る
#: (2026-08-22)。環境変数 VERA_BASE_REPO と設定 hf_store_repo が優先。
#: **黙って 208MB を落とさない** — 取りに行くのは `vera fetch-store` を
#: 打った人の行為で、不在は不在として型で答える(この装置の線)。
DEFAULT_BASE_REPO = "kofdai/Verantyx-Vera-base-store"
#: 配布元のアカウント。ここを固定しておくと、**後から出したデータセットが
#: そのまま IDE の一覧に現れる**(版を出すたびにアプリを直さなくてよい)。
#: 環境変数 VERA_STORE_AUTHOR で差し替えられる。
STORE_AUTHOR = "kofdai"
#: 一覧に載せる名前の条件(閉じた規則)。関係ないデータセットを店として
#: 出さないため。名前で選ぶだけなので、中身の確認は verify が行う。
STORE_NAME_HINTS = ("vera", "verantyx")


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


def list_stores(author: str = "", *, verify: bool = True,
                limit: int = 20) -> Dict[str, Any]:
    """配布元アカウントにある「店」を一覧する。

    版を増やすたびにアプリを直さなくて済むよう、固定するのは**アカウント**
    だけにして、そこにあるものを毎回読む。名前で候補を絞り(閉じた規則)、
    ``verify`` のときだけ実際に ``vera_store.json`` を持つかを確かめる —
    持っていないものを店として見せるのは、無いものを在ると言うのと同じ。

    網につながらない機械では、空一覧ではなく型で断る。
    """
    who = (author or os.environ.get("VERA_STORE_AUTHOR", "") or
           STORE_AUTHOR).strip()
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return {"verdict": "UNKNOWN_NO_HUB_CLIENT",
                "how_to_close": "pip install huggingface_hub"}
    api = HfApi()
    try:
        found = list(api.list_datasets(author=who))[:limit * 3]
    except Exception as e:
        return {"verdict": "UNKNOWN_OFFLINE", "author": who,
                "error": f"{type(e).__name__}: {e}"[:160],
                "note": "一覧は網が要る。既に手元に店があるなら要らない"}
    rows: List[Dict[str, Any]] = []
    for d in found:
        rid = getattr(d, "id", "")
        if not any(h in rid.lower() for h in STORE_NAME_HINTS):
            continue
        row: Dict[str, Any] = {"repo": rid,
                               "url": f"https://huggingface.co/datasets/{rid}"}
        last = getattr(d, "lastModified", None)
        if last is not None:
            row["last_modified"] = str(last)
        if verify:
            try:
                info = api.repo_info(rid, repo_type="dataset",
                                     files_metadata=True)
                sib = {f.rfilename: (getattr(f, "size", 0) or 0)
                       for f in info.siblings}
                if "vera_store.json" not in sib:
                    continue          # 店でないものは一覧に載せない
                row["bytes"] = sib["vera_store.json"]
            except Exception:
                row["bytes"] = None   # 確かめられなかった、を空と混ぜない
        rows.append(row)
        if len(rows) >= limit:
            break
    rows.sort(key=lambda r: r["repo"])
    return {"verdict": "ANSWER" if rows else "UNKNOWN_NONE_PUBLISHED",
            "author": who, "stores": rows, "default": default_base_repo()}


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
