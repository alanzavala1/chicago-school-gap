-- =====================================================================
-- Finding 1 — The lottery: does neighborhood income predict the quality
-- of the default (neighborhood) high school you're assigned to?
--
-- Unit: census tract (2020). Each tract is assigned to the neighborhood-HS
-- attendance boundary that contains the tract's Census internal point
-- (INTPTLAT/INTPTLON, guaranteed inside the tract). That school's SAT g11
-- is the "quality" of the school the tract is handed. Income = ACS 2024
-- 5-yr median household income for the tract.
--
-- Aggregation honesty: internal-point assignment puts each whole tract with
-- one school even if the tract edge clips a second boundary; tracts are ~equal
-- population so tract-level corr approximates a per-resident view. We also
-- report a school-level correlation (below) as a robustness check.
-- =====================================================================

DROP TABLE IF EXISTS tract_assignment CASCADE;
CREATE TABLE tract_assignment AS
SELECT
  t.geoid,
  i.median_hh_income,
  b.school_id          AS assigned_school_id,
  s.short_name         AS assigned_school,
  s.school_type        AS assigned_school_type,
  s.sat_g11            AS assigned_sat,
  s.attendance_pct     AS assigned_attendance,
  s.truancy_pct        AS assigned_truancy
FROM tracts t
JOIN attendance_boundaries b
  ON ST_Contains(b.geom, ST_SetSRID(ST_MakePoint(t.intptlon, t.intptlat), 4326))
JOIN schools s            ON s.school_id = b.school_id
LEFT JOIN acs_income i     ON i.geoid = t.geoid;

-- guard: confirm internal-point assignment is unique (no boundary overlap dupes)
-- (a tract appearing twice would inflate counts)
SELECT 'tracts_assigned' AS metric, count(*) AS value FROM tract_assignment
UNION ALL
SELECT 'distinct_tracts', count(DISTINCT geoid) FROM tract_assignment
UNION ALL
SELECT 'with_income_and_sat',
       count(*) FILTER (WHERE median_hh_income IS NOT NULL AND assigned_sat IS NOT NULL)
FROM tract_assignment;

-- ---------------------------------------------------------------------
-- THE HEADLINE NUMBER: tract-level correlation income <-> assigned SAT
-- ---------------------------------------------------------------------
SELECT
  count(*) FILTER (WHERE median_hh_income IS NOT NULL AND assigned_sat IS NOT NULL) AS n_tracts,
  round(corr(assigned_sat, median_hh_income)::numeric, 3)                 AS pearson_r,
  round((corr(assigned_sat, median_hh_income)^2)::numeric, 3)             AS r_squared,
  round(regr_slope(assigned_sat, median_hh_income)::numeric * 10000, 2)   AS sat_pts_per_$10k_income
FROM tract_assignment;

-- Each quality axis separately vs income (all on the SAME complete 45-school set)
SELECT
  round(corr(assigned_sat,        median_hh_income)::numeric, 3) AS r_income_sat,
  round(corr(assigned_attendance, median_hh_income)::numeric, 3) AS r_income_attendance,
  round(corr(assigned_truancy,    median_hh_income)::numeric, 3) AS r_income_truancy
FROM tract_assignment;

-- Composite school-quality index = mean of z(SAT), z(attendance), z(-truancy),
-- z-scored across the assigned default schools, then correlated with tract income.
WITH stats AS (
  SELECT avg(sat_g11) m_sat, stddev_pop(sat_g11) s_sat,
         avg(attendance_pct) m_att, stddev_pop(attendance_pct) s_att,
         avg(truancy_pct) m_tru, stddev_pop(truancy_pct) s_tru
  FROM schools WHERE school_id IN (SELECT DISTINCT assigned_school_id FROM tract_assignment)
), q AS (
  SELECT ta.median_hh_income,
         ( (ta.assigned_sat - st.m_sat)/st.s_sat
         + (ta.assigned_attendance - st.m_att)/st.s_att
         - (ta.assigned_truancy - st.m_tru)/st.s_tru ) / 3.0 AS quality_index
  FROM tract_assignment ta CROSS JOIN stats st
  WHERE ta.median_hh_income IS NOT NULL
)
SELECT round(corr(quality_index, median_hh_income)::numeric, 3) AS r_income_composite_quality,
       count(*) AS n_tracts FROM q;

-- Spearman (rank) correlation — robust to non-linearity / outliers
WITH ranked AS (
  SELECT
    rank() OVER (ORDER BY median_hh_income) AS r_income,
    rank() OVER (ORDER BY assigned_sat)     AS r_sat
  FROM tract_assignment
  WHERE median_hh_income IS NOT NULL AND assigned_sat IS NOT NULL
)
SELECT round(corr(r_sat, r_income)::numeric, 3) AS spearman_rho FROM ranked;

-- ---------------------------------------------------------------------
-- Robustness: school-level correlation (one row per neighborhood school;
-- income = median of its tracts' median incomes). Removes tract clustering.
-- ---------------------------------------------------------------------
WITH per_school AS (
  SELECT
    assigned_school_id,
    max(assigned_school) AS school,
    max(assigned_sat)    AS sat,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY median_hh_income) AS median_tract_income,
    count(*)             AS n_tracts
  FROM tract_assignment
  WHERE median_hh_income IS NOT NULL
  GROUP BY assigned_school_id
)
SELECT
  count(*) FILTER (WHERE sat IS NOT NULL)                                  AS n_schools,
  round(corr(sat, median_tract_income)::numeric, 3)                       AS pearson_r_school_level
FROM per_school;
