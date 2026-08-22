#!/usr/bin/env python3
"""
ax_opaque_reader.py — deterministic screen reader / clicker for AX-opaque apps.

WHY THIS EXISTS
    Microsoft Teams (bundle com.microsoft.teams2) refuses AXManualAccessibility
    with kAXErrorAttributeUnsupported (-25205), so its web content exposes NO
    accessibility tree -- an AX dump yields only unnamed container groups.
    The only reliable programmatic route is:
        capture window -> Vision OCR -> operate via synthesized CGEvent clicks.

DESIGN NOTES (the things a throwaway version gets wrong)
    1. TWO OCR PASSES, NEVER ONE.
       Vision's usesLanguageCorrection is essential for Japanese prose but
       actively HARMFUL for alphanumeric identifiers: it "corrects" course codes
       such as IA22 -> 1A22 and ajax -> aijax. We therefore run:
           pass "ja"  : languageCorrection=ON,  languages=[ja-JP, en-US]
           pass "raw" : languageCorrection=OFF, languages=[en-US]
       and report BOTH. The caller can then see where the two disagree instead
       of receiving a single silently-fabricated string.
    2. NO SILENT EMPTY CAPTURES.
       screencapture -l returns rc=0 and writes a valid-but-black PNG when the
       target window is occluded/minimised. We treat "0 OCR observations" as a
       hard failure rather than an empty-but-successful read.
    3. CLICKS ARE VERIFIED.
       click subcommand takes --expect TEXT and re-OCRs after the click; if the
       expected text does not appear it retries, then exits non-zero. It never
       reports a transition it did not observe.
    4. Coordinates are converted to global screen space from the live window
       bounds each run -- never cached, never guessed.

USAGE
    read  [--app NAME] [--json]
    click TEXT [--app NAME] [--occurrence N] [--expect TEXT] [--retries N]
    tabs  --names A,B,C      (read, then report which of the names are present)

EXIT CODES
    0 ok | 2 no window | 3 capture/OCR empty | 4 text not found | 5 postcondition failed
"""

import argparse
import json
import os
import subprocess
import sys
import time

import Quartz
import Vision
from Foundation import NSURL

DEFAULT_APP = "Teams"
SHOT = "/tmp/ax_opaque_reader_shot.png"

# Identifiers that Vision's language model mangles. Supplying them as custom
# words lets the corrected pass keep them intact instead of inventing variants.
CUSTOM_WORDS = [
    "ajax", "Ajax", "AJAX", "JavaScript", "Copilot", "Teams",
    "IA22", "IH22", "IH12", "JS22", "NT21", "IO21", "DB22", "PY23",
    "OHS26", "OHC26", "NAKAO", "OHIH12A63238", "OHIH12A63234",
]


# --------------------------------------------------------------------------
# window discovery
# --------------------------------------------------------------------------
def find_window(app_substr):
    """Largest on-screen window whose owner name contains app_substr."""
    opts = (Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements)
    infos = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID)
    cands = []
    for w in infos or []:
        owner = w.get("kCGWindowOwnerName", "") or ""
        if app_substr.lower() not in owner.lower():
            continue
        b = w.get("kCGWindowBounds", {}) or {}
        area = float(b.get("Width", 0)) * float(b.get("Height", 0))
        if area <= 0:
            continue
        cands.append({
            "area": area,
            "wid": int(w.get("kCGWindowNumber", 0)),
            "owner": owner,
            "title": w.get("kCGWindowName", "") or "",
            "x": float(b.get("X", 0)), "y": float(b.get("Y", 0)),
            "w": float(b.get("Width", 0)), "h": float(b.get("Height", 0)),
        })
    if not cands:
        return None
    cands.sort(key=lambda c: -c["area"])
    return cands[0]


def activate(app_substr, settle=1.2):
    # osascript needs the real app name; "Teams" resolves to Microsoft Teams.
    name = "Microsoft Teams" if "teams" in app_substr.lower() else app_substr
    subprocess.run(["osascript", "-e",
                    'tell application "%s" to activate' % name],
                   capture_output=True)
    time.sleep(settle)


# --------------------------------------------------------------------------
# capture + OCR
# --------------------------------------------------------------------------
def capture(win):
    if os.path.exists(SHOT):
        os.remove(SHOT)
    r = subprocess.run(["screencapture", "-x", "-o", "-l", str(win["wid"]), SHOT],
                       capture_output=True, text=True)
    if not os.path.exists(SHOT):
        return None, "screencapture produced no file (rc=%d, %s)" % (
            r.returncode, r.stderr.strip())
    size = os.path.getsize(SHOT)
    if size < 1000:
        return None, "capture too small (%d bytes) -- window likely occluded" % size
    # real pixel dimensions (Retina backing store, not points)
    src = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(SHOT), None)
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None) if src else None
    dims = (Quartz.CGImageGetWidth(img), Quartz.CGImageGetHeight(img)) if img else (0, 0)
    return {"bytes": size, "px": dims}, None


def _ocr_pass(corrected):
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(bool(corrected))
    try:
        req.setRecognitionLanguages_(["ja-JP", "en-US"] if corrected else ["en-US"])
    except Exception:
        pass
    if corrected:
        try:
            req.setCustomWords_(CUSTOM_WORDS)
        except Exception:
            pass
    return req


def ocr(win):
    """Returns (rows_corrected, rows_raw). Row = dict with normalized + global coords."""
    url = NSURL.fileURLWithPath_(SHOT)
    out = []
    for corrected in (True, False):
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, {})
        req = _ocr_pass(corrected)
        ok, err = handler.performRequests_error_([req], None)
        if not ok:
            return None, None, "Vision request failed: %s" % err
        rows = []
        for o in (req.results() or []):
            top = o.topCandidates_(1)
            if not top or len(top) == 0:
                continue
            cand = top[0]
            bb = o.boundingBox()
            cx = float(bb.origin.x) + float(bb.size.width) / 2.0
            cy = 1.0 - (float(bb.origin.y) + float(bb.size.height) / 2.0)
            rows.append({
                "text": cand.string(),
                "conf": round(float(cand.confidence()), 3),
                "nx": round(cx, 4), "ny": round(cy, 4),
                "gx": round(win["x"] + cx * win["w"]),
                "gy": round(win["y"] + cy * win["h"]),
            })
        rows.sort(key=lambda r: (r["ny"], r["nx"]))
        out.append(rows)
    return out[0], out[1], None


def group_lines(rows, tol=0.012):
    """Cluster fragments into visual lines so a card's title/date/class read together."""
    lines, cur = [], []
    for r in rows:
        if cur and abs(r["ny"] - cur[0]["ny"]) > tol:
            lines.append(cur)
            cur = []
        cur.append(r)
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda r: r["nx"])
        out.append({
            "ny": ln[0]["ny"],
            "text": "  ".join(x["text"] for x in ln),
            "parts": ln,
        })
    return out


def read_window(app):
    win = find_window(app)
    if not win:
        print("ERR no on-screen window for app substring %r" % app)
        sys.exit(2)
    meta, err = capture(win)
    if err:
        print("ERR capture: %s" % err)
        sys.exit(3)
    corr, raw, err = ocr(win)
    if err:
        print("ERR ocr: %s" % err)
        sys.exit(3)
    if not corr and not raw:
        print("ERR OCR returned zero observations -- capture was blank/occluded")
        sys.exit(3)
    return win, meta, corr, raw


# --------------------------------------------------------------------------
# clicking
# --------------------------------------------------------------------------
def click_at(gx, gy):
    pt = Quartz.CGPointMake(float(gx), float(gy))
    Quartz.CGWarpMouseCursorPosition(pt)
    time.sleep(0.15)
    down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown,
                                          pt, Quartz.kCGMouseButtonLeft)
    up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp,
                                        pt, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.06)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def pick(rows, target, occurrence):
    exact = [r for r in rows if r["text"].strip() == target]
    sub = [r for r in rows if target in r["text"] and r not in exact]
    hits = exact + sub
    if not hits:
        return None, 0
    if occurrence >= len(hits):
        return None, len(hits)
    return hits[occurrence], len(hits)


# --------------------------------------------------------------------------
def dump(win, meta, corr, raw, as_json):
    if as_json:
        print(json.dumps({"window": win, "capture": meta,
                          "corrected": corr, "raw": raw},
                         ensure_ascii=False, indent=1))
        return
    print("WINDOW  %s" % win["title"])
    print("ORIGIN  (%.0f,%.0f)  SIZE %.0fx%.0f pt   CAPTURE %dx%d px (%d bytes)"
          % (win["x"], win["y"], win["w"], win["h"],
             meta["px"][0], meta["px"][1], meta["bytes"]))
    print("        scale = %.2fx  (>1 confirms native Retina capture)"
          % (meta["px"][0] / win["w"] if win["w"] else 0))

    print("\n--- PASS A: language-corrected (Japanese prose is reliable here) ---")
    for ln in group_lines(corr):
        print("[y=%.3f] %s" % (ln["ny"], ln["text"]))

    print("\n--- PASS B: raw, no language correction (identifiers are reliable here) ---")
    for ln in group_lines(raw):
        print("[y=%.3f] %s" % (ln["ny"], ln["text"]))

    ca = {r["text"] for r in corr}
    rb = {r["text"] for r in raw}
    only_a = sorted(ca - rb)
    only_b = sorted(rb - ca)
    print("\n--- DISAGREEMENT (these strings are NOT trustworthy verbatim) ---")
    print("only in corrected: %s" % (only_a if only_a else "(none)"))
    print("only in raw      : %s" % (only_b if only_b else "(none)"))
    low = [r for r in corr if r["conf"] < 0.5]
    print("low-confidence (<0.50): %s"
          % ([(r["text"], r["conf"]) for r in low] if low else "(none)"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["read", "click"])
    ap.add_argument("text", nargs="?")
    ap.add_argument("--app", default=DEFAULT_APP)
    ap.add_argument("--occurrence", type=int, default=0)
    ap.add_argument("--expect")
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    activate(a.app)

    if a.cmd == "read":
        win, meta, corr, raw = read_window(a.app)
        dump(win, meta, corr, raw, a.json)
        return

    if not a.text:
        print("ERR click requires TEXT")
        sys.exit(1)

    for attempt in range(a.retries + 1):
        win, meta, corr, raw = read_window(a.app)
        hit, n = pick(corr, a.text, a.occurrence)
        if hit is None:
            hit, n = pick(raw, a.text, a.occurrence)
        if hit is None:
            print("ERR text %r not found (candidates matched: %d)" % (a.text, n))
            print("visible lines were:")
            for ln in group_lines(corr):
                print("  %s" % ln["text"])
            sys.exit(4)

        print("CLICK attempt %d -> (%d,%d) text=%r  [%d match(es)]"
              % (attempt + 1, hit["gx"], hit["gy"], hit["text"], n))
        before = win["title"]
        click_at(hit["gx"], hit["gy"])
        time.sleep(2.2)

        win2, meta2, corr2, raw2 = read_window(a.app)
        if a.expect:
            texts = [r["text"] for r in corr2] + [r["text"] for r in raw2]
            if any(a.expect in t for t in texts) or a.expect in win2["title"]:
                print("POSTCONDITION OK: %r observed" % a.expect)
                dump(win2, meta2, corr2, raw2, a.json)
                return
            print("POSTCONDITION MISS: %r not observed (title now %r)"
                  % (a.expect, win2["title"]))
            continue

        print("(no --expect given; title %r -> %r)" % (before, win2["title"]))
        dump(win2, meta2, corr2, raw2, a.json)
        return

    print("ERR postcondition %r never satisfied after %d attempts"
          % (a.expect, a.retries + 1))
    sys.exit(5)


if __name__ == "__main__":
    main()
