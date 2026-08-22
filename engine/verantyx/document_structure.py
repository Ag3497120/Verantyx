"""A document has sections and labels. The answer usually lives in one.

Why
---
A contest PDF was loaded and the store held it — 「必須要件」 sixteen times
over — and the engine still answered 「本課題 必須要件」, an index rather
than an answer. The document's actual answer was two lines the ingest
never kept:

    2. 必須要件
        データベースへのデータ登録（INSERT 処理）
        データベースからのデータ参照（SELECT 処理）

Sentence-level ingest read 51 of 68 lines, and the 17 it dropped were the
answer. A bullet is not a sentence, so it was never placed.

What this does, and what it refuses to do
-----------------------------------------
It **quotes**. A heading's section is returned verbatim, in document
order; a label's value is returned as written. Nothing here paraphrases,
summarises, or infers, and every emitted string is a substring of the
source or it does not appear at all — the pass line the pre-registration
calls the one that decides the mechanism.

That makes this a retrieval claim, not a comprehension one. The engine
does not understand the requirements; it can quote the right two lines
when asked about the heading they sit under. Every verdict here is worded
to keep saying so.

A sidecar, never a vote
-----------------------
This index is written beside the store and read by its own stage under
its own door name. It never enters the census, the same rule
`jawiki_shallow` has lived under since 2026-08-14: material a reader can
be handed is not material that gets to vote.

The PDF's indentation is gone
-----------------------------
Measured on the contest PDF: every extracted line reports indent 0, so
the nesting a reader sees on the page is not in the text. Structure is
recovered from what survived — numbered headings (`1. …`) and labelled
values (`提出期限: …`) — and from line width, because a line that wrapped
is a line that ran out of room. That last one is a measured property of
the document, not a constant: the wrap width is taken from the document
itself.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: `1. 必須要件` — a numbered heading. The number must be followed by a
#: space, or 「1.5倍」 becomes a section.
_HEADING = re.compile(r"^(\d+)[.．]\s+(\S.*)$")

#: `## 概要` — a Markdown heading. The author typed the marks by hand, so
#: unlike the bare-number form this cannot appear by accident in prose —
#: the only false source is `#`-comments inside code, which the fence
#: tracker in `_split_sections` excludes. 実測 2026-08-19: チャットログ
#: 級のMarkdown文書(#/##見出し)が単一節フォールバックに畳まれ、
#: 「どの節に何がある」が一切取れなかった — 見出し検出の狭さが文書分解の
#: 律速だった。
_MD_HEADING = re.compile(r"^(#{1,6})\s+(\S.*)$")

#: 「【概要】」「■ 適用範囲」 — 日本語ビジネス文書の飾り見出し。全行が
#: 【】に収まる短い行、または ■/◆ で始まる短い無終止の行だけを見出しに
#: する(。で終わる行は文、長い行は本文)。●・・- は箇条書き(_BULLET)と
#: 衝突するので見出し記号には数えない。
_DECOR_HEADING = re.compile(r"^(?:【.{1,24}】|[■◆]\s*\S.{0,23})$")

#: 「第2条 出張旅費」「第三章 総則」。日本語の規程はこの形で区切られるので、
#: アラビア数字とピリオドしか見ていない読み手には、条文書は一枚の節として
#: 届く。実測: 4条の社内規程が節1つに畳まれ、「第2条は」に見出し行だけが
#: 返り、その条の中身は一行も出なかった。
_JP_HEADING = re.compile(
    r"^第\s*([0-9０-９一二三四五六七八九十百]+)\s*([条章節項編款])\s*(.*)$")

_KANJI_DIGIT = {"〇": 0, "一": 1, "二": 2, "三": 3, "四": 4,
                "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _numeral(raw: str) -> Optional[int]:
    """「12」「１２」「十二」→ 12。読めなければ None。

    見出しの番号は順序の判定にしか使わないので、位取りは十・百まで。
    それを超える条番号を持つ規程はあるが、そこは番号ではなく本文の
    並び順で足りる — 読めない番号は見出しとして扱わないだけで、行は
    直前の節に残る。
    """
    t = raw.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if t.isdigit():
        return int(t)
    total, unit = 0, 0
    for ch in t:
        if ch in _KANJI_DIGIT:
            unit = _KANJI_DIGIT[ch]
        elif ch == "十":
            total += (unit or 1) * 10
            unit = 0
        elif ch == "百":
            total += (unit or 1) * 100
            unit = 0
        else:
            return None
    return (total + unit) or None

#: `提出期限: 2026 年 9 月 11 日（金） 23:59 まで` — a labelled value. The
#: name is short by construction; a long left side is a sentence that
#: happens to contain a colon.
_LABEL = re.compile(r"^(.{1,14}?)\s*[：:]\s*(\S.*)$")

#: A line ending in one of these has finished; anything else at full
#: width is a wrap.
_CLOSED = ("。", "）", ")", "」", "』", "：", ":", "；", ";", "！", "？")

#: A bullet marker at the head of a line. Measured: `load_paths` keeps
#: these (「• 提出期限: …」, 「o 入力フォームから…」) where the domain reader
#: strips them, and they are the strongest structural signal the PDF still
#: carries now that its indentation is gone. A line that starts with one
#: begins an item, so it can never be the continuation of the line above —
#: which is also what stops two adjacent items being welded into
#: 「…機能の実装o 画像ファイルの…」.
_BULLET = re.compile(r"^\s*(?:[•・○●◦▪‧·\u2022\u25e6]|o|[-*])\s+")


@dataclass
class Section:
    """One heading and the lines beneath it, verbatim and in order."""

    ordinal: int
    heading: str
    lines: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {"ordinal": self.ordinal, "heading": self.heading,
                "lines": list(self.lines)}


def _display_width(s: str) -> int:
    """Rendered width, counting a CJK character as two columns.

    Measured, and the reason this function exists: in characters, a wrapped
    line came out at 36 and an unwrapped item at 35, so no ratio separated
    them. The document mixes ASCII (Python, JavaScript, UPDATE) with
    Japanese, and ASCII is half as wide — counting characters was measuring
    the wrong quantity. In display columns the same lines are 67 and 57,
    and the ordinary 0.8 floor separates them with room to spare. The
    threshold was not moved; the measurement was corrected.
    """
    return sum(2 if unicodedata.east_asian_width(c) in "WFA" else 1
               for c in s)


def _wrap_width(lines: List[str]) -> int:
    """The width this document wraps at, from the document."""
    widths = sorted(_display_width(x) for x in lines if x.strip())
    if not widths:
        return 0
    # The long tail is the wrapped body text; the max is the wrap width.
    return widths[-1]


def rejoin(text: str) -> List[str]:
    """Physical lines back into logical ones.

    A PDF line break is not a sentence break. 「以下」/「の要件および…」 is
    one clause split by the page, and reading it as two lines is why the
    requirement lines looked like fragments.

    A line is treated as wrapped when it is near the document's own wrap
    width AND does not end on a closing mark. The width test is what keeps
    「テーマ設定の例」 — seven characters — from swallowing the example
    beneath it.
    """
    raw = [x.rstrip() for x in (text or "").splitlines()]
    width = _wrap_width(raw)
    floor = int(width * 0.8) if width else 0
    out: List[str] = []
    buf = ""
    for line in raw:
        s = line.strip()
        if not s:
            if buf:
                out.append(buf)
                buf = ""
            continue
        if buf and (_BULLET.match(line) or _HEADING.match(s)
                    or _MD_HEADING.match(s) or _JP_HEADING.match(s)):
            # A new item cannot be the tail of the previous one.
            out.append(buf)
            buf = ""
        buf = (buf + s) if buf else s
        # 見出し行そのものが折返しに見えることがある(「## Assistant」は
        # 終止記号なし・幅が floor を超えうる)。見出しは常に一行で完結 —
        # 次の行を溶接しない。
        is_head = bool(_MD_HEADING.match(s) or _JP_HEADING.match(s)
                       or _HEADING.match(s) or _DECOR_HEADING.match(s))
        wrapped = (not is_head
                   and _display_width(line.rstrip()) >= floor
                   and not s.endswith(_CLOSED))
        if not wrapped:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


#: 実測 2026-08-19: チャットログ(6,495行、「Verantyx project overview」)を
#: 通すと、アラビア数字見出し(_HEADING)が本文中の箇条書き(assistantの
#: 回答に埋め込まれた「1. 」「2. 」…)に反応し、2,222行・2,346行という
#: 巨大な「節」を作った——見出しテキストも「**時制・時点** — ｢当時の
#: 首相｣型｡面に時点を持つ設計自体が未」のように文の途中で切れていた。
#: この規模の節は、この店の規程・仕様書コーパス(第N条は数行、「1.」の
#: 素直な項目も数十行止まり)には一度も出ない — 番号が単調増加という
#: 条件だけでは、会話ログの散発的な箇条書きを本物の目次と区別できない。
_RUNAWAY_SECTION_LINES = 200


def _split_sections(
    lines: List[str], allow_arabic: bool
) -> Tuple[List[Section], Dict[str, str]]:
    """One pass of the split. `allow_arabic` gates `_HEADING`(「1. 」形)
    only — `_JP_HEADING`(「第N条」)stays on always, since its pattern is
    narrow enough that it has never been seen to misfire on ordinary
    prose. `_MD_HEADING`/`_DECOR_HEADING` も常時ON: 著者が手で打った
    マークであり、実測された誤発火の類(裸の番号が本文の箇条書きに反応)
    には属さない。Markdown の ## 節は 200 行を超えても正当(チャットログ
    の ## User / ## Assistant)なので、暴走検知の不信対象にもしない。"""
    secs: List[Section] = [Section(ordinal=0, heading="", lines=[])]
    labels: Dict[str, str] = {}
    #: コードフェンス内の `# comment` を見出しに立てないための状態。
    in_fence = False
    #: 番号の単調性は見出しの種類ごとに数える。章と条が交互に現れる規程
    #: (第1章 → 第1条 第2条 → 第2章 → 第3条) を一本の数列として読むと、
    #: 章に戻った時点で以降の条が全て節に立たなくなる。
    tops: Dict[str, int] = {}
    for line in lines:
        head = _BULLET.sub("", line).strip()
        if head.startswith("```"):
            in_fence = not in_fence
            secs[-1].lines.append(line)
            continue
        if in_fence:
            # フェンス内はコード — 見出し検出は全種とも走らせない。
            secs[-1].lines.append(line)
            continue
        mm = _MD_HEADING.match(head)
        if mm:
            tops["md"] = tops.get("md", 0) + 1
            secs.append(Section(ordinal=tops["md"],
                                heading=mm.group(2).strip()))
            continue
        if _DECOR_HEADING.match(head) and not head.endswith(("。", "．")):
            tops["decor"] = tops.get("decor", 0) + 1
            # 【概要】は行そのまま — 飾りごと引用に使われる名前。
            secs.append(Section(ordinal=tops["decor"], heading=head))
            continue
        jm = _JP_HEADING.match(head)
        if jm:
            n = _numeral(jm.group(1))
            kind = jm.group(2)
            if n is not None and n > tops.get(kind, 0):
                tops[kind] = n
                # 見出しは行そのまま。「第2条」は人が引用に使う名前で、
                # アラビア数字の「1.」とは違って落とせない。
                secs.append(Section(ordinal=n, heading=head))
                continue
        m = _HEADING.match(head) if allow_arabic else None
        if m:
            n = int(m.group(1))
            top = tops.get("", 0)
            # A numbered line whose number does not continue the document's
            # own sequence is a nested list, not a new section. 「6. 提出物
            # および提出期限」 is followed by 「1. プロジェクトフォルダ一式」,
            # and reading that 1 as a section split the submission list into
            # four empty headings — so the section that should answer
            # 「提出物は」 held two lines and none of its four items.
            if n > top:
                tops[""] = n
                secs.append(Section(ordinal=n, heading=m.group(2).strip()))
                continue
        secs[-1].lines.append(line)
        lm = _LABEL.match(head)
        if lm:
            name, value = lm.group(1).strip(), lm.group(2).strip()
            # First writing wins: a document that says 提出期限 twice is
            # stating it once and referring back to it, and overwriting
            # would silently prefer the reference.
            if name and value and name not in labels:
                labels[name] = value
    if not secs[0].lines:
        secs.pop(0)
    return secs, labels


def sections(text: str) -> Tuple[List[Section], Dict[str, str]]:
    """(sections, labels) — the document's own structure, verbatim.

    Text before the first heading belongs to no section; it is the
    document's preamble and is returned as section 0 so a question about
    the document itself has somewhere to land.
    """
    lines = rejoin(text)
    secs, labels = _split_sections(lines, allow_arabic=True)
    # 見出し検出の自己検査: 実際に立った節のどれかが暴走していないか。
    # 暴走していれば、アラビア数字見出しは信用せず引き直す(第N条・
    # Markdown・飾り見出しは残る — 誤発火の実測があるのは裸の番号だけで、
    # ## User のような Markdown 節は 200 行を超えても正当)。偽の見出し
    # 構造より、見出しの少ない正直な分割の方が読み手にとって安全。
    if any(len(s.lines) > _RUNAWAY_SECTION_LINES for s in secs):
        secs, labels = _split_sections(lines, allow_arabic=False)
    return secs, labels


def index(text: str, source: str) -> Dict[str, Any]:
    """The whole document, indexed by what a person would ask about."""
    secs, labels = sections(text)
    out = {"source": source,
           "sections": [s.as_dict() for s in secs],
           "labels": labels,
           "lines": len(rejoin(text))}
    # 文書側の辺(2026-08-19): 同じ行に書かれた内容連の対。連合の辺
    # (同一文共起、経路0/60→43回復・誤答0の実測)と同じ規則を、この
    # 文書自身に。節ごとに持ち、lookup が引用へ注釈として添える —
    # 「この文書はAとBを一つの行で関係づけている」という、追試可能な
    # 主張だけを運ぶ。票には入らない。
    try:
        from .lang import ja_content_runs
        for sec in out["sections"]:
            pairs = []
            for ln in (sec.get("lines") or []):
                runs = sorted({r for r in (ja_content_runs(ln) or [])
                               if 2 <= len(r) <= 10})
                if 2 <= len(runs) <= 12:
                    pairs += [(runs[i], runs[j])
                              for i in range(len(runs))
                              for j in range(i + 1, len(runs))]
            if pairs:
                sec["edges"] = sorted(set(pairs))[:64]
    except Exception:
        pass
    return out


def sidecar_path(store_path: Path) -> Path:
    return Path(store_path).with_suffix(".documents.json")


def set_document(store_path: Path, source: str, *,
                 detached: Optional[bool] = None,
                 priority: Optional[int] = None,
                 date: Optional[str] = None) -> Dict[str, Any]:
    """接続の切替と優先度 — データは消さない。

    「外す」が削除だったため、一度取り込んだ文書を戻せなかった(実測
    2026-08-19、ユーザ報告)。detached は接続の状態であって存在の状態では
    ない: lookup は接続中だけを見るが、sidecar には残り、attach で戻る。
    完全削除は purge(save 側の従来経路)だけが行う。"""
    book = load(store_path)
    for d in book.get("documents", []):
        if d.get("source") != source:
            continue
        if detached is not None:
            d["detached"] = bool(detached)
        if priority is not None:
            d["priority"] = int(priority)
        if date is not None:
            # 時系列(2026-08-19、操作者要請)。メモ同士は必ず矛盾する —
            # 「Xが欠点」の後に「X修理済み」が来る。これは時間的上書きで
            # あって規範衝突ではない。date は並び順と表示だけを変える:
            # 同優先度なら新しい文書から読み、引用には日付が付く。
            # 票には一切入らない — 古い記述は消えず、日付つきで並ぶ。
            d["date"] = str(date)
        sidecar_path(store_path).write_text(
            json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
        return {"verdict": "SET", "source": source,
                "detached": d.get("detached", False),
                "priority": d.get("priority", 0),
                "date": d.get("date")}
    return {"verdict": "UNKNOWN_NO_SUCH_DOCUMENT", "source": source,
            "have": [d.get("source") for d in book.get("documents", [])]}


def load(store_path: Path) -> Dict[str, Any]:
    p = sidecar_path(store_path)
    if not p.is_file():
        return {"documents": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"documents": []}


def save(store_path: Path, doc: Dict[str, Any]) -> Dict[str, Any]:
    """Add one document to the sidecar, replacing any earlier read of it."""
    book = load(store_path)
    docs = [d for d in book.get("documents", [])
            if d.get("source") != doc.get("source")]
    docs.append(doc)
    book["documents"] = docs
    sidecar_path(store_path).write_text(
        json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"verdict": "WROTE", "source": doc.get("source"),
            "sections": len(doc.get("sections", [])),
            "labels": len(doc.get("labels", {})),
            "documents": len(docs),
            "note": "見出しと項目をそのまま保存した。引用のみで、票は持たない"}


def _norm(s: str) -> str:
    """Compare on content, not on the spaces a PDF sprinkled in."""
    return re.sub(r"[\s　]+", "", s or "")


def content_terms(subject: str) -> List[str]:
    """The subject's own content words — no morphology, no guessing.

    Shared by the two places that need to know what a question is about:
    the fallback probe below, and the narrowing inside a matched section.
    """
    import re as _re
    from .lang import ja_content_runs
    out = set(ja_content_runs(subject))
    out |= {m.group(0) for m in _re.finditer(r"[ァ-ヶーA-Za-z0-9]+[一-龥]{0,2}", subject)}
    out |= {m.group(0) for m in _re.finditer(r"[一-龥]{2,}", subject)}
    return [t for t in out if len(t) >= 2]


def _ngrams(text: str, n: int) -> set:
    t = _norm(text)
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


#: 語段・2字段・3字段。concord の階段と同じ考えで、同じ行集合を別の解像度で
#: 読む。段を分割にしてはならない（語長で仕分けると各語が1段にしか入らず、
#: 一致は低いのではなく起こり得ない）ので、全段が全行を自分の粒度で見る。
_GRAINS = (0, 2, 3)


def _section_spread(book: Dict[str, Any], term: str) -> int:
    """探査語が何節にまたがって現れるか。少ないほど集中的で特定的。

    「集中度」こそが実際の特定性の指標だった。長さでも主辞性でもない。
    """
    pn = _norm(term)
    if not pn:
        return 10 ** 6
    n = 0
    for d in book.get("documents", []):
        for sec in d.get("sections", []):
            text = (sec.get("heading", "") or "") + "\n" + \
                   "\n".join(sec.get("lines") or [])
            if pn in _norm(text):
                n += 1
    return n
    # n==0(どの節にも無い語)は最小値のまま返す。最初は「一度も現れない
    # 語は最後尾に送る」つもりで大きな値を返していたが、それは既存の
    # 不在昇格(_earlier_absent)の前提と正面衝突した。あの仕組みは
    # 「より特定的な語を先に試し、不在なら記録しておいて、後で一般語が
    # ヒットしたときにその不在を名乗る」という設計で、不在の語こそ
    # 先頭に来る必要がある。実測: 大きな値を返すと「飛行機のチケット代
    # は精算できますか」で不在の探査語(飛行機・チケット・代)が最後に
    # 送られ、実在する「精算」が先に試されて不在昇格が起きないまま
    # DOCUMENT_LINE で確定してしまった(3/9 が新たに壊れた)。


def rank_probes(subject: str, terms: List[str], book: Dict[str, Any]) -> List[str]:
    """探査語を、文書内での集中度(特定性)優先で並べる。

    実測 2026-08-18、二つの対立するケースで「AのB は B が主辞」という
    構文規則(主要部後置)だけでは決着がつかないと分かった:

        出張旅費の精算はいつまでに → 主辞は精算。文書内でも精算(1節)は
            出張旅費(2節: 見出しと第2条本文の両方に出る一般語)より集中
            的 — 主辞と集中度が一致し、どちらでも正解に届く

        減給の上限は → 主辞は上限。だが上限は文書内で2節(繰越上限・
            宿泊費の上限)にまたがる一般語で、減給は1節(懲戒)に集中。
            主辞優先だけを採ると「繰越上限は20日とする。」という無関係
            な行を返した — 主辞性と集中度が逆を向いた実例

        書留の料金は → 書留(不在)・料金(1節)。両方とも集中度は測れる
            が、不在昇格の判定(_absent)は別の仕組みで、ここでは触れない

    集中度が本体、主辞性は同点の時だけの補助にした。長さや原文の出現
    位置に頼っていた旧版より、二つの実例の両方が同時に通る。
    """
    def is_modifier(t: str) -> bool:
        i = subject.find(t)
        while i != -1:
            if subject[i + len(t):i + len(t) + 1] == "の":
                return True
            i = subject.find(t, i + 1)
        return False
    key = lambda t: (_section_spread(book, t), is_modifier(t),
                     -len(t), subject.find(t))
    return sorted(terms, key=key)


def _independent_in(probe: str, text: str) -> bool:
    """探査語 probe は text の中で、複合語の一部ではなく独立して立つか。

    実測 2026-08-18、経費精算規程で「飛行機のチケット代は精算できますか」
    に対し、より特定的な探査語(飛行機・チケット・食事代)は文書のどこにも
    無いので順に空振りし、最後に残った探査語「精算」が見出し「第7条
    不正精算」の部分文字列として一致した。「精算」は文書中に4回現れる
    一般語で、「不正精算」の中では「不正」に直接続く複合語の一部 —
    独立した主題ではない。無関係な条文(懲戒)が「精算できますか」の答え
    として返っていた。

    独立とは、text の中で probe の両隣が文字列の端か、内容字でない
    ことを言う。「不正精算」の「精算」は左隣が内容字(正)なので不合格、
    「精算方法」の「精算」も右隣が内容字(方)なので不合格。「経費精算
    規程」全体を探査語として引くのとは違う話 — ここは一片の話。
    """
    i = text.find(probe)
    while i != -1:
        left_ok = i == 0 or not _is_content_char(text[i - 1])
        j = i + len(probe)
        right_ok = j == len(text) or not _is_content_char(text[j])
        if left_ok and right_ok:
            return True
        i = text.find(probe, i + 1)
    return False


#: 助詞は機能語であって内容語ではない。実測 2026-08-18、経費精算規程で
#: 「交通費の上限」の「上限」が「独立していない」と誤判定された —
#: 左隣の「の」がひらがなという理由だけで内容字扱いされていたため。
#: 「不正精算」の「精算」の左隣「正」(漢字)とは事情が違う。「の」を
#: 挟めば A と B は明確に分離可能な構造で、B は独立した主題である。
_PARTICLE_CHARS = frozenset("のはがをにでへとも")


def _is_content_char(c: str) -> bool:
    if c in _PARTICLE_CHARS:
        return False
    return ("一" <= c <= "龥" or "ぁ" <= c <= "ん" or "ァ" <= c <= "ヶ"
            or c == "ー" or c.isalnum())


def _stair_pick(lines: List[str], subject: str) -> Optional[str]:
    """節の中で、問いが実際に指している行。段が一致したときだけ返す。

    見出しに一致すると節が丸ごと返る。それは問いが節そのもののとき
    （「第5条は」）は正しく、一行が答えるときは危ない。実測 2026-08-18、
    就業規則20問で17答のうち6答が節ごとで、最悪の形がこれだった:

        「時間外労働の割増賃金は」→ 第3条の3行
          時間外労働を命じる場合は、事前に所属長の承認を得るものとする。
          時間外労働の割増賃金は、通常賃金の25パーセント増しとする。  ← 答え
          深夜労働の割増賃金は、通常賃金の50パーセント増しとする。    ← 別の問いの答え

    25と50が同じ重さで並び、どちらが問いの答えかを読み手が選ぶ。

    先に手製の数え上げ（問いの語を最も多く含む行）を書いたが、これは誤り
    が二重だった。一つ、測定済みの機構があるのに手で書いた。二つ、直した
    分岐がこれらの問いの通る分岐ではなく、一度も発火せずに測定値が変わら
    なかった — にもかかわらず同じ数字を見て先へ進んだ。

    採るのは concord の階段の規律そのもの:

    * 段は分割ではなく解像度。全段が全行を、自分の粒度で見る
    * 同点の段は棄権する。全段が同点なら全段が同じ最小要素を選ぶので、
      証拠と無関係な一致が作られる（実測 全一致 73.3% → 辞書順で 23.7%、
      3対1 より悪い）
    * 2段以上が答えたうえで全一致したときだけ行を指す。割れたら節のまま

    合算はしない。段は独立に投票し、一致だけが信号になる — 重みを一つの
    数に畳むと、なぜその行かが数字に潰れて追試できなくなる。
    """
    if len(lines) < 2:
        return None
    votes: List[int] = []
    for g in _GRAINS:
        if g == 0:
            probe = set(content_terms(subject))
            units = lambda line: set(content_terms(line))  # noqa: E731
        else:
            probe = _ngrams(subject, g)
            units = lambda line, g=g: _ngrams(line, g)     # noqa: E731
        if not probe:
            continue
        scored = [(len(probe & units(l)), i) for i, l in enumerate(lines)]
        best = max(scored)[0]
        if best == 0:
            continue
        winners = [i for n, i in scored if n == best]
        if len(winners) != 1:
            continue
        votes.append(winners[0])
    if len(votes) < 2 or len(set(votes)) != 1:
        return None
    return lines[votes[0]]


def _doc_vocab(book: Dict[str, Any]) -> set:
    """文書が実際に書いている語だけ。外の辞書は持ち込まない。"""
    v: set = set()
    for d in book.get("documents", []):
        for sec in d.get("sections", []):
            v |= set(content_terms(sec.get("heading") or ""))
            for line in sec.get("lines") or []:
                v |= set(content_terms(line))
        for name, val in (d.get("labels") or {}).items():
            v |= set(content_terms(name)) | set(content_terms(val))
    return {w for w in v if len(w) >= 2}


def typo_hint(book: Dict[str, Any], term: str) -> List[str]:
    """この語は、文書が書いている別の語の打ち損じか。訂正はしない。

    誤字回復は測定済み(回復@5 84.8%、実在語への誤発火 0/500)なのに、
    文書の経路からは一度も呼ばれていなかった。実測 2026-08-18、
    「時間害労働の割増賃金は」は拒否文で「時間害労働」という非語を名指す
    だけで、文書が 時間外労働 を持っていることには触れなかった。

    語彙は文書自身のものに限る。外の辞書を積むと、文書に無い語を「在る」
    側に数えてしまう。3規程133語で 時間害労働→時間外労働、割増賃銀→
    割増賃金、宿泊日→宿泊費 を回復し、実在語4件への誤発火は 0。
    片仮名は位置単位を持たないので棄権する(インシデソト)。

    返すのは候補だけで、問いは書き換えない。どれを意味していたかを決める
    のは読み手であって、この関数ではない。
    """
    try:
        from . import lattice as _lat, typo_recovery as _tr
    except Exception:
        return []
    vocab = book.get("_vocab")
    if vocab is None:
        vocab = _doc_vocab(book)
        try:
            book["_vocab"] = vocab
            book["_lattice"] = _lat.build(vocab)
        except Exception:
            return []
    lat = book.get("_lattice")
    if lat is None or not vocab:
        return []
    try:
        r = _tr.recover(term, lattice=lat, vocab=vocab)
    except Exception:
        return []
    if r.get("verdict") != "TYPO_CANDIDATE":
        return []
    return [c.get("word") for c in (r.get("candidates") or [])[:3] if c.get("word")]


def _title_descent(book: Dict[str, Any], subject: str):
    """題名で文書へ降り、別の語で節へ降りる。二語とも文書自身の言葉。

    棚が一件のうちは要らない。増えた途端に効く — 実測 2026-08-18、3規程・
    7問で「出張の申請はいつまでに」が就業規則の第5条 出張へ降りた。正しい
    文書は出張旅費規程だが、その見出しは 申請/上限/期限 で、出張 はどこにも
    無い。題名にしかない。見出しだけを見る読み手には、文書の名前が見えて
    いなかった。

    conduct_tree を先に当てたが、この規模では移らなかった(7問中5問が
    UNKNOWN_NO_ROUTE)。あれは36法令の連合で測った器官で、核が13〜35しか
    ない文書には伝導の流れる先が無い。検証済みとは「その規模・その形で」
    であって、移送は無料ではない。だからここは器官を持ち込まず、book が
    既に持っている source を経路に載せるだけにしてある。

    二語を要求するのは、題名一致だけで文書を決め打ちしないため。出張 が
    題名に当たっても、節を選ぶ語が別に要る。片方しか無ければ何も返さず、
    従来の順路がそのまま動く。

    実測: 複数文書 6/7 → 7/7、単一文書の回帰 誤答 0。
    """
    terms = content_terms(subject)
    docs = book.get("documents", []) or []

    # 題名そのものを名指した問い(2026-08-19、P4修理)。「多型」に対し
    # 多型.txt が在るなら、その文書がこの問いの主題である — 部分一致の
    # 積み重ねではなく、題名の完全一致という最強の証拠。二語要求は
    # 「題名一致だけで文書を決め打ちしない」ための規律だが、完全一致は
    # 決め打ちではなく同定なので、その規律の対象外。実測(60文書):
    # 「多型」が多型.txt を素通りしてバイオマーカー(医学).txt の本文行に
    # 当たっていた。返すのは絞り込み(_TITLE_SCOPE_ONLY)だけ — 節を選ぶ
    # のは従来の順路で、ここは範囲を狭めるだけに留める。
    q_norm = _norm(subject)
    if q_norm:
        exact = [d for d in docs
                 if _norm(str(d.get("source", "")).rsplit(".", 1)[0]) == q_norm]
        if exact:
            return {"verdict": "_TITLE_SCOPE_ONLY",
                    "sources": [d.get("source") for d in exact],
                    "note": "問いが文書の題名そのもの — この文書の中だけを見る"}

    if len(terms) < 2:
        return None

    matched: List[Tuple[Dict[str, Any], List[str]]] = []
    for doc in docs:
        stem = _norm(str(doc.get("source", "")).rsplit(".", 1)[0])
        if not stem:
            continue
        by_title = [t for t in terms if _norm(t) and _norm(t) in stem]
        if by_title:
            matched.append((doc, by_title))
    if not matched:
        return None

    # 題名一致の強さで並べる(2026-08-19、P4修理)。従来は文書順の最初の
    # 一致がそのまま経路になり、「哲学の庭」が 哲学.txt へ、「ハドロン
    # 物理学」が プロジェクト:物理学.txt へ降りていた(60文書実測 3/30)。
    # 問いをより多く覆う題名の方が良い経路である、というだけの順位づけ —
    # 門ではないので、一致が一件しかない従来の場面では並びは変わらない。
    # 覆う量は「一致した語の文字数の合計」で測る: 語数だけでは
    # ハドロン/ハドロン物理/物理学 のような重なる切片が水増しになる。
    matched.sort(key=lambda m: (-sum(len(_norm(t)) for t in m[1]),
                                -len(m[1]),
                                str(m[0].get("source"))))

    for doc, by_title in matched:
        rest = rank_probes(subject, [t for t in terms if t not in by_title], book)
        # 最優先の探査語(rest[0])が不発なら次を試す — DOCUMENT_MULTI と
        # 同じ「最優先語が複数節に独立着地したら列挙する」規律を、題名で
        # 文書に降りた後にも適用する。実測 2026-08-18: 経費精算規程を
        # 別文書(総務規程)と一緒に読み込むと、「経費の上限は」が
        # ここ(題名降下)で先に確定し、後段の DOCUMENT_MULTI まで処理が
        # 届かず、交通費・宿泊費の上限を聞き逃したまま会議費だけ返した。
        for t in rest:
            pn = _norm(t)
            if not pn:
                continue
            hits: List[Dict[str, Any]] = []
            for sec in doc.get("sections", []):
                head = _norm(sec.get("heading") or "")
                raw_head = sec.get("heading") or ""
                if not head or not sec.get("lines"):
                    continue
                if pn in head and _independent_in(pn, raw_head):
                    lines = list(sec["lines"])
                    one = _stair_pick(lines, subject)
                    hits.append({"section": sec.get("heading"),
                                 "text": one or "\n".join(lines),
                                 "lines": lines, "source": doc.get("source"),
                                 "date": doc.get("date"),
                                 "line": one})
            if not hits:
                continue
            if len(hits) >= 2:
                joined = "\n".join(
                    "[%s%s／%s] %s" % (h["source"],
                                       ("(%s)" % h.get("date")) if h.get("date") else "",
                                       h["section"], h["text"])
                    for h in hits)
                return {"verdict": "DOCUMENT_MULTI", "subject": subject,
                        "items": hits, "text": joined, "quoted": True,
                        "reached_via": "%s→%s" % (by_title[0], t),
                        "note": "題名「%s」に降りた後、「%s」が独立に%d節へ"
                                "当たった。1つに絞らず全部を引用する"
                                % (doc.get("source"), t, len(hits))}
            h = hits[0]
            return {"verdict": "DOCUMENT_LINE" if h["line"] else "DOCUMENT_SECTION",
                    "subject": h["section"],
                    "text": h["text"], "lines": h["lines"],
                    "source": h["source"], "quoted": True,
                    "reached_via": "%s→%s" % (by_title[0], t),
                    "note": "題名「%s」で文書に降り、「%s」で節に降りた"
                            % (doc.get("source"), t)}

        # 見出しには当たらなかった。題名で1文書に絞り込めているのに
        # ここで諦めて後段の全文書検索に処理を渡すと、無関係な——時には
        # 矛盾する——別文書の答えを拾ってしまう。実測 2026-08-18:
        # 「本社のグリーン車は使えますか」は by_title=['本社'] で
        # 本社経費精算規程.txt 一件に正しく絞り込めたが、その文書では
        # グリーン車の定めが見出しではなく「第5条 交通費の上限」の
        # 本文行にしかなく、ここまでは本文行を見ていなかったため
        # None を返し、後段が名古屋支社経費規程.txt(グリーン車を許可する
        # 矛盾した規程)の見出しを拾って誤答した。見出しの次は、この
        # 文書の中だけで本文行も見る——他の文書の本文には触れない。
        for t in rest:
            pn = _norm(t)
            if not pn:
                continue
            line_hits: List[Dict[str, Any]] = []
            for sec in doc.get("sections", []):
                for ln in (sec.get("lines") or []):
                    if pn in ln:
                        line_hits.append({"section": sec.get("heading"),
                                           "text": ln, "source": doc.get("source"),
                                           "date": doc.get("date")})
            if not line_hits:
                continue
            if len(line_hits) >= 2:
                joined = "\n".join(
                    "[%s%s／%s] %s" % (h["source"],
                                       ("(%s)" % h.get("date")) if h.get("date") else "",
                                       h["section"], h["text"])
                    for h in line_hits)
                return {"verdict": "DOCUMENT_MULTI", "subject": subject,
                        "items": line_hits, "text": joined, "quoted": True,
                        "reached_via": "%s→%s" % (by_title[0], t),
                        "note": "題名「%s」に降りた後、「%s」を含む本文行が"
                                "%d件見つかった。1つに絞らず全部を引用する"
                                % (doc.get("source"), t, len(line_hits))}
            h = line_hits[0]
            return {"verdict": "DOCUMENT_LINE", "subject": h["section"],
                    "text": h["text"], "lines": [h["text"]],
                    "source": h["source"], "quoted": True,
                    "reached_via": "%s→%s" % (by_title[0], t),
                    "note": "題名「%s」で文書に降り、本文行で「%s」に当たった"
                            % (doc.get("source"), t)}

    # 題名で名指しされた文書(たち)の、見出しにも本文行にも当たらなかった。
    # ここで DOCUMENT_NOT_SPECIFIED_IN_TITLE のような固有の型を返して
    # 打ち切ると、単一文書の時から使ってきた「明記なしの型」(governing
    # 文・誤字候補つき、絶対不在の昇格)を素通りさせてしまう — 実測
    # 2026-08-18: 経費精算規程.txt 一件だけの場面で「精算」が題名にも
    # 当たるため、以前は _lookup 本体の absence-promotion まで届いて
    # いた「3万円の食事代は精算できますか」が、ここで素っ気ない拒否に
    # 化けて後退した。答えを返すのではなく、探す範囲だけをこの文書
    # (たち)に絞って呼び出し元(_lookup)へ渡す — 未指名の文書へは
    # 渡さないという規律は保ったまま、既存の型は生かす。
    sources = [d.get("source") for d, _ in matched]
    return {"verdict": "_TITLE_SCOPE_ONLY", "sources": sources,
            "by_title": matched[0][1]}


_ARTICLE_RE = re.compile(r"^第\s*[0-9０-９一二三四五六七八九十百]+\s*[条章節項編款]\s*(.*)$")


def _heading_only(heading: str) -> str:
    """「第2条 交通費の上限」→「交通費の上限」。条番号は監査に要らない。"""
    m = _ARTICLE_RE.match(heading or "")
    return (m.group(1).strip() if m and m.group(1).strip() else heading or "")


def _reference_summary(result: Dict[str, Any]) -> Optional[str]:
    """引用の隣に添える、見出しだけの構成的要約。新しい語は一切作らない。

    実測 2026-08-18: 一般知識のWriter(jawiki由来の文型)を文書の内容語に
    流用したら、「精算は、グリーンをグリーン車さない。」「精算は、グリーン
    （がいしょくほう）である。」という意味不明・汚染混じりの文が出た —
    文書モードの大原則(文書に無いことは答えない)に反する危険な結果。

    安全なのは、見出し(条項名)をそのまま繋ぐことだけ。DOCUMENT_MULTI
    (経費の上限は→交通費/会議費/宿泊費の3件)を「〜についてそれぞれ
    定めがあります」と目次化する。単一の答えには、根拠の節名を
    「この定めは〜にあります」と添える。どちらも文書自身の見出し文字列
    以外の語を一つも使わない。
    """
    verdict = result.get("verdict")
    if verdict == "DOCUMENT_MULTI":
        heads = [_heading_only(it.get("section") or "")
                 for it in (result.get("items") or [])]
        heads = [h for h in heads if h]
        if heads:
            return "、".join(heads) + "についてそれぞれ定めがあります。"
    elif verdict in ("DOCUMENT_LINE", "DOCUMENT_SECTION"):
        # section(節見出し)を優先する。subject は本文行への直接マッチ
        # (605行目以降、探査語そのもの)のときは節見出しではなく探査語
        # そのもの("グリーン")が入る — 実測、それを見出しと誤認して
        # 「この定めは「グリーン」にあります」という不完全な参考文に
        # なった。DOCUMENT_SECTION 側は section を持たず subject に
        # 見出しを持つので、両方を順に試す。
        #
        # ただし section キーが存在してなお空文字列(見出しの無い節 —
        # 会話ログのような無見出し文書の本文行ヒット)なら、それは
        # 「見出しが無いと分かっている」という事実そのもので、subject
        # へは逃げない。逃げると subject には探査語(質問の主題そのもの)
        # が入っており、「この定めは「verantyx」にあります」のような、
        # 問いをそのまま繰り返すだけの空虚な参考文になる — 実測
        # 2026-08-19、見出し検出が直った後の会話ログ文書で発見。
        # section キーが無い(DOCUMENT_SECTION の3つの返し口はどれも
        # section を持たない)場合はこれまで通り subject を見出しとして
        # 使う — そちらの subject は探査語ではなく本物の見出しだから。
        if "section" in result and not result.get("section"):
            return None
        head = _heading_only(str(result.get("section") or
                                  result.get("subject") or ""))
        if head:
            return "この定めは「%s」にあります。" % head
    return None


_DEF_EDGES: Optional[Dict[str, List[str]]] = None


def _def_edges() -> Dict[str, List[str]]:
    """辞書辺(2026-08-19、experiments/def_edges)。jawiki 1,419,406定義文
    から、二重ライセンス(漢字の区切りを共有 ∧ 異なる定義文で2回以上
    同一文共起)で収穫した語→隣語。欠点↔弱点 の類。順位づけ・経路にだけ
    使い、票と本文には入れない(jgen辞書実験: 順位可・主張54.8%不可)。"""
    global _DEF_EDGES
    if _DEF_EDGES is None:
        p = corpus_root() / "build" / "def_edges.json"
        try:
            _DEF_EDGES = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _DEF_EDGES = {}
    return _DEF_EDGES


def lookup(subject: str, book: Dict[str, Any]) -> Dict[str, Any]:
    """``_lookup`` に見出しベースの参考要約(reference)を重ねた薄い皮。

    証拠(verdict/text)は _lookup がそのまま持つ。reference は見出しの
    並びだけで作る構成的な文で、新しい主張は一つも含まない —
    constructed:True を付け、証言と混同させない。
    """
    # 接続中の文書だけ・優先度順のビュー(2026-08-19)。「外す」は削除では
    # なく切断 — 一度取り込んだ文書は detached:True で残り、attach で
    # 戻る。priority は高いほど先に照合される(企業の複数文書で「これを
    # 優先して判断」の配線)。原本 book は変更しない。
    # 時系列: 同優先度なら日付の新しい文書から照合する(date降順、無日付は
    # 最後)。時間的上書き(「Xが欠点」→後日「X修理済み」)を、削除ではなく
    # 並び順で表す — 古い記述は残り、引用には日付が付く。
    # 安定3段(全て票の外): 名前順 → 日付降順(ISO文字列、無日付は最後)
    # → 優先度降順。Pythonの安定ソートで後段が前段の同点を保つ。
    active = sorted(
        [d for d in book.get("documents", []) if not d.get("detached")],
        key=lambda d: str(d.get("source")))
    active.sort(key=lambda d: (str(d.get("date") or "") == "",
                               str(d.get("date") or "")),)
    active[:] = sorted(
        [d for d in active if d.get("date")],
        key=lambda d: str(d.get("date")), reverse=True,
    ) + [d for d in active if not d.get("date")]
    active.sort(key=lambda d: -int(d.get("priority") or 0))
    book = {**book, "documents": active}
    result = _lookup(subject, book)
    # 辞書辺の後退(2026-08-19、experiments/def_edges)。明記なし・不在が
    # 確定した後でだけ動く: 不在語の辞書隣語(欠点→弱点)が文書に実在する
    # なら、その引用を**置換を名乗って**返す。主題取りこぼし門(賢者の石)
    # の後ろの席なので、複合語不在はここに来ても隣語を持たず不変。
    if result.get("verdict") in ("DOCUMENT_NOT_SPECIFIED",
                                 "UNKNOWN_NOT_IN_DOCUMENTS"):
        absent = str(result.get("subject") or "").strip()
        for partner in (_def_edges().get(absent) or [])[:4]:
            # 置換形(veraの弱点)が題名絞り込み等で落ちる場合に備え、
            # 裸の隣語でも引く — どちらも同じ門を全て通る。
            _qs = []
            if absent and absent in subject:
                _qs.append(subject.replace(absent, partner))
            _qs.append(partner)
            r2 = None
            for q2 in _qs:
                _r = _lookup(q2, book)
                if str(_r.get("verdict") or "").startswith("DOCUMENT") and \
                        _r.get("verdict") != "DOCUMENT_NOT_SPECIFIED":
                    r2 = _r
                    break
            if r2 is not None:
                r2 = dict(r2)
                r2["substituted"] = {"asked": absent, "used": partner,
                                     "licence": "def_edge"}
                r2["reached_via"] = "%s→辞書辺→%s" % (absent, partner)
                r2["note"] = ("「%s」の記載は無い。辞書の定義文で繰り返し"
                              "並記される隣語「%s」の記載を引用する — "
                              "同義の主張ではなく、辺の隣という実測。%s"
                              % (absent, partner, r2.get("note") or ""))
                result = r2
                break
    if result.get("source"):
        for d in active:
            if d.get("source") == result.get("source") and d.get("date"):
                result["source_date"] = d.get("date")
                break
    ref = _reference_summary(result)
    if ref:
        result["reference"] = ref
        result["reference_constructed"] = True
    # 引用が立った節の辺(行内共起)を注釈として添える。判定は変えない。
    if result.get("verdict") in ("DOCUMENT_LINE", "DOCUMENT_SECTION"):
        sec_name = str(result.get("section") or result.get("subject") or "")
        for doc in book.get("documents", []):
            if result.get("source") and doc.get("source") != result.get("source"):
                continue
            for sec in doc.get("sections", []):
                if sec.get("heading") == sec_name and sec.get("edges"):
                    result["edge_pairs"] = sec["edges"][:16]
                    break
    return result


def _lookup(subject: str, book: Dict[str, Any]) -> Dict[str, Any]:
    """What the loaded documents say about this subject, verbatim.

    Labels are consulted before headings: 「提出期限」 is a labelled value
    in one document and would otherwise be answered by whatever section
    happens to contain the word.
    """
    q = _norm(subject)
    if not q:
        return {"verdict": "UNKNOWN_NO_SUBJECT"}

    for doc in book.get("documents", []):
        for name, value in (doc.get("labels") or {}).items():
            if _norm(name) == q:
                return {"verdict": "DOCUMENT_LABEL", "subject": name,
                        "text": "%s: %s" % (name, value),
                        "value": value, "source": doc.get("source"),
                        "quoted": True,
                        "note": "文書の記載をそのまま引用。要約も推論もしていない"}

    # Exact heading, then a heading that contains the subject. Containment
    # is second so 「必須要件」 cannot be taken by 「必須要件を満たす場合」
    # while an exact heading for it exists.
    for exact in (True, False):
        for doc in book.get("documents", []):
            for sec in doc.get("sections", []):
                h = _norm(sec.get("heading", ""))
                if not h:
                    continue
                hit = (h == q) if exact else (q in h)
                if not hit:
                    continue
                lines = list(sec.get("lines") or [])
                if not lines:
                    # A heading with nothing under it. Assembling an
                    # answer from neighbouring text would be inventing a
                    # section the document does not have.
                    return {"verdict": "UNKNOWN_NO_ITEMS",
                            "subject": sec.get("heading"),
                            "source": doc.get("source"),
                            "note": "見出しはあるが、その下に記載が無い"}
                one = _stair_pick(lines, subject)
                if one is not None:
                    return {"verdict": "DOCUMENT_LINE",
                            "subject": sec.get("heading"),
                            "text": one,
                            "section": sec.get("heading"),
                            "source": doc.get("source"),
                            "quoted": True,
                            "note": "節の中で、問いの語を最も多く含む行。"
                                    "同数の行があれば節のまま返す"}
                return {"verdict": "DOCUMENT_SECTION",
                        "subject": sec.get("heading"),
                        "text": "\n".join(lines),
                        "lines": lines,
                        "ordinal": sec.get("ordinal"),
                        "source": doc.get("source"),
                        "quoted": True,
                        "note": "文書の該当節をそのまま引用。並び順は原文のまま"}
    # 棚が複数になった時点で、文書の名前が経路の一部になる。
    descended = _title_descent(book, subject)
    if descended is not None:
        if descended.get("verdict") == "_TITLE_SCOPE_ONLY":
            # 題名で1文書(たち)に絞り込めたが、その中に答えは無かった。
            # ここで諦めて未指名の文書へ処理を渡すと、矛盾する別文書の
            # 答えを拾ってしまう(実測 2026-08-18: 「本社のグリーン車は
            # 使えますか」が名古屋支社経費規程.txtの答えを返した)。
            # 以降の後退段(0〜3)は既存のまま——ただし探す範囲を、この
            # 題名で絞り込んだ文書だけに narrow する。文書が元々1件しか
            # 無い場面では絞り込み後も同じ1件のままなので、単一文書の
            # 挙動は変わらない。
            scope = set(descended.get("sources") or [])
            book = {"documents": [d for d in book.get("documents", [])
                                   if d.get("source") in scope]}
        else:
            return descended

    # ── ここから後退。すべて閉じた規則で、置換は必ず名乗る ──────────────
    #
    # Measured 2026-08-18 on a company-regulation probe: 「宿泊費の上限は」
    # fell through — 宿泊費 is a line under the 精算上限 heading, not a
    # heading itself — and 「グリーン車は使えますか」 has no heading at all,
    # yet the honest answer exists in the document: the governing section,
    # plus the checkable fact that the term is never mentioned. An engine
    # whose claim is "the document's own words or a typed refusal" owes
    # exactly those two shapes, and owed them since 2026-08-16, when
    # 「指定された要件は」 was recorded as the modified-noun-phrase hole.

    from .lang import ja_content_runs
    import re as _re

    # 探査語。ja_content_runs は文字種境界で割る（グリーン車 → グリーン+車）
    # ので、複合語の形も原文から直接拾う。閉じた2形だけ:
    # カタカナ/ラテン+漢字尾（グリーン車・エコノミークラス）と漢字連。
    cand = set(ja_content_runs(subject))
    cand |= {m.group(0) for m in _re.finditer(r"[ァ-ヶーA-Za-z0-9]+[一-龥]{0,2}", subject)}
    cand |= {m.group(0) for m in _re.finditer(r"[一-龥]{2,}", subject)}
    # ひらがなの内容語（はがき・きっぷ）。ja_content_runs は機能語を避ける
    # ためにひらがな連を捨てるが、主題の位置に立つ3字以上は内容語である
    # ことが多い。閉じた除外集合だけを引く。
    _HIRA_STOP = {"について", "ください", "ですか", "でしょう", "および",
                  "または", "ならびに", "こんにちは", "ありがとう"}
    # 疑問語で始まる連は問いの側であって主題ではない。実測: 「申出はいつ
    # までに」が探査語「はいつま」を作り、拒否文がその非語を名指した。
    _HIRA_ASK = ("いつ", "どこ", "どの", "どう", "どちら", "どれ",
                 "なに", "なぜ", "いく", "だれ")
    for m in _re.finditer(r"[ぁ-ん]{3,}", subject):
        run = m.group(0)
        # 内容字（漢字・カタカナ・ラテン）の直後に立つ先頭のひらがなは、
        # その語に付いた助詞である。文頭の「はがき」の は とは違う —
        # 位置がその二つを分ける。
        if m.start() > 0 and not ("ぁ" <= subject[m.start() - 1] <= "ん") \
           and run[0] in "のはがをにでへとも":
            run = run[1:]
        # 末尾の助詞を剥がす（はがきの → はがき）。主題位置のひらがな連は
        # 助詞まで一続きで取れてしまう。
        while len(run) > 3 and run[-1] in "のはがをにでへとも":
            run = run[:-1]
        if len(run) < 3:
            continue
        # 動詞語尾で終わる連（された・している）は形態であって主題ではない
        if run[-1] in "たてる":
            continue
        # ひらがなだけで か に終わる連は問いの尾（できますか・でしょうか）。
        if run[-1] == "か":
            continue
        if run.startswith(_HIRA_ASK):
            continue
        if run not in _HIRA_STOP:
            cand.add(run)
    probes: List[str] = []
    for run in rank_probes(subject, sorted(cand, key=lambda r: (-len(r), subject.find(r))), book):
        # 主題自身も探査語に含める。以前は _norm(run) != q で除外して
        # いた — 完全一致の段が先に引いたから、という理由だが、その段が
        # 引くのはラベルと見出しだけで、行は一度も主題そのもので引かれて
        # いなかった。実測 2026-08-18: lookup("繰越上限は") は行に届き、
        # lookup("繰越上限") は UNKNOWN。engine は助詞を剥いでから引く
        # ので、裸の名詞主題が全部この穴に落ちていた。問い形の主題は
        # どの run とも一致しない(qに助詞が残る)ので、この変更は裸形
        # だけに効く。
        if len(run) >= 2:
            probes.append(run)

    # 不在の昇格: 最も特定的な探査語が文書のどこにも無いなら、より汎用の
    # 語の行で「答えたふり」をしてはならない。グリーン車で入れた型の一般化 —
    # 「書留の料金は」に対し、書留の不在を名乗った上で料金の定めを支配則
    # として引用する。不在は部分文字列検査で追試できる。
    _all_text = "\n".join(
        "\n".join(ln for sec in doc.get("sections", []) for ln in (sec.get("lines") or []))
        + "\n" + "\n".join("%s %s" % (k, v) for k, v in (doc.get("labels") or {}).items())
        + "\n" + "\n".join(sec.get("heading", "") for sec in doc.get("sections", []))
        for doc in book.get("documents", []))
    _absent = {pr for pr in probes if pr not in _all_text}

    # 主題の取りこぼし検査(2026-08-19、60文書スケール実測)。「賢者の石」は
    # 石(1字)が探査語になれず probes=[賢者] だけになり、どの文書かの
    # 「賢者」を含む行が DOCUMENT_LINE で立った — 聞かれていない物の行で
    # 聞かれた物に答える捏造(書留/料金と同型)だが、不在の昇格は探査語
    # 同士でしか働かなかった。探査語に覆われない内容字が主題に残るなら、
    # 主題そのものが「最も特定的で不在の語」である。
    _content_c = _re.compile(r"[一-龥ァ-ヶーA-Za-z0-9]")
    _cover = "".join(probes)
    _uncovered = [c for c in q if _content_c.match(c) and c not in _cover]
    _subject_absent = bool(_uncovered) and q not in _all_text

    # 0. 複数根拠: 最優先の探査語が独立に複数の節へ着地するなら、
    # 単一に絞らず全部を列挙する。
    #
    # 実測 2026-08-18: 「経費の上限は」の探査語は 上限(spread3)・経費
    # (spread3) — 同点で、そもそも単一の探査語では絞り込めない状況。
    # 「上限」は交通費・会議費・宿泊費の3節に均等に独立ヒットする。
    # 従来はここで1.ループが最初にヒットした節(会議費)を勝手に選び、
    # 「経費の上限は」に「1人あたり5,000円」とだけ答えていた — 読み手は
    # 交通費・宿泊費の上限を聞き逃したことにさえ気づけない。
    #
    # 同点は棄権、が_stair_pickの規律だったが、ここでの「棄権」は
    # 「答えない」ではなく「1つに絞らず全部見せる」の方が読み手の役に
    # 立つ。列挙は捏造ではない — 見つかった節をそのまま並べるだけ。
    if probes:
        top = probes[0]
        pn0 = _norm(top)
        if pn0:
            hits: List[Dict[str, Any]] = []
            hit_docs: set = set()
            for doc in book.get("documents", []):
                for sec in doc.get("sections", []):
                    raw_head = sec.get("heading", "") or ""
                    head = _norm(raw_head)
                    if head and pn0 in head and sec.get("lines") \
                            and _independent_in(pn0, raw_head):
                        lines = list(sec.get("lines") or [])
                        one = _stair_pick(lines, subject)
                        hits.append({"section": sec.get("heading"),
                                     "text": one or "\n".join(lines),
                                     "source": doc.get("source"),
                                     "date": doc.get("date")})
                        hit_docs.add(doc.get("source"))
            # 見出しに一件も当たらなかった文書にも、本文行にしか書いて
            # いない矛盾する定めがあり得る。見出しだけを比べると、その
            # 文書は最初から候補にすら入らず、矛盾を見落として片方だけを
            # 答えてしまう。実測 2026-08-18:「グリーン車は使えますか」
            # — 名古屋支社経費規程.txtは見出し「第4条 グリーン車」で
            # 許可するが、本社経費精算規程.txtは同じ語を「第5条 交通費の
            # 上限」の本文行で禁じる。見出しに無い文書を1文書1件までの
            # 補完で拾い、既存の節ごと列挙(見出し側)は壊さない。
            #
            # ただし、見出し側に候補が1件も無いなら、この補完は動かさ
            # ない。実測 2026-08-18(corp2/5類似文書):「宿泊費の上限は」
            # は見出しに1件も独立着地せず、この補完だけが動いて
            # 経費精算規程.txtの「対象経費に宿泊費を含む」という無関係な
            # 行まで候補に混ぜ、単一の正しい答え(出張旅費規程.txt)を
            # 無意味な列挙に変えて後退させた。本文行の補完は「見出しで
            # 見つかった矛盾に、もう一件の文書を足す」安全網であって、
            # 候補をゼロから作る役ではない。
            if hits:
                for doc in book.get("documents", []):
                    if doc.get("source") in hit_docs:
                        continue
                    found = False
                    for sec in doc.get("sections", []):
                        for ln in (sec.get("lines") or []):
                            if pn0 in ln:
                                hits.append({"section": sec.get("heading"),
                                             "text": ln, "source": doc.get("source")})
                                hit_docs.add(doc.get("source"))
                                found = True
                                break
                    if found:
                        break
            if len(hits) >= 2:
                joined = "\n".join(
                    "[%s%s／%s] %s" % (h["source"],
                                       ("(%s)" % h.get("date")) if h.get("date") else "",
                                       h["section"], h["text"])
                    for h in hits)
                return {"verdict": "DOCUMENT_MULTI",
                        "subject": subject,
                        "reached_via": top,
                        "items": hits,
                        "text": joined,
                        "quoted": True,
                        "note": "「%s」が独立に%d節へ当たった。1つに絞らず"
                                "全部を引用する" % (top, len(hits))}

    # 1. 内容語で、ラベル→見出し→本文行の順に照合（主辞抽出を包含する形）
    for _pi, probe in enumerate(probes):
        pn = _norm(probe)
        for doc in book.get("documents", []):
            for name, value in (doc.get("labels") or {}).items():
                if _norm(name) == pn:
                    return {"verdict": "DOCUMENT_LABEL", "subject": name,
                            "text": "%s: %s" % (name, value), "value": value,
                            "source": doc.get("source"), "quoted": True,
                            "reached_via": probe,
                            "note": "「%s」の記載は無いが、内容語「%s」がラベルに一致。引用のみ"
                                    % (subject, probe)}
            for sec in doc.get("sections", []):
                head = _norm(sec.get("heading", ""))
                # 独立性は空白を保持した元の見出しで判定する。_norm は
                # PDFの余分な空白を吸収するために全空白を消すが、それは
                # 「第5条 交通費の上限」の条番号とタイトルの間という
                # "意味のある区切り" も一緒に消していた。実測: 独立性を
                # 正規化後の head に対して判定すると「第5条」の右隣が
                # 「交」(内容字)に見えて不合格になり、正しい節到達
                # (第5条は)まで巻き添えで壊れた。空白を残した見出しで
                # 見れば、区切りは区切りのまま残る。
                raw_head = sec.get("heading", "") or ""
                if pn and pn in head and sec.get("lines") \
                        and _independent_in(pn, raw_head):
                    one = _stair_pick(list(sec.get("lines") or []), subject)
                    if one is not None:
                        return {"verdict": "DOCUMENT_LINE",
                                "subject": sec.get("heading"),
                                "text": one, "section": sec.get("heading"),
                                "source": doc.get("source"), "quoted": True,
                                "reached_via": probe,
                                "note": "内容語「%s」で見出しに到達し、節の中で"
                                        "全段が一致した行。割れれば節のまま返す"
                                        % probe}
                    return {"verdict": "DOCUMENT_SECTION",
                            "subject": sec.get("heading"),
                            "text": "\n".join(sec.get("lines") or []),
                            "lines": list(sec.get("lines") or []),
                            "source": doc.get("source"), "quoted": True,
                            "reached_via": probe,
                            "note": "内容語「%s」で見出しに到達。該当節をそのまま引用" % probe}
        # 2. 本文の行そのもの。行は文書の最小の定めで、引用に要約は要らない
        for doc in book.get("documents", []):
            for sec in doc.get("sections", []):
                hit = [ln for ln in (sec.get("lines") or []) if probe in ln]
                _earlier_absent = [probes[j] for j in range(_pi)
                                   if probes[j] in _absent]
                if hit and _earlier_absent:
                    # 特定語（書留）は不在で、汎用語（料金）だけが当たった。
                    # 汎用の行を答えとして出せば、聞かれていない物の値段で
                    # 聞かれた物に答える捏造になる。
                    return {"verdict": "DOCUMENT_NOT_SPECIFIED",
                            "subject": _earlier_absent[0],
                            "section": sec.get("heading"),
                            "term_absent": True,
                            "governing": hit[:3],
                            "source": doc.get("source"), "quoted": True,
                            "text": "文書は「%s」を明記していない。「%s」の定め（%s）: %s"
                                    % (_earlier_absent[0], probe,
                                       sec.get("heading"), " / ".join(hit[:3])),
                            "typo_candidates": typo_hint(book, _earlier_absent[0]),
                            "note": "不在は部分文字列検査で追試可能。近い語の定めを"
                                    "引用しただけで、「%s」の答えではない" % _earlier_absent[0]}
                if hit and _subject_absent:
                    # 主題(賢者の石)自体は文書のどこにも無く、覆えた部分
                    # (賢者)の行しか無い — 行を答えに立てず明記なしを名乗る。
                    return {"verdict": "DOCUMENT_NOT_SPECIFIED",
                            "subject": subject,
                            "section": sec.get("heading"),
                            "term_absent": True,
                            "governing": hit[:3],
                            "source": doc.get("source"), "quoted": True,
                            "text": "文書は「%s」を明記していない。「%s」の定め（%s）: %s"
                                    % (subject, probe,
                                       sec.get("heading"), " / ".join(hit[:3])),
                            "typo_candidates": typo_hint(book, subject),
                            "note": "不在は部分文字列検査で追試可能。近い語の行を"
                                    "引用しただけで、「%s」の答えではない" % subject}
                if hit:
                    return {"verdict": "DOCUMENT_LINE",
                            "subject": probe,
                            "section": sec.get("heading"),
                            "text": "\n".join(hit),
                            "lines": hit,
                            "source": doc.get("source"), "quoted": True,
                            "note": "「%s」を含む行をそのまま引用（節: %s）"
                                    % (probe, sec.get("heading"))}

    # 3. 明記なしの型。語そのものは文書のどこにも無い（部分文字列検査 —
    #    機械で追試できる主張）が、文字種境界の尾単位（グリーン車→車）を
    #    共有する定めがあるなら、それが「最も近い定め」。可否は言わない —
    #    沈黙の判定と、支配する条文の引用だけが、この構造に言える全部です。
    tails: List[str] = []
    for probe in probes or [q]:
        m = _re.search(r"[ァ-ヶーA-Za-z]+([一-龥]{1,2})$", probe)
        if m:
            tails.append(m.group(1))
    for tail in tails:
        for doc in book.get("documents", []):
            for sec in doc.get("sections", []):
                hit = [ln for ln in (sec.get("lines") or []) if tail in ln]
                if hit:
                    term = probes[0] if probes else subject
                    return {"verdict": "DOCUMENT_NOT_SPECIFIED",
                            "subject": term,
                            "section": sec.get("heading"),
                            "term_absent": True,
                            "governing": hit,
                            "source": doc.get("source"), "quoted": True,
                            "text": "文書は「%s」を明記していない。最も近い定め（%s）: %s"
                                    % (term, sec.get("heading"), " / ".join(hit)),
                            "note": "不在は部分文字列検査で追試可能。可否の判断はしていない — "
                                    "明記が無いという事実と、支配する定めの引用のみ"}

    # 最終の型付き沈黙にも誤字候補を添える。実測: 「経比精算とは」
    # (経費精算の誤字)は、不在昇格の対象になる行が無いのでここまで
    # 落ちてきて、以前は候補なしの沈黙だった。文書自身の語彙で候補が
    # 引ければ添える — 訂正はしない、答えたことにもしない。
    # subject そのもの("経比精算とは")ではなく、探査語(内容語だけを
    # 切り出したもの)を渡す。lattice は助詞付きの生文では回復できない。
    hint: List[str] = []
    for pr in probes:
        hint = typo_hint(book, pr)
        if hint:
            break
    out = {"verdict": "UNKNOWN_NOT_IN_DOCUMENTS", "subject": subject}
    if hint:
        out["typo_candidates"] = hint
    return out


#: WITHDRAWN 2026-08-17 — kept only so the failure is legible. Do not
#: wire this in. See docs/PREREGISTERED_2026-08-17_lexicon_heading_alias.md:
#: the floor was derived from twenty single-WORD negative controls and
#: measured against them, and it holds for words. People type SENTENCES,
#: and a sentence's token average drifts toward a document's general
#: vector: 29 of 50 commonsense questions crossed the floor and were
#: answered with a section of a contest PDF. 「氷は冷たいですか」 returned
#: 「原則として、授業で利用した以下の環境を用いて…Python, Flask」.
#:
#: The stop condition named exactly this and forbids a second threshold,
#: a margin term, or a bigger lexicon. It is honoured.
#:
#: The floor a proposed heading must clear. Pre-registered
#: 2026-08-17 as the smallest value that refuses all twenty declared
#: negative controls on the fit document, and confirmed on a held-out
#: document where the highest nonsense score was 0.348. It is a property
#: of THIS lexicon: swap the table and it must be re-derived, because a
#: floor carried over from another model is a number with no measurement
#: behind it.
ALIAS_FLOOR = 0.42


def propose_heading(subject: str, book: Dict[str, Any],
                    lex: Any, floor: float = ALIAS_FLOOR) -> Optional[str]:
    """A heading the loaded documents hold that this subject may mean.

    The dictionary PROPOSES; `lookup` still decides. It may only name a
    heading the index already contains, so the worst it can do is send the
    reader to the wrong section of a real document — never to a section
    that does not exist. Measured on a held-out document: 4 of 8
    paraphrases reached their heading, 4 were refused, 0 went wrong.

    A ranking read of a static embed table. No generation, no sampling —
    0-4 ms and byte-identical across runs, so determinism survives. The
    same table's POLARITY is forbidden (54.8%, a coin flip, measured
    2026-08-08) and is not touched here.
    """
    if lex is None or not subject.strip():
        return None
    keys: List[str] = []
    for doc in book.get("documents", []):
        keys.extend(str(sec.get("heading")) for sec in doc.get("sections", [])
                    if sec.get("heading"))
        keys.extend(str(k) for k in (doc.get("labels") or {}))
    if not keys:
        return None
    try:
        hits = lex.nearest(subject, keys, k=1)
    except Exception:
        return None
    if hits and hits[0][1] >= floor:
        return hits[0][0]
    return None


def verify_quoted(result: Dict[str, Any], text: str) -> bool:
    """Every emitted line is a substring of the source, or this fails.

    The mechanical check the pre-registration puts the whole mechanism on:
    a sentence naming a requirement the document does not contain is worse
    than the index it replaces.
    """
    flat = _norm(text)
    for line in (result.get("lines") or []):
        if _norm(line) not in flat:
            return False
    v = result.get("value")
    return not (v and _norm(v) not in flat)
