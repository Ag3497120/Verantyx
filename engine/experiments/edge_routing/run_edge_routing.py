# -*- coding: utf-8 -*-
"""辺による経路選択 — EDGE_ROUTING.md が事前登録。読み取り専用・決定論。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from verantyx.export_sqlite import edge_partners_of, vera as load_published

DB = Path.home() / "Projects" / "vera-corpus" / "build" / "vera.db"
EDB = DB.parent / "vera_edges.db"
N_ARMS = 6
N_FACES = 4
MAX_OFF = 40


def content_ok(w):
    return 2 <= len(w) <= 8 and not any(c.isdigit() for c in w)


def main():
    v = load_published(DB)
    store = v.stores["ja"]

    # 腕の選抜: 質量順、facet30以上・辺端点10以上。決定論。
    # 追記(第1回実行後): 生の質量順は 二・三・displaystyle というジャンク
    # ハブを拾った — is_junk_core が弾くために作られた核そのもの。実在の
    # 内容核だけに絞る(is_junk_core を通し、語彙にある語に限る)。
    from verantyx.lex_filters import is_junk_core
    from verantyx.document_structure import _numeral
    vocab = v.writer.vocab
    # 第2回追記: 出典・参考文献・概要(Wikiの定型見出し=ストアの出典
    # ラベル)と漢数詞(十一・十二)が残った。ストア自身の source_labels と
    # 既存の漢数詞パーサで除外 — どちらも主題ではない、という既存の判定。
    labels = {str(s) for s in (getattr(store, "source_labels", ()) or ())}
    ranked = sorted(store.crosses,
                    key=lambda c: (-store.mass(c), c))
    arms = []
    for c in ranked:
        if is_junk_core(c) or c not in vocab:
            continue
        if c in labels or _numeral(c) is not None:
            continue
        if len(store.crosses[c]) < 30:
            continue
        ep = edge_partners_of(EDB, c, limit=512)
        if len(ep) < 10:
            continue
        arms.append((c, set(ep)))
        if len(arms) == N_ARMS:
            break
    cores = [c for c, _e in arms]
    edges = {c: e for c, e in arms}
    faces = {c: {f for f, _n in store.top_facets(c, k=N_FACES)}
             for c in cores}
    facetset = {c: {f for f in store.crosses[c] if content_ok(f)}
                for c in cores}
    print("腕:", cores, file=sys.stderr)

    # 探針: ちょうど1核だけが facet として持つ語
    probes = []  # (word, owner, on_face)
    for c in cores:
        off_used = 0
        for w in sorted(facetset[c]):
            owners = [k for k in cores if w in facetset[k]]
            if len(owners) != 1:
                continue
            on = w in faces[c]
            if not on:
                if off_used >= MAX_OFF:
                    continue
                off_used += 1
            probes.append((w, c, on))

    def route_a(w):
        hit = [c for c in cores if w in faces[c]]
        return hit[0] if len(hit) == 1 else ("TIE" if hit else None)

    def route_b(w):
        hit = [c for c in cores if w in faces[c] or w in edges[c]]
        return hit[0] if len(hit) == 1 else ("TIE" if hit else None)

    res = {"A": {"on": [0, 0, 0, 0], "off": [0, 0, 0, 0]},
           "B": {"on": [0, 0, 0, 0], "off": [0, 0, 0, 0]}}
    # [correct, wrong, no_route, tie]
    for w, owner, on in probes:
        band = "on" if on else "off"
        for arm, fn in (("A", route_a), ("B", route_b)):
            got = fn(w)
            i = (0 if got == owner else
                 2 if got is None else
                 3 if got == "TIE" else 1)
            res[arm][band][i] += 1

    n_on = sum(res["A"]["on"])
    n_off = sum(res["A"]["off"])
    return {"arms": cores, "n_probes_on_face": n_on,
            "n_probes_off_face": n_off,
            "cells": "correct/wrong/no_route/tie_abstain", "result": res}


if __name__ == "__main__":
    out = {"slice_mass": main()}
    # 第2スライス: 法律テーマの腕(罪/法/権 で終わる核、閉じた形態条件)。
    # 質量順の腕がWiki定型見出しに寄ったため、主題が実在の分野である
    # スライスを並記して記録の説得力を上げる。判定規則は同一。
    import experiments.edge_routing.run_edge_routing as _self
    _theme = lambda c: c.endswith(("罪", "法", "権"))
    _orig = _self.main
    def main_themed():
        import verantyx.export_sqlite as ES
        v = ES.vera(DB)
        store = v.stores["ja"]
        from verantyx.lex_filters import is_junk_core
        vocab = v.writer.vocab
        ranked = sorted(store.crosses, key=lambda c: (-store.mass(c), c))
        cores = []
        edges = {}
        for c in ranked:
            if not _theme(c) or is_junk_core(c) or c not in vocab:
                continue
            if len(store.crosses[c]) < 30:
                continue
            ep = ES.edge_partners_of(EDB, c, limit=512)
            if len(ep) < 10:
                continue
            cores.append(c)
            edges[c] = set(ep)
            if len(cores) == N_ARMS:
                break
        faces = {c: {f for f, _n in store.top_facets(c, k=N_FACES)}
                 for c in cores}
        facetset = {c: {f for f in store.crosses[c] if content_ok(f)}
                    for c in cores}
        print("腕(法律):", cores, file=sys.stderr)
        probes = []
        for c in cores:
            off_used = 0
            for w in sorted(facetset[c]):
                owners = [k for k in cores if w in facetset[k]]
                if len(owners) != 1:
                    continue
                on = w in faces[c]
                if not on:
                    if off_used >= MAX_OFF:
                        continue
                    off_used += 1
                probes.append((w, c, on))
        def ra(w):
            hit = [c for c in cores if w in faces[c]]
            return hit[0] if len(hit) == 1 else ("TIE" if hit else None)
        def rb(w):
            hit = [c for c in cores if w in faces[c] or w in edges[c]]
            return hit[0] if len(hit) == 1 else ("TIE" if hit else None)
        res = {"A": {"on": [0]*4, "off": [0]*4},
               "B": {"on": [0]*4, "off": [0]*4}}
        for w, owner, on in probes:
            band = "on" if on else "off"
            for arm, fn in (("A", ra), ("B", rb)):
                got = fn(w)
                i = (0 if got == owner else 2 if got is None
                     else 3 if got == "TIE" else 1)
                res[arm][band][i] += 1
        return {"arms": cores,
                "n_probes_on_face": sum(res["A"]["on"]),
                "n_probes_off_face": sum(res["A"]["off"]),
                "cells": "correct/wrong/no_route/tie_abstain",
                "result": res}
    out["slice_legal"] = main_themed()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    Path(__file__).with_name("results_edge_routing.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
