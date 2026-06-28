"""
Stage 15 — Real CTA transit access (OpenTripPlanner).

Transit analogue of stage 14: door-to-door public-transit travel time (walk +
CTA bus/rail + transfers) from each analysis tract to each selective-enrollment
high school, via a local OTP engine (see analysis/otp/otp_up.sh).

This is the access lens that matters for car-free families — the majority in many
CPS neighborhoods. Driving (stage 14) assumes a car; transit does not.

Method (kept honest):
  - Origins = tract internal points (same as stage 14 & 07_finding2.sql).
  - Destinations = the 11 selective-enrollment schools (the access question).
  - Transit time depends on departure time, so we sample several weekday-morning
    departures and take the MEDIAN of the best (min-duration) itinerary per
    departure. Service date is a normal Wednesday inside the GTFS service span.
  - Door-to-door: walk-only is allowed when it beats waiting for transit.

Outputs (static; no live engine in production):
  output/transit_times_selective.csv  — tract x selective median transit minutes
  output/transit_access.json          — per-tract transit access fields + method meta

Validation is reported across ALL demographic axes (income, poverty, and every
racial group) as a neutral correlation table — the pattern is left to emerge from
the data, not pre-selected. (Mirrors the project's "show all variables" rule.)

Prereq: OTP up & loaded  ->  bash analysis/otp/otp_up.sh  (wait ~30-60s)
Usage:  python analysis/15_transit_access.py
"""
import csv
import json
import os
import statistics
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "output")

OTP_URL = os.environ.get("OTP_URL", "http://localhost:8080/otp/routers/default/index/graphql")
SERVICE_DATE = os.environ.get("OTP_DATE", "2026-07-08")   # a normal Wed in the CTA GTFS span
DEPARTURES = ["07:00am", "07:30am", "08:00am"]            # morning window; median across these
WALK_RELUCTANCE = 2.0
NUM_ITINERARIES = 4
MAX_WORKERS = 8
ELITE_SAT = 1250          # matches 07_finding2.sql
NEAR_MIN = 30             # "reachable" transit threshold (also the UMN 30-min standard)

_local = threading.local()


def session():
    s = getattr(_local, "s", None)
    if s is None:
        s = _local.s = requests.Session()
    return s


def load_origins():
    with open(os.path.join(OUT, "tracts.geojson"), encoding="utf-8") as f:
        analysis_geoids = {ft["properties"]["geoid"] for ft in json.load(f)["features"]}
    with open(os.path.join(RAW, "tiger_tracts_2020.geojson"), encoding="utf-8") as f:
        tiger = json.load(f)["features"]
    origins = {p["GEOID"]: (float(p["INTPTLON"]), float(p["INTPTLAT"]))
               for p in (ft["properties"] for ft in tiger) if p["GEOID"] in analysis_geoids}
    missing = analysis_geoids - set(origins)
    if missing:
        raise RuntimeError(f"{len(missing)} analysis tracts lack a TIGER internal point")
    return origins


def load_selective():
    with open(os.path.join(OUT, "schools.geojson"), encoding="utf-8") as f:
        feats = json.load(f)["features"]
    sel = []
    for ft in feats:
        p = ft["properties"]
        if str(p.get("is_selective")).lower() != "true":
            continue
        lon, lat = ft["geometry"]["coordinates"]
        sel.append({"school_id": p["school_id"], "name": p["name"],
                    "sat_g11": float(p["sat_g11"]) if p.get("sat_g11") else None,
                    "lon": float(lon), "lat": float(lat)})
    return sel


PLAN_Q = """{ plan(
  from:{lat:%f, lon:%f} to:{lat:%f, lon:%f}
  date:"%s" time:"%s"
  transportModes:[{mode:WALK},{mode:TRANSIT}]
  numItineraries:%d walkReluctance:%f
){ itineraries { duration } } }"""


def best_duration_min(flat, flon, tlat, tlon, time):
    """Min-duration itinerary (minutes) for one departure, or None."""
    q = PLAN_Q % (flat, flon, tlat, tlon, SERVICE_DATE, time, NUM_ITINERARIES, WALK_RELUCTANCE)
    for attempt in range(3):
        try:
            r = session().post(OTP_URL, json={"query": q}, timeout=60)
            r.raise_for_status()
            d = r.json()
            if d.get("errors"):
                return None
            its = d["data"]["plan"]["itineraries"]
            if not its:
                return None
            return min(it["duration"] for it in its) / 60.0
        except requests.RequestException:
            if attempt == 2:
                return None
    return None


def median_transit_min(o, dst):
    """Median best-itinerary minutes across the morning departures."""
    vals = [v for t in DEPARTURES
            if (v := best_duration_min(o[1], o[0], dst["lat"], dst["lon"], t)) is not None]
    return round(statistics.median(vals), 1) if vals else None


def preflight():
    try:
        r = session().post(OTP_URL, json={"query": "{feeds{feedId}}"}, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        sys.exit(f"\nERROR: OTP not reachable at {OTP_URL} ({e}).\n"
                 f"Start it:  bash analysis/otp/otp_up.sh   (then wait ~30-60s for graph load)\n")
    # confirm the service date actually returns transit itineraries
    test = best_duration_min(41.857, -87.640, 41.873066, -87.627675, DEPARTURES[0])
    if test is None:
        sys.exit(f"\nERROR: no itinerary for the test pair on {SERVICE_DATE}. "
                 f"Pick another weekday in the GTFS span via OTP_DATE=YYYY-MM-DD.\n")
    print(f"preflight ok (test trip {test:.0f} min on {SERVICE_DATE})")


def build(origins, selective):
    geoids = sorted(origins)
    pairs = [(g, dst) for g in geoids for dst in selective]
    results = {g: {} for g in geoids}
    done = [0]
    lock = threading.Lock()

    def work(pair):
        g, dst = pair
        m = median_transit_min(origins[g], dst)
        with lock:
            results[g][dst["school_id"]] = m
            done[0] += 1
            if done[0] % 1000 == 0:
                print(f"  {done[0]}/{len(pairs)} pairs")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        list(ex.map(work, pairs))
    return results, geoids


def summarize(results, geoids, selective):
    by_id = {s["school_id"]: s for s in selective}
    summary = {}
    for g in geoids:
        reach = sorted(((m, by_id[sid]) for sid, m in results[g].items() if m is not None),
                       key=lambda x: x[0])
        nearest = reach[0] if reach else None
        elite = [(m, s) for m, s in reach if s["sat_g11"] and s["sat_g11"] >= ELITE_SAT]
        summary[g] = {
            "nearest_selective_transit_min": nearest[0] if nearest else None,
            "sat_of_nearest_selective_transit": nearest[1]["sat_g11"] if nearest else None,
            "transit_min_to_nearest_elite": elite[0][0] if elite else None,
            "n_selective_within_30min": sum(1 for m, _ in reach if m <= NEAR_MIN),
        }
    return summary


def write_outputs(results, geoids, selective, summary):
    by_id = {s["school_id"]: s for s in selective}
    csv_path = os.path.join(OUT, "transit_times_selective.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["geoid", "school_id", "school", "sat_g11", "transit_min_median"])
        for g in geoids:
            for sid, m in results[g].items():
                s = by_id[sid]
                w.writerow([g, sid, s["name"], s["sat_g11"], m])
    json_path = os.path.join(OUT, "transit_access.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"meta": {
            "method": "OTP door-to-door transit (walk + CTA bus/rail + transfers) from tract internal points to selective schools",
            "engine": "OpenTripPlanner 2.5.0", "feed": "CTA GTFS",
            "service_date": SERVICE_DATE, "departure_window": DEPARTURES,
            "statistic": "median of best itinerary across departures",
            "near_threshold_min": NEAR_MIN, "elite_sat": ELITE_SAT,
            "limits": "CTA only (excludes Metra/Pace — may understate access where those fill gaps); "
                      "regular weekday schedule.",
        }, "tracts": summary}, f, indent=2)
        f.write("\n")
    return csv_path, json_path


def validate(summary, geoids):
    """Neutral, multi-axis validation: correlate transit access with EVERY
    demographic axis (no single group singled out), and show the full demographic
    profile of each access quartile. Also compare transit vs driving."""
    with open(os.path.join(OUT, "tracts.geojson"), encoding="utf-8") as f:
        props = {ft["properties"]["geoid"]: ft["properties"] for ft in json.load(f)["features"]}
    drive = None
    dpath = os.path.join(OUT, "driving_access.json")
    if os.path.exists(dpath):
        drive = json.load(open(dpath, encoding="utf-8"))["tracts"]

    n_unreached = sum(1 for g in geoids if summary[g]["nearest_selective_transit_min"] is None)
    print("\n=== validation ===")
    print(f"tracts with no transit-reachable selective: {n_unreached}/{len(geoids)}")

    AXES = [("median_hh_income", "income"), ("poverty_rate", "poverty"),
            ("pct_white", "%white"), ("pct_black", "%black"), ("pct_hispanic", "%hispanic")]
    metric = "transit_min_to_nearest_elite"
    print(f"\nCorrelation of transit minutes to nearest elite selective with each axis")
    print("(neutral: all axes shown; + = more minutes as the axis rises):")
    for key, label in AXES:
        xs, ys = [], []
        for g in geoids:
            a, b = props[g].get(key), summary[g][metric]
            if a is not None and b is not None:
                xs.append(a); ys.append(b)
        if len(xs) > 2:
            r = float(np.corrcoef(xs, ys)[0, 1])
            print(f"   {label:10s} r = {r:+.3f}   (n={len(xs)})")

    # transit access quartiles -> full demographic profile of each (no group singled out)
    rows = [(summary[g][metric], props[g]) for g in geoids if summary[g][metric] is not None]
    vals = np.array([r[0] for r in rows])
    edges = np.quantile(vals, [0, .25, .5, .75, 1.0])
    print("\nTransit-access quartile (min to nearest elite) -> mean profile of those tracts:")
    print("  quartile           min   income   %white  %black  %hisp")
    for q in range(4):
        lo, hi = edges[q], edges[q + 1]
        grp = [p for v, p in rows if (v >= lo and (v <= hi if q == 3 else v < hi))]
        if not grp:
            continue
        mean = lambda k: np.nanmean([p.get(k) if p.get(k) is not None else np.nan for p in grp])
        tag = "best access" if q == 0 else "worst access" if q == 3 else ""
        print(f"  Q{q+1} {tag:12s} {np.mean([v for v,p in rows if (v>=lo and (v<=hi if q==3 else v<hi))]):5.0f}  "
              f"{mean('median_hh_income'):7.0f}  {mean('pct_white'):5.0f}%  {mean('pct_black'):5.0f}%  {mean('pct_hispanic'):5.0f}%")

    # the car-free penalty: transit vs driving to nearest elite
    if drive:
        ratios = []
        for g in geoids:
            t = summary[g]["transit_min_to_nearest_elite"]
            d = drive.get(g, {}).get("drive_min_to_nearest_elite")
            if t and d:
                ratios.append(t / d)
        if ratios:
            print(f"\ntransit/driving time ratio to nearest elite: median {np.median(ratios):.1f}x "
                  f"(transit takes ~{np.median(ratios):.1f}x as long as driving)")


def main():
    print("=== Stage 15 - CTA transit access (OTP) ===")
    origins = load_origins()
    selective = load_selective()
    print(f"origins (tracts): {len(origins)}   selective destinations: {len(selective)}   "
          f"date {SERVICE_DATE}   departures {DEPARTURES}")
    preflight()
    results, geoids = build(origins, selective)
    summary = summarize(results, geoids, selective)
    csv_path, json_path = write_outputs(results, geoids, selective, summary)
    print(f"\nwrote {os.path.relpath(csv_path, ROOT)}")
    print(f"wrote {os.path.relpath(json_path, ROOT)}")
    validate(summary, geoids)


if __name__ == "__main__":
    main()
