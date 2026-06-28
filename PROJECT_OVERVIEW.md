# Chicago School Gap — Project Overview, Direction & Build Plan

**Status:** Phase 1–2 analysis complete and confirmed; v1 interactive map built. Now
pivoting the product to a single "school-health" map with a data-science core and
semantic-zoom exploration. _Last updated: 2026-06-24._

Companion documents (this file is the high-level synthesis; those hold the detail):
- [`PROJECT_BRIEF.md`](./PROJECT_BRIEF.md) — original vision, verified data sources, scope guards.
- [`analysis/FINDINGS.md`](./analysis/FINDINGS.md) — the confirmed numbers, methods, honest limits.
- [`analysis/DATA_INVENTORY.md`](./analysis/DATA_INVENTORY.md) — every field, what's used, what's available.

---

## 1. What this project is

An interactive map of Chicago that shows, for any part of the city, the quality of the
public high school a student is assigned by address, how that compares across the city, and
whether the selective-enrollment system widens or narrows the gap.

**The one question everything serves:**
> In Chicago, how much does the neighborhood you're born into determine the high school you
> get — and does selective enrollment counteract that, or reinforce it?

**Project vs. personal story (kept separate).** The product is a neutral analytical tool that
stands on its data with no reference to any person. The author's background — growing up in
Brighton Park and testing into a selective school (Jones) — is *narration* used only when
presenting the project (a README intro, a demo, an application), never a component of the
analysis.

---

## 2. Who it's for — UChicago Applied Data Fellowship

This is a portfolio project aimed at **data-analyst / data-for-impact / civic-tech roles**,
with the **University of Chicago Applied Data Fellowship (ADF)** as the anchor target. The ADF
embeds data practitioners inside government and nonprofit partners and asks them to turn messy
public data into **policy-relevant insight a non-technical decision-maker can act on**. It
spans three tracks: **policy / project management · data analysis & visualization · data
engineering & data science.**

This project is deliberately designed to hit all three, and to fill the gap a previous
full-stack project (NFLDB) doesn't: **finding a real insight in messy public data and
communicating it to a non-technical audience.** The new data-science layer (below) is what
pushes it from "analysis & viz" squarely into "data science" as well.

### Skills it demonstrates (mapped to ADF)
| Skill | How this project shows it |
|---|---|
| **GIS / geospatial** (headline new skill) | PostGIS spatial joins, distance/proximity, choropleths, semantic-zoom map |
| **SQL + PostGIS** | Joining 7+ datasets; `ST_Within`, `ST_Distance`, `ST_DWithin`, spatial rollups |
| **Statistical analysis** | Correlations, partial correlation / confound control, representation ratios |
| **Data science** (new) | PCA composite index, k-means clustering, a predictive model + residual analysis |
| **Python data engineering** | Reproducible multi-source pipeline (Socrata, Census, TIGER), wrangling |
| **Interactive data visualization** | React + MapLibre map with drill-down exploration |
| **Data-to-decision communication** | A tool a parent could use + a short written brief; honest framing |

---

## 3. What we've found so far (confirmed in the data)

Cross-sectional, one school year (CPS SY2024–25 + ACS 2020–24 5-year). Full detail and method
in [`analysis/FINDINGS.md`](./analysis/FINDINGS.md).

**Finding 1 — Your neighborhood sorts your assigned school, and the line is racial, not income.**
- Neighborhood income correlates with assigned-school SAT (tract r = 0.38, school-level r = 0.52).
- **But it's mostly a proxy for race.** Controlling for poverty + racial composition, income's
  partial correlation collapses to **−0.07**. The strongest single predictor is **% Black
  (r = −0.52)**; % Hispanic ≈ 0. Income only *looks* predictive because Chicago is segregated by
  income and race at once.
- Honest data-quality note that reinforces this: 18 tracts have a *suppressed* (missing) income
  estimate; they span the full 0–100% Black range but average **61% Black vs 33% citywide** (and
  ~39% poverty vs 18%), so income is **missing-not-at-random** — a real but modest skew toward
  Black, high-poverty tracts. (2 of those 18 also lack race, so race coverage is 789/791.)

**Finding 2 — Selective enrollment reinforces the gap; it doesn't fix it.**
- **Representation:** even with the tier system, selective schools under-represent low-income
  (ratio 0.66), Black (0.79), and Hispanic (0.67) students, and over-represent White students
  **2.4×**.
- **Quality-aware access:** distance to *any* selective school isn't racially patterned, but
  access to a *good* one is — % Black ↔ nearest-selective SAT r = **−0.61**; the Blackest
  neighborhoods are ~2× farther from a top selective (7.3 mi vs ~3 mi).
- **They compound (r = +0.47):** the "double-disadvantage" neighborhoods (weak assigned school
  *and* weak access) are **78% Black**; "double-advantage" are **58% White**. (Tract counts are
  approximate — see FINDINGS — but this demographic skew is the robust, reproducible result.)

**Bottom line:** the neighborhood you're born into strongly shapes your public-school options
along racial lines, and the escape valve (selective enrollment) is least reachable exactly where
the default schools are weakest. _Descriptive — access, sorting, representation; never causal, and
never admission odds by neighborhood._

---

## 4. What's already built

**Analysis layer (complete & reproducible):** PostgreSQL + PostGIS (Docker `postgis/postgis`,
container `chicago-postgis`, db `school_gap`). A scripted pipeline:
`01_download.py` → `02_load.py`/`load.sql` → `03_finding1.sql` → `04_diagnostics` →
`05_proxy_tiers` → `06_honesty_check.py` → `07_finding2.sql` → `09_export.sql` → GeoJSON.

**Data integrity wins already banked (the "don't get fooled" work):**
- Caught a **tract-vintage mismatch** (Chicago portal tracts are 2010-vintage; ACS is 2020) that
  would have silently dropped ~37% of tracts — switched to Census TIGER 2020 tracts (100% join).
- Caught **broken placeholder columns** (every `*_avg`/`*_cps_pct` field is a constant district
  figure); use the real per-school `*_school`/`*_year_N` fields instead.
- The Census API now **requires a key**; replaced with the keyless **Census Reporter** API for
  the identical ACS tables — zero secrets, fully reproducible.

**Frontend v1 (built, now being reconceived):** React + TypeScript + MapLibre GL JS
(`react-map-gl`), CARTO dark basemap, static GeoJSON (no live DB in production). It has a
choropleth with switchable layers, a legend, a neighborhood panel (with reverse-geocoded
address via Nominatim), a rich school panel, school pins, and a swipe-compare. **The layer-toggle
model is what we're replacing** (see §6).

**Data sources (all verified, keyless):** CPS School Progress Reports SY2425 (`twrw-chuq`), School
Profile demographics (`3dhs-m3w4`), HS attendance boundaries (`4kfz-zr3a`), Chicago community
areas (`igwz-8jzy`), Census TIGER 2020 tracts, ACS 2020–24 (income/race/poverty via Census
Reporter).

---

## 5. The new direction (decided this session)

**Problem with v1:** it's an excellent *explorer* but a passive one. Ten toggles that re-skin the
same map read as "tabs of the same thing," the mixed color systems add visual noise, and the
core insight is something the user has to assemble themselves.

**New concept — the map *is* the hook, with depth you fall into.** One clean landing view of
Chicago as a **school-health map**: neighborhoods shaded on a struggling → thriving scale, every
school plotted as a point, the clusters of trouble and success immediately visible. **No toggles.**
The user then **zooms or clicks to go deeper** — city → community area → tract → individual school
— pulling more detail at each level they choose.

Two honest, distinct signals share the map:
- **Areas** are colored by *what a resident there is handed* — the performance of their assigned
  school plus their selective access.
- **School points** are colored by *how each school itself performs* (its own cluster), so the
  selective schools and the "beating-the-odds" schools stand out among the points.

**Confirmed design decisions:**
1. Top level = the **77 named community areas** (interpretable "larger clusters"), drilling to
   the 791 tracts, then to schools.
2. **Methods stay deliberately lean** (post-audit calibration): a *transparent* performance index
   (PCA/k-means demoted to validation, not the headline), plus **one** policy-lever analysis
   (selective capacity vs. need). "Beating-the-odds" residuals are optional and carefully modeled.
3. Keep the **two-signal split** (areas = what you're assigned; points = each school's own
   performance).
4. **Protect the simple spine.** The backbone story stays: assigned-school quality varies by
   neighborhood → the axis is racial segregation more than income → selective enrollment doesn't
   fully counteract it → access to *good* selective is worst where defaults are weakest → here's
   what that means spatially. Every analysis below serves that spine; none buries it.

---

## 6. The analytical layer (calibrated after audit — fewer methods, used honestly)

The first plan leaned on PCA + k-means as the "data-science core." The audit (and a reviewer)
correctly flagged that because the outcome metrics are highly collinear, the data is essentially
one-dimensional — so PCA mostly produces a fancy "overall performance" axis and k-means just
slices a continuum and dresses bins up as "natural clusters." For an ADF audience, **fewer methods
used transparently beats ML for show.** Revised:

**A. A transparent performance index (lead) — validated, not generated, by PCA.** Standardize the
per-school outcome metrics (SAT g11, 4-yr graduation, college enrollment, freshman on-track,
attendance, chronic truancy [inverted]) and take a simple **z-score mean** as the index — anyone
can read how it's built. Then *check* it against **PC1** and an **external rating** (Illinois
Report Card / CPS SQRP) to show it isn't arbitrary. Covers the ~130–150 standard high schools with
outcome data; non-testing alternative/special-ed/virtual schools are excluded and that's disclosed.

**B. Tiers, not "clusters."** Group schools into struggling / middle / thriving by **transparent
quantiles of the index**, not k-means. If k-means is shown at all, it's only to confirm the
quantile tiers — and we report the silhouette score honestly rather than implying discovered types.

**C. "Beating the odds" residuals — OPTIONAL, carefully modeled.** A *simple, cross-validated*
linear model predicting the index from student/neighborhood profile, **segmented by school type**
(selective schools select their students — don't conflate intake with performance). Residuals flag
schools doing better/worse than demographically similar peers — framed strictly as "**outperforms
similar schools**," never "better-run." Kept as a secondary highlight, never the centerpiece, and
only if the model is disciplined; with ~150 schools, residuals are noisy and won't be over-read.

**D. The policy-lever chapter — selective capacity vs. need (the one new analysis).** The honest,
feasible, ADF-grade question: *the geography of selective-enrollment capacity creates unequal
**practical access**, worst exactly where default schools are weakest.* Note carefully: selective
schools are **citywide institutions**, not neighborhood-owned — the claim is about access, not
ownership. Compute selective **capacity-per-school-age-child by area** (capacity proxied by
**enrolled selective students**, *disclosed as a proxy* until a real seat/offer/facility source is
found), overlay against the double-disadvantage areas, and quantify the mismatch. An optional
**siting step is a scenario tool, not a prescription**: "*if CPS added ~N selective-equivalent
seats, these locations would most reduce the largest access gaps under this model.*"

**E. Roll up to places.** Each **tract** → its assigned-school performance + selective access. Each
**community area** → **population-weighted** rollup, with a stated MAUP / ecological-inference
caveat (area averages don't describe individuals). The drill-down-to-tract design mitigates this.

**Stretch (schedule-gated): transit-time access.** Straight-line miles understate burden for
car-free families, but GTFS/OpenTripPlanner is a project of its own. A strong straight-line
analysis with honest caveats is the baseline; CTA travel time is added only if it lands cleanly.

**Tooling note:** the z-mean index, quantiles, PCA (SVD), and a CV'd linear model are all
implementable in NumPy if `scikit-learn` wheels are unavailable on Python 3.14. Method choice is
recorded either way.

### Reproducibility (now enforced)
All SQL is checked in (including `08_combined.sql`, the tie-safe combined-status); `run_all.sh`
rebuilds the pipeline end-to-end from a clean database; the ACS release is **pinned** (`acs2024_5yr`,
asserted on load); and `requirements.txt` defines the Python env. Verified by a clean-room rebuild
that reproduced the numbers exactly.

---

## 7. The map experience (semantic zoom, no toggles)

- **Landing (city):** 77 community areas shaded struggling→thriving + all schools as points
  (color = performance **tier**; any beating-the-odds schools get a distinct glow). A single
  headline stat floats on the map. This is the visual hook.
- **Zoom in / click an area:** its **tracts** fade in at finer resolution; a panel summarizes the
  community area (its schools, demographics, health).
- **Zoom / click a school:** the rich **school panel** (already built), now showing its tier
  and (optionally) over/under-performance vs. similar schools.
- Drill-down is driven by **zoom + click together**, so it feels like one continuous map you fall
  into rather than tabs you flip.
- **Visual refresh throughout:** one cohesive, restrained, colorblind-safe palette; softer fills
  so streets show through; glow on school points; smooth morphing transitions between levels.

---

## 8. Honest framing rules (non-negotiable)

- **Descriptive, not causal.** An index and tiers of *outcomes*; demographics *predicting*
  outcomes, never *causing* them.
- **Access, not ownership.** Selective schools are citywide; claims are about *practical access*
  to capacity, never "this neighborhood's seats." Siting is a *scenario*, not a prescription.
- **Capacity is proxied.** Where real seat/offer counts are unavailable, "capacity" = enrolled
  selective students, **labeled as a proxy.**
- **No admission-odds prediction** — origin-level admissions data is not public. The model
  predicts *school performance*, and residuals are framed as "outperforms its demographic
  profile," not "is better-run."
- **One year, cross-sectional.** No multi-year trends (test changes + COVID break the series).
- **Aggregation honesty** — PCA avoids arbitrary metric weighting; rollups are population-weighted
  and the choice is stated; excluded schools (non-testing) are disclosed.
- **It's race, stated carefully.** Income and race are too collinear to fully separate (that
  entanglement is itself the finding); lead with the partial-correlation evidence, not unstable
  individual coefficients.

---

## 9. Build plan

**Phase 0 — Hardening (DONE).** Tie-safe deterministic combined-status (`08_combined.sql`),
`run_all.sh` clean-room rebuild, pinned ACS release, `requirements.txt`, corrected docs.

**Phase A — Analysis (calibrated; build on the existing PostGIS pipeline).**
1. Assemble the per-school feature matrix from the loaded tables.
2. **Transparent z-score performance index;** validate against PC1 + an external rating.
3. **Quantile performance tiers** (k-means only to confirm; report silhouette honestly).
4. **Policy-lever chapter:** selective capacity-per-child by area (capacity = enrolled selective
   students, *disclosed proxy*) → need-vs-supply mismatch → optional scenario siting.
5. _Optional:_ simple CV'd, type-segmented residual model ("beating the odds"), only if disciplined.
6. Population-weighted roll-ups to tract + community area (MAUP caveat).
7. Export refreshed GeoJSON: `community_areas` (health + tier), `tracts` (health + access/need),
   `schools` (index, tier, optional residual) — extending the current export step.

**Phase B — Map rebuild.**
1. Single landing view (community areas + school points), cohesive palette, glow, headline stat.
2. Semantic-zoom drill-down: city → community area → tract → school (fade-in by zoom + click).
3. Remove the layer switcher; reuse and extend the existing panels. Keep one way to inspect the
   demographic relationship so the "is it race?" check stays visible.

**Phase C — Polish & communicate.**
1. Transitions, optional beating-the-odds highlight, refined typography/legend.
2. A 2–3 page written brief stating the finding for a non-technical decision-maker.
3. Deploy the static frontend.

**Out of scope (unchanged):** multi-year trends, real turn-by-turn routing (straight-line v1),
elementary schools, admission-odds modeling, selective-cutoff PDF scraping.

---

## 10. Immediate next step

Phase 0 hardening is complete and verified by a clean-room rebuild. Begin **Phase A**: assemble
the school feature matrix, compute the **transparent performance index** (validate against PC1 +
an external rating), derive **quantile tiers**, then the **capacity-vs-need policy chapter** — the
foundation the new map is built on. The "beating-the-odds" residual model stays optional.
