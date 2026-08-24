# -*- coding: utf-8 -*-
"""モデル別プロンプト。**モデルを切り替えるとプロンプトが切り替わる。**

役割は二つで、混ぜない:

- **center(中心)** — 部品分解を考える ReAct ループの頭脳。LM Studio の
  qwen3.6:35b-a3b など。指示文(プロンプト)を持つ
- **parallel(並列常駐)** — Marqo-FashionSigLIP などの埋め込みモデル。
  指示を聞く模型ではないので「プロンプト」の正体は**クエリバンク**
  (部品の有無を画像埋め込みとの距離で確かめる英文クエリ)。中心モデルの
  出力 queries と語彙バンクの両方を検索に流す

設計の約束:

1. **プロンプトは版を持つ。** 出典は「どのモデルが・どの版のプロンプトで
   出したか」まで台帳に乗る。版の無い提案は追跡できない
2. **規律はプロンプトの中だけでなく、受け取り側でも検査する。** モデルが
   信頼度の数字を紛れ込ませてきたら ``UNKNOWN_FORBIDDEN_CONFIDENCE``
   で返す — プロンプトで守らせようとするだけでは、守れたことを誰も
   確かめられない
3. 新しいモデルの追加 = この辞書への1エントリ(+VM2ベンチの通過)。
   これはコントリビューターIssueの形に開いてある
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from . import parts as _parts

# ---------------------------------------------------------------------------
# 規律。**全モデルのプロンプトにそのまま入る** (discipline_check が
# 「入っていること」を検査するので、勝手に削れない)。
DISCIPLINE: Tuple[str, ...] = (
    "1. 見えていることだけを述べる。背面・内側・見えなかった部分は"
    "unknowns に入れる。推測で埋めない",
    "2. 確率・信頼度・スコアの数字を出さない。根拠は「画像のどの領域か」"
    "で示す",
    "3. 服の名前(種類)を決めつけない。kind_guess はあっても無くてもよい"
    "提案であり、採用は人がする",
    "4. 出力は JSON 一つだけ。説明文・挨拶・コードフェンスを付けない",
)

#: 出力スキーマ(プロンプトにそのまま貼られる)。
SCHEMA_TEXT = """{
  "kind_guess": "文字列 または null",
  "parts": [
    {"part": "語彙の家族名 または new_part",
     "proposed_family": "part が new_part のときだけ",
     "variant_hint": "見た目の特徴(自由文)",
     "ports": ["接続口の名前"],
     "evidence": "何を見てそう言ったか(自由文)",
     "region": "画像のどのあたりか(自由文)"}
  ],
  "unknowns": [
    {"aspect": "決められない側面",
     "why": "なぜ見えないか",
     "candidate_hints": ["候補の方向性(採用は人)"]}
  ],
  "queries": ["類似検索に流す英文クエリ"]
}"""


def _decomposition_prompt() -> str:
    vocab = "\n".join(f"- {k}: {v}" for k, v in _parts.PART_VOCAB.items())
    ports = ", ".join(_parts.PORTS)
    rules = "\n".join(DISCIPLINE)
    return f"""あなたは服飾構造解析器です。画像の服を「部品の組合せ」に分解してください。
服の種類を当てる課題ではありません。部品と接続口と、見えないものの列挙が仕事です。

## 部品語彙(この中から選ぶ。無い部品は part="new_part" で提案する)
{vocab}

## 接続口(ports。この語彙からのみ)
{ports}

## 規律(違反した出力は全体が受理されません)
{rules}

## 出力スキーマ
{SCHEMA_TEXT}
"""


# ---------------------------------------------------------------------------
#: クエリバンク(並列常駐の埋め込み検索用・英文)。
#: **部品ごとの在り否を確かめる短いクエリ。** 埋め込みの類似は
#: 「似ている」であって「在る」ではないので、結果は提案の欄に入り、
#: 閾値で確定に昇格させることはしない。
PART_QUERY_BANK: Dict[str, List[str]] = {
    "bodice": ["fitted bodice", "cropped top", "bodice with waist seam"],
    "skirt_panel": ["high-low hem skirt", "pleated skirt",
                    "A-line skirt", "gathered skirt"],
    "cape": ["shoulder cape", "cape over dress", "poncho cape"],
    "sleeve": ["long set-in sleeve", "puff sleeve", "bell sleeve",
               "gathered cuff"],
    "collar": ["stand collar", "choker neckline", "peter pan collar"],
    "closure": ["front button placket", "back zipper", "lace-up front",
                "ribbon tie front"],
    "waist_finish": ["elastic waistband", "waist belt", "sash tie bow"],
    "decoration": ["ribbon bow", "lace trim", "snowflake embroidery"],
}


# ---------------------------------------------------------------------------
_PROMPTS: Dict[str, Dict[str, Any]] = {
    "lmstudio:qwen3.6:35b-a3b": {
        "role": "center",
        "version": "v2026-08-24.1",
        "text": _decomposition_prompt(),
    },
    "siglip:marqo-fashionSigLIP": {
        "role": "parallel",
        "version": "v2026-08-24.1",
        "text": None,
        "query_bank": PART_QUERY_BANK,
    },
}
_DEFAULT = {
    "role": "center",
    "version": "v2026-08-24.1",
    "text": _decomposition_prompt(),
}


def for_model(model_id: str) -> Dict[str, Any]:
    """モデルIDからプロンプト束を返す。**一致は 完全 → 家族接頭辞 → 既定。**

    ``lmstudio:qwen3.6:35b-a3b`` に固有文があればそれを、無ければ既定。
    だから新しいモデルの登録は1エントリでよく、既定の規律は全員に効く。
    """
    entry = _PROMPTS.get(model_id)
    if entry is None:
        family = model_id.split(":", 1)[0]
        for k, v in _PROMPTS.items():
            if k.startswith(family + ":"):
                entry = v
                break
    e = dict(entry if entry is not None else _DEFAULT)
    e["model_id"] = model_id
    e["matched"] = "default" if entry is None else "profile"
    e["discipline"] = list(DISCIPLINE)
    e["schema"] = SCHEMA_TEXT
    return e


def register(model_id: str, role: str, version: str,
             text: Optional[str], query_bank: Optional[Dict[str, List[str]]]
             ) -> None:
    """新しいモデルの登録口。**コントリビューターIssueの着地点。**"""
    if role not in ("center", "parallel"):
        raise ValueError("UNKNOWN_ROLE: center か parallel を選ぶ")
    if role == "center" and not text:
        raise ValueError("UNKNOWN_EMPTY_PROMPT: center には指示文が要る")
    _PROMPTS[model_id] = {"role": role, "version": version, "text": text,
                          "query_bank": query_bank or {}}


def profiles() -> List[str]:
    return sorted(_PROMPTS)


# ---------------------------------------------------------------------------
# 受け取り側の検査。**プロンプトが守らせようとしたことを、ここが確かめる。**
FORBIDDEN_KEYS = ("confidence", "probability", "score", "certainty")


def parse_decomposition(model_id: str, text: str) -> Dict[str, Any]:
    """中心モデルの出力を検査する。**断りは値。捏造は通らない。**"""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"verdict": "UNKNOWN_MALFORMED_PROPOSAL",
                "why": "JSON として読めない",
                "how_to_close": "モデルに出力を JSON 一つだけにさせる"
                                "(プロンプトの規律4)"}
    if not isinstance(data, dict):
        return {"verdict": "UNKNOWN_MALFORMED_PROPOSAL",
                "why": "一番外側はオブジェクトであるべき"}

    blob = json.dumps(data, ensure_ascii=False).lower()
    hit = [k for k in FORBIDDEN_KEYS if f'"{k}"' in blob]
    if hit:
        return {"verdict": "UNKNOWN_FORBIDDEN_CONFIDENCE",
                "which": hit,
                "why": "モデルの自己申告の数字は事実の欄に入らない"
                       "(VM2)。根拠は領域と複数観測の一致で示す",
                "how_to_close": "該当キーを外して出し直させる"}

    parts_out: List[Dict[str, Any]] = []
    bad_ports: List[str] = []
    bad_parts: List[str] = []
    for p in data.get("parts", []) or []:
        if not isinstance(p, dict):
            continue
        fam = p.get("part")
        if fam != "new_part" and fam not in _parts.PART_VOCAB:
            bad_parts.append(str(fam))
            continue
        ports = [x for x in (p.get("ports") or [])]
        bad_ports += [x for x in ports if x not in _parts.PORTS]
        parts_out.append(p)
    if bad_parts:
        return {"verdict": "UNKNOWN_UNKNOWN_PART",
                "which": sorted(set(bad_parts)),
                "how_to_close": "語彙に家族として足すか、new_part として"
                                "提案させる"}
    if bad_ports:
        return {"verdict": "UNKNOWN_UNKNOWN_PORT",
                "which": sorted(set(bad_ports)),
                "how_to_close": f"接続口は {'/'.join(_parts.PORTS)} のみ"}

    prof = for_model(model_id)
    return {
        "verdict": "ANSWER",
        "model_id": model_id,
        "prompt_version": prof["version"],
        # **出典はここまで刻む。** 台帳の source にそのまま乗る。
        "source": f"{model_id}; prompt={prof['version']}",
        "kind_guess": data.get("kind_guess"),
        "parts": parts_out,
        "unknowns": data.get("unknowns", []) or [],
        "queries": [q for q in (data.get("queries") or [])
                    if isinstance(q, str) and q.strip()],
    }


def to_proposals(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """検査済みの分解を台帳の提案に変換する。**全部 PROPOSED。**

    装飾(decoration)も提案としては載る — ただし型紙の幾何には
    入らない(部品語彙の定義どおり)。
    """
    src = parsed.get("source", "")
    out: List[Dict[str, Any]] = []
    for p in parsed.get("parts", []):
        ev = p.get("evidence") or p.get("region") or ""
        out.append({
            "part": p.get("part"), "aspect": "presence",
            "value": p.get("variant_hint") or p.get("proposed_family")
                     or p.get("part"),
            "source": f"{src}; evidence={ev}" if ev else src,
        })
    for u in parsed.get("unknowns", []):
        out.append({
            "part": "unknown", "aspect": u.get("aspect", "unknown"),
            "value": " / ".join(u.get("candidate_hints", [])),
            "source": f"{src}; why={u.get('why', '')}",
        })
    return out


def siglip_queries(parsed: Optional[Dict[str, Any]] = None,
                   families: Optional[List[str]] = None) -> List[str]:
    """並列常駐モデルに流すクエリ。**語彙バンク + 中心モデルの提案。**

    families を絞れば部品単位の類似(「この部分はあの服に似ている」)
    に、絞らなければ服全体の類似に使える。
    """
    out: List[str] = []
    bank = _PROMPTS.get("siglip:marqo-fashionSigLIP", {}).get(
        "query_bank", PART_QUERY_BANK)
    for fam in (families or list(bank)):
        out += bank.get(fam, [])
    if parsed:
        out += parsed.get("queries", [])
    # 重複は数えない — 同じ文を二度投げて確度が上がったことにならない。
    seen, uniq = set(), []
    for q in out:
        if q not in seen:
            seen.add(q)
            uniq.append(q)
    return uniq
