"""The refusal log as a standing work queue — growth where questions failed.

Measured before it was automated: 34 subjects the engine refused during one
week of operation, fetched by name, raised subject accuracy to 13/14 across
every suffix, moved 時効 from a one-document accident to a ranked answer
with three witnesses, and lifted ranked leads from 7/12 to 10/12. The fetch
list was not curated — it was derived from a stated rule, and that is what
makes the growth honest: the corpus thickens where the QUESTIONS said it
was thin, not where anyone thought it should.

    queue   vera.ask appends the subject of every UNKNOWN_NOT_PRESENT to
            $VERA_QUEUE (one JSON line each), when that variable is set.
            Off by default: an ask that writes files is a side effect a
            library must opt into, not perform silently
    grow    python3 -m verantyx.grow --queue refusals.jsonl
            dedupes, drops subjects the store meanwhile holds, fetches the
            rest by title with the rule recorded in the manifest, rebuilds,
            re-exports, verifies

Two verdicts stay OUT of the queue on purpose (see `remedy`): TIME_DEPENDENT
does not close by registration and NO_SUBJECT should not be closed — a
queue that accumulates unclosable items is a queue nobody trusts.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

#: The one verdict whose remedy is "register documents about the subject".
QUEUEABLE = "UNKNOWN_NOT_PRESENT"


def log_refusal(result: Dict[str, Any], path: Optional[str] = None) -> bool:
    """Append a queueable refusal to the queue file. Returns whether it did."""
    path = path or os.environ.get("VERA_QUEUE")
    if not path or result.get("verdict") != QUEUEABLE:
        return False
    subject = result.get("subject")
    if not subject:
        return False
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"subject": subject,
                            "asked": time.strftime("%Y-%m-%d")},
                           ensure_ascii=False) + "\n")
    return True


def pending(queue: Path, store: Any,
            witnesses: Optional[Dict[str, Any]] = None) -> List[str]:
    """Deduplicated subjects still missing, oldest first.

    Missing WHERE depends on the entry's rule. A refusal entry is checked
    against the merged sovereign — the question failed there. A peer-gap
    entry (rule "peer_gap:W") is checked against witness W: the merged
    store already holds the subject through some OTHER selection rule,
    which is precisely why it is W's debt and not a refusal. Filtering
    both against the merged store silently dropped every peer-gap the
    moment it was enqueued — the loop closed on paper and never fetched.
    """
    seen: List[str] = []
    for line in Path(queue).read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        subj = rec.get("subject")
        if not subj or subj in seen:
            continue
        rule = str(rec.get("rule") or "")
        if rule.startswith("peer_gap:") and witnesses:
            w = rule.split(":", 1)[1]
            held = subj in (witnesses.get(w).crosses
                            if witnesses.get(w) else store.crosses)
        else:
            held = subj in store.crosses
        if not held:
            seen.append(subj)
    return seen


def github_suggestions(repo: str = "Ag3497120/Verantyx-Vera-alpha",
                       label: str = "vera-suggest") -> List[Dict[str, Any]]:
    """Open community suggestions, read from the public issue tracker.

    The worldwide inlet. Anyone may file an issue with the label; nothing
    enters the structure until a human has read the issue AND run this
    command — two approvals, both visible in public. No new
    infrastructure: the queue is the issue tracker, the audit trail is
    the issue history, and a rejected suggestion is a closed issue.
    """
    import urllib.request

    url = ("https://api.github.com/repos/%s/issues?state=open&labels=%s"
           % (repo, label))
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "verantyx-vera grow"})
    with urllib.request.urlopen(req, timeout=30) as r:
        issues = json.loads(r.read().decode())
    out = []
    for it in issues:
        title = str(it.get("title") or "")
        subject = title.replace("[提案]", "").strip()
        if subject:
            out.append({"subject": subject, "issue": it.get("number"),
                        "by": ((it.get("user") or {}).get("login")),
                        "rule": "community:issue#%s" % it.get("number")})
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--queue", required=True)
    ap.add_argument("--root", default=str(corpus_root()))
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be fetched, fetch nothing")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--demand", action="store_true",
                    help="pull the anonymous demand ranking from "
                         "verantyx.ai into the queue")
    ap.add_argument("--github", action="store_true",
                    help="also pull open vera-suggest issues into the queue")
    a = ap.parse_args(argv)
    root = Path(a.root)

    from .export_sqlite import load, witnesses as load_witnesses

    Path(a.queue).touch()
    if a.demand:
        import urllib.request
        try:
            req = urllib.request.Request(
                "https://verantyx.ai/api/vera/demand",
                headers={"User-Agent": "verantyx-vera grow"})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode())
            rows = d.get("demand") or []
            with open(a.queue, "a", encoding="utf-8") as f:
                for rec in rows:
                    f.write(json.dumps({"subject": rec["subject"],
                                        "count": rec["count"],
                                        "rule": "demand",
                                        "asked": time.strftime("%Y-%m-%d")},
                                       ensure_ascii=False) + "\n")
            print(json.dumps({"demand": len(rows),
                              "top": [r0["subject"] for r0 in rows[:8]]},
                             ensure_ascii=False))
        except Exception as exc:
            print(json.dumps({"demand": "unavailable",
                              "why": type(exc).__name__}))
    if a.github:
        got = github_suggestions()
        with open(a.queue, "a", encoding="utf-8") as f:
            for rec in got:
                rec["asked"] = time.strftime("%Y-%m-%d")
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(json.dumps({"community_suggestions": len(got),
                          "subjects": [g["subject"] for g in got][:10]},
                         ensure_ascii=False))

    store = load(root / "build" / "vera.db")["ja"]
    wits = load_witnesses(root / "build" / "vera.db")
    subjects = pending(Path(a.queue), store, witnesses=wits)[:a.limit]
    if not subjects:
        print(json.dumps({"verdict": "ANSWER", "pending": 0,
                          "note": "every queued subject is now held"},
                         ensure_ascii=False))
        return 0
    if a.dry_run:
        print(json.dumps({"verdict": "ANSWER", "pending": len(subjects),
                          "would_fetch": subjects, "dry_run": True},
                         ensure_ascii=False, indent=1))
        return 0

    from .corpus_wikipedia import fetch_titles

    stamp = time.strftime("%Y%m%d")
    manifest = Path("corpora") / f"wikipedia_ja_queue_{stamp}.json"
    got = fetch_titles(
        subjects, root / "wikipedia_named", manifest,
        rule=("subjects from the operational queue %s — refusals "
              "(UNKNOWN_NOT_PRESENT) and peer gaps (held by >=2 sibling "
              "witnesses, absent in the rule-free one); nothing curated"
              % a.queue),
        label="ja.wikipedia 拒否キュー由来 %s" % stamp)

    # Rebuild through the same front doors everything else uses.
    from .build_ja import main as build_main
    from .export_sqlite import main as export_main

    build_main(["--root", str(root), "--rebuild"])
    # Force a fresh export: with --verify alone and an existing vera.db the
    # exporter SKIPS re-exporting and verifies new pickles against the old
    # file — the first real loop run came back DRIFTED on exactly that,
    # 6,090 labels in the rebuilt federation against 6,070 in the stale
    # artifact. The edges sidecar is rebuilt too: new documents mean new
    # provenance, and stale edges would licence yesterday's pairs only.
    (root / "build" / "vera.db").unlink(missing_ok=True)
    code = export_main(["--root", str(root), "--verify",
                        "--edges", str(root / "build" / "vera_edges.db")])
    print(json.dumps({"verdict": "ANSWER" if code == 0 else "DRIFTED",
                      "fetched": got["articles"], "missing": got["missing"],
                      "manifest": str(manifest)}, ensure_ascii=False, indent=1))
    return code


if __name__ == "__main__":
    sys.exit(main())
