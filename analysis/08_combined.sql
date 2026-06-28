-- =====================================================================
-- 08_combined.sql — Combined-status classification (TIE-SAFE & DETERMINISTIC)
--
-- Crosses each assigned tract's default-school quality (assigned_sat) with the
-- quality of the nearest selective school (sat_of_nearest_selective) into thirds,
-- then labels the corners.
--
-- WHY NOT ntile(): the school-level inputs are highly DISCRETE — 45 distinct
-- assigned-school SATs and only 11 distinct nearest-selective SATs (81 tracts share
-- one value, 119 share another). ntile() forces equal-sized groups, so it splits
-- identical values across different tiers, and which side a tied tract lands on
-- depends on row order — making the result arbitrary AND non-deterministic between
-- rebuilds (this is what drifted the published counts).
--
-- FIX: assign tiers by VALUE against fixed percentile cutpoints. Identical inputs
-- therefore always get the same tier, and reruns are byte-identical. The honest
-- cost is UNEQUAL group sizes (a real consequence of the discreteness). The robust,
-- reproducible result is the DEMOGRAPHIC SKEW of the corners — not the exact counts.
-- =====================================================================

DROP TABLE IF EXISTS tract_combined CASCADE;
CREATE TABLE tract_combined AS
WITH base AS (
  SELECT * FROM tract_full
  WHERE assigned_sat IS NOT NULL AND sat_of_nearest_selective IS NOT NULL
),
cut AS (  -- fixed value cutpoints (33rd/67th pctile of each axis)
  SELECT
    percentile_cont(0.3333) WITHIN GROUP (ORDER BY assigned_sat)               AS d33,
    percentile_cont(0.6667) WITHIN GROUP (ORDER BY assigned_sat)               AS d67,
    percentile_cont(0.3333) WITHIN GROUP (ORDER BY sat_of_nearest_selective)   AS a33,
    percentile_cont(0.6667) WITHIN GROUP (ORDER BY sat_of_nearest_selective)   AS a67
  FROM base
),
tiered AS (
  SELECT b.*,
    CASE WHEN b.assigned_sat <= c.d33 THEN 1
         WHEN b.assigned_sat <= c.d67 THEN 2 ELSE 3 END AS default_tier,   -- 1 = weakest default
    CASE WHEN b.sat_of_nearest_selective <= c.a33 THEN 1
         WHEN b.sat_of_nearest_selective <= c.a67 THEN 2 ELSE 3 END AS access_tier -- 1 = weakest access
  FROM base b CROSS JOIN cut c
)
SELECT *,
  CASE
    WHEN default_tier=1 AND access_tier=1 THEN 'double_disadvantage'  -- weak school + weak access
    WHEN default_tier=3 AND access_tier=3 THEN 'double_advantage'     -- strong school + strong access
    WHEN default_tier=1 OR access_tier=1  THEN 'single_disadvantage'
    ELSE 'middle'
  END AS combined_status
FROM tiered;

-- report group sizes + demographic skew (the robust, reproducible result)
SELECT combined_status, count(*) AS n_tracts,
  round(avg(pct_black)*100)    AS avg_pct_black,
  round(avg(pct_white_nh)*100) AS avg_pct_white,
  round(avg(median_hh_income)) AS avg_income
FROM tract_combined GROUP BY combined_status
ORDER BY array_position(ARRAY['double_disadvantage','single_disadvantage','middle','double_advantage'], combined_status);
