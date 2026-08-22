# -*- coding: utf-8 -*-
"""服飾台帳 — 服を作る装置ではなく、**何がどこまで分かっているか**を持つ装置。

事前登録: experiments/garment/PREREG.md

映像や写真から服を生成しない。裁断は取り返しがつかないので、埋めた推測を
確定として縫製師に渡さないことが全て。台帳が持つのは四つの状態で、
**混ぜない**:

    OBSERVED               観測が一致した(出典に時刻・カット)
    CONTESTED              観測が食い違った(片方を勝たせない)
    INFERRED               構造から推した。観測ではない
    PROPOSED               外から来た。**未採用** — 確定欄に出ない
    UNKNOWN_NOT_OBSERVED   見えていない。閉じ方を添える

## モデルの点数を事実にしない

視覚モデルの「ウール 0.71」は、モデルが自分に付けた点数であって布の
性質ではない。**出典の一部としては運ぶが、事実の欄には入れない。**
この装置が出せる確度は「独立した観測が何本一致したか」だけ。

## 「無し」と「見えていない」を分ける

「ポケット無し」は観測。「ポケットは映っていない」は不在。縫製師にとって
前者は裁断してよい情報で、後者は確認すべき宿題。同じ欄に書いた瞬間、
指示書は使えなくなる。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

#: 部位 → その部位について決めるべき側面(閉じた表)。
#: 「何を聞かれていないか」が分かるのは、聞くべきことが先に決まっている
#: からで、これが無いと未観測を数えられない。
PARTS: Dict[str, List[str]] = {
    "collar": ["shape", "material", "closure"],
    "sleeve": ["length", "construction", "cuff"],
    "body": ["silhouette", "length", "dart"],
    "back": ["structure", "closure", "vent"],
    "pocket": ["existence", "type", "position"],
    "fabric": ["kind", "weight", "pattern"],
    "lining": ["existence", "kind"],
    "detail": ["button", "stitch", "trim"],
}

OBSERVED = "OBSERVED"
CONTESTED = "CONTESTED"
INFERRED = "INFERRED"
PROPOSED = "PROPOSED"
UNKNOWN = "UNKNOWN_NOT_OBSERVED"


@dataclass
class Entry:
    """ひとつの主張。**どこから来たか**を必ず持つ。"""

    part: str
    aspect: str
    value: str
    kind: str                 # observation / inference / proposal
    source: str               # カット番号・URL・人・モデル名
    note: str = ""            # モデルの点数などはここ(事実の欄ではない)
    adopted_by: str = ""      # 採用した人。提案が事実になる唯一の道


@dataclass
class Ledger:
    """一着分の台帳。"""

    title: str = ""
    entries: List[Entry] = field(default_factory=list)

    # -- 置く ------------------------------------------------------------
    def observe(self, part: str, aspect: str, value: str, source: str,
                note: str = "") -> "Entry":
        return self._add(part, aspect, value, "observation", source, note)

    def infer(self, part: str, aspect: str, value: str, source: str,
              note: str = "") -> "Entry":
        """構造から推す。観測と同じ欄には**絶対に**入らない。"""
        return self._add(part, aspect, value, "inference", source, note)

    def propose(self, part: str, aspect: str, value: str, source: str,
                note: str = "") -> "Entry":
        """外から来たもの(画像検索・視覚モデル・人の意見)。未採用。"""
        return self._add(part, aspect, value, "proposal", source, note)

    def adopt(self, part: str, aspect: str, value: str,
              by: str) -> Optional[Entry]:
        """提案を採用する。**これが提案が事実になる唯一の道。**

        採用しても提案の出所は消えない — 後から「誰の提案を誰が通したか」
        を辿れないと、裁断後に責任の所在が消える。
        """
        for e in self.entries:
            if (e.part == part and e.aspect == aspect and e.value == value
                    and e.kind == "proposal" and not e.adopted_by):
                e.kind = "observation"
                e.adopted_by = by
                return e
        return None

    def _add(self, part, aspect, value, kind, source, note) -> Entry:
        e = Entry(part=str(part), aspect=str(aspect), value=str(value),
                  kind=kind, source=str(source), note=str(note))
        self.entries.append(e)
        return e

    # -- 読む ------------------------------------------------------------
    def state(self, part: str, aspect: str) -> Dict[str, Any]:
        """ひとつの側面がいまどの状態か。**推測で埋めない。**"""
        rows = [e for e in self.entries
                if e.part == part and e.aspect == aspect]
        obs = [e for e in rows if e.kind == "observation"]
        inf = [e for e in rows if e.kind == "inference"]
        pro = [e for e in rows if e.kind == "proposal" and not e.adopted_by]

        if obs:
            values = {e.value for e in obs}
            if len(values) > 1:
                # 観測が割れたら片方を勝たせない。多数決もしない —
                # 3対1の誤りは3の側にも普通に起きる。
                return {"state": CONTESTED, "part": part, "aspect": aspect,
                        "sides": [{"value": v,
                                   "sources": [e.source for e in obs
                                               if e.value == v]}
                                  for v in sorted(values)],
                        "proposals": _brief(pro)}
            e0 = obs[0]
            return {"state": OBSERVED, "part": part, "aspect": aspect,
                    "value": e0.value,
                    "sources": [e.source for e in obs],
                    "agreed": len(obs),
                    "adopted_by": e0.adopted_by or "",
                    "proposals": _brief(pro)}
        if inf:
            return {"state": INFERRED, "part": part, "aspect": aspect,
                    "value": inf[0].value,
                    "basis": [e.source for e in inf],
                    "proposals": _brief(pro)}
        if pro:
            return {"state": PROPOSED, "part": part, "aspect": aspect,
                    "proposals": _brief(pro),
                    "how_to_close": "採用するか、観測で確かめる"}
        return {"state": UNKNOWN, "part": part, "aspect": aspect,
                "how_to_close": _how_to_close(part, aspect)}

    def spec(self) -> Dict[str, Any]:
        """縫製師に渡す指示書。**三つの節を混ぜない。**"""
        confirmed, inferred, open_items, contested = [], [], [], []
        for part, aspects in PARTS.items():
            for aspect in aspects:
                s = self.state(part, aspect)
                if s["state"] == OBSERVED:
                    confirmed.append(s)
                elif s["state"] == CONTESTED:
                    contested.append(s)
                elif s["state"] == INFERRED:
                    inferred.append(s)
                else:
                    open_items.append(s)
        return {
            "verdict": "ANSWER",
            "title": self.title,
            "confirmed": confirmed,       # 裁ってよい
            "contested": contested,       # 割れている。人が決める
            "inferred": inferred,         # 推論。確認を要する
            "open": open_items,           # 未確定 = そのまま作業指示
            "counts": {"confirmed": len(confirmed), "contested": len(contested),
                       "inferred": len(inferred), "open": len(open_items)},
            "note": "confirmed 以外を裁断の根拠にしないこと。"
                    "inferred と proposal は観測ではない",
        }

    def worklist(self) -> List[Dict[str, str]]:
        """未確定の一覧 = 裁断前に潰すことの一覧。"""
        out = []
        for s in self.spec()["open"]:
            out.append({"part": s["part"], "aspect": s["aspect"],
                        "state": s["state"],
                        "how_to_close": s.get("how_to_close", "")})
        return out

    # -- 保存 ------------------------------------------------------------
    def save(self, path: Any) -> Dict[str, Any]:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(
            {"title": self.title,
             "entries": [asdict(e) for e in self.entries]},
            ensure_ascii=False, indent=1), encoding="utf-8")
        return {"verdict": "ANSWER", "path": str(p),
                "entries": len(self.entries)}

    @classmethod
    def load(cls, path: Any) -> "Ledger":
        p = Path(path)
        if not p.is_file():
            return cls()
        d = json.loads(p.read_text(encoding="utf-8"))
        led = cls(title=d.get("title", ""))
        led.entries = [Entry(**row) for row in d.get("entries", [])]
        return led


def _brief(rows: List[Entry]) -> List[Dict[str, str]]:
    return [{"value": e.value, "source": e.source, "note": e.note}
            for e in rows]


#: 閉じ方の閉じた表。分からないものに「調べてください」とだけ返すのは、
#: 二時に現場で読む人にとって何も言っていないのと同じ。
_CLOSERS = {
    ("back", "structure"): "背面が映るカットを探す / 依頼者に確認する",
    ("back", "closure"): "背面のカット、または類似品の実物で確認する",
    ("pocket", "existence"): "腰から下が映るカットを探す",
    ("fabric", "kind"): "映像からは特定不能。実物・購入品・依頼者に確認",
    ("fabric", "weight"): "実物に触れるか、類似品の仕様を取り寄せる",
    ("lining", "existence"): "裾・袖口の返りが映るカットを探す",
}


def _how_to_close(part: str, aspect: str) -> str:
    return _CLOSERS.get((part, aspect),
                        f"{part} の {aspect} が映るカットを探す / 依頼者に確認")
