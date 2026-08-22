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
import re
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

#: 参照の状態。**「参照が無い」は「見ていない」ではない。**
REF_NONE = "UNKNOWN_UNVERIFIABLE_SOURCE"     # 開き直す手がかりが無い
REF_MISSING = "UNKNOWN_SOURCE_NOT_FOUND"     # 手元からは開けない
REF_OK = "VERIFIABLE"

#: 生成物の印。**自分が描いた絵を後から証拠として読み直さない**ため。
#: 一周回ると、モデルの出力がコマ由来の観測の顔をして戻ってくる。
GENERATED_MARK = ".vera-generated"

#: 素材の由来。割ったコマだけが残って元が分からない状態を作らない。
INTAKE_INDEX = "intake.json"

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
    at: str = ""              # 映像上の時刻 "0:12:05"。証拠の時系列に使う
    # -- 後から同じものを見に行くための参照 ----------------------------
    # 出典が文字列なだけだと、書いた本人以外は確かめられない。
    # **見る役は誰でもよい**が、見に行けることは要る。
    ref_path: str = ""        # 手元のファイル(映像・画像・PDF)
    ref_mark: str = ""        # そのファイルの中の位置 "0:12:05" / "f182" / "p.12"
    ref_url: str = ""         # 手元に置けないもの


def mark_generated(path: Any) -> Path:
    """描かせた画像に印を付ける。印はファイルの隣に置く — 画像自体を
    書き換えると、印だけ剥がして証拠に化けさせられる。"""
    p = Path(path)
    stamp = p.with_name(p.name + GENERATED_MARK)
    stamp.write_text("generated, not observed\n", encoding="utf-8")
    return stamp


def is_generated(path: Any) -> bool:
    """その画像が**この装置が描いたもの**か。

    印が無ければ生成物ではない、とは言い切れない(外から持ち込まれた
    生成画像は分からない)。ここで塞げるのは自分が描いたものだけで、
    それ以上を主張しない。
    """
    if not path:
        return False
    p = Path(str(path))
    return p.with_name(p.name + GENERATED_MARK).exists()


def ref_status(e: "Entry") -> str:
    """その項目を今この機体から開き直せるか。

    **手元に無いことは、存在しないことではない。** 外付けを繋げば開ける
    ものを「無い」と書くと、後で本当に失われたものと区別できなくなる。
    """
    if e.ref_path:
        return REF_OK if Path(e.ref_path).exists() else REF_MISSING
    if e.ref_url:
        # URL は手元では確かめない。開き直す手がかりはある。
        return REF_OK
    return REF_NONE


def ref_key(e: "Entry") -> str:
    """独立して数えてよいかの同一性。

    同じファイルの同じコマを二度読んでも、証拠は一つである。参照が
    無いものは出典の文字列で数える — それしか手がかりが無いため。
    """
    if e.ref_path:
        return f"file:{e.ref_path}#{e.ref_mark}"
    if e.ref_url:
        return f"url:{e.ref_url}#{e.ref_mark}"
    return f"text:{e.source}"


def ref_brief(e: "Entry") -> Dict[str, Any]:
    return {"status": ref_status(e), "path": e.ref_path,
            "mark": e.ref_mark, "url": e.ref_url, "source": e.source}


@dataclass
class Ledger:
    """一着分の台帳。"""

    title: str = ""
    entries: List[Entry] = field(default_factory=list)

    # -- 置く ------------------------------------------------------------
    def observe(self, part: str, aspect: str, value: str, source: str,
                note: str = "", ref_path: str = "", ref_mark: str = "",
                ref_url: str = "") -> "Entry":
        """観測を置く。参照(ファイル+位置 / URL)を添えると、後から
        **同じものを見に行ける**。添えなくても観測は観測で、確定欄には
        出る — ファイルを付けていないことは、見ていないことではない。
        ただし各行は「再確認できるか」を必ず伴う。

        **生成された画像からは観測できない。** 設計図を描かせた絵を
        後から読み直すと、モデルの出力がコマ由来の観測の顔をして戻って
        くる。一周回ると誰も出所を辿れないので、ここで断る。
        """
        if is_generated(ref_path):
            raise ValueError(
                "UNKNOWN_GENERATED_NOT_EVIDENCE: "
                f"{Path(ref_path).name} は生成された画像。"
                "描いたものを見て観測したことにはできない / "
                "元のコマか実物を出典にする")
        return self._add(part, aspect, value, "observation", source, note,
                         ref_path=ref_path, ref_mark=ref_mark,
                         ref_url=ref_url)

    def infer(self, part: str, aspect: str, value: str, source: str,
              note: str = "") -> "Entry":
        """構造から推す。観測と同じ欄には**絶対に**入らない。"""
        return self._add(part, aspect, value, "inference", source, note)

    def propose(self, part: str, aspect: str, value: str, source: str,
                note: str = "", ref_path: str = "", ref_mark: str = "",
                ref_url: str = "") -> "Entry":
        """外から来たもの(画像検索・視覚モデル・人の意見)。未採用。

        コマから出た提案は、そのコマを参照に持てる。**同じコマを同じ
        モデルに二度読ませても積まない** — 同じ絵を見直して確度は
        上がらないので、重複は既存の項目を返すだけにする。
        """
        key = (str(part), str(aspect), str(value), str(source),
               str(ref_path or ""), str(ref_mark or ""))
        for e in self.entries:
            if e.kind != "proposal" or e.adopted_by:
                continue
            if (e.part, e.aspect, e.value, e.source,
                    e.ref_path, e.ref_mark) == key:
                return e
        return self._add(part, aspect, value, "proposal", source, note,
                         ref_path=ref_path, ref_mark=ref_mark,
                         ref_url=ref_url)

    def adopt(self, part: str, aspect: str, value: str,
              by: str) -> Optional[Entry]:
        """提案を採用する。**これが提案が事実になる唯一の道。**

        採用しても提案の出所は消えない — 後から「誰の提案を誰が通したか」
        を辿れないと、裁断後に責任の所在が消える。

        **名前の無い採用は受け付けない。** これを扉(mcp_server)と画面
        (Atelier)だけで止めていた版があり、測定 V60 で落ちた: 台帳を
        直接呼べば匿名で通せてしまう。責任の所在は表面の作法ではなく
        台帳の性質なので、ここで閉じる。
        """
        who = (by or "").strip()
        if not who:
            raise ValueError(
                "UNKNOWN_NO_ADOPTER: 採用者の名前が要る。"
                "誰が通したか辿れない採用は、間違いの責任が消える")
        for e in self.entries:
            if (e.part == part and e.aspect == aspect and e.value == value
                    and e.kind == "proposal" and not e.adopted_by):
                e.kind = "observation"
                e.adopted_by = who
                return e
        return None

    def _add(self, part, aspect, value, kind, source, note,
             ref_path="", ref_mark="", ref_url="") -> Entry:
        e = Entry(part=str(part), aspect=str(aspect), value=str(value),
                  kind=kind, source=str(source), note=str(note),
                  ref_path=str(ref_path or ""), ref_mark=str(ref_mark or ""),
                  ref_url=str(ref_url or ""))
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
                                               if e.value == v],
                                   "refs": [ref_brief(e) for e in obs
                                            if e.value == v]}
                                  for v in sorted(values)],
                        "proposals": _brief(pro)}
            e0 = obs[0]
            # **同じコマを二度読んでも証拠は一つ。** 数えるのは項目では
            # なく参照で、これをしないと同じ画面を繰り返し見るだけで
            # 確度が上がって見える。
            keys = {ref_key(e) for e in obs}
            refs = [ref_brief(e) for e in obs]
            return {"state": OBSERVED, "part": part, "aspect": aspect,
                    "value": e0.value,
                    "sources": [e.source for e in obs],
                    "agreed": len(keys),
                    "entries": len(obs),
                    "refs": refs,
                    # 確定の各行は「再確認できるか」を必ず伴う。
                    "verifiable": any(r["status"] == REF_OK for r in refs),
                    "unverifiable_reason": (
                        "" if any(r["status"] == REF_OK for r in refs)
                        else ("参照先が手元に無い"
                              if any(r["status"] == REF_MISSING for r in refs)
                              else "開き直す参照が付いていない")),
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
            # proposed は open の**内訳**で、open から引かない。提案は
            # 何も閉じないので、引くと閉じたように見える。
            "counts": {"confirmed": len(confirmed), "contested": len(contested),
                       "inferred": len(inferred), "open": len(open_items),
                       # 確定のうち、後から見に行ける本数。裁つ前に
                       # どれを確かめ直せるかが、これで判る。
                       "verifiable": sum(1 for c in confirmed
                                         if c.get("verifiable")),
                       "proposed": sum(1 for o in open_items
                                       if o.get("state") == PROPOSED),
                       "unobserved": sum(1 for o in open_items
                                         if o.get("state") != PROPOSED)},
            "note": "confirmed 以外を裁断の根拠にしないこと。"
                    "inferred と proposal は観測ではない",
        }

    def timeline(self) -> List[Dict[str, Any]]:
        """証拠を映像の時刻順に並べる。**時刻を持たないものも落とさない** —
        検索や人の証言は時刻を持たないが、証拠であることは変わらない。
        """
        def key(e: Entry) -> tuple:
            t = _timecode(e.at or e.source)
            return (0, t) if t is not None else (1, 0)

        rows = []
        for e in sorted(self.entries, key=key):
            t = _timecode(e.at or e.source)
            rows.append({"at": _fmt(t) if t is not None else "",
                         "seconds": t, "part": e.part, "aspect": e.aspect,
                         "value": e.value, "kind": e.kind,
                         "source": e.source, "note": e.note,
                         "adopted_by": e.adopted_by})
        return rows

    def techpack(self) -> Dict[str, Any]:
        """縫製師に渡す資料。**未確定は消さず、独立した節にする。**

        AI の内部構造を見せない — 見せるのは服飾設計の資料として読める形。
        ただし「何が根拠か」は各項目に残す。裁った後に遡れないと、
        間違いの原因が永久に分からない。
        """
        spec = self.spec()
        by_part: Dict[str, List[Dict[str, Any]]] = {}
        for s_ in spec["confirmed"] + spec["contested"] + spec["inferred"]:
            by_part.setdefault(s_["part"], []).append(s_)
        return {
            "verdict": "ANSWER",
            "title": self.title or "(無題)",
            "sections": [
                {"no": "01", "name": "Overview",
                 "rows": [{"label": "確定した項目",
                           "value": str(spec["counts"]["confirmed"])},
                          {"label": "割れている項目",
                           "value": str(spec["counts"]["contested"])},
                          {"label": "推論(要確認)",
                           "value": str(spec["counts"]["inferred"])},
                          {"label": "未確定",
                           "value": str(spec["counts"]["open"])},
                          {"label": "うち提案あり(未採用)",
                           "value": str(spec["counts"]["proposed"])}]},
                {"no": "02", "name": "Front", "parts":
                 {k: by_part.get(k, []) for k in ("collar", "body", "detail")}},
                {"no": "03", "name": "Back", "parts":
                 {k: by_part.get(k, []) for k in ("back",)}},
                {"no": "04", "name": "Sleeve & Pocket", "parts":
                 {k: by_part.get(k, []) for k in ("sleeve", "pocket")}},
                {"no": "05", "name": "Materials", "parts":
                 {k: by_part.get(k, []) for k in ("fabric", "lining")}},
                {"no": "06", "name": "Construction",
                 "rows": [{"label": f"{s_['part']} / {s_['aspect']}",
                           "value": s_.get("value", ""),
                           "state": s_["state"]}
                          for s_ in spec["inferred"]]},
                {"no": "07", "name": "Contested — 人が決めること",
                 "rows": [{"label": f"{s_['part']} / {s_['aspect']}",
                           "value": " / ".join(x["value"]
                                               for x in s_.get("sides", [])),
                           "state": s_["state"]}
                          for s_ in spec["contested"]]},
                {"no": "08", "name": "Evidence",
                 "timeline": self.timeline()},
                {"no": "09", "name": "Unknowns — 裁断前に潰すこと",
                 "rows": [{"label": f"{w['part']} / {w['aspect']}",
                           "value": w["how_to_close"], "state": w["state"]}
                          for w in self.worklist()]},
            ],
            "note": "01-05 の確定欄以外は裁断の根拠にしないこと",
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


_TC = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?")


def _timecode(text: str) -> Optional[int]:
    """"cut 0:12:05" から秒を取る。無ければ None(時刻の不在は隠さない)。"""
    m = _TC.search(str(text or ""))
    if not m:
        return None
    a, b, c = m.group(1), m.group(2), m.group(3)
    return (int(a) * 3600 + int(b) * 60 + int(c)) if c else (
        int(a) * 60 + int(b))


def _fmt(sec: int) -> str:
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _brief(rows: List[Entry]) -> List[Dict[str, Any]]:
    # 提案にも参照を付けて出す。どのコマを見て言ったのかが分からないと、
    # 採用するかどうかを人が判断できない。
    return [{"value": e.value, "source": e.source, "note": e.note,
             "ref": ref_brief(e)} for e in rows]


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


# ======================================================================
#  取り込み台帳 — 割ったコマの出所
# ======================================================================
#
# 動画をコマに割るのは計算であって判断ではない。ただし**割った跡が
# 残らないと**、コマだけが手元にあって元の映像が分からない状態になる。
# そうなるとコマ由来の観測は、出典を持っているように見えて辿れない。


@dataclass
class Clip:
    """元の素材から取り出した一枚。"""

    path: str          # 取り出したコマの場所
    mark: str          # "f182" / "0:12:05"
    seconds: float = 0.0


@dataclass
class Source:
    """取り込んだ素材ひとつ。"""

    path: str          # 元ファイル
    kind: str          # video / image / document
    at: str = ""       # 取り込んだ時刻
    bytes: int = 0
    clips: List[Clip] = field(default_factory=list)
    note: str = ""


@dataclass
class Intake:
    """何を入れて、どう割ったか。"""

    sources: List[Source] = field(default_factory=list)

    def register(self, path: Any, kind: str, at: str = "",
                 note: str = "") -> Source:
        p = Path(str(path))
        existing = next((s for s in self.sources if s.path == str(p)), None)
        if existing:
            return existing
        s = Source(path=str(p), kind=kind, at=at, note=note,
                   bytes=(p.stat().st_size if p.exists() else 0))
        self.sources.append(s)
        return s

    def add_clip(self, source_path: Any, clip_path: Any, mark: str,
                 seconds: float = 0.0) -> Clip:
        s = next((x for x in self.sources if x.path == str(source_path)), None)
        if s is None:
            raise ValueError(
                "UNKNOWN_SOURCE_NOT_REGISTERED: 元の素材が登録されていない。"
                "コマだけ残ると、出典があるように見えて辿れない")
        for c in s.clips:
            if c.mark == mark:
                return c
        c = Clip(path=str(clip_path), mark=mark, seconds=seconds)
        s.clips.append(c)
        return c

    def origin_of(self, clip_path: Any) -> Optional[Dict[str, Any]]:
        """このコマがどの素材のどこから来たか。"""
        for s in self.sources:
            for c in s.clips:
                if c.path == str(clip_path):
                    return {"source": s.path, "kind": s.kind,
                            "mark": c.mark, "seconds": c.seconds,
                            "ingested_at": s.at}
        return None

    def report(self) -> Dict[str, Any]:
        return {"verdict": "ANSWER",
                "sources": [asdict(s) for s in self.sources],
                "counts": {"sources": len(self.sources),
                           "clips": sum(len(s.clips) for s in self.sources)}}

    def save(self, path: Any) -> Dict[str, Any]:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"sources": [asdict(s) for s in self.sources]},
                                ensure_ascii=False, indent=1),
                     encoding="utf-8")
        return {"verdict": "ANSWER", "path": str(p)}

    @classmethod
    def load(cls, path: Any) -> "Intake":
        p = Path(path)
        if not p.is_file():
            return cls()
        d = json.loads(p.read_text(encoding="utf-8"))
        out = cls()
        for row in d.get("sources", []):
            clips = [Clip(**c) for c in row.pop("clips", [])]
            out.sources.append(Source(clips=clips, **row))
        return out
