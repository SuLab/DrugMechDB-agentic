#!/usr/bin/env bash
# Prompt-caching validation: one curation per pair, curator + critic on Opus 4.8,
# sequential so the shared static prefix stays warm across curations as it would in
# a campaign. Stops before the next pair once cumulative spend passes the budget.
set -u
cd "$(dirname "$0")/../.."
BUDGET=22
TOTAL=0
for id in DB00619_MESH_D015464_1 DB00843_MESH_D000544_1 DB09038_MESH_D003924_1 \
          DB00002_MESH_D003110_1 DB00009_MESH_D011655_1; do
  if awk "BEGIN{exit !($TOTAL > $BUDGET)}"; then
    echo "BUDGET STOP: cumulative \$$TOTAL > \$$BUDGET before $id"; break
  fi
  echo "=== $id  (cumulative so far \$$TOTAL) ==="
  .venv-py310/bin/python scripts/run_pilot.py --pairs experiments/caching_test/pairs.yaml \
      --out-root experiments/caching_test --critic --run --only "$id"
  latest=$(ls -t experiments/caching_test/run_summary_*.json | head -1)
  cost=$(.venv-py310/bin/python -c "import json;print(json.load(open('$latest'))['totals'].get('total_cost_usd') or 0)")
  TOTAL=$(awk "BEGIN{print $TOTAL + $cost}")
done
echo "DONE cumulative \$$TOTAL"
