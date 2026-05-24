#!/usr/bin/env bash
set -euo pipefail

# Absolute paths
BASE_DIR="/Users/motonishikoudai/avh_math"
KB="$BASE_DIR/avh_math/db/foundation_kb.jsonl"
CAND="$BASE_DIR/avh_math/db/phase27_candidates.jsonl"
PATCH="$BASE_DIR/avh_math/db/phase27_patches.jsonl"
P25="$BASE_DIR/avh_math/db/phase25_results.jsonl"
P26="$BASE_DIR/avh_math/db/phase26_patches.jsonl"
TOOLS="$BASE_DIR/tools"

# Phase 25/26 scripts location
PHASE25_JOBS="$BASE_DIR/phase25_jobs.py"
PHASE25_RUNNER="$BASE_DIR/phase25_runner.py"
PHASE26_APPLY="$BASE_DIR/phase26_apply_patches.py"

echo "[Phase27] (1) generate candidates"
python3 "$TOOLS/phase27_generate_candidates.py" --kb "$KB" --out "$CAND"

echo "[Phase27] (2) candidates -> patches"
python3 "$TOOLS/phase27_candidates_to_patches.py" --candidates "$CAND" --out "$PATCH"

echo "[Phase27] (3) apply patches to KB (use your Phase19 applier)"
python3 "$TOOLS/phase19_apply_patches.py" --kb "$KB" --patches "$PATCH" --backup

echo "[Phase27] (4) re-run Phase25 minimality verification (WITH CANDIDATES)"
# Remove previous results to force re-run
rm -f "$P25"
python3 "$PHASE25_RUNNER" --jobs "$BASE_DIR/avh_math/db/phase25_jobs.jsonl" --kb "$KB" --out "$P25" --use-candidates

echo "[Phase27] (5) Phase26 reflect results back to KB"
python3 "$PHASE26_APPLY" --phase25 "$P25" --out "$P26" --include_unknown
python3 "$TOOLS/phase19_apply_patches.py" --kb "$KB" --patches "$P26" --backup

echo "[OK] Phase27 loop complete"