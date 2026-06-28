-- =====================================================================
-- Stage 16 — Routed access (real driving + CTA transit), per tract.
--
-- Loads the OSRM driving matrix (14_driving_access.py) and the OTP transit
-- matrix (15_transit_access.py) and builds tract_routed: driving + transit
-- analogues of the Finding-2 access fields, alongside the straight-line metrics
-- in tract_full (which stay as a transparent fallback / comparison).
--
-- Two honest access lenses: DRIVING assumes a car (highways equalize, so the gap
-- is moderate); TRANSIT is the reality for car-free families (the gap is far
-- sharper). Descriptive access only — never admission odds.
--
-- Prereq: run_all.sh docker-cp's the two CSVs into the container's /tmp first.
--   docker cp output/driving_times_selective.csv  chicago-postgis:/tmp/
--   docker cp output/transit_times_selective.csv  chicago-postgis:/tmp/
-- Elite threshold matches 07_finding2.sql (selective, SAT >= 1250).
-- =====================================================================

-- raw matrices (one row per tract x selective school) ------------------
DROP TABLE IF EXISTS drive_selective CASCADE;
CREATE TABLE drive_selective (
  geoid text, school_id text, school text, sat_g11 numeric, drive_min numeric, drive_mi numeric
);
COPY drive_selective FROM '/tmp/driving_times_selective.csv' WITH (FORMAT csv, HEADER);

DROP TABLE IF EXISTS transit_selective CASCADE;
CREATE TABLE transit_selective (
  geoid text, school_id text, school text, sat_g11 numeric, transit_min_median numeric
);
COPY transit_selective FROM '/tmp/transit_times_selective.csv' WITH (FORMAT csv, HEADER);

-- per-tract routed summaries -------------------------------------------
DROP TABLE IF EXISTS tract_routed CASCADE;
CREATE TABLE tract_routed AS
WITH d AS (
  SELECT geoid,
    round(min(drive_min), 1)                                        AS drive_min_nearest_selective,
    round(min(drive_min) FILTER (WHERE sat_g11 >= 1250), 1)         AS drive_min_to_nearest_elite,
    count(*) FILTER (WHERE drive_min <= 15)                         AS n_selective_within_15min_drive,
    (array_agg(sat_g11 ORDER BY drive_min))[1]                      AS sat_of_nearest_selective_drive
  FROM drive_selective WHERE drive_min IS NOT NULL GROUP BY geoid
),
tr AS (
  SELECT geoid,
    round(min(transit_min_median), 1)                                   AS transit_min_nearest_selective,
    round(min(transit_min_median) FILTER (WHERE sat_g11 >= 1250), 1)    AS transit_min_to_nearest_elite,
    count(*) FILTER (WHERE transit_min_median <= 30)                    AS n_selective_within_30min_transit,
    (array_agg(sat_g11 ORDER BY transit_min_median))[1]                 AS sat_of_nearest_selective_transit
  FROM transit_selective WHERE transit_min_median IS NOT NULL GROUP BY geoid
),
cl AS (  -- the geographically CLOSEST selective (by road distance) + drive time to it.
         -- This is the single intuitive "your nearest selective" used by the map routes
         -- and the panel, so both always refer to the same school.
  SELECT DISTINCT ON (geoid)
    geoid, school AS closest_selective, school_id AS closest_school_id,
    round(drive_min, 1) AS closest_drive_min, round(drive_mi, 2) AS closest_mi, sat_g11 AS closest_sat
  FROM drive_selective WHERE drive_mi IS NOT NULL
  ORDER BY geoid, drive_mi
),
clt AS (  -- CTA time to that SAME closest school (median), so map line == panel number
  SELECT t.geoid, round(t.transit_min_median, 1) AS closest_transit_min
  FROM transit_selective t JOIN cl ON cl.geoid = t.geoid AND cl.closest_school_id = t.school_id
),
keys AS (
  SELECT geoid FROM drive_selective UNION SELECT geoid FROM transit_selective
)
SELECT k.geoid,
  d.drive_min_nearest_selective, d.drive_min_to_nearest_elite,
  d.n_selective_within_15min_drive, d.sat_of_nearest_selective_drive,
  tr.transit_min_nearest_selective, tr.transit_min_to_nearest_elite,
  tr.n_selective_within_30min_transit, tr.sat_of_nearest_selective_transit,
  cl.closest_selective, cl.closest_drive_min, cl.closest_mi, cl.closest_sat,
  clt.closest_transit_min
FROM keys k
LEFT JOIN d  ON d.geoid  = k.geoid
LEFT JOIN tr ON tr.geoid = k.geoid
LEFT JOIN cl ON cl.geoid = k.geoid
LEFT JOIN clt ON clt.geoid = k.geoid;

ALTER TABLE tract_routed ADD PRIMARY KEY (geoid);

-- sanity: coverage + the transit-vs-driving gap to an elite selective ---
SELECT
  count(*)                                                   AS tracts,
  count(drive_min_to_nearest_elite)                          AS with_drive,
  count(transit_min_to_nearest_elite)                        AS with_transit,
  round(avg(drive_min_to_nearest_elite), 1)                  AS avg_drive_to_elite,
  round(avg(transit_min_to_nearest_elite), 1)               AS avg_transit_to_elite,
  round((avg(transit_min_to_nearest_elite)
        / NULLIF(avg(drive_min_to_nearest_elite), 0))::numeric, 2) AS transit_over_drive
FROM tract_routed;
