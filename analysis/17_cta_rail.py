"""
Stage 17 — CTA transit network -> GeoJSON (map context layers).

Visual-context layers for the map (not part of the analysis): the CTA rapid-transit
('L') lines in their official colors + rail stations, and the bus route network.
Together they make the transit-access finding *legible*: the fast 'L' clusters
downtown/north, while buses blanket the whole city — so the South/Southwest gap is
about a lack of *fast* rail, not a lack of transit. That nuance is the honest story.

Source: the CTA GTFS already downloaded for OTP (data/otp/cta.gtfs.zip).
  rail = route_type 1 (8 lines), bus = route_type 3 (125 routes).
Buses are deduped to the longest shape per route and geometry-simplified
(Douglas–Peucker) so the layer stays light enough to ship statically.

Outputs (also copied to the frontend):
  output/cta_rail_lines.geojson      — one LineString per rail shape, with color
  output/cta_rail_stations.geojson   — rail stations (location_type == 1)
  output/cta_bus_lines.geojson       — one simplified LineString per bus route

Usage:  python analysis/17_cta_rail.py
"""
import csv
import io
import json
import math
import os
import zipfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
GTFS = os.path.join(ROOT, "data", "otp", "cta.gtfs.zip")
OUT = os.path.join(ROOT, "output")
FRONTEND = os.path.join(ROOT, "frontend", "public", "data")
RAIL, BUS = "1", "3"   # GTFS route_type: 1 = subway/metro ('L'), 3 = bus


def read(zf, name):
    with zf.open(name) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")))


def _perp(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(points, eps):
    """Iterative Douglas–Peucker (lon/lat). Keeps shape, drops redundant points."""
    n = len(points)
    if n < 3:
        return points[:]
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        s, e = stack.pop()
        dmax, idx = 0.0, 0
        for i in range(s + 1, e):
            d = _perp(points[i], points[s], points[e])
            if d > dmax:
                dmax, idx = d, i
        if dmax > eps and idx > 0:
            keep[idx] = True
            stack.append((s, idx))
            stack.append((idx, e))
    return [points[i] for i in range(n) if keep[i]]


def round_coords(coords):
    return [[round(lon, 5), round(lat, 5)] for lon, lat in coords]


def ordered_shapes(zf, route_ids):
    """shape_id -> ordered [[lon,lat],...] for shapes used by the given routes,
    plus shape_id -> route_id."""
    shape_route = {}
    for t in read(zf, "trips.txt"):
        rid, sid = t.get("route_id"), t.get("shape_id")
        if rid in route_ids and sid and sid not in shape_route:
            shape_route[sid] = rid
    seqs = defaultdict(list)
    for row in read(zf, "shapes.txt"):
        sid = row["shape_id"]
        if sid in shape_route:
            seqs[sid].append((int(row["shape_pt_sequence"]),
                              float(row["shape_pt_lon"]), float(row["shape_pt_lat"])))
    shapes = {sid: [[lon, lat] for _, lon, lat in sorted(rows)] for sid, rows in seqs.items()}
    return shapes, shape_route


def main():
    if not os.path.exists(GTFS):
        raise FileNotFoundError(f"{GTFS} missing — run analysis/otp/otp_up.sh first (it downloads the feed).")
    zf = zipfile.ZipFile(GTFS)
    routes = read(zf, "routes.txt")

    # ---- rail: every shape, official per-route color, crisp simplification ----
    rail = {r["route_id"]: r for r in routes if r["route_type"] == RAIL}
    rail_shapes, rail_shape_route = ordered_shapes(zf, set(rail))
    rail_features = []
    for sid, coords in rail_shapes.items():
        coords = round_coords(simplify(coords, 0.00004))
        if len(coords) < 2:
            continue
        r = rail[rail_shape_route[sid]]
        rail_features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"route": r.get("route_long_name") or r.get("route_short_name"),
                           "color": "#" + (r.get("route_color") or "888888")},
        })

    rail_stations = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(float(s["stop_lon"]), 5), round(float(s["stop_lat"]), 5)]},
        "properties": {"name": s["stop_name"]},
    } for s in read(zf, "stops.txt") if s.get("location_type") == "1"]

    # ---- bus: one (longest) shape per route, heavier simplification, uniform ----
    bus = {r["route_id"]: r for r in routes if r["route_type"] == BUS}
    bus_shapes, bus_shape_route = ordered_shapes(zf, set(bus))
    longest = {}  # route_id -> (shape_id, npts)
    for sid, coords in bus_shapes.items():
        rid = bus_shape_route[sid]
        if rid not in longest or len(coords) > longest[rid][1]:
            longest[rid] = (sid, len(coords))
    bus_features = []
    for rid, (sid, _) in longest.items():
        coords = round_coords(simplify(bus_shapes[sid], 0.00012))
        if len(coords) < 2:
            continue
        bus_features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"route": bus[rid].get("route_short_name") or bus[rid].get("route_long_name")},
        })

    def write(name, feats):
        for d in (OUT, FRONTEND):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                json.dump({"type": "FeatureCollection", "features": feats}, f)
        kb = os.path.getsize(os.path.join(OUT, name)) // 1024
        print(f"  {name}: {len(feats)} features, {kb} KB")

    os.makedirs(FRONTEND, exist_ok=True)
    print(f"rail routes {len(rail)}, bus routes {len(bus)}")
    write("cta_rail_lines.geojson", rail_features)
    write("cta_rail_stations.geojson", rail_stations)
    write("cta_bus_lines.geojson", bus_features)


if __name__ == "__main__":
    main()
