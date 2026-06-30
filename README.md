# Chicago School Gap

An interactive map that shows how a Chicago student's public high school options depend on where
they live: the high school they're assigned by home address, how it compares to others across the
city, and how far the strongest schools are — by car and by public transit.

**Live demo:** _to be added after deploy_ · **Numbers, methods, and limits:** [`analysis/FINDINGS.md`](./analysis/FINDINGS.md)

It's built entirely on public data and is **descriptive** — it measures assignment, school
outcomes, access, and student-body composition. It does not make causal claims and does not
estimate anyone's odds of admission (origin-level admissions data isn't public).

---

## Why I built it

I'm a recent computer science graduate, and I built this to take a real, messy public-data
problem from end to end: sourcing and joining several datasets geospatially, writing a
reproducible analysis pipeline, computing real travel times, and turning all of it into something
interactive that a non-technical person can read. Chicago high school access is a concrete topic
with good open data, real stakes, and enough complexity (spatial joins, multiple data sources,
routing) to be worth doing carefully.

---

## Background

A bit of context, since the system is specific to Chicago:

- **Every Chicago address is zoned to one default "neighborhood" high school** by an attendance
  boundary. That's the school a student gets automatically.
- **The main alternative is a selective-enrollment high school** — test-in schools that admit
  students citywide rather than by address, and that generally post much higher outcomes. There
  are 11 of them among ~170 CPS high schools.
- **CPS uses a "tier" system to balance selective access.** Each address's census tract is scored
  on socioeconomic factors into four tiers, and 70% of selective seats are split evenly across the
  tiers (the rest by citywide rank) — an explicit attempt to keep access from concentrating in
  wealthier areas ([CPS selection process](https://www.cps.edu/gocps/high-school/results/selective-enrollment/)).
- Independent research has found selective schools still skew wealthier and whiter than the
  district ([UChicago Consortium](https://consortium.uchicago.edu/news-item/can-selective-enrollment-in-Chicago-Public-Schools-be-fairer)),
  and CPS's own [Annual Regional Analysis](https://www.cps.edu/about/district-data/metrics/annual-regional-analysis-information/)
  (with Kids First Chicago) documents that program supply is geographically uneven.

This project measures and maps those patterns from scratch with open data, and adds a piece the
existing reports don't: **real car and CTA travel times** to selective schools, neighborhood by
neighborhood.

---

## What the map shows

- **A choropleth of Chicago's 77 community areas**, grouped by school access and quality
  (toggleable on/off).
- **All 170 CPS high schools as pins**, with selective-enrollment schools styled distinctly.
- **Click any neighborhood** for a panel with its assigned school, the schools located there
  (vs. the citywide median), demographics as context, and travel time to the nearest selective
  school by car and by CTA — and the map draws the actual driving and transit routes, labeled
  with their times.
- **CTA context layers** — the 'L' rail lines (in their official colors) with stations, and the
  bus network — to show how the transit network itself shapes access.

Best viewed on a desktop browser.

---

## What the data shows

One school year, cross-sectional (CPS SY2024–25 + ACS 2020–24 5-year), across 791 assigned
census tracts. Full detail in [`analysis/FINDINGS.md`](./analysis/FINDINGS.md). Descriptive only.

**1 — A neighborhood's assigned-school quality tracks its racial makeup more than its income.**
Tract median income correlates with assigned-school SAT (r = 0.38), but that correlation
collapses to about −0.07 after controlling for poverty and racial composition. The strongest
single predictor is share Black (r = −0.52); share Hispanic is near zero. Income and race are
heavily collinear in Chicago, so the relationship reads as segregation rather than income alone.

**2 — Selective enrollment doesn't close the gap.** Enrollment-weighted against the district,
selective schools under-represent low-income (ratio 0.66), Black (0.79), and Hispanic (0.67)
students, and over-represent white students (2.36×).

**3 — The access gap is moderate by car but large by transit.** To the nearest top-tier selective
(SAT ≥ 1250), the best- vs. worst-access quartile gap is ~1.6× by car but ~3.1× by CTA, and a
transit trip runs about 3.3–3.7× longer than driving (median transit time to a top selective is
35 minutes, ranging 4–107). By transit the disadvantage isn't one group's: longer trips track
share Black (+0.24) and share Hispanic (+0.27) at similar size, the strongest single thread is
white / higher-income *advantage* (share white −0.41, income −0.36), and the very longest trips
are in geographically isolated edge neighborhoods (e.g., Mount Greenwood, Riverdale, Hegewisch).

---

## Data sources

All public and keyless. CPS data is from the Chicago open-data portal (Socrata); ACS estimates
come from the keyless Census Reporter API (the official Census API now requires a key); tract
geometry is from Census TIGER; transit and street data are open feeds.

| Data | Source | Provides |
|---|---|---|
| CPS School Progress Reports SY2425 | Socrata `twrw-chuq` | SAT, graduation, attendance, truancy, type, lat/long |
| CPS School Profile SY2425 | Socrata `3dhs-m3w4` | enrollment + race / low-income composition |
| HS attendance boundaries SY2425 | Socrata `4kfz-zr3a` | neighborhood-school assignment polygons |
| Community areas | Socrata `igwz-8jzy` | the 77 community-area polygons |
| Census tracts (2020) | Census TIGERweb | tract geometry + internal points |
| ACS 2020–24 5-year | Census Reporter (`B19013`, `B03002`, `B17001`) | median income, race, poverty by tract |
| CTA schedules | CTA GTFS feed | bus/rail routes, stops, timetables (transit routing) |
| Street network | OpenStreetMap (BBBike Chicago extract) | road + pedestrian network (driving + walk routing) |

A field-by-field inventory — what's used, what's available but unused, and known data traps — is
in [`analysis/DATA_INVENTORY.md`](./analysis/DATA_INVENTORY.md).

---

## How it's built

**Analysis — PostgreSQL + PostGIS, Python.** The analysis runs in a PostGIS container. Spatial SQL
(`ST_Within`, `ST_Distance`, `ST_DWithin`, spatial joins) assigns each tract to its neighborhood
high school via its Census internal point and the attendance-boundary polygons, joins tracts to
ACS income / race / poverty and to community areas, and computes selective-enrollment access and
enrollment-weighted student-body representation. Python (`pandas`, `numpy`) handles the
multi-source download, the income-vs-race confound check (partial correlation), and a
dependency-free k-means + PCA that groups community areas on school measures only (not race or
income).

**Travel time — OSRM and OpenTripPlanner.** Straight-line distance overstates access, so real
travel time from each tract to the selective schools is computed two ways, both run locally in
Docker: **OSRM** on the OpenStreetMap extract for road-network driving, and **OpenTripPlanner**
on the CTA GTFS feed for door-to-door transit (walk + bus/rail + transfers, median across a
weekday 7–8 AM departure window). The route paths drawn on click are precomputed from the same
engines.

**Frontend — React + TypeScript + MapLibre GL JS.** A Vite single-page app renders static GeoJSON
on a CARTO basemap via `react-map-gl` / MapLibre. Clicked-point reverse geocoding uses the keyless
OSM Nominatim API.

**Architecture.** The database and routing engines are **build-time tools only**. Their results
are exported to static GeoJSON/CSV, and the frontend serves those files directly — no backend at
runtime, so the app deploys as a static site.

```
build-time (local)                              runtime (static host)
  PostGIS ─┐
  OSRM    ─┼─ Python/SQL pipeline ─► output/*.geojson, *.csv ─► React app serves static files
  OTP     ─┘                          frontend/public/data/
```

---

## Reproducing it

Requirements: Docker, a Python env with `requirements.txt` installed, and Node (for `mapshaper`,
run via `npx`).

```bash
# 1. start PostGIS
docker run -d --name chicago-postgis -e POSTGRES_PASSWORD=chicago \
  -e POSTGRES_DB=school_gap -p 5433:5432 postgis/postgis:16-3.4

# 2. (optional, for travel time) bring up the routing engines, then build the matrices
bash analysis/osrm/osrm_up.sh        # driving  — downloads OSM extract, builds graph, serves :5000
bash analysis/otp/otp_up.sh          # transit  — downloads CTA GTFS, builds graph, serves :8080
python analysis/14_driving_access.py # driving travel-time matrix
python analysis/15_transit_access.py # CTA transit travel-time matrix
python analysis/18_routes.py         # route geometry for click-to-route

# 3. rebuild the whole pipeline end to end
PY=/path/to/python ./analysis/run_all.sh

# 4. run the map
cd frontend && npm install && npm run dev
```

`run_all.sh` rebuilds every table and export from a clean database. The routing-engine outputs are
committed, so the rebuild reproduces the map without the engines running; the matrices regenerate
when the engines are up. The ACS release is pinned so reruns can't silently drift to a new vintage.

---

## Repository layout

```
analysis/        download + PostGIS pipeline (numbered stages 01–18), SQL, and method docs
  osrm/ otp/     Docker bring-up scripts for the routing engines
  FINDINGS.md    numbers, methods, and honest limits
  DATA_INVENTORY.md   field-by-field coverage audit
output/          exported GeoJSON/CSV (the analysis's source of truth)
frontend/        React + TypeScript + MapLibre app (serves static data from public/data)
```

Large or regenerable inputs (raw downloads, OSM/GTFS feeds, routing graphs, the generated
`load.sql`, `node_modules`) are gitignored; the computed outputs the app needs are committed.

---

## Limits

- **Descriptive, one year, cross-sectional.** No trends over time, no causal claims, no
  admission-odds estimates.
- **Transit is CTA-only** (no Metra or Pace), so transit access is understated where those run;
  driving times are free-flow (no live traffic).
- **Routes start at a neighborhood's center point**, not the exact click — matching how the
  travel-time numbers are computed.
- **Selective tiers, where referenced, are approximated** from ACS income, not the official CPS
  tier (which isn't published as a current bulk file); it's labeled as a proxy.

---

## Author

[Alan Zavala](https://github.com/alanzavala1)
