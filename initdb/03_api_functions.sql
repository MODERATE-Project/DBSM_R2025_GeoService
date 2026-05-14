-- ============================================================
-- DBSM GeoService — RPC Functions for PostgREST
-- Schema v2 (R2025): fid, unique_id, source, area, height,
--   shapefactor, epoch, use, eub_json, osm_json, msb_json + geom
--
-- Column types in v2 tables (from ogr2ogr import):
--   fid        → integer       (declared as bigint → cast required)
--   unique_id  → varchar       (declared as text   → cast required)
--   source     → varchar       (declared as text   → cast required)
--   eub_json   → varchar       (declared as text   → cast required)
--   osm_json   → varchar       (declared as text   → cast required)
--   msb_json   → varchar       (declared as text   → cast required)
--   area, height, shapefactor → double precision   (no cast needed)
--   epoch, use → bigint                            (no cast needed)
-- ============================================================

-- 1. Buildings within a Bounding Box (for map viewers)
-- POST /rpc/buildings_in_bbox
-- Body: {"country_table":"malta","min_lon":14.18,"min_lat":35.80,"max_lon":14.58,"max_lat":36.08}
CREATE OR REPLACE FUNCTION v2.buildings_in_bbox(
    country_table text,
    min_lon       float,
    min_lat       float,
    max_lon       float,
    max_lat       float
)
RETURNS TABLE (
    fid       bigint,
    unique_id text,
    source    text,
    area      double precision,
    height    double precision,
    "use"     bigint,
    geom      geometry
)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, v2, v1 AS $$
BEGIN
    RETURN QUERY EXECUTE format(
        'SELECT fid::bigint, unique_id::text, source::text, area, height, "use", geom
         FROM v2.%I
         WHERE geom && ST_Transform(ST_MakeEnvelope($1, $2, $3, $4, 4326), 3035)
         LIMIT 5000',
        country_table
    ) USING min_lon, min_lat, max_lon, max_lat;
END;
$$;


-- 2. Buildings near a GPS point
-- POST /rpc/buildings_nearby
-- Body: {"country_table":"malta","lat":35.8989,"lon":14.5146,"radius_m":300}
CREATE OR REPLACE FUNCTION v2.buildings_nearby(
    country_table text,
    lat           float,
    lon           float,
    radius_m      float
)
RETURNS TABLE (
    fid          bigint,
    unique_id    text,
    area         double precision,
    height       double precision,
    "use"        bigint,
    distance_m   float,
    geom         geometry
)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, v2, v1 AS $$
BEGIN
    RETURN QUERY EXECUTE format(
        'SELECT fid::bigint, unique_id::text, area, height, "use",
                ST_Distance(geom, ST_Transform(ST_SetSRID(ST_MakePoint($2, $1), 4326), 3035))::float AS distance_m,
                geom
         FROM v2.%I
         WHERE ST_DWithin(geom, ST_Transform(ST_SetSRID(ST_MakePoint($2, $1), 4326), 3035), $3)
         ORDER BY distance_m
         LIMIT 1000',
        country_table
    ) USING lat, lon, radius_m;
END;
$$;


-- 3. Aggregated country statistics
-- POST /rpc/country_statistics
-- Body: {"country_table":"malta"}
CREATE OR REPLACE FUNCTION v2.country_statistics(country_table text)
RETURNS TABLE (
    total_buildings  bigint,
    avg_area         double precision,
    total_area       double precision,
    avg_height       double precision,
    avg_shapefactor  double precision,
    min_epoch        bigint,
    max_epoch        bigint
)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, v2, v1 AS $$
BEGIN
    RETURN QUERY EXECUTE format(
        'SELECT COUNT(*)::bigint,
                AVG(area)::double precision,
                SUM(area)::double precision,
                AVG(height)::double precision,
                AVG(shapefactor)::double precision,
                MIN(epoch)::bigint,
                MAX(epoch)::bigint
         FROM v2.%I',
        country_table
    );
END;
$$;


-- 4. Filter buildings by use type
-- POST /rpc/buildings_by_use
-- Body: {"country_table":"malta","use_type":1}
CREATE OR REPLACE FUNCTION v2.buildings_by_use(
    country_table text,
    use_type      bigint
)
RETURNS TABLE (
    fid       bigint,
    unique_id text,
    area      double precision,
    height    double precision,
    geom      geometry
)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, v2, v1 AS $$
BEGIN
    RETURN QUERY EXECUTE format(
        'SELECT fid::bigint, unique_id::text, area, height, geom
         FROM v2.%I
         WHERE "use" = $1
         LIMIT 2000',
        country_table
    ) USING use_type;
END;
$$;


-- 5. Compare R2023 vs R2025 (new or geometrically modified buildings)
-- POST /rpc/compare_versions
-- Body: {"country_table":"malta","limit_rows":500,"offset_rows":0}
CREATE OR REPLACE FUNCTION v2.compare_versions(
    country_table text,
    limit_rows    int DEFAULT 10000,
    offset_rows   int DEFAULT 0
)
RETURNS TABLE (
    fid    bigint,
    status text
)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, v2, v1 AS $$
BEGIN
    RETURN QUERY EXECUTE format(
        'SELECT v2.fid::bigint,
                CASE WHEN v1.fid IS NULL THEN ''NEW''
                     WHEN NOT ST_Equals(v1.geom, v2.geom) THEN ''MODIFIED''
                     ELSE ''UNCHANGED'' END::text AS status
         FROM v2.%I v2
         LEFT JOIN v1.%I v1 ON v1.fid = v2.fid
         ORDER BY v2.fid
         LIMIT $1 OFFSET $2',
        country_table, country_table
    ) USING limit_rows, offset_rows;
END;
$$;


-- 6. Full building details by unique_id
-- POST /rpc/building_by_id
-- Body: {"country_table":"spain","uid":"ES120_N239E37_Y2277.3078_X9323.5932"}
CREATE OR REPLACE FUNCTION v2.building_by_id(
    country_table text,
    uid           text
)
RETURNS TABLE (
    fid          bigint,
    unique_id    text,
    source       text,
    area         double precision,
    height       double precision,
    shapefactor  double precision,
    epoch        bigint,
    "use"        bigint,
    eub_json     text,
    osm_json     text,
    msb_json     text,
    geom         geometry
)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, v2, v1 AS $$
BEGIN
    RETURN QUERY EXECUTE format(
        'SELECT fid::bigint, unique_id::text, source::text,
                area, height, shapefactor, epoch, "use",
                eub_json::text, osm_json::text, msb_json::text, geom
         FROM v2.%I
         WHERE unique_id = $1',
        country_table
    ) USING uid;
END;
$$;


-- 7. Find buildings similar to a reference building within a radius
-- Matches by area and height within configurable tolerances (±30% default).
-- Ordered by composite similarity score (descending) then distance (ascending).
-- POST /rpc/buildings_similar
-- Body: {"country_table":"spain","ref_unique_id":"ES120_N239E37_Y2277.3078_X9323.5932","radius_m":5000}
CREATE OR REPLACE FUNCTION v2.buildings_similar(
    country_table  text,
    ref_unique_id  text,
    radius_m       float DEFAULT 5000,
    area_pct       float DEFAULT 0.30,
    height_pct     float DEFAULT 0.30,
    max_results    int   DEFAULT 200
)
RETURNS TABLE (
    fid          bigint,
    unique_id    text,
    area         double precision,
    height       double precision,
    "use"        bigint,
    epoch        bigint,
    shapefactor  double precision,
    distance_m   double precision,
    similarity   double precision,
    geom         geometry
)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, v2 AS $$
DECLARE
    ref_area   double precision;
    ref_height double precision;
    ref_geom   geometry;
BEGIN
    EXECUTE format(
        'SELECT area, height, geom FROM v2.%I WHERE unique_id = $1',
        country_table
    ) INTO ref_area, ref_height, ref_geom USING ref_unique_id;

    IF ref_geom IS NULL THEN
        RAISE EXCEPTION 'Building % not found in table %', ref_unique_id, country_table;
    END IF;

    RETURN QUERY EXECUTE format(
        $sql$
        SELECT
            fid::bigint,
            unique_id::text,
            area::double precision,
            height::double precision,
            "use"::bigint,
            epoch::bigint,
            shapefactor::double precision,
            round(ST_Distance(geom, $3)::numeric, 1)::double precision AS distance_m,
            -- Similarity score 0-1: area and height each contribute 50%%
            round(GREATEST(0.0,
                1.0
                - 0.5 * ABS(COALESCE(area,   0) - COALESCE($1, 0))
                        / NULLIF(COALESCE($1, 0) * $5, 0)
                - 0.5 * ABS(COALESCE(height, 0) - COALESCE($2, 0))
                        / NULLIF(COALESCE($2, 0) * $6, 0)
            )::numeric, 3)::double precision AS similarity,
            geom
        FROM v2.%I
        WHERE
            unique_id != $4
            AND ST_DWithin(geom, $3, $7)
            AND (
                $1 IS NULL OR $1 = 0
                OR area BETWEEN $1 * (1.0 - $5) AND $1 * (1.0 + $5)
            )
            AND (
                $2 IS NULL OR $2 = 0
                OR height BETWEEN $2 * (1.0 - $6) AND $2 * (1.0 + $6)
            )
        ORDER BY similarity DESC, distance_m ASC
        LIMIT $8
        $sql$,
        country_table
    ) USING ref_area, ref_height, ref_geom, ref_unique_id,
            area_pct, height_pct, radius_m, max_results;
END;
$$;


-- ============================================================
-- Execution Permissions
-- ============================================================
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA v2 TO web_anon;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA v1 TO web_anon;
