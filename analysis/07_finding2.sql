-- =====================================================================
-- Finding 2 — Selective-enrollment access & representation.
-- Selective enrollment is the main route to a high-quality CPS high school
-- that sits outside the neighborhood-assignment system. Two questions:
--   (A) ACCESS: how reachable are selective schools from each neighborhood?
--   (B) REPRESENTATION: do selective student bodies reflect the district, or
--       skew white/higher-income despite the tier system?
-- Descriptive only: access & representation, NOT admission odds by neighborhood.
-- =====================================================================

-- The selective set (11 schools with SAT; all have geom + demographics).
DROP VIEW IF EXISTS selective_schools CASCADE;
CREATE VIEW selective_schools AS
SELECT s.school_id, s.short_name, s.sat_g11, s.geom,
       d.total, d.low_income, d.pct_low_income, d.black, d.hispanic, d.white, d.asian
FROM schools s LEFT JOIN school_demographics d ON d.school_id = s.school_id
WHERE s.is_hs AND s.school_type = 'Selective enrollment' AND s.sat_g11 IS NOT NULL;

SELECT count(*) AS n_selective, count(total) AS with_demographics FROM selective_schools;

-- ---------------------------------------------------------------------
-- (B) REPRESENTATION — enrollment-weighted composition (sum counts, not avg
-- of percentages: the brief's aggregation-honesty point). Selective vs all CPS HS.
-- ---------------------------------------------------------------------
WITH dist AS (  -- all CPS high schools with demographics = the district student body
  SELECT sum(d.total) tot, sum(d.low_income) li, sum(d.black) bl,
         sum(d.hispanic) hi, sum(d.white) wh
  FROM schools s JOIN school_demographics d ON d.school_id = s.school_id
  WHERE s.is_hs AND d.total > 0
), sel AS (
  SELECT sum(total) tot, sum(low_income) li, sum(black) bl, sum(hispanic) hi, sum(white) wh
  FROM selective_schools
)
SELECT g.grp,
  round(100.0*g.li/g.tot,1)  AS pct_low_income,
  round(100.0*g.bl/g.tot,1)  AS pct_black,
  round(100.0*g.hi/g.tot,1)  AS pct_hispanic,
  round(100.0*g.wh/g.tot,1)  AS pct_white
FROM (
  SELECT 'all_cps_hs' grp, tot, li, bl, hi, wh FROM dist
  UNION ALL SELECT 'selective_only', tot, li, bl, hi, wh FROM sel
) g ORDER BY g.grp DESC;

-- Representation ratios (selective % / district %): <1 = under-represented.
WITH dist AS (
  SELECT sum(d.total) tot, sum(d.low_income) li, sum(d.black) bl, sum(d.hispanic) hi, sum(d.white) wh
  FROM schools s JOIN school_demographics d ON d.school_id = s.school_id WHERE s.is_hs AND d.total>0
), sel AS (
  SELECT sum(total) tot, sum(low_income) li, sum(black) bl, sum(hispanic) hi, sum(white) wh FROM selective_schools
)
SELECT
  round((sel.li/sel.tot)/(dist.li/dist.tot),2) AS rep_ratio_low_income,
  round((sel.bl/sel.tot)/(dist.bl/dist.tot),2) AS rep_ratio_black,
  round((sel.hi/sel.tot)/(dist.hi/dist.tot),2) AS rep_ratio_hispanic,
  round((sel.wh/sel.tot)/(dist.wh/dist.tot),2) AS rep_ratio_white
FROM dist, sel;

-- ---------------------------------------------------------------------
-- (A) ACCESS — per-tract proximity to selective schools (geography = real meters).
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS tract_access CASCADE;
CREATE TABLE tract_access AS
WITH pt AS (
  SELECT geoid, ST_SetSRID(ST_MakePoint(intptlon, intptlat),4326)::geography AS g
  FROM tracts
),
sel AS (  -- selective schools; "elite" = top-5 by SAT (all >=1250, a 145-pt break above #6)
  SELECT school_id, sat_g11, geom::geography AS g, (sat_g11 >= 1250) AS is_elite
  FROM schools WHERE is_hs AND school_type='Selective enrollment' AND sat_g11 IS NOT NULL
)
SELECT
  pt.geoid,
  round((MIN(ST_Distance(pt.g, sel.g))/1609.34)::numeric,2) AS nearest_selective_mi,
  count(*) FILTER (WHERE ST_DWithin(pt.g, sel.g, 3*1609.34)) AS n_selective_within_3mi,
  count(*) FILTER (WHERE ST_DWithin(pt.g, sel.g, 5*1609.34)) AS n_selective_within_5mi,
  -- quality-aware access: SAT of the geographically nearest selective, and distance to an elite one
  (array_agg(sel.sat_g11 ORDER BY ST_Distance(pt.g, sel.g)))[1] AS sat_of_nearest_selective,
  round((MIN(ST_Distance(pt.g, sel.g)) FILTER (WHERE sel.is_elite)/1609.34)::numeric,2) AS miles_to_nearest_elite
FROM pt CROSS JOIN sel
GROUP BY pt.geoid;

-- Access vs neighborhood race: are Black neighborhoods farther from selective schools?
-- Tie access to income/race/poverty/default-quality at tract level.
DROP TABLE IF EXISTS tract_full CASCADE;
CREATE TABLE tract_full AS
SELECT
  t.geoid,
  (SELECT ca.name FROM community_areas ca
   WHERE ST_Contains(ca.geom, ST_SetSRID(ST_MakePoint(t.intptlon, t.intptlat),4326))
   LIMIT 1) AS community_area,
  i.median_hh_income, dem.pct_black, dem.pct_hispanic, dem.pct_white_nh, dem.poverty_rate,
  ta.assigned_school, ta.assigned_school_id, ta.assigned_sat, ta.assigned_attendance, ta.assigned_truancy,
  acc.nearest_selective_mi, acc.n_selective_within_3mi, acc.n_selective_within_5mi,
  acc.sat_of_nearest_selective, acc.miles_to_nearest_elite
FROM tracts t
LEFT JOIN acs_income i        ON i.geoid = t.geoid
LEFT JOIN acs_demographics dem ON dem.geoid = t.geoid
LEFT JOIN tract_assignment ta ON ta.geoid = t.geoid
LEFT JOIN tract_access acc    ON acc.geoid = t.geoid;

-- Correlations: does access track race / income / default quality?
SELECT
  round(corr(nearest_selective_mi, pct_black)::numeric,3)        AS r_dist_pctblack,
  round(corr(nearest_selective_mi, median_hh_income)::numeric,3) AS r_dist_income,
  round(corr(nearest_selective_mi, assigned_sat)::numeric,3)     AS r_dist_defaultSAT,
  round(corr(n_selective_within_3mi, pct_black)::numeric,3)      AS r_count3_pctblack
FROM tract_full WHERE assigned_sat IS NOT NULL;
