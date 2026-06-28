-- =====================================================================
-- 12_community_metrics.sql — community-area metrics for clustering.
--
-- This is the aggregation layer for the map's community-area typology.
-- It keeps demographics available for context, but the downstream clustering
-- script uses only school outcomes, local school supply, and access measures.
-- =====================================================================

DROP VIEW IF EXISTS community_metrics_json_v;
DROP TABLE IF EXISTS community_metrics CASCADE;

CREATE TABLE community_metrics AS
WITH ca AS (
  SELECT name, geom FROM community_areas
),
tract_metrics AS (
  SELECT
    tf.community_area,
    count(*) AS tract_count,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY tf.median_hh_income) AS median_hh_income,
    avg(tf.poverty_rate * 100.0) AS poverty_rate,
    avg(tf.pct_black * 100.0) AS pct_black,
    avg(tf.pct_hispanic * 100.0) AS pct_hispanic,
    avg(tf.pct_white_nh * 100.0) AS pct_white,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY tf.assigned_sat) AS assigned_sat,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY td.assigned_grad) AS assigned_grad,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY td.assigned_college) AS assigned_college,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY td.assigned_ontrack) AS assigned_ontrack,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY tf.assigned_attendance) AS assigned_attendance,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY tf.assigned_truancy) AS assigned_truancy,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY tf.nearest_selective_mi) AS nearest_selective_mi,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY tf.sat_of_nearest_selective) AS sat_of_nearest_selective,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY tf.miles_to_nearest_elite) AS miles_to_nearest_elite,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY tf.n_selective_within_3mi) AS n_selective_within_3mi,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY td.default_index) AS assigned_default_index,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY td.access_index) AS selective_access_index,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY td.national_gap) AS national_gap
  FROM tract_full tf
  LEFT JOIN tract_distress td ON td.geoid = tf.geoid
  WHERE tf.community_area IS NOT NULL AND tf.assigned_sat IS NOT NULL
  GROUP BY tf.community_area
),
combined_status_counts AS (
  SELECT
    community_area,
    jsonb_object_agg(combined_status, status_count ORDER BY combined_status) AS combined_status_counts
  FROM (
    SELECT tf.community_area, tc.combined_status, count(*) AS status_count
    FROM tract_full tf
    JOIN tract_combined tc ON tc.geoid = tf.geoid
    WHERE tf.community_area IS NOT NULL AND tf.assigned_sat IS NOT NULL AND tc.combined_status IS NOT NULL
    GROUP BY tf.community_area, tc.combined_status
  ) counts
  GROUP BY community_area
),
local_schools AS (
  SELECT
    ca.name AS community_area,
    s.school_id,
    s.school_type,
    s.sat_g11,
    s.grad_4yr,
    s.college_enroll,
    s.freshman_ontrack,
    s.attendance_pct,
    s.truancy_pct
  FROM schools s
  JOIN ca ON ST_Contains(ca.geom, s.geom)
  WHERE s.is_hs
),
school_bounds AS (
  SELECT
    min(sat_g11) sat0, max(sat_g11) sat1,
    min(grad_4yr) grad0, max(grad_4yr) grad1,
    min(college_enroll) coll0, max(college_enroll) coll1,
    min(freshman_ontrack) otk0, max(freshman_ontrack) otk1,
    min(attendance_pct) att0, max(attendance_pct) att1,
    min(truancy_pct) tru0, max(truancy_pct) tru1
  FROM schools
  WHERE is_hs
),
school_indices AS (
  SELECT
    ls.*,
    (
      coalesce((sb.sat1 - ls.sat_g11) / NULLIF(sb.sat1 - sb.sat0, 0), 0) +
      coalesce((sb.grad1 - ls.grad_4yr) / NULLIF(sb.grad1 - sb.grad0, 0), 0) +
      coalesce((sb.coll1 - ls.college_enroll) / NULLIF(sb.coll1 - sb.coll0, 0), 0) +
      coalesce((sb.otk1 - ls.freshman_ontrack) / NULLIF(sb.otk1 - sb.otk0, 0), 0) +
      coalesce((sb.att1 - ls.attendance_pct) / NULLIF(sb.att1 - sb.att0, 0), 0) +
      coalesce((ls.truancy_pct - sb.tru0) / NULLIF(sb.tru1 - sb.tru0, 0), 0)
    ) / NULLIF(
      (ls.sat_g11 IS NOT NULL)::int +
      (ls.grad_4yr IS NOT NULL)::int +
      (ls.college_enroll IS NOT NULL)::int +
      (ls.freshman_ontrack IS NOT NULL)::int +
      (ls.attendance_pct IS NOT NULL)::int +
      (ls.truancy_pct IS NOT NULL)::int,
      0
    ) AS school_weakness_index
  FROM local_schools ls
  CROSS JOIN school_bounds sb
),
local_metrics AS (
  SELECT
    community_area,
    count(*) AS local_hs_count,
    count(*) FILTER (WHERE sat_g11 IS NOT NULL) AS local_testing_hs_count,
    count(*) FILTER (WHERE school_type <> 'Selective enrollment') AS local_nonselective_hs_count,
    count(*) FILTER (WHERE school_type <> 'Selective enrollment' AND sat_g11 IS NOT NULL) AS local_nonselective_testing_hs_count,
    count(*) FILTER (WHERE school_type = 'Neighborhood') AS local_neighborhood_hs_count,
    count(*) FILTER (WHERE school_type = 'Selective enrollment') AS local_selective_hs_count,
    avg(sat_g11) AS local_sat,
    avg(grad_4yr) AS local_grad,
    avg(college_enroll) AS local_college,
    avg(freshman_ontrack) AS local_ontrack,
    avg(attendance_pct) AS local_attendance,
    avg(truancy_pct) AS local_truancy,
    avg(school_weakness_index) AS local_school_index,
    avg(school_weakness_index) FILTER (WHERE school_type <> 'Selective enrollment') AS local_nonselective_school_index
  FROM school_indices
  GROUP BY community_area
),
tract_points AS (
  SELECT
    tf.community_area,
    ST_SetSRID(ST_MakePoint(t.intptlon, t.intptlat), 4326)::geography AS g
  FROM tract_full tf
  JOIN tracts t ON t.geoid = tf.geoid
  WHERE tf.community_area IS NOT NULL AND tf.assigned_sat IS NOT NULL
),
strong_schools AS (
  SELECT geom::geography AS g
  FROM schools
  WHERE is_hs AND sat_g11 >= 1010
),
strong_nonselective_schools AS (
  SELECT geom::geography AS g
  FROM schools
  WHERE is_hs AND sat_g11 >= 1010 AND school_type <> 'Selective enrollment'
),
strong_access AS (
  SELECT
    per_tract.community_area,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY nearest_strong_mi) AS nearest_strong_mi
  FROM (
    SELECT
      tp.community_area,
      min(ST_Distance(tp.g, ss.g) / 1609.34) AS nearest_strong_mi
    FROM tract_points tp
    CROSS JOIN strong_schools ss
    GROUP BY tp.community_area, tp.g
  ) per_tract
  GROUP BY per_tract.community_area
),
strong_nonselective_access AS (
  SELECT
    per_tract.community_area,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY nearest_strong_nonselective_mi) AS nearest_strong_nonselective_mi
  FROM (
    SELECT
      tp.community_area,
      min(ST_Distance(tp.g, ss.g) / 1609.34) AS nearest_strong_nonselective_mi
    FROM tract_points tp
    CROSS JOIN strong_nonselective_schools ss
    GROUP BY tp.community_area, tp.g
  ) per_tract
  GROUP BY per_tract.community_area
)
SELECT
  ca.name AS community_area,
  tm.tract_count,
  round(tm.median_hh_income::numeric) AS median_hh_income,
  round(tm.poverty_rate::numeric, 1) AS poverty_rate,
  round(tm.pct_black::numeric, 1) AS pct_black,
  round(tm.pct_hispanic::numeric, 1) AS pct_hispanic,
  round(tm.pct_white::numeric, 1) AS pct_white,
  round(tm.assigned_sat::numeric, 1) AS assigned_sat,
  round(tm.assigned_grad::numeric, 1) AS assigned_grad,
  round(tm.assigned_college::numeric, 1) AS assigned_college,
  round(tm.assigned_ontrack::numeric, 1) AS assigned_ontrack,
  round(tm.assigned_attendance::numeric, 1) AS assigned_attendance,
  round(tm.assigned_truancy::numeric, 1) AS assigned_truancy,
  round(tm.nearest_selective_mi::numeric, 2) AS nearest_selective_mi,
  round(tm.sat_of_nearest_selective::numeric, 1) AS sat_of_nearest_selective,
  round(tm.miles_to_nearest_elite::numeric, 2) AS miles_to_nearest_elite,
  round(tm.n_selective_within_3mi::numeric, 1) AS n_selective_within_3mi,
  round(tm.assigned_default_index::numeric, 4) AS assigned_default_index,
  round(tm.selective_access_index::numeric, 4) AS selective_access_index,
  round(tm.national_gap::numeric, 3) AS national_gap,
  coalesce(csc.combined_status_counts, '{}'::jsonb) AS combined_status_counts,
  coalesce(lm.local_hs_count, 0) AS local_hs_count,
  coalesce(lm.local_testing_hs_count, 0) AS local_testing_hs_count,
  coalesce(lm.local_nonselective_hs_count, 0) AS local_nonselective_hs_count,
  coalesce(lm.local_nonselective_testing_hs_count, 0) AS local_nonselective_testing_hs_count,
  coalesce(lm.local_neighborhood_hs_count, 0) AS local_neighborhood_hs_count,
  coalesce(lm.local_selective_hs_count, 0) AS local_selective_hs_count,
  round(lm.local_sat::numeric, 1) AS local_sat,
  round(lm.local_grad::numeric, 1) AS local_grad,
  round(lm.local_college::numeric, 1) AS local_college,
  round(lm.local_ontrack::numeric, 1) AS local_ontrack,
  round(lm.local_attendance::numeric, 1) AS local_attendance,
  round(lm.local_truancy::numeric, 1) AS local_truancy,
  round(lm.local_school_index::numeric, 4) AS local_school_index,
  round(lm.local_nonselective_school_index::numeric, 4) AS local_nonselective_school_index,
  round(sa.nearest_strong_mi::numeric, 2) AS nearest_strong_mi,
  round(snsa.nearest_strong_nonselective_mi::numeric, 2) AS nearest_strong_nonselective_mi
FROM ca
LEFT JOIN tract_metrics tm ON tm.community_area = ca.name
LEFT JOIN combined_status_counts csc ON csc.community_area = ca.name
LEFT JOIN local_metrics lm ON lm.community_area = ca.name
LEFT JOIN strong_access sa ON sa.community_area = ca.name
LEFT JOIN strong_nonselective_access snsa ON snsa.community_area = ca.name
ORDER BY ca.name;

CREATE VIEW community_metrics_json_v AS
SELECT jsonb_pretty(jsonb_build_object(
  'schema_version', 1,
  'source', 'analysis/12_community_metrics.sql',
  'communities', jsonb_agg(to_jsonb(community_metrics) ORDER BY community_area)
)) AS data
FROM community_metrics;

SELECT count(*) AS community_areas,
       sum((local_hs_count > 0)::int) AS with_local_high_school,
       sum((local_hs_count = 0)::int) AS without_local_high_school
FROM community_metrics;
