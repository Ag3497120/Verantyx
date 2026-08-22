# -*- coding: utf-8 -*-
"""立体を**組み立てる**。生成しない。

事前登録: experiments/garment/PREREG8_SOLID.md

2D の作図と同じ規律で、理由はより強い。**立体は線画より説得力がある** —
回して見た人は「背面はこうか」と読み取り、それが誰も観測していない形なら、
嘘は線より深く入る。

**これは着装シミュレーションではない。** 服の3Dで本当に有用なのは型紙を
身体に着せて布の落ち方を見ることで、それには型紙が要る。まだ無い。ここで
作れるのは寸法から起こしたプロポーションの立体だけで、布の挙動は一切
主張しない。

## 奥行き

胸囲は**周囲**であって幅ではない。幅と奥行きに分けるには比が要るが、
台帳に奥行きの実測は無い。既定の比で楕円にするしかなく、**それは仮定**
である。仮定を黙って形にすると実測から出た形と区別が付かないので、
出力に必ず書く。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from .garment_draw import DEFAULT_RATIO, _confirmed_parts, _dims

#: 断面を楕円にするときの奥行き/幅。**仮定であって実測ではない。**
#: 人体の胴はおおむねこの程度に扁平だが、この一着がそうだとは
#: 誰も測っていない。
ASSUMED_DEPTH_RATIO = 0.62

#: 断面の分割数。多くしても情報は増えない — 増えるのは面の数だけ。
SEGMENTS = 24

#: 立体にできる部位。**場所と体積を持つものだけ。**
SOLIDABLE = ("body", "sleeve", "collar")


def _ellipse(cx: float, cz: float, girth: float, y: float,
             depth_ratio: float) -> List[Tuple[float, float, float]]:
    """周囲から楕円の断面を作る。

    周囲 = π(a+b) の近似(ラマヌジャンの一次近似ではなく単純な平均周)で
    幅と奥行きを出す。**厳密さより、どこが仮定かが分かることを優先する。**
    """
    # girth ≒ π (a + b), b = a * ratio  →  a = girth / (π (1 + ratio))
    a = girth / (math.pi * (1.0 + depth_ratio))
    b = a * depth_ratio
    pts = []
    for i in range(SEGMENTS):
        t = 2.0 * math.pi * i / SEGMENTS
        pts.append((cx + a * math.cos(t), y, cz + b * math.sin(t)))
    return pts


def _tube(rings: List[List[Tuple[float, float, float]]],
          base: int) -> List[Tuple[int, int, int]]:
    """断面の輪をつないで三角形にする。端は塞がない — 服は筒である。"""
    faces: List[Tuple[int, int, int]] = []
    n = SEGMENTS
    for r in range(len(rings) - 1):
        for i in range(n):
            a = base + r * n + i
            b = base + r * n + (i + 1) % n
            c = base + (r + 1) * n + i
            d = base + (r + 1) * n + (i + 1) % n
            faces.append((a, c, b))
            faces.append((b, c, d))
    return faces


def build(ledger: Any, measures: Any = None) -> Dict[str, Any]:
    """立体を組む。返すのは形と、**何を作らなかったか・何を仮定したか**。"""
    confirmed = _confirmed_parts(ledger)
    dims, defaulted, unit = _dims(measures)

    made = [p for p in SOLIDABLE if p in confirmed]
    skipped = [{"part": p, "why": "確定した側面が無い"}
               for p in SOLIDABLE if p not in confirmed]

    L = dims["body_length"]
    chest = dims["chest"]
    shoulder = dims["shoulder"]
    hem = dims["hem_width"]
    sleeve_len = dims["sleeve_length"]

    verts: List[Tuple[float, float, float]] = []
    faces: List[Tuple[int, int, int]] = []
    groups: List[Dict[str, Any]] = []

    def emit(rings, part):
        base = len(verts)
        for ring in rings:
            verts.extend(ring)
        f = _tube(rings, base)
        groups.append({"part": part, "first_face": len(faces),
                       "faces": len(f)})
        faces.extend(f)

    if "body" in made:
        # 肩・胸・腰・裾の4断面。**間を補間しない** — 補間した形は
        # 誰も観測していない曲線になる。
        rings = [
            _ellipse(0, 0, shoulder * math.pi * 0.5, 0.0,
                     ASSUMED_DEPTH_RATIO),
            _ellipse(0, 0, chest, -L * 0.22, ASSUMED_DEPTH_RATIO),
            _ellipse(0, 0, chest * 0.96, -L * 0.55, ASSUMED_DEPTH_RATIO),
            _ellipse(0, 0, hem * math.pi * 0.5, -L, ASSUMED_DEPTH_RATIO),
        ]
        emit(rings, "body")

    if "sleeve" in made:
        for sign in (-1.0, 1.0):
            x0 = sign * shoulder * 0.5
            rings = [
                _ellipse(x0, 0, chest * 0.30, -L * 0.05,
                         ASSUMED_DEPTH_RATIO),
                _ellipse(x0 + sign * sleeve_len * 0.30, 0,
                         chest * 0.20, -L * 0.05 - sleeve_len * 0.85,
                         ASSUMED_DEPTH_RATIO),
            ]
            emit(rings, "sleeve")

    if "collar" in made:
        rings = [
            _ellipse(0, 0, shoulder * math.pi * 0.34, L * 0.03,
                     ASSUMED_DEPTH_RATIO),
            _ellipse(0, 0, shoulder * math.pi * 0.30, L * 0.10,
                     ASSUMED_DEPTH_RATIO),
        ]
        emit(rings, "collar")

    return {
        "verdict": "ANSWER",
        "vertices": [[round(x, 2), round(y, 2), round(z, 2)]
                     for x, y, z in verts],
        "faces": [list(f) for f in faces],
        "groups": groups,
        "made": made,
        "skipped": skipped,
        "dimensions": dims,
        "defaulted": sorted(defaulted),
        "unit": unit,
        # **仮定を黙って形にしない。**
        "assumed": {
            "depth_ratio": ASSUMED_DEPTH_RATIO,
            "why": "胸囲は周囲であって幅ではない。幅と奥行きに分けるには"
                   "比が要るが、奥行きの実測は台帳に無い。この比は仮定で、"
                   "測ったものではない",
        },
        "not_a_simulation":
            "これはプロポーションの立体です。型紙を身体に着せたものでは"
            "なく、布の落ち方は一切主張していません。",
        "note": "台帳の確定項目と寸法だけから組んだ。"
                "確定していない部位は面を持たない",
    }


def to_obj(solid: Dict[str, Any]) -> str:
    """OBJ にする。**注記をファイルの先頭に残す** — 形だけ渡ると、
    受け取った側は測ったものだと思う。"""
    out = ["# Vera Atelier — 台帳から組んだプロポーションの立体",
           "# 生成物です。観測の出典にはできません。",
           f"# {solid['not_a_simulation']}",
           f"# 奥行きは仮定の比 {solid['assumed']['depth_ratio']}"
           f"（実測ではない）"]
    if solid["defaulted"]:
        out.append("# 既定の比率で補った寸法: "
                   + "、".join(solid["defaulted"]))
    if solid["skipped"]:
        out.append("# 確定が無いため作らなかった部位: "
                   + "、".join(s["part"] for s in solid["skipped"]))
    for v in solid["vertices"]:
        out.append(f"v {v[0]} {v[1]} {v[2]}")
    for g in solid["groups"]:
        out.append(f"g {g['part']}")
        for f in solid["faces"][g["first_face"]:
                                g["first_face"] + g["faces"]]:
            out.append(f"f {f[0] + 1} {f[1] + 1} {f[2] + 1}")
    return "\n".join(out) + "\n"


def save(ledger: Any, path: Any, measures: Any = None) -> Dict[str, Any]:
    """立体を書き出し、**生成物の印を付ける**。"""
    from pathlib import Path

    from .garment import mark_generated

    solid = build(ledger, measures)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(to_obj(solid), encoding="utf-8")
    stamp = mark_generated(p)
    return {k: v for k, v in solid.items()
            if k not in ("vertices", "faces")} | {"path": str(p),
                                                  "stamp": str(stamp)}
