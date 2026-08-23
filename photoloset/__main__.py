"""Run the browser application.

    python3 -m photoloset                 # Japanese, this machine only
    python3 -m photoloset --lang en       # English
    python3 -m photoloset --lan           # also reachable from this LAN
"""
from __future__ import annotations

import argparse

from .garment_app import _PORT, serve


def main() -> int:
    ap = argparse.ArgumentParser(prog="photoloset", description=__doc__)
    ap.add_argument("--lang", default="ja", choices=("ja", "en"),
                    help="interface language (default: ja)")
    ap.add_argument("--port", type=int, default=_PORT)
    ap.add_argument("--lan", action="store_true",
                    help="serve to this LAN as well as this machine")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    return serve(port=a.port, open_browser=not a.no_browser,
                 lan=a.lan, lang=a.lang)


if __name__ == "__main__":
    raise SystemExit(main())
