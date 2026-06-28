-- =====================================================================
-- 10_territories.sql — "Access territories": carve Chicago into regions by
-- which SELECTIVE-ENROLLMENT school is nearest, tagged with that school's SAT.
--
-- A Voronoi tessellation of the 11 selective schools, computed in a planar CRS
-- (EPSG:3435, Illinois State Plane East ftUS) so "nearest" is true ground
-- distance, then clipped to the Chicago / CPS boundary and transformed back to
-- WGS84 for the map. Each cell = the area whose closest selective school is X.
-- Color the map by each cell's SAT and the inequality of access becomes geography:
-- big dim territories where the nearest good school is far, small bright ones up north.
-- =====================================================================

DROP TABLE IF EXISTS selective_territories CASCADE;
CREATE TABLE selective_territories AS
WITH sel AS (
  SELECT school_id, short_name, sat_g11, ST_Transform(geom, 3435) AS g
  FROM schools
  WHERE is_hs AND school_type = 'Selective enrollment' AND sat_g11 IS NOT NULL
),
city AS (
  SELECT ST_Transform(ST_Union(geom), 3435) AS g FROM community_areas
),
vor AS (  -- one polygon per seed point; order not guaranteed -> rejoin spatially
  SELECT (ST_Dump(ST_VoronoiPolygons(ST_Collect(g)))).geom AS cell FROM sel
)
SELECT
  s.school_id,
  s.short_name,
  s.sat_g11,
  ST_Multi(ST_Transform(ST_Intersection(v.cell, c.g), 4326)) AS geom
FROM vor v
JOIN sel s   ON ST_Contains(v.cell, s.g)   -- the cell that contains this school
CROSS JOIN city c;

CREATE INDEX selective_territories_gix ON selective_territories USING GIST (geom);

-- sanity: 11 territories, SAT range, and their relative sizes (sq mi)
SELECT short_name, sat_g11,
  round((ST_Area(geom::geography) / 2589988.11)::numeric, 1) AS sq_mi
FROM selective_territories ORDER BY sat_g11;
