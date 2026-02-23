-- ============================================================
-- DBSM GeoService — Funciones RPC para PostgREST
-- Esquema v2 (R2025): fid, unique_id, source, area, height,
--   shapefactor, epoch, use, eub_json, osm_json, msb_json + geom
-- ============================================================

-- 1. Edificios dentro de un Bounding Box (para visores de mapa)
-- POST /rpc/edificios_en_bbox
-- Body: {"tabla":"spain","min_lon":-4.0,"min_lat":40.0,"max_lon":-3.0,"max_lat":41.0}
CREATE OR REPLACE FUNCTION v2.edificios_en_bbox(
    tabla    text,
    min_lon  float,
    min_lat  float,
    max_lon  float,
    max_lat  float
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
LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
BEGIN
    RETURN QUERY EXECUTE format(
        'SELECT fid, unique_id, source, area, height, "use", geom
         FROM v2.%I
         WHERE geom && ST_MakeEnvelope($1, $2, $3, $4, 4326)
         LIMIT 5000',
        tabla
    ) USING min_lon, min_lat, max_lon, max_lat;
END;
$$;

-- 2. Edificios cercanos a un punto GPS
-- POST /rpc/edificios_cercanos
-- Body: {"tabla":"spain","lat":40.4168,"lon":-3.7038,"radio_m":500}
CREATE OR REPLACE FUNCTION v2.edificios_cercanos(
    tabla   text,
    lat     float,
    lon     float,
    radio_m float
)
RETURNS TABLE (
    fid          bigint,
    unique_id    text,
    area         double precision,
    height       double precision,
    "use"        bigint,
    distancia_m  float,
    geom         geometry
)
LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
BEGIN
    RETURN QUERY EXECUTE format(
        'SELECT fid, unique_id, area, height, "use",
                ST_Distance(geom::geography, ST_Point($2,$1)::geography)::float AS distancia_m,
                geom
         FROM v2.%I
         WHERE ST_DWithin(geom::geography, ST_Point($2,$1)::geography, $3)
         ORDER BY distancia_m
         LIMIT 1000',
        tabla
    ) USING lat, lon, radio_m;
END;
$$;

-- 3. Estadísticas agregadas de un país
-- POST /rpc/estadisticas_pais
-- Body: {"tabla":"spain"}
CREATE OR REPLACE FUNCTION v2.estadisticas_pais(tabla text)
RETURNS TABLE (
    total_edificios  bigint,
    area_media       double precision,
    area_total       double precision,
    altura_media     double precision,
    shapefactor_med  double precision,
    epoch_min        bigint,
    epoch_max        bigint
)
LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
BEGIN
    RETURN QUERY EXECUTE format(
        'SELECT COUNT(*)::bigint,
                AVG(area), SUM(area),
                AVG(height),
                AVG(shapefactor),
                MIN(epoch)::bigint, MAX(epoch)::bigint
         FROM v2.%I',
        tabla
    );
END;
$$;

-- 4. Filtrar por tipo de uso en un país
-- POST /rpc/edificios_por_uso
-- Body: {"tabla":"spain","uso":1011}
CREATE OR REPLACE FUNCTION v2.edificios_por_uso(
    tabla text,
    uso   bigint
)
RETURNS TABLE (
    fid       bigint,
    unique_id text,
    area      double precision,
    height    double precision,
    geom      geometry
)
LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
BEGIN
    RETURN QUERY EXECUTE format(
        'SELECT fid, unique_id, area, height, geom
         FROM v2.%I
         WHERE "use" = $1
         LIMIT 2000',
        tabla
    ) USING uso;
END;
$$;

-- 5. Comparativa R2023 vs R2025 (edificios nuevos o con geometría modificada)
-- POST /rpc/comparar_versiones
-- Body: {"tabla":"spain"}
CREATE OR REPLACE FUNCTION v2.comparar_versiones(tabla text)
RETURNS TABLE (
    fid    bigint,
    estado text
)
LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
BEGIN
    RETURN QUERY EXECUTE format(
        'SELECT v2.fid,
                CASE WHEN v1.fid IS NULL THEN ''NUEVO''
                     WHEN NOT ST_Equals(v1.geom, v2.geom) THEN ''MODIFICADO''
                     ELSE ''SIN_CAMBIOS'' END AS estado
         FROM v2.%I v2
         LEFT JOIN v1.%I v1 ON v1.fid = v2.fid',
        tabla, tabla
    );
END;
$$;

-- 6. Detalle completo de un edificio por unique_id
-- POST /rpc/edificio_por_id
-- Body: {"tabla":"spain","uid":"ES-12345"}
CREATE OR REPLACE FUNCTION v2.edificio_por_id(
    tabla text,
    uid   text
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
LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
BEGIN
    RETURN QUERY EXECUTE format(
        'SELECT fid, unique_id, source, area, height,
                shapefactor, epoch, "use",
                eub_json, osm_json, msb_json, geom
         FROM v2.%I
         WHERE unique_id = $1',
        tabla
    ) USING uid;
END;
$$;

-- ============================================================
-- Permisos de ejecución
-- ============================================================
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA v2 TO web_anon;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA v1 TO web_anon;
