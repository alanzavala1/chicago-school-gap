-- =====================================================================
-- 11_distress.sql — composite neighborhood "distress" score (0 best .. 1 worst).
--
-- Two halves, equally weighted:
--   DEFAULT-SCHOOL quality (what you're assigned): SAT, 4-yr graduation, college
--     enrollment, freshman on-track, attendance, chronic truancy (truancy inverted).
--   SELECTIVE ACCESS: SAT of nearest selective, distance to nearest top selective.
--
-- Each component is min-max normalized across the 791 assigned tracts and oriented so
-- higher = worse. default_index = mean of available default components; access_index =
-- mean of the two access components; distress = mean(default_index, access_index).
-- All school/access — NO demographics, so the score stays non-circular (we then SHOW
-- that it tracks race; it isn't built from it).
-- =====================================================================

DROP TABLE IF EXISTS tract_distress CASCADE;
CREATE TABLE tract_distress AS
WITH comp AS (
  SELECT tf.geoid,
         tf.assigned_sat sat, tf.assigned_attendance att, tf.assigned_truancy tru,
         s.grad_4yr grad, s.college_enroll coll, s.freshman_ontrack otk,
         tf.sat_of_nearest_selective nsel, tf.miles_to_nearest_elite emi
  FROM tract_full tf
  LEFT JOIN schools s ON s.school_id = tf.assigned_school_id
  WHERE tf.assigned_sat IS NOT NULL AND tf.sat_of_nearest_selective IS NOT NULL
),
st AS (
  SELECT min(sat) sat0,max(sat) sat1, min(att) att0,max(att) att1, min(tru) tru0,max(tru) tru1,
         min(grad) g0,max(grad) g1, min(coll) c0,max(coll) c1, min(otk) o0,max(otk) o1,
         min(nsel) n0,max(nsel) n1, min(emi) e0,max(emi) e1
  FROM comp
),
norm AS (  -- normalized, higher = worse
  SELECT c.geoid, c.grad, c.coll, c.otk,
    -- SIGNED national-benchmark gap: mean of (value/benchmark - 1) vs college-ready SAT
    -- (1010), national ACGR graduation (87%), national college enrollment (62%).
    -- >0 = above the bars (green), <0 = below (red), 0 = exactly meets. Access/attendance/
    -- on-track have no clean national analog so they are excluded from this frame.
    ( (c.sat/1010.0 - 1)
    + (c.grad/87.0 - 1)
    + coalesce(c.coll/62.0 - 1, 0) ) / (2 + (c.coll IS NOT NULL)::int) AS nat_gap,
    (st.sat1-c.sat)/(st.sat1-st.sat0) d_sat,
    (st.g1-c.grad)/(st.g1-st.g0)      d_grad,
    (st.c1-c.coll)/(st.c1-st.c0)      d_coll,
    (st.o1-c.otk)/(st.o1-st.o0)       d_otk,
    (st.att1-c.att)/(st.att1-st.att0) d_att,
    (c.tru-st.tru0)/(st.tru1-st.tru0) d_tru,
    (st.n1-c.nsel)/(st.n1-st.n0)      d_nsel,
    (c.emi-st.e0)/(st.e1-st.e0)       d_elite
  FROM comp c CROSS JOIN st
),
idx AS (
  SELECT geoid, grad, coll, otk, nat_gap,
    (coalesce(d_sat,0)+coalesce(d_grad,0)+coalesce(d_coll,0)+coalesce(d_otk,0)+coalesce(d_att,0)+coalesce(d_tru,0))
      / NULLIF((d_sat IS NOT NULL)::int+(d_grad IS NOT NULL)::int+(d_coll IS NOT NULL)::int
              +(d_otk IS NOT NULL)::int+(d_att IS NOT NULL)::int+(d_tru IS NOT NULL)::int, 0) AS def_idx,
    (d_nsel + d_elite) / 2.0 AS acc_idx
  FROM norm
)
SELECT geoid,
  grad AS assigned_grad, coll AS assigned_college, otk AS assigned_ontrack,
  round(def_idx::numeric, 4) AS default_index,
  round(acc_idx::numeric, 4) AS access_index,
  round(nat_gap::numeric, 3) AS national_gap,
  round(((def_idx + acc_idx) / 2.0)::numeric, 3) AS distress,
  -- percentile rank (0 best .. 1 worst): drives the vivid even-contrast shading,
  -- and = "worse than N% of neighborhoods" shown in the panel (same number, consistent).
  round(percent_rank() OVER (ORDER BY (def_idx + acc_idx))::numeric, 3) AS distress_rank
FROM idx;

-- distribution (for the shading color breaks) + sanity spot-checks
SELECT round(min(distress),3) min, round(max(distress),3) max,
  round(percentile_cont(0.25) WITHIN GROUP (ORDER BY distress)::numeric,3) p25,
  round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY distress)::numeric,3) p50,
  round(percentile_cont(0.75) WITHIN GROUP (ORDER BY distress)::numeric,3) p75
FROM tract_distress;
