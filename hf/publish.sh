#!/usr/bin/env bash
# Publish Vera α to Hugging Face: the structure as a model repo, the page as
# a STATIC Space that runs the real engine in the browser.
#
#   hf auth login                 # once; the token stays with you
#   NS=your-username ./hf/publish.sh
#
# Two things this learned the hard way, both preserved here:
#
#   * Gradio and Docker Spaces need PRO. A free account gets 402 on create.
#     The Space here is `sdk: static` and runs CPython under Pyodide instead,
#     which is not a downgrade — the page loads the same `verantyx` and the
#     same SQLite the model repo publishes, so there is no second
#     implementation that could disagree with the first.
#   * `hf upload` calls repo-create implicitly and defaults the SDK to
#     gradio, so it 402s against an EXISTING static Space. The upload goes
#     through the Python API, which does not create.
set -euo pipefail

NS="${NS:-}"
MODEL="${MODEL:-$NS/vera-alpha}"
SPACE="${SPACE:-$NS/ask-vera}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
VIS="--public"
[ "${PRIVATE:-0}" = "1" ] && VIS="--private"

if [ -z "$NS" ]; then
  echo "set NS to your Hugging Face username or org, e.g. NS=kofdai $0" >&2
  exit 2
fi
if ! hf auth whoami >/dev/null 2>&1; then
  echo "not logged in — run 'hf auth login' first (the token stays with you)" >&2
  exit 2
fi
if [ ! -f "$HERE/model/vera.db" ] || [ ! -f "$HERE/space_static/vera_web.db" ]; then
  echo "artifacts missing. build them with:" >&2
  echo "  python3 -m verantyx.export_sqlite --verify --web hf/space_static/vera_web.db" >&2
  echo "  cp ~/Projects/vera-corpus/build/vera.db hf/model/" >&2
  echo "  cp ~/Projects/vera-corpus/build/writer.json hf/model/ hf/space_static/" >&2
  echo "  (cd hf/space_static && zip -qr9 verantyx.zip ../../verantyx -x '*__pycache__*')" >&2
  exit 2
fi

# Verify before uploading, not after. A published artifact that answers
# differently from the one the card describes is the failure this whole
# module exists to prevent.
echo "==> verifying the artifact before it goes anywhere"
( cd "$ROOT" && python3 -m verantyx.export_sqlite --verify >/dev/null )
echo "    answers and shape match the built federation"

echo "==> model repo $MODEL  (vera.db 140MB, CC BY-SA 4.0 — see hf/model/LICENSE)"
hf repo create "$MODEL" --type model $VIS --exist-ok
hf upload "$MODEL" "$HERE/model" . --type model \
  --commit-message "Vera α: the federation as one auditable SQLite file"

echo "==> static space $SPACE  (Pyodide runs the real engine client-side)"
hf repo create "$SPACE" --type space --space-sdk static $VIS --exist-ok
python3 - "$SPACE" "$HERE/space_static" <<'PY'
import sys
from huggingface_hub import HfApi
repo, folder = sys.argv[1], sys.argv[2]
print(HfApi().upload_folder(
    folder_path=folder, repo_id=repo, repo_type="space",
    commit_message="Ask Vera — the real engine, in the browser, refusals included"))
PY

cat <<EOF

published
  model  https://huggingface.co/$MODEL
  space  https://huggingface.co/spaces/$SPACE

The Space needs no configuration: it fetches verantyx.zip, vera_web.db and
writer.json from its own repository, loads Pyodide's sqlite3 package, and
builds the sovereign in the visitor's browser. Roughly 30MB gzipped, on a
button press rather than on page load.
EOF
