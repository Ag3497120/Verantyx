"""Tiny terminal UI — arrow-key selection with a dumb-terminal fallback.

No dependencies. `select(...)` renders a menu navigated with ↑/↓ (or j/k),
Enter confirms, Esc/q cancels. `read_input(...)` reads one logical line of
input but captures a multi-line paste (traceback, multi-sentence note, JSON
blob) as a single string instead of splitting it line by line — the plain
``input()`` builtin submits on every embedded newline in a paste, which
silently truncates or misfires multi-line pastes. When stdin is not a TTY
(CI, pipes, forks) everything falls back to plain ``input()``, so tests stay
scriptable and deterministic.
"""
from __future__ import annotations

import sys
from typing import Callable, List, Optional, Sequence


def _is_tty() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _read_key() -> str:
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":  # escape sequence
            nxt = sys.stdin.read(1)
            if nxt == "[":
                arrow = sys.stdin.read(1)
                return {"A": "up", "B": "down"}.get(arrow, "esc")
            return "esc"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def select(
    title: str,
    options: Sequence[str],
    *,
    default: int = 0,
    descriptions: Optional[Sequence[str]] = None,
) -> Optional[int]:
    """Return the chosen index, or None if cancelled."""
    if not options:
        return None
    if not _is_tty():
        print(title)
        for i, o in enumerate(options):
            print(f"  [{i}] {o}")
        try:
            raw = input(f"select 0-{len(options)-1} (default {default}): ").strip()
        except EOFError:
            return default
        if raw == "":
            return default
        try:
            i = int(raw)
            return i if 0 <= i < len(options) else None
        except ValueError:
            return None

    idx = max(0, min(default, len(options) - 1))
    n_lines = len(options) + 1
    print(title)
    first = True
    while True:
        if not first:
            sys.stdout.write(f"\x1b[{n_lines - 1}A")
        first = False
        for i, o in enumerate(options):
            marker = "▶" if i == idx else " "
            desc = ""
            if descriptions and i == idx and descriptions[i]:
                desc = f"  — {descriptions[i]}"
            line = f" {marker} {o}{desc}"
            sys.stdout.write("\x1b[2K" + line[:120] + "\n")
        sys.stdout.flush()
        key = _read_key()
        if key in ("up", "k"):
            idx = (idx - 1) % len(options)
        elif key in ("down", "j"):
            idx = (idx + 1) % len(options)
        elif key in ("\r", "\n"):
            return idx
        elif key in ("esc", "q", "\x03"):
            return None


def _consume_raw_input(
    next_char: Callable[[], str], *, echo: bool = True
) -> Optional[str]:
    """Pure state machine behind ``read_input``'s TTY path — testable
    without a real terminal by injecting a fake ``next_char``.

    Recognizes the bracketed-paste markers a terminal sends around a paste
    (``ESC[200~`` ... ``ESC[201~``): while "pasting", ``\\r``/``\\n`` become
    literal newlines in the buffer instead of submitting, and a CRLF pair
    collapses to one newline. A real Enter (outside a paste) submits.
    Backspace edits the buffer; Ctrl-C or EOF-with-empty-buffer returns
    None. Other escape sequences (arrow keys, etc.) are swallowed, not
    inserted into the buffer.
    """
    buf: List[str] = []
    pasting = False
    last_was_cr = False
    while True:
        ch = next_char()
        if ch == "" or ch == "\x03" or (ch == "\x04" and not buf):
            return None
        if ch == "\x1b":
            nxt = next_char()
            if nxt == "[":
                rest = ""
                while True:
                    c2 = next_char()
                    if c2 == "":
                        break
                    rest += c2
                    if not (c2.isdigit() or c2 == ";"):
                        break
                if rest == "200~":
                    pasting = True
                elif rest == "201~":
                    pasting = False
            last_was_cr = False
            continue
        if ch in ("\r", "\n"):
            if pasting:
                if ch == "\n" and last_was_cr:
                    last_was_cr = False
                    continue
                buf.append("\n")
                if echo:
                    sys.stdout.write("\r\n")
                    sys.stdout.flush()
                last_was_cr = ch == "\r"
                continue
            if echo:
                sys.stdout.write("\r\n")
                sys.stdout.flush()
            return "".join(buf)
        if ch in ("\x7f", "\x08"):
            last_was_cr = False
            if buf:
                buf.pop()
                if echo:
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            continue
        last_was_cr = False
        buf.append(ch)
        if echo:
            sys.stdout.write(ch)
            sys.stdout.flush()


def read_input(prompt: str = "") -> Optional[str]:
    """Read one logical input; a TTY paste (multi-line, embedded newlines)
    comes back as a single string instead of being split line by line.

    Falls back to plain ``input()`` when stdin is not a TTY, or when
    ``termios``/``tty`` aren't available (non-Unix). Returns None on
    Ctrl-C, Ctrl-D, or EOF — callers should treat that as "quit".
    """
    if not _is_tty():
        try:
            return input(prompt)
        except EOFError:
            return None
    try:
        import termios
        import tty
    except ImportError:
        try:
            return input(prompt)
        except EOFError:
            return None

    sys.stdout.write(prompt)
    sys.stdout.flush()
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        sys.stdout.write("\x1b[?2004h")  # enable bracketed paste
        sys.stdout.flush()
        tty.setraw(fd)
        return _consume_raw_input(lambda: sys.stdin.read(1))
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\x1b[?2004l")  # disable bracketed paste
        sys.stdout.flush()


def confirm_action(
    summary: str,
    *,
    detail: str = "",
    allow_always: bool = True,
) -> str:
    """Approval gate for agent actions → 'approve' | 'always' | 'deny'."""
    print(f"\n┌─ approval required ─────────────────────────")
    print(f"│ {summary}")
    for line in (detail or "").splitlines()[:12]:
        print(f"│   {line[:110]}")
    print(f"└─────────────────────────────────────────────")
    opts: List[str] = ["Approve (once)"]
    keys = ["approve"]
    if allow_always:
        opts.append("Always allow this tool (this session)")
        keys.append("always")
    opts.append("Deny")
    keys.append("deny")
    i = select("", opts, default=0)
    return keys[i] if i is not None else "deny"
