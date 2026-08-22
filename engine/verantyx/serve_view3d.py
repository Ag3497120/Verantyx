"""Serve the 3D view next to the engine and stream what a query touches.

A published artifact cannot do this. Its CSP blocks every external host and
neither runtime capability the platform offers (`downloads`, `mcp`) opens
one, so a page on claude.ai has no way to reach a Python process on this
machine. Saying otherwise would be a promise the browser refuses to keep.

Served from here it is a same-origin fetch and works. The page detects
which case it is in and says so rather than pretending — "未接続 — 静的表示"
against "接続 — 推論を可視化中".

What is streamed is what the engine actually consults, not a replay: each
setting of `GradedJudge` is asked in turn and the cores its rungs scored are
emitted as they are scored. A visualisation that animated a plausible path
instead would be the same failure as a generated sentence arriving where a
citation is expected.

    vera-view3d --root ~/Projects/vera-corpus --page <dir>
    open http://localhost:8790/vera3d.html
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import argparse
import json
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

CLIENTS: "List[queue.Queue]" = []
STATE: Dict[str, Any] = {}


def emit(msg: Dict[str, Any]) -> None:
    dead = []
    for q in CLIENTS:
        try:
            q.put_nowait(msg)
        except Exception:
            dead.append(q)
    for q in dead:
        if q in CLIENTS:
            CLIENTS.remove(q)


def load(root: Path) -> None:
    """Load every sovereign, not just the Japanese one.

    `vera.load` is the same entry the MCP server and the IDE use, so the
    picture and the tools cannot answer differently — a viewer watching a
    query resolve is watching the thing that actually resolved it.
    """
    # Load the PUBLISHED artifact, not the pickles. Same answers (--verify
    # pins that), and it is the only path that carries the sidecars — edges,
    # gaps, facet provenance — so the viewer shows the structure the world
    # downloads rather than a local variant of it.
    from .export_sqlite import vera as load_published
    from .vera import load as load_vera

    db = root / "build" / "vera.db"
    v = load_published(db) if db.exists() else load_vera(root)
    STATE["vera"] = v
    STATE["root"] = root
    STATE["store"] = v.stores["ja"]
    STATE["judge"] = v.judges["ja"]


def run_query(query: str) -> Dict[str, Any]:
    """Ask, streaming each stage as it happens.

    The stream is the layering: language, then the staircase setting by
    setting, then the core, then the reach if nothing was held. A viewer
    sees which stage produced the answer, which is the same thing the
    verdict name says.
    """
    from .lang import detect, ja_content_runs
    from .resolution import ask as rung_ask

    v = STATE["vera"]
    lang = detect(query)
    if lang == "latin" and "en" in v.stores:
        lang = "en"
    emit({"type": "language", "language": lang, "have": sorted(v.stores)})
    if lang not in v.stores:
        emit({"type": "verdict", "verdict": "UNKNOWN_LANGUAGE_NOT_HELD",
              "item": None, "detail": lang})
        return {"verdict": "UNKNOWN_LANGUAGE_NOT_HELD"}

    j, st = v.judges[lang], v.stores[lang]
    terms = (j.read or ja_content_runs)(query)
    emit({"type": "ask", "query": query, "terms": terms})
    if not terms:
        emit({"type": "verdict", "verdict": "UNKNOWN_UNPARSED", "item": None})
        return {"verdict": "UNKNOWN_UNPARSED"}

    # The query's own terms, wherever the store holds them.
    seen = [t for t in terms if t in st.crosses]
    if seen:
        emit({"type": "touch", "nodes": seen, "why": "query"})

    readings: Dict[str, Optional[str]] = {}
    for name, _cfg in j.settings:
        r = rung_ask(j.ladders[name], terms)
        item = r["item"] if r["verdict"] == "ANSWER" else None
        readings[name] = item
        emit({"type": "reading", "setting": name,
              "verdict": r["verdict"], "item": item,
              "answered": r.get("answered", 0), "concord": r.get("concord", 0)})
        if item:
            emit({"type": "touch", "nodes": [item], "why": name})
        time.sleep(.16)          # so a reader can watch the settings differ

    full = v.ask(query)
    detail = "%s/%s" % (full.get("agreeing", 0), full.get("of", 0))
    if full.get("reached"):
        for r in full["reached"]:
            emit({"type": "touch", "nodes": [r["item"]], "why": r["verdict"]})
            emit({"type": "reach", "term": r["term"], "route": r["verdict"],
                  "item": r["item"]})
    sentences = [s["text"] for s in
                 (full.get("written") or {}).get("sentences", [])]
    wt = full.get("witnesses") or {}
    origin = sorted({x for vs in (full.get("facet_origin") or {}).values()
                     for x in vs})[:3]
    emit({"type": "verdict", "verdict": full["verdict"],
          "item": full.get("core") or full.get("item"),
          "detail": detail, "readings": readings,
          "language": lang, "path": full.get("text"),
          "sentences": sentences,
          "remedy": full.get("remedy"),
          "coverage": full.get("coverage"),
          "facet_only": full.get("as_facet_only"),
          "missing": full.get("missing"),
          "witness": ({"agree": wt.get("agree"),
                       "answered": wt.get("answered")} if wt else None),
          "origin": origin,
          "order": full.get("order_evidence"),
          "grain": full.get("grain"),
          "tier": full.get("tier"),
          "known_gap": full.get("known_gap"),
          "subject": full.get("subject"),
          "nearest": full.get("nearest_held")})
    # THE ANSWERING CORE'S ACTUAL CROSS. The picture drew leaves and cores
    # and stopped there: facets — the things that occupy the four faces of
    # an arm — were never nodes, so the geometry the whole engine is built
    # on was the one thing the geometry viewer did not show. Nor were the
    # sentence-edges, added later, anywhere in it. Both ride the answer now,
    # so what lights up is the cross that produced it.
    core_key = full.get("core_key") or full.get("core")
    if core_key:
        cross = st.crosses.get(str(core_key)) or {}
        faces = sorted(cross, key=lambda f: (-cross[f], f))[:24]
        pairs = []
        if v.edges is not None:
            try:
                pairs = v.edges(str(core_key), faces)
            except Exception:
                pairs = []
        emit({"type": "cross", "core": full.get("core"), "faces": faces,
              "counts": [cross[f] for f in faces], "edges": pairs,
              "capacity": 24,
              "order": full.get("order_evidence")})

    # The structure evolves under the reader. A refused subject is fetched
    # by name, ingested through the same front door every corpus uses, and
    # the new cores stream to the page as they land — the evolution loop's
    # single-question form. Session memory plus a durable queue entry: the
    # in-process stores answer immediately, the article file and the queue
    # line survive for the next grow run to make permanent.
    # Both registration-closable refusals grow, because they are the same
    # gap seen from two distances: NOT_PRESENT names its subject already;
    # NO_EVIDENCE is the commoner shape (subject unheld, staircase
    # abstains) and carries none — the subject is derived the same way the
    # gate derives it, and only a clean single-phrase Japanese subject
    # fires. 譲渡担保とは was measured NO_EVIDENCE with a live article
    # waiting; greetings derive no subject and never fire.
    if full.get("verdict") in ("UNKNOWN_NOT_PRESENT", "UNKNOWN_NO_EVIDENCE"):
        subject = full.get("subject")
        if not subject and lang == "ja":
            from .stacked import subject_check
            cov = subject_check(v.stores["ja"], query, "")
            if cov.get("single") and cov.get("subject")                     and cov["subject"] not in v.stores["ja"].crosses:
                subject = cov["subject"]
        if subject:
            # OFFERED, never taken. The automatic version ingested the
            # moment it refused; the governed version follows the
            # project's own quarantine rule — an AI may propose, only a
            # human accepts. /preview shows WHAT would be ingested and
            # /grow ingests only after the reader approves.
            emit({"type": "grow_offer", "subject": subject})
    return full


def preview_one(subject: str) -> Dict[str, Any]:
    """Fetch and HOLD the article so the reader sees it before approving."""
    from .corpus_wikipedia import extract

    try:
        text = extract(subject, intro=False)
    except Exception as exc:
        return {"ok": False, "why": type(exc).__name__}
    if not text:
        return {"ok": False, "why": "no_article"}
    STATE.setdefault("pending", {})[subject] = text
    return {"ok": True, "subject": subject, "chars": len(text),
            "head": text[:220],
            "url": "https://ja.wikipedia.org/wiki/" + subject}


def grow_one(subject: str) -> None:
    from .document_ingest import Document, ingest_documents
    from .grow import log_refusal

    emit({"type": "grow_start", "subject": subject})
    # Only what the reader saw and approved is ingested — the text held by
    # preview_one, never a fresh fetch that could differ from the preview.
    text = (STATE.get("pending") or {}).pop(subject, None)
    if not text:
        emit({"type": "grow_missing", "subject": subject,
              "why": "not_previewed"})
        return

    v = STATE["vera"]
    st = v.stores["ja"]
    before = set(st.crosses)
    label = f"指名／{subject}.txt"
    st.source_labels.add(label)
    ingest_documents(st, [Document(source=label, text=text)])
    wit = v.witnesses.get("指名")
    if wit is not None:
        wit.source_labels.add(label)
        ingest_documents(wit, [Document(source=label, text=text)])
    new = sorted(set(st.crosses) - before)

    # Durable trail: the article file lands where build_ja reads, and the
    # queue line lets the next `grow` run record it in a manifest properly.
    root = STATE.get("root")
    if root:
        try:
            (Path(root) / "wikipedia_named" / f"{subject}.txt").write_text(
                text, encoding="utf-8")
        except Exception:
            pass
        log_refusal({"verdict": "UNKNOWN_NOT_PRESENT", "subject": subject},
                    path=str(Path(root) / "build" / "refusals.jsonl"))

    emit({"type": "grown", "subject": subject, "count": len(new),
          "cores": new[:60], "domain": "指名"})
    # The judge must re-index or the staircase cannot see the new cores.
    # Measured at 1.4s on 86,967 — done after the grown event so the page
    # shows the structure first and the readiness second.
    v.add("ja", st)
    STATE["judge"] = v.judges["ja"]
    emit({"type": "grow_ready", "subject": subject})


class H(BaseHTTPRequestHandler):
    page_dir = Path(".")

    def log_message(self, *a):        # quiet
        pass

    def _send(self, code, ctype, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            q: "queue.Queue" = queue.Queue(maxsize=400)
            CLIENTS.append(q)
            try:
                while True:
                    try:
                        m = q.get(timeout=15)
                        self.wfile.write(
                            b"data: " + json.dumps(m, ensure_ascii=False).encode()
                            + b"\n\n")
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except Exception:
                pass
            finally:
                if q in CLIENTS:
                    CLIENTS.remove(q)
            return

        if u.path == "/gaps":
            # The mapped holes, as data the picture can place: subject, how
            # many witnesses hold it, and which. A gap is structure too —
            # leaving it out of the view left the reader with a map that
            # showed only what exists.
            v = STATE.get("vera")
            out = []
            g = getattr(v, "gaps", None) if v else None
            if g is not None:
                for core, cr in list(g.crosses.items())[:4000]:
                    holders = sorted(f.split(":", 1)[1] for f in cr
                                     if f.startswith("held_by:"))
                    lacks = sorted(f.split(":", 1)[1] for f in cr
                                   if f.startswith("gap:"))
                    out.append({"subject": core, "held_by": holders,
                                "lacked_by": lacks})
            self._send(200, "application/json",
                       json.dumps({"gaps": out}, ensure_ascii=False).encode())
            return

        if u.path in ("/preview", "/grow"):
            subj = parse_qs(u.query).get("s", [""])[0]
            try:
                subj = subj.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
            if u.path == "/preview":
                self._send(200, "application/json",
                           json.dumps(preview_one(subj),
                                      ensure_ascii=False).encode())
            else:
                threading.Thread(target=grow_one, args=(subj,),
                                 daemon=True).start()
                self._send(200, "application/json",
                           json.dumps({"verdict": "ACCEPTED"}).encode())
            return

        if u.path == "/ask":
            qs = parse_qs(u.query).get("q", [""])[0]
            # `BaseHTTPRequestHandler` hands the request line back decoded as
            # latin-1, so a Japanese query arrives as mojibake and parses to
            # zero terms — UNKNOWN_UNPARSED for a question the store can
            # answer. Re-encode and read it as what it was sent as.
            try:
                qs = qs.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
            threading.Thread(target=run_query, args=(qs,), daemon=True).start()
            self._send(200, "application/json",
                       json.dumps({"verdict": "ACCEPTED", "query": qs},
                                  ensure_ascii=False).encode())
            return

        name = u.path.lstrip("/") or "vera3d.html"
        f = (self.page_dir / name).resolve()
        if not str(f).startswith(str(self.page_dir.resolve())) or not f.is_file():
            self._send(404, "text/plain; charset=utf-8", b"not found")
            return
        ct = ("text/html; charset=utf-8" if f.suffix == ".html"
              else "application/json; charset=utf-8" if f.suffix == ".json"
              else "application/octet-stream")
        self._send(200, ct, f.read_bytes())


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(corpus_root()))
    ap.add_argument("--page", required=True, help="directory holding vera3d.html")
    ap.add_argument("--port", type=int, default=8790)
    a = ap.parse_args(argv)

    print("連合を読み込み中…", flush=True)
    load(Path(a.root))
    v = STATE["vera"]
    print("ソブリン: %s  → http://localhost:%d/vera3d.html"
          % ({k: len(s.crosses) for k, s in v.stores.items()}, a.port), flush=True)
    print(f"問う:  curl 'http://localhost:{a.port}/ask?q=正当防衛とは'", flush=True)
    H.page_dir = Path(a.page)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
