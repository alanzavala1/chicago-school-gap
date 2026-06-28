# Data Inventory & Coverage Audit

What we pulled, what we use, what's available-but-unused, and what we haven't pulled.
Purpose: cover our bases. We deliberately keep Finding 1 lean (SAT lead) — this is the
menu, not a mandate to use everything.

## ⚠️ Dataset trap (applies to all of twrw-chuq)
Every `*_avg`, `*_avg_pct`, and `*_cps_pct` column is a **broken placeholder** — the same
district-wide value repeated for every school (e.g. `student_attendance_avg_pct`=88.3,
`teacher_attendance_avg_pct`=94, `sat_grade_11_score_cps_avg`, all `graduation_*_cps_pct`).
**Always use the `*_school` / `*_year_N` per-school variants, and check distinct-count
before trusting any column.** `_year_2` = current year, `_year_1` = prior (verified).

## In hand & USED (Finding 1)
- `sat_grade_11_score_school` (lead quality metric), `student_attendance_year_2` (real
  attendance), `chronic_truancy_pct`, school lat/long, type/category.
- Tract geometry (TIGER 2020), ACS B19013 income, HS attendance boundaries.

## In hand, REAL, but UNUSED — extra outcome measures
All near-complete for the 45 default schools (coverage shown /45). Strong candidates to
enrich the composite quality index or serve as alternative quality lenses:

| Field (`*_school` / `*_year`) | Cov (45) | What it is | Value |
|---|---|---|---|
| `graduation_4_year_school` | 45/45 | 4-yr graduation rate | ⭐ top outcome (brief originally wanted it) |
| `freshmen_on_track_school` | 45/45 | Freshman OnTrack | ⭐ CPS's signature leading indicator of grad |
| `college_enrollment_school` | 45/45 | % enrolling in college | strong downstream outcome |
| `one_year_dropout_rate_year` | 45/45 | dropout rate | direct, inverse-quality |
| `mobility_rate_pct` | 45/45 | student mobility/instability | context, not pure quality |
| `college_persistence_school` | 44/45 | % persisting in college | downstream outcome |
| `school_survey_safety` + other 5Essentials | ~mostly | climate survey ratings | softer signal, mixed coverage |

Note: these outcomes are mutually correlated (a school strong on SAT is usually strong on
graduation/OnTrack), so adding them tightens the composite but won't tell a *new* story.

## Downloaded & loaded since first draft (now part of the pipeline)
| Dataset | ID | Status / use |
|---|---|---|
| **Demographics / School Profile** | `3dhs-m3w4` (SY2425) | ✅ downloaded + loaded (`school_demographics`). Powers the Finding-1 income-vs-race honesty check, Finding-2 representation, and school-panel composition. |
| **Community Areas** | `igwz-8jzy` | ✅ downloaded + loaded (`community_areas`). Tracts/schools tagged with their 77 named neighborhoods (e.g. Brighton Park); top tier of the planned drill-down map. |

## Still not downloaded — pull when relevant
| Dataset | ID | Why / when |
|---|---|---|
| **School Admissions** | `rvbr-fi8c` | selective/program types — deeper Finding-2 detail (not required for current findings). |
| **Selective seat / offer / facility capacity** | (source TBD) | the planned policy-lever analysis wants *actual* capacity; until found, use **enrolled selective students as a disclosed proxy** for available capacity (enrollment ≠ capacity). |
| **External school ratings** | Illinois Report Card / CPS SQRP | to **validate** the performance index against an independent benchmark. |

## Recommendation
- **Finding 1:** SAT as lead + 3-axis composite + the income-vs-race honesty check are done.
- **Next analytical step (calibrated):** the policy-lever chapter — selective *capacity* vs
  *need* by geography (practical access, not "ownership"), framed as a transparent scenario,
  with capacity proxied by enrollment **and disclosed as such** until a real seat source is found.
