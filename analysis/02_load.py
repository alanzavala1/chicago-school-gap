"""
Phase 1 loader: turn the four raw files into a single idempotent .sql script that
builds the PostGIS tables. Run the emitted SQL with:

    docker exec -i chicago-postgis psql -U postgres -d school_gap -v ON_ERROR_STOP=1 -f - < analysis/load.sql

We generate SQL (rather than use a Python DB driver) so the pipeline has zero
binary-wheel dependencies and is trivially reproducible / inspectable.

Tables built (all geometry SRID 4326 / WGS84):
  schools                all 649 CPS schools; point geom from lat/long; SAT 0 -> NULL
  attendance_boundaries  49 neighborhood-HS assignment polygons (key: school_id)
  tracts                 1332 Cook County 2020 census tract polygons (key: geoid)
  acs_income             1332 ACS 2024 5-yr median HH income rows (key: geoid)
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.normpath(os.path.join(HERE, "..", "data", "raw"))
OUT_SQL = os.path.join(HERE, "load.sql")


def q(s):
    """SQL string literal, single-quote escaped; None -> NULL."""
    if s is None:
        return "NULL"
    return "'" + str(s).replace("'", "''") + "'"


def num(s, zero_is_null=False):
    """Numeric literal or NULL. Optionally treat 0 as NULL (SAT non-testers)."""
    if s is None or s == "":
        return "NULL"
    try:
        v = float(s)
    except (TypeError, ValueError):
        return "NULL"
    if zero_is_null and v == 0:
        return "NULL"
    return repr(v)


def geom_from_geojson(geom):
    """ST_GeomFromGeoJSON(...) forced to SRID 4326, multi-promoted for polygons."""
    j = json.dumps(geom).replace("'", "''")
    return f"ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON('{j}'),4326))"


def load_schools(sql):
    pr = json.load(open(os.path.join(RAW, "progress_sy2425.json"), encoding="utf-8"))
    sql.append("DROP TABLE IF EXISTS schools CASCADE;")
    sql.append("""CREATE TABLE schools (
  school_id text PRIMARY KEY,
  short_name text,
  long_name text,
  school_type text,
  primary_category text,
  sat_g11 numeric,           -- SAT grade 11 school score; 0 nulled (non-testers)
  attendance_pct numeric,    -- REAL per-school attendance, current yr (student_attendance_year_2)
  attendance_prior numeric,  -- prior-year attendance (student_attendance_year_1)
  truancy_pct numeric,       -- chronic truancy %
  progress_grad text,        -- progress toward graduation (rating text)
  address text,              -- street address
  grad_4yr numeric,          -- 4-year graduation rate (graduation_4_year_school)
  college_enroll numeric,    -- % enrolling in college (college_enrollment_school)
  freshman_ontrack numeric,  -- Freshman OnTrack % (freshmen_on_track_school)
  is_hs boolean,
  lat double precision,
  lon double precision,
  geom geometry(Point,4326)
);""")
    rows = 0
    for r in pr:
        sid = r.get("school_id")
        lat, lon = r.get("school_latitude"), r.get("school_longitude")
        geom = (f"ST_SetSRID(ST_MakePoint({num(lon)},{num(lat)}),4326)"
                if lat not in (None, "") and lon not in (None, "") else "NULL")
        is_hs = "true" if r.get("primary_category") == "HS" else "false"
        # NOTE: student_attendance_avg_pct is a broken placeholder (constant 88.3 =
        # district figure). Real per-school attendance lives in the _year_N columns.
        # Cross-referencing the SY2324 file confirms _year_2 is the most recent year
        # (SY2425) and _year_1 the prior year. So attendance_pct = student_attendance_year_2.
        sql.append(
            "INSERT INTO schools VALUES ("
            f"{q(sid)},{q(r.get('short_name'))},{q(r.get('long_name'))},"
            f"{q(r.get('school_type'))},{q(r.get('primary_category'))},"
            f"{num(r.get('sat_grade_11_score_school'), zero_is_null=True)},"
            f"{num(r.get('student_attendance_year_2'))},{num(r.get('student_attendance_year_1'))},"
            f"{num(r.get('chronic_truancy_pct'))},{q(r.get('progress_toward_graduation'))},"
            f"{q(r.get('address'))},{num(r.get('graduation_4_year_school'))},"
            f"{num(r.get('college_enrollment_school'))},{num(r.get('freshmen_on_track_school'))},"
            f"{is_hs},{num(lat)},{num(lon)},{geom});")
        rows += 1
    sql.append("CREATE INDEX schools_geom_gix ON schools USING GIST (geom);")
    return rows


def load_attendance(sql):
    fc = json.load(open(os.path.join(RAW, "hs_attendance_boundaries.geojson"), encoding="utf-8"))
    sql.append("DROP TABLE IF EXISTS attendance_boundaries CASCADE;")
    sql.append("""CREATE TABLE attendance_boundaries (
  gid serial PRIMARY KEY,
  school_id text,
  school_name text,
  grade_cat text,
  boundary_grades text,
  geom geometry(MultiPolygon,4326)
);""")
    rows = 0
    for f in fc["features"]:
        p = f["properties"]
        if not f.get("geometry"):
            continue
        sql.append(
            "INSERT INTO attendance_boundaries (school_id,school_name,grade_cat,boundary_grades,geom) VALUES ("
            f"{q(p.get('school_id'))},{q(p.get('school_nam'))},{q(p.get('grade_cat'))},"
            f"{q(p.get('boundarygr'))},{geom_from_geojson(f['geometry'])});")
        rows += 1
    sql.append("CREATE INDEX ab_geom_gix ON attendance_boundaries USING GIST (geom);")
    return rows


def load_tracts(sql):
    fc = json.load(open(os.path.join(RAW, "tiger_tracts_2020.geojson"), encoding="utf-8"))
    sql.append("DROP TABLE IF EXISTS tracts CASCADE;")
    sql.append("""CREATE TABLE tracts (
  geoid text PRIMARY KEY,
  basename text,
  intptlat double precision,
  intptlon double precision,
  geom geometry(MultiPolygon,4326)
);""")
    rows = 0
    for f in fc["features"]:
        p = f["properties"]
        if not f.get("geometry"):
            continue
        sql.append(
            "INSERT INTO tracts (geoid,basename,intptlat,intptlon,geom) VALUES ("
            f"{q(p.get('GEOID'))},{q(p.get('BASENAME'))},{num(p.get('INTPTLAT'))},"
            f"{num(p.get('INTPTLON'))},{geom_from_geojson(f['geometry'])});")
        rows += 1
    sql.append("CREATE INDEX tracts_geom_gix ON tracts USING GIST (geom);")
    return rows


def load_acs(sql):
    d = json.load(open(os.path.join(RAW, "acs_b19013_cook.json"), encoding="utf-8"))
    sql.append("DROP TABLE IF EXISTS acs_income CASCADE;")
    sql.append(f"""CREATE TABLE acs_income (
  geoid text PRIMARY KEY,
  name text,
  median_hh_income numeric,   -- ACS B19013_001E; release: {d.get('release')}
  moe numeric
);""")
    rows = 0
    for r in d["rows"]:
        sql.append(
            "INSERT INTO acs_income VALUES ("
            f"{q(r.get('geoid'))},{q(r.get('name'))},"
            f"{num(r.get('median_hh_income'))},{num(r.get('moe'))});")
        rows += 1
    return rows


def load_acs_demographics(sql):
    d = json.load(open(os.path.join(RAW, "acs_demographics_cook.json"), encoding="utf-8"))
    sql.append("DROP TABLE IF EXISTS acs_demographics CASCADE;")
    sql.append("""CREATE TABLE acs_demographics (
  geoid text PRIMARY KEY,
  pop_total numeric,
  pct_white_nh numeric,
  pct_black numeric,
  pct_hispanic numeric,
  poverty_rate numeric
);""")
    rows = 0
    for r in d["rows"]:
        sql.append(
            "INSERT INTO acs_demographics VALUES ("
            f"{q(r.get('geoid'))},{num(r.get('pop_total'))},{num(r.get('pct_white_nh'))},"
            f"{num(r.get('pct_black'))},{num(r.get('pct_hispanic'))},{num(r.get('poverty_rate'))});")
        rows += 1
    return rows


def load_school_demographics(sql):
    d = json.load(open(os.path.join(RAW, "school_demographics_sy2425.json"), encoding="utf-8"))
    sql.append("DROP TABLE IF EXISTS school_demographics CASCADE;")
    sql.append("""CREATE TABLE school_demographics (
  school_id text PRIMARY KEY,
  total numeric,
  low_income numeric,
  pct_low_income numeric,
  black numeric, hispanic numeric, white numeric, asian numeric
);""")
    rows = 0
    for r in d:
        tot = r.get("student_count_total")
        li = r.get("student_count_low_income")
        try:
            pct = float(li) / float(tot) if tot and float(tot) > 0 else None
        except (TypeError, ValueError):
            pct = None
        sql.append(
            "INSERT INTO school_demographics VALUES ("
            f"{q(r.get('school_id'))},{num(tot)},{num(li)},{num(pct)},"
            f"{num(r.get('student_count_black'))},{num(r.get('student_count_hispanic'))},"
            f"{num(r.get('student_count_white'))},{num(r.get('student_count_asian'))});")
        rows += 1
    return rows


def load_community_areas(sql):
    fc = json.load(open(os.path.join(RAW, "community_areas.geojson"), encoding="utf-8"))
    sql.append("DROP TABLE IF EXISTS community_areas CASCADE;")
    sql.append("""CREATE TABLE community_areas (
  gid serial PRIMARY KEY,
  name text,
  area_num text,
  geom geometry(MultiPolygon,4326)
);""")
    rows = 0
    for f in fc["features"]:
        p = f["properties"]
        if not f.get("geometry"):
            continue
        # title-case the ALL-CAPS community names for display
        name = (p.get("community") or "").title()
        sql.append(
            "INSERT INTO community_areas (name,area_num,geom) VALUES ("
            f"{q(name)},{q(p.get('area_numbe'))},{geom_from_geojson(f['geometry'])});")
        rows += 1
    sql.append("CREATE INDEX ca_geom_gix ON community_areas USING GIST (geom);")
    return rows


if __name__ == "__main__":
    sql = ["BEGIN;", "SET client_min_messages TO WARNING;"]
    n_sch = load_schools(sql)
    n_ab = load_attendance(sql)
    n_tr = load_tracts(sql)
    n_acs = load_acs(sql)
    n_acsd = load_acs_demographics(sql)
    n_schd = load_school_demographics(sql)
    n_ca = load_community_areas(sql)
    sql.append("COMMIT;")
    with open(OUT_SQL, "w", encoding="utf-8") as f:
        f.write("\n".join(sql))
    print(f"wrote {OUT_SQL}")
    print(f"  schools={n_sch}  attendance_boundaries={n_ab}  tracts={n_tr}  acs_income={n_acs}"
          f"  acs_demographics={n_acsd}  school_demographics={n_schd}  community_areas={n_ca}")
