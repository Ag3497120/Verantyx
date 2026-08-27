# -*- coding: utf-8 -*-
"""型紙を DXF R12(AC1009)で書き出す。**外部の CAD が読める唯一の出口。**

事前登録: なし(このモジュールに事前登録は無い)。理由: `garment_pattern` /
`garment_marks` が確定させた幾何を、別の書式に**移すだけ**で、新しい幾何や
規則を持ち込まない。事前登録が要るのは値を決める側で、ここは決めない。

## 標準への態度

ASTM D6673-10 ("DXF-AAMA")は **2019年1月に廃止され、後継が無い**。実務では
まだ「DXF-ASTM」と呼ばれることがあるが、生きた規格として引用はできない。
**このモジュールはその適合を名乗らない。** 書き出すのは素の DXF R12 —
グループコードの並びとして正しいテキストで、層の名前で意味を示す。ただし
全体は ASCII ではない: 日本語の裁片名は cp932 (Shift_JIS系) バイト列で書く
(下の「日本語の裁片名」節を参照)。

## なぜ標準ライブラリだけで書けるか

DXF R12 は「グループコード / 値」を1行ずつ交互に並べただけの平テキストで、
ライブラリが要る複雑さではない。``POLYLINE``/``VERTEX``/``SEQEND`` で1本の
折れ線、``LINE`` で直線、``TEXT`` で文字。ここに無いのは曲線近似(円弧を
持たない多角形描画のみ)と AutoCAD 拡張(ハッチング等)で、この型紙の出力に
どちらも要らない。

## 出来上がり線と裁ち切り線は別の曲線

``garment_pattern.draft`` が引くのは出来上がり線(縫う線)。裁ち切り線は
``garment_marks.offset_outline`` が縫い代ぶん外へ足したもので、**別の点列**。
両方を別の層に載せる — 層の名前だけで「どちらか」を CAD 側の人が読める
ようにする。層番号(``garment_marks`` の 1/4/7/14)は内部の呼び名であって、
この書き出しには持ち込まない。層は名前で識別する。

## 並べ方は平行移動だけ

後身頃・前身頃・袖はどれも中心・衿ぐり付近を原点に引かれているので、
そのまま書き出すと重なる(``to_svg`` が同じ理由で ``x_cursor`` を使っている
のと同じ事情)。ここでは裁片ごとに **X 方向の平行移動だけ** を足して横に
並べる。回転や反転は加えない — 加えなければ、書き出した頂点は
「型紙の座標 + 記録した移動量」で厳密に戻せる。移動量は返り値の
``placement`` に裁片名ごとに残す。

## 日本語の裁片名

**最初は ``\\U+XXXX`` エスケープで書いていたが、実測で外れていた。**
ezdxf(標準ライブラリではない、確かめるためだけに使った)で読み直すと、
``\\U+5F8C\\U+8EAB\\U+9803`` はそのままの文字列として返り、デコードされ
なかった —— この拡張は MTEXT の書式コードで、素の TEXT のグループコード1
には効かない。素の UTF-8 バイト列も試したが、コードページ宣言(HEADER の
``$DWGCODEPAGE``)が無い R12 は既定で ANSI 系にデコードされ、文字化けした
(実測: 「後身頃」が ``å¾Œèº«é\xa0ƒ`` になった)。

正しい道は **HEADER に ``$DWGCODEPAGE`` を ``ANSI_932``(Shift_JIS 系)と
宣言し、ファイル全体をその符号化(``cp932``、標準ライブラリの組み込み
コーデック)で書く**こと。ezdxf はこの宣言を読んで自動的に正しくデコード
した(実測で確認)。日本語の実務の DXF が実際にこの経路を使う。

## 文字は正しくても、字形が無ければ描けない

**符号化が合っていても、実機の CAD 画面には「?」が3つ並んだ。** ezdxf は
文字列として ``"後身頃"`` を正しく返す(パーサだから、字形は要らない)。
だが QCAD(実機のアプリケーション、標準ライブラリではない — 確かめる
ためだけに使った。ezdxf とは別の独立した経路)で同じファイルを開いて
描画すると、TEXT の3文字とも「?」だった。原因は符号化ではなく
**STYLE テーブルが無かったこと**。R12 は STYLE テーブルを省略しても
文法上は正当で、その場合 TEXT は暗黙に "STANDARD" スタイルを指すが、
"STANDARD" に何のフォントを割り当てるかは読む側の実装任せになる。
QCAD の既定フォントには漢字の字形が無く、全滅した(実測)。

STYLE テーブルに "STANDARD" を明示し、プライマリフォントを
``MS-Gothic``(和文 DXF が慣習的に使うフォント名 — この Mac に
"MS-Gothic" という名のフォントは存在しないが、フォント解決系がこの
名前を手がかりに CJK 対応フォントへ振り替えた)で書いたところ、同じ
QCAD で「後身頃」の3文字とも正しく描かれた(実測、TEXT 側は一切
変更していない — ``STYLE`` テーブルを足しただけで直った)。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

Pt = Tuple[float, float]

#: 層の名前。**名前だけで「出来上がり線」か「裁ち切り線」かが分かること**
#: が brief の要求で、内部の層番号(garment_marks の 1/4/7/14)はここへ
#: 持ち込まない。
LAYER_SEW = "SEWING_LINE"
LAYER_CUT = "CUT_LINE"
LAYER_NOTCH = "NOTCHES"
LAYER_GRAIN = "GRAIN_LINES"
LAYER_LABEL = "LABELS"

#: AutoCAD Color Index。7=既定(白/黒)、1=赤、5=青、3=緑。
_LAYER_COLOR = {LAYER_SEW: 7, LAYER_CUT: 1, LAYER_NOTCH: 5,
               LAYER_GRAIN: 3, LAYER_LABEL: 7}
_LAYER_ORDER = (LAYER_SEW, LAYER_CUT, LAYER_NOTCH, LAYER_GRAIN, LAYER_LABEL)

#: TEXT の既定スタイル名と、そこに割り当てるプライマリフォント。
#: 「文字は正しくても、字形が無ければ描けない」節を参照 — STYLE
#: テーブルを省いたまま実機(QCAD)で開くと、裁片名の漢字3文字とも
#: "?" になった(実測)。"STANDARD" を明示し、和文 DXF が慣習的に
#: 使う ``MS-Gothic`` をプライマリフォントにしたところ直った。
TEXT_STYLE = "STANDARD"
TEXT_FONT = "MS-Gothic"

UNMARKED = "UNKNOWN_UNMARKED_DRAFT"

#: 裁片どうしの間隔(cm)。並べ方の節を参照。
PAD_CM = 10.0
GAP_CM = 15.0


#: このファイルが宣言する文字符号化。ANSI_932 は Shift_JIS 系(cp932)。
#: HEADER の ``$DWGCODEPAGE`` に書く値と、ファイルを実際に書くときの
#: エンコーディング名は、この一つの定数から両方導く — 片方だけ変えると
#: 宣言と実体がずれて、相手の CAD は宣言を信じて文字化けする。
DWGCODEPAGE = "ANSI_932"
ENCODING = "cp932"


def _encodable(s: str) -> bool:
    """``ENCODING`` で書けない文字が混じっていないか。**既定で通さない。**

    cp932 に無い文字(絵文字や一部の拡張漢字)が裁片名に紛れ込むと、
    書き出しは例外で落ちるか、``errors`` の扱い次第で文字を silently
    落とす。どちらも「型付きで断る」の対極なので、書く前に確かめる。
    """
    try:
        s.encode(ENCODING)
        return True
    except UnicodeEncodeError:
        return False


def _num(v: float) -> str:
    """座標を固定小数4桁(0.1ミクロン)で書く。**負のゼロを出さない。**"""
    v = round(float(v), 4)
    if v == 0.0:
        v = 0.0
    return f"{v:.4f}"


def _polyline(layer: str, points: Sequence[Pt]) -> str:
    """閉じた POLYLINE。**始点を重複させない** — 閉フラグ(70=1)が
    最後の頂点から最初の頂点へ戻る辺を暗黙に足す。二重に書くと
    ``len(points)`` から頂点数を数える側が1個多く数える。
    """
    out = [f"0\nPOLYLINE\n8\n{layer}\n66\n1\n70\n1\n"]
    for x, y in points:
        out.append(f"0\nVERTEX\n8\n{layer}\n10\n{_num(x)}\n20\n{_num(y)}\n"
                   f"30\n0.0\n")
    out.append("0\nSEQEND\n")
    return "".join(out)


def _line(layer: str, a: Pt, b: Pt) -> str:
    return (f"0\nLINE\n8\n{layer}\n"
           f"10\n{_num(a[0])}\n20\n{_num(a[1])}\n30\n0.0\n"
           f"11\n{_num(b[0])}\n21\n{_num(b[1])}\n31\n0.0\n")


def _text(layer: str, x: float, y: float, height: float, s: str) -> str:
    return (f"0\nTEXT\n8\n{layer}\n"
           f"10\n{_num(x)}\n20\n{_num(y)}\n30\n0.0\n"
           f"40\n{height:.2f}\n1\n{s}\n")


def _header(bbox: Tuple[float, float, float, float]) -> str:
    minx, miny, maxx, maxy = bbox
    return (
        "0\nSECTION\n2\nHEADER\n"
        "9\n$ACADVER\n1\nAC1009\n"
        f"9\n$DWGCODEPAGE\n3\n{DWGCODEPAGE}\n"
        "9\n$INSBASE\n10\n0.0\n20\n0.0\n30\n0.0\n"
        f"9\n$EXTMIN\n10\n{_num(minx)}\n20\n{_num(miny)}\n30\n0.0\n"
        f"9\n$EXTMAX\n10\n{_num(maxx)}\n20\n{_num(maxy)}\n30\n0.0\n"
        "0\nENDSEC\n"
    )


def _tables() -> str:
    """LAYER と STYLE、2つのテーブルを持つ。**5層、これで brief の要求を
    満たす。** STYLE は当初 LAYER だけで済ませていたが、実機の CAD
    (QCAD)で裁片名の漢字が "?" になる実測を受けて足した ——
    ``TEXT_STYLE``/``TEXT_FONT`` の節、モジュール冒頭の「文字は正しくても、
    字形が無ければ描けない」を参照。"""
    parts = [f"0\nSECTION\n2\nTABLES\n0\nTABLE\n2\nLAYER\n70\n"
            f"{len(_LAYER_ORDER)}\n"]
    for name in _LAYER_ORDER:
        parts.append(f"0\nLAYER\n2\n{name}\n70\n0\n"
                     f"62\n{_LAYER_COLOR[name]}\n6\nCONTINUOUS\n")
    parts.append("0\nENDTAB\n")
    parts.append(
        "0\nTABLE\n2\nSTYLE\n70\n1\n"
        f"0\nSTYLE\n2\n{TEXT_STYLE}\n70\n0\n"
        "40\n0.0\n41\n1.0\n50\n0.0\n71\n0\n42\n1.0\n"
        f"3\n{TEXT_FONT}\n"
        "0\nENDTAB\n")
    parts.append("0\nENDSEC\n")
    return "".join(parts)


def to_dxf(marked_draft: Dict[str, Any]) -> Dict[str, Any]:
    """マーク済みの型紙(``garment_marks.apply`` の返り値)を DXF R12 にする。

    素の ``garment_pattern.draft`` の返り値(マーク前)を渡すと拒否する —
    裁ち切り線・合印・布目線が無ければ、出来上がり線しか書き出せず、
    この道具が exports と呼ぶものにならない。
    """
    if marked_draft.get("verdict") != "ANSWER":
        return dict(marked_draft)
    sa = marked_draft.get("seam_allowance")
    notches = marked_draft.get("notches")
    grains = marked_draft.get("grain")
    if not isinstance(sa, dict) or notches is None or grains is None:
        return {
            "verdict": UNMARKED,
            "how_to_close": "garment_marks.apply(draft) を通してから渡す",
            "why": "DXF は裁ち切り線・合印・布目線を書き出す道具で、"
                  "無印の型紙は出来上がり線しか持っていない",
        }
    unencodable = [p["name"] for p in marked_draft["pieces"]
                  if not _encodable(p["name"])]
    if unencodable:
        return {
            "verdict": "UNKNOWN_NAME_NOT_ENCODABLE",
            "which": unencodable,
            "how_to_close": (f"裁片名が {ENCODING} で書けません。"
                             "この文字集合に無い記号は使わないでください"),
            "why": (f"HEADER で $DWGCODEPAGE={DWGCODEPAGE} と宣言する以上、"
                   f"本文全体をその符号化で書く必要があり、書けない文字は"
                   f"黙って落とすのではなく事前に断ります"),
        }

    from .garment_marks import arc_lengths, at_arc

    grain_by_piece = {g["piece"]: g for g in grains}

    entities: List[str] = []
    placement: Dict[str, List[float]] = {}
    piece_report: List[Dict[str, Any]] = []
    notch_lines: Dict[str, int] = {}
    cut_line_missing: List[Dict[str, str]] = []
    bbox = [None, None, None, None]  # minx, miny, maxx, maxy

    def track(x: float, y: float) -> None:
        if bbox[0] is None:
            bbox[0] = bbox[2] = x
            bbox[1] = bbox[3] = y
        else:
            bbox[0] = min(bbox[0], x)
            bbox[2] = max(bbox[2], x)
            bbox[1] = min(bbox[1], y)
            bbox[3] = max(bbox[3], y)

    x_cursor = PAD_CM
    for p in marked_draft["pieces"]:
        name = p["name"]
        outline = [(float(q[0]), float(q[1])) for q in p["outline"]]
        off = sa.get(name, {})
        cut_ok = off.get("verdict") == "ANSWER"
        cut_line = ([(float(q[0]), float(q[1])) for q in off["cut_line"]]
                    if cut_ok else [])

        xs = [x for x, _y in outline] + [x for x, _y in cut_line]
        ys = [y for _x, y in outline] + [y for _x, y in cut_line]
        dx = x_cursor - min(xs)
        placement[name] = [round(dx, 4), 0.0]

        def T(q: Pt) -> Pt:
            return (q[0] + dx, q[1])

        sew_t = [T(q) for q in outline]
        for x, y in sew_t:
            track(x, y)
        entities.append(_polyline(LAYER_SEW, sew_t))

        if cut_ok:
            cut_t = [T(q) for q in cut_line]
            for x, y in cut_t:
                track(x, y)
            entities.append(_polyline(LAYER_CUT, cut_t))
        else:
            cut_line_missing.append({"piece": name,
                                     "verdict": off.get("verdict", "?")})

        edges = p["edges"]
        n_lines = 0
        for n in notches.get(name, []):
            edge = edges.get(n["edge"])
            if not edge:
                continue
            pl = edge["points"]
            total = arc_lengths(pl)[-1]
            base = at_arc(pl, n["arc_cm"])
            ahead = at_arc(pl, min(n["arc_cm"] + 0.5, total))
            back = at_arc(pl, max(n["arc_cm"] - 0.5, 0.0))
            tx, ty = ahead[0] - back[0], ahead[1] - back[1]
            L = math.hypot(tx, ty) or 1.0
            nx, ny = ty / L, -tx / L
            d = n["depth_cm"]
            # 単は1本、双は2本 — garment_pattern.to_svg と同じ幾何
            # (辺に直交する向きへ、切り込みの深さぶん)。
            offsets = (0.0,) if n["kind"] == "single" else (-0.3, 0.3)
            for o in offsets:
                bx = base[0] + tx / L * o
                by = base[1] + ty / L * o
                a = T((bx, by))
                b = T((bx + nx * d, by + ny * d))
                track(*a)
                track(*b)
                entities.append(_line(LAYER_NOTCH, a, b))
                n_lines += 1
        notch_lines[name] = n_lines

        g = grain_by_piece.get(name)
        if g:
            (gx1, gy1), (gx2, gy2) = g["line"]
            a, b = T((gx1, gy1)), T((gx2, gy2))
            track(*a)
            track(*b)
            entities.append(_line(LAYER_GRAIN, a, b))

        top_y = min(y for _x, y in outline)
        lx, ly = dx, top_y - 3.0
        track(lx, ly)
        entities.append(_text(LAYER_LABEL, lx, ly, 3.0, name))

        piece_report.append({"piece": name, "vertices": len(outline),
                             "cut_vertices": len(cut_line)})
        w = max(xs) - min(xs)
        x_cursor += w + GAP_CM

    if bbox[0] is None:
        bbox = [0.0, 0.0, 0.0, 0.0]

    body = ("0\nSECTION\n2\nENTITIES\n" + "".join(entities)
           + "0\nENDSEC\n")
    comment = ("999\nphotoloset garment export -- no ASTM D6673 / "
              "DXF-AAMA conformance is claimed (that standard was "
              "withdrawn 2019-01 with no replacement). Units: "
              "centimetres. Layer SEWING_LINE is the finished stitch "
              "line; CUT_LINE adds the seam allowance. Text is Shift_JIS "
              f"({ENCODING}), declared in $DWGCODEPAGE.\n")
    doc = (comment + _header(tuple(bbox)) + _tables() + body + "0\nEOF\n")

    return {
        "verdict": "ANSWER",
        "text": doc,
        "encoding": ENCODING,
        "dwgcodepage": DWGCODEPAGE,
        "dxf_version": "AC1009 (R12)",
        "units": "cm",
        "no_standard_conformance":
            "ASTM D6673-10 (DXF-AAMA)は2019年1月に廃止され後継が無いので、"
            "この書き出しは規格適合を名乗りません。R12のグループコードを"
            "そのまま書いた素のDXFです",
        "layers": {"sew": LAYER_SEW, "cut": LAYER_CUT, "notch": LAYER_NOTCH,
                  "grain": LAYER_GRAIN, "label": LAYER_LABEL},
        "placement": placement,
        "placement_note":
            "裁片ごとに X 方向へ平行移動しただけです(重ならないように"
            "並べるため)。回転・反転はしていないので、書き出した頂点から "
            "placement[名前][0] を引けば draft の座標に厳密に戻ります",
        "pieces": piece_report,
        "notch_lines": notch_lines,
        "cut_line_missing": cut_line_missing,
        "extents_cm": {"min": [round(bbox[0], 4), round(bbox[1], 4)],
                       "max": [round(bbox[2], 4), round(bbox[3], 4)]},
    }


def save(measures: Any, path: Any) -> Dict[str, Any]:
    """型紙を DXF に書き出し、**生成物の印を付ける**。"""
    from pathlib import Path

    from . import garment_pattern as _pattern
    from .garment import mark_generated
    from .garment_marks import apply as _marks

    draft = _pattern.draft(measures)
    marked = _marks(draft)
    out = to_dxf(marked)
    if out.get("verdict") != "ANSWER":
        return out
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # **バイトで書く、``write_text`` ではない。** $DWGCODEPAGE に
    # ANSI_932 と宣言した以上、ファイル全体がその符号化(cp932)で
    # なければ宣言と実体がずれる。既定の UTF-8 で書けば、罫線や層名の
    # ASCII 部分は同じに見えて、日本語の裁片名だけが文字化けする —
    # 実測で確かめた壊れ方(`_encodable` 節を参照)と同じ種類の食い違い。
    p.write_bytes(out["text"].encode(ENCODING))
    stamp = mark_generated(p)
    return {k: v for k, v in out.items() if k != "text"} | {
        "path": str(p), "stamp": str(stamp)}
