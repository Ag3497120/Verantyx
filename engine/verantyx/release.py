"""One command from approved suggestions to a switchable published model.

The evolution basis WITHOUT a database: the model repository's commit
history is the checkpoint history, and the Space's `versions/` directory is
the switcher's menu. Every release stamps the same shape:

    vera-<GEN>-<YYYYMMDD>       GEN letters are STRUCTURE generations —
                                A stays A while the geometry and gates are
                                unchanged and only knowledge grows; a real
                                structural improvement releases B, carrying
                                the corpus forward. Same-day re-releases
                                append .2, .3 …

    versions/index.json         what the Space's model toggle reads:
                                [{id, gen, date, db, edges, writer, notes,
                                  cores}]

The run is the approval: a human reads the vera-suggest issues, then runs

    python3 -m verantyx.release --notes "..."           # knowledge release
    python3 -m verantyx.release --gen B --notes "..."   # structure release

and the command pulls the approved queue (issues + refusals), rebuilds
through the same front doors as always, VERIFIES (answers and shape, banks
untouched), writes the dated artifacts, and uploads: full artifacts to the
model repo, browser artifacts + updated index to the Space. Nothing manual
between approval and the toggle.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import argparse
import gzip
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

SPACE = "kofdai/ask-vera"

#: Distribution rule: a structure generation gets its own model repo, and
#: knowledge-only (minor) releases UPDATE that repo in place. So vera-A-*
#: keeps landing in kofdai/vera-alpha forever — its commit history is the
#: checkpoint history — and the first B release creates kofdai/vera-b and
#: accumulates there. Readers can then pin a structure by pinning a repo,
#: while "latest of my structure" is just the repo head.
def model_repo(gen: str) -> str:
    return "kofdai/vera-alpha" if gen.upper() == "A" else f"kofdai/vera-{gen.lower()}"
REPO_DIR = Path(__file__).resolve().parent.parent
STATIC = REPO_DIR / "hf" / "space_static"


def _gz(src: Path, dst: Path) -> None:
    dst.write_bytes(gzip.compress(src.read_bytes(), 9))


def next_id(index: List[Dict[str, Any]], gen: str, date: str) -> str:
    base = f"vera-{gen}-{date}"
    taken = {e["id"] for e in index}
    if base not in taken:
        return base
    n = 2
    while f"{base}.{n}" in taken:
        n += 1
    return f"{base}.{n}"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(corpus_root()))
    ap.add_argument("--gen", default="A",
                    help="structure generation letter; bump only when the "
                         "geometry or gates changed")
    ap.add_argument("--notes", default="")
    ap.add_argument("--queue", default=None,
                    help="refusal/suggestion queue to ingest first")
    ap.add_argument("--skip-github", action="store_true")
    ap.add_argument("--skip-upload", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root)
    date = time.strftime("%Y%m%d")

    # 1. Approved growth in — the human approval is running this command.
    queue = a.queue or str(root / "build" / "refusals.jsonl")
    Path(queue).touch()
    grow_args = ["--queue", queue, "--root", str(root)]
    if not a.skip_github:
        grow_args.append("--github")
    from .grow import main as grow_main
    grow_main(grow_args)

    # 2. Fresh browser artifacts from whatever grow rebuilt (grow already
    #    re-exported and verified the full db; --verify there is the gate).
    from .export_sqlite import export_edges, export_web
    web = export_web(root, STATIC / "vera_web.db")
    export_edges(root, STATIC / "vera_edges.db", top=8)

    # 3. Stamp the version.
    vdir = STATIC / "versions"
    vdir.mkdir(exist_ok=True)
    idx_path = vdir / "index.json"
    index: List[Dict[str, Any]] = (json.loads(idx_path.read_text())
                                   if idx_path.exists() else [])
    vid = next_id(index, a.gen, date)
    files = {}
    for name, src in (("db", STATIC / "vera_web.db"),
                      ("edges", STATIC / "vera_edges.db"),
                      ("writer", root / "build" / "writer.json")):
        out = vdir / f"{vid}.{name}.gz"
        _gz(src, out)
        files[name] = f"versions/{out.name}"
    # Credit: everyone whose queued suggestion this release consumed. The
    # names ride the version entry and the boot line — a contribution that
    # becomes a permanent, named part of the structure is the reward this
    # geometry can uniquely offer.
    contributors: List[str] = []
    try:
        for line in Path(queue).read_text(encoding="utf-8").splitlines():
            try:
                by = json.loads(line).get("by")
            except Exception:
                continue
            if by and by not in contributors:
                contributors.append(by)
    except Exception:
        pass
    entry = {"id": vid, "gen": a.gen, "date": date, **files,
             "repo": model_repo(a.gen),
             "notes": a.notes, "contributors": contributors,
             "cores": web.get("facets") and None}
    from .export_sqlite import load as _load
    entry["cores"] = len(_load(root / "build" / "vera.db")["ja"].crosses)
    index.append(entry)
    idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=1))

    # 4. Publish: full artifacts to the model repo (its commit history is
    #    the checkpoint history), browser artifacts + menu to the Space.
    if not a.skip_upload:
        from huggingface_hub import HfApi
        api = HfApi()
        repo = model_repo(a.gen)
        # A structure release goes to a repo of its own; create on first use.
        api.create_repo(repo_id=repo, repo_type="model", exist_ok=True)
        for src, name in ((root / "build" / "vera.db", "vera.db"),
                          (root / "build" / "vera_edges.db", "vera_edges.db"),
                          (root / "build" / "writer.json", "writer.json")):
            if src.exists():
                api.upload_file(path_or_fileobj=str(src), path_in_repo=name,
                                repo_id=repo, repo_type="model",
                                commit_message=f"{vid}: {a.notes or 'release'}")
        api.upload_folder(folder_path=str(STATIC), repo_id=SPACE,
                          repo_type="space",
                          allow_patterns=["versions/*", "vera_web.db.gz",
                                          "vera_edges.db.gz", "writer.json.gz"],
                          commit_message=f"{vid} on the model toggle")
    print(json.dumps({"verdict": "ANSWER", "version": vid,
                      "repo": model_repo(a.gen),
                      "cores": entry["cores"], "files": files,
                      "uploaded": not a.skip_upload}, ensure_ascii=False,
                     indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
