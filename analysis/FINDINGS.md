# Phase 1 Findings — The Gate

**Status: Finding 1 CONFIRMED — but reframed by the honesty check. Proceed to Phase 2.**
Date: 2026-06-24. One year, cross-sectional. CPS SY2425 + ACS 2024 5-year.

> **Headline (honest version):** The neighborhood you're born into strongly sorts the
> default high school you're handed — and the dividing line is **overwhelmingly racial
> (share Black), not income per se.** Neighborhood income *looks* like it predicts school
> quality (r=0.38), but that effect washes out to ~0 once you control for racial
> composition; % Black is the stronger and the surviving signal. See the honesty check.

---

## Finding 1 — Does the neighborhood you're born into decide the high school you get?

**Yes.** Higher-income Chicago neighborhoods are assigned to higher-quality default
(neighborhood) high schools (income↔SAT r=0.38 tract, 0.52 school). But the income story
is mostly a proxy: the real axis is **racial composition** (see honesty check below). The
relationship is also *moderate in size* because all neighborhood defaults are clustered low
— the genuinely good schools sit outside the assignment system (see "The real gap").

### The numbers (real, reproducible)

| Measure | Value | n |
|---|---|---|
| **Tract-level Pearson r** (income ↔ assigned-school SAT) | **0.378** | 773 tracts |
| Tract-level Spearman ρ (rank, robust) | 0.387 | 773 |
| R² (variance explained) | 0.143 | — |
| Regression slope | **+7.7 SAT pts per +$10k** tract income | — |
| **School-level Pearson r** (one row per neighborhood school) | **0.517** | 45 schools |

The school-level r (0.52) is higher than the tract-level r (0.38) because tract-level
includes many tracts pointing at the same school (pseudo-replication) plus within-zone
income spread; both tell the same story.

**Robust across three independent quality measures** (not an artifact of SAT alone) —
income correlates with each axis of the assigned default school in the same direction:

| Quality axis of assigned default school | Pearson r vs tract income |
|---|---|
| SAT grade 11 | +0.378 |
| Attendance (real, current year) | +0.299 |
| Chronic truancy | −0.230 |
| **Composite z-index (SAT + attendance − truancy)** | **+0.330** |

All 45 default neighborhood schools have complete SAT, attendance, and truancy data, so
this rests on no imputation.

### The gradient (most communicative view)

Tracts grouped into income deciles → mean SAT of the school they're assigned:

| Income decile | Income range | Mean assigned SAT | Mean truancy |
|---|---|---|---|
| 1 (poorest) | $13.6k–36k | 775 | 76.8% |
| 5 | $63k–73k | 842 | 69.1% |
| 10 (richest) | $141k–250k | 881 | 67.1% |

Monotonic (one minor wobble at decile 7). **~106 SAT points** separate the default
schools of the poorest vs richest deciles.

### The real gap (honest nuance — and the setup for Finding 2)

The income→default-school effect is only *moderate* because **all neighborhood default
schools are clustered low**: SAT 716–1081, mean **837**. The genuinely good schools are
the **11 selective-enrollment** schools — mean SAT **1141** (up to 1334) — which sit
*entirely outside* the neighborhood-assignment system. So your neighborhood weakly sorts
you among mediocre defaults; the real quality leap requires *escaping* the default system
via selective enrollment. That is exactly Finding 2.

**Personal anchor (Brighton Park):** Brighton Park tracts are assigned to **Kelly HS**
(neighborhood, SAT 885, 62% truancy). Alan's escape hatch, **Jones** (selective, SAT
**1276**), is 5.1 miles away. The top selectives (Payton 1334, Northside 1303, Young
1297) all cluster North/Central — none near Brighton Park.

### Honesty check — is it income, or is it race? (IT'S RACE)

We tested whether neighborhood *income* predicts assigned-school quality on its own, or
only because income tracks racial/poverty composition (deeply collinear in Chicago:
income↔%white r=+0.75, income↔poverty r=−0.69). Tract level, n=773, complete data.
`analysis/06_honesty_check.py`.

| Predictor of assigned-school SAT | bivariate r | R² alone |
|---|---|---|
| Median household income | +0.378 | 0.143 |
| Poverty rate | −0.375 | 0.141 |
| **% Black** | **−0.524** | **0.274** |
| % Hispanic | +0.048 | 0.002 |
| % White (non-Hispanic) | +0.549 | — |

**Decisive result — partial correlation:** income vs assigned SAT controlling for poverty
+ racial composition drops from **+0.378 → −0.068** (essentially zero). Income's apparent
effect is almost entirely explained by racial composition. **% Black is the single
strongest axis;** % Hispanic is ~0 (Hispanic neighborhoods like Brighton Park are *not*
the ones handed the worst defaults — the penalty concentrates in Black neighborhoods).

**Reframe:** the honest statement is *"the neighborhood you're born into strongly sorts the
default high school you're handed, and the dividing line is overwhelmingly racial (share
Black) — income predicts quality mainly because Chicago is segregated by income and race at
once."* This is descriptive (segregation + historical disinvestment), **not** "race causes
school quality." Collinearity is severe, so individual OLS coefficients are unstable (the
income coefficient even flips sign — a textbook suppression artifact); we therefore lean on
the single-factor R² comparison and the partial correlation, not the multivariate betas.
Map implication: the "looks-like-the-same-map" pair is **% Black ↔ school quality**, not
income ↔ school quality.

*Data-quality note reinforcing this:* 18 of 791 analysis tracts have a suppressed (null)
ACS median income. They **span the full 0–100% Black range but average 61% Black vs 33%
citywide, and ~39% poverty vs 18% citywide** — so income suppression skews toward Black,
high-poverty tracts (Census suppresses estimates in small / high-variance tracts), making
neighborhood income **missing-not-at-random**. The skew is real but modest, not uniform.
(Honest correction: an earlier draft overstated this as "78–93% Black" from a 6-row sample,
and 2 of the 18 tracts also lack race data — so race coverage is 789/791, not all 791.)

### Honest limits
- **Descriptive only.** This measures sorting/access, not causation and not admission odds.
- **Quality = SAT grade 11** (primary), with attendance and truancy as corroborating
  axes. Data caveats, verified at the source:
  - `student_attendance_avg_pct` is a broken placeholder (constant 88.3 = district
    figure; `teacher_attendance_avg_pct` likewise flat 94). Real per-school attendance
    lives in `student_attendance_year_2` (current yr; confirmed by cross-referencing the
    SY2324 file) — 167/170 coverage, range 43–94%. We use that.
  - SAT: 150/170 HS have a real score; the 20 without are genuinely non-testing schools
    (YCCS dropout-recovery charters, special-ed, virtual, alt "option" schools) — a real
    feature of the system, not a coverage gap. SAT `0` treated as missing.
  - No ACT: CPS replaced the ACT with the grade-11 SAT (SAT School Day) in spring 2017;
    SAT is the complete current measure. ACT exists only pre-2017 (excluded by design).
- **Assignment = Census internal point in attendance boundary** (1 tract → 1 default
  school; 791 of ~860 Chicago tracts have a neighborhood-HS default; the rest fall in
  areas with no default neighborhood HS).
- Vintage-consistent: 2020 tracts + ACS 2024 5-yr (both 2020-vintage); 100% GEOID join.

---

## Finding 2 — Does selective enrollment counteract the gap, or reinforce it?

**It reinforces it.** Selective enrollment is the main route to a high-quality CPS high
school outside the neighborhood-assignment system — but the neighborhoods stuck with the
worst defaults are also the worst-served by selective access, and selective student bodies
skew away from the kids the system is supposed to reach. Descriptive (access, proximity,
representation) — NOT admission odds by neighborhood. `analysis/07_finding2.sql`.

### (A) Representation — enrollment-weighted, 11 selective schools vs all CPS HS
| Group | Selective | District (all CPS HS) | Representation ratio |
|---|---|---|---|
| Low-income | 47.8% | 72.5% | **0.66** (under) |
| Black | 27.8% | 35.2% | 0.79 (under) |
| Hispanic | 32.7% | 48.6% | 0.67 (under) |
| White | 23.0% | 9.7% | **2.36 (over)** |

Even with the tier system, selective bodies under-represent low-income, Black, and Hispanic
students and over-represent white students 2.4×.

### (B) Access — quality-aware (raw "nearest selective" hides it)
Distance to the *nearest* selective is barely patterned by race (r=−0.19). But the nearest
selective for a South Side neighborhood is often a low-SAT one; access to a *good* selective
is sharply racial:
- % Black ↔ **SAT of nearest reachable selective: r = −0.61**
- % Black ↔ **miles to nearest elite (top-5, SAT≥1250): r = +0.50** (income r=−0.40; Hispanic r≈0)

| Neighborhood % Black quartile | Avg miles to elite selective | Avg SAT of nearest selective |
|---|---|---|
| Q1 (0–3%) | 3.7 | 1202 |
| Q2 (3–10%) | 2.8 | 1224 |
| Q3 (10–72%) | 4.6 | 1112 |
| **Q4 (72–100%)** | **7.3** | **1001** |

The Blackest neighborhoods are ~2× farther from an elite selective and the best selective
they can reach scores ~200 SAT points lower.

### (C) Combined status — the disadvantages compound (r = +0.47)
Default-school quality and reachable-selective quality are **positively** correlated
(r=+0.47) across the 791 assigned tracts — selective access is best exactly where the
default is already best. Classifying tracts into value-based thirds on each axis
(`analysis/08_combined.sql`, tie-safe & deterministic):

| Combined status | Tracts | % Black | % Hispanic | % White | Avg income |
|---|---|---|---|---|---|
| **Double disadvantage** (weak default + weak access) | 166 | **78%** | 14% | 4% | $45.6k |
| Single disadvantage | 262 | 39% | 27% | 23% | $79.1k |
| Middle | 249 | 7% | 42% | 41% | $95.8k |
| **Double advantage** (strong default + strong access) | 114 | 8% | 17% | **58%** | $97.7k |

_Group sizes are unequal by design: the inputs are discrete (45 distinct assigned-school
SATs, 11 distinct nearest-selective SATs), so value-based thirds can't be equal-count — and
that's the honest choice, because the alternative (`ntile`) splits identical values across
tiers arbitrarily and non-deterministically. **The robust, reproducible result is the
demographic skew of the corners, not the exact tract counts.**_

**Answer to the project's question:** selective enrollment **does not rescue** the
worst-default neighborhoods — those same neighborhoods have the worst access to good
selectives and are under-represented inside selective schools. The double-disadvantage
neighborhoods are 78% Black; the double-advantage are 58% white. Consistent with Finding 1,
the axis is race; Hispanic neighborhoods (e.g. Brighton Park) sit mostly in the middle, not
the worst-off group.

### (D) Routed access — real driving vs CTA transit time (replaces straight-line)

Straight-line distance overstates access for car-free families. We computed real
travel time from each tract's internal point to the 11 selective schools two ways:
**driving** (OSRM road network) and **CTA transit** (OpenTripPlanner: walk + bus/rail
+ transfers, median across weekday 7–8 AM departures, service date 2026-07-08).
`analysis/14_driving_access.py`, `analysis/15_transit_access.py`,
`analysis/16_routed_access.sql`. Straight-line miles are retained for comparison.

**Moderate by car, severe by transit.** To the nearest *elite* selective (SAT ≥ 1250):

| Access lens | best-access quartile | worst-access quartile | ratio |
|---|---|---|---|
| Straight-line | 3.7 mi | 7.3 mi | ~2.0× |
| **Driving** | 9.6 min | 15.7 min | ~1.6× |
| **CTA transit** | 18 min | 56 min | ~3.1× |

Citywide, transit to an elite selective takes a **median 35 min (range 4–107)** and
**~3.3–3.7× as long as driving**. Highways equalize the car trip; transit does not —
that contrast *is* the access finding, and it is the burden that falls on the families
least likely to own a car.

**It is NOT a single-group story — and that matters.** Correlating transit time to the
nearest elite selective against every demographic axis (none pre-selected):

| Axis | r |
|---|---|
| % white | **−0.41** (whiter → faster) |
| median income | −0.36 |
| % Hispanic | **+0.27** |
| % Black | **+0.24** |
| poverty rate | +0.14 |

This **differs from the straight-line/driving result**, where % Black was the dominant
axis. By transit, **Black and Hispanic neighborhoods are disadvantaged at nearly equal
magnitude**, and the strongest single thread is white / high-income *advantage*. The
worst-access transit quartile is **39% Black and 39% Hispanic** (mean income $69k); the
best is **51% white** ($110k). The three single worst tracts span **Mount Greenwood
(white), Riverdale (Black), and Hegewisch** — i.e. the extremes are **geographic
isolation at the city's edges**, not one race. **Brighton Park** (the Hispanic anchor)
sits ~20 min from its nearest selective but **42 min from an elite one** — clearly
transit-disadvantaged, which the straight-line analysis (where Hispanic areas looked
"middle") masked. Leading with % Black alone would have reported a real but **incomplete**
picture; the transit lens is the more honest one.

**Honest limits.** CTA only — excludes Metra (esp. Metra Electric on the South Side) and
Pace, so transit access is *understated* where those fill gaps; 1–2 of 791 tracts had no
routable transit trip in the search window. Regular weekday schedule, morning window.
Descriptive access (door-to-door travel time), never admission odds.

---

## Data gate resolved — CPS tiers

Official CPS selective-enrollment tiers (1–4) are **not published as a bulk tract
dataset** — only an address-by-address GoCPS School Locator. The only downloadable
tier-by-tract data (Open City `open-city/cps-tiers`) ends at **2018** on **2010-vintage**
tracts (repo archived Nov 2025) → stale + vintage mismatch.

**Decision: ACS-income proxy tiers** (median-HH-income quartiles on the 2020 tracts).
CPS's real index is 6 socioeconomic factors (5 ACS-derived + 1 school-performance);
income is the dominant axis. The proxy is transparent, vintage-consistent, and clearly
labelled as *not* the official tier — sufficient for the descriptive access framing.

| Proxy tier | Income range | n tracts |
|---|---|---|
| 1 (most disadvantaged) | $13.6k–51k | 194 |
| 2 | $51k–72.6k | 193 |
| 3 | $72.9k–101k | 193 |
| 4 (most advantaged) | $101k–250k | 193 |

Brighton Park lands mostly Tier 2 (working-class, not poorest) — passes sanity check.
**Phase-2 upgrade path:** pull ACS B15003 (education), B25003 (homeownership), B11003
(single-parent), B16004 (language) via the same keyless Census Reporter route to build a
closer multi-variable proxy index.

---

## Pipeline (reproducible)

1. `analysis/01_download.py` → `data/raw/` (Socrata + TIGERweb + Census Reporter, keyless)
2. `analysis/02_load.py` → `analysis/load.sql` → PostGIS (`docker exec -i ... psql`)
3. `analysis/03_finding1.sql` — the headline correlation (SAT lead + composite robustness)
4. `analysis/04_finding1_diagnostics.sql` — gradient, truancy, anchor
5. `analysis/05_proxy_tiers.sql` — tier-gate resolution
6. `analysis/06_honesty_check.py` — income vs race confound test (reframed Finding 1)
7. `analysis/07_finding2.sql` — selective access + representation (straight-line)
8. **Routed access (real travel time):** `analysis/osrm/osrm_up.sh` + `analysis/14_driving_access.py`
   (OSRM driving) and `analysis/otp/otp_up.sh` + `analysis/15_transit_access.py` (OTP CTA transit)
   → matrices in `output/*_selective.csv`; `analysis/16_routed_access.sql` → `tract_routed`.
   Engine-dependent; their CSV outputs are committed so the rebuild consumes them keyless.
9. `analysis/09_export.sql` (+ views) → `output/{tracts,schools,city_boundary,community_areas}.geojson` (frontend layers)

**DB:** container `chicago-postgis`, PostGIS 16-3.4, port **5433**, db `school_gap`,
user `postgres` / pw `chicago`. Tables: `schools` (649), `attendance_boundaries` (49),
`tracts` (1332), `acs_income` (1332), `tract_assignment` (791), `tract_proxy_tier` (773).

**Income source note:** the official Census API now hard-requires a key; we use the
keyless Census Reporter API for the identical ACS B19013 table (zero secrets).
