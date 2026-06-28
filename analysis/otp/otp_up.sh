#!/usr/bin/env bash
# =====================================================================
# otp_up.sh — bring up a local OpenTripPlanner (OTP2) transit engine for Chicago.
#
# Build-time analysis tool (like PostGIS / OSRM): it computes a tract->school
# CTA transit-time matrix (see 15_transit_access.py) whose results are baked into
# static output/. Nothing here ships to production.
#
# What it does (idempotent):
#   1. downloads the CTA GTFS schedule feed into data/otp/   (~98 MB)
#   2. reuses the Chicago OSM extract from the OSRM stage (the walk network)
#   3. builds the OTP graph (one-time, ~2-5 min)
#   4. (re)starts OTP serving the GraphQL routing API on :8080
#
# OTP version is PINNED (reproducibility, like the pinned ACS release): the
# GraphQL endpoint/schema differ across OTP releases, so we don't float :latest.
#
# Prereqs: Docker running; analysis/osrm/osrm_up.sh already run once (for the
#          OSM extract). No Java/local install — all in the container.
# Usage:   bash analysis/otp/otp_up.sh
# Stop:    docker rm -f chicago-otp
# =====================================================================
set -euo pipefail
export MSYS_NO_PATHCONV=1          # keep git-bash from rewriting container paths

cd "$(dirname "$0")/../.."         # repo root
OTP_DIR="data/otp"
mkdir -p "$OTP_DIR"

GTFS_URL="${GTFS_URL:-https://www.transitchicago.com/downloads/sch_data/google_transit.zip}"
GTFS="$OTP_DIR/cta.gtfs.zip"
OSM_SRC="data/osrm/chicago.osm.pbf"
OSM="$OTP_DIR/chicago.osm.pbf"
IMG="opentripplanner/opentripplanner:2.5.0"
NAME="chicago-otp"
ABS="$(pwd)/$OTP_DIR"
XMX="${OTP_XMX:-6g}"               # graph build/serve heap; box has 32 GB

echo "== 1. CTA GTFS feed =="
if [ ! -s "$GTFS" ]; then
  echo "downloading $GTFS_URL"
  curl -L --fail -o "$GTFS" "$GTFS_URL"
else
  echo "[skip] $GTFS present ($(du -h "$GTFS" | cut -f1))"
fi

echo "== 2. OSM street/walk network (reuse OSRM extract) =="
if [ ! -s "$OSM" ]; then
  if [ ! -s "$OSM_SRC" ]; then
    echo "ERROR: $OSM_SRC not found. Run analysis/osrm/osrm_up.sh first (it downloads the extract)."
    exit 1
  fi
  cp "$OSM_SRC" "$OSM"
  echo "copied $OSM_SRC -> $OSM"
else
  echo "[skip] $OSM present"
fi

echo "== 3. build OTP graph =="
if [ ! -f "$OTP_DIR/graph.obj" ]; then
  docker run --rm -e "JAVA_TOOL_OPTIONS=-Xmx${XMX}" -v "$ABS:/var/opentripplanner" "$IMG" --build --save
else
  echo "[skip] graph.obj present (delete it to force a rebuild)"
fi

echo "== 4. (re)start OTP server =="
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -e "JAVA_TOOL_OPTIONS=-Xmx${XMX}" -p 8080:8080 \
  -v "$ABS:/var/opentripplanner" "$IMG" --load --serve >/dev/null

echo "OTP starting on http://localhost:8080 — graph load takes ~20-60s."
echo "Wait for readiness, then run:  python analysis/15_transit_access.py"
