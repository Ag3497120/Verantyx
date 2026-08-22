# -*- coding: utf-8 -*-
"""真の未到達: 定義行以外にどこにも名前が現れない公開関数。
MCP扉(@mcp.tool)・CLI登録・fork一覧は「呼ばれている」側に数える。"""
import ast, json, re
from collections import defaultdict
from pathlib import Path

PKG = Path("verantyx")
files = sorted(p for p in PKG.glob("*.py") if p.name != "__init__.py")

defs = []      # (name, module, lineno, kind, decorated)
srcs = {}
for p in files:
    src = p.read_text(encoding="utf-8", errors="ignore")
    srcs[str(p)] = src
    try:
        tree = ast.parse(src)
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            dec = any("tool" in ast.dump(d) or "command" in ast.dump(d)
                      for d in getattr(node, "decorator_list", []))
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            defs.append((node.name, p.stem, node.lineno, kind, dec))

# 全走査対象
scan = {}
for p in list(PKG.glob("*.py")) + list(Path("experiments").rglob("*.py")) \
        + list(Path("tools").rglob("*.py")) + list(Path(".").glob("*.py")):
    if p.exists():
        scan[str(p)] = p.read_text(encoding="utf-8", errors="ignore")

dead = []
for name, mod, line, kind, dec in defs:
    if dec:            # MCP扉/CLIコマンド = プロトコル経由で到達
        continue
    hits = 0
    for path, src in scan.items():
        for m in re.finditer(r"\b%s\b" % re.escape(name), src):
            ls = src.rfind("\n", 0, m.start()) + 1
            le = src.find("\n", m.start())
            lineTxt = src[ls:le if le > 0 else len(src)]
            if re.match(r"\s*(async\s+)?(def|class)\s+%s\b" % re.escape(name), lineTxt):
                continue
            if lineTxt.strip().startswith("#") or lineTxt.strip().startswith("#:"):
                continue
            hits += 1
    if hits == 0:
        dead.append({"name": name, "module": mod, "line": line, "kind": kind})

by_mod = defaultdict(list)
for d in dead:
    by_mod[d["module"]].append(d)
print("公開定義(非デコレータ):", sum(1 for d in defs if not d[4]))
print("**参照が完全にゼロ**:", len(dead))
print()
for mod in sorted(by_mod, key=lambda m: -len(by_mod[m])):
    print("%-24s %2d  %s" % (mod, len(by_mod[mod]),
          ", ".join("%s:%d" % (i["name"], i["line"]) for i in by_mod[mod][:5])
          + (" …" if len(by_mod[mod]) > 5 else "")))
Path("/private/tmp/claude-501/-Users-motonishikoudai-Projects-Vera/c56bbede-f983-4538-b2e5-cfeeaec5c491/scratchpad/dead.json").write_text(
    json.dumps(dead, ensure_ascii=False, indent=1), encoding="utf-8")
