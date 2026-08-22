"""コーパスの根の一元化 — 移植の前提修理(2026-08-19)。

20ファイルが `Path.home() / "Projects" / "vera-corpus"` を直書きしていた。
macOS のこの機体でしか成立しないパスで、Windows/Linux 移植の即死点。
環境変数 VERA_CORPUS_ROOT が根を差し替え、無指定なら従来の場所 — 挙動は
この機体では一切変わらない。
"""
from __future__ import annotations

import os
from pathlib import Path


def corpus_root() -> Path:
    """The corpus root: $VERA_CORPUS_ROOT, else ~/Projects/vera-corpus."""
    env = os.environ.get("VERA_CORPUS_ROOT")
    return Path(env) if env else Path.home() / "Projects" / "vera-corpus"
