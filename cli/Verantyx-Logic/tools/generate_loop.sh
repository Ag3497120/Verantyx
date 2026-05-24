#!/usr/bin/env bash
set -euo pipefail

# Initialize file
OUT="avh_math/db/text_cross_seed.jsonl"
: > "$OUT"

TOTAL=100000
CHUNK=2000

echo "Starting generation of $TOTAL lines in chunks of $CHUNK..."

start=1
while [ $start -le $TOTAL ]; do
    python3 tools/append_seed_chunk.py $start $CHUNK
    start=$((start + CHUNK))
done

echo "Done! Total lines:"
wc -l "$OUT"
