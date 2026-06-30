#!/usr/bin/env bash
# =====================================================================
# run_all.sh — rebuild the entire analysis pipeline from scratch, in order.
# This is the single source of truth for "how to reproduce the numbers."
#
# Prerequisites:
#   - Docker running, with the PostGIS container up:
#       docker run -d --name chicago-postgis -e POSTGRES_PASSWORD=chicago \
#         -e POSTGRES_DB=school_gap -p 5433:5432 postgis/postgis:16-3.4
#   - A Python env with requirements.txt installed; point $PY at it.
#   - Node (for mapshaper, via npx) to simplify the tract geometry.
#
# Usage:   PY=/path/to/python ./analysis/run_all.sh
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")/.."           # repo root

PY="${PY:-python}"
CONTAINER="${CONTAINER:-chicago-postgis}"
psql() { docker exec -i "$CONTAINER" psql -U postgres -d school_gap -v ON_ERROR_STOP=1 -q "$@"; }

echo "== 1. download raw data (Socrata + TIGER + Census Reporter, pinned release) =="
"$PY" analysis/01_download.py

echo "== 2. generate + apply load.sql (base tables) =="
"$PY" analysis/02_load.py
psql -f - < analysis/load.sql

echo "== 3. Finding 1 (creates tract_assignment) =="
psql -f - < analysis/03_finding1.sql > /dev/null

echo "== 4. Finding 1 diagnostics =="
psql -f - < analysis/04_finding1_diagnostics.sql > /dev/null

echo "== 5. proxy tiers =="
psql -f - < analysis/05_proxy_tiers.sql > /dev/null

echo "== 6. honesty check (income vs race; Python/numpy) =="
"$PY" analysis/06_honesty_check.py

echo "== 7. Finding 2 (creates tract_access, tract_full) =="
psql -f - < analysis/07_finding2.sql > /dev/null

echo "== 8. combined status (tie-safe, deterministic; creates tract_combined) =="
psql -f - < analysis/08_combined.sql

echo "== 8b. composite distress score (8 indicators; feeds the community clustering) =="
psql -f - < analysis/11_distress.sql > /dev/null

echo "== 8c. community-area metrics for clustering =="
psql -f - < analysis/12_community_metrics.sql > /dev/null

echo "== 8d. routed access: real driving (OSRM) + CTA transit (OTP) =="
# The matrices are produced by engine-dependent stages run manually:
#   bash analysis/osrm/osrm_up.sh && "$PY" analysis/14_driving_access.py
#   bash analysis/otp/otp_up.sh  && "$PY" analysis/15_transit_access.py
# Their CSV outputs are committed, so this clean-room rebuild consumes them
# without needing the engines up. If absent, fall back to an empty table so the
# straight-line export still works.
if [ -f output/driving_times_selective.csv ] && [ -f output/transit_times_selective.csv ]; then
  docker cp output/driving_times_selective.csv "$CONTAINER":/tmp/
  docker cp output/transit_times_selective.csv "$CONTAINER":/tmp/
  psql -f - < analysis/16_routed_access.sql > /dev/null
else
  echo "   (no routed matrices found; exporting straight-line only — see analysis/osrm + analysis/otp)"
  psql -c "DROP TABLE IF EXISTS tract_routed CASCADE; CREATE TABLE tract_routed (
    geoid text PRIMARY KEY, drive_min_nearest_selective numeric, drive_min_to_nearest_elite numeric,
    n_selective_within_15min_drive int, sat_of_nearest_selective_drive numeric,
    transit_min_nearest_selective numeric, transit_min_to_nearest_elite numeric,
    n_selective_within_30min_transit int, sat_of_nearest_selective_transit numeric);" > /dev/null
fi

echo "== 9. export GeoJSON/JSON views + files =="
psql -f - < analysis/09_export.sql > /dev/null
for layer in tracts schools city_boundary community_areas; do
  docker exec "$CONTAINER" psql -U postgres -d school_gap -t -A \
    -c "SELECT * FROM ${layer}_geojson_v;" > "output/${layer}.geojson"
done
docker exec "$CONTAINER" psql -U postgres -d school_gap -t -A \
  -c "SELECT data FROM community_metrics_json_v;" > "output/community_metrics.json"

echo "== 9b. community-area PCA + clustering =="
"$PY" analysis/13_community_groups.py

echo "== 9c. CTA 'L' rail context layer =="
# Needs the CTA GTFS fetched by analysis/otp/otp_up.sh. Its GeoJSON outputs are
# committed, so a clean-room rebuild without the feed reuses them.
if [ -f data/otp/cta.gtfs.zip ]; then
  "$PY" analysis/17_cta_rail.py
else
  echo "   (no CTA feed; reusing committed cta_rail_*.geojson — see analysis/otp/otp_up.sh)"
fi

echo "== 9d. real route geometry for click-to-route (needs OSRM :5000 + OTP :8080) =="
# Engine-dependent (can't be rebuilt from data files alone). Regenerates when both
# routers are up; otherwise the committed output/routes.geojson is reused as-is.
if curl -sf "http://localhost:5000/route/v1/driving/-87.63,41.88;-87.62,41.89" >/dev/null 2>&1 \
   && curl -sf -X POST "http://localhost:8080/otp/routers/default/index/graphql" \
        -H "Content-Type: application/json" --data '{"query":"{feeds{feedId}}"}' >/dev/null 2>&1; then
  "$PY" analysis/18_routes.py
else
  echo "   (routers down; reusing committed output/routes.geojson — see analysis/osrm + analysis/otp)"
fi

echo "== 10. simplify tracts (topology-aware) + copy layers to frontend =="
cp output/schools.geojson output/city_boundary.geojson output/community_areas.geojson output/community_groups.json frontend/public/data/
npx -y mapshaper output/tracts.geojson -simplify 18% keep-shapes \
  -o force frontend/public/data/tracts.geojson

echo "== DONE — pipeline rebuilt from scratch =="
