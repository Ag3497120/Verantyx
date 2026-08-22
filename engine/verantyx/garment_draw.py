# -*- coding: utf-8 -*-
"""設計図を**作図する**。生成しない。

事前登録: experiments/garment/PREREG7_DRAW.md

生成モデルに「このコートを描いて」と言うと、台帳に無いものが絵に入る —
袖の形、ボタンの数、丈。その絵を縫製師が見れば、台帳に無いものまで
指示として読む。だからここはモデルを呼ばない。

描くのは**台帳にある確定項目と寸法だけ**で、決定的に描く。同じ台帳から
は必ず同じ図が出る。これは作図であって生成ではない。

**未確定は描かない。** 描けない部位は輪郭に出さず、図の中に「未確定」
として名前だけ残す。想像で線を引くのが、この段で一番危ない。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .garment import OBSERVED, PARTS

#: 図の既定の比率。**寸法が無いときにだけ使う**。使ったことは図に書く。
#: 数字は作図用の目安で、採寸の代わりではない。
DEFAULT_RATIO = {
    "body_length": 1.00,     # 基準
    "shoulder": 0.47,
    "chest": 1.10,
    "sleeve_length": 0.62,
    "hem_width": 1.18,
}

#: 図に描ける部位。場所を持たないもの(fabric/lining)は描かない。
DRAWABLE = ("collar", "sleeve", "body", "pocket", "back")


def _confirmed_parts(ledger: Any) -> Dict[str, Dict[str, str]]:
    """確定した側面だけを部位ごとに集める。**推論と提案は入れない。**"""
    out: Dict[str, Dict[str, str]] = {}
    for row in ledger.spec()["confirmed"]:
        out.setdefault(row["part"], {})[row["aspect"]] = row.get("value", "")
    return out


def _dims(measures: Any) -> Tuple[Dict[str, float], List[str], str]:
    """使う寸法と、既定で補った箇所。"""
    used: Dict[str, float] = {}
    defaulted: List[str] = []
    unit = "cm"
    if measures is not None:
        sheet = measures.sheet()
        for row in sheet["measured"] + sheet["derived"]:
            used[row["spot"]] = float(row["value"])
            unit = row.get("unit") or unit
    base = used.get("body_length")
    if base is None:
        # 基準が無ければ図は比率だけで描く。**それを図に書く。**
        base = 100.0
        defaulted.append("body_length")
        used["body_length"] = base
    for spot, ratio in DEFAULT_RATIO.items():
        if spot not in used:
            used[spot] = round(base * ratio, 1)
            defaulted.append(spot)
    return used, defaulted, unit


def draw(ledger: Any, measures: Any = None) -> Dict[str, Any]:
    """SVG の設計図を作る。

    返すのは図そのものと、**何を描かなかったか**。描かなかったものが
    分からない図は、完成した設計図と区別が付かない。
    """
    confirmed = _confirmed_parts(ledger)
    dims, defaulted, unit = _dims(measures)

    drawn: List[str] = []
    skipped: List[Dict[str, str]] = []
    for part in DRAWABLE:
        if part in confirmed:
            drawn.append(part)
        else:
            aspects = PARTS.get(part, [])
            skipped.append({"part": part,
                            "why": "確定した側面が無い",
                            "aspects": ", ".join(aspects)})

    L = dims["body_length"]
    W = dims["chest"] / 2
    S = dims["shoulder"]
    SL = dims["sleeve_length"]
    HW = dims["hem_width"] / 2

    # 図の座標。**寸法をそのまま形にする** — 目分量を入れない。
    pad, scale = 40, 3.2
    cx = pad + W * scale
    top = pad + 20
    body = [(cx - S * scale / 2, top),
            (cx + S * scale / 2, top),
            (cx + HW * scale, top + L * scale),
            (cx - HW * scale, top + L * scale)]

    def poly(points, cls):
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        return (f'<polygon points="{d}" fill="none" stroke="#111" '
                f'stroke-width="1.4" data-part="{cls}"/>')

    # 画面表示は SVG を貼らずに**同じ座標から描き直す**。macOS の
    # NSImage は SVG の viewBox を再現しないことがあり、図の一部だけが
    # 出た(実地で踏んだ: 襟だけ見えてポケットと寸法が消えた)。
    # SVG は書き出し用の原本、shapes は画面用 — **同じ数字から作る**。
    shapes: List[Dict[str, Any]] = []
    # 紙に出る文字と画面に出る文字を**同じ配列から**作る。別々に書くと、
    # 書き出した図と画面の図が違うものになる。
    labels: List[Dict[str, Any]] = []

    def label(x, y, text, tone="ink"):
        labels.append({"x": round(x, 1), "y": round(y, 1),
                       "text": text, "tone": tone})

    def add(points, part):
        shapes.append({"part": part,
                       "points": [[round(x, 1), round(y, 1)]
                                  for x, y in points]})

    svg: List[str] = []
    w = int(cx + W * scale + pad)
    h = int(top + L * scale + pad + 90)
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" '
               f'height="{h}" viewBox="0 0 {w} {h}">')
    svg.append('<rect width="100%" height="100%" fill="#fff"/>')

    if "body" in drawn:
        svg.append(poly(body, "body")); add(body, "body")
    if "sleeve" in drawn:
        for sign in (-1, 1):
            x0 = cx + sign * S * scale / 2
            pts = [(x0, top + 4),
                   (x0 + sign * 26, top + 16),
                   (x0 + sign * 20, top + SL * scale),
                   (x0 - sign * 2, top + SL * scale)]
            svg.append(poly(pts, "sleeve")); add(pts, "sleeve")
    if "collar" in drawn:
        pts = [(cx - 26, top), (cx, top + 34), (cx + 26, top)]
        svg.append(poly(pts, "collar")); add(pts, "collar")
    if "pocket" in drawn:
        pts = [(cx - 58, top + L * scale * 0.62),
               (cx - 12, top + L * scale * 0.62),
               (cx - 12, top + L * scale * 0.70),
               (cx - 58, top + L * scale * 0.70)]
        svg.append(poly(pts, "pocket")); add(pts, "pocket")

    # 寸法の記入。既定で補ったものには印を付ける。
    y = top + L * scale + 24
    dim_text = (f'着丈 {dims["body_length"]}{unit}'
                f'{"（既定の比率）" if "body_length" in defaulted else ""}'
                f'　肩幅 {dims["shoulder"]}{unit}'
                f'{"（既定）" if "shoulder" in defaulted else ""}'
                f'　袖丈 {dims["sleeve_length"]}{unit}'
                f'{"（既定）" if "sleeve_length" in defaulted else ""}')
    svg.append(f'<text x="{pad}" y="{y}" font-size="12" fill="#111">'
               f'{dim_text}</text>')
    label(pad, y, dim_text, "ink")
    # **描かなかったものを図の上に書く。**
    if skipped:
        names = "、".join(s["part"] for s in skipped)
        warn = f"未確定のため描いていない: {names}"
        svg.append(f'<text x="{pad}" y="{y + 20}" font-size="12" '
                   f'fill="#b04">{warn}</text>')
        label(pad, y + 20, warn, "warn")
    foot = ("この図は台帳から作図したもので、生成物です。"
            "観測の出典にはできません。")
    svg.append(f'<text x="{pad}" y="{y + 40}" font-size="11" fill="#666">'
               f'{foot}</text>')
    label(pad, y + 40, foot, "quiet")
    svg.append("</svg>")

    return {
        "verdict": "ANSWER",
        "svg": "\n".join(svg),
        "shapes": shapes,
        "labels": labels,
        "canvas": {"width": w, "height": h},
        "drawn": drawn,
        "skipped": skipped,
        "dimensions": dims,
        "defaulted": sorted(defaulted),
        "unit": unit,
        "note": "台帳にある確定項目と寸法だけを描いた。"
                "未確定は線を引かず、名前だけ残している",
    }


def save(ledger: Any, path: Any, measures: Any = None) -> Dict[str, Any]:
    """図をファイルに書き、**生成物の印を付ける**。

    印が付いた画像から `garment_observe` はできない。描いた図を後から
    読み直すと、台帳の中身が観測の顔をして戻ってくる。
    """
    from pathlib import Path

    from .garment import mark_generated

    out = draw(ledger, measures)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(out["svg"], encoding="utf-8")
    stamp = mark_generated(p)
    return {**{k: v for k, v in out.items() if k != "svg"},
            "path": str(p), "stamp": str(stamp)}
