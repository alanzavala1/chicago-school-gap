-- Export analysis to GeoJSON FeatureCollections for the static frontend.
-- Run each \copy to a file (see 09_export.sh). All variables travel with the tract
-- layer so the map can explore ALL of them (income, race, poverty, default quality,
-- selective access) — the honesty check governs wording, not what the tool exposes.

-- 1) TRACT layer — the 791 Chicago tracts with a default assignment, full metrics.
-- Includes a 0..1 "distress" score = mean of normalized (worse=higher) assigned-school
-- SAT and nearest-selective SAT, computed over the same 791 tracts. Drives the shading.
CREATE OR REPLACE VIEW tracts_geojson_v AS
SELECT json_build_object(
  'type','FeatureCollection',
  'features', COALESCE(json_agg(f), '[]'::json)
)
FROM (
  SELECT json_build_object(
    'type','Feature',
    'geometry', ST_AsGeoJSON(t.geom, 6)::json,
    'properties', json_build_object(
      'geoid', tf.geoid,
      'community_area', tf.community_area,
      'median_hh_income', round(tf.median_hh_income),
      'pct_black', round((tf.pct_black*100)::numeric,1),
      'pct_hispanic', round((tf.pct_hispanic*100)::numeric,1),
      'pct_white', round((tf.pct_white_nh*100)::numeric,1),
      'poverty_rate', round((tf.poverty_rate*100)::numeric,1),
      'assigned_school', tf.assigned_school,
      'assigned_sat', tf.assigned_sat,
      'assigned_attendance', tf.assigned_attendance,
      'assigned_truancy', tf.assigned_truancy,
      'assigned_grad', round(td.assigned_grad,1),
      'assigned_college', round(td.assigned_college,1),
      'assigned_ontrack', round(td.assigned_ontrack,1),
      'nearest_selective_mi', tf.nearest_selective_mi,
      'sat_of_nearest_selective', tf.sat_of_nearest_selective,
      'miles_to_nearest_elite', tf.miles_to_nearest_elite,
      'n_selective_within_3mi', tf.n_selective_within_3mi,
      -- real routed access (16_routed_access.sql): driving assumes a car;
      -- transit (CTA walk+bus+rail) is the car-free reality. Straight-line
      -- miles above stay as a transparent fallback/comparison.
      'drive_min_to_nearest_elite', tr.drive_min_to_nearest_elite,
      'transit_min_to_nearest_elite', tr.transit_min_to_nearest_elite,
      'n_selective_within_30min_transit', tr.n_selective_within_30min_transit,
      -- the closest selective (one school) + drive/CTA time to it; matches the map routes
      'closest_selective', tr.closest_selective,
      'closest_selective_mi', tr.closest_mi,
      'closest_selective_sat', tr.closest_sat,
      'closest_selective_drive_min', tr.closest_drive_min,
      'closest_selective_transit_min', tr.closest_transit_min,
      'combined_status', tc.combined_status,
      -- composite distress (11_distress.sql) + its two halves, for shading + the panel
      'distress', td.distress,
      'distress_rank', td.distress_rank,
      'national_gap', td.national_gap,
      'default_index', td.default_index,
      'access_index', td.access_index
    )
  ) AS f
  FROM tract_full tf
  JOIN tracts t ON t.geoid = tf.geoid
  LEFT JOIN tract_combined tc ON tc.geoid = tf.geoid
  LEFT JOIN tract_distress td ON td.geoid = tf.geoid
  LEFT JOIN tract_routed tr ON tr.geoid = tf.geoid
  WHERE tf.assigned_sat IS NOT NULL
) sub;

-- 2) SCHOOLS layer — all 170 high schools as points (pins).
CREATE OR REPLACE VIEW schools_geojson_v AS
SELECT json_build_object('type','FeatureCollection','features', COALESCE(json_agg(f),'[]'::json))
FROM (
  SELECT json_build_object(
    'type','Feature',
    'geometry', ST_AsGeoJSON(s.geom,6)::json,
    'properties', json_build_object(
      'school_id', s.school_id, 'name', s.short_name, 'long_name', s.long_name,
      'type', s.school_type, 'is_selective', (s.school_type='Selective enrollment'),
      'address', s.address,
      'community_area', (SELECT ca.name FROM community_areas ca
                         WHERE ST_Contains(ca.geom, s.geom) LIMIT 1),
      'sat_g11', s.sat_g11, 'attendance', s.attendance_pct, 'truancy', s.truancy_pct,
      'grad_4yr', s.grad_4yr, 'college_enroll', s.college_enroll, 'freshman_ontrack', s.freshman_ontrack,
      'enrollment', d.total, 'pct_low_income', round((d.pct_low_income*100)::numeric,1),
      'pct_black', round((100.0*d.black/NULLIF(d.total,0))::numeric,1),
      'pct_hispanic', round((100.0*d.hispanic/NULLIF(d.total,0))::numeric,1),
      'pct_white', round((100.0*d.white/NULLIF(d.total,0))::numeric,1)
    )
  ) AS f
  FROM schools s LEFT JOIN school_demographics d ON d.school_id = s.school_id
  WHERE s.is_hs
) sub;

-- 3) ASSIGNMENT ZONES — the 49 neighborhood-HS attendance boundaries.
CREATE OR REPLACE VIEW zones_geojson_v AS
SELECT json_build_object('type','FeatureCollection','features', COALESCE(json_agg(f),'[]'::json))
FROM (
  SELECT json_build_object(
    'type','Feature',
    'geometry', ST_AsGeoJSON(b.geom,6)::json,
    'properties', json_build_object(
      'school_id', b.school_id, 'school_name', b.school_name, 'sat_g11', s.sat_g11)
  ) AS f
  FROM attendance_boundaries b LEFT JOIN schools s ON s.school_id = b.school_id
) sub;

-- 6) DISTRESS POINTS — one point per assigned tract (its internal point) carrying a
-- 0..1 "problem" score = how weak its assigned school AND nearest selective are.
-- Feeds the red heat layer (bright = worst). Good areas score ~0 and stay dark.
CREATE OR REPLACE VIEW distress_points_geojson_v AS
WITH base AS (
  SELECT t.geoid, t.intptlon, t.intptlat, tf.assigned_sat, tf.sat_of_nearest_selective
  FROM tract_full tf JOIN tracts t ON t.geoid = tf.geoid
  WHERE tf.assigned_sat IS NOT NULL AND tf.sat_of_nearest_selective IS NOT NULL
),
stats AS (
  SELECT min(assigned_sat) amin, max(assigned_sat) amax,
         min(sat_of_nearest_selective) smin, max(sat_of_nearest_selective) smax FROM base
),
scored AS (
  SELECT b.intptlon, b.intptlat,
    ( (s.amax - b.assigned_sat) / NULLIF(s.amax - s.amin, 0)
    + (s.smax - b.sat_of_nearest_selective) / NULLIF(s.smax - s.smin, 0) ) / 2.0 AS distress
  FROM base b CROSS JOIN stats s
)
SELECT json_build_object('type','FeatureCollection','features', COALESCE(json_agg(f),'[]'::json))
FROM (
  SELECT json_build_object('type','Feature',
    'geometry', json_build_object('type','Point',
      'coordinates', json_build_array(round(intptlon::numeric,5), round(intptlat::numeric,5))),
    'properties', json_build_object('distress', round(distress::numeric,3))
  ) AS f FROM scored
) sub;

-- 5) ACCESS TERRITORIES — Voronoi of selective schools, colored by SAT (10_territories.sql).
CREATE OR REPLACE VIEW territories_geojson_v AS
SELECT json_build_object('type','FeatureCollection','features', COALESCE(json_agg(f),'[]'::json))
FROM (
  SELECT json_build_object(
    'type','Feature',
    'geometry', ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.0003), 6)::json,
    'properties', json_build_object('school', short_name, 'sat_g11', sat_g11)
  ) AS f
  FROM selective_territories
) sub;

-- 4) CITY BOUNDARY — Chicago / CPS district outline = the 77 community areas dissolved.
CREATE OR REPLACE VIEW city_boundary_geojson_v AS
SELECT json_build_object(
  'type','FeatureCollection',
  'features', json_build_array(json_build_object(
    'type','Feature',
    'properties', json_build_object('name','Chicago / CPS district'),
    'geometry', ST_AsGeoJSON(ST_SimplifyPreserveTopology(ST_Union(geom), 0.0002), 6)::json
  ))
)
FROM community_areas;

-- 7) COMMUNITY AREAS - one polygon per Chicago community area.
-- The frontend joins community_groups.json onto this layer for the default
-- cluster map, so the visual unit is a community area rather than individual tracts.
CREATE OR REPLACE VIEW community_areas_geojson_v AS
SELECT json_build_object('type','FeatureCollection','features', COALESCE(json_agg(f),'[]'::json))
FROM (
  SELECT json_build_object(
    'type','Feature',
    'geometry', ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.0002), 6)::json,
    'properties', json_build_object('name', name, 'area_num', area_num)
  ) AS f
  FROM community_areas
  ORDER BY name
) sub;
