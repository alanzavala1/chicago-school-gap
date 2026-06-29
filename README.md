# Chicago School Gap

An interactive map of Chicago that examines how a student's public high school options depend
on where in the city they live. For any neighborhood it shows the high school assigned by
address, how that school compares to others citywide, and how far the nearest selective-enrollment
schools are — by car and by CTA transit.

The question the project is built around:

> How much does the neighborhood a student lives in shape the public high school they are
> assigned, and does selective enrollment widen or narrow that gap?

Everything in the project is **descriptive**: it measures assignment, school outcomes, access,
and student-body composition. It does not make causal claims and does not estimate admission
odds (origin-level admissions data is not public).

I built this as a portfolio project to practice the geospatial, data-engineering, and
data-communication skills used in civic / data-for-impact work. It is one current school year,
cross-sectional (CPS SY2024–25 with ACS 2020–24 5-year estimates).

---

## What the map shows

- **Community-area choropleth** — Chicago's 77 community areas grouped by school access and
  quality (toggleable on/off).
- **School pins** — all 170 CPS high schools; selective-enrollment schools styled distinctly.
- **Click a neighborhood** — a panel with its assigned (default) school, the schools located
  there, demographics as context, and travel time to the nearest selective school by car and by
  CTA; the map draws the real driving and transit routes, labeled with their times.
- **CTA context layers** — the 'L' rail lines (official colors) + stations and the bus network,
  each toggleable, to show how the transit network itself shapes access.

---

## Data sources

All public and keyless. CPS datasets are from the Chicago open-data portal (Socrata); ACS
estimates are pulled from the keyless Census Reporter API (the official Census API now requires
a key); tract geometry is from Census TIGER; transit and street data are open feeds.

| Data | Source | Provides |
|---|---|---|
| CPS School Progress Reports SY2425 | Socrata `twrw-chuq` | SAT, graduation, attendance, truancy, type, lat/long |
| CPS School Profile SY2425 | Socrata `3dhs-m3w4` | enrollment + race / low-income composition |
| HS attendance boundaries SY2425 | Socrata `4kfz-zr3a` | neighborhood-school assignment polygons |
| Community areas | Socrata `igwz-8jzy` | the 77 community-area polygons |
| Census tracts (2020) | Census TIGERweb | tract geometry + internal points |
| ACS 2020–24 5-year | Census Reporter (`B19013`, `B03002`, `B17001`) | median income, race, poverty by tract |
| CTA schedules | CTA GTFS feed | bus/rail routes, stops, and timetables (transit routing) |
| Street network | OpenStreetMap (BBBike Chicago extract) | road + pedestrian network (driving + walk routing) |

A full field-by-field inventory (what is used, what is available but unused, and known data
traps) is in [`analysis/DATA_INVENTORY.md`](./analysis/DATA_INVENTORY.md).

---

## How it was built

### Analysis layer — PostgreSQL + PostGIS, Python
The analysis runs in a PostGIS container. I used spatial SQL (`ST_Within`, `ST_Distance`,
`ST_DWithin`, spatial joins) to:
- assign each tract to its neighborhood high school via its Census internal point and the
  attendance-boundary polygons;
- join tracts to ACS income / race / poverty and to community areas;
- compute selective-enrollment access and enrollment-weighted student-body representation.

Python (`pandas`, `numpy`) handles the multi-source download, the income-vs-race confound check
(partial correlation), and a `scikit-learn`-free k-means + PCA used to group community areas.

### Travel time — OSRM (driving) and OpenTripPlanner (transit)
Straight-line distance overstates access, so I computed real travel time from each tract to the
selective schools two ways, both run locally in Docker as build-time tools:
- **OSRM** on the OpenStreetMap extract for road-network driving times/distances.
- **OpenTripPlanner 2.5.0** on the CTA GTFS feed for door-to-door transit (walk + bus/rail +
  transfers), taking the median across a weekday 7–8 AM departure window.

Route *geometry* for the click-to-route feature is precomputed from the same engines, so the
map draws true paths without needing a live server.

### Frontend — React + TypeScript + MapLibre GL JS
A Vite single-page app renders static GeoJSON on a CARTO basemap with `react-map-gl` /
MapLibre. Address reverse-geocoding (for the clicked point) uses the keyless OSM Nominatim API.

### Architecture
The database and routing engines are **build-time tools only**. Their results are exported to
static GeoJSON/CSV, and the frontend serves those files directly — there is no backend at
runtime, so the app deploys as a static site (e.g., Vercel with root `frontend/`).

```
build-time (local)                              runtime (static host)
  PostGIS ─┐
  OSRM    ─┼─ Python/SQL pipeline ─► output/*.geojson, *.csv ─► React app serves static files
  OTP     ─┘                          frontend/public/data/
```

---

## Findings (descriptive)

Full numbers, methods, and caveats are in [`analysis/FINDINGS.md`](./analysis/FINDINGS.md).

**1 — A neighborhood's assigned school tracks its racial composition more than its income.**
Tract income correlates with assigned-school SAT (r = 0.38), but that correlation collapses to
about −0.07 after controlling for poverty and racial composition; the strongest single
predictor is share Black (r = −0.52), while share Hispanic is near zero. Income and race are
heavily collinear in Chicago, so the relationship reads as segregation rather than income alone.

**2 — Selective enrollment does not close the gap.** Enrollment-weighted, selective schools
under-represent low-income (ratio 0.66), Black (0.79), and Hispanic (0.67) students and
over-represent white students (2.36×). Access to a *good* selective is geographically uneven.

**Access by car vs CTA transit.** To the nearest top-tier selective (SAT ≥ 1250), the gap
between best- and worst-access quartiles is moderate by car (~1.6×) but much larger by transit
(~3.1×); transit trips run about 3.3–3.7× longer than driving. By transit the disadvantage is
**not concentrated in one group** — share Black (+0.24) and share Hispanic (+0.27) track longer
trips at similar magnitude, the strongest single thread is white / higher-income *advantage*
(share white −0.41, income −0.36), and the longest trips are in geographically isolated edge
neighborhoods (e.g., Mount Greenwood, Riverdale, Hegewisch).

---

## Reproducing the analysis

Requirements: Docker, a Python environment with `requirements.txt` installed, and Node (for
`mapshaper`, run via `npx`).

```bash
# 1. start PostGIS
docker run -d --name chicago-postgis -e POSTGRES_PASSWORD=chicago \
  -e POSTGRES_DB=school_gap -p 5433:5432 postgis/postgis:16-3.4

# 2. (optional, for travel time) start the routing engines
bash analysis/osrm/osrm_up.sh        # driving  (downloads OSM extract, builds graph, serves :5000)
bash analysis/otp/otp_up.sh          # transit  (downloads CTA GTFS, builds graph, serves :8080)
python analysis/14_driving_access.py # driving matrix
python analysis/15_transit_access.py # CTA transit matrix
python analysis/18_routes.py         # route geometry for click-to-route

# 3. rebuild the whole pipeline end-to-end
PY=/path/to/python ./analysis/run_all.sh

# 4. run the map
cd frontend && npm install && npm run dev
```

`run_all.sh` rebuilds every table and export from a clean database. The routing-engine outputs
are committed, so the rebuild reproduces the map without the engines running; the matrices are
regenerated when the engines are up. The ACS release is pinned so reruns can't silently drift.

---

## Repository layout

```
analysis/        download + PostGIS pipeline (numbered stages 01–18), SQL, and method docs
  osrm/ otp/     Docker bring-up scripts for the routing engines
  FINDINGS.md    numbers, methods, and honest limits
  DATA_INVENTORY.md   field-by-field coverage audit
output/          exported GeoJSON/CSV (analysis source of truth)
frontend/        React + TypeScript + MapLibre app (serves static data from public/data)
PROJECT_BRIEF.md / PROJECT_OVERVIEW.md   the project's design and decisions
```

Large or regenerable inputs (raw downloads, OSM/GTFS feeds, routing graphs, the generated
`load.sql`, `node_modules`) are gitignored; the computed outputs the app needs are committed.

---

## Limits

- **Descriptive, one year, cross-sectional.** No trends over time, no causal claims, and no
  admission-odds estimates.
- **Transit is CTA-only** (no Metra or Pace), so transit access is understated where those lines
  run; driving times are free-flow (no live traffic).
- **Routes start at a neighborhood's center point**, not the exact click, matching how the
  travel-time numbers are computed.
- **Selective tiers are approximated** from ACS income, not the official CPS tier dataset (which
  is not published as a current bulk file); this is labeled as a proxy throughout.

---

## Author

[Alan Zavala](https://github.com/alanzavala1)
