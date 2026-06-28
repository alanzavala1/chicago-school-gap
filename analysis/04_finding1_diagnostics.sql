-- Finding 1 diagnostics: gradient, second quality axis, and the personal anchor.

-- (1) Income DECILE -> mean assigned-school SAT. Tests for a monotonic gradient
--     (more communicative than a single r, and robust to the linear assumption).
WITH d AS (
  SELECT *, ntile(10) OVER (ORDER BY median_hh_income) AS income_decile
  FROM tract_assignment
  WHERE median_hh_income IS NOT NULL AND assigned_sat IS NOT NULL
)
SELECT
  income_decile,
  count(*)                                    AS n_tracts,
  to_char(round(min(median_hh_income)),'999G999')   AS inc_low,
  to_char(round(max(median_hh_income)),'999G999')   AS inc_high,
  round(avg(assigned_sat))                    AS mean_assigned_sat,
  round(avg(assigned_truancy),1)              AS mean_assigned_truancy
FROM d GROUP BY income_decile ORDER BY income_decile;

-- (2) Second quality axis: does income predict assigned-school TRUANCY?
--     (negative r expected: richer neighborhood -> lower-truancy default school)
SELECT
  count(*) FILTER (WHERE median_hh_income IS NOT NULL AND assigned_truancy IS NOT NULL) AS n,
  round(corr(assigned_truancy, median_hh_income)::numeric, 3) AS pearson_r_truancy
FROM tract_assignment;

-- (3) Personal anchor — Brighton Park (community area 58, SW Side). Find the
--     neighborhood school(s) its tracts are assigned to and their stats.
--     Brighton Park ~ bounded by tracts around lon -87.70, lat 41.82.
SELECT
  assigned_school, assigned_school_type,
  count(*) AS n_tracts,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY median_hh_income)) AS median_income,
  max(assigned_sat) AS sat, max(assigned_truancy) AS truancy
FROM tract_assignment ta
JOIN tracts t ON t.geoid = ta.geoid
WHERE ST_Contains(
        ST_MakeEnvelope(-87.73, 41.805, -87.685, 41.835, 4326),
        ST_SetSRID(ST_MakePoint(t.intptlon, t.intptlat), 4326))
GROUP BY assigned_school, assigned_school_type
ORDER BY n_tracts DESC;

-- (4) For context: the selective-enrollment "escape hatches" and their SAT,
--     vs the neighborhood-school SAT range tracts are actually assigned.
SELECT
  'selective_enrollment' AS bucket, count(*) n,
  round(avg(sat_g11)) avg_sat, min(sat_g11) min_sat, max(sat_g11) max_sat
FROM schools WHERE is_hs AND school_type='Selective enrollment' AND sat_g11 IS NOT NULL
UNION ALL
SELECT 'assigned_neighborhood_default', count(DISTINCT assigned_school_id),
  round(avg(assigned_sat)), min(assigned_sat), max(assigned_sat)
FROM tract_assignment WHERE assigned_sat IS NOT NULL;
