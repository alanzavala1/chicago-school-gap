#!/usr/bin/env bash
# =====================================================================
# osrm_up.sh — bring up a local OSRM driving-routing engine for Chicago.
#
# This is a BUILD-TIME analysis tool, exactly like the PostGIS container:
# it computes a tract->school driving-time matrix (see 14_driving_access.py)
# whose results are baked into static output/. Nothing here ships to prod.
#
# What it does (all idempotent):
#   1. downloads a Chicago OSM street extract into data/osrm/   (~100 MB)
#   2. builds the routing graph with the MLD pipeline (one-time, ~1-2 min)
#   3. (re)starts osrm-routed serving the /table matrix API on :5000
#
# Prereqs: Docker running. No Java, no local install — all in the container.
# Usage:   bash analysis/osrm/osrm_up.sh
# Stop:    docker rm -f chicago-osrm
# =====================================================================
set -euo pipefail
# git-bash on Windows otherwise rewrites the container-side /data, /opt paths.
export MSYS_NO_PATHCONV=1

cd "$(dirname "$0")/../.."          # repo root
OSRM_DIR="data/osrm"
mkdir -p "$OSRM_DIR"

# BBBike's Chicago extract (smaller, faster build). If you ever see unrouted
# tracts in the validation step, swap in the statewide Geofabrik extract for
# fuller coverage:  PBF_URL=https://download.geofabrik.de/north-america/us/illinois-latest.osm.pbf
PBF_URL="${PBF_URL:-https://download.bbbike.org/osm/bbbike/Chicago/Chicago.osm.pbf}"
PBF="$OSRM_DIR/chicago.osm.pbf"
IMG="osrm/osrm-backend"
NAME="chicago-osrm"
ABS="$(pwd)/$OSRM_DIR"

echo "== 1. OSM extract =="
if [ ! -s "$PBF" ]; then
  echo "downloading $PBF_URL"
  curl -L --fail -o "$PBF" "$PBF_URL"
else
  echo "[skip] $PBF already present ($(du -h "$PBF" | cut -f1))"
fi

echo "== 2. build routing graph (MLD) =="
if [ ! -f "$OSRM_DIR/.built" ]; then
  docker run --rm -t -v "$ABS:/data" "$IMG" osrm-extract   -p /opt/car.lua /data/chicago.osm.pbf
  docker run --rm -t -v "$ABS:/data" "$IMG" osrm-partition  /data/chicago.osrm
  docker run --rm -t -v "$ABS:/data" "$IMG" osrm-customize  /data/chicago.osrm
  touch "$OSRM_DIR/.built"
else
  echo "[skip] graph already built (delete $OSRM_DIR/.built to force a rebuild)"
fi

echo "== 3. (re)start routing server =="
docker rm -f "$NAME" >/dev/null 2>&1 || true
# --max-table-size must exceed (origins + destinations) in a single /table call;
# 14_driving_access.py batches well under this, but give plenty of headroom.
docker run -d --name "$NAME" -p 5000:5000 -v "$ABS:/data" "$IMG" \
  osrm-routed --algorithm mld --max-table-size 5000 /data/chicago.osrm >/dev/null

sleep 2
echo "OSRM serving on http://localhost:5000  (test: curl 'http://localhost:5000/table/v1/driving/-87.63,41.88;-87.62,41.89?annotations=duration')"
