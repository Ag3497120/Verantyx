# -*- coding: utf-8 -*-
"""能力の索引 — 「それは既に在るか」に1コマンドで答える。

事前登録: experiments/guard/PREREG10_INDEX.md

67,145行・129扉・89 fork・74通の事前登録・441ページの構想。この量は
人の作業記憶にも、モデルの文脈窓にも入らない。だから作業者は毎回
**既にあるものを作り直す**。索引の不在は注意力では埋まらない。

## 索引は生成物であって一覧ではない

手書きの一覧は書いた瞬間から古くなり、地図自体が同じ問題を起こす。
だからここは何も列挙しない — ソースと文書を**その場で読む**。索引が
実物とずれることは構成上あり得ない、が唯一の設計上の主張。

## 埋め込みを使わない

順位は語の重なりだけで決める(決定的)。無いものには何も返さない —
似た名前を代わりに返すのは、再実装より悪い(在ると誤認させる)。
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any, Dict, List

def _resolve_root() -> Path:
    """リポジトリ根。**凍結バイナリでは `__file__` が展開先を指す** ——
    この企てで3度踏んだ罠なので、既存の作法(experience.py と同じ
    ①環境変数 ②`__file__` の親(目印が居れば) ③cwd)に揃える。

    索引はソースを読んで作るものなので、ソースの無い機械では空になる。
    そのときは黙って空を返さず、根が見つからなかったことを言う。
    """
    import os

    env = os.environ.get("VERA_REPO_ROOT")
    if env and (Path(env) / "verantyx" / "mcp_server.py").exists():
        return Path(env)
    cand = Path(__file__).resolve().parent.parent
    if (cand / "verantyx" / "mcp_server.py").exists():
        return cand
    here = Path.cwd()
    for d in [here] + list(here.parents)[:3]:
        if (d / "verantyx" / "mcp_server.py").exists():
            return d
    home = Path.home() / "Projects" / "Verantyx-Vera-alpha"
    if (home / "verantyx" / "mcp_server.py").exists():
        return home
    return cand


ROOT = _resolve_root()


def _first_line(doc: str) -> str:
    for line in (doc or "").strip().splitlines():
        line = line.strip()
        if line:
            return line[:160]
    return ""


def _parse(path: Path) -> Any:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _doors(root: Path) -> List[Dict[str, str]]:
    """@mcp.tool() の付いた関数を、走らせずに読む(店を読み込まない)。"""
    tree = _parse(root / "verantyx" / "mcp_server.py")
    out: List[Dict[str, str]] = []
    if tree is None:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            src = ast.dump(dec)
            if "'tool'" in src or '"tool"' in src:
                doc = ast.get_docstring(node) or ""
                out.append({"kind": "door", "name": node.name,
                            "about": _first_line(doc),
                            "text": doc[:2000],
                            "where": "verantyx/mcp_server.py"})
                break
    return out


def _forks(root: Path) -> List[Dict[str, str]]:
    path = root / "verantyx" / "cross_geometry_forks.py"
    tree = _parse(path)
    out: List[Dict[str, str]] = []
    if tree is None:
        return out
    registered = set(re.findall(r"^\s+(\w+_fork)\(\),", path.read_text(
        encoding="utf-8"), re.M))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.endswith("_fork"):
            doc = ast.get_docstring(node) or ""
            out.append({"kind": "fork", "name": node.name,
                        "about": _first_line(doc), "text": doc[:2000],
                        "where": "verantyx/cross_geometry_forks.py",
                        "registered": "yes" if node.name in registered
                                      else "no"})
    return out


def _commands(root: Path) -> List[Dict[str, str]]:
    tree = _parse(root / "verantyx" / "cli.py")
    out: List[Dict[str, str]] = []
    if tree is None:
        return out
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_parser"):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        help_text = ""
        for kw in node.keywords:
            if kw.arg == "help" and isinstance(kw.value, ast.Constant):
                help_text = str(kw.value.value)
            elif kw.arg == "help" and isinstance(kw.value, ast.JoinedStr):
                help_text = ""
        out.append({"kind": "command", "name": str(node.args[0].value),
                    "about": " ".join(help_text.split())[:160],
                    "where": "verantyx/cli.py"})
    return out


def _modules(root: Path) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for path in sorted((root / "verantyx").glob("*.py")):
        tree = _parse(path)
        doc = (ast.get_docstring(tree) if tree is not None else "") or ""
        out.append({"kind": "module", "name": path.stem,
                    "about": _first_line(doc), "text": doc[:2000],
                    "where": f"verantyx/{path.name}"})
    return out


def _papers(root: Path) -> List[Dict[str, str]]:
    """事前登録と結果 — 「何を測ると決め、何が出たか」の在処。"""
    out: List[Dict[str, str]] = []
    for pattern, kind in (("PREREG*.md", "prereg"), ("RESULTS*.md", "results"),
                          ("MEASURED*.md", "measured")):
        for path in sorted(root.rglob(pattern)):
            if ".git" in path.parts:
                continue
            head, body = "", ""
            try:
                body = path.read_text(encoding="utf-8")
                for line in body.splitlines():
                    if line.strip():
                        head = line.strip("# ").strip()[:160]
                        break
            except Exception:
                pass
            out.append({"kind": kind, "name": path.stem, "about": head,
                        "text": body[:2000],
                        "where": str(path.relative_to(root))})
    return out


def build(root: Any = None) -> Dict[str, Any]:
    """索引を今つくる。手書きの一覧は持たない(構成上ずれない)。"""
    r = Path(root) if root else _resolve_root()
    if not (r / "verantyx" / "mcp_server.py").exists():
        return {"verdict": "UNKNOWN_NO_SOURCE_TREE", "root": str(r),
                "entries": [], "counts": {}, "total": 0,
                "note": "索引はソースから導出するので、ソースの無い機械"
                        "では作れない。VERA_REPO_ROOT を指すか、"
                        "リポジトリのある場所で実行する"}
    entries = (_doors(r) + _forks(r) + _commands(r) + _modules(r)
               + _papers(r))
    counts: Dict[str, int] = {}
    for e in entries:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    return {"verdict": "ANSWER", "root": str(r), "entries": entries,
            "counts": counts, "total": len(entries),
            "note": "derived from source and documents at call time; "
                    "there is no hand-written list to go stale"}


_SPLIT = re.compile(r"[\s,.;:_/()\[\]{}·、。「」]+")
#: 「その能力は在るか」に答える順。実装(扉・命令・モジュール)が先、
#: 性質の固定(fork)、そのあとに測定の記録(結果・事前登録)。
_KIND_ORDER = {"door": 0, "command": 1, "module": 2, "fork": 3,
               "results": 4, "measured": 5, "prereg": 6}
#: この企ての用語だけを写す閉じた対応表(日本語で引いて英語で書かれた
#: 資産に届くため)。**資産の一覧ではない** — 資産は増減するので手書き
#: では必ず古くなるが、用語は動かないので手で持てる。新しい概念が
#: 日本語名しか持たないときは、ここに足すか英語で引く(正直な限界)。
_GLOSS = {
    "配置": "placement", "摂動": "perturbation", "不変": "invariance",
    "文書": "document", "投入": "ingest", "取り込み": "ingest",
    "約束": "covenant", "破棄": "retire", "退役": "retire",
    "欠け": "gap", "欠落": "gap", "保留": "pending quarantine",
    "証人": "witness", "索引": "index", "合意": "consensus",
    "矛盾": "contradiction", "極性": "polarity", "姉妹語": "siblings",
    "店": "store", "十字": "cross", "腕": "arm", "面": "facet",
    "核": "core", "段": "ladder resolution", "粒度": "granularity",
    "階層": "hierarchy", "木": "hierarchy tree", "番人": "guard covenant",
    "監査": "audit", "数学": "math", "証明": "prove proof",
    "記憶": "memory", "分野": "domain", "語彙": "lexicon vocabulary",
    "転移": "transfer", "経験": "experience", "検査": "doctor check",
    "風化": "fading", "連合": "federation", "主権": "sovereign",
    "自己進化": "self_evolve", "説明": "explain", "要約": "summarize",
    "会話": "conversation", "失敗": "failure", "能力": "capacity",
    "誓約": "covenant", "遮断": "block", "隔離": "quarantine",
}


def _groups(terms: List[str]) -> List[List[str]]:
    """語ごとに「その語か、その訳語のどれか」の束を作る。

    束の中は or、束と束の間は **and**。最初は全部 or にしていたが、
    「hydroponic lettuce yield」が yield 一語で当たって、存在しない
    ものに ANSWER を返した(事前登録の停止条件)。問いの全部の語に
    応えられないなら、それは持っていないということ。
    """
    out: List[List[str]] = []
    for t in terms:
        variants = [t]
        for ja, en in _GLOSS.items():
            if ja in t:
                variants += en.split()
        out.append(variants)
    return out


def _terms(text: str) -> List[str]:
    """語に割るだけ。**部分窓は作らない。**

    最初は日本語に2文字窓を足したが、「ブロックチェーン」が「ロック」に
    当たって、存在しない資産に ANSWER を返した(事前登録の停止条件)。
    在ると誤って教えるのは、作り直しより高くつく。
    """
    return [t for t in _SPLIT.split((text or "").lower()) if t]


def search(query: str, limit: int = 12, root: Any = None) -> Dict[str, Any]:
    """語で引く。**無いものには何も返さない。**

    順位は語の重なりだけ(決定的、埋め込み無し)。似た名前を代わりに
    返さないのは、再実装より誤認のほうが高くつくから — 「在る」と
    誤って教えると、人はそれを探しに行って時間を失う。
    """
    idx = build(root)
    if idx.get("verdict") == "UNKNOWN_NO_SOURCE_TREE":
        return idx
    groups = _groups([t for t in _terms(query) if t])
    if not groups:
        return {"verdict": "UNKNOWN_EMPTY_QUERY"}
    scored = []
    for e in idx["entries"]:
        hay = (f"{e['name']} {e.get('about', '')} {e.get('text', '')} "
               f"{e.get('where', '')}").lower()
        hay_terms = set(_terms(hay))
        hits = [g for g in groups
                if any(v in hay or v in hay_terms for v in g)]
        if len(hits) < len(groups):      # 全部の束に応えられないなら持っていない
            continue
        # 名前に当たったほうが強い(説明文の偶然の一致より確か)
        name_hits = sum(1 for g in groups
                        if any(v in e["name"].lower() for v in g))
        # 問いは「その能力は在るか」なので、**実装が先・証拠は後**。
        # 事前登録と結果は「測った記録」であって能力そのものではない。
        rank = _KIND_ORDER.get(e["kind"], 9)
        scored.append(((-(len(hits) + name_hits * 2), rank, -name_hits,
                        e["name"]), e))
    if not scored:
        return {"verdict": "UNKNOWN_NOT_FOUND", "query": query,
                "searched": idx["total"], "counts": idx["counts"],
                "note": "nothing in the code or the papers matches; this is "
                        "an answer, not a failure — it means the thing is "
                        "not there yet"}
    scored.sort(key=lambda row: row[0])
    # 照合に使った本文は返さない(読む人の目の前を埋めるだけ)。
    hits = [{k: v for k, v in row[1].items() if k != "text"}
            for row in scored[:limit]]
    return {"verdict": "ANSWER", "query": query, "searched": idx["total"],
            "hits": hits, "total_hits": len(scored)}


def markdown(root: Any = None) -> str:
    """人が読む形。生成物なので、置いた瞬間から古くなる前提で使う。"""
    idx = build(root)
    lines = ["# 能力の索引(生成物 — `vera index build` で作り直す)", ""]
    lines.append("| 種類 | 数 |")
    lines.append("|---|---|")
    for kind, n in sorted(idx["counts"].items()):
        lines.append(f"| {kind} | {n} |")
    for kind in ("door", "command", "module", "fork", "prereg", "results",
                 "measured"):
        rows = [e for e in idx["entries"] if e["kind"] == kind]
        if not rows:
            continue
        lines += ["", f"## {kind} ({len(rows)})", ""]
        for e in sorted(rows, key=lambda x: x["name"]):
            about = e.get("about", "")
            lines.append(f"- `{e['name']}` — {about}" if about
                         else f"- `{e['name']}`")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(json.dumps(build()["counts"], ensure_ascii=False))
