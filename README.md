# DBSM GeoService

Containerized geospatial microservice stack for managing, publishing and querying the **Database of Structures and Buildings Mapping (DBSM)** — a pan-European building footprint dataset covering 28 countries in two versions: R2023 (v1) and R2025 (v2).

Built as a Proof of Concept for the [MODERATE](https://github.com/MODERATE-Project/poc-dbsm-r2023) European project.

---

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Service Access](#service-access)
- [Repository Structure](#repository-structure)
- [Workflows](#workflows)
  - [Initial Setup](#1-initial-setup)
  - [Importing a Country](#2-importing-a-country)
  - [Bulk Import](#3-bulk-import)
  - [Updating SQL Functions](#4-updating-sql-functions)
  - [Verifying a Publication](#5-verifying-a-publication)
  - [Full Reset](#6-full-reset)
- [Task Reference](#task-reference)
- [API Reference](#api-reference)
- [Swagger UI — Verified Call Examples](#swagger-ui--verified-call-examples)
- [Data Schema](#data-schema)
- [GeoServer](#geoserver)
- [QGIS Integration](#qgis-integration)
- [Performance Considerations](#performance-considerations)
- [Known Issues](#known-issues)
- [Roadmap](#roadmap)
- [References](#references)

---

## Architecture

```
┌─ Docker Compose (dbsm-geoservice-net) ────────────────────────┐
│                                                                │
│   PostgreSQL 16 + PostGIS 3          :5432                    │
│              │                                                 │
│              ├──► PostgREST v12.2.8  :3000                    │
│              │         │                                       │
│              │         └──► Swagger UI v5.21.0  :8082         │
│              │                                                 │
│              ├──► GeoServer 2.24.2   :8081                    │
│              │                                                 │
│              └──► PgAdmin 4          :5050                    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**PostgreSQL** is the single source of truth. All other services read from it directly. Two schemas partition the data by version:

| Schema | Dataset | Description |
|--------|---------|-------------|
| `v1` | DBSM R2023 | Geometry + source only (`fid`, `source`, `geom`) |
| `v2` | DBSM R2025 | Full attribute set including height, use, epoch, JSON metadata |

---

## Prerequisites

| Tool | Purpose | Installation |
|------|---------|-------------|
| Docker Engine ≥ 24 | Container runtime | [docs.docker.com](https://docs.docker.com/engine/install/) |
| Docker Compose ≥ 2 | Multi-container orchestration | Included with Docker Desktop |
| Task | CLI task runner | `sh -c "$(curl -sL https://taskfile.dev/install.sh)" -- -d -b /usr/local/bin` |
| GDAL / ogr2ogr | GeoPackage import | `sudo apt install gdal-bin` |
| Python 3 + requests | GeoServer automation | `pip install requests` |

**QGIS 3.x** is optional, required only for the desktop client integration.

### Hardware recommendations

| Scope | RAM | Disk |
|-------|-----|------|
| Malta, Luxembourg (small countries) | 4 GB | < 2 GB in PostgreSQL |
| Spain, Italy, France | 16–32 GB | 20–50 GB in PostgreSQL |
| All 28 countries × 2 versions | 64+ GB | ~500 GB in PostgreSQL |

---

## Quick Start

```bash
# 1. Clone and configure environment
cp .env.default .env
# Edit .env if you need to change ports or credentials

# 2. Start all services
task up

# 3. Initialise GeoServer shared resources (first time only)
task geoserver:init VERSION=v2
task geoserver:init VERSION=v1

# 4. Import your first dataset
task import CITY=malta VERSION=v2
```

The stack is ready when all containers report healthy:
```bash
task ps
```

---

## Service Access

| Service | URL | Credentials |
|---------|-----|-------------|
| PostgREST API | http://localhost:3000 | Public (no auth) |
| Swagger UI | http://localhost:8082 | Public (no auth) |
| GeoServer | http://localhost:8081/geoserver/web | `admin` / `geoserver` |
| PgAdmin | http://localhost:5050 | `user@domain.com` / `postgres` |
| PostgreSQL (direct) | `localhost:5432` | `dbsm_admin` / `postgres` |

> All credentials are defined in `.env` and can be overridden before first startup.

---

## Repository Structure

```
.
├── docker-compose.yml          # Service definitions, network, volumes
├── Dockerfile.postgis          # Custom PostgreSQL 16 + PostGIS 3 image
├── Taskfile.yml                # CLI task automation
├── import_data.sh              # ogr2ogr pipeline: GeoPackage → PostGIS
├── gsconfig.py                 # GeoServer REST API automation
├── .env.default                # Environment template (committed)
├── .env                        # Active environment (gitignored)
├── servers.json                # PgAdmin auto-discovery preset
├── pg_service.conf             # PostgreSQL libpq service alias
│
├── initdb/
│   ├── 01_postgis.sql          # PostGIS extension + v1/v2 schemas
│   ├── 02_postgrest.sql        # Roles: web_anon (read-only), authenticator
│   ├── 03_api_functions.sql    # PostgREST RPC endpoint definitions
│   └── geoserver.xml           # GeoServer security config (mounted into container)
│
├── styles/
│   ├── dbsm_buildings.sld      # v2 style: height classification (5 colour bands)
│   └── dbsm_buildings_v1.sld   # v1 style: flat colour (no height attribute)
│
├── docs/
│   ├── openapi.yaml            # Auto-generated PostgREST OpenAPI spec
│   └── call_example.txt        # Example API calls with geometry
│
├── qgis_project/
│   └── dbsm_demo.qgs           # QGIS 3 demo project with layers and Python actions
│
├── datasets/                   # GeoPackage source files (gitignored, ~240 GB)
├── postgres_data/              # PostgreSQL persistent volume (gitignored)
├── geoserver_data/             # GeoServer persistent volume (gitignored)
└── pgadmin_data/               # PgAdmin persistent volume (gitignored)
```

### File descriptions

**`docker-compose.yml`**  
Defines five services on a shared bridge network. Health checks on PostgreSQL ensure PostgREST and GeoServer only start when the database is accepting connections.

**`Taskfile.yml`**  
Single-command interface for all common operations. Loads `.env` automatically. See [Task Reference](#task-reference) for the full list.

**`import_data.sh`**  
Validates prerequisites, invokes `ogr2ogr` to convert a GeoPackage into a PostGIS table, and applies role-based permissions. Accepts `CITY=<name>|all` and `VERSION=v1|v2`.

**`gsconfig.py`**  
Idempotent Python script that configures GeoServer via its REST API: creates workspaces, datastores, uploads SLD styles, publishes feature types, recalculates bounding boxes, and maintains a LayerGroup aggregating all published layers. Safe to re-run.

**`initdb/01_postgis.sql`**  
Activates the PostGIS extension and creates the `v1` and `v2` schemas owned by `dbsm_admin`. Executed automatically on first container startup.

**`initdb/02_postgrest.sql`**  
Creates the `web_anon` role (unauthenticated, SELECT-only on both schemas) and the `authenticator` login role. PostgREST uses these roles to enforce access control.

**`initdb/03_api_functions.sql`**  
Defines seven PL/pgSQL functions exposed as HTTP endpoints by PostgREST. All use `SECURITY DEFINER` with an explicit `search_path`.

**`initdb/geoserver.xml`**  
GeoServer security configuration file. Mounted directly into the container at `/opt/geoserver/data_dir/security/geoserver.xml` so GeoServer picks it up on startup without manual web-UI configuration.

**`qgis_project/dbsm_demo.qgs`**  
Ready-to-open QGIS 3 project. Connects directly to the local PostGIS stack and contains pre-configured layers and Python actions for interactive exploration of the DBSM dataset. See [QGIS Integration](#qgis-integration) for the full description.

**`styles/dbsm_buildings.sld`**  
OGC SLD for v2 layers. Classifies buildings by height into five bands: unknown/zero (grey), ≤ 6 m (yellow), 6–15 m (orange), 15–30 m (red), > 30 m (dark red).

**`styles/dbsm_buildings_v1.sld`**  
OGC SLD for v1 layers. Single flat rule (beige fill, brown stroke) — v1 data does not include a `height` attribute.

---

## Workflows

### 1. Initial Setup

```bash
task up                          # Build images and start all services
task geoserver:init VERSION=v2   # Create workspace, datastore, style for v2
task geoserver:init VERSION=v1   # Same for v1
```

`geoserver:init` is idempotent — safe to re-run if any step was interrupted.

### 2. Importing a Country

```bash
task import CITY=malta VERSION=v2
```

This single command executes three steps in sequence:

1. **Import** — `import_data.sh` converts `./datasets/dbsm-v2-malta-R2025.gpkg` into `v2.malta` in PostgreSQL, grants SELECT to `web_anon`.
2. **Publish** — `gsconfig.py` creates or updates the GeoServer layer, recalculates the bounding box, assigns the SLD style, and rebuilds the LayerGroup.
3. **Reload** — Sends `SIGUSR1` to PostgREST to refresh its schema cache, making the new table immediately available via the API.

**GeoPackage naming convention:**

| Version | Expected filename |
|---------|------------------|
| v1 | `./datasets/dbsm-v1-<city>-merge.gpkg` |
| v2 | `./datasets/dbsm-v2-<city>-R2025.gpkg` |

### 3. Bulk Import

```bash
task import CITY=all VERSION=v2
```

In `CITY=all` mode, `import_data.sh` iterates over **all** `.gpkg` files in `./datasets/` regardless of the `VERSION` argument — both v1 and v2 files are imported, with the schema determined by the filename (e.g., `dbsm-v2-malta-R2025.gpkg` → `v2.malta`). The `VERSION` parameter only affects the subsequent GeoServer publish step, which will publish layers exclusively to the specified workspace (`dbsm_v2` in this example).

To bulk-import and publish only one version, place only the relevant `.gpkg` files in `./datasets/` before running the command.

### 4. Updating SQL Functions

After modifying any file in `initdb/`:

```bash
task db:apply-sql
```

Re-applies all three SQL files in order and reloads PostgREST. The `ERROR: already exists` messages for schemas and roles are expected and harmless.

### 5. Verifying a Publication

```bash
task geoserver:verify CITY=malta VERSION=v2
task geoserver:status VERSION=v2
```

`verify` checks that the WMS GetCapabilities endpoint responds and that the named layer is present.  
`status` lists all feature types currently published in a workspace.

### 6. Full Reset

```bash
task db:reset   # WARNING: destroys all data
```

Runs `clean:nuke` (removes containers, volumes, and data directories) followed by `up`. Use only in development.

---

## Task Reference

| Task | Description |
|------|-------------|
| `task up` | Build images and start all containers |
| `task down` | Stop and remove containers — volumes are preserved |
| `task stop` | Pause containers without removing them |
| `task start` | Resume paused containers |
| `task restart` | Stop and restart all containers |
| `task logs` | Stream live logs from all containers |
| `task ps` | Show container status and health |
| `task import CITY=<c> VERSION=<v>` | Full pipeline: import → publish → API reload |
| `task geoserver:publish CITY=<c> VERSION=<v>` | Publish a single PostGIS table to GeoServer |
| `task geoserver:init VERSION=<v>` | Create shared GeoServer resources (idempotent) |
| `task geoserver:status VERSION=<v>` | List published layers in a workspace |
| `task geoserver:verify CITY=<c> VERSION=<v>` | Verify WMS GetCapabilities for a layer |
| `task api:reload` | Signal PostgREST to reload schema cache |
| `task db:apply-sql` | Re-apply all SQL init files and reload API |
| `task db:apply-sql-safe` | Same, but only if tables already exist |
| `task clean:soft` | Remove containers and networks, preserve volumes |
| `task clean:nuke` | **DESTRUCTIVE** — remove containers, volumes and data directories |
| `task db:reset` | **DESTRUCTIVE** — full teardown and restart |

---

## API Reference

Base URL: `http://localhost:3000`  
All RPC functions are available at `POST /rpc/<function_name>`.  
Interactive documentation: **Swagger UI at http://localhost:8082**

### Available Endpoints

#### `POST /rpc/buildings_in_bbox`
Returns buildings within a geographic bounding box. Maximum 5,000 features.

```json
{
  "country_table": "malta",
  "min_lon": 14.0, "min_lat": 35.8,
  "max_lon": 14.6, "max_lat": 36.1
}
```

#### `POST /rpc/buildings_nearby`
Returns buildings within a radius around a GPS point, ordered by distance. Maximum 1,000 features.

```json
{
  "country_table": "malta",
  "lat": 35.8989,
  "lon": 14.5146,
  "radius_m": 500
}
```

#### `POST /rpc/country_statistics`
Returns aggregated metrics for an entire country dataset.

```json
{ "country_table": "spain" }
```

Returns: `total_buildings`, `avg_area`, `total_area`, `avg_height`, `avg_shapefactor`, `min_epoch`, `max_epoch`.

#### `POST /rpc/buildings_by_use`
Filters buildings by use classification code. Maximum 2,000 features.

```json
{ "country_table": "malta", "use_type": 1 }
```

Use codes: `0` = unknown, `1` = residential, `2` = non-residential.

#### `POST /rpc/compare_versions`
Detects differences between v1 (R2023) and v2 (R2025) for the same country. Supports pagination.

```json
{ "country_table": "malta", "limit_rows": 10000, "offset_rows": 0 }
```

Returns: `fid` + `status` (`NEW` / `MODIFIED` / `UNCHANGED`).

#### `POST /rpc/building_by_id`
Returns full attribute detail for a single building, including raw JSON source metadata.

```json
{ "country_table": "spain", "uid": "ES120_N239E37_Y2277.3078_X9323.5932" }
```

#### `POST /rpc/buildings_similar`
Finds buildings similar to a reference building by area and height within a configurable radius. Returns a composite similarity score (0–1).

```json
{
  "country_table": "spain",
  "ref_unique_id": "ES120_N239E37_Y2277.3078_X9323.5932",
  "radius_m": 5000,
  "area_pct": 0.30,
  "height_pct": 0.30,
  "max_results": 200
}
```

Results are ordered by `similarity DESC`, then `distance_m ASC`.

### Direct Table Access

PostgREST exposes each country table in schema `v2` as a direct REST resource. By default (`PGRST_DB_SCHEMA=v2` in `.env`), only `v2` tables are accessible this way — `v1` tables are not reachable via direct table endpoints (use the RPC functions instead).

```bash
# First 10 buildings in Malta (v2)
GET http://localhost:3000/malta?limit=10

# Buildings taller than 20 m
GET http://localhost:3000/spain?height=gt.20&limit=100

# Select specific columns
GET http://localhost:3000/malta?select=unique_id,area,height&limit=50
```

---

## Swagger UI — Verified Call Examples

All examples below have been tested against an instance with Malta, Luxembourg, Spain and Italy imported.  
Open **http://localhost:8082**, locate the function, click **Try it out**, paste the body shown, and click **Execute**.

> **Geometry and Swagger UI rendering**  
> Functions that return a `geom` column can produce very large responses (tens of MB) that Swagger UI cannot render in the browser. To avoid this, append `?select=` to the request URL in Swagger to exclude the geometry column:
> ```
> http://127.0.0.1:3000/rpc/buildings_in_bbox?select=fid,unique_id,source,area,height,use
> ```
> The geometry is still returned by default when calling from curl, QGIS, or any other client.

---

### `buildings_in_bbox` — Buildings within a bounding box

Retrieves buildings inside a rectangular area. Coordinates are in **WGS84 (EPSG:4326)**.

**Swagger URL** (add this in the address bar to exclude geometry):
```
http://127.0.0.1:3000/rpc/buildings_in_bbox?select=fid,unique_id,source,area,height,use
```

**Malta — Valletta city block (~50 buildings)**
```json
{
  "country_table": "malta",
  "min_lon": 14.507,
  "min_lat": 35.894,
  "max_lon": 14.516,
  "max_lat": 35.901
}
```

**Spain — Villaviciosa city centre (~80 buildings)**
```json
{
  "country_table": "spain",
  "min_lon": -5.432,
  "min_lat": 43.481,
  "max_lon": -5.421,
  "max_lat": 43.488
}
```

Expected response: array with `fid`, `unique_id`, `source`, `area`, `height`, `use` (and `geom` unless excluded). Capped at 5,000 features.

---

### `buildings_nearby` — Buildings within a radius of a point

Searches for buildings within `radius_m` metres of a GPS coordinate. Results are ordered by distance ascending.

**Swagger URL** (exclude geometry):
```
http://127.0.0.1:3000/rpc/buildings_nearby?select=fid,unique_id,area,height,use,distance_m
```

**Malta — Valletta city centre, 150 m radius (~30 buildings)**
```json
{
  "country_table": "malta",
  "lat": 35.8989,
  "lon": 14.5146,
  "radius_m": 150
}
```

**Spain — Gijón city centre, 200 m radius (~40 buildings)**
```json
{
  "country_table": "spain",
  "lat": 43.5453,
  "lon": -5.6615,
  "radius_m": 200
}
```

Expected response: array ordered by `distance_m`, including `fid`, `unique_id`, `area`, `height`, `use`, `distance_m` (and `geom` unless excluded).

---

### `country_statistics` — Aggregated dataset metrics

Returns a single row with summary statistics for the entire country.

**Malta**
```json
{ "country_table": "malta" }
```

**Spain**
```json
{ "country_table": "spain" }
```

Expected response:
```json
[{
  "total_buildings": 142531,
  "avg_area": 112.4,
  "total_area": 16021934.2,
  "avg_height": 8.3,
  "avg_shapefactor": 0.48,
  "min_epoch": 0,
  "max_epoch": 5
}]
```

---

### `buildings_by_use` — Filter by use classification

Returns buildings matching a specific use code. Maximum 2,000 features.

Use codes: `0` = unknown / no data, `1` = residential, `2` = non-residential.

**Swagger URL** (exclude geometry):
```
http://127.0.0.1:3000/rpc/buildings_by_use?select=fid,unique_id,area,height
```

**Malta — residential buildings**
```json
{
  "country_table": "malta",
  "use_type": 1
}
```

**Spain — non-residential buildings**
```json
{
  "country_table": "spain",
  "use_type": 2
}
```

---

### `building_by_id` — Full detail for a single building

Returns all columns for one building, including the raw JSON source metadata (`eub_json`, `osm_json`, `msb_json`).

**Spain — verified unique_id from Villaviciosa**
```json
{
  "country_table": "spain",
  "uid": "ES120_N239E37_Y2277.3078_X9323.5932"
}
```

To find a valid `unique_id` for any other building, run `buildings_in_bbox` first and copy a `unique_id` from the response.

Expected response: single-element array with all schema columns including the JSON metadata fields.

---

### `compare_versions` — Diff between v1 (R2023) and v2 (R2025)

Compares the two dataset versions for the same country. Requires the country to be imported in **both** `v1` and `v2` schemas.

**Malta — first 500 differences**
```json
{
  "country_table": "malta",
  "limit_rows": 500,
  "offset_rows": 0
}
```

Expected response: array of `{ "fid": 12345, "status": "NEW" | "MODIFIED" | "UNCHANGED" }`.

> If only v2 is imported, all rows will return `"NEW"` since there are no v1 records to compare against.

---

### `buildings_similar` — Buildings similar to a reference building

Finds buildings within a radius that match the reference building's area and height within a configurable tolerance. Results are ordered by composite similarity score descending.

**Spain — buildings similar to a specific building in Villaviciosa, 5 km radius**
```json
{
  "country_table": "spain",
  "ref_unique_id": "ES120_N239E37_Y2277.3078_X9323.5932",
  "radius_m": 5000,
  "area_pct": 0.30,
  "height_pct": 0.30,
  "max_results": 50
}
```

**Malta — tighter tolerance, 1 km radius**
```json
{
  "country_table": "malta",
  "ref_unique_id": "<paste a unique_id from buildings_in_bbox>",
  "radius_m": 1000,
  "area_pct": 0.20,
  "height_pct": 0.20,
  "max_results": 100
}
```

Expected response: array ordered by `similarity` (1.0 = identical attributes) then `distance_m`. Each row includes `fid`, `unique_id`, `area`, `height`, `use`, `epoch`, `shapefactor`, `distance_m`, `similarity`, `geom`.

**Similarity score interpretation:**

| Score | Meaning |
|-------|---------|
| 0.90 – 1.00 | Very similar — nearly identical area and height |
| 0.70 – 0.89 | Similar — within ~15% on both dimensions |
| 0.50 – 0.69 | Loosely similar — at or approaching the tolerance boundary |
| < 0.50 | Should not appear — filtered out by the tolerance conditions |

---

## Data Schema

All tables in schema `v2` share the following structure:

| Column | Type | Description |
|--------|------|-------------|
| `fid` | integer | Primary key |
| `unique_id` | varchar | Global identifier: `{NUTS3}_{grid}_{lon}_{lat}` |
| `source` | varchar | Data source: `eub` (EuroBuildings), `osm` (OpenStreetMap), `msb` (Microsoft Buildings) |
| `height` | float | Building height in metres |
| `shapefactor` | float | Surface-to-volume ratio (m²/m³) — measure of compactness |
| `epoch` | bigint | Construction decade: `0`=pre-1980, `1`=1980–90, `2`=1990–2000, `3`=2000–10, `4`=2010–20, `5`=2020+ |
| `use` | bigint | Building use: `0`=unknown, `1`=residential, `2`=non-residential |
| `area` | float | Footprint area in m² |
| `eub_json` | varchar | EuroBuildings metadata: age, type, building subtype, levels, roof-shape |
| `osm_json` | varchar | OpenStreetMap metadata |
| `msb_json` | varchar | Microsoft Buildings metadata |
| `geom` | geometry | MultiPolygon, EPSG:3035 (ETRS89-LAEA) |

Schema `v1` tables contain only: `fid`, `source`, `geom`.

### JSON metadata fields

The `eub_json` column is the richest source of auxiliary data when available:

```json
{
  "height": 12.5,
  "age": 2001.0,
  "type": "residential",
  "building": "apartments",
  "levels": "4",
  "roof-shape": "",
  "date": ""
}
```

Field availability varies by country and building. `age` (exact construction year) is more precise than `epoch` (decade bin) when present.

---

## GeoServer

### Published resources

| Resource | Name | Description |
|----------|------|-------------|
| Workspace (v2) | `dbsm_v2` | Groups all v2 layers |
| Workspace (v1) | `dbsm_v1` | Groups all v1 layers |
| DataStore (v2) | `postgis_v2` | PostGIS connection → schema `v2` |
| DataStore (v1) | `postgis_v1` | PostGIS connection → schema `v1` |
| Style (v2) | `dbsm_buildings` | Height-classified SLD |
| Style (v1) | `dbsm_buildings_v1` | Flat-colour SLD |
| Layer | `dbsm_v2:<country>` | One per imported country |
| LayerGroup | `dbsm_v2_all` | All v2 countries aggregated |
| LayerGroup | `dbsm_v1_all` | All v1 countries aggregated |

### WMS / WFS endpoints

```
WMS GetCapabilities (v2):
http://localhost:8081/geoserver/dbsm_v2/ows?service=WMS&version=1.3.0&request=GetCapabilities

WFS GetCapabilities (v2):
http://localhost:8081/geoserver/dbsm_v2/ows?service=WFS&version=2.0.0&request=GetCapabilities
```

### Automation

All GeoServer configuration is managed by `gsconfig.py`. Manual intervention via the web UI is not required for normal operations. The script uses a delete-and-recreate strategy for LayerGroups to work around a known bug in GeoServer 2.24.x where `PUT` does not reliably replace the `<publishables>` list.

---

## QGIS Integration

### Demo project

The file `qgis_project/dbsm_demo.qgs` is a ready-to-open QGIS 3 project (saved with QGIS 3.44). It connects directly to the local PostGIS stack (`localhost:5432`, database `dbsm`) and provides a pre-configured environment for interactive exploration of DBSM data.

Open the project from QGIS: `Project > Open…` → select `qgis_project/dbsm_demo.qgs`.

### Layer structure

The project includes the following layers:

| Layer | Source | Purpose |
|-------|--------|---------|
| `OpenStreetMap` | XYZ tiles (osm.org) | Basemap |
| `CNTR_RG_01M_2016_3035` | External GeoPackage (Eurostat GISCO) | Country boundaries — triggers country-level load actions |
| `COMM_RG_01M_2016_3035` | External GeoJSON (Eurostat GISCO) | Municipality/commune boundaries — triggers commune-level load action |
| `<country>.v2` | PostGIS `v2.<country>` | DBSM R2025 building footprints |
| `<country>.v1` | PostGIS `v1.<country>` | DBSM R2023 building footprints (comparison) |
| `<country>.v2 — vista actual` | PostGIS `v2.<country>` filtered by view extent | Lightweight load of only the buildings visible on screen |

The project is pre-loaded with example layers for Malta, Luxembourg, and Spain. Additional countries can be loaded interactively via the actions below.

> **External reference layers**: `CNTR_RG_01M_2016_3035` and `COMM_RG_01M_2016_3035` are Eurostat GISCO boundary files not included in this repository. Download them from [Eurostat GISCO](https://gisco-services.ec.europa.eu/distribution/v2/) (1:1M scale, EPSG:3035) and place them relative to the project file, or update the layer paths in QGIS after opening.

### Direct PostgreSQL connection

To add layers manually, connect QGIS to the database using:

| Parameter | Value |
|-----------|-------|
| Host | `localhost` |
| Port | `5432` |
| Database | `dbsm` |
| Schema | `v2` or `v1` |
| Username | `dbsm_admin` |
| Password | `postgres` |

Alternatively, use the provided `pg_service.conf` as a libpq service definition.

### Python actions

All actions are pre-configured in `dbsm_demo.qgs` and available via `Layer Properties > Actions` or by right-clicking a feature on the map. They are organised by the layer they belong to.

---

#### Actions on the country boundaries layer (`CNTR_RG_01M_2016_3035`)

Click on any country polygon to trigger these actions. They read the `NAME_ENGL` field to identify the PostGIS table name.

**Action: Load v2 country footprints**  
Adds the full `v2.<country>` PostGIS table as a new layer.

```python
from qgis.utils import iface
from qgis.core import QgsVectorLayer, QgsProject

codigo_iso3 = '[% "NAME_ENGL" %]'.lower()
uri = (
    f"dbname='dbsm' host=localhost port=5432 "
    f"user='dbsm_admin' password='postgres' "
    f"sslmode=disable key='fid' srid=3035 "
    f"type=MultiPolygon table=\"v2\".\"{codigo_iso3}\" (geom) sql="
)
layer = QgsVectorLayer(uri, f"{codigo_iso3}.v2", "postgres")
if not layer.isValid():
    iface.messageBar().pushMessage("Error", f"Could not load v2.{codigo_iso3} — is the dataset imported?", level=3)
else:
    QgsProject.instance().addMapLayer(layer)
    iface.messageBar().pushMessage("OK", f"Layer v2.{codigo_iso3} loaded", level=0)
```

**Action: Load v1 country footprints**  
Same as above but loads from schema `v1` (DBSM R2023).

```python
from qgis.utils import iface
from qgis.core import QgsVectorLayer, QgsProject

codigo_iso3 = '[% "NAME_ENGL" %]'.lower()
uri = (
    f"dbname='dbsm' host=localhost port=5432 "
    f"user='dbsm_admin' password='postgres' "
    f"sslmode=disable key='fid' srid=3035 "
    f"type=MultiPolygon table=\"v1\".\"{codigo_iso3}\" (geom) sql="
)
layer = QgsVectorLayer(uri, f"{codigo_iso3}.v1", "postgres")
if not layer.isValid():
    iface.messageBar().pushMessage("Error", f"Could not load v1.{codigo_iso3} — is the dataset imported?", level=3)
else:
    QgsProject.instance().addMapLayer(layer)
    iface.messageBar().pushMessage("OK", f"Layer v1.{codigo_iso3} loaded", level=0)
```

---

#### Actions on the communes layer (`COMM_RG_01M_2016_3035`)

Click on any municipality polygon to load only the buildings that intersect that administrative boundary.

**Action: Load commune footprints**  
Reads the `TRUE_FLAG` (ISO2 country code) and `COMM_NAME` fields, looks up the corresponding PostGIS table name, and adds a spatially-filtered layer. The `COUNTRY_MAP` dictionary maps ISO2 codes to imported table names — extend it as more countries are imported.

```python
from qgis.utils import iface
from qgis.core import QgsProject, QgsVectorLayer

COUNTRY_MAP = {
    'ES': 'spain', 'MT': 'malta', 'LU': 'luxembourg',
    'IT': 'italy', 'AT': 'austria', 'BE': 'belgium',
    'DE': 'germany', 'FR': 'france', 'PT': 'portugal',
}

feature_id   = [% $id %]
bounds_layer = iface.activeLayer()
feature      = bounds_layer.getFeature(feature_id)
country_code = feature['TRUE_FLAG']
zone_name    = feature['COMM_NAME'] or feature['NUTS_CODE'] or country_code
country      = COUNTRY_MAP.get(str(country_code).upper())

if not country:
    iface.messageBar().pushMessage(
        "Error", f"Country '{country_code}' has no imported table in v2",
        level=2, duration=6)
else:
    geom     = feature.geometry().simplify(10)  # 10 m tolerance to limit WKT length
    geom_wkt = geom.asWkt()
    sql = f"ST_Intersects(geom, ST_GeomFromText('{geom_wkt}', 3035))"
    uri = (
        f"dbname='dbsm' host=localhost port=5432 "
        f"user='dbsm_admin' password='postgres' "
        f"sslmode=disable key='fid' srid=3035 "
        f"type=MultiPolygon table=\"v2\".\"{country}\" (geom) sql={sql}"
    )
    layer_name = f"{country}.v2 — {zone_name}"
    for lyr in QgsProject.instance().mapLayers().values():
        if lyr.name() == layer_name:
            QgsProject.instance().removeMapLayer(lyr)
            break
    nueva_capa = QgsVectorLayer(uri, layer_name, "postgres")
    if not nueva_capa.isValid():
        iface.messageBar().pushMessage("Error", f"Could not load v2.{country}", level=3, duration=6)
    else:
        QgsProject.instance().addMapLayer(nueva_capa)
        n = nueva_capa.featureCount()
        iface.messageBar().pushMessage("OK", f"{n} buildings loaded — {zone_name}", level=0, duration=5)
```

---

#### Actions on building layers (`<country>.v2`)

These actions are available on any v2 country layer and operate on the selected feature.

**Action: Get similar buildings**  
Calls `v2.buildings_similar` and applies a subset filter to the current layer, showing only the reference building and its matches. Zoom adjusts to the filtered result set.

```python
from qgis.utils import iface
from qgis.core import QgsProviderRegistry, QgsDataSourceUri

unique_id = '[% "unique_id" %]'
layer     = iface.activeLayer()
src_uri   = QgsDataSourceUri(layer.dataProvider().dataSourceUri())
country   = src_uri.table()

RADIUS_M   = 5000
AREA_PCT   = 0.30
HEIGHT_PCT = 0.30

try:
    md   = QgsProviderRegistry.instance().providerMetadata('postgres')
    conn = md.createConnection(src_uri.connectionInfo(False), {})
    sql  = (
        f"SELECT fid FROM v2.buildings_similar("
        f"'{country}', '{unique_id}', {RADIUS_M}, {AREA_PCT}, {HEIGHT_PCT})"
    )
    fids = [str(row[0]) for row in conn.executeSql(sql)]
    if not fids:
        iface.messageBar().pushMessage(
            "No results", f"No similar buildings within {RADIUS_M}m", level=1, duration=5)
    else:
        filter_str = f'"unique_id" = \'{unique_id}\' OR "fid" IN ({", ".join(fids)})'
        layer.setSubsetString(filter_str)
        layer.triggerRepaint()
        canvas = iface.mapCanvas()
        canvas.setExtent(layer.extent())
        canvas.zoomByFactor(1.3)
        canvas.refresh()
        iface.messageBar().pushMessage(
            "Filter active",
            f"{len(fids)} similar buildings (radius {RADIUS_M}m) — run Restore view to go back",
            level=0, duration=8)
except Exception as e:
    iface.messageBar().pushMessage("Error", str(e), level=2, duration=10)
```

**Action: Show buildings in bbox**  
Adds a new layer containing only the buildings that intersect the current map canvas extent, without loading the full country table. Useful for large datasets (Spain, Italy, Germany).

```python
from qgis.utils import iface
from qgis.core import (
    QgsVectorLayer, QgsProject,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsDataSourceUri
)

layer       = iface.activeLayer()
src_uri     = QgsDataSourceUri(layer.dataProvider().dataSourceUri())
codigo_iso3 = src_uri.table()

canvas   = iface.mapCanvas()
crs_src  = canvas.mapSettings().destinationCrs()
crs_3035 = QgsCoordinateReferenceSystem('EPSG:3035')
xform    = QgsCoordinateTransform(crs_src, crs_3035, QgsProject.instance())
ext      = xform.transformBoundingBox(canvas.extent())

sql = (
    f"ST_Intersects(geom, ST_MakeEnvelope("
    f"{ext.xMinimum():.2f},{ext.yMinimum():.2f},"
    f"{ext.xMaximum():.2f},{ext.yMaximum():.2f},3035))"
)
uri = (
    f"dbname='dbsm' host=localhost port=5432 "
    f"user='dbsm_admin' password='postgres' "
    f"sslmode=disable key='fid' srid=3035 "
    f"type=MultiPolygon table=\"v2\".\"{codigo_iso3}\" (geom) sql={sql}"
)
nueva_capa = QgsVectorLayer(uri, f"{codigo_iso3}.v2 — current view", "postgres")
if not nueva_capa.isValid():
    iface.messageBar().pushMessage("Error", f"Could not load v2.{codigo_iso3}", level=3)
else:
    QgsProject.instance().addMapLayer(nueva_capa)
    n = nueva_capa.featureCount()
    iface.messageBar().pushMessage("OK", f"{n} buildings loaded in current view — {codigo_iso3}.v2", level=0)
```

**Action: Restore view**  
Clears any active subset filter on the current layer and zooms to full extent.

```python
from qgis.utils import iface

layer = iface.activeLayer()
layer.setSubsetString("")
layer.triggerRepaint()
iface.mapCanvas().zoomToFullExtent()
iface.mapCanvas().refresh()
iface.messageBar().pushMessage("OK", "View restored", level=0, duration=3)
```

---

## Performance Considerations

Performance degrades significantly with large national datasets (Spain: 9.1 GB, Italy: 22.1 GB, Germany: 46.6 GB). The following improvements are ordered by impact-to-effort ratio.

### 1. PostgreSQL configuration tuning (high impact, no code changes)

The default Docker PostgreSQL configuration targets minimal hardware. Add the following to the `postgres` service command in `docker-compose.yml`:

```yaml
command: >
  postgres
  -c shared_buffers=2GB
  -c effective_cache_size=6GB
  -c work_mem=256MB
  -c maintenance_work_mem=512MB
  -c max_parallel_workers_per_gather=4
  -c random_page_cost=1.1
```

Adjust values proportionally to available RAM. No data loss, no rebuild required.

### 2. CLUSTER and VACUUM ANALYZE (high impact, low effort)

Physically reorders table pages on disk to match the spatial index, significantly reducing I/O for bounding-box queries:

```sql
CLUSTER v2.spain USING spain_geom_idx;
VACUUM ANALYZE v2.spain;
```

Can be added as an optional step in `import_data.sh` after the ogr2ogr call.

### 3. GeoWebCache tile seeding (very high impact for WMS, medium effort)

GeoServer ships with GeoWebCache. Pre-generating tiles for commonly viewed zoom levels makes subsequent WMS requests instantaneous, regardless of dataset size.

Configure via: `GeoServer UI > Tile Caching > Tile Layers > <layer> > Seed/Truncate`

Can also be automated via the GeoWebCache REST API and integrated into `gsconfig.py`.

### 4. Scale-dependent rendering in SLD (high impact, requires calibration)

Preventing GeoServer from rendering individual building polygons at country-level zoom avoids the expensive query. A simplified overview rule (flat colour, no attribute filters) handles large scales, while the full classification only activates below 1:50,000.

This requires measuring the exact scale denominators at the target zoom levels for the datasets in use.

### 5. Vector tiles (very high impact, high effort)

Replacing WMS with vector tiles (served by `pg_tileserv` or `Martin`) moves rendering from the server to the client. The server returns lightweight binary data; QGIS or a web browser renders it locally. This is the most scalable long-term solution but requires adding a new service to the stack.

---

## Known Issues

| Issue | Status | Workaround |
|-------|--------|-----------|
| GeoServer 2.24.x `PUT /layergroups` does not replace `<publishables>` | Open upstream bug | `gsconfig.py` uses DELETE + POST instead |
| PostgREST returns `character varying` for geometry columns as base64 WKB by default | By design | Use `Accept: application/geo+json` header or `ST_AsText()` in functions |
| Large datasets (Spain, Italy) cause slow WMS preview renders in GeoServer | Infrastructure limitation | See [Performance Considerations](#performance-considerations) |

---

## Roadmap

### In progress
- Stabilise QGIS "Reset view" action for all layer name formats
- Scale-dependent SLD rendering calibrated to dataset extents

### Planned
- `building_features` RPC function: flattened feature vector from JSON metadata (`age`, `type`, `levels`) for ML/analysis pipelines
- `age_distribution` RPC function: construction decade histogram per country
- PostgreSQL configuration tuning in `docker-compose.yml`
- GeoWebCache seeding integrated into the `task import` pipeline
- QGIS 3D Map View configuration using the `height` field for building extrusion

### Under evaluation
- Natural language to API query interface (LLM + LangChain → PostgREST)
- Morphological clustering of buildings by `[area, height, shapefactor, epoch, use]`
- Vector tile service (`pg_tileserv` or `Martin`) as a high-performance alternative to WMS

---

## References

- [GDAL / ogr2ogr documentation](https://gdal.org/en/stable/programs/ogr2ogr.html)
- [PostgREST documentation](https://docs.postgrest.org/en/v12/)
- [GeoServer REST API reference](https://docs.geoserver.org/stable/en/user/rest/)
- [Kartoza GeoServer Docker image](https://github.com/kartoza/docker-geoserver)
- [MODERATE Project — DBSM R2023 PoC](https://github.com/MODERATE-Project/poc-dbsm-r2023)
- [OGC SLD specification](https://www.ogc.org/standard/sld/)
- [Task runner](https://taskfile.dev)
