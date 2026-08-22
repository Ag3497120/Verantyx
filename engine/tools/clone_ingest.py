"""運用者のクローンの記憶層を組む — ローカル限定、公開経路から構造的に切る。

置き場所
--------
`~/.verantyx-clone/` に置く。**リポジトリの中には置かない。** vera.db は
HuggingFace に公開実績があり、こちらには Apple Notes と未公開の方針判断が
入る。同じ木の下に置けば、いつか一緒に公開される。別の場所にするのが
唯一確実な切り方である。

何を入れるか
------------
2026-08-17、運用者が選んだ4種:

    決定と基準      「Xなら捨てる」「Yは厳禁」— 分岐を実際に決めるもの
    評価・所感      各ファイル/計画への見方 — **推測で埋めない。本人に訊く**
    作業のやり方    事前登録を書く、数値を捏造しない
    文体・言い回し   どう書くか

出典は3つ。どれも運用者自身が書いたものだけを取る:

    Apple Notes     208件
    コミット履歴     4リポジトリ 1,087本 — 判断とその理由が最も濃い
    HANDOFF/STATUS  引き継ぎ文書

なぜ推測で埋めないか
--------------------
記録に無い意見を持つクローンは、運用者が決して下さない判断を、確信を持って
下す。そして記録からは見分けがつかない。100時間の無人運転を壊すのはこちら側
であって、`ABSENT` が多いことではない。**沈黙が安全機構である。**
"""
from __future__ import annotations

import gzip
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

CLONE_HOME = Path.home() / ".verantyx-clone"
NOTES_DB = (Path.home() / "Library/Group Containers/group.com.apple.notes"
            / "NoteStore.sqlite")

#: 取り出したテキストから落とす。ノートの本文に混ざる制御断片。
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
#: protobuf の中の短い機械語断片。本文ではない。
_NOISE = re.compile(r"^[\W\d_]{0,3}$")


@dataclass
class Fragment:
    """一片。出典と話者を必ず持つ。持たないものは入れない。"""
    text: str
    source: str
    speaker: str = "operator"
    kind: str = ""          # decision / evaluation / method / style / raw
    when: str = ""

    def as_line(self) -> str:
        return self.text.strip()


@dataclass
class Harvest:
    fragments: List[Fragment] = field(default_factory=list)
    per_source: Dict[str, int] = field(default_factory=dict)
    skipped: Dict[str, int] = field(default_factory=dict)

    def add(self, f: Fragment) -> None:
        self.fragments.append(f)
        self.per_source[f.source] = self.per_source.get(f.source, 0) + 1

    def skip(self, why: str) -> None:
        self.skipped[why] = self.skipped.get(why, 0) + 1


# ── Apple Notes ──────────────────────────────────────────────────────────
def _note_text(blob: bytes) -> str:
    """gzip された protobuf から本文を取り出す。

    正式なパーサは使わない。Notes の protobuf 定義は非公開で、Apple の版
    ごとに変わる。ここが欲しいのは**文**であって構造ではないので、展開して
    UTF-8 として読める連続部分を拾う方が、間違った定義に合わせるより壊れにくい。
    """
    try:
        raw = gzip.decompress(blob)
    except Exception:
        return ""
    out: List[str] = []
    cur = bytearray()
    for b in raw:
        if 0x20 <= b < 0x7f or b >= 0xc0 or (0x80 <= b < 0xc0 and cur):
            cur.append(b)
        else:
            if len(cur) >= 4:
                try:
                    s = cur.decode("utf-8")
                except UnicodeDecodeError:
                    s = ""
                if s and not _NOISE.match(s):
                    out.append(s)
            cur = bytearray()
    if len(cur) >= 4:
        try:
            out.append(cur.decode("utf-8"))
        except UnicodeDecodeError:
            pass
    return _CTRL.sub(" ", "\n".join(out))


def harvest_notes(h: Harvest, db: Path = NOTES_DB, limit: Optional[int] = None) -> None:
    if not db.exists():
        h.skip("notes:db_missing")
        return
    tmp = CLONE_HOME / "_notes_copy.sqlite"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp.write_bytes(db.read_bytes())
    except PermissionError:
        h.skip("notes:no_full_disk_access")
        return
    con = sqlite3.connect(str(tmp))
    q = ("select o.ZTITLE1, d.ZDATA from ZICCLOUDSYNCINGOBJECT o "
         "join ZICNOTEDATA d on o.ZNOTEDATA = d.Z_PK where d.ZDATA is not null")
    if limit:
        q += " limit %d" % int(limit)
    for title, blob in con.execute(q):
        body = _note_text(blob or b"")
        if not body.strip():
            h.skip("notes:empty")
            continue
        for line in body.splitlines():
            line = line.strip()
            # 4文字未満は語の破片。ノートの本文にはならない。
            if len(line) < 8:
                continue
            h.add(Fragment(text=line, source="note:%s" % (title or "無題")[:40],
                           kind="raw"))
    con.close()
    tmp.unlink(missing_ok=True)


# ── コミット履歴 ─────────────────────────────────────────────────────────
#: 運用者本人のコミットだけを取る。共著者として私が書いた本文は、運用者の
#: 判断ではない。混ぜると「自分で書いたものを自分の記録として読む」という、
#: いちばん静かな汚染になる。
_MINE = re.compile(r"Co-Authored-By:\s*Claude", re.I)


def harvest_commits(h: Harvest, repos: Iterable[Path], author: str = "") -> None:
    for repo in repos:
        if not (repo / ".git").exists():
            h.skip("commits:not_a_repo")
            continue
        cmd = ["git", "-C", str(repo), "log", "--no-merges",
               "--pretty=format:%H%x1f%an%x1f%aI%x1f%B%x1e"]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=120).stdout
        except Exception:
            h.skip("commits:git_failed")
            continue
        for rec in out.split("\x1e"):
            parts = rec.strip().split("\x1f")
            if len(parts) < 4:
                continue
            _sha, an, when, body = parts[0], parts[1], parts[2], parts[3]
            if author and author.lower() not in an.lower():
                h.skip("commits:other_author")
                continue
            if _MINE.search(body):
                h.skip("commits:assistant_authored")
                continue
            for line in body.splitlines():
                line = line.strip()
                if len(line) < 8 or line.startswith(("#", "Signed-off-by")):
                    continue
                h.add(Fragment(text=line, source="commit:%s" % repo.name,
                               kind="decision", when=when[:10]))


# ── 引き継ぎ文書 ─────────────────────────────────────────────────────────
def harvest_docs(h: Harvest, paths: Iterable[Path]) -> None:
    for p in paths:
        if not p.exists():
            h.skip("docs:missing")
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip().lstrip("#-*> ").strip()
            if len(line) < 12 or line.startswith("|") or line.startswith("```"):
                continue
            h.add(Fragment(text=line, source="doc:%s" % p.name, kind="method"))


# ── 記憶層へ ─────────────────────────────────────────────────────────────
def build(h: Harvest, verbose: bool = True):
    """断片を Conversation の層化メモリへ。話者は必ず添える。"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from verantyx.conversation import Conversation

    conv = Conversation()
    for f in h.fragments:
        conv.add_turn(f.speaker, f.as_line())
    if verbose:
        cores = {c for t in conv.turns for c in t.cores}
        print("断片 %d / ターン %d / 核 %d本" % (len(h.fragments), len(conv.turns), len(cores)))
    return conv


def main() -> None:
    home = Path.home()
    h = Harvest()
    harvest_notes(h)
    harvest_commits(h, [home / "Projects" / n for n in
                        ("Verantyx", "verantyx-cli", "Verantyx-Vera-alpha", "Vera")])
    harvest_docs(h, sorted((home / "Projects" / "Vera").glob("HANDOFF*.md"))
                 + sorted((home / "Projects" / "Vera").glob("STATUS*.md")))

    print("── 収穫 ──")
    for s, n in sorted(h.per_source.items(), key=lambda kv: -kv[1])[:12]:
        print("  %-44s %5d" % (s[:44], n))
    print("  … 出典 %d種 / 断片 %d" % (len(h.per_source), len(h.fragments)))
    print("── 除外 ──")
    for w, n in sorted(h.skipped.items(), key=lambda kv: -kv[1]):
        print("  %-30s %5d" % (w, n))
    return h


if __name__ == "__main__":
    main()
