# -*- coding: utf-8 -*-
"""分野コーパスを集める — ローカルの技術文書・規約・指示だけ。

集めるのは「コーディングの規約・指示・技術文書」。本店 (hf:imdb) が
英語の映画・人物・地理の散文であるのに対し、番人が扱う語 (TypeScript /
pytest / 絵文字 / 型注釈 …) はそこに一語も無い。ここではその語が実際に
使われている文書だけを集める。

除外は2種:
  SECRET  秘密らしい字面 (鍵・トークン・パスワード・メールアドレス) を
          含むファイル。中身は見ずにパスと理由だけ記録する
  DUP     内容が同一のファイル (複数リポジトリに同じ README がある)

出力: corpus_manifest.json (ファイル一覧・文字数・言語・除外の記録)
ネットワークは使わない。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from verantyx.lang import detect as detect_lang  # noqa: E402

HOME = Path.home()
OUT = Path(__file__).resolve().parent / "corpus_manifest.json"

#: 秘密らしい字面。1つでも当たったらファイルごと落とす (誤って落とす方に
#: 倒す — 技術文書は他にいくらでもあるが、漏れた鍵は戻らない)。
SECRET_PATTERNS = [
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("hf_token", re.compile(r"\bhf_[A-Za-z0-9]{20,}")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")),
    ("bearer", re.compile(r"[Bb]earer\s+[A-Za-z0-9._\-]{24,}")),
    ("assigned_secret", re.compile(
        r"(?i)\b(api[_-]?key|secret|passwd|password|token)\s*[:=]\s*"
        r"[\"']?[A-Za-z0-9/+_\-]{16,}")),
    # メールアドレス。利用者本人のものも含めて個人情報として落とす。
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
]

SKIP_DIR_PARTS = {
    ".git", ".venv", ".venv311", "node_modules", "site-packages",
    "build", "dist", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".DS_Store", "htmlcov", ".tox", "target",
}


def _skip(p: Path) -> bool:
    return any(part in SKIP_DIR_PARTS for part in p.parts)


def _iter_sources():
    """(group, path) を返す。素材はローカルの md だけ。"""
    alpha = HOME / "Projects" / "Verantyx-Vera-alpha"
    # 1. 本リポジトリの技術文書 (docs/ / experiments/ / ルートの md)
    for p in sorted(alpha.rglob("*.md")):
        if not _skip(p.relative_to(alpha)):
            yield ("repo_vera_alpha", p)

    # 2. ~/Projects 配下の他リポジトリ: README / CONTRIBUTING / CLAUDE /
    #    docs 直下。深さ3までに限る (生成物の山を拾わないため)。
    for proj in sorted((HOME / "Projects").glob("*/")):
        if proj.name == "Verantyx-Vera-alpha":
            continue
        for p in sorted(proj.rglob("*.md")):
            rel = p.relative_to(proj)
            if _skip(rel) or len(rel.parts) > 3:
                continue
            yield (f"repo_{proj.name}", p)

    # 3. Claude Code 公式プラグイン集の文書 (英語のコーディング規約・
    #    フック・スキル定義)。番人が扱う語がまさに使われている素材。
    mk = HOME / ".claude" / "plugins" / "marketplaces"
    for p in sorted(mk.rglob("*.md")):
        if not _skip(p):
            yield ("claude_plugins", p)

    # 4. 本人の作業記憶 (日本語の技術メモ)
    mem = HOME / ".claude" / "projects"
    for p in sorted(mem.rglob("memory/*.md")):
        yield ("claude_memory", p)

    # 5. Claude Code の changelog (英語・機能と設定の語彙)
    ch = HOME / ".claude" / "cache" / "changelog.md"
    if ch.exists():
        yield ("claude_changelog", ch)


def main() -> int:
    seen_hash: dict[str, str] = {}
    kept: list[dict] = []
    excluded_secret: list[dict] = []
    excluded_dup: list[dict] = []
    excluded_empty: list[str] = []

    for group, path in _iter_sources():
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError) as exc:
            excluded_empty.append(f"{path} ({type(exc).__name__})")
            continue
        if len(text.strip()) < 200:
            excluded_empty.append(str(path))
            continue
        hit = [name for name, rx in SECRET_PATTERNS if rx.search(text)]
        if hit:
            excluded_secret.append({"path": str(path), "matched": hit})
            continue
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()
        if h in seen_hash:
            excluded_dup.append({"path": str(path), "same_as": seen_hash[h]})
            continue
        seen_hash[h] = str(path)
        kept.append({"group": group, "path": str(path),
                     "chars": len(text), "lang": detect_lang(text),
                     "sha1": h})

    by_lang: dict[str, dict] = {}
    by_group: dict[str, dict] = {}
    for row in kept:
        for tbl, key in ((by_lang, row["lang"]), (by_group, row["group"])):
            slot = tbl.setdefault(key, {"files": 0, "chars": 0})
            slot["files"] += 1
            slot["chars"] += row["chars"]

    manifest = {
        "files": len(kept),
        "chars": sum(r["chars"] for r in kept),
        "by_lang": by_lang,
        "by_group": by_group,
        "excluded": {
            "secret": excluded_secret,
            "duplicate": len(excluded_dup),
            "duplicate_examples": excluded_dup[:10],
            "too_short_or_unreadable": len(excluded_empty),
        },
        "kept": kept,
    }
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"files={len(kept)} chars={manifest['chars']}")
    print("by_lang=", json.dumps(by_lang, ensure_ascii=False))
    print("by_group=", json.dumps(by_group, ensure_ascii=False))
    print(f"excluded_secret={len(excluded_secret)} "
          f"dup={len(excluded_dup)} short={len(excluded_empty)}")
    for row in excluded_secret[:20]:
        print("  SECRET:", row["path"], row["matched"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
