#!/usr/bin/env sh
# Overnight pilot + quality proof — one paste.
#
# Runs the FULL pipeline over the stress set:
#   curate -> research -> draft -> write -> QC -> structural gate -> semantic critic (loop)
# then the blinded quality judge over the produced paths.
#
# Resumable (safe to re-run: finished curations are skipped). Outputs land only in
# experiments/pilot/ (never kb/paths). BILLS the Anthropic API.
#
# Usage:
#   ./scripts/run_overnight.sh                      # foreground
#   nohup ./scripts/run_overnight.sh > experiments/pilot/overnight.log 2>&1 &   # background + log
set -e
cd "$(dirname "$0")/.."
PY=./.venv-py310/bin/python

echo "[overnight] $(date)  pilot (--critic) — full pipeline incl. the semantic validator"
$PY scripts/run_pilot.py --run --critic

echo "[overnight] $(date)  pilot done — running the blinded quality judge over the output"
$PY scripts/run_blinded_judge.py experiments/pilot/outputs --run --out-dir experiments/pilot/blinded

echo "[overnight] $(date)  DONE."
echo "  cost/iters/verdicts : experiments/pilot/run_summary.json"
echo "  quality report      : experiments/pilot/blinded/blinded_judge_results.md"
echo "  per-path critic audit: provenance/<id>.semantic_review.yaml"
