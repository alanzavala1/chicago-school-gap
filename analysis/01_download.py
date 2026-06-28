"""
Phase 1 data download for Chicago School Gap.

Pulls the four datasets needed to test Finding 1 (income -> assigned-school quality):
  1. HS Progress Reports SY2425 (twrw-chuq)        -> school outcomes + type + lat/long
  2. HS Attendance Boundaries SY2425 (4kfz-zr3a)   -> neighborhood-school assignment polygons
  3. Census Tract Boundaries (4hp8-2i8z)           -> tract polygons
  4. ACS 5-yr median household income B19013_001E  -> tract-level income (Cook County, 17/031)

Writes raw files into data/raw/. Idempotent: skips files already downloaded unless --force.
"""
import json
import os
import sys
import time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "..", "data", "raw")
os.makedirs(RAW, exist_ok=True)

SOCRATA = "https://data.cityofchicago.org/resource/{id}.{fmt}"
FORCE = "--force" in sys.argv

# Pin the ACS release so reruns can NEVER silently drift to a newer vintage.
# (Census Reporter's /show/latest alias would do exactly that.) Change deliberately.
ACS_RELEASE = "acs2024_5yr"          # Census Reporter release slug
ACS_RELEASE_NAME = "ACS 2024 5-year"  # human name we assert against
CR_BASE = f"https://api.censusreporter.org/1.0/data/show/{ACS_RELEASE}"


def assert_release(raw):
    got = (raw.get("release", {}) or {}).get("name")
    if got != ACS_RELEASE_NAME:
        raise RuntimeError(
            f"ACS release mismatch: expected '{ACS_RELEASE_NAME}', got '{got}'. "
            f"Update ACS_RELEASE/ACS_RELEASE_NAME deliberately if this is intended.")


def out(name):
    return os.path.normpath(os.path.join(RAW, name))


def have(name):
    p = out(name)
    return os.path.exists(p) and os.path.getsize(p) > 0


def get(url, params=None, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=120)
            r.raise_for_status()
            return r
        except Exception as e:
            print(f"   retry {i+1}/{tries}: {e}")
            time.sleep(3)
    raise RuntimeError(f"failed: {url}")


def download_socrata_json(dsid, name, limit=5000):
    if have(name) and not FORCE:
        print(f"[skip] {name} already present")
        return out(name)
    print(f"[get ] {name} <- {dsid} (json, limit={limit})")
    r = get(SOCRATA.format(id=dsid, fmt="json"), params={"$limit": limit})
    data = r.json()
    with open(out(name), "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"       {len(data)} rows -> {name}")
    return out(name)


def download_socrata_geojson(dsid, name, limit=5000):
    if have(name) and not FORCE:
        print(f"[skip] {name} already present")
        return out(name)
    print(f"[get ] {name} <- {dsid} (geojson, limit={limit})")
    r = get(SOCRATA.format(id=dsid, fmt="geojson"), params={"$limit": limit})
    data = r.json()
    n = len(data.get("features", []))
    with open(out(name), "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"       {n} features -> {name}")
    return out(name)


def download_tiger_tracts(name):
    """2020-vintage census tract polygons for Cook County (FIPS 17031) from Census
    TIGERweb (keyless ArcGIS REST, layer 0 of TIGERweb/Tracts_Blocks).

    Vintage decision: the Chicago portal tract layer (4hp8-2i8z) is 2010-vintage;
    only ~63% of its GEOIDs match ACS 2024 5-year (2020-vintage) tracts, which
    would silently drop ~37% of tracts in the income join. Pulling tract geometry
    straight from Census TIGER 2020 makes geometry and income share one vintage =>
    100% GEOID alignment with the ACS pull (verified: 1332/1332 Cook tracts match).
    """
    if have(name) and not FORCE:
        print(f"[skip] {name} already present")
        return out(name)
    print("[get ] TIGER 2020 census tracts, Cook County (paginated GeoJSON)")
    base = ("https://tigerweb.geo.census.gov/arcgis/rest/services/"
            "TIGERweb/Tracts_Blocks/MapServer/0/query")
    feats, off = [], 0
    while True:
        r = get(base, params={
            "where": "STATE='17' AND COUNTY='031'",
            "outFields": "GEOID,BASENAME,INTPTLAT,INTPTLON",
            "outSR": 4326, "returnGeometry": "true",
            "f": "geojson", "resultOffset": off, "resultRecordCount": 1000,
        })
        d = r.json()
        batch = d.get("features", [])
        if not batch:
            break
        feats.extend(batch)
        if not d.get("exceededTransferLimit") and len(batch) < 1000:
            break
        off += len(batch)
    fc = {"type": "FeatureCollection", "features": feats}
    with open(out(name), "w", encoding="utf-8") as f:
        json.dump(fc, f)
    print(f"       {len(feats)} tract polygons -> {name}")
    return out(name)


def download_acs(name):
    """ACS 5-yr median household income B19013_001E for all Cook County tracts.

    Source decision: the official Census API (api.census.gov) now hard-requires a
    free key (keyless requests redirect to missing_key.html). To keep the pipeline
    reproducible with zero secrets, we pull the identical ACS table from the
    keyless Census Reporter API (api.censusreporter.org), a well-known civic-tech
    ACS frontend. Same underlying Census ACS 5-year estimates; latest release.

    geo_ids="140|05000US17031" => summary level 140 (census tract) within Cook
    County (FIPS 17031). Census Reporter geoids look like 14000US17031010100;
    the standard 11-digit tract GEOID is the trailing substring (17031010100).
    """
    if have(name) and not FORCE:
        print(f"[skip] {name} already present")
        return out(name)
    print(f"[get ] ACS B19013 median HH income (Census Reporter, {ACS_RELEASE})")
    r = get(CR_BASE, params={"table_ids": "B19013", "geo_ids": "140|05000US17031"})
    raw = r.json()
    assert_release(raw)
    rows = []
    for cr_geoid, payload in raw.get("data", {}).items():
        est = payload.get("B19013", {}).get("estimate", {}).get("B19013001")
        moe = payload.get("B19013", {}).get("error", {}).get("B19013001")
        geoid11 = cr_geoid.split("US")[-1]  # 14000US17031010100 -> 17031010100
        rows.append({
            "geoid": geoid11,
            "cr_geoid": cr_geoid,
            "name": raw.get("geography", {}).get(cr_geoid, {}).get("name"),
            "median_hh_income": est,
            "moe": moe,
        })
    payload = {"release": raw.get("release", {}).get("name"), "rows": rows}
    with open(out(name), "w", encoding="utf-8") as f:
        json.dump(payload, f)
    print(f"       {len(rows)} tract rows ({payload['release']}) -> {name}")
    return out(name)


def download_acs_demographics(name):
    """Tract race (B03002) + poverty (B17001) for Cook County, keyless Census Reporter.
    Used for the Finding-1 honesty check: does neighborhood income predict assigned-school
    quality beyond neighborhood racial/poverty composition (they are collinear in Chicago)?
    """
    if have(name) and not FORCE:
        print(f"[skip] {name} already present")
        return out(name)
    print(f"[get ] ACS race + poverty by tract (Census Reporter, {ACS_RELEASE})")
    r = get(CR_BASE, params={"table_ids": "B03002,B17001", "geo_ids": "140|05000US17031"})
    raw = r.json()
    assert_release(raw)
    rows = []
    for cr_geoid, p in raw.get("data", {}).items():
        race = p.get("B03002", {}).get("estimate", {})
        pov = p.get("B17001", {}).get("estimate", {})
        tot = race.get("B03002001") or 0
        pov_univ = pov.get("B17001001") or 0
        rows.append({
            "geoid": cr_geoid.split("US")[-1],
            "pop_total": tot,
            "pct_white_nh": (race.get("B03002003", 0) / tot) if tot else None,
            "pct_black": (race.get("B03002004", 0) / tot) if tot else None,
            "pct_hispanic": (race.get("B03002012", 0) / tot) if tot else None,
            "poverty_rate": (pov.get("B17001002", 0) / pov_univ) if pov_univ else None,
        })
    with open(out(name), "w", encoding="utf-8") as f:
        json.dump({"release": raw.get("release", {}).get("name"), "rows": rows}, f)
    print(f"       {len(rows)} tract rows -> {name}")
    return out(name)


if __name__ == "__main__":
    print("=== Chicago School Gap — Phase 1 download ===")
    download_socrata_json("twrw-chuq", "progress_sy2425.json", limit=5000)
    download_socrata_geojson("4kfz-zr3a", "hs_attendance_boundaries.geojson", limit=5000)
    download_tiger_tracts("tiger_tracts_2020.geojson")
    download_acs("acs_b19013_cook.json")
    download_acs_demographics("acs_demographics_cook.json")
    download_socrata_json("3dhs-m3w4", "school_demographics_sy2425.json", limit=1000)
    download_socrata_geojson("igwz-8jzy", "community_areas.geojson", limit=200)
    print("=== done ===")
