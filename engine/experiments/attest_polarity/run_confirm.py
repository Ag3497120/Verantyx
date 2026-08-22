# -*- coding: utf-8 -*-
"""確認測定 — docs/PREREGISTERED_2026-08-20_attest_polarity.md が事前登録。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verantyx.attest_llm import check_all
from verantyx.cross_store import CrossStore
from verantyx.polarity import ingest_polar_ja

DOC = ("会社は、従業員に対し、通勤に要する実費を支給する。"
       "自家用車通勤の場合は1キロメートルあたり15円を支給する。"
       "月額30000円を上限とする。")


def doc_store():
    """極性証拠を持たない店 — **実測時と同じ load_documents 経路**で作る。

    最初の治具は ingest_sentence で作ったが、それでは 会社 が核にならず
    K1/K3 が主題不在で落ちた(欠陥ではなく治具の誤り)。測ったものと
    同じ経路で作る。
    """
    from verantyx.document_ingest import Document, ingest_documents
    st = CrossStore(track_provenance=True)
    ingest_documents(st, [Document(source="就業規則.txt", text=DOC)])
    return st


def polar_store():
    """極性証拠を持つ店(ingest_polar_ja で構築)。"""
    st = CrossStore(track_provenance=True)
    for s in ("避難所は開設している。", "水道は復旧していない。",
              "避難所は受付中である。", "水道は断水している。"):
        ingest_polar_ja(st, s)
        st.ingest_sentence(s)
    return st


def main():
    t0 = time.time()
    res = {}
    ds, ps = doc_store(), polar_store()

    # K1: 測定済みの4例 — 肯定と否定で verdict が分かれること
    K1 = []
    for label, subj, text in (
            ("正しい", "会社", "従業員に対し通勤に要する実費を支給する"),
            ("否定", "会社", "従業員に対し通勤に要する実費を支給しない"),
            ("正しい2", "自家用車通勤", "1キロメートルあたり15円を支給する"),
            ("否定2", "自家用車通勤", "1キロメートルあたり15円を支給しない")):
        r = check_all(ds, subj, text)
        K1.append({"label": label, "verdict": r.get("verdict"),
                   "support": r.get("support"),
                   "unjudged": [u["term"] for u in r.get("unjudged", [])]})
    res["K1"] = K1
    res["K1_split"] = (K1[0]["verdict"] != K1[1]["verdict"]
                       and K1[2]["verdict"] != K1[3]["verdict"])

    # K2: 極性証拠のある店で反対極が CONTRADICTED + facet 名指し
    K2 = []
    for label, subj, text in (
            ("店=否定/主張=肯定", "水道", "水道は復旧している"),
            ("店=肯定/主張=否定", "避難所", "避難所は開設していない"),
            ("一致(肯定)", "避難所", "避難所は開設している")):
        r = check_all(ps, subj, text)
        K2.append({"label": label, "verdict": r.get("verdict"),
                   "contradictions": [(c["term"], c["claim"], c["corpus"],
                                       c["facet"])
                                      for c in r.get("contradictions", [])]})
    res["K2"] = K2
    res["K2_ok"] = (K2[0]["verdict"] == "CONTRADICTED_BY_CORPUS"
                    and K2[1]["verdict"] == "CONTRADICTED_BY_CORPUS"
                    and all(c[3] for c in K2[0]["contradictions"])
                    and K2[2]["verdict"] != "CONTRADICTED_BY_CORPUS")

    # K3: 極性の争点が無い主張は従来どおり
    r_plain = check_all(ds, "会社", "従業員に対し通勤に要する実費を支給する")
    res["K3"] = {"no_polarity_dispute": r_plain.get("verdict"),
                 "unjudged_when_negated": K1[1]["verdict"]}
    res["K3_ok"] = (r_plain.get("verdict") == "ANSWER"
                    and K1[1]["verdict"] == "UNKNOWN_POLARITY_UNJUDGED")

    # K4: 文の並び順を変えても verdict 一致
    a = check_all(ds, "会社", "実費を支給しない。上限は30000円とする")
    b = check_all(ds, "会社", "上限は30000円とする。実費を支給しない")
    res["K4"] = {"forward": a.get("verdict"), "reversed": b.get("verdict")}
    res["K4_ok"] = a.get("verdict") == b.get("verdict")

    # K5: 退行なし — 主題の型付き拒否が不変
    K5 = []
    for label, subj, text in (
            ("未保持の主題", "超伝導", "電気抵抗がゼロになる現象である"),
            ("薄い主題", "月額30000", "上限である")):
        r = check_all(ds, subj, text)
        K5.append({"label": label, "verdict": r.get("verdict")})
    res["K5"] = K5
    res["K5_ok"] = K5[0]["verdict"] == "UNKNOWN_SUBJECT_NOT_HELD"

    res["all_pass"] = all([res["K1_split"], res["K2_ok"], res["K3_ok"],
                           res["K4_ok"], res["K5_ok"]])
    res["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    Path(__file__).with_name("results.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")


if __name__ == "__main__":
    main()
