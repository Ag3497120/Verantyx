# -*- coding: utf-8 -*-
"""開発走行(探索用・事前登録の外)。確認測定は run_confirm.py で別の目標集合。

開発目標: rev(rev(l)) = l — 梯子の発明(補題 rev(app(x, cons(a, nil))) =
cons(a, rev(x)) 級)を、候補の発明+接地淘汰+十字エネルギーで自動化する。
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prover import Prover, parse_term

DEV_GOALS = [
    ("D1", "app(x, nil)", "x"),
    ("D2", "len(app(x, y))", "add(len(x), len(y))"),
    ("D3", "rev(rev(x))", "x"),
]

def main():
    out = {"goals": []}
    for name, l, r in DEV_GOALS:
        p = Prover()
        t0 = time.time()
        ok, how = p.prove(parse_term(l), parse_term(r))
        out["goals"].append({
            "name": name, "goal": f"{l} = {r}",
            "proved": ok, "how": how,
            "lemmas": p.stats["lemmas"],
            "nodes": p.stats["nodes"], "invented": p.stats["invented"],
            "cross_waves": len(p.trace),
            "seconds": round(time.time() - t0, 1)})
    print(json.dumps(out, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results_dev.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()
