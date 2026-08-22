"""Fetch, verify and record a corpus by manifest — never by redistribution.

Every published figure in this repository was measured on documents that are
not in this repository. That is deliberate: they are third-party government
publications, and disaster bulletins get revised and withdrawn, so a frozen
copy would quietly diverge from what the ministry is actually saying.

It is also how the original corpus was lost. It lived in a session temp
directory, the directory was cleaned, and the only thing that survived was the
figures written into commit messages. A number whose corpus cannot be
reconstructed is a number nobody can check, including its author.

So the artifact kept here is a MANIFEST: name, url, sha256, bytes. Enough for
anyone to reconstruct the corpus, and enough to notice when they can't —
because the interesting failure is not "the download broke", it is "the
ministry issued a correction and your numbers now describe a corpus that no
longer exists". A checksum mismatch has to be loud for exactly that reason.

Downloading is the one thing in this package that touches the network, which
is why it is a separate module invoked explicitly and never imported by the
reading path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

#: Be a polite client of a government site that may be under load during the
#: event its documents describe.
DELAY_SECONDS = 1.0
TIMEOUT = 60
USER_AGENT = "verantyx-vera corpus_fetch (+https://github.com/Ag3497120/Verantyx)"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(path: Path) -> Dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if "files" not in raw:
        raise ValueError(f"{path} has no 'files' list")
    return raw


def record(folder: Path, out: Path, *, source_map: Optional[Path] = None,
           label: str = "") -> Dict[str, Any]:
    """Write a manifest for documents already on disk.

    A manifest without URLs is accepted and says so in its own contents. It is
    enough to detect that a corpus changed under you; it is not enough for
    anyone else to reproduce a measurement, and pretending otherwise would
    make the manifest a worse lie than having none.
    """
    urls: Dict[str, str] = {}
    if source_map and Path(source_map).exists():
        for line in Path(source_map).read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                parts = line.split(None, 1)
            if len(parts) >= 2:
                urls[parts[0].strip()] = parts[1].strip()

    files: List[Dict[str, Any]] = []
    for p in sorted(Path(folder).rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        files.append({
            "name": p.name,
            "url": urls.get(p.name, ""),
            "sha256": sha256(p),
            "bytes": p.stat().st_size,
        })
    missing = [f["name"] for f in files if not f["url"]]
    manifest = {
        "label": label or Path(folder).name,
        "recorded": time.strftime("%Y-%m-%d"),
        "files": files,
        "reproducible": not missing,
        "note": ("Every file carries its source URL." if not missing else
                 f"{len(missing)} file(s) have no URL — this manifest can "
                 f"detect drift but cannot reconstruct the corpus."),
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return manifest


def verify(manifest: Dict[str, Any], folder: Path) -> Dict[str, Any]:
    """Re-hash what is on disk against the manifest."""
    ok, changed, absent = [], [], []
    for entry in manifest["files"]:
        p = Path(folder) / entry["name"]
        if not p.exists():
            absent.append(entry["name"])
        elif sha256(p) == entry["sha256"]:
            ok.append(entry["name"])
        else:
            changed.append(entry["name"])
    return {
        "verdict": "ANSWER" if not (changed or absent) else "UNKNOWN_CORPUS_DRIFT",
        "ok": len(ok), "changed": changed, "missing": absent,
        "meaning": (
            "The corpus on disk is the one the manifest describes."
            if not (changed or absent) else
            "The corpus on disk is NOT what the manifest describes. Any figure "
            "measured against this manifest no longer applies to these files. "
            "A changed checksum often means the publisher issued a correction, "
            "which is worth reading before re-measuring."
        ),
    }


def fetch(manifest: Dict[str, Any], out: Path) -> Dict[str, Any]:
    """Download every file, then verify. Network is used only here."""
    import urllib.error
    import urllib.request

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    got, failed, skipped = [], [], []

    for i, entry in enumerate(manifest["files"]):
        target = out / entry["name"]
        if target.exists() and sha256(target) == entry["sha256"]:
            skipped.append(entry["name"])
            continue
        url = entry.get("url")
        if not url:
            failed.append({"name": entry["name"], "reason": "no url in manifest"})
            continue
        if i:
            time.sleep(DELAY_SECONDS)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = r.read()
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            failed.append({"name": entry["name"],
                           "reason": f"{type(exc).__name__}: {exc}"})
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry["sha256"]:
            # Written anyway, under a name that cannot be mistaken for the
            # real thing: a publisher's correction is worth reading, and
            # deleting it would hide the most informative outcome here.
            (out / (entry["name"] + ".changed")).write_bytes(data)
            failed.append({"name": entry["name"],
                           "reason": "checksum differs — the published file "
                                     "changed; saved as .changed",
                           "expected": entry["sha256"], "got": digest})
            continue
        target.write_bytes(data)
        got.append(entry["name"])

    return {"verdict": "ANSWER" if not failed else "UNKNOWN_CORPUS_DRIFT",
            "fetched": len(got), "already_present": len(skipped),
            "failed": failed}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Fetch, verify or record a corpus by manifest.")
    ap.add_argument("--manifest")
    ap.add_argument("--out", required=True)
    ap.add_argument("--verify", action="store_true",
                    help="only re-hash what is on disk; no network")
    ap.add_argument("--record", metavar="FOLDER",
                    help="write a manifest for documents already on disk")
    ap.add_argument("--source-map", help="TSV of filename<TAB>url")
    ap.add_argument("--label", default="")
    a = ap.parse_args(argv)

    if a.record:
        m = record(Path(a.record), Path(a.out),
                   source_map=Path(a.source_map) if a.source_map else None,
                   label=a.label)
        print(json.dumps({"verdict": "ANSWER", "wrote": a.out,
                          "files": len(m["files"]),
                          "reproducible": m["reproducible"],
                          "note": m["note"]}, ensure_ascii=False, indent=2))
        return 0

    if not a.manifest:
        print(json.dumps({"verdict": "UNKNOWN_NO_MANIFEST",
                          "advice": "pass --manifest, or --record a folder"},
                         ensure_ascii=False))
        return 1

    m = load_manifest(Path(a.manifest))
    result = verify(m, Path(a.out)) if a.verify else fetch(m, Path(a.out))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # Exit non-zero on drift so this is usable as a CI gate. Substring-matching
    # the rendered JSON, as a first version did, returned 0 for a drift report
    # because the word ANSWER appears inside the explanatory text.
    return 0 if result["verdict"] == "ANSWER" else 1


if __name__ == "__main__":
    sys.exit(main())
