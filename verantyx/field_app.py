"""The local web application, built to field-software rules rather than to taste.

Runs on 127.0.0.1 with the Python standard library, makes no network call of
any kind, and reads documents that never leave the machine. That is the whole
reason it exists as a separate thing from the public demo: a municipal officer
has drafts, shelter registers and hospital lists in front of them, and the
correct place for those is nowhere.

The interface follows the conventions of software people actually operate
under pressure, which are not the conventions of a marketing page:

    the primary action is always on screen        never behind a menu, never
                                                  below a fold; an officer
                                                  should never hunt for "read
                                                  these documents"
    every state is named in words                 no bare spinner. "読み取り中
                                                  (12/40)" tells you whether
                                                  to wait; a rotating circle
                                                  does not
    a refusal says what to do next                UNKNOWN_* already names what
                                                  is missing, so the screen
                                                  can carry the procedure. A
                                                  message that only reports
                                                  failure leaves someone to
                                                  invent the next step at two
                                                  in the morning
    the quiet number comes first                  coverage and opposable pairs
                                                  sit ABOVE the findings,
                                                  because a list of detections
                                                  read without knowing that
                                                  60% went unread is a list
                                                  trusted for the wrong reason
    words, not icons                              an icon means something
                                                  different in every agency;
                                                  a label means one thing
    everything within two clicks                  six sections, all in one
                                                  bar, no nesting
    keyboard first                                Ctrl/Cmd+Enter runs, / goes
                                                  to search — people who use a
                                                  tool all day stop using the
                                                  mouse
    guidance where the question is                each section carries its own
                                                  short explanation inline, so
                                                  nobody has to find a manual
                                                  while a phone is ringing
    high contrast, large targets                  a laptop on a folding table
                                                  in a gymnasium, in daylight

Nothing decorative. Every pixel that is not information was removed on
purpose, and the sections are ordered the way the work actually happens:
read documents → see what is contested → look up one place → check the
engine's own defects → decide the vocabulary queue.
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional

from .audit_app import SUPPORTED, _MAX_BYTES
from .field_session import (HOME, Session, listing, load, new_id, save,
                            search as store_search, silence)

_PORT = 8900


def _write_files(root: Path, files: List[Dict[str, str]]):
    written, refused = [], []
    for f in files or []:
        name = Path(f.get("name", "")).name
        if not name:
            continue
        if Path(name).suffix.lower() not in SUPPORTED:
            refused.append({"name": name,
                            "reason": "NO_LOADER",
                            "supported": sorted(SUPPORTED)})
            continue
        try:
            data = base64.b64decode(f.get("b64", ""))
        except Exception:
            refused.append({"name": name, "reason": "UNDECODABLE"})
            continue
        (root / name).write_bytes(data)
        written.append(name)
    return written, refused


def read_documents(files: List[Dict[str, str]], *, home: Path = HOME
                   ) -> Dict[str, Any]:
    """Everything one pass produces, in the order the screen shows it."""
    home = Path(home)
    from .arm_schema import ArmIndex
    from .corpus_audit import audit_paths
    from .cross_store import CrossStore
    from .document_ingest import deep_report, ingest_documents
    from .document_loaders import load_paths
    from .metamorphic import probe_paths, rule_conflicts
    from .vocab_growth import successions
    from .proposal_verify import check as verify_proposal

    if not files:
        return {"verdict": "UNKNOWN_NO_DOCUMENTS"}

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        written, refused = _write_files(root, files)
        if not written:
            return {"verdict": "UNKNOWN_NO_READABLE_DOCUMENTS",
                    "refused": refused, "supported": sorted(SUPPORTED)}

        paths = [str(root)]
        audit = audit_paths(paths)
        docs = load_paths([str(root / n) for n in written])["documents"]

        store, arms = CrossStore(track_provenance=True), ArmIndex()
        ingest_documents(store, docs, arms)

        board = []
        for core in sorted(set(store.crosses),
                           key=lambda c: -store.core_count.get(c, 0)):
            d = deep_report(store, core, arms)
            if d["disputed"] or d["updated"]:
                board.append({"core": core, "confidence": d["confidence"],
                              "disputed": d["disputed"], "updated": d["updated"]})

        proven = [x.as_dict() for x in probe_paths(paths) if x.proven]
        conflicts = [x.as_dict() for x in rule_conflicts(paths)]

        # The queue is PERSISTED, not just displayed. Two reasons, and both
        # are about the person rather than the engine: a candidate they
        # already judged must never be asked again (a queue that re-asks
        # settled questions is a queue people stop reading), and the officer
        # coming on at 22:00 has to be able to finish what the day shift
        # started. `decide` reads this same file.
        decided = _decided(home)
        queue = []
        for p in successions(paths):
            if p.word in decided:
                continue
            v = verify_proposal(p, paths)
            if v.state == "contradicts":
                continue
            row = p.as_dict()
            row["state"] = v.state
            row["why"] = v.why
            row["sources"] = v.sources
            row["status"] = "proposed"
            queue.append(row)
        queue.sort(key=lambda r: 0 if r["state"] == "verified" else 1)
        _remember(queue, home)

        lex = _lexicon()
        if lex is not None:
            from .ja_grammar import ASPECT_OF
            known = sorted(ASPECT_OF)
            for row in queue:
                sl = lex.state_likeness(row["word"], known)
                if sl is not None:
                    row["state_likeness"] = sl
                    row["nearest"] = lex.nearest(row["word"], known, k=3)

    quiet = silence(audit)
    dets = [asdict(d) for d in audit.detections]

    # Every read is a shift record, saved without being asked. The officer at
    # 22:00 does not know at 14:00 that today will need handing over — by the
    # time they know, the moment to press "save" has passed. What is kept is
    # the RESULT (what was read, what was found), never the documents.
    sess = Session(session_id=new_id(),
                   label="、".join(written)[:80],
                   documents=written,
                   coverage=quiet["coverage"],
                   detections=[{"topic": d["topic"], "aspect": d["aspect"],
                                "evidence": d.get("evidence") or []}
                               for d in dets])
    save(sess, home)

    return {
        "verdict": "ANSWER",
        "accepted": written,
        "refused": refused,
        "quiet": quiet,
        "detections": dets,
        "board": board[:40],
        "proven": proven,
        "conflicts": conflicts,
        "queue": queue,
        "store": _pack_store(store),
        "session": sess.as_dict(),
    }


def _proposals_path(home: Path) -> Path:
    from .vocab_growth import PROPOSALS

    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    return home / PROPOSALS


def _load_proposals(home: Path) -> List[Dict[str, Any]]:
    path = _proposals_path(home)
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else []
    except ValueError:
        return []


def _decided(home: Path) -> Dict[str, str]:
    return {r["word"]: r.get("status", "")
            for r in _load_proposals(home)
            if r.get("word") and r.get("status") in ("accepted", "refused")}


def _remember(queue: List[Dict[str, Any]], home: Path) -> None:
    """Merge this run's candidates into the standing queue, keeping verdicts."""
    rows = _load_proposals(home)
    by_word = {r.get("word"): r for r in rows if r.get("word")}
    for row in queue:
        old = by_word.get(row["word"])
        if old and old.get("status") in ("accepted", "refused"):
            continue
        by_word[row["word"]] = {**(old or {}), **row}
    _proposals_path(home).write_text(
        json.dumps(list(by_word.values()), ensure_ascii=False, indent=2),
        encoding="utf-8")


def _pack_store(store) -> Dict[str, Any]:
    """Enough of the store for search to run in a later request."""
    prov = getattr(store, "provenance", {}) or {}
    return {c: {"facets": sorted(store.crosses[c]),
                "prov": {k: [str(x) for x in v]
                         for k, v in (prov.get(c) or {}).items()}}
            for c in store.crosses}


def search_packed(packed: Dict[str, Any], query: str) -> List[Dict[str, Any]]:
    """The same search as `field_session.search`, over a packed store.

    A packed store rather than a live one because this server holds nothing
    between requests on purpose: a process that keeps the last officer's
    documents in memory is a process that shows them to the next officer.
    """
    from .ja_grammar import ASPECT_OF

    q = (query or "").strip()
    if not q:
        return []
    out = []
    for core in sorted(packed or {}):
        if q not in core and core not in q:
            continue
        entry = packed[core]
        claims = []
        for facet in entry.get("facets", []):
            if ":" not in facet:
                continue
            aspect, value = facet.split(":", 1)
            slot = (entry.get("prov") or {}).get(facet) or []
            claims.append({
                "aspect": aspect, "value": value,
                "pole": (ASPECT_OF.get(value.replace("not_", "")) or ("", "?"))[1],
                "evidence": slot[2] if len(slot) > 2 else "",
            })
        out.append({"core": core, "claims": claims})
        if len(out) >= 40:
            break
    return out


def _lexicon():
    from .jgen_lexicon import open_configured
    return open_configured(HOME)


def run_loop(files: List[Dict[str, str]]) -> Dict[str, Any]:
    """Prove, repair, measure, keep — on the documents in front of you."""
    import shutil
    from .self_evolve import (attempt, propose, propose_suppressions,
                              rejected_before, record)
    from . import ja_grammar as grammar

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        written, refused = _write_files(root, files)
        if not written:
            return {"verdict": "UNKNOWN_NO_READABLE_DOCUMENTS",
                    "refused": refused}
        paths = [str(root)]
        home = HOME
        home.mkdir(parents=True, exist_ok=True)
        skip = rejected_before(home)
        cands = ([(n, "normalizer") for n in propose(paths, skip)]
                 + [(c, "suppression") for c in propose_suppressions(paths, skip)])
        rows, stacked = [], []
        try:
            for name, mech in cands:
                r = attempt(name, paths, mechanism=mech)
                record(r, home)
                rows.append({"mechanism": mech, "candidate": name,
                             "accepted": r.accepted, "reason": r.reason,
                             "before": r.before, "after": r.after})
                if r.accepted:
                    bag = (grammar.SUPPRESSIONS if mech == "suppression"
                           else grammar.NORMALIZERS)
                    entry = (r.normalizer, r.reason)
                    bag.append(entry)
                    stacked.append((bag, entry))
        finally:
            for bag, entry in stacked:
                if entry in bag:
                    bag.remove(entry)
    return {"verdict": "ANSWER", "skipped": skip, "repairs": rows}


def decide(word: str, verdict: str, *, home: Path = HOME) -> Dict[str, Any]:
    """Record the operator's judgement on one vocabulary candidate.

    Accepting writes the overlay. This is the ONE place in the whole system
    where a vocabulary join gets written, and it happens because a person
    pressed a button that says so — `vocab_growth` and `proposal_verify` both
    have no such function, and the eval asserts they never grow one.
    """
    from .vocab_growth import PROPOSALS

    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    path = home / PROPOSALS
    rows = []
    if path.exists():
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            rows = []
    target = next((r for r in rows if r.get("word") == word), None)
    if target is None:
        return {"verdict": "UNKNOWN_NO_SUCH_PROPOSAL", "word": word}

    target["status"] = "accepted" if verdict == "accept" else "refused"
    target["decided_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                    encoding="utf-8")

    written = None
    if verdict == "accept":
        overlay = home / "grammar.json"
        raw = {}
        if overlay.exists():
            try:
                raw = json.loads(overlay.read_text(encoding="utf-8"))
            except ValueError:
                raw = {}
        item = [target["word"], target["aspect"], target["polarity"]]
        have = {tuple(x) for x in raw.get("aspect_joins", [])}
        if tuple(item) not in have:
            raw.setdefault("aspect_joins", []).append(item)
        overlay.write_text(json.dumps(raw, ensure_ascii=False, indent=2),
                           encoding="utf-8")
        written = str(overlay)
    return {"verdict": "ANSWER", "word": word, "status": target["status"],
            "overlay": written}


_PAGE_PATH = Path(__file__).with_name("field_app.html")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # noqa: D401 — a field tool is not a web log
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # Nothing on this page loads from anywhere else, and saying so stops a
        # future edit from quietly introducing a CDN into a tool whose whole
        # promise is that documents do not leave the machine.
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; "
                         "script-src 'unsafe-inline'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, _PAGE_PATH.read_bytes(),
                       "text/html; charset=utf-8")
        elif self.path == "/api/sessions":
            self._json({"verdict": "ANSWER", "sessions": listing(HOME)})
        elif self.path == "/api/lexicon-status":
            self._json({"verdict": "ANSWER", "loaded": _lexicon() is not None,
                        "config": str(HOME / "lexicon.json")})
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        if length > _MAX_BYTES:
            self._json({"verdict": "UNKNOWN_TOO_LARGE",
                        "limit_mb": _MAX_BYTES // (1024 * 1024)}, 413)
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._json({"verdict": "UNKNOWN_BAD_REQUEST"}, 400)
            return

        try:
            if self.path == "/api/read":
                self._json(read_documents(payload.get("files") or []))
            elif self.path == "/api/search":
                self._json({"verdict": "ANSWER",
                            "hits": search_packed(payload.get("store") or {},
                                                  payload.get("q") or "")})
            elif self.path == "/api/loop":
                self._json(run_loop(payload.get("files") or []))
            elif self.path == "/api/decide":
                self._json(decide(payload.get("word") or "",
                                  payload.get("verdict") or "refuse"))
            elif self.path == "/api/note":
                # The handover note. Loaded and re-saved rather than trusted
                # from the page, so a note can never overwrite the findings it
                # is a note about.
                sid = payload.get("session_id") or ""
                sess = load(sid, HOME)
                if sess is None:
                    self._json({"verdict": "UNKNOWN_NO_SUCH_SESSION"})
                    return
                sess.note = str(payload.get("note") or "")[:2000]
                save(sess, HOME)
                self._json({"verdict": "ANSWER", "saved": sid})
            elif self.path == "/api/lexicon":
                lex = _lexicon()
                if lex is None:
                    self._json({"verdict": "UNKNOWN_NO_LEXICON",
                                "config": str(HOME / "lexicon.json")})
                    return
                from .ja_grammar import ASPECT_OF
                known = sorted(ASPECT_OF)
                words = [w for w in (payload.get("words") or "").split() if w]
                self._json({"verdict": "ANSWER", "words": [
                    {"word": w,
                     "state_likeness": lex.state_likeness(w, known),
                     "nearest": lex.nearest(w, known, k=4)} for w in words]})
            else:
                self._send(404, b"not found", "text/plain")
        except Exception as exc:  # noqa: BLE001 — the screen gets a typed reason
            self._json({"verdict": "UNKNOWN_UNREADABLE",
                        "detail": f"{type(exc).__name__}: {exc}"})


def serve(port: int = _PORT, open_browser: bool = True) -> int:
    import webbrowser

    HOME.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Vera field — {url}")
    print("No network. Documents never leave this machine. / "
          "外部接続なし。資料はこの機械から出ません。")
    print("Ctrl+C to stop. / 止めるには Ctrl+C。")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped. / 終了しました。")
    finally:
        server.server_close()
    return 0
