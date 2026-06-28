"""
Stage 14 — Real driving access (OSRM).

Replaces the straight-line distance proxy in Finding 2's access metrics with
REAL road-network driving times/distances from each analysis tract to each CPS
high school, via a local OSRM engine (see analysis/osrm/osrm_up.sh).

Origins are the tract internal points (intptlon/intptlat) — the SAME points
07_finding2.sql uses for the straight-line metrics — so the two are directly
comparable. Destinations are all 170 high schools.

Outputs (baked static; no live engine in production):
  output/driving_times_selective.csv  — tract x selective long matrix (the reusable core)
  output/driving_access.json          — per-tract driving analogues of the Finding-2 access fields

Honest framing: driving time is one access lens (assumes a car). The transit
lens (the burden for car-free families) is the next stage. This stage does not
yet rewire the SQL/finding — it produces the comparable matrix and validates it.

Prereq: OSRM up on localhost:5000  ->  bash analysis/osrm/osrm_up.sh
Usage:  python analysis/14_driving_access.py
"""
import csv
import json
import os
import sys
import numpy as np
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "output")

OSRM_URL = os.environ.get("OSRM_URL", "http://localhost:5000")
METERS_PER_MILE = 1609.34
ELITE_SAT = 1250          # matches 07_finding2.sql: elite = selective, SAT >= 1250
STRONG_SAT = 1010         # matches frontend STRONG_SCHOOL_SAT
BATCH = 80                # origins per /table call (keeps URL + table size small)


def load_origins():
    """tract geoid -> (lon, lat) internal point, restricted to the 791 analysis
    tracts (those present in output/tracts.geojson)."""
    with open(os.path.join(OUT, "tracts.geojson"), encoding="utf-8") as f:
        analysis_geoids = {ft["properties"]["geoid"] for ft in json.load(f)["features"]}
    with open(os.path.join(RAW, "tiger_tracts_2020.geojson"), encoding="utf-8") as f:
        tiger = json.load(f)["features"]
    origins = {}
    for ft in tiger:
        p = ft["properties"]
        gid = p["GEOID"]
        if gid in analysis_geoids:
            origins[gid] = (float(p["INTPTLON"]), float(p["INTPTLAT"]))
    missing = analysis_geoids - set(origins)
    if missing:
        raise RuntimeError(f"{len(missing)} analysis tracts have no TIGER internal point, e.g. {sorted(missing)[:3]}")
    return origins  # dict, insertion order irrelevant (we sort on use)


def load_destinations():
    with open(os.path.join(OUT, "schools.geojson"), encoding="utf-8") as f:
        feats = json.load(f)["features"]
    dests = []
    for ft in feats:
        p = ft["properties"]
        lon, lat = ft["geometry"]["coordinates"]
        sat = p.get("sat_g11")
        dests.append({
            "school_id": p["school_id"],
            "name": p["name"],
            "is_selective": str(p.get("is_selective")).lower() == "true",
            "sat_g11": float(sat) if sat else None,
            "lon": float(lon),
            "lat": float(lat),
        })
    return dests


def osrm_table(coords, n_src, n_dst):
    """Call OSRM /table for the first n_src coords (sources) x last n_dst coords
    (destinations). Returns (durations_min, distances_mi) as 2D lists; cells may
    be None when OSRM cannot route the pair."""
    pts = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coords)
    sources = ";".join(str(i) for i in range(n_src))
    dests = ";".join(str(i) for i in range(n_src, n_src + n_dst))
    url = f"{OSRM_URL}/table/v1/driving/{pts}"
    try:
        r = requests.get(url, params={"sources": sources, "destinations": dests,
                                      "annotations": "duration,distance"}, timeout=120)
        r.raise_for_status()
    except requests.RequestException as e:
        sys.exit(f"\nERROR: could not reach OSRM at {OSRM_URL} ({e}).\n"
                 f"Bring it up first:  bash analysis/osrm/osrm_up.sh\n")
    d = r.json()
    if d.get("code") != "Ok":
        sys.exit(f"OSRM returned code={d.get('code')}: {d.get('message')}")
    durs = [[(v / 60.0 if v is not None else None) for v in row] for row in d["durations"]]
    dists = [[(v / METERS_PER_MILE if v is not None else None) for v in row] for row in d["distances"]]
    return durs, dists


def build_matrix(origins, dests):
    """drive[geoid][school_id] = {"min": float|None, "mi": float|None}."""
    geoids = sorted(origins)
    dst_coords = [(d["lon"], d["lat"]) for d in dests]
    drive = {g: {} for g in geoids}
    for start in range(0, len(geoids), BATCH):
        chunk = geoids[start:start + BATCH]
        coords = [origins[g] for g in chunk] + dst_coords
        durs, dists = osrm_table(coords, len(chunk), len(dests))
        for i, g in enumerate(chunk):
            for j, dest in enumerate(dests):
                drive[g][dest["school_id"]] = {"min": durs[i][j], "mi": dists[i][j]}
        print(f"  routed tracts {start + len(chunk)}/{len(geoids)}")
    return drive, geoids


def summarize(drive, geoids, dests):
    """Per-tract driving analogues of the Finding-2 access fields."""
    by_id = {d["school_id"]: d for d in dests}
    selective = [d for d in dests if d["is_selective"]]
    summary = {}
    for g in geoids:
        sel_reach = [(drive[g][d["school_id"]], d) for d in selective
                     if drive[g][d["school_id"]]["min"] is not None]
        sel_reach.sort(key=lambda x: x[0]["min"])
        nearest_sel = sel_reach[0] if sel_reach else None
        elite = [(c, d) for c, d in sel_reach if d["sat_g11"] and d["sat_g11"] >= ELITE_SAT]
        strong = [drive[g][d["school_id"]]["min"] for d in dests
                  if d["sat_g11"] and d["sat_g11"] >= STRONG_SAT
                  and drive[g][d["school_id"]]["min"] is not None]
        summary[g] = {
            "nearest_selective_drive_min": round(nearest_sel[0]["min"], 1) if nearest_sel else None,
            "nearest_selective_drive_mi": round(nearest_sel[0]["mi"], 2) if nearest_sel else None,
            "sat_of_nearest_selective_drive": nearest_sel[1]["sat_g11"] if nearest_sel else None,
            "drive_min_to_nearest_elite": round(elite[0][0]["min"], 1) if elite else None,
            "n_selective_within_15min": sum(1 for c, _ in sel_reach if c["min"] <= 15),
            "n_selective_within_3mi": sum(1 for c, _ in sel_reach if c["mi"] is not None and c["mi"] <= 3),
            "nearest_strong_drive_min": round(min(strong), 1) if strong else None,
        }
    return summary


def write_outputs(drive, geoids, dests, summary):
    selective_ids = [d for d in dests if d["is_selective"]]
    csv_path = os.path.join(OUT, "driving_times_selective.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["geoid", "school_id", "school", "sat_g11", "drive_min", "drive_mi"])
        for g in geoids:
            for d in selective_ids:
                cell = drive[g][d["school_id"]]
                w.writerow([g, d["school_id"], d["name"], d["sat_g11"],
                            None if cell["min"] is None else round(cell["min"], 1),
                            None if cell["mi"] is None else round(cell["mi"], 2)])
    json_path = os.path.join(OUT, "driving_access.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "method": "OSRM road-network driving from tract internal points to all CPS high schools",
                "profile": "car (MLD)",
                "osm_source": "data/osrm/chicago.osm.pbf",
                "origins": len(geoids),
                "selective_destinations": len(selective_ids),
                "elite_sat": ELITE_SAT,
                "strong_sat": STRONG_SAT,
                "note": "Driving access (assumes a car). Transit access is a separate stage.",
            },
            "tracts": summary,
        }, f, indent=2)
        f.write("\n")
    return csv_path, json_path


def validate(summary, geoids):
    """Sanity-check against the existing straight-line Finding-2 metrics and
    re-run the headline (access by neighborhood race) in real drive minutes."""
    with open(os.path.join(OUT, "tracts.geojson"), encoding="utf-8") as f:
        props = {ft["properties"]["geoid"]: ft["properties"] for ft in json.load(f)["features"]}

    # coverage
    n_unrouted = sum(1 for g in geoids if summary[g]["nearest_selective_drive_min"] is None)
    print(f"\n=== validation ===")
    print(f"tracts with no routable selective: {n_unrouted}/{len(geoids)}"
          + ("  (consider the Geofabrik extract — see osrm_up.sh)" if n_unrouted else "  (full coverage)"))

    # straight-line miles vs driving minutes to nearest selective (should be strong, <1)
    sl, dm = [], []
    for g in geoids:
        a = props[g].get("nearest_selective_mi")
        b = summary[g]["nearest_selective_drive_min"]
        if a is not None and b is not None:
            sl.append(a); dm.append(b)
    if sl:
        r = float(np.corrcoef(sl, dm)[0, 1])
        print(f"corr(straight-line mi, drive min) to nearest selective: r={r:.3f}  (n={len(sl)})")

    # headline recomputation: drive-time to nearest elite by %Black quartile
    rows = [(props[g].get("pct_black"), summary[g]["drive_min_to_nearest_elite"],
             props[g].get("miles_to_nearest_elite")) for g in geoids]
    rows = [(b, dmin, smi) for b, dmin, smi in rows if b is not None and dmin is not None]
    if rows:
        blacks = np.array([r[0] for r in rows])
        edges = np.quantile(blacks, [0, .25, .5, .75, 1.0])
        print("\n%Black quartile  ->  mean DRIVE min to elite (straight-line mi for contrast):")
        for q in range(4):
            lo, hi = edges[q], edges[q + 1]
            sel = [(dmin, smi) for b, dmin, smi in rows
                   if (b >= lo and (b <= hi if q == 3 else b < hi))]
            if sel:
                md = np.mean([x[0] for x in sel])
                ms = np.mean([x[1] for x in sel if x[1] is not None])
                print(f"  Q{q+1} (%Black {lo:4.0f}-{hi:3.0f}%): {md:5.1f} min   ({ms:.1f} mi)")


def main():
    print("=== Stage 14 - driving access (OSRM) ===")
    origins = load_origins()
    dests = load_destinations()
    print(f"origins (tracts): {len(origins)}   destinations (schools): {len(dests)}   "
          f"selective: {sum(d['is_selective'] for d in dests)}")
    drive, geoids = build_matrix(origins, dests)
    summary = summarize(drive, geoids, dests)
    csv_path, json_path = write_outputs(drive, geoids, dests, summary)
    print(f"\nwrote {os.path.relpath(csv_path, ROOT)}")
    print(f"wrote {os.path.relpath(json_path, ROOT)}")
    validate(summary, geoids)


if __name__ == "__main__":
    main()
