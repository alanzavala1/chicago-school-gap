# Data Inventory & Coverage Audit

A field-by-field record of what's pulled, what the analysis uses, what's available but
unused, and the data traps worth knowing about. The analysis is deliberately lean — it
leads on SAT and a small composite — so this is the menu, not a list of everything in play.

## ⚠️ Dataset trap (applies to all of twrw-chuq)
Every `*_avg`, `*_avg_pct`, and `*_cps_pct` column is a **broken placeholder** — the same
district-wide value repeated for every school (e.g. `student_attendance_avg_pct`=88.3,
`teacher_attendance_avg_pct`=94, `sat_grade_11_score_cps_avg`, all `graduation_*_cps_pct`).
**Always use the `*_school` / `*_year_N` per-school variants, and check the distinct count
before trusting any column.** `_year_2` = current year, `_year_1` = prior (verified).

## In hand and used
- `sat_grade_11_score_school` (lead quality metric), `student_attendance_year_2` (real
  attendance), `chronic_truancy_pct`, school lat/long, type/category.
- Tract geometry (TIGER 2020), ACS B19013 income, ACS B03002 race, ACS B17001 poverty,
  HS attendance boundaries, community areas.

## In hand, real, but unused — extra outcome measures
All near-complete for the 45 default neighborhood schools (coverage shown out of 45).
These are candidates to enrich the composite quality index or serve as alternative quality
lenses:

| Field (`*_school` / `*_year`) | Cov (45) | What it is | Notes |
|---|---|---|---|
| `graduation_4_year_school` | 45/45 | 4-yr graduation rate | top downstream outcome |
| `freshmen_on_track_school` | 45/45 | Freshman OnTrack | CPS's signature leading indicator of graduation |
| `college_enrollment_school` | 45/45 | % enrolling in college | strong downstream outcome |
| `one_year_dropout_rate_year` | 45/45 | dropout rate | direct, inverse-quality |
| `mobility_rate_pct` | 45/45 | student mobility/instability | context, not pure quality |
| `college_persistence_school` | 44/45 | % persisting in college | downstream outcome |
| `school_survey_safety` + other 5Essentials | ~mostly | climate survey ratings | softer signal, mixed coverage |

These outcomes are mutually correlated (a school strong on SAT is usually strong on
graduation / OnTrack), so adding them tightens the composite but doesn't tell a new story.
The analysis leaves them out to keep the quality measure simple and legible.

## Available but not pulled
| Dataset | ID | Why it might matter |
|---|---|---|
| School Admissions | `rvbr-fi8c` | selective / program types — deeper detail on the selective-enrollment picture |
| Selective seat / offer / facility capacity | (no current bulk source found) | a real capacity-vs-need analysis would need actual seat counts; CPS doesn't publish them as a current bulk file, and enrollment is not the same as capacity |
| External school ratings | Illinois Report Card / CPS SQRP | an independent benchmark to validate the SAT-based quality index against |

## Notes on what's deliberately left out
- **Official CPS selective-enrollment tiers** aren't published as a current bulk tract
  dataset (only an address-by-address lookup), so where tiers are referenced the project
  uses an ACS-income proxy and labels it as such. See `analysis/FINDINGS.md`.
- **A capacity-vs-need ("policy lever") analysis** is out of scope here: it needs actual
  selective seat counts, which aren't available as open data, and proxying capacity with
  enrollment would be too rough to report honestly.
