-- ============================================================
-- DBSM GeoService — RPC Functions for PostgREST
-- Schema v2 (R2025): fid, unique_id, source, area, height,
--   shapefactor, epoch, use, eub_json, osm_json, msb_json + geom
-- ============================================================

-- 1. Buildings within a Bounding Box (for map viewers)
-- POST /rpc/buildings_in_bbox
-- Body: {"country_table":"malta","min_lon":14.0,"min_lat":35.8,"max_lon":14.6,"max_lat":36.1}
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
        'SELECT fid, unique_id, source, area, height, "use", geom
         FROM v2.%I
         WHERE geom && ST_MakeEnvelope($1, $2, $3, $4, 4326)
         LIMIT 5000',
        country_table
    ) USING min_lon, min_lat, max_lon, max_lat;
END;
$$;

-- 2. Buildings near a GPS point
-- POST /rpc/buildings_nearby
-- Body: {"country_table":"malta","lat":35.8989,"lon":14.5146,"radius_m":500}
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
        'SELECT fid, unique_id, area, height, "use",
                ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography)::float AS distance_m,
                geom
         FROM v2.%I
         WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, $3)
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
                AVG(area), SUM(area),
                AVG(height),
                AVG(shapefactor),
                MIN(epoch)::bigint, MAX(epoch)::bigint
         FROM v2.%I',
        country_table
    );
END;
$$;

-- 4. Filter buildings by use type
-- POST /rpc/buildings_by_use
-- Body: {"country_table":"malta","use_type":1011}
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
        'SELECT fid, unique_id, area, height, geom
         FROM v2.%I
         WHERE "use" = $1
         LIMIT 2000',
        country_table
    ) USING use_type;
END;
$$;

-- 5. Compare R2023 vs R2025 (New or geometrically modified buildings)
-- POST /rpc/compare_versions
-- Body: {"country_table":"malta", "limit_rows": 10000, "offset_rows": 0}
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
        'SELECT v2.fid,
                CASE WHEN v1.fid IS NULL THEN ''NEW''
                     WHEN NOT ST_Equals(v1.geom, v2.geom) THEN ''MODIFIED''
                     ELSE ''UNCHANGED'' END AS status
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
-- Body: {"country_table":"malta","uid":"MT-12345"}
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
        'SELECT fid, unique_id, source, area, height,
                shapefactor, epoch, "use",
                eub_json, osm_json, msb_json, geom
         FROM v2.%I
         WHERE unique_id = $1',
        country_table
    ) USING uid;
END;
$$;

-- ============================================================
-- Execution Permissions
-- ============================================================
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA v2 TO web_anon;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA v1 TO web_anon;