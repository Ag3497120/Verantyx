"""Reconstruct a Wikipedia corpus from a manifest that recorded no URLs.

`corpus_fetch` exists because a corpus was lost once already. It was lost a
second time anyway, and the manifests are why: the e-Gov entries carry a URL
each and came back whole, while all 202 Wikipedia entries carry an empty
one. The manifest could tell that the corpus was gone and not how to get it
back — which is the failure its own docstring warns about, written down and
then not applied to half the corpora.

A Wikipedia filename IS a retrieval key, so this reconstructs the URL from
the name and refetches through the API. That is strictly weaker than a
recorded URL and the difference is visible in the result: an article is
edited between the recording and the refetch, so the checksum is expected to
differ, and a mismatch here says the article changed rather than that the
download broke. Both outcomes are reported per file and neither is silent.

The two extraction modes are not interchangeable. `wikipedia_ja_domains_2026`
holds lead sections (176 to 3,618 bytes) and `wikipedia_ja_cited_2026` holds
whole articles (806 to 549,034); refetching one as the other rebuilds a
corpus the same size in files and nothing like it in content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

#: The wiki to read. Parameterised because a federation that mixes
#: languages in one store cannot be asked in either: the English decomposer
#: collapsed 「Article 199」 to `article`, and a Japanese question then
#: competed with English cores for the same census. One language, one
#: sovereign — see `multilingual.LanguageRouter`.
API = "https://ja.wikipedia.org/w/api.php"


def api_for(wiki: str = "ja") -> str:
    return "https://%s.wikipedia.org/w/api.php" % wiki
DELAY_SECONDS = 0.5
TIMEOUT = 60
USER_AGENT = ("verantyx-vera corpus_wikipedia "
              "(+https://github.com/Ag3497120/Verantyx)")


def url_for(title: str, *, intro: bool, wiki: str = "ja") -> str:
    """The API call that produced this file, rebuilt from its name."""
    q = {
        "action": "query", "prop": "extracts", "explaintext": "1",
        "format": "json", "redirects": "1", "titles": title,
    }
    if intro:
        q["exintro"] = "1"
    return api_for(wiki) + "?" + urllib.parse.urlencode(q)


def extract(title: str, *, intro: bool, wiki: str = "ja") -> Optional[str]:
    req = urllib.request.Request(url_for(title, intro=intro, wiki=wiki),
                                 headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = json.loads(r.read().decode("utf-8"))
    pages = (data.get("query") or {}).get("pages") or {}
    for _pid, page in pages.items():
        if "missing" in page:
            return None
        return page.get("extract") or ""
    return None


def rebuild(manifest: Dict[str, Any], out: Path, *, intro: bool) -> Dict[str, Any]:
    """Refetch every entry by title. Reports drift as its own outcome."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    same, drifted, missing, failed = [], [], [], []

    for i, entry in enumerate(manifest["files"]):
        name = entry["name"]
        title = name[:-4] if name.endswith(".txt") else name
        target = out / name
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() == entry["sha256"]:
                same.append(name)
                continue
        if i:
            time.sleep(DELAY_SECONDS)
        try:
            text = extract(title, intro=intro)
        except Exception as exc:                      # network, decode, API
            failed.append({"name": name, "reason": f"{type(exc).__name__}: {exc}"})
            continue
        if text is None:
            missing.append(name)
            continue
        blob = text.encode("utf-8")
        target.write_bytes(blob)
        digest = hashlib.sha256(blob).hexdigest()
        (same if digest == entry["sha256"] else drifted).append(name)

    return {
        # Drift is the EXPECTED outcome for a live encyclopedia, so it is not
        # a failure verdict — but it is never folded into "fetched" either.
        "verdict": "ANSWER" if not failed and not missing else "UNKNOWN_PARTIAL",
        "unchanged": len(same), "changed_since_recording": len(drifted),
        "no_longer_exists": missing, "failed": failed,
        "note": "a changed file is a real article that was edited, not a bad "
                "download; figures measured on the recorded corpus do not "
                "carry over to it unchanged",
    }


def add_urls(manifest_path: Path, *, intro: bool) -> Dict[str, Any]:
    """Write the retrieval URL into a manifest that has none.

    The point of the exercise: the next loss should not need this module.
    """
    m = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    n = 0
    for entry in m["files"]:
        if entry.get("url"):
            continue
        name = entry["name"]
        entry["url"] = url_for(name[:-4] if name.endswith(".txt") else name,
                               intro=intro)
        n += 1
    m["reproducible"] = all(e.get("url") for e in m["files"])
    m["note"] = ("URLs reconstructed from article titles on 2026-08-10; the "
                 "articles are live and may since have been edited, so a "
                 "checksum mismatch means drift, not a broken fetch.")
    Path(manifest_path).write_text(
        json.dumps(m, ensure_ascii=False, indent=1, sort_keys=False),
        encoding="utf-8")
    return {"manifest": str(manifest_path), "urls_added": n,
            "reproducible": m["reproducible"]}


def category_members(category: str, *, limit: int = 500,
                     wiki: str = "ja") -> List[str]:
    """Article titles in one category, paged. Subcategories excluded."""
    titles: List[str] = []
    cont: Optional[str] = None
    while len(titles) < limit:
        q = {"action": "query", "list": "categorymembers", "format": "json",
             "cmtitle": category, "cmtype": "page",
             "cmlimit": str(min(500, limit - len(titles)))}
        if cont:
            q["cmcontinue"] = cont
        req = urllib.request.Request(
            api_for(wiki) + "?" + urllib.parse.urlencode(q),
            headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            d = json.loads(r.read().decode("utf-8"))
        titles += [m["title"] for m in
                   (d.get("query") or {}).get("categorymembers") or []]
        cont = (d.get("continue") or {}).get("cmcontinue")
        if not cont:
            break
        time.sleep(DELAY_SECONDS)
    return titles


def fetch_categories(
    categories: List[str],
    out: Path,
    manifest_path: Path,
    *,
    label: str = "",
    per_category: int = 500,
    wiki: str = "ja",
) -> Dict[str, Any]:
    """Fetch every article in the named categories and record a manifest.

    The categories are Wikipedia's own classification, which is the point.
    The doctrinal articles that bridge a legal term to an article number —
    殺人罪 to 刑法第百九十九条 — were in a corpus with no manifest and are
    gone, and choosing replacements by hand would mean choosing the articles
    that make a demonstration work. A named category is a rule stated before
    the result is seen, the same argument that makes `egov.divisions` use the
    legislature's own 編/章 rather than clustering the articles.

    The selection rule is written INTO the manifest, so a reader can see
    what was asked for and not only what came back.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files: List[Dict[str, Any]] = []
    per_cat: Dict[str, int] = {}
    empty: List[str] = []
    seen: set = set()

    for cat in categories:
        titles = category_members(cat, limit=per_category, wiki=wiki)
        per_cat[cat] = len(titles)
        for title in titles:
            if title in seen:
                continue
            seen.add(title)
            time.sleep(DELAY_SECONDS)
            try:
                text = extract(title, intro=False, wiki=wiki)
            except Exception:
                continue
            if not text:
                empty.append(title)
                continue
            name = title.replace("/", "／") + ".txt"
            blob = text.encode("utf-8")
            (out / name).write_bytes(blob)
            files.append({"name": name,
                          "url": url_for(title, intro=False, wiki=wiki),
                          "sha256": hashlib.sha256(blob).hexdigest(),
                          "bytes": len(blob)})

    manifest = {
        "label": label or "ja.wikipedia カテゴリ収集",
        "recorded": time.strftime("%Y-%m-%d"),
        "selection_rule": {"wiki": wiki, "categories": categories,
                           "per_category_limit": per_category,
                           "subcategories": False},
        "files": files,
        "reproducible": all(e.get("url") for e in files),
        "note": "selected by Wikipedia's own categories, not by hand; the "
                "rule is recorded above so the selection can be re-run and "
                "criticised independently of the articles it produced.",
    }
    Path(manifest_path).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"verdict": "ANSWER", "articles": len(files),
            "per_category": per_cat, "no_extract": empty[:5],
            "manifest": str(manifest_path)}


def fetch_titles(
    titles: List[str],
    out: Path,
    manifest_path: Path,
    *,
    label: str = "",
    rule: str = "",
    wiki: str = "ja",
) -> Dict[str, Any]:
    """Fetch the named articles and record WHY these names, in the manifest.

    A hand-typed title list is exactly the selection this project refuses —
    choosing the articles that make a demonstration work. The exception that
    keeps it honest is a list produced by a rule stated before the result:
    here, the refusal log. Every title below was a subject the engine
    refused during operation (UNKNOWN_NOT_PRESENT with the subject named),
    which is the trajectory's 「拒否のログがそのまま作業待ち行列」 carried
    out. The rule goes INTO the manifest so a reader can check that the
    list matches it and criticise the rule rather than the picks.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files: List[Dict[str, Any]] = []
    missing: List[str] = []
    for title in titles:
        time.sleep(DELAY_SECONDS)
        try:
            text = extract(title, intro=False, wiki=wiki)
        except Exception:
            missing.append(title)
            continue
        if not text:
            missing.append(title)
            continue
        name = title.replace("/", "／") + ".txt"
        blob = text.encode("utf-8")
        (out / name).write_bytes(blob)
        files.append({"name": name,
                      "url": url_for(title, intro=False, wiki=wiki),
                      "sha256": hashlib.sha256(blob).hexdigest(),
                      "bytes": len(blob)})
    manifest = {
        "label": label or "ja.wikipedia 指名収集",
        "recorded": time.strftime("%Y-%m-%d"),
        "selection_rule": {"wiki": wiki, "titles": titles,
                           "rule": rule or "named explicitly"},
        "files": files,
        "reproducible": all(e.get("url") for e in files),
        "note": "titles named by the recorded rule, not curated for effect; "
                "the rule is stated so the list can be re-derived and "
                "criticised independently of the articles it produced.",
    }
    Path(manifest_path).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"verdict": "ANSWER", "articles": len(files),
            "missing": missing, "manifest": str(manifest_path)}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out")
    ap.add_argument("--intro", action="store_true",
                    help="lead section only (wikipedia_ja_domains_2026)")
    ap.add_argument("--add-urls", action="store_true",
                    help="write reconstructed URLs into the manifest")
    ap.add_argument("--categories", nargs="+",
                    help="fetch every article in these categories instead")
    ap.add_argument("--titles", nargs="+",
                    help="fetch these named articles; state --rule")
    ap.add_argument("--rule", default="",
                    help="the rule that produced the title list")
    ap.add_argument("--label", default="")
    ap.add_argument("--per-category", type=int, default=500)
    ap.add_argument("--wiki", default="ja", help="wiki subdomain, e.g. en")
    a = ap.parse_args(argv)

    if a.titles:
        if not a.out:
            print(json.dumps({"verdict": "UNKNOWN_NO_OUT"}, ensure_ascii=False))
            return 1
        print(json.dumps(
            fetch_titles(a.titles, Path(a.out), Path(a.manifest),
                         label=a.label, rule=a.rule, wiki=a.wiki),
            ensure_ascii=False, indent=2))
        return 0

    if a.categories:
        if not a.out:
            print(json.dumps({"verdict": "UNKNOWN_NO_OUT"}, ensure_ascii=False))
            return 1
        print(json.dumps(
            fetch_categories(a.categories, Path(a.out), Path(a.manifest),
                             label=a.label, per_category=a.per_category,
                             wiki=a.wiki),
            ensure_ascii=False, indent=2))
        return 0

    if a.add_urls:
        print(json.dumps(add_urls(Path(a.manifest), intro=a.intro),
                         ensure_ascii=False, indent=2))
        return 0
    if not a.out:
        print(json.dumps({"verdict": "UNKNOWN_NO_OUT"}, ensure_ascii=False))
        return 1
    m = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    print(json.dumps(rebuild(m, Path(a.out), intro=a.intro),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
