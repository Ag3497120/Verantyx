"""運用者が実際に打鍵した文だけを取り出す — 唯一、汚染されていない出典。

なぜ他が使えないか（2026-08-17 実測）
------------------------------------
    Apple Notes 48,335断片   66%が貼り付けたAI会話ログ。残りも助手の出力と
                             Webの貼り付けが大半。資格情報65行、第三者の
                             個人識別子539断片を含む。
    コミット 1,077本         Verantyx で Claude共著の明示は496本中199本だが、
                             表記の無いものを読むと文体は助手のもの。規約が
                             後から入っただけで、自動規則では分離できない。

どちらも取り込めば、出来るのは**運用者のクローンではなく、運用者が話して
きた助手たちのクローン**である。そして100時間、それが分岐を決める。

打鍵された文は違う。`type: user` かつ `content` が文字列の行だけが、人間が
キーボードから入れたものである。ツール結果は `content` が list で
`tool_result` を含み、システム注入は `<system-reminder>` を含む。この二つを
落とせば残りは本人の言葉しかない。

除外するもの
------------
資格情報と第三者の個人情報は、採否以前に落とす。ローカル限定であっても、
100時間動くエージェントが読む場所に置くものではない。
"""
from __future__ import annotations

import glob
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

TRANSCRIPTS = Path.home() / ".claude" / "projects"

#: 採否以前に落とす。数える一方で、中身は記録しない。
_CRED = re.compile(
    r"パスワード|password|passwd|二段階認証|Steam ?Guard|username\s*=|"
    r"sk-[A-Za-z0-9]{8}|api[_-]?key|secret|token\s*[:=]\s*['\"]|ssh-rsa",
    re.I)
_PII = re.compile(r"[A-Z]{2,}\d{6,}|\d{3}-\d{4}-\d{4}|\b\d{16}\b")
#: 貼り付け由来。打鍵ではない。
#:
#: 行単位では足りなかった。運用者は会話ログを丸ごと貼って見せることがあり、
#: その中の一行 一行は「打鍵されたメッセージの中身」ではあっても本人の言葉
#: ではない。**話者ラベルが付いていたら、そのメッセージ全体が貼り付けである** —
#: 人は自分の発言に「Assistant:」とは書かない。メッセージ単位で落とす。
_PASTED = re.compile(r"^(##\s*(Assistant|User)\b|###\s*Tool Run|```)")
_PASTED_MSG = re.compile(
    r"^\s*(Assistant|User|System)\s*[:：]|<think>|🤖\s*(モデルプロファイル|Model Profile)|"
    r"\[SkillLib\]|^\s*###?\s*Tool Run", re.M)
_INJECTED = re.compile(r"<system-reminder>|<command-name>|Caveat: The messages below")


@dataclass
class Typed:
    lines: List[str] = field(default_factory=list)
    sessions: int = 0
    messages: int = 0
    dropped: Dict[str, int] = field(default_factory=dict)

    def drop(self, why: str, n: int = 1) -> None:
        self.dropped[why] = self.dropped.get(why, 0) + n


def collect(root: Path = TRANSCRIPTS, min_chars: int = 12) -> Typed:
    t = Typed()
    for path in sorted(glob.glob(str(root / "**" / "*.jsonl"), recursive=True)):
        t.sessions += 1
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("type") != "user":
                    continue
                content = (d.get("message") or {}).get("content")
                # ツール結果は list。打鍵は必ず str。
                if not isinstance(content, str):
                    t.drop("tool_result")
                    continue
                if _INJECTED.search(content):
                    t.drop("system_injected")
                    continue
                if _PASTED_MSG.search(content):
                    t.drop("pasted_transcript_msg")
                    continue
                t.messages += 1
                for raw in content.splitlines():
                    s = raw.strip()
                    if len(s) < min_chars:
                        continue
                    if _PASTED.match(s):
                        t.drop("pasted")
                        continue
                    if _CRED.search(s):
                        t.drop("credential")
                        continue
                    if _PII.search(s):
                        t.drop("personal_identifier")
                        continue
                    t.lines.append(s)
    return t


def main() -> None:
    t = collect()
    uniq = list(dict.fromkeys(t.lines))
    print("記録 %d本 / 打鍵メッセージ %d通" % (t.sessions, t.messages))
    print("行 %d（重複除去後 %d）" % (len(t.lines), len(uniq)))
    print("── 採否以前に落としたもの ──")
    for w, n in sorted(t.dropped.items(), key=lambda kv: -kv[1]):
        print("   %-22s %7d" % (w, n))
    print("\n── 打鍵された文の例（先頭から）──")
    for s in uniq[:6]:
        print("   %s" % s[:76])
    return t


if __name__ == "__main__":
    main()
