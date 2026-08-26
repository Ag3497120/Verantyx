# -*- coding: utf-8 -*-
"""English output for a tool whose strings are Japanese.

This is a **translation layer over the engine's output**, not a rewrite of the
engine. The reason is deliberate: the drafting, marking and sewing code is
shared with a larger project, and forking 3,795 lines to thread a `_()` call
through every message would make the two copies drift. Instead every value the
engine returns is walked on the way out and swapped against a table.

That choice has one honest consequence, and it is measurable rather than
hand-waved: a string the table does not know comes back in Japanese. So the
module also reports what it missed —

    from photoloset import i18n
    i18n.missing(result)     # every Japanese string with no translation
    i18n.coverage(result)    # (translated, total)

If `missing()` is non-empty, the English is incomplete *there*, and you can see
exactly where. A silent fallback that returned an approximation would be worse
than a visible gap.

Three mechanisms, in order of precedence:

1. `SENTENCES` — exact match. Notes, refusal reasons, formula descriptions.
2. `RULES` — regular expressions for strings the engine builds from parts,
   e.g. "<part> の <aspect> が映るカットを探す / 依頼者に確認".
3. `TERMS` + composition — piece and edge names. Because the engine writes
   "前身頃/肩線" and "袖/袖山(前半) ↔ 前身頃/袖ぐり", the composition rules for
   `/`, `↔`, `(right)`, `(left)` and `(front)`, `(back)` are applied so those
   never need their own table entries.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

LANGUAGES = ("ja", "en")
DEFAULT = "ja"

_JA = re.compile(r"[぀-ヿ㐀-鿿＀-￯]")


def has_japanese(s: str) -> bool:
    return bool(_JA.search(s))


# ---------------------------------------------------------------------------
# 3. Terms — pieces, edges, measurement spots, notch roles
# ---------------------------------------------------------------------------

TERMS: Dict[str, str] = {
    # pieces
    "前身頃": "front bodice",
    "後身頃": "back bodice",
    "袖": "sleeve",
    # edges
    "肩線": "shoulder seam",
    "脇線": "side seam",
    "袖ぐり": "armhole",
    "衿ぐり": "neckline",
    "袖山": "sleeve cap",
    "裾": "hem",
    "袖口": "cuff",
    "中心線": "centre line",
    "袖下線": "underarm seam",
    # measurement spots
    "着丈": "body length",
    "胸囲": "chest",
    "肩幅": "shoulder width",
    "袖丈": "sleeve length",
    "胴囲": "waist",
    "腰囲": "hip",
    "スカート丈": "skirt length",
    "袖口幅": "cuff width",
    "裾幅": "hem width",
    "襟の高さ": "collar height",
    "ポケット位置(肩からの距離)": "pocket position (distance from shoulder)",
    # notch roles and landmarks
    "肩点": "shoulder point",
    "脇": "underarm",
    "前振り": "front pitch point",
    "後振り": "back pitch point",
    "前胸": "front chest",
    "後肩甲": "back shoulder blade",
    "たて地": "grain",
    # drafting quantities
    "いせ込み": "ease",
    "袖ぐり深さ": "armhole depth",
    "袖山の高さ": "cap height",
    "袖山の幅": "cap width",
    "前衿ぐり深さ": "front neckline depth",
    "後衿ぐり深さ": "back neckline depth",
    "肩線の下がり": "shoulder slope",
    "身頃幅 (前後それぞれ)": "bodice width (each of front and back)",
    "衿ぐり幅 (前後共通)": "neckline width (same front and back)",
    "袖幅 (袖口側)": "sleeve width (at the cuff)",
    "肩先の位置 (x)": "shoulder tip position (x)",
    "袖山の control 点 (x)": "cap control point (x)",
    "袖山の control 点 (y)": "cap control point (y)",
    "袖ぐりの control 点 (y)": "armhole control point (y)",
    "前袖ぐりの control 点 (x)": "front armhole control point (x)",
    "後袖ぐりの control 点 (x)": "back armhole control point (x)",
    # section headings
    "寸法": "measurements",
    "由来": "provenance",
    "未確定": "not determined",
    "確定した項目": "settled",
    "割れている項目": "contested",
    "推論(要確認)": "inferred (needs checking)",
    "うち提案あり(未採用)": "of which proposed but not adopted",
    "袖山と袖ぐり": "cap against armhole",
    "肩線・脇線": "shoulder seam, side seam",
    "前後身頃/袖ぐり の合計": "front + back bodice / armhole, combined",
    # skirt edges and landmarks
    "ウエスト": "waist",
    "ウエスト(カーシング)": "waist (elastic casing)",
    "丈": "length",
    "中間": "midpoint",
    "ヒップ": "hip",
    "襟ぐり": "neckline",
    "肩線・脇線に準じる(接続の縫い目)": "after shoulder and side seams "
                                      "(a joining seam)",
    "同じ点から引いているので差は構成上ゼロです":
        "both edges come from the same points, so the difference is zero "
        "by construction",
    "衿ぐり (前)": "front neckline",
    "衿ぐり (後)": "back neckline",
    "袖山(前半)": "cap (front half)",
    "袖山(後半)": "cap (back half)",
    "ケープ": "cape",
    "スカート前": "skirt front",
    "スカート後": "skirt back",
    # cape formula keys
    "ケープの内半径": "cape inner radius",
    "ケープの外半径": "cape outer radius",
    "扇の開き": "sector angle",
    "弧の分割": "arc subdivision",
    "ハイローの落ち差": "high-low drop",
    # zone labels
    "胸のゆとり": "chest ease",
    "袖ぐり深さの追加": "extra armhole depth",
    "袖山のいせ": "cap ease",
    "袖口の広さ": "cuff width",
    "フレアの割合": "flare ratio",
    # new measurement spots (parts)
    "襟ぐり周囲": "neck circumference",
    "上身頃丈": "bodice length",
    "ケープ丈": "cape length",
}

_SUFFIX = {
    "(右)": "(right)", "(左)": "(left)",
    "(前)": "(front)", "(後)": "(back)",
    "(前半)": "(front half)", "(後半)": "(back half)",
}


def _term(s: str) -> Optional[str]:
    """Translate a compound name by composing its parts.

    Handles "A/B", "A ↔ B", "A・B" and the "(right)/(left)/(front)/(back)"
    suffixes, so those combinations never need a table entry of their own.
    """
    s = s.strip()
    if s in TERMS:
        return TERMS[s]
    for sep, join in ((" ↔ ", " <-> "), ("/", " / "), ("・", ", ")):
        if sep.strip() and sep.strip() in s:
            parts = [p.strip() for p in s.split(sep.strip())]
            done = [_term(p) for p in parts]
            if all(done):
                return join.join(d for d in done if d)
    for ja, en in _SUFFIX.items():
        if s.endswith(ja):
            base = _term(s[: -len(ja)])
            if base:
                return f"{base} {en}"
    return None


# ---------------------------------------------------------------------------
# 2. Rules — strings the engine assembles from parts
# ---------------------------------------------------------------------------

RULES: List[Tuple[re.Pattern, Any]] = [
    (re.compile(r"^(\S+) の (\S+) が映るカットを探す / 依頼者に確認(?:する)?$"),
     lambda m: f"find a shot where the {m.group(1)} {m.group(2)} is visible, "
               f"or ask the client"),
    (re.compile(r"^(.+?)をもう一度測って、どちらが正しいか決める$"),
     lambda m: f"measure the {_term(m.group(1)) or m.group(1)} again and "
               f"decide which reading is right"),
    (re.compile(r"^(.+?)を実物か資料から測る$"),
     lambda m: f"measure the {_term(m.group(1)) or m.group(1)} on the real "
               f"garment or from a spec"),
    (re.compile(r"^(\S+) の (.+?) を出典付きで入れる$"),
     lambda m: f"supply {m.group(1)}'s {m.group(2)} with a source"),
    (re.compile(r"^(.+?)、(.+?) を実測すれば引ける$"),
     lambda m: f"measure {m.group(1)} and {m.group(2)} and it can be drafted"),
    (re.compile(r"^袖ぐり側の合印から、脇〜振りはいせ0・振り〜肩にいせ"
                r"([\d.]+)cmを区間長で配って決めた$"),
     lambda m: f"measured from the armhole notch: zero ease from underarm to "
               f"pitch point, {m.group(1)} cm of ease distributed from pitch "
               f"point to shoulder in proportion to segment length"),
    (re.compile(r"^(\S+) ([\d.]+)cm × ([\d.]+)$"),
     lambda m: f"{_term(m.group(1)) or m.group(1)} {m.group(2)} cm x {m.group(3)}"),
    (re.compile(r"^決まらないのは(.+?)です\(([\d.]+)cm 振れます\)$"),
     lambda m: f"what is not determined is the "
               f"{_term(m.group(1)) or m.group(1)} — it swings by {m.group(2)} cm"),
    (re.compile(r"^(.+?)は一致しています$"),
     lambda m: f"{_term(m.group(1)) or m.group(1)} agree"),
    (re.compile(r"^(前|後)振り: 襟ぐりから袖ぐり深さの半分の高さ "
                r"\(y=([\d.]+)cm\)。テーラリングの通則$"),
     lambda m: f"{'front' if m.group(1) == '前' else 'back'} pitch point: half "
               f"the armhole depth below the neckline (y={m.group(2)} cm), the "
               f"usual tailoring rule"),
    # --- the cross store's own refusals ---------------------------------
    # **A refusal a caller cannot read is the one string that most needs
    # translating.** These were outside the table (67 untranslated across
    # the newly load-bearing modules) while the README said 0; the refusal
    # texts are in now, and README.md states what is still out of scope.
    (re.compile(r"^(.+?) に (.+?) は載っていない$"),
     lambda m: f"{m.group(1)} does not carry {m.group(2)}"),
    (re.compile(r"^([ab]) の核 (.+?) は店に無い$"),
     lambda m: f"the {m.group(1)} end names core {m.group(2)}, which is not "
               f"in the store"),
    (re.compile(r"^([ab])=(.+?) は \(core, key\) の形ではない$"),
     lambda m: f"the {m.group(1)} end {m.group(2)} is not a (core, key) pair"),
    (re.compile(r"^値(.*?): (\S+) は JSON で往復しない$"),
     lambda m: f"value{m.group(1)}: {m.group(2)} does not survive the JSON "
               f"round trip this store saves in"),
    (re.compile(r"^(.+?)\{(.+?)\}: 鍵が文字列ではない \((.+?)\) — "
                r"JSON の往復で文字列に化ける$"),
     lambda m: f"{m.group(1)}[{m.group(2)}]: the key is not a string "
               f"({m.group(3)}) — the JSON round trip turns it into one"),
    (re.compile(r"^一般構造の主張に出典が無い。空の出典は(\d+)本のうちの"
                r"1本に数えない$"),
     lambda m: f"a general claim with no source: an empty source is not one "
               f"of the {m.group(1)} it costs"),
    (re.compile(r"^独立した出典を(\d+)本示すか、specific に落とす$"),
     lambda m: f"name {m.group(1)} independent sources, or write it as "
               f"`specific`"),
    (re.compile(r"^(.+?)/(.+?) という候補はライブラリに無い$"),
     lambda m: f"the library has no {m.group(1)} variant called "
               f"{m.group(2)}"),
    (re.compile(r"^(.+?)/(.+?) という候補は無い$"),
     lambda m: f"there is no {m.group(1)} variant called {m.group(2)}"),
    (re.compile(r"^スカート（(.+)）$"),
     lambda m: "skirt ("
               + " / ".join(string(part) for part in m.group(1).split("・"))
               + ")"),
    # --- the four fields of a seat, and the values JSON cannot hold ------
    # ``_persistable`` names WHERE it found the trouble, so the path prefix
    # ("値", "[0]", ".required") is carried through untranslated on purpose:
    # it is an address inside the caller's own value.
    (re.compile(r"^(.+?): (\S+) は JSON で往復しない "
                r"\(NaN と ±Infinity は JSON の数ではない\)$"),
     lambda m: f"{_path_word(m.group(1))}: {m.group(2)} does not survive the "
               f"JSON round trip (NaN and +/-Infinity are not JSON numbers)"),
    (re.compile(r"^(.+?): 自分自身を含んでいる — JSON は循環を書けない$"),
     lambda m: f"{_path_word(m.group(1))}: contains itself — JSON cannot "
               f"write a cycle"),
    (re.compile(r"^(\S+) — 住所は文字列でなければ JSON の鍵として"
                r"往復しない$"),
     lambda m: f"{m.group(1)} — an address has to be a string to survive as "
               f"a JSON key"),
    (re.compile(r"^(.+?) の (.+?) に席はあるが主張が一つも無い "
                r"\(空の席は主張ではない\)$"),
     lambda m: f"{m.group(1)} has a seat at {m.group(2)} but not one claim "
               f"on it (an empty seat is not a claim)"),
    # --- a measurement that is not a number ------------------------------
    (re.compile(r"^(.+?): (.+?) は数ではない。寸法は数で書く$"),
     lambda m: f"{m.group(1)}: {m.group(2)} is not a number — a measurement "
               f"is written as one"),
]


def _path_word(p: str) -> str:
    """The path prefix ``_persistable`` prints. Only the bare word is ours."""
    return "value" if p == "値" else p


def _rule(s: str) -> Optional[str]:
    for pattern, make in RULES:
        m = pattern.match(s)
        if m:
            return make(m)
    return None


# ---------------------------------------------------------------------------
# 1. Sentences — exact match
# ---------------------------------------------------------------------------

SENTENCES: Dict[str, str] = {
    # --- the parts catalogue: family variants, their notes, the labels ---
    # These are OUTPUT a reader sees (assemble(), Library.variants(), the
    # block label), so they are in the table. What is deliberately NOT in
    # it is stated in README.md: store ADDRESSES (core names and seat keys
    # in to_dict/write_plan/seats/seam_edges) and the prompt bank's text,
    # which is written for the model, not for the reader.
    "Aライン": "A-line",
    "Aライン（裾に向かって広がる）": "A-line (flares towards the hem)",
    "ストレート": "straight",
    "ストレート（裾はほぼ真っ直ぐ）": "straight (an almost straight hem)",
    "ゴムウエスト（開き無し）": "elastic waist (no opening)",
    "ゴムウエスト。前後とも中心線は折り(わ)":
        "elastic waist; both centre lines are folds",
    "後ろセンターファスナー": "centre-back zip",
    "後ろ中心に開きを入れる": "an opening at the centre back",
    "ファスナー用の開き量と、開きを持つ縫い代の取り方はまだ引けない。"
    "宣言だけ載せてある":
        "the opening allowance for a zip, and the seam allowance around an "
        "opening, cannot be drafted yet — only the declaration is on record",
    "シャーリング": "shirring",
    "ウエストに楽を持たせてゴムに寄せる":
        "ease at the waist, gathered onto elastic",
    "たて地。中心線と平行": "straight grain, parallel to the centre line",
    "ウエスト線の左右の端を吊る。肩の無い服は肩で吊れない":
        "hung from the two ends of the waistline — a garment with no "
        "shoulders cannot hang from the shoulders",
    "前は手前": "the front is nearer",
    "後ろは奥": "the back is further",
    # **The reason a writer gave, in the writer's own words.** These three
    # are seat VALUES rather than engine prose, which is why they sat
    # outside the table while their two neighbours ("the front is nearer",
    # "the back is further") were translated — the same declaration, the
    # same reader, half of it in Japanese. An English caller is meant to
    # read them.
    "袖は横": "the sleeve is off to the side",
    "吊るのは前身頃だけ。後ろは肩の縫い目を通してぶら下がる":
        "only the front bodice is pinned up; the back hangs from it through "
        "the shoulder seam",
    "袖山のいせ込みを脇の下側に入れない(テーラリングの通説)":
        "no sleeve-cap ease below the pitch point (the usual tailoring "
        "rule)",
    "propose_variant で先に提案する":
        "propose it with propose_variant first",
    "脇の中間に単合印。前後で対になる":
        "a single notch at the mid side seam, paired front to back",
    "既知の候補から選ぶ": "choose one of the known variants",
    "三枚コート（前身頃・後身頃・袖）":
        "three-piece coat (front bodice, back bodice, sleeve)",
    # --- prose the store returns beside a verdict ------------------------
    "配置が答えを決めているなら、それは宣言ではなく並びの産物":
        "if placement decides the answer, the answer is a product of the "
        "arrangement rather than of the declaration",
    "格納順が答えを決めているなら、それは宣言ではなく並びの産物":
        "if storage order decides the answer, the answer is a product of "
        "the ordering rather than of the declaration",
    "いま載っているものを入れ直しても答えが動かない、という後退よけです。"
    "本物の順序検査は ingest_order_check":
        "a regression guard: re-ingesting what is already stored does not "
        "move any answer. The real order check is ingest_order_check",
    "モデルの自己申告の数字は事実の欄に入らない(VM2)。"
    "根拠は領域と複数観測の一致で示す":
        "a model's self-reported number is not a fact (VM2); ground a claim "
        "in the image region and in agreement between observations",
    "該当キーを外して出し直させる": "drop that key and ask again",
    # --- the cross store's refusals, and how to close them ---------------
    "宣言に足す": "add it to the declaration",
    "宣言に主張の種別を書く": "state the kind of claim in the declaration",
    "出典を名乗るか、specific に落とす":
        "name a source, or write the claim as `specific`",
    "JSON で往復する形 (数・文字列・真偽・None・list・文字列鍵の dict) に直す":
        "use a shape that survives the JSON round trip (number, string, "
        "boolean, None, list, or a dict with string keys)",
    "JSON で往復する形に直す (核と鍵は空でない文字列、値と出典は数・文字列・"
    "真偽・None・list・文字列鍵の dict)":
        "use a shape that survives the JSON round trip (the core and the key "
        "are non-empty strings; the value and the source are a number, "
        "string, boolean, None, list, or a dict with string keys)",
    "空の名前は住所ではない": "an empty name is not an address",
    # --- the quarantine core is a place, not a spelling ------------------
    "隔離核は提案の置き場所。腕を持つ主張をここに座らせると、主題の閉包から"
    "読めないまま実腕の予算だけを食う":
        "the quarantine core is where proposals live. An armed claim seated "
        "here cannot be read from the subject's closure and still spends a "
        "real arm's budget",
    "提案を主題の核に採り入れてから、主題の核に書く":
        "adopt the proposal into the subject core, then write it there",
    "隔離核の中の腕付きの席 — 主題から読めないのに予算を食う":
        "an armed seat inside a quarantine core — unreadable from the "
        "subject, and still spending budget",
    # --- an empty seat, and the shapes the loader will not build ---------
    "宣言に足すか、空の席を消す": "add it to the declaration, or delete the "
                                 "empty seat",
    "席に主張が一つも無い — 店は空の席を作らない":
        "the seat carries no claim at all — the store never creates one",
    "形の合わない席は載せていない — 黙って直すと格納が答えを動かす":
        "seats whose shape does not hold were not loaded — repairing them "
        "silently would let storage move an answer",
    "店の形は dict": "a store is a dict",
    "cores は 核の名前 → 席の並び の dict":
        "`cores` maps a core name to a list of seats",
    "核は席の並び": "a core is a list of seats",
    "席は dict": "a seat is a dict",
    "腕は名前か None": "an arm is a name or None",
    "宣言の序数は整数 — 並べ替えで比べるので、文字列が一つ混ざると seats() "
    "が上げる":
        "the declaration ordinal is an integer — seats() sorts on it, so one "
        "string mixed in makes the reader raise",
    "values は並び": "`values` is a list",
    "主張は dict": "a claim is a dict",
    "出典は並び": "`sources` is a list",
    "edges は並び": "`edges` is a list",
    "辺は dict": "an edge is a dict",
    "隔離核の名前は文字列": "a quarantine core's name is a string",
    "quarantine は名前の並び": "`quarantine` is a list of names",
    "seq は整数": "`seq` is an integer",
    "席の鍵は文字列": "a seat's key is a string",
    "子コアに分ける (マトリョーシカは幾何が要求すること)":
        "split into a child core (the matryoshka is required by the "
        "geometry, not a taste)",
    "隔離核も 1核=24席。腕を持たない席は核あたりで数える":
        "the quarantine core obeys the same 1 core = 24 seats; seats with "
        "no arm are counted per core",
    "1核 = 24席。腕ごとの予算とは別に、核そのものの上限":
        "1 core = 24 seats — the core's own ceiling, separate from the "
        "per-arm budget",
    "1核 = 24席。腕付きの席と隔離席を合わせても超えない":
        "1 core = 24 seats — armed seats and quarantined seats counted "
        "together",
    "両端の核を先に立ててから結ぶ":
        "create both end cores before linking them",
    "分ける先の親核を先に立ててから書く":
        "create the parent core before writing into a split child",
    "探して無かった、は主張ではない。載せません":
        "\"looked and did not find it\" is not a claim; nothing is stored",
    "宣言を確かめて、正しい方だけを残す":
        "check the declaration and keep only the right one",
    "腕は kind から導かれる。書く側が選ぶものではない":
        "the arm is derived from the kind; the writer does not choose it",
    "この席は座ったときの腕にしか課金されていない":
        "this seat is charged only to the arm it was seated on",
    "分れた子が nest 辺で親から届かない — この核の割れは構造上見えない":
        "a split child the parent cannot reach through a nest edge — a "
        "contest inside it is structurally invisible",
    "分れた子の親核が店に無い — この核は誰からも届かない":
        "the split child's parent core is not in the store — nothing can "
        "reach this core",
    "同じ席に同じ (種別, 値) が二つ。同じ主張の裏付けは出典を足すこと":
        "the same (kind, value) twice on one seat; corroborate a claim by "
        "adding a source instead",
    "一つの閉包に同じ住所が二つ":
        "the same address twice inside one closure",
    "同じオブジェクトが二席に居る。外から片方を書き換えられる":
        "one object seated twice — it can be rewritten from outside",
    "主題を指して読むか、宣言をそろえる":
        "read against a named subject, or make the declarations agree",
    "無し": "none",
    "catalog にある番号から選ぶ": "choose a number listed in the catalog",
    "JSON として読めない": "not readable as JSON",
    "モデルに出力を JSON 一つだけにさせる(プロンプトの規律4)":
        "make the model answer with one JSON object and nothing else "
        "(prompt discipline 4)",
    # skirt drafting: formula names and texts (declared on the block)
    "ウエスト幅 (1枚)": "waist width (per panel)",
    "ヒップ幅 (1枚)": "hip width (per panel)",
    "ヒップの位置": "hip line position",
    "ウエストの楽": "waist ease",
    "ヒップの楽": "hip ease",
    "waist / 2 + ウエストの楽": "waist / 2 + waist ease",
    "max(hip / 2 + ヒップの楽, ウエスト幅)":
        "max(hip / 2 + hip ease, waist width)",
    "skirt_length の実測そのまま": "the measured skirt_length, as-is",
    "ウエストから hip_depth 下がったところ": "hip_depth below the waist",
    "ヒップ幅 × flare_ratio": "hip width × flare_ratio",
    "+2.0cm（**既定**）": "+2.0 cm (**tool default**)",
    "1.35（Aライン。**この道具が決めた値**で、服飾の標準ではない）":
        "1.35 (A-line. **a value this tool chose**, not an industry "
        "standard)",
    "1.02（ストレート。**この道具が決めた値**)":
        "1.02 (straight. **a value this tool chose**)",
    "1枚あたり +2.0cm。ゴムに寄せる分（**既定**。生地とゴムで変わる）":
        "+2.0 cm per panel, gathered onto elastic (**default**; varies "
        "with fabric and elastic)",
    "20.0cm（**この道具の既定**。標準では約18-20cmとされるが、"
    "出典を確認していない）":
        "20.0 cm (**this tool's default**. Commonly cited as about "
        "18–20 cm; the source is unverified)",
    '1"相当': 'about 1"',
    "ゴム通し分。**既定・出典未確認**":
        "elastic casing. **a tool default; the source is unverified**",
    # skirt notes
    "これはこの道具の簡易製図です。式は全て出しているので、違うと"
    "思ったら式を見てください。":
        "This is this tool's own simplified drafting. Every formula is "
        "printed — if it looks wrong, argue with the formula.",
    "型紙は裁つものなので、足りない寸法を既定で埋めません":
        "A pattern is cut, so missing measurements are never filled "
        "with defaults",
    "脇が合わないと脇が縫えない":
        "if the side seams do not match, the sides cannot be sewn",
    "脇線(右): 前 ↔ 後": "side seam (right): front ↔ back",
    "脇線(左): 前 ↔ 後": "side seam (left): front ↔ back",
    "辺の弧長の中点。前後で対にして、縫いずれを見つけるための印":
        "the midpoint of the edge's arc length. Paired front-to-back so "
        "sewing drift shows up as a mismatch",
    # parts / composed garments
    "waist: bodice:1 ↔ skirt:1 (前身頃↔スカート前)": "waist: bodice ↔ skirt front",
    "waist: bodice:1 ↔ skirt:1 (後身頃↔スカート後)": "waist: bodice ↔ skirt back",
    "armhole_l: bodice:1 ↔ sleeve:1 (前身頃↔袖(左))": "armhole: bodice ↔ sleeve (front)",
    "armhole_l: bodice:1 ↔ sleeve:1 (後身頃↔袖(左))": "armhole: bodice ↔ sleeve (back)",
    "neck: bodice:1 ↔ cape:1 (前身頃↔ケープ)": "neckline: bodice ↔ cape (front)",
    "neck: bodice:1 ↔ cape:1 (後身頃↔ケープ)": "neckline: bodice ↔ cape (back)",
    "これはこの道具の簡易製図です。式は全て出しています。":
        "This is this tool's own simplified drafting. Every formula is "
        "printed.",
    "max(hip / 4 + 2.0, ウエスト幅)": "max(hip / 4 + 2.0, waist width)",
    "ウエスト(カーシング)": "waist (elastic casing)",
    "ウエスト幅 (1/4)": "waist width (quarter)",
    "ヒップ幅 (1/4)": "hip width (quarter)",
    "身頃幅 (胸, 1枚)": "bodice width at chest (per panel)",
    "身頃幅 (ウエスト, 1枚)": "bodice width at waist (per panel)",
    "襟ぐり幅": "neckline width",
    "襟ぐり深さ": "neckline depth",
    "肩線: 前 ↔ 後": "shoulder seam: front ↔ back",
    "脇線: 前 ↔ 後": "side seam: front ↔ back",
    "脇線: スカート前 ↔ スカート後": "side seam: skirt front ↔ skirt back",
    "袖下線: 袖(左) の筒": "underarm seam: closes left sleeve into a tube",
    "袖下線: 袖(右) の筒": "underarm seam: closes right sleeve into a tube",
    "接続する辺の長さ差。**差が出るのが普通** — ギャザーの分だけ"
    "長い側が寄る":
        "length difference across a joined edge. **A difference is "
        "normal** — the longer side gathers onto the shorter",
    "縫い合わせる辺の長さ差": "length difference of the edges being sewn",
    # --- the ledger's own refusal, which the approval gate returns as a
    # value. It has been in garment.py since V60 and no output path swept it
    # until the look loop started answering with it.
    "UNKNOWN_NO_ADOPTER: 採用者の名前が要る。"
    "誰が通したか辿れない採用は、間違いの責任が消える":
        "UNKNOWN_NO_ADOPTER: an adoption needs the name of the person making "
        "it. An adoption nobody can be traced to loses the responsibility "
        "for a mistake",
    # --- compose.graph_from: the retrieved structure becomes a parts graph
    "ケープワンピース": "cape dress",
    "構造は instances を持つ辞書です":
        "a structure is a dict carrying instances",
    "検索が部品を1つも指していない。先に per_part で部品ごとに聞く":
        "the retrieval named no part at all. Ask per_part first, part by "
        "part",
    "同じ部品の同じ側面に別々の値が来ている。"
    "どちらかを選んで建てると、選んだことが記録に残らないまま承認を集めます":
        "one part has two different values for one aspect. Building either "
        "of them collects approval without recording that a choice was made",
    "割れた側面を人が裁定してから建てる":
        "have a person settle the split aspect, then build",
    "引ける部品だけで建てると、検索が指した服とは別の服に承認が出ます":
        "building only the draftable parts collects approval for a garment "
        "that is not the one the retrieval named",
    "unknown の部品は parts.PART_VOCAB に足すか new_part として提案する。"
    "undraftable の部品は garment_parts に手続きを書き、"
    "parts.PART_GEOMETRY に登録する。いま引けるのは known にある部品だけです":
        "add the parts under `unknown` to parts.PART_VOCAB or propose them "
        "as new_part; write a procedure in garment_parts for the parts under "
        "`undraftable` and register it in parts.PART_GEOMETRY. What can be "
        "drafted today is listed under `known`",
    "検索で得た構造。画素からではありません":
        "the retrieved structure. Not the pixels",
    "名前は (語彙の宣言順, 中身) で決まります。入力の並びは番号に入りません":
        "names come from (vocabulary order, content). The order of the input "
        "does not enter the numbering",
    "種類名はこの組合せのラベルです。能力は部品の側にあります":
        "the garment-type name is a label for this combination. The "
        "capability lives in the parts",
    "部品の組合せから組み立てました。種類の登録はありません":
        "assembled from parts. No garment type was registered",
    "繋がっておらず、処理も決まっていない口があります。"
    "黙って閉じた服に見せません":
        "some ports are neither connected nor given a finish. The tool "
        "will not pretend the garment is closed",
    "接続するか、port_finish で わ(fold)か 端処理(free) を決める":
        "connect the port, or declare it in port_finish as fold or free",
    # coat formulas kept company by the skirt's own:
    "2.0（固定）": "2.0 (fixed)",
    "2.0cm（この道具の既定）": "2.0 cm (this tool's default)",
    "身頃幅 − 1.0（固定）": "bodice width - 1.0 (fixed)",
    "身頃幅 − 1.6（固定） ※ 前後の袖ぐりの違いはこの 0.6cm だけ":
        "bodice width - 1.6 (fixed). This 0.6 cm is the only difference "
        "between the front and back armhole",
    "shoulder / 2 ※ shoulder は肩幅の全長とみなす":
        "shoulder / 2, taking `shoulder` to be the full across-shoulder width",
    "袖山の幅 × 0.5": "cap width x 0.5",
    "袖ぐり深さ × 0.55": "armhole depth x 0.55",
    "袖ぐり深さ × 0.78": "armhole depth x 0.78",
    "袖山の高さ × 0.22": "cap height x 0.22",
    "袖山の幅の解き方": "how the cap width is solved",
    "袖山の長さが「袖ぐりの合計 + いせ込み」になるよう解く":
        "solved so the cap length equals the combined armhole length plus ease",
    "二分探索 60 回、範囲 (0.1, 袖ぐりの合計)":
        "60 bisection steps over the range (0.1, combined armhole length)",
    "反復の上限に達した": "hit the iteration cap",
    "段を増やすか、反復を増やす": "use a finer mesh, or more iterations",
    "力のかかる曲線 (armscye)": "load-bearing curve (armscye)",
    "力のかからない曲線 (neckline)": "curve under no load (neckline)",
    "肩線・脇線に準じる": "same as the shoulder and side seams",
    "並価格帯の裾に準じる": "as for a hem in the mid price range",
    "並価格帯の裾。**裾は減らさない**":
        "a hem in the mid price range. **Never reduce the hem**",
    "**わ**（中心）なので縫い代を付けない":
        "this is a fold at the centre, so no allowance is added",
    "肩点": "shoulder point",
    "袖ぐりの肩側の端点": "the shoulder end of the armhole",
    "袖ぐりの脇側の端点": "the underarm end of the armhole",
    "袖山の頂点。袖ぐりの肩点と組む":
        "the apex of the cap; pairs with the armhole's shoulder point",
    "袖山の端点。袖ぐりの脇と組む":
        "the end of the cap; pairs with the armhole's underarm",
    "振りと肩点の弧長の中点。いせを配る区間を割るため":
        "the arc-length midpoint between the pitch point and the shoulder "
        "point, used to split the interval the ease is distributed over",
    "たて地の向き。耳(selvage)と平行に置く":
        "grain direction. Lay it parallel to the selvage",
    "線の位置に意味はありません。意味を持つのは向きだけです":
        "where the line sits carries no meaning. Only its direction does",
    "切り込みが縫い代の半分を超えると弱点になる":
        "a notch cut deeper than half the seam allowance becomes a weak point",
    "縫い代は入っていません。引いたのは出来上がり線です。":
        "seam allowance is not included. What is drawn is the sewing line.",
    "縫い代は値として持ちません。出来上がり線と裁ち切り線の差が縫い代です。"
    "片方だけ持つと復元できません":
        "seam allowance is not stored as a value. It is the difference between "
        "the sewing line and the cut line. Keeping only one of them makes the "
        "other unrecoverable",
    "型紙は寸法からの派生で、実物の型紙を見たものではありません":
        "the pattern is derived from measurements. Nobody has looked at a real "
        "pattern for this garment",
    "型紙は裁つものなので、足りない寸法を既定で埋めません。"
    "立体(見るもの)とはここが違います":
        "a pattern gets cut, so a missing measurement is never filled in with a "
        "default. This is where it differs from the solid, which is only looked at",
    "型紙が引けていないので縫えません":
        "there is no pattern to sew, so nothing was sewn",
    "これはこの道具の簡易製図で、文化式・ドレメ式などの公表された製図法では"
    "ありません。式は全て出しているので、違うと思ったら式を見てください。":
        "this is the tool's own simplified block, not Bunka, Doreme or any "
        "other published drafting system. Every formula is printed, so if you "
        "disagree with it, look at the formulas.",
    "層番号は内部の呼び名です。ASTM D6673-10 は 2019年1月に廃止され後継が"
    "ないので、規格対応は名乗りません":
        "layer numbers are an internal naming convention. ASTM D6673-10 was "
        "withdrawn in January 2019 with no replacement, so no conformance to "
        "it is claimed",
    "合印は実物どおり 2.5mm で描いています。1:1 で刷れば見えます":
        "notches are drawn at their real 2.5 mm. Print at 1:1 and you will see them",
    "合印は二枚の間の約束です。相手のいない印は通していません。いせは合印で"
    "区切った区間ごとに配っていて、脇の下には入れません":
        "a notch is a promise between two pieces. A notch with no partner is "
        "not passed through. Ease is distributed per interval between notches, "
        "and none is placed under the arm",
    "前後の肩線が合わないと肩が縫えない":
        "if the front and back shoulder seams do not match, the shoulder cannot "
        "be sewn",
    "前後の脇線が合わないと脇が縫えない":
        "if the front and back side seams do not match, the side cannot be sewn",
    "袖山は袖ぐりよりやや長いのが普通(いせ込み)。短ければ入らず、"
    "長すぎれば縫い込めない":
        "the cap is normally a little longer than the armhole, which is the "
        "ease. Too short and it will not go in; too long and it cannot be "
        "eased in",
    "前後で同じ点から引いているので、差は構成上ゼロです。"
    "通っても何も確かめていません":
        "front and back are drawn from the same points, so the difference is "
        "structurally zero. Passing this confirms nothing",
    "袖山の幅はこの差が いせ込み になるまで二分探索で決めています。"
    "だからこれは型紙の検算ではなく、探索が収束したことの確認です":
        "the cap width is bisected until this difference equals the ease, so "
        "this is not a check on the pattern, only a confirmation that the "
        "search converged",
    "縫い目は型紙の名前付き辺から決めています。近さで勝手に繋いでいません":
        "seams come from the pattern's named edges. Nothing is joined just "
        "because it happened to be nearby",
    "縫製の実務公差 1mm。目の位置に頂点を置いたので、残るのは軟拘束の残差だけ":
        "1 mm practical sewing tolerance. A vertex is placed at each stitch "
        "position, so what remains is only the soft-constraint residual",
    "縫い目が閉じても服はまだ落ち続けます。ここが True なのは縫い目について"
    "だけで、形が定まったという意味ではありません":
        "a garment keeps falling long after its seams close. True here refers "
        "to the seams only. It does not mean the shape has settled",
    "落とした形は生成物です。観測の出典にはできません。":
        "the draped shape is generated. It cannot be cited as the source of an "
        "observation.",
    "検査が通らなかったので形を返していません。順序や初期配置が決めた皺を、"
    "物理として見せないためです":
        "a check failed, so no shape is returned. Wrinkles decided by update "
        "order or by the starting positions must not be presented as physics",
    "頂点の更新順で形が変わるなら、それは物理ではなく順序の産物です":
        "if the shape changes with the order vertices are updated, what you are "
        "looking at is the order, not physics",
    "初期配置で形が変わるなら、それは局所最小で、どちらを見せても恣意的です":
        "if the shape changes with the starting positions it is a local "
        "minimum, and showing either one is arbitrary",
    "粗中細で同じ形に寄らないなら、見ているのは解像度の産物です":
        "if coarse, medium and fine meshes do not converge on the same shape, "
        "what you are looking at is the resolution",
    "織物は自重で数%しか伸びません。大きく伸びるなら、計算ではなく物性の"
    "置き方が違います":
        "a woven fabric stretches only a few percent under its own weight. A "
        "large stretch means the material properties are wrong, not the maths",
    "位置ベース(PBD)には減少するエネルギーが定義されないので、この検査は"
    "勾配を降りる解法にだけ意味があります":
        "position-based dynamics has no defined decreasing energy, so this "
        "check only means anything for a gradient-descent solver",
    "始点を増やして最小エネルギーのものを取るか、割れたまま両方を人に見せる":
        "add more starting points and take the lowest-energy result, or leave "
        "it split and show a person both",
    "**片方を選んでいません。** 両方の形を返しています":
        "**neither one has been chosen.** Both shapes are returned",
    "同じ場所の実測が食い違っています。どちらかを勝手に採りません":
        "two measurements of the same spot disagree. Neither is adopted for you",
    "映像からは特定不能。実物・購入品・依頼者に確認":
        "cannot be determined from footage. Check the real garment, a purchased "
        "sample, or ask the client",
    "実物に触れるか、類似品の仕様を取り寄せる":
        "handle the real garment, or obtain the spec of a comparable one",
    "背面が映るカットを探す / 依頼者に確認する":
        "find a shot showing the back, or ask the client",
    "背面のカット、または類似品の実物で確認する":
        "check with a shot of the back, or with a comparable garment in hand",
    "腰から下が映るカットを探す": "find a shot showing below the waist",
    "裾・袖口の返りが映るカットを探す":
        "find a shot showing the hem and cuff turn-back",
    "生地の剛性を実測で入れるか、仮定の式を直す":
        "supply a measured fabric stiffness, or fix the assumed formula",
    "まだ渡していない（未取得ではない）":
        "not handed over yet. This is not the same as not obtained",
    "まだ渡していない（調べた結果ゼロ、ではない）":
        "not handed over yet. This is not a search that returned nothing",
    "開き直す参照が付いていない": "no reference attached that can be reopened",
    "01-05 の確定欄以外は裁断の根拠にしないこと":
        "do not cut against anything except the settled fields in 01-05",
    "confirmed 以外を裁断の根拠にしないこと。inferred と proposal は観測ではない":
        "do not cut against anything but confirmed. Inferred and proposal are "
        "not observations",
    "derived は比率×基準の計算値で、実測ではない。裁つ前に実測で確かめる":
        "derived is a ratio times a base, calculated rather than measured. "
        "Confirm it by measuring before you cut",
    # The SVG note block is hard-wrapped across several <text> elements and
    # two separate notes can end up geometrically adjacent, so the clause
    # splitter needs each sentence on its own as well as the combined form.
    "実線=出来上がり線 / 破線=裁ち切り線 / 青=合印(単は前・双は後) / 緑=布目線。"
    "縮尺 1:1(cm)":
        "solid = sewing line / dashed = cut line / blue = notch (single front, "
        "double back) / green = grain. Scale 1:1 (cm)",
    "これはこの道具の簡易製図で、文化式・ドレメ式などの公表された製図法ではありません":
        "this is the tool's own simplified block, not Bunka, Doreme or any "
        "other published drafting system",
    "式は全て出しているので、違うと思ったら式を見てください":
        "every formula is printed, so if you disagree with it, look at the formulas",
    "層番号は内部の呼び名です":
        "layer numbers are an internal naming convention",
    "ASTM D6673-10 は 2019年1月に廃止され後継がないので、規格対応は名乗りません":
        "ASTM D6673-10 was withdrawn in January 2019 with no replacement, so no "
        "conformance to it is claimed",
    "合印は実物どおり 2.5mm で描いています":
        "notches are drawn at their real 2.5 mm",
    "1:1 で刷れば見えます": "print at 1:1 and you will see them",
    "採用するか、観測で確かめる":
        "adopt it, or confirm it with an observation",
    "計算値。実測ではない": "a calculated value, not a measurement",
    "更新順は Jacobi なので構成上効きません":
        "the update is Jacobi, so the order cannot matter by construction",
    "通ったことは何の確認にもなりません": "passing it confirms nothing",
    "縫って落とした形は生成物です": "the sewn and draped shape is generated",
    "観測の出典にはできません": "it cannot be cited as the source of an observation",
    "検査が通らなかったので形を返していません":
        "a check failed, so no shape is returned",
    "初期配置が決めた皺を、物理として見せないためです":
        "wrinkles decided by the starting positions must not be shown as physics",
    "Contested — 人が決めること": "Contested - for a person to decide",
    "Unknowns — 裁断前に潰すこと": "Unknowns - close these before cutting",
    "前振り: 本来は前ゴージから2cm上だが、**この製図には衿とゴージが無い**。"
    "規則が使えないので後振りと同じ高さ (y=10.00cm) で代用している。"
    "実測ではなく代用":
        "front pitch point: properly this sits 2 cm above the front gorge, but "
        "**this block has no collar and no gorge**. The rule cannot be applied, "
        "so the back pitch height (y=10.00 cm) is used instead. A substitute, "
        "not a measurement",
}


# ---------------------------------------------------------------------------
# Walking a result
# ---------------------------------------------------------------------------

def _clauses(s: str) -> Optional[str]:
    """Translate a multi-sentence string by translating each clause.

    The engine composes some refusals out of clauses that also appear on their
    own. Splitting on the full stop and translating each part means those do
    not each need their own table entry — but only if **every** clause is
    known. One unknown clause and this returns None, so a half-English
    sentence never escapes.
    """
    if "。" not in s.strip("。"):
        return None
    parts = [p for p in s.split("。") if p.strip()]
    if len(parts) < 2:
        return None
    done = [SENTENCES.get(p) or _rule(p) or _term(p) for p in parts]
    if not all(done):
        return None
    out = [d.rstrip(".") for d in done if d]
    return ". ".join(x[:1].upper() + x[1:] if x else x for x in out) + "."


def _segment(s: str) -> Optional[str]:
    """Translate a run of sentences that has no separator to split on.

    The SVG note block puts unrelated notes on adjacent lines, so rejoining a
    paragraph can butt one sentence straight against the next with no full stop
    between them. Splitting on punctuation cannot see that boundary, so this
    walks the string taking the longest known sentence at each step. If the
    whole string is not consumed it gives up, so a partial match never escapes
    as half-translated English.
    """
    keys = sorted((k for k in SENTENCES if len(k) > 3), key=len, reverse=True)
    rest, out, guard = s, [], 0
    while rest and guard < 64:
        guard += 1
        rest = rest.lstrip("。 ")
        if not rest:
            break
        for k in keys:
            if rest.startswith(k):
                out.append(SENTENCES[k])
                rest = rest[len(k):]
                break
        else:
            return None
    if rest or not out:
        return None
    return ". ".join(x.rstrip(".")[:1].upper() + x.rstrip(".")[1:]
                     for x in out) + "."


def string(s: str, lang: str = "en") -> str:
    """Translate one string. Unknown Japanese comes back unchanged."""
    if lang == "ja" or not isinstance(s, str) or not has_japanese(s):
        return s
    return (SENTENCES.get(s) or _rule(s) or _term(s)
            or _clauses(s) or _segment(s) or s)


_SVG_TEXT = re.compile(r"(<text\b[^>]*>)(.*?)(</text>)", re.S)
_ATTR = re.compile(r'(\w[\w-]*)="([^"]*)"')

# A Japanese glyph is about one font-size wide; a Latin one about half that.
# `to_svg` wraps its notes to fit, so an English line fits roughly twice the
# characters. Re-wrapping at the Japanese count would leave the paragraph
# occupying half the width it should.
_WRAP_RATIO = 2.05


def _attrs(tag: str) -> Dict[str, str]:
    return {m.group(1): m.group(2) for m in _ATTR.finditer(tag)}


def _wrap(text: str, width: int) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if len(trial) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [""]


def svg(document: str, lang: str = "en") -> str:
    """Translate a pattern SVG. Geometry is never touched.

    Two things happen here that a plain string swap cannot do.

    `to_svg` hard-wraps its long notes across several `<text>` elements, so a
    fragment on its own is not a sentence and has no translation. Consecutive
    elements sharing an x, a font-size and a fill are rejoined into the
    paragraph they came from, translated as one, and re-wrapped for English —
    which needs about twice the characters per line at the same font size.

    Re-wrapping can produce more or fewer lines than the Japanese did, so the
    text below a paragraph is shifted and the viewBox height grows to match.
    Every coordinate that belongs to the pattern itself is left alone.
    """
    if lang == "ja":
        return document

    items = list(_SVG_TEXT.finditer(document))
    if not items:
        return document

    groups: List[List[Any]] = []
    for m in items:
        a = _attrs(m.group(1))
        key = (a.get("x"), a.get("font-size"), a.get("fill"))
        y = float(a.get("y", 0))
        if groups:
            prev = groups[-1][-1]
            pa = _attrs(prev.group(1))
            pkey = (pa.get("x"), pa.get("font-size"), pa.get("fill"))
            dy = y - float(pa.get("y", 0))
            if key == pkey and 0 < dy <= 6.0:
                groups[-1].append(m)
                continue
        groups.append([m])

    out, cursor, shift, extra = [], 0, 0.0, 0.0
    for g in groups:
        joined = "".join(x.group(2) for x in g)
        en = string(joined, lang)
        first = _attrs(g[0].group(1))
        size = float(first.get("font-size", 3))
        y0 = float(first.get("y", 0))
        dy = 4.5
        if len(g) > 1:
            dy = float(_attrs(g[1].group(1)).get("y", 0)) - y0
        width = int(len(joined) / max(len(g), 1) * _WRAP_RATIO) if len(g) > 1 else 0
        lines = _wrap(en, width) if width and en != joined else [en]

        out.append(document[cursor:g[0].start()])
        for i, line in enumerate(lines):
            tag = g[0].group(1)
            tag = re.sub(r'y="[\d.-]+"', f'y="{y0 + shift + i * dy:.2f}"', tag)
            out.append(f"{tag}{line}</text>")
            if i < len(lines) - 1:
                out.append("\n")
        cursor = g[-1].end()
        grew = (len(lines) - len(g)) * dy
        shift += grew
        extra = max(extra, shift)
    out.append(document[cursor:])
    doc = "".join(out)

    if extra > 0:
        def bump(m):
            w, h = m.group(1), float(m.group(2))
            return f'height="{h + extra:.0f}" viewBox="0 0 {w} {h + extra:.0f}"'
        doc = re.sub(r'height="[\d.]+" viewBox="0 0 ([\d.]+) ([\d.]+)"', bump,
                     doc, count=1)
    return doc


def translate(value: Any, lang: str = "en") -> Any:
    """Walk any engine result and translate every string, keys included."""
    if lang == "ja":
        return value
    if isinstance(value, str):
        if value.lstrip().startswith("<svg"):
            return svg(value, lang)
        return string(value, lang)
    if isinstance(value, dict):
        return {string(k, lang) if isinstance(k, str) else k:
                translate(v, lang) for k, v in value.items()}
    if isinstance(value, list):
        return [translate(v, lang) for v in value]
    if isinstance(value, tuple):
        return tuple(translate(v, lang) for v in value)
    return value


def _strings_in(s: str) -> List[str]:
    """The translatable strings inside a value.

    Normally that is the value itself. An SVG document is the exception: its
    labels live in text nodes, so counting the whole document as one string
    would report a pattern with every label translated as "one string missing".
    """
    if s.lstrip().startswith("<svg"):
        return [m.group(2) for m in _SVG_TEXT.finditer(s)]
    return [s]


def missing(value: Any) -> List[str]:
    """Every Japanese string in `value` that the table cannot translate.

    This is the honest edge of this module. If it returns anything, the English
    output is incomplete at exactly those strings.
    """
    out: List[str] = []

    def walk(v: Any) -> None:
        if isinstance(v, str):
            for part in _strings_in(v):
                if has_japanese(part) and string(part) == part:
                    out.append(part)
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(k)
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(value)
    seen, uniq = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def coverage(value: Any) -> Tuple[int, int]:
    """(translated, total) Japanese strings found in `value`."""
    total: List[str] = []

    def walk(v: Any) -> None:
        if isinstance(v, str):
            total.extend(p for p in _strings_in(v) if has_japanese(p))
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(k)
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(value)
    uniq = list(dict.fromkeys(total))
    return len(uniq) - len(missing(value)), len(uniq)

# ---------------------------------------------------------------------------
# The browser application's own chrome
# ---------------------------------------------------------------------------
#
# The page is one HTML document with template literals in it, so parsing it to
# swap labels would be fragile. These are exact substrings of that source,
# replaced longest-first at serve time. Short labels carry enough surrounding
# markup to be unambiguous — "値" alone would also match inside other words.

APP_UI: Dict[str, str] = {
    "/* 図に載せるのは**空間的な部位だけ**。fabric と lining は場所を持たない":
        "/* Only parts that occupy space go on the drawing. fabric and lining "
        "have no place,",
    "ので図から外し、下の材料帯に置く — 存在しない場所を指させると、":
        "so they are taken off it and put in the materials strip below. Point "
        "at a place that does not exist and",
    "読み手は「そこを見た」と誤解する。 */":
        "the reader will think somebody looked there. */",
    "/* ---- 中央: 服の図。部位をクリックすると右が変わる ---- */":
        "/* ---- centre: the garment. Click a part and the right pane follows "
        "---- */",
    "/* ---- 右: 構造インスペクタ(チャットではない) ---- */":
        "/* ---- right: the structure inspector. Not a chat ---- */",
    "/* ---- 下段: 証拠のタイムラインと配分 ---- */":
        "/* ---- bottom: the evidence timeline and where it came from ---- */",
    "// 部位の状態 = 最も弱い側面に引きずられる。強い方に丸めない。":
        "// A part's state is dragged down to its weakest aspect. Never rounded up.",
    "];                 // 場所を持たない部位":
        "];                 // parts with no place",
    "};        // 図の別名 → 台帳の部位":
        "};        // drawing alias -> ledger part",
    "色は状態です。緑=確定 / 赤=割れている / 橙=推論 / 灰=未観測。":
        "Colour is state. Green = settled / red = contested / orange = inferred "
        "/ grey = not observed.",
    "クリックすると右の構造インスペクタが変わります。":
        "Click one and the structure inspector on the right follows.",
    "確度はモデルの点数ではなく、": "Confidence is not a model score. It is ",
    "<b>独立した観測が何本一致したか</b>です。":
        "<b>how many independent observations agreed</b>.",
    "UNKNOWN は失敗ではなく、次に探すもの。":
        "UNKNOWN is not a failure. It is the next thing to go and look for.",
    "証拠がまだありません。右のインスペクタから記録してください。":
        "No evidence yet. Record some from the inspector on the right.",
    "観測が食い違っている。片方を勝たせていない — 人が決める":
        "the observations disagree. Neither has been allowed to win - a person "
        "decides",
    "件の独立した観測が一致": " independent observations agree",
    "側面 · 状態は最も弱い側面に合わせる":
        " aspects &middot; the state follows the weakest of them",
    "材料は場所を持たないので図に載せない":
        "materials have no place, so they are not on the drawing",
    "設定画・スクリーンショット": "Reference art and screenshots",
    "実際に作れる服(未生成)": "A garment you could actually make (not generated)",
    "Veraが持っている構造": "The structure the ledger holds",
    "次に何をすれば閉じるか": "What would close this",
    "直接の観測が無い": "no direct observation",
    "採用する人の名前(記録に残ります)": "Name of the person adopting (it is kept)",
    "構造から推した(観測ではない)": "inferred from the structure, not observed",
    "出典 (cut 0:12:05 / URL)": "Source (cut 0:12:05 / URL)",
    "証拠として採用": "Adopt as evidence",
    "印刷 / PDF": "Print / PDF",
    'placeholder="値"': 'placeholder="Value"',
    'placeholder="注記"': 'placeholder="Note"',
    '<option value="observation">観測</option>':
        '<option value="observation">Observation</option>',
    '<option value="inference">推論</option>':
        '<option value="inference">Inference</option>',
    '<option value="proposal">提案</option>':
        '<option value="proposal">Proposal</option>',
    '<span class="ev">提案</span>': '<span class="ev">proposal</span>',
    '<span class="ev">観測</span>': '<span class="ev">observation</span>',
    '<span class="ev">推論</span>': '<span class="ev">inference</span>',
    'onclick="add()">置く</button>': 'onclick="add()">Record</button>',
    ">記録する</div>": ">Record</div>",
    "'none'\">閉じる</button>": "'none'\">Close</button>",
    '<div class="ev">根拠: ': '<div class="ev">basis: ',
    "(出所の申告。事実ではない)": "(a stated origin, not a fact)",
    "` · 採用: ${esc(s.adopted_by)}`": "` &middot; adopted by ${esc(s.adopted_by)}`",
    '<div class="hint">なし</div>': '<div class="hint">none</div>',
}


def page(html: str, lang: str = "en") -> str:
    """Translate the browser application's own chrome.

    Longest key first, so a short label never eats part of a longer phrase.
    """
    if lang == "ja":
        return html
    for ja in sorted(APP_UI, key=len, reverse=True):
        html = html.replace(ja, APP_UI[ja])
    return html
