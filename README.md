# Chicago School Gap

An interactive map of Chicago that shows, for any part of the city, the high school a student
is handed and how far they'd have to go for a better one — and whether selective enrollment
rescues the neighborhoods stuck with the worst schools or leaves them doubly behind.

**One question:** *In Chicago, how much does the neighborhood you're born into determine the
high school you get — and does selective enrollment counteract that, or reinforce it?*

This is a data-for-impact project: joining public CPS and US Census data geospatially to
quantify, and make explorable, the link between neighborhood and school access.

## Status
✅ **Phase 1 (analysis-first) complete — Finding 1 confirmed and reframed.** The neighborhood
you're born into strongly sorts the default high school you're handed — and the honesty check
shows the dividing line is **overwhelmingly racial (share Black), not income per se**:
neighborhood income↔school-quality (r=0.38) washes out to ~0 once racial composition is
controlled for, while % Black is the strongest surviving predictor (r=−0.52). See
**[analysis/FINDINGS.md](./analysis/FINDINGS.md)** for numbers, method, and honest limits.

✅ **Phase 2 complete — selective enrollment reinforces the gap.** Selective schools
under-represent low-income/Black/Hispanic students (white students over-represented 2.4×),
and the Blackest neighborhoods are ~2× farther from an elite selective. Default-school
quality and reachable-selective quality compound (r = +0.47): "double-disadvantage"
neighborhoods (weak default + weak access) are **78% Black**; "double-advantage" are
**58% white**. Tract/school/zone layers exported to `output/*.geojson`.

✅ **Real travel-time access (driving + CTA transit).** Straight-line distance is
replaced with real road-network driving (OSRM) and door-to-door CTA transit
(OpenTripPlanner). The gap is **moderate by car but severe by transit** — to a top
selective, the worst-access quartile is ~1.6× the best by car but **~3.1× by CTA**
(transit runs ~3.3–3.7× longer than driving). And by transit it is **not a single-group
story**: Black and Hispanic neighborhoods are disadvantaged at near-equal magnitude, with
the strongest thread being white/high-income advantage and the extremes being geographic
isolation at the city's edges. See **[analysis/FINDINGS.md](./analysis/FINDINGS.md)** §(D).

See **[PROJECT_BRIEF.md](./PROJECT_BRIEF.md)** for the full vision, data sources,
architecture, plan, and scope.

## Stack (planned)
- **Analysis:** PostgreSQL + PostGIS (geospatial joins) · Python (pandas)
- **Frontend:** React + TypeScript + MapLibre GL JS
- **Data:** Chicago open data (Socrata) + US Census ACS

## Built by
[Alan Zavala](https://github.com/alanzavala1)
