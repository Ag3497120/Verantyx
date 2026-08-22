"""Files in, `Document`s out — with a typed refusal when a format is beyond us.

`ingest_documents` takes text. Getting text out of the things people actually
have — a PDF from a city office, a .docx circular, an exported CSV — is a
separate job, and one where guessing is expensive: a loader that silently
returns an empty string produces a knowledge base that looks ingested and
holds nothing.

So every loader either returns text or says why it could not, and
`load_path` reports `UNKNOWN_NO_PARSER` / `UNKNOWN_UNREADABLE` rather than an
empty `Document`. An empty document is indistinguishable from a document that
genuinely said nothing, and those need opposite responses.

Formats, and what each costs:

    .txt .md .log     stdlib
    .html .htm        stdlib (html.parser)
    .csv .tsv         stdlib — each row becomes a sentence
    .json             stdlib — leaf strings, path-prefixed
    .docx             stdlib — a .docx is a zip of XML, so no dependency
    .pdf              needs the `docs` extra (pypdf); refuses by name without it

The .docx path is worth stating plainly because it looks like it should need
a library: Word documents are zip archives whose word/document.xml holds the
text, so zipfile and ElementTree are enough. PDF has no such shortcut — the
text is inside a compressed content stream with its own encoding — which is
why it is the one format that costs a dependency.
"""
from __future__ import annotations

import csv
import importlib.util
import unicodedata
import io
import json
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional

from .document_ingest import Document

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".log", ".rst"}
SUPPORTED = TEXT_SUFFIXES | {".html", ".htm", ".csv", ".tsv", ".json",
                             ".docx", ".pdf"}


class _TextExtractor(HTMLParser):
    """Body prose only — separated from navigation by what the text IS.

    Two structural attempts failed on real government pages, each for its
    own reason, and two failures from different causes are evidence the
    approach is wrong rather than unlucky. Counting nesting broke on void
    elements (<br> incremented and never decremented); counting same-named
    tags broke on the mismatched <div>s that real pages ship. Both assumed
    well-formed markup, which the web does not supply.

    So the distinction is drawn on the text instead, using the property that
    actually separates the two: navigation is link labels — short, no
    sentence-ending punctuation, and inside <a>. Body prose is sentences.
    Neither test can be defeated by malformed HTML, because neither reads
    the tree.

    Measured on five real 内閣府 pages: 「サイトマップ」「English」「内閣府
    ホーム」 drop out, and the paragraphs about 指定緊急避難場所 and
    プッシュ型支援 stay.
    """

    _SKIP = {"script", "style", "noscript", "head", "select", "option", "svg"}

    #: A line is prose if it ends like a sentence, or is long enough that it
    #: cannot be a menu label. Both thresholds are script-aware: Japanese
    #: carries far more meaning per character, so the length bar is lower.
    _SENTENCE_END = ("。", "．", ".", "！", "!", "？", "?", "」", "）", ")")
    _MIN_PROSE_CJK = 16
    _MIN_PROSE_LATIN = 40

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip = 0
        self._in_link = 0
        # A table ROW is the unit, not a cell. Each <td> arrives as its own
        # text node, so 熊本市's closure table gave 「7/28(火)～7/31(金) ※8/1
        # ～開館」 and 「熊本市職業訓練センター」 as separate fragments — the
        # state with no subject and the subject with no state, 244 rows of
        # them. The PDF path learned this from 内閣府's damage tables; HTML
        # needed it for exactly the same reason.
        self._row: List[str] = []
        self._in_row = 0
        self._subject_col: Optional[int] = None

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self._SKIP:
            self._skip += 1
        elif tag == "a":
            self._in_link += 1
        elif tag == "tr":
            self._flush_row()
            self._in_row = 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag == "a" and self._in_link:
            self._in_link -= 1
        elif tag == "tr":
            self._flush_row()
        elif tag == "table":
            self._flush_row()

    #: Column headers that name the row's subject. A Japanese table is read
    #: head-final by the rule downstream — the state belongs to the noun
    #: BEFORE it — but an HTML table's column ORDER is set by whoever built
    #: the page, and 熊本市 puts 閉鎖期間 before 施設名. The header row says
    #: which column is which, so the subject column is moved to the front and
    #: the row then reads the way every other row in this codebase does.
    _SUBJECT_HEADERS = ("施設名", "名称", "場所", "市町村", "自治体", "路線",
                        "事業者", "会場", "窓口", "地区", "地域", "対象")

    def _flush_row(self) -> None:
        """Emit the cells collected so far as one line.

        Joined with a space, which is what the tabular reader downstream
        already treats as a column boundary — so an HTML row and a PDF row
        arrive in the same shape and are read by the same rule.
        """
        self._in_row = 0
        if not self._row:
            return
        cells, self._row = self._row, []

        # A header row is remembered rather than emitted: it names nothing,
        # and downstream it would look like a claim with no value.
        idx = next((i for i, c in enumerate(cells)
                    if c.strip() in self._SUBJECT_HEADERS), None)
        if idx is not None:
            self._subject_col = idx
            return

        col = getattr(self, "_subject_col", None)
        if col is not None and col < len(cells) and col != 0:
            cells = [cells[col]] + [c for i, c in enumerate(cells) if i != col]

        row = " ".join(cells)
        if len(row) >= 4:
            self.parts.append(row)

    def _is_prose(self, text: str) -> bool:
        if text.endswith(self._SENTENCE_END):
            return True
        floor = (self._MIN_PROSE_CJK if re.search(r"[぀-ヿ㐀-䶿一-鿿]", text)
                 else self._MIN_PROSE_LATIN)
        return len(text) >= floor

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text or self._skip:
            return
        # Link text is a label until proven otherwise. A link whose text is a
        # whole sentence is a real sentence and is kept; 「サイトマップ」 is not.
        if self._in_link and not text.endswith(self._SENTENCE_END):
            return
        if self._in_row:
            # Inside a row every cell is kept, prose-like or not: a facility
            # name and a date are both short and neither ends in 。, and it is
            # the ROW that carries the claim.
            self._row.append(text)
            return
        if self._is_prose(text):
            self.parts.append(text)


def _from_html(raw: str) -> str:
    p = _TextExtractor()
    p.feed(raw)
    p._flush_row()
    return "\n".join(p.parts)


_FENCE = re.compile(r"^```.*?^```", re.M | re.S)
_INDENTED_CODE = re.compile(r"^(?: {4}|\t).*$", re.M)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")     # keep the text, drop the target
_BARE_URL = re.compile(r"https?://\S+|www\.\S+")
_PATH = re.compile(r"(?:[\w.\-]+/){1,}[\w.\-]+")     # a/b/c.py
_FILENAME = re.compile(r"\b[\w\-]+\.(?:md|txt|json|ya?ml|toml|py|swift|js|ts|tsx|sh|rs|c|h|html|css|png|jpe?g|pdf|log|lock|cfg|ini)\b")
_HEADING_MARK = re.compile(r"^#{1,6}\s*", re.M)
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.M)


def _from_markdown(raw: str) -> str:
    """Prose only — code, URLs and paths removed before anything sees them.

    Measured on 2,491 real documents from this author's repositories: read as
    plain text, the highest-mass cores were `com` (2,506), `md` (2,209),
    `json` (1,673), `ts` (1,202). Those are the tails of URLs, the extensions
    in file paths, and the language tags on code fences. An index built from
    that is an index of file extensions, not of what the documents are about.

    Each removal is for a specific one of those:

      fenced/indented code   the language tag and every identifier inside
      inline code            `--store`, `CrossStore`, flag names
      link targets           kept the text, dropped the URL
      bare URLs              `example.com` contributes "com"
      paths and filenames    `docs/DESIGN.md` contributes "docs" and "md"
      table rows             pipe-delimited cells are data, not sentences

    Aggressive on purpose. A document whose content is entirely code has
    nothing to say to a prose index, and losing a sentence costs less than
    letting `md` become the most-discussed topic in the corpus.
    """
    text = _FENCE.sub(" ", raw)
    text = _TABLE_ROW.sub(" ", text)
    text = _INDENTED_CODE.sub(" ", text)
    text = _INLINE_CODE.sub(" ", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _BARE_URL.sub(" ", text)
    text = _FILENAME.sub(" ", text)
    text = _PATH.sub(" ", text)
    text = _HEADING_MARK.sub("", text)
    # Collapse the holes so sentence splitting is not fooled by the gaps.
    return re.sub(r"[ \t]{2,}", " ", text)


def _from_csv(raw: str, delimiter: str = ",") -> str:
    """One row per line, `column: value` joined.

    Naming the column matters: a bare row of values loses which field each
    one was, and a store full of unlabelled values cannot be questioned.
    """
    out: List[str] = []
    reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return ""
    header = rows[0]
    for row in rows[1:]:
        pairs = [f"{h} {v}" for h, v in zip(header, row) if v.strip()]
        if pairs:
            out.append(", ".join(pairs) + ".")
    return "\n".join(out)


def _from_json(raw: str) -> str:
    """Leaf strings, prefixed with their path, so nesting survives as words."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc

    out: List[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path} {k}".strip())
        elif isinstance(node, list):
            for v in node:
                walk(v, path)
        elif isinstance(node, str) and node.strip():
            out.append(f"{path} {node}".strip() + ".")
        elif isinstance(node, (int, float, bool)):
            out.append(f"{path} {node}.")

    walk(obj, "")
    return "\n".join(out)


_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _from_docx(path: Path) -> str:
    """Paragraph text out of word/document.xml.

    A .docx is a zip; no third-party reader is needed. Runs inside a
    paragraph are joined without separators because Word splits a single
    sentence across runs whenever formatting changes mid-line — joining with
    spaces would insert them inside words.
    """
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(path) as zf:
        try:
            xml = zf.read("word/document.xml")
        except KeyError as exc:
            raise ValueError("not a Word document (no word/document.xml)") from exc
    root = ET.fromstring(xml)
    paragraphs: List[str] = []
    for para in root.iter(f"{_W_NS}p"):
        text = "".join(t.text or "" for t in para.iter(f"{_W_NS}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


# ---------------------------------------------------------------------------
# Physical lines vs logical lines
# ---------------------------------------------------------------------------

#: In extracted text a wrapped line and a finished line look identical — both
#: end in "\n" — and telling them apart decides whether a document is read at
#: all. The sentence splitter cuts at 。, tables have no 。, so a table is one
#: sentence. Measured on four revisions of 内閣府's 令和8年熊本地震 damage
#: report: 77.8% of 267,064 characters sat inside segments spanning four lines
#: or more, the largest being 259 lines and 5,836 characters filed under the
#: single core 国土交通省. The per-municipality facts those tables carry —
#: 「熊本県 熊本市 断水あり」 on 7/29, 「熊本市 … ・復旧済」 on 8/6 — never became
#: claims about 熊本市, which is why the corpus reported zero opposable pairs
#: while plainly containing an update.
#:
#: The signal is the page's own geometry rather than anything linguistic: a
#: laid-out column breaks a line only when the line is FULL, so a short line
#: ended on purpose and a full-width line continues into the next. The width
#: is measured per document, because a PDF column, a hard-wrapped .md file and
#: a plain-text note each wrap somewhere different.
#:
#: Deliberately not applied to CSV, TSV, JSON or HTML: those arrive as logical
#: lines already, and a wide CSV row would be glued to the row beneath it.
_WRAP_KEEP = 0.90        # a line this fraction of full width is still filling
_WRAP_MIN_LINES = 8      # below this there is no distribution to measure
_WRAP_MIN_WIDTH = 20     # below this, "full width" is not a meaningful idea
_LINE_ENDS = ("。", "．", ".", "！", "!", "？", "?", "」", "）", ")", "：", ":")
_CJK_CHAR = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")


def _column_width(lines: List[str]) -> int:
    lengths = sorted(len(ln) for ln in lines if ln.strip())
    if len(lengths) < _WRAP_MIN_LINES:
        return 0
    return lengths[int(len(lengths) * 0.90)]


def _join_wrapped(head: str, tail: str) -> str:
    if not head:
        return tail
    # Japanese wraps mid-word and takes no space; English needs one back.
    if _CJK_CHAR.search(head[-1]) or _CJK_CHAR.search(tail[:1] or " "):
        return head + tail
    return head + " " + tail


#: A field that is data rather than words: digits with the punctuation data
#: carries — 約25,269 / 7/28～8/1 / 0※. Two such fields on one line is the
#: shape of a TABLE ROW.
_DATA_FIELD = re.compile(r"^[約計]?[0-9０-９][0-9０-９,，.．/／~～\-－※]*$")


def _is_table_row(line: str) -> bool:
    """A table row is line-atomic and must never be joined to its neighbour.

    Width alone cannot tell a full-width table row from wrapped prose, and
    the cost of confusing them is not a lost line but a MOVED claim. Found
    blind on 国交省's 第33報: 「宇城市 約18,000 約9.900 7/28～ ・管破損に伴う
    漏水」 fills its column, ends in no punctuation, and was read as wrapped —
    so the next line, 天草市's row, was glued on with the CJK no-space join
    and the corpus contained the word 漏水天草市. 天草市's restoration was
    then a claim about that non-word, invisible to anyone asking about the
    real municipality.

    What distinguishes the row is its fields: prose does not carry two
    whitespace-separated tokens of bare digits and data punctuation.
    """
    fields = line.split()
    return sum(1 for f in fields if _DATA_FIELD.match(f)) >= 2


def _normalized(text: str) -> str:
    """Apply whatever transforms the engine proved it needed on itself.

    Runs AFTER the rows are settled, because `_is_table_row` reads the spacing
    it would otherwise remove — a column gap and an extractor's stray space are
    the same character, and only the row detector can tell them apart.
    """
    from .ja_grammar import NORMALIZERS

    if not NORMALIZERS:
        return text
    from .metamorphic import PERTURBATIONS

    for name, _why in NORMALIZERS:
        fn = PERTURBATIONS.get(name)
        if fn:
            text = fn[0](text)
    return text


def unwrap_layout(text: str) -> str:
    """Rejoin lines the page broke, so the remaining newlines mean something."""
    lines = (text or "").split("\n")
    width = _column_width(lines)
    if width < _WRAP_MIN_WIDTH:
        return _normalized(text)
    full = width * _WRAP_KEEP

    out: List[str] = []
    buf = ""
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            if buf:
                out.append(buf)
                buf = ""
            continue
        if _is_table_row(line):
            # Rows stand alone: flush any wrapped prose before, and never
            # let the row itself continue into the next line.
            if buf:
                out.append(buf)
                buf = ""
            out.append(line.strip())
            continue
        buf = _join_wrapped(buf, line.strip() if buf else line)
        if len(line) < full or line.rstrip().endswith(_LINE_ENDS):
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return _normalized("\n".join(out))



#: Scripts a normal document mixes freely without meaning anything by it.
#: Everything else is counted, and a document that draws on four or more
#: of those is not multilingual — it is broken.
_ORDINARY_SCRIPTS = frozenset({
    "LATIN", "DIGIT", "SPACE", "CJK", "HIRAGANA", "KATAKANA", "IDEOGRAPHIC",
    "FULLWIDTH", "HALFWIDTH", "KATAKANA-HIRAGANA", "NO-BREAK", "ZERO",
    "LEFT", "RIGHT", "HORIZONTAL", "VERTICAL", "BOX", "EM", "EN", "HYPHEN",
    "COMMA", "QUESTION", "EXCLAMATION", "BULLET", "MIDDLE", "WAVE",
    "REPLACEMENT", "BLACK", "WHITE", "UPWARDS", "DOWNWARDS", "LEFTWARDS",
    "RIGHTWARDS", "HEAVY", "LIGHT", "DOUBLE", "SUPERSCRIPT", "SUBSCRIPT",
    "DEGREE", "MICRO", "SECTION", "PILCROW", "DAGGER", "ELLIPSIS", "PRIME",
    "MINUS", "MULTIPLICATION", "DIVISION", "NOT", "PLUS", "INFINITY",
    "PARTIAL", "INCREMENT", "NABLA", "ELEMENT", "INTEGRAL", "ALMOST",
    "IDENTICAL", "LESS-THAN", "GREATER-THAN", "SQUARE", "CIRCLED",
    "PARENTHESIZED", "NUMBER",
})

#: Four, not two. A Russian paper carrying maths mixes Cyrillic with Greek
#: and Latin and is perfectly legible; the measured break is far above it.
ILLEGIBLE_SCRIPT_COUNT = 4


def script_mix(text: str) -> Dict[str, int]:
    """Which unusual scripts this text draws on, and how heavily.

    A PDF whose embedded font carries no ToUnicode map extracts as a
    character-for-character substitution into whatever blocks the CIDs
    happen to land in. Measured on one real 12,336-line PDF: pypdf
    returned Greek, Tibetan, Oriya, Coptic, Devanagari and Arabic *in the
    same document* — 20 scripts — where PDFKit read the same file as clean
    Japanese. Nothing about the bytes said "failure": `extract_text`
    returned a long, confident string, and 10,191 sentences and 2,032
    cores went into the store before anyone read one.

    Simpler tests were measured first and rejected. The share of odd
    characters puts a Japanese maths note (0.15) *above* the broken PDF
    (0.048), and counting runs of them puts ordinary Russian (0.81) above
    it too. What actually separates the two is that a real document
    commits to one or two scripts, and a mis-decoded one draws from every
    block at once.
    """
    counts: Dict[str, int] = {}
    for ch in text:
        if ch.isspace() or ord(ch) < 128:
            continue
        token = unicodedata.name(ch, "UNNAMED").split()[0]
        if token in _ORDINARY_SCRIPTS:
            continue
        counts[token] = counts.get(token, 0) + 1
    floor = max(1, int(len(text) * 0.0005))
    return {k: v for k, v in counts.items() if v >= floor}


def _from_pdf(path: Path) -> str:
    if importlib.util.find_spec("pypdf") is None:
        # `name=` matters: the caller distinguishes this from any other
        # missing import by `exc.name`, and the positional message alone
        # leaves it None, so the guard let it through and the whole batch
        # died on one PDF.
        raise ModuleNotFoundError("pypdf is required for PDF", name="pypdf")
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n".join(p for p in pages if p)


def load_path(path: str, source: Optional[str] = None) -> Dict[str, Any]:
    """One file → a Document, or a typed reason it is not one.

    `source` defaults to the filename, which is what a reader needs to see
    beside a disputed claim. Callers with a real citation (a URL, an agency
    name) should pass it.
    """
    p = Path(path)
    label = source or p.name
    if not p.is_file():
        return {"verdict": "UNKNOWN_UNREADABLE", "path": str(p),
                "reason": "no such file"}

    suffix = p.suffix.lower()
    if suffix not in SUPPORTED:
        return {"verdict": "UNKNOWN_NO_PARSER", "path": str(p),
                "suffix": suffix or "(none)",
                "reason": f"no loader for '{suffix}'",
                "supported": sorted(SUPPORTED)}

    # Formats whose newlines come from page layout rather than from the
    # author. See `unwrap_layout`.
    laid_out = suffix in {".pdf", ".docx", ".md", ".markdown",
                          ".txt", ".log", ".rst"}
    try:
        if suffix == ".pdf":
            text = _from_pdf(p)
        elif suffix == ".docx":
            text = _from_docx(p)
        else:
            raw = p.read_text(encoding="utf-8", errors="replace")
            if suffix in {".md", ".markdown", ".txt", ".log", ".rst"}:
                # Plain-text notes get the same cleaning as Markdown.
                # Measured on a 107,752-line notes file that is nominally
                # .txt but full of markdown syntax and pasted code: read
                # raw, its top "topic" was `py` (1,471 mentions), with
                # `json` and `com` close behind; cleaned, all three vanish
                # and the real topics (ステップ, 投稿, 実装…) keep their
                # counts. On genuinely plain prose every one of these
                # patterns is a no-op except the path/URL strippers, which
                # are exactly what prose wants stripped. The known cost:
                # indented prose paragraphs are treated as code blocks and
                # dropped — the module's standing trade, a lost sentence
                # over a corpus-wide fake topic.
                text = _from_markdown(raw)
            elif suffix in {".html", ".htm"}:
                text = _from_html(raw)
            elif suffix == ".csv":
                text = _from_csv(raw)
            elif suffix == ".tsv":
                text = _from_csv(raw, delimiter="\t")
            elif suffix == ".json":
                text = _from_json(raw)
            else:
                text = raw
    except ModuleNotFoundError as exc:
        if exc.name != "pypdf":
            raise
        return {"verdict": "UNKNOWN_NO_PARSER", "path": str(p), "suffix": suffix,
                "reason": "PDF support needs the `docs` extra",
                "install": 'python3 -m pip install "verantyx-vera[docs] @ git+https://github.com/Ag3497120/Verantyx-Vera-alpha"'}
    except Exception as exc:  # noqa: BLE001 — deliberate, see below
        # Every parser failure becomes a typed refusal for THIS file, and the
        # batch continues. Deliberately broad: third-party parsers raise
        # their own exception hierarchies, and a list of the ones seen so far
        # is a list that is wrong the first time a new format appears.
        #
        # Measured: with pypdf installed, a truncated PDF raised
        # PdfStreamError — outside the previous (OSError, ValueError,
        # BadZipFile) tuple — and took down the whole run. One corrupt file
        # must never cost the other nine hundred.
        return {"verdict": "UNKNOWN_UNREADABLE", "path": str(p),
                "reason": f"{type(exc).__name__}: {exc}"}

    if laid_out:
        text = unwrap_layout(text)

    # 読めない文字列は、読めなかったことより悪い。長く自信ありげな
    # 文字列が返るので、誰も読まないまま店に入る。実測: この門が無い間に
    # 1件のPDFが連合の核 2,140 のうち 937 を化けで埋めた。
    mixed = script_mix(text)
    if len(mixed) >= ILLEGIBLE_SCRIPT_COUNT:
        top = sorted(mixed.items(), key=lambda kv: -kv[1])[:6]
        return {"verdict": "UNKNOWN_ILLEGIBLE_TEXT", "path": str(p),
                "scripts": len(mixed),
                "sample": [k for k, _ in top],
                "reason": "%d の異なる文字体系が混在している — 埋め込み"
                          "フォントに ToUnicode 対応表が無く、字が別の"
                          "ブロックへ写ったまま出てきた疑いが濃い"
                          % len(mixed),
                "note": "取り込みは行っていない。原文をテキストに書き出して"
                        "から渡すか、PDFKit のように CID を解ける読取器を"
                        "通したものを渡すこと"}

    if not text.strip():
        # Distinct from a parse failure, and it matters: a scanned PDF is an
        # image of text, and no amount of retrying the loader will help. The
        # answer is OCR, which this does not do and should not pretend to.
        return {"verdict": "UNKNOWN_EMPTY_DOCUMENT", "path": str(p),
                "reason": "parsed, but no extractable text (a scanned image?)"}

    return {"verdict": "ANSWER", "path": str(p), "source": label,
            "chars": len(text), "document": Document(source=label, text=text)}


def load_paths(paths: List[str]) -> Dict[str, Any]:
    """Load many, keeping the failures. A batch that drops what it could not
    read reports a smaller corpus as if it were the whole one."""
    loaded: List[Document] = []
    skipped: List[Dict[str, Any]] = []
    for path in paths:
        res = load_path(path)
        if res["verdict"] == "ANSWER":
            loaded.append(res["document"])
        else:
            skipped.append({k: v for k, v in res.items() if k != "document"})
    return {"documents": loaded, "loaded": len(loaded), "skipped": skipped}


def load_directory(root: str, recursive: bool = True) -> Dict[str, Any]:
    """Every supported file under a folder — the "here is the whole folder of
    circulars" path."""
    base = Path(root)
    if not base.is_dir():
        return {"documents": [], "loaded": 0,
                "skipped": [{"verdict": "UNKNOWN_UNREADABLE", "path": str(base),
                             "reason": "not a directory"}]}
    it = base.rglob("*") if recursive else base.glob("*")
    files = sorted(str(p) for p in it
                   if p.is_file() and p.suffix.lower() in SUPPORTED)
    out = load_paths(files)
    out["scanned"] = len(files)
    return out
