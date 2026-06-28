"""
Stage 18 — Real route geometry per neighborhood (for the click-to-route map).

For each analysis tract we save the actual route *paths* (not just times) so the
static map can draw a real street/transit route on click instead of a straight
line. Routes originate at the tract internal point (same origin as the travel-time
matrices), so they are "the route from this neighborhood."

Per tract, three routes:
  - assigned  : driving route to the assigned (default) neighborhood school   [OSRM]
  - selective : driving route to the nearest selective school                 [OSRM]
  - transit   : CTA route to that same nearest selective (walk+bus/rail)       [OTP]

Output (copied to the frontend), one FeatureCollection of LineStrings keyed by
geoid + role, each with the trip minutes:
  output/routes.geojson

Prereq: OSRM (:5000) and OTP (:8080) both up — see analysis/osrm + analysis/otp.
Usage:  python analysis/18_routes.py
"""
import csv
import json
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "output")
FRONTEND = os.path.join(ROOT, "frontend", "public", "data")

OSRM = os.environ.get("OSRM_URL", "http://localhost:5000")
OTP = os.environ.get("OTP_URL", "http://localhost:8080/otp/routers/default/index/graphql")
SERVICE_DATE = os.environ.get("OTP_DATE", "2026-07-08")
DEPART = "07:30am"          # one representative morning departure for the drawn path
MAX_WORKERS = 8

_local = threading.local()


def session():
    s = getattr(_local, "s", None)
    if s is None:
        s = _local.s = requests.Session()
    return s


def haversine(a, b):
    R = 3958.8
    dlat = math.radians(b[1] - a[1]); dlng = math.radians(b[0] - a[0])
    s = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[1])) * math.cos(math.radians(b[1])) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(s))


def _perp(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(points, eps=0.00007):
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
            stack.append((s, idx)); stack.append((idx, e))
    return [points[i] for i in range(n) if keep[i]]


def round_coords(coords):
    return [[round(lon, 5), round(lat, 5)] for lon, lat in coords]


def osrm_route(o, d):
    """Driving route geometry (coords) + minutes, or (None, None)."""
    url = f"{OSRM}/route/v1/driving/{o[0]:.6f},{o[1]:.6f};{d[0]:.6f},{d[1]:.6f}"
    try:
        r = session().get(url, params={"overview": "full", "geometries": "geojson"}, timeout=30)
        r.raise_for_status()
        j = r.json()
        if j.get("code") != "Ok" or not j.get("routes"):
            return None, None
        rt = j["routes"][0]
        return rt["geometry"]["coordinates"], rt["duration"] / 60.0
    except requests.RequestException:
        return None, None


def decode_polyline(s):
    """Decode a Google-encoded polyline (precision 5) -> [[lon,lat], ...]."""
    coords, lat, lng, i = [], 0, 0, 0
    while i < len(s):
        for is_lat in (True, False):
            shift, result = 0, 0
            while True:
                b = ord(s[i]) - 63; i += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            d = ~(result >> 1) if result & 1 else (result >> 1)
            if is_lat:
                lat += d
            else:
                lng += d
        coords.append([lng / 1e5, lat / 1e5])
    return coords


def otp_route(o, d):
    """Best transit itinerary geometry (concatenated legs) + minutes, or (None, None)."""
    q = ('{ plan(from:{lat:%f,lon:%f} to:{lat:%f,lon:%f} date:"%s" time:"%s" '
         'transportModes:[{mode:WALK},{mode:TRANSIT}] numItineraries:3 walkReluctance:2.0) '
         '{ itineraries { duration legs { legGeometry { points } } } } }') % (o[1], o[0], d[1], d[0], SERVICE_DATE, DEPART)
    try:
        r = session().post(OTP, json={"query": q}, timeout=60)
        r.raise_for_status()
        j = r.json()
        its = (j.get("data", {}).get("plan", {}) or {}).get("itineraries", [])
        if not its:
            return None, None
        best = min(its, key=lambda it: it["duration"])
        path = []
        for leg in best["legs"]:
            pts = leg.get("legGeometry", {}).get("points")
            if pts:
                seg = decode_polyline(pts)
                if path and seg and path[-1] == seg[0]:
                    seg = seg[1:]
                path.extend(seg)
        return (path or None), best["duration"] / 60.0
    except requests.RequestException:
        return None, None


def load_inputs():
    geoids = {}
    with open(os.path.join(OUT, "tracts.geojson"), encoding="utf-8") as f:
        for ft in json.load(f)["features"]:
            p = ft["properties"]
            geoids[p["geoid"]] = p.get("assigned_school")
    with open(os.path.join(RAW, "tiger_tracts_2020.geojson"), encoding="utf-8") as f:
        origins = {p["GEOID"]: (float(p["INTPTLON"]), float(p["INTPTLAT"]))
                   for p in (ft["properties"] for ft in json.load(f)["features"]) if p["GEOID"] in geoids}
    with open(os.path.join(OUT, "schools.geojson"), encoding="utf-8") as f:
        feats = json.load(f)["features"]
    by_name = {ft["properties"]["name"]: tuple(ft["geometry"]["coordinates"]) for ft in feats}
    selective = [{"name": ft["properties"]["name"], "c": tuple(ft["geometry"]["coordinates"])}
                 for ft in feats if str(ft["properties"].get("is_selective")).lower() == "true"]
    return geoids, origins, by_name, selective


def load_closest():
    """Per tract: the geographically CLOSEST selective by road distance (name + drive
    minutes), and a lookup of CTA median minutes to any (tract, school). Read from the
    same matrices the panel/findings use, so the drawn line == the panel number."""
    def rows(name):
        with open(os.path.join(OUT, name), encoding="utf-8") as f:
            return list(csv.DictReader(f))
    closest = {}  # geoid -> (school, drive_min, drive_mi)
    for r in rows("driving_times_selective.csv"):
        if not r["drive_mi"]:
            continue
        mi = float(r["drive_mi"]); g = r["geoid"]
        if g not in closest or mi < closest[g][2]:
            closest[g] = (r["school"], float(r["drive_min"]) if r["drive_min"] else None, mi)
    transit = {(r["geoid"], r["school"]): (float(r["transit_min_median"]) if r["transit_min_median"] else None)
               for r in rows("transit_times_selective.csv")}
    return closest, transit


def main():
    geoids, origins, by_name, selective = load_inputs()
    closest_by_road, transit_lookup = load_closest()
    print(f"tracts {len(origins)}  selective {len(selective)}  (date {SERVICE_DATE}, depart {DEPART})")

    features = []
    lock = threading.Lock()
    done = [0]

    def feat(geoid, role, school, coords, minutes):
        coords = round_coords(simplify(coords))
        if len(coords) < 2:
            return
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"geoid": geoid, "role": role, "school": school,
                           "minutes": round(minutes, 1) if minutes is not None else None},
        })

    def work(geoid):
        o = origins[geoid]
        # driving to assigned school (label = OSRM time; no matrix for the default school)
        aname = geoids.get(geoid)
        ac = by_name.get(aname) if aname else None
        if ac:
            g, mins = osrm_route(o, ac)
            if g:
                with lock: feat(geoid, "assigned", aname, g, mins)
        # the closest selective (same school the panel reports); label with the matrix
        # times so the map pill exactly equals the panel number.
        cl = closest_by_road.get(geoid)
        cc = by_name.get(cl[0]) if cl else None
        if cl and cc:
            cname, cdrive = cl[0], cl[1]
            g, _ = osrm_route(o, cc)
            if g:
                with lock: feat(geoid, "selective", cname, g, cdrive)
            g, _ = otp_route(o, cc)
            if g:
                with lock: feat(geoid, "transit", cname, g, transit_lookup.get((geoid, cname)))
        with lock:
            done[0] += 1
            if done[0] % 150 == 0:
                print(f"  {done[0]}/{len(origins)} tracts")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        list(ex.map(work, sorted(origins)))

    fc = {"type": "FeatureCollection", "features": features}
    os.makedirs(FRONTEND, exist_ok=True)
    for d in (OUT, FRONTEND):
        with open(os.path.join(d, "routes.geojson"), "w", encoding="utf-8") as f:
            json.dump(fc, f)
    kb = os.path.getsize(os.path.join(OUT, "routes.geojson")) // 1024
    by_role = {}
    for ft in features:
        by_role[ft["properties"]["role"]] = by_role.get(ft["properties"]["role"], 0) + 1
    print(f"wrote output/routes.geojson — {len(features)} routes {by_role}, {kb} KB")


if __name__ == "__main__":
    main()
