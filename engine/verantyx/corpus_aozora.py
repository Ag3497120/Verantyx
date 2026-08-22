"""Spoken Japanese, from public-domain fiction — the register nothing else had.

Of 1,276 harvested forms, 376 came from statutes, 581 from encyclopedia
articles and none from anything a person says aloud. That is why a greeting
could only be answered in statute voice, and it is a property of the corpus
rather than of the structure: a register the reader never saw is a register
the writer cannot write.

Aozora Bunko is public-domain Japanese literature, and its dialogue sits
inside 「」 where it can be taken without taking the narration around it.
That matters — narration is descriptive prose, which the corpus already has
far too much of, and quoted speech is the thing it has none of.

    fetch      one author's works index, then each work's HTML
    extract    only the spans inside 「」, one per line
    manifest   name, url, sha256, bytes — same contract as everything else

## What this does and does not give

Dialogue from novels is not dialogue with a system. It has the shapes —
question, answer, request, acknowledgement, the polite and plain registers
side by side — and it carries a century-old vocabulary that a modern
exchange does not. `Form.source` records which corpus a template came from,
so a draft built on one of these says so.

Nothing here is a knowledge source. Fiction asserts nothing about the world,
and these documents exist to supply FORMS. Keeping them out of the knowledge
federation is the same separation `writer` already keeps between what a
sentence is about and how it is put.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

BASE = "https://www.aozora.gr.jp"
DELAY_SECONDS = 0.6
TIMEOUT = 60
USER_AGENT = ("verantyx-vera corpus_aozora "
              "(+https://github.com/Ag3497120/Verantyx)")

#: Quoted speech. Nested quotes are left alone — a 『』 inside 「」 is a
#: citation the speaker is making, not a second speaker.
_SPEECH = re.compile(r"「([^「」]{2,200})」")
_TAG = re.compile(r"<[^>]+>")
_RUBY = re.compile(r"<rp>.*?</rp>|<rt>.*?</rt>", re.S)


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
    for enc in ("shift_jis", "utf-8", "euc-jp"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("shift_jis", errors="ignore")


def work_urls(person_page: str, limit: int = 40) -> List[Tuple[str, str]]:
    """(title, card url) from an author's index page."""
    html = _get(person_page)
    out: List[Tuple[str, str]] = []
    for m in re.finditer(r'<a href="(\.\./cards/[^"]+card(\d+)\.html)">([^<]+)</a>',
                         html):
        href, _num, title = m.groups()
        # urljoin, not concatenation: the index links out with ../cards/…
        # and a naive join leaves index_pages/../cards/ in the URL, which
        # the server serves as something else entirely.
        out.append((title.strip(),
                    urllib.parse.urljoin(person_page, href)))
        if len(out) >= limit:
            break
    return out


def text_url(card_url: str) -> Optional[str]:
    """The HTML body linked from a card page."""
    html = _get(card_url)
    m = re.search(r'href="(\./files/[^"]+\.html)"', html)
    if not m:
        return None
    return urllib.parse.urljoin(card_url, m.group(1))


def speech(html: str) -> str:
    """Only what is inside 「」, one utterance per line."""
    body = _RUBY.sub("", html)
    body = _TAG.sub("", body)
    lines = [s.strip() for s in _SPEECH.findall(body)]
    return "\n".join(s for s in lines if s)


def fetch(
    person_pages: Iterable[str],
    out: Path,
    manifest_path: Path,
    *,
    label: str = "",
    per_author: int = 20,
) -> Dict[str, Any]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files: List[Dict[str, Any]] = []
    empty: List[str] = []
    for page in person_pages:
        for title, card in work_urls(page, limit=per_author):
            time.sleep(DELAY_SECONDS)
            try:
                turl = text_url(card)
                if not turl:
                    continue
                time.sleep(DELAY_SECONDS)
                spoken = speech(_get(turl))
            except Exception:
                continue
            if len(spoken) < 400:
                empty.append(title)
                continue
            name = re.sub(r"[^\w一-龥ぁ-んァ-ヶー]+", "_", title)[:60] + ".txt"
            blob = spoken.encode("utf-8")
            (out / name).write_bytes(blob)
            files.append({"name": name, "url": turl,
                          "sha256": hashlib.sha256(blob).hexdigest(),
                          "bytes": len(blob)})
    manifest = {
        "label": label or "青空文庫 会話文（「」内のみ）",
        "recorded": time.strftime("%Y-%m-%d"),
        "selection_rule": {"person_pages": list(person_pages),
                           "per_author": per_author,
                           "extract": "spans inside 「」 only, no narration"},
        "files": files,
        "reproducible": all(e.get("url") for e in files),
        "note": "public-domain fiction, taken for FORMS not for facts; "
                "fiction asserts nothing about the world and these documents "
                "must not enter the knowledge federation",
    }
    Path(manifest_path).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"verdict": "ANSWER", "works": len(files), "too_little_speech": empty[:5],
            "chars": sum(e["bytes"] for e in files),
            "manifest": str(manifest_path)}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--person", action="append", required=True,
                    help="author index page id, e.g. 148 for 夏目漱石")
    ap.add_argument("--out", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--per-author", type=int, default=20)
    a = ap.parse_args(argv)
    pages = ["%s/index_pages/person%s.html" % (BASE, p) for p in a.person]
    print(json.dumps(fetch(pages, Path(a.out), Path(a.manifest),
                           label=a.label, per_author=a.per_author),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
