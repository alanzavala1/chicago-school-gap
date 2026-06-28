-- =====================================================================
-- CPS tier data gate — RESOLUTION: ACS-income proxy tiers.
--
-- Official CPS selective-enrollment tiers (1-4) are NOT published as a
-- bulk tract dataset (only an address-by-address GoCPS School Locator).
-- The only downloadable tier-by-tract data (Open City open-city/cps-tiers)
-- stops at 2018 and is keyed to 2010-vintage tracts -> stale + vintage
-- mismatch with our 2020 tracts / ACS 2024.
--
-- Decision: approximate tiers with ACS median household income quartiles on
-- the SAME 2020 tracts. CPS's real index is 6 socioeconomic factors (5 of
-- them ACS-derived: income, single-parent share, language, homeownership,
-- adult education) + 1 school-performance term; income is the dominant axis.
-- This proxy is transparent, vintage-consistent, and clearly labelled NOT the
-- official tier. Used only for descriptive access/sorting (never admission odds).
-- Phase-2 upgrade path: pull B15003/B25003/B11003/B16004 from Census Reporter
-- (same keyless route) to build a closer multi-variable proxy index.
--
-- Tier 1 = lowest-income quartile (most disadvantaged) ... Tier 4 = highest.
-- =====================================================================

DROP TABLE IF EXISTS tract_proxy_tier CASCADE;
CREATE TABLE tract_proxy_tier AS
SELECT
  t.geoid,
  i.median_hh_income,
  ntile(4) OVER (ORDER BY i.median_hh_income) AS proxy_tier   -- 1=poorest .. 4=richest
FROM tracts t
JOIN acs_income i ON i.geoid = t.geoid
-- restrict to Chicago tracts (those that fall within a neighborhood-HS boundary,
-- i.e. the city's residential coverage) so quartiles reflect Chicago, not all Cook.
WHERE EXISTS (
  SELECT 1 FROM attendance_boundaries b
  WHERE ST_Contains(b.geom, ST_SetSRID(ST_MakePoint(t.intptlon, t.intptlat), 4326))
)
AND i.median_hh_income IS NOT NULL;

-- tier bands (sanity: monotonic income ranges)
SELECT proxy_tier, count(*) n,
       round(min(median_hh_income)) inc_min,
       round(max(median_hh_income)) inc_max,
       round(avg(median_hh_income)) inc_avg
FROM tract_proxy_tier GROUP BY proxy_tier ORDER BY proxy_tier;

-- sanity: Brighton Park (Kelly HS area) should land in a low tier
SELECT pt.proxy_tier, round(pt.median_hh_income) income, ta.assigned_school
FROM tract_proxy_tier pt
JOIN tracts t ON t.geoid = pt.geoid
JOIN tract_assignment ta ON ta.geoid = pt.geoid
WHERE ST_Contains(
        ST_MakeEnvelope(-87.73, 41.805, -87.685, 41.835, 4326),
        ST_SetSRID(ST_MakePoint(t.intptlon, t.intptlat), 4326))
ORDER BY pt.proxy_tier;
