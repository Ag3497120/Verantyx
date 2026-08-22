"""Execute a Japanese instruction against a GUI app, with no LLM anywhere.

    python3.11 tools/act_from_intent.py "teamsを開いて課題を見て"

The whole path is lookups, OS APIs and string matching:

    intent_frames.parse   the closed 48-verb table            → [OPEN, READ]
    open -a               NSWorkspace's CLI front door        → app running
    CGWindowList          the app's own window bounds         → capture target
    Vision                macOS's built-in OCR, two passes    → text + boxes
    str.__contains__      find the noun THE USER said         → click point
    CGEvent               a real click                        → new screen
    observation.place     the result onto the six arms        → typed verdicts

Nothing here names Teams, and nothing here weighs plausibility. The app
comes from the instruction's OPEN argument and the thing to look for
comes from its READ argument, so 「safariを開いて請求書を見て」 runs the
same code down the same branches.

Rescued from /tmp/teams_ocr.py and /tmp/teams_click.py, which a strong
model wrote on 2026-08-13 and which were one reboot from being gone.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Quartz                                        # noqa: E402
import Vision                                        # noqa: E402
from Foundation import NSURL                         # noqa: E402

from verantyx.intent_frames import parse             # noqa: E402
from verantyx.observation import Observation, report # noqa: E402

SHOT = "/tmp/vera_act.png"


def window_of(app_hint: str):
    """Largest on-screen window whose owner matches. None when absent."""
    opts = (Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements)
    cands = []
    for w in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID):
        owner = (w.get("kCGWindowOwnerName", "") or "")
        if app_hint.casefold() not in owner.casefold():
            continue
        b = w.get("kCGWindowBounds", {})
        cands.append((float(b.get("Width", 0)) * float(b.get("Height", 0)),
                      int(w.get("kCGWindowNumber", 0)),
                      w.get("kCGWindowName", "") or "", b))
    if not cands:
        return None
    cands.sort(reverse=True)
    return cands[0]


def _ocr(png: str, corrected: bool):
    url = NSURL.fileURLWithPath_(png)
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, {})
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(corrected)
    req.setRecognitionLanguages_(["ja-JP", "en-US"])
    ok, _err = handler.performRequests_error_([req], None)
    if not ok:
        return []
    out = []
    for o in (req.results() or []):
        top = o.topCandidates_(1)
        if not top or len(top) == 0:
            continue
        bb = o.boundingBox()
        cx = float(bb.origin.x) + float(bb.size.width) / 2.0
        cy = 1.0 - (float(bb.origin.y) + float(bb.size.height) / 2.0)
        h = float(bb.size.height)
        out.append((cy, cx, h, top[0].string()))
    out.sort()
    return out


def read_window(app_hint: str):
    """Two OCR passes over the app's window. Both are returned; neither
    is repaired, and neither is preferred — that is the caller's problem
    and `observation.readings` is how it is meant to be handled."""
    win = window_of(app_hint)
    if win is None:
        return None
    _area, wid, name, b = win
    # Bring it forward first. `screencapture -l` on an occluded window
    # returns a BLACK image and OCR then returns zero rows — which the
    # 8/13 audit flagged as "zero results treated as success" and never
    # fixed. Activating is half the fix; the caller distinguishing
    # "captured nothing" from "the word is not there" is the other half.
    subprocess.run(["osascript", "-e",
                    'tell application "%s" to activate' % app_hint],
                   capture_output=True)
    time.sleep(1.5)
    if os.path.exists(SHOT):
        os.remove(SHOT)
    subprocess.run(["screencapture", "-x", "-o", "-l", str(wid), SHOT],
                   capture_output=True, text=True)
    if not os.path.exists(SHOT) or os.path.getsize(SHOT) < 1000:
        return None
    WX, WY = float(b.get("X", 0)), float(b.get("Y", 0))
    WW, WH = float(b.get("Width", 0)), float(b.get("Height", 0))
    corr, raw = _ocr(SHOT, True), _ocr(SHOT, False)
    rows = [(cy, cx, h, t, WX + cx * WW, WY + cy * WH)
            for cy, cx, h, t in corr]
    return {"title": name, "rows": rows,
            "raw": [t for _, _, _, t in raw],
            "corrected": [t for _, _, _, t in corr]}


def click(gx: float, gy: float) -> None:
    pt = Quartz.CGPointMake(gx, gy)
    Quartz.CGWarpMouseCursorPosition(pt)
    time.sleep(0.15)
    for kind in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        Quartz.CGEventPost(Quartz.kCGHIDEventTap,
                           Quartz.CGEventCreateMouseEvent(
                               None, kind, pt, Quartz.kCGMouseButtonLeft))
        time.sleep(0.06)


def main(text: str) -> int:
    framed = parse(text)
    print("INTENT:", framed)
    if framed.get("verdict") != "INTENT":
        print("→ 表の外。モデルに渡す番であって、推測する番ではない。")
        return 1

    ops = framed["op"] if isinstance(framed["op"], list) else [framed["op"]]
    args = framed["args"] if isinstance(framed["args"], list) else [framed["args"]]
    plan = list(zip(ops, args))

    app = next((a.get("object") for o, a in plan if o == "OPEN"), None)
    want = next((a.get("object") for o, a in plan if o == "READ"), None)
    if not app:
        print("→ OPEN の対象がない")
        return 1

    # The user says "teams"; the machine holds "Microsoft Teams". Resolve
    # against what is actually installed rather than guessing a bundle
    # name — and refuse when several match, because picking one here is
    # how an agent opens the wrong app with total confidence.
    installed = []
    for root in ("/Applications", "/System/Applications",
                 os.path.expanduser("~/Applications")):
        try:
            installed += [(n[:-4], os.path.join(root, n))
                          for n in os.listdir(root) if n.endswith(".app")]
        except OSError:
            pass
    matches = [(n, p) for n, p in installed if app.casefold() in n.casefold()]
    if not matches:
        print("UNKNOWN_APP_NOT_PRESENT: %r に一致するアプリが無い" % app)
        return 5
    if len(matches) > 1:
        print("AMBIGUOUS_APP: %r に %d 件一致。選ばない。" % (app, len(matches)))
        for n, _p in matches:
            print("   ", n)
        return 6
    app, app_path = matches[0]
    print("RESOLVED: %s" % app_path)

    subprocess.run(["open", "-a", app_path], capture_output=True)
    time.sleep(4.0)

    before = read_window(app)
    if before is None:
        print("UNKNOWN_NO_WINDOW: %s の窓が見つからない" % app)
        return 2
    print("WINDOW: %s  (%d行)" % (before["title"], len(before["rows"])))
    if not before["rows"]:
        # Zero rows is NOT "the word is absent". It is "nothing was read",
        # and calling it absence is how a black capture becomes a
        # confident answer about what is on a screen.
        print("UNKNOWN_CAPTURE_EMPTY: 一文字も読めていない。"
              "窓が隠れている / 描画前 / 画面収録の許可が無い のいずれか。")
        return 7

    if not want:
        return 0

    hits = [r for r in before["rows"] if want in r[3]]
    if not hits:
        print("UNKNOWN_NOT_ON_SCREEN: %r は画面に無い" % want)
        print("  見えている語:", " / ".join(t for _, _, _, t, _, _ in
                                          before["rows"][:14]))
        return 3
    if len(hits) > 1:
        print("AMBIGUOUS_ON_SCREEN: %r が %d 箇所。選ばない。" % (want, len(hits)))
        for cy, cx, _h, t, gx, gy in hits:
            print("   y=%.3f x=%.3f  %s" % (cy, cx, t))
        return 4

    cy, cx, _h, t, gx, gy = hits[0]
    print("CLICK (%d,%d)  text=%r" % (round(gx), round(gy), t))
    click(gx, gy)
    time.sleep(2.5)

    after = read_window(app)
    if after is None:
        print("UNKNOWN_NO_WINDOW_AFTER")
        return 2

    # Did anything change? A click whose postcondition is the same screen
    # is the coordinate-mismatch failure from 8/13, and it must be seen
    # here rather than inferred from the contents later.
    moved = (after["title"] != before["title"]
             or after["corrected"] != before["corrected"])
    print("POSTCONDITION: %s" % ("画面が変わった" if moved
                                 else "変化なし ← クリックは効いていない"))

    rows = after["rows"]
    heights = sorted(h for _, _, h, _, _, _ in rows if h > 0)
    row_h = heights[len(heights) // 2] if heights else 0.0
    last_bottom = max((cy + h / 2 for cy, _, h, _, _, _ in rows), default=1.0)
    closed = (1.0 - last_bottom) >= row_h and row_h > 0

    obs = Observation(
        subject="%s の %s" % (app, want),
        by=("vision:corrected", "vision:raw"),
        after="clicked %r at (%d,%d)" % (t, round(gx), round(gy)),
        yielded=after["title"],
        claim="%s に表示されている %s" % (app, want),
        items=tuple(x[3] for x in rows),
        items_closed=closed)
    rep = report(obs)

    print()
    print("=== 読めた内容 (%d行) ===" % len(rows))
    for cy, _cx, _h, tt, _gx, _gy in rows:
        print("  [y=%.3f] %s" % (cy, tt))
    print()
    print("=== 配置 ===")
    print("  contested      :", rep["contested"])
    print("  instances_open :", rep["instances_open"])
    print("  gap_verdicts   :", rep["gap_verdicts"] or "(なし)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
