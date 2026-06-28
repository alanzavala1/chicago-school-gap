# Chicago School Gap — Project Brief

> **This file is the single source of truth for the project.** It contains everything an
> agent (or a future me) needs to pick this up cold and start building. Read it top to
> bottom before doing anything.

---

## 1. One-sentence goal

**An interactive map of Chicago that shows, for any part of the city, the high school a
student is handed and how far they'd have to go for a better one — revealing whether
selective enrollment rescues the neighborhoods stuck with the worst schools or leaves them
doubly behind.**

The single question everything serves:
> *In Chicago, how much does the neighborhood you're born into determine the high school you
> get — and does selective enrollment counteract that, or reinforce it?*

If a feature doesn't help answer that question, it's out of scope.

---

## 2. Why this project exists (the stake)

Alan grew up in **Brighton Park** (working-class, heavily Mexican/immigrant, Southwest Side),
went to a small Catholic elementary school, then **tested into Jones College Prep** — a CPS
**selective-enrollment** high school — which put him on the path to a CS degree. He is the kid
who made it through the "escape hatch." Most kids from Brighton Park don't. This project uses
data to examine the gap he lived. **Brighton Park → Jones is the personal anchor / demo
example throughout.**

This is a portfolio project to land **data analyst / data-for-impact / civic-tech roles and
fellowships** (notably the **UChicago Applied Data Fellowship**, which embeds data people in
government/nonprofits to turn data into policy recommendations). It complements his other
project (NFLDB — a full-stack analytics platform) by proving the half NFLDB doesn't:
**finding an insight in messy public data and communicating it to a non-technical
decision-maker.**

---

## 3. The two findings (this is the actual analysis — not a school directory)

**Finding 1 — The lottery: does your neighborhood decide your school?**
- Join neighborhoods → their *assigned* (default) neighborhood high school → that school's
  outcomes; join neighborhoods → Census income.
- Quantify how strongly neighborhood income predicts default-school quality
  (correlation / simple regression). Report a real number.
- Visual: a **two-map comparison** — left = neighborhoods shaded by income, right = shaded by
  assigned-school quality. If they look like the same map, that's the gut-punch.

**Finding 2 — The escape hatch: does selective enrollment fix it?**
- Selective enrollment is the only way out of a bad default school.
- Measure **access/reach** per neighborhood: tier (cutoff advantage) + **distance/proximity to
  selective schools** (most cluster North/Central).
- Measure **representation**: do selective schools' student bodies reflect low-income kids, or
  skew wealthy despite the tier system? (compare selective schools' low-income % to district).
- The payoff: are the worst-default neighborhoods *also* the worst for escape access
  ("double-bind")? If yes → selective enrollment **reinforces** the lottery. The map colors
  neighborhoods by this combined status.

**HONEST LIMIT (do not overclaim):** We can measure *access, proximity, and representation*.
We **cannot** measure real admission odds by neighborhood — origin-level admissions data is
not public. Frame everything as **access / sorting / representation (descriptive)**, never
"your odds of getting in are X" and never "school funding *causes* outcomes" (no causal claims).

---

## 4. The product (what we're building)

A **Google-Maps-style** interactive web map of Chicago — three ways in:

1. **City view:** whole city, neighborhoods *shaded* by the data (income / default-school
   quality / double-bind status), all ~170 high schools as pins (color = type/quality,
   selective schools styled distinctly).
2. **Neighborhood view:** click a neighborhood/zone → panel with its income + demographics,
   its assigned default school(s) + stats, and the selective schools with distances/lines.
3. **Address search:** type an address → drops into the neighborhood → shows assigned
   school(s) + stats + distance to the nearest better/selective schools.
   - v1 = straight-line distance + drawn line. v2 (stretch) = real route distance/time via a
     free routing API (transit time is the most meaningful upgrade).

It must *feel* like Google Maps (drag/zoom/click/search) but it's a focused custom tool, not a
general map app.

---

## 5. Tech stack & architecture (decided)

- **Analysis layer: PostgreSQL + PostGIS** (run via the `postgis/postgis` Docker image
  locally — reuses Alan's Docker skill, $0). This is the showcase for **standard SQL +
  geospatial** (`ST_Within`, `ST_Distance`, `ST_DWithin`, spatial joins). Deliberately
  different from NFLDB's DuckDB — shows tool-selection judgment (talking point: "DuckDB for
  embedded analytics in NFLDB; Postgres/PostGIS here because the work is geospatial and
  PostGIS is the standard").
- **Frontend: React + TypeScript + MapLibre GL JS** (via `react-map-gl`) with a free basemap.
  Reuses Alan's React/TS strength.
- **Address search/geocoding:** free OSM **Nominatim** (or Mapbox free tier).
- **Architecture note:** the database is a **build-time analysis tool**. The map is read-only
  with small data, so **precompute results to GeoJSON** and have the frontend serve static
  GeoJSON — **no live DB needed in production.** PostGIS powers analysis + the SQL you show
  off; the shipped app stays simple. (Deploy target TBD — static hosting is fine; Cloud Run
  like NFLDB is an option.)

---

## 6. Data sources (ALL VERIFIED — real IDs, do not re-research from scratch)

All Chicago datasets are on the **Socrata** open-data portal. API pattern:
`https://data.cityofchicago.org/resource/<id>.json?$limit=N`
(also `.csv`, and `.geojson` for spatial/boundary datasets). No key needed for reasonable use.

| Purpose | Dataset | ID | Notes (verified) |
|---|---|---|---|
| Outcomes + type + **geo** | School Progress Reports **SY2425** | `twrw-chuq` | newest. Use this. (SY2324 = `2dn2-x66j`, which was inspected: 71 cols incl. `school_id`, `short_name`, `school_type`, `primary_category`, `sat_grade_11_score_school`, `student_attendance_avg_pct`, `chronic_truancy_pct`, `progress_toward_graduation`, **`school_latitude`/`school_longitude`**). Verify SY2425 columns match on first load. |
| **Demographics** | School Profile Information SY2324 | `cu4u-b4d9` | has `student_count_total`, `student_count_low_income`, `_black`, `_hispanic`, `_white`, `_asian`, `classification_description`. (SY2425 = `3dhs-m3w4`.) |
| Selective/admissions programs | School Admissions Information SY2324 | `rvbr-fi8c` | `program_type`, `program_group`, `program_selections`. |
| **Neighborhood assignment** | High School Attendance Boundaries SY2425 | `4kfz-zr3a` | polygons; neighborhood (non-selective) schools only — that's the point. (`.geojson` available.) |
| School locations | School Locations SY2526 | `pb6d-zzuh` | (SY2425 = `hexd-c4gn`) |
| Census tract boundaries | Boundaries – Census Tracts | `4hp8-2i8z` (or 2010: `5jrd-6zik`) | polygons, `.geojson`. |
| Community Area boundaries | Boundaries – Community Areas | `cauq-8yn6` (map) / `m39i-3ntz` | 77 stable community areas — good neighborhood unit. |

**Census income (separate source):** US Census **ACS 5-year**, table **`B19013_001E`** (median
household income) at **tract** level for **Cook County (state 17, county 031)**, via the Census
API (`https://api.census.gov/data/...`). Needs a **free API key**
(`https://api.census.gov/data/key_signup.html`).

**Verified data facts (SY2324 progress reports):** 650 schools total; **171 high schools**;
`school_type` breakdown: **397 Neighborhood, 114 Charter, 43 Magnet, 11 Selective enrollment**,
plus Classical, Regional gifted, Military, Career academy, Citywide-Option. HS field coverage:
SAT 169/171, lat/long **171/171**, attendance 168/171, graduation 169/171, truancy 147/171.

**STILL TO VERIFY (one open gate):** **CPS tier-by-census-tract** mapping (the selective-
enrollment tiers 1–4). CPS assigns tiers per tract from 6 socioeconomic variables. Sources to
check: Open City's tier tool (`cpstiers.opencityapps.org`), CPS GoCPS resources, or approximate
tiers from ACS income if no clean dataset exists. Needed for the "escape hatch" tier component.

**Join keys:** CPS datasets join on `school_id`. Spatial joins (schools→tracts→ACS, tracts→
attendance boundaries) via PostGIS using lat/long → geometry. Schools have full lat/long, so
geocoding schools is unnecessary; only the address-search feature needs geocoding.

---

## 7. Skills this project demonstrates (for the fellowship / resume)

Maps to ADF's three tracks (policy/PM · data analysis & viz · data engineering & data science):

- **GIS / Geospatial** — *new skill, the headline win.* Spatial joins, distance/proximity,
  choropleth mapping (PostGIS + MapLibre). Alan rated this "no familiarity" on the ADF app;
  this makes it demonstrable.
- **SQL (standard) + PostGIS** — joining 5+ datasets; spatial SQL.
- **Python data analysis** — wrangling, correlation, representation ratios.
- **Statistical analysis** — income↔quality correlation, accessibility metrics, representation
  ratios (real derived numbers, not re-display). Fills the analyst gap NFLDB doesn't cover.
- **Interactive data visualization** — the map (MapLibre + React).
- **Multi-source data engineering** — Socrata + Census APIs, reproducible documented pipeline.
- **Data-to-decision communication** — a tool a parent could use + a short written brief.

Pitch line: *"I joined public CPS and Census data geospatially and built an interactive map
that quantifies and shows how Chicago neighborhoods determine school access — turning messy
data into something non-technical people can use."*

---

## 8. Traps to avoid (we discussed these at length — do not fall in)

1. **"Pretty data dump."** The map must *make an argument* (shading reveals the lottery; panel
   frames hand-vs-escape), not just plot dots. The derived metrics (correlation, accessibility,
   representation) are the substance.
2. **Causal overreach.** Descriptive only — access, sorting, representation. Never "X causes Y."
3. **Broken time-series.** Use **one current school year, cross-sectional.** Do NOT build trends
   across years (COVID wiped 2020 testing; the state test changed ~2019).
4. **"It's nuanced" mush.** School-level gives concrete, nameable findings — keep them concrete.
5. **Aggregation honesty.** Be explicit about choices (e.g., enrollment-weighting); this project
   is *about* cherry-picking, so don't cherry-pick.
6. **Confirmation bias.** Report what the data says even if it contradicts the "system fails poor
   kids" prior. Honesty is the whole credibility.
7. **Scope creep.** **High schools only, one year, one question, two findings.** Explicitly OUT:
   multi-year trends, selective-cutoff PDF scraping (stretch only), real turn-by-turn routing
   (v2), elementary schools, TIF/funding-formula analysis (abandoned earlier direction).
8. **Dashboard eats the analysis.** **Analysis-first.** Freeze the finding before building UI.

---

## 9. Plan (phased — analysis-first)

- **Phase 0 — Setup:** folder ✓, git ✓, GitHub remote (manual, see README), PostGIS Docker
  container, project skeleton (`/data`, `/analysis`, `/frontend`, `/output`).
- **Phase 1 — Analysis-first (THE GATE):** load schools + tract boundaries + attendance
  boundaries + ACS income into PostGIS; run the core spatial joins; **confirm Finding 1 is
  actually in the data** (income↔assigned-school-quality correlation). If the story isn't
  there, STOP and reassess before building anything visual.
- **Phase 2 — Full analysis:** compute all metrics (accessibility/distance, representation,
  double-bind status); export everything to **GeoJSON** for the frontend.
- **Phase 3 — The map:** React + MapLibre — city view (shaded + pins), neighborhood click
  panel, address search + distance lines.
- **Phase 4 — Communicate + ship:** write the 2–3 page brief with the finding; polish; deploy
  static frontend.

---

## 10. Environment notes

- OS: Windows 11, shell is PowerShell (Bash tool also available). Docker available (used for
  NFLDB).
- A working Python with pandas + openpyxl exists at
  `C:/Users/alan/nfl/nfl-platform/api/venv/Scripts/python.exe` (or create a fresh venv for this
  project; will also need `geopandas`, `psycopg2-binary`/`sqlalchemy`, `requests`).
- Personal contact/links for any deploy/README: GitHub `alanzavala1`.

---

## 11. Direction updates (2026-06-24, after Phase 1)

Decisions made once the data was in hand. These refine §3–4; see `analysis/FINDINGS.md`
for the numbers behind them.

1. **Finding 1 reframed: it's race, not income.** Bivariately, neighborhood income predicts
   assigned default-school quality (r=0.38), but that washes out to ~0 after controlling for
   racial/poverty composition; **% Black is the strongest surviving predictor** (r=−0.52),
   % Hispanic ≈ 0. Income was mostly a proxy for segregation. State the finding this way;
   never as "income causes" or "race causes" (descriptive only; the variables are too
   collinear to cleanly separate — that entanglement is itself the point).

2. **The tool shows ALL variables; the honesty check only governs wording.** Do not narrow
   the product to one variable. Income, race (all groups), poverty, and school quality are
   all explorable layers — users see for themselves that they trace the same map. The
   "race is the strongest thread" conclusion lives in the *written analysis*, not as a filter
   that hides data.

3. **Project ≠ personal story.** Build the tool to be true and complete on its own data,
   with zero reference to Alan. "Brighton Park → Jones" is *narration* used when presenting
   it (README intro, demo, application), not a component of the analysis. (Honest caveat for
   that narration: Brighton Park is Hispanic; its default Kelly HS (SAT 885) is mid-pack, not
   bottom-tier — Alan's real story is *access/distance* to selective schools, i.e. Finding 2,
   not escaping a terrible local school.)

4. **One interactive map, not two static ones.** The §3 "two-map comparison" was just a way
   to get simultaneous visual comparison. Achieve that in a single experience instead:
   layer switcher + swipe/slider compare (+ optional bivariate shading), plus click-a-
   neighborhood → panel with all its numbers. Decide specifics in Phase 3.

5. **Terminology:** call it **selective-enrollment access** / **Finding 2**, not "escape
   hatch." For the combined worst-default + worst-access neighborhoods, use a neutral term
   like "double disadvantage," not loaded framing.
