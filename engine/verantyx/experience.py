"""経験のコンパイル — 散在する在庫を9状態型に写す読み出し層(束ねない)。

操作者の方針(2026-08-20): Memory ではなく**経験のコンパイル** —
行動→結果→成功/失敗/未知/反例→証拠→条件→モデル依存性→転移性→
再検証→昇格/棄却、の状態機械。この器官はその**第一段: 読むだけ**。

守る線: 元の在庫(8箇所)は一切動かさない。写像だけが新しい。
各行は (state, subject, evidence, source_file) を持ち、出所を必ず
名指す — 読者が原本に辿れない行はこの台帳に居られない。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .paths import corpus_root

STATES = ("CLAIM", "EVIDENCE", "GAP", "FAILURE", "COUNTEREXAMPLE",
          "TRANSFER", "RULE", "PROCEDURE", "WITNESS")


def _rows_from_gaps(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    d = json.loads(path.read_text(encoding="utf-8"))
    nodes = d.get("nodes", d) if isinstance(d, dict) else {}
    out = []
    for n in (nodes.values() if isinstance(nodes, dict) else nodes):
        if not isinstance(n, dict):
            continue
        state = "GAP" if n.get("status") != "RESOLVED" else "EVIDENCE"
        out.append({"state": state, "subject": n.get("subject"),
                    "detail": {"status": n.get("status"),
                               "failure_type": n.get("failure_type"),
                               "needs": n.get("acquisition_methods")},
                    "source": str(path)})
    return out


def _rows_from_proof_ledger(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    d = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for l in d.get("lemmas", []):
        st = "RULE" if l.get("lean_verdict") == "VERIFIED" else "CLAIM"
        out.append({"state": st, "subject": f'{l["lhs"]} = {l["rhs"]}',
                    "detail": {"witness": l.get("lean_verdict"),
                               "tactic": l.get("lean_tactic"),
                               "cited": l.get("cited")},
                    "source": str(path)})
    for k, v in d.get("trials", {}).items():
        if v == "failed":
            out.append({"state": "FAILURE", "subject": k,
                        "detail": {"kind": "proof_trial"},
                        "source": str(path)})
        elif v == "refuted":
            out.append({"state": "COUNTEREXAMPLE", "subject": k,
                        "detail": {"kind": "goal_refuted"},
                        "source": str(path)})
    return out


def _rows_from_import_rules(path: Path, kind: str) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    d = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for r in d.get("rules", []):
        out.append({"state": "RULE",
                    "subject": f'{r["lhs"]} = {r["rhs"]}',
                    "detail": {"name": r.get("name"),
                               "witness": r.get("witness"), "kind": kind},
                    "source": str(path)})
    for r in d.get("rejected", []):
        st = ("COUNTEREXAMPLE" if r.get("why") in ("refuted",)
              or "refuted" in str(r.get("why", "")) else "FAILURE")
        out.append({"state": st, "subject": r.get("name"),
                    "detail": {"why": r.get("why"),
                               "witness": r.get("witness")},
                    "source": str(path)})
    return out


def _rows_from_harness_facts(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    d = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for f in d.get("facts", []):
        v = str(f.get("verdict", ""))
        st = ("RULE" if v == "ADOPTED" else
              "COUNTEREXAMPLE" if v.startswith("HARMFUL") else "EVIDENCE")
        out.append({"state": st, "subject": f.get("fact"),
                    "detail": {"model": f.get("model"),
                               "measured": f.get("measured"),
                               "verdict": v, "witness": f.get("witness")},
                    "source": str(path)})
    if d.get("transfer"):
        out.append({"state": "TRANSFER", "subject": d["transfer"],
                    "detail": d.get("contour_3models", {}),
                    "source": str(path)})
    return out


def _rows_from_refusals(path: Path, cap: int = 200) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines()[:cap]:
        try:
            r = json.loads(line)
        except Exception:
            continue
        out.append({"state": "FAILURE", "subject": r.get("query"),
                    "detail": {"verdict": r.get("verdict")},
                    "source": str(path)})
    return out


def _resolve_root() -> Path:
    """リポジトリ根。凍結バイナリでは __file__ が展開先を指すため、
    ①環境変数 ②__file__ の親(gap_graph.json が居れば) ③cwd の順。"""
    import os
    env = os.environ.get("VERA_REPO_ROOT")
    if env:
        return Path(env)
    cand = Path(__file__).resolve().parent.parent
    if (cand / "gap_graph.json").exists():
        return cand
    return Path.cwd()


def compile_view(repo_root: Path | None = None) -> Dict[str, Any]:
    """8箇所の在庫を読むだけで9型に写す。元の在庫は不動。"""
    root = repo_root or _resolve_root()
    build = corpus_root() / "build"
    exp = root / "experiments"
    rows: List[Dict[str, Any]] = []
    rows += _rows_from_gaps(root / "gap_graph.json")
    for p in sorted((exp / "cross_energy_prover").glob("proof_ledger*.gaps.json")):
        rows += _rows_from_gaps(p)
    for p in sorted((exp / "cross_energy_prover").glob("proof_ledger*.json")):
        if ".gaps." in p.name:
            continue
        rows += _rows_from_proof_ledger(p)
    rows += _rows_from_import_rules(build / "mathlib_eq_rules.json", "nat")
    rows += _rows_from_import_rules(build / "mathlib_list_rules.json", "list")
    rows += _rows_from_harness_facts(exp / "harness_algebra"
                                     / "harness_facts.json")
    rows += _rows_from_refusals(build / "refusals.jsonl")
    counts = {s: 0 for s in STATES}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    return {"votes": "none",
            "note": "読み出し層 — 元の在庫は不動、写像だけが新しい",
            "counts": counts, "n_rows": len(rows),
            "sources": sorted({r["source"] for r in rows}),
            "rows": rows}
