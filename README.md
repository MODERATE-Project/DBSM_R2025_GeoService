# DBSM GeoService

Containerized geospatial microservice stack for managing, publishing and querying the **Database of Structures and Buildings Mapping (DBSM)** — a pan-European building footprint dataset covering all 27 EU Member States in two versions: R2023 (v1) and R2025 (v2).

Built as a Proof of Concept for the [MODERATE](https://github.com/MODERATE-Project/poc-dbsm-r2023) European project.

---

## Table of Contents

- [Architecture](#architecture)
- [Dataset Overview](#dataset-overview)
  - [Version Comparison](#version-comparison-v1-vs-v2)
  - [Available Countries](#available-countries)
  - [Downloading Datasets](#downloading-datasets)
  - [File Naming Convention](#file-naming-convention)
  - [Licence](#licence)
- [Prerequisites](#prerequisites)
- [Deployment Guide](#deployment-guide)
  - [Step 1 — Clone the repository](#step-1--clone-the-repository)
  - [Step 2 — Configure the environment](#step-2--configure-the-environment)
  - [Step 3 — Build and start the stack](#step-3--build-and-start-the-stack)
  - [Step 4 — Initialise GeoServer](#step-4--initialise-geoserver)
  - [Step 5 — Download datasets](#step-5--download-datasets)
  - [Step 6 — Import data](#step-6--import-data)
  - [Step 7 — Set up the QGIS desktop client](#step-7--set-up-the-qgis-desktop-client)
- [Service Access](#service-access)
- [Environment Variables Reference](#environment-variables-reference)
- [Repository Structure](#repository-structure)
- [Workflows](#workflows)
- [Task Reference](#task-reference)
- [API Reference](#api-reference)
- [Swagger UI — Verified Call Examples](#swagger-ui--verified-call-examples)
- [Data Schema](#data-schema)
- [GeoServer](#geoserver)
- [QGIS — Desktop Client Guide](#qgis--desktop-client-guide)
- [Performance Considerations](#performance-considerations)
- [Known Issues & Troubleshooting](#known-issues--troubleshooting)
- [Roadmap](#roadmap)
- [References](#references)

---

## Architecture

```
┌─ Docker Compose (dbsm-geoservice-net) ────────────────────────┐
│                                                                │
│   PostgreSQL 16 + PostGIS 3          :3500                    │
│              │                                                 │
│              ├──► PostgREST v12.2.8  :3501                    │
│              │         │                                       │
│              │         └──► Swagger UI v5.21.0  :3504         │
│              │                                                 │
│              ├──► GeoServer 2.24.2   :3503                    │
│              │                                                 │
│              └──► PgAdmin 4          :3502                    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**PostgreSQL** is the single source of truth. All other services read from it directly. Two schemas partition the data by dataset version:

| Schema | Dataset | Description |
|--------|---------|-------------|
| `v1` | DBSM R2023 | Geometry + source only — lightweight, geometry-focused |
| `v2` | DBSM R2025 | Full attribute set: height, use, epoch, compactness, JSON metadata |

---

## Dataset Overview

The DBSM (Database of Structures and Buildings Mapping) is produced and maintained by the Joint Research Centre (JRC) of the European Commission. It provides pan-European building footprint data intended for energy efficiency analysis, urban planning, and environmental modelling under the [MODERATE](https://moderate-project.eu/) project.

**Data catalogue:** [https://data.jrc.ec.europa.eu/collection/id-00382](https://data.jrc.ec.europa.eu/collection/id-00382)

### Version Comparison: v1 vs v2

Understanding the difference between versions is essential for selecting the right import strategy. The two versions are complementary, not interchangeable.

| Feature | v1 — DBSM R2023 | v2 — DBSM R2025 |
|---------|----------------|----------------|
| **Release year** | 2023 | 2025 |
| **Coverage** | 27 EU Member States | 27 EU Member States + outermost regions (Azores, Madeira, Canary Islands) |
| **Building count** | ~340 million footprints | ~286 million footprints (after deduplication) |
| **Geometry** | MultiPolygon, EPSG:3035 | MultiPolygon, EPSG:3035 (improved accuracy) |
| **Height** | Not included | Per-building height in metres |
| **Use type** | Not included | Residential / Non-residential / Unknown |
| **Construction epoch** | Not included | Decade bin (pre-1980 to 2020+) |
| **Compactness** | Not included | Shape factor (surface-to-volume ratio) |
| **Source metadata** | Not included | JSON fields: EuroBuildings, OpenStreetMap, Microsoft Buildings |
| **Geometry quality** | First-generation merge | 54M duplicates/errors removed, cross-validated against GHS-BUILT-S |
| **PostgreSQL schema** | `v1` | `v2` |
| **Use case** | Baseline geometry, version comparison | Full analysis, API queries, QGIS exploration |

**Recommendation:** Import v2 for all primary use cases. Import v1 only when you need to compare building stock changes between the two dataset generations (using the `compare_versions` API endpoint). All advanced PostgREST RPC functions and QGIS actions operate exclusively on the v2 schema.

#### v1 attribute table

| Column | Type | Description |
|--------|------|-------------|
| `fid` | integer | Feature identifier |
| `source` | varchar | Data source code |
| `geom` | geometry(MultiPolygon, 3035) | Building footprint |

#### v2 attribute table

| Column | Type | Description |
|--------|------|-------------|
| `fid` | integer | Primary key |
| `unique_id` | varchar | Global ID: `{NUTS3}_{grid}_{lon}_{lat}` format |
| `source` | varchar | Source priority: `eub` (EuroBuildings) › `osm` (OpenStreetMap) › `msb` (Microsoft Buildings) |
| `area` | float | Footprint area in m² |
| `height` | float | Building height in metres (derived from multiple sources) |
| `shapefactor` | float | Surface-to-volume ratio (m²/m³) — measure of thermal compactness; lower = more compact |
| `epoch` | bigint | Construction period: `0`=unknown, `1`=pre-1980, `2`=1980–1989, `3`=1990–1999, `4`=2000–2009, `5`=2010+ |
| `use` | bigint | Building use: `0`=unknown, `1`=residential, `2`=non-residential |
| `eub_json` | varchar | EuroBuildings metadata JSON: `height`, `age`, `type`, `building`, `levels`, `roof-shape` |
| `osm_json` | varchar | OpenStreetMap metadata JSON |
| `msb_json` | varchar | Microsoft Buildings metadata JSON |
| `geom` | geometry(MultiPolygon, 3035) | Building footprint in EPSG:3035 (ETRS89-LAEA) |

Example `eub_json` content:
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

Field availability varies by country and building. The `age` field (exact construction year, when available) is more precise than `epoch` (decade bin).

---

### Available Countries

Both v1 and v2 cover all **27 EU Member States**. The table below lists them with the exact filenames expected by the import pipeline (after the [rename step](#file-naming-convention) for v2).

Sizes shown are the GeoPackage file sizes on the JRC FTP server. PostgreSQL will use approximately 1.5× that space after import (uncompressed storage + GIST spatial indexes).

| Country | Task name | v1 file | v1 size | v2 file (after rename) | v2 size |
|---------|-----------|---------|---------|----------------------|---------|
| Austria | `austria` | `dbsm-v1-austria-merge.gpkg` | 1.0 GB | `dbsm-v2-austria-R2025.gpkg` | 3.6 GB |
| Belgium | `belgium` | `dbsm-v1-belgium-merge.gpkg` | 1.6 GB | `dbsm-v2-belgium-R2025.gpkg` | 4.8 GB |
| Bulgaria | `bulgaria` | `dbsm-v1-bulgaria-merge.gpkg` | 699 MB | `dbsm-v2-bulgaria-R2025.gpkg` | 1.8 GB |
| Croatia | `croatia` | `dbsm-v1-croatia-merge.gpkg` | 516 MB | `dbsm-v2-croatia-R2025.gpkg` | 1.3 GB |
| Cyprus | `cyprus` | `dbsm-v1-cyprus-merge.gpkg` | 138 MB | `dbsm-v2-cyprus-R2025.gpkg` | 632 MB |
| Czechia | `czechia` | `dbsm-v1-czechia-merge.gpkg` | 1.2 GB | `dbsm-v2-czechia-R2025.gpkg` | 5.8 GB |
| Denmark | `denmark` | `dbsm-v1-denmark-merge.gpkg` | 964 MB | `dbsm-v2-denmark-R2025.gpkg` | 2.9 GB |
| Estonia | `estonia` | `dbsm-v1-estonia-merge.gpkg` | 198 MB | `dbsm-v2-estonia-R2025.gpkg` | 1.7 GB |
| Finland | `finland` | `dbsm-v1-finland-merge.gpkg` | 860 MB | `dbsm-v2-finland-R2025.gpkg` | 11 GB |
| France | `france` | `dbsm-v1-france-merge.gpkg` | 12 GB | `dbsm-v2-france-R2025.gpkg` | 27 GB |
| Germany | `germany` | `dbsm-v1-germany-merge.gpkg` | 8.8 GB | `dbsm-v2-germany-R2025.gpkg` | 49 GB |
| Greece | `greece` | `dbsm-v1-greece-merge.gpkg` | 1.0 GB | `dbsm-v2-greece-R2025.gpkg` | 2.7 GB |
| Hungary | `hungary` | `dbsm-v1-hungary-merge.gpkg` | 1.0 GB | `dbsm-v2-hungary-R2025.gpkg` | 2.7 GB |
| Ireland | `ireland` | `dbsm-v1-ireland-merge.gpkg` | 674 MB | `dbsm-v2-ireland-R2025.gpkg` | 1.7 GB |
| **Italy** ★ | `italy` | `dbsm-v1-italy-merge.gpkg` | 4.6 GB | `dbsm-v2-italy-R2025.gpkg` | 23 GB |
| Latvia | `latvia` | `dbsm-v1-latvia-merge.gpkg` | 209 MB | `dbsm-v2-latvia-R2025.gpkg` | 629 MB |
| Lithuania | `lithuania` | `dbsm-v1-lithuania-merge.gpkg` | 443 MB | `dbsm-v2-lithuania-R2025.gpkg` | 1.3 GB |
| **Luxembourg** ★ | `luxembourg` | `dbsm-v1-luxembourg-merge.gpkg` | 46 MB | `dbsm-v2-luxembourg-R2025.gpkg` | 92 MB |
| **Malta** ★ | `malta` | `dbsm-v1-malta-merge.gpkg` | 16 MB | `dbsm-v2-malta-R2025.gpkg` | 37 MB |
| Netherlands | `netherlands` | `dbsm-v1-netherlands-merge.gpkg` | 2.7 GB | `dbsm-v2-netherlands-R2025.gpkg` | 24 GB |
| Poland | `poland` | `dbsm-v1-poland-merge.gpkg` | 4.3 GB | `dbsm-v2-poland-R2025.gpkg` | 11 GB |
| Portugal | `portugal` | `dbsm-v1-portugal-merge.gpkg` | 1.1 GB | `dbsm-v2-portugal-R2025.gpkg` | 2.9 GB |
| Romania | `romania` | `dbsm-v1-romania-merge.gpkg` | 1.8 GB | `dbsm-v2-romania-R2025.gpkg` | 5.8 GB |
| Slovakia | `slovakia` | `dbsm-v1-slovakia-merge.gpkg` | 659 MB | `dbsm-v2-slovakia-R2025.gpkg` | 7.2 GB |
| Slovenia | `slovenia` | `dbsm-v1-slovenia-merge.gpkg` | 243 MB | `dbsm-v2-slovenia-R2025.gpkg` | 2.5 GB |
| **Spain** ★ | `spain` | `dbsm-v1-spain-merge.gpkg` | 2.0 GB | `dbsm-v2-spain-R2025.gpkg` | 10 GB |
| Sweden | `sweden` | `dbsm-v1-sweden-merge.gpkg` | 1.1 GB | `dbsm-v2-sweden-R2025.gpkg` | 3.3 GB |

**v1 total:** ~50 GB (GeoPackage) → ~75 GB in PostgreSQL  
**v2 total:** ~208 GB (GeoPackage) → ~310 GB in PostgreSQL  
**Both versions, all 27 countries:** ~258 GB (GeoPackage) → ~390 GB in PostgreSQL

★ Countries pre-configured in the reference QGIS project and used in all verified API examples.

> **Note on adding countries beyond the pre-configured four:** Any country can be imported and queried via the API and GeoServer. The QGIS project and its Python actions are pre-wired for Italy, Spain, Malta and Luxembourg (and additionally Austria, Belgium, Germany, France, Portugal in the commune-level action). To add other countries to QGIS actions, see [Extending the QGIS project to new countries](#extending-the-project-to-new-countries).

---

### Downloading Datasets

Datasets are distributed by the JRC through their open data portal and a public FTP server. No registration is required.

**Data catalogue (root):** [https://data.jrc.ec.europa.eu/collection/id-00382](https://data.jrc.ec.europa.eu/collection/id-00382)

#### v1 — DBSM R2023

- **Dataset page:** [https://data.jrc.ec.europa.eu/dataset/60c6b14d-3dda-4034-b461-390dc8ed8665](https://data.jrc.ec.europa.eu/dataset/60c6b14d-3dda-4034-b461-390dc8ed8665)
- **FTP per-country directory:** [https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/DBSM/DBSM_Europe_R2023/per-country/](https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/DBSM/DBSM_Europe_R2023/per-country/)
- **Full archive (all countries, ~20 GB):** available on the dataset page above
- **Technical publication:** [JRC135616](https://publications.jrc.ec.europa.eu/repository/handle/JRC135616)

#### v2 — DBSM R2025

- **Dataset page:** [https://data.jrc.ec.europa.eu/dataset/a601a4a8-9289-4fc4-983a-25d54f957f3a](https://data.jrc.ec.europa.eu/dataset/a601a4a8-9289-4fc4-983a-25d54f957f3a)
- **FTP per-country directory:** [https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/DBSM/DBSM_Europe_R2025/per-country/](https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/DBSM/DBSM_Europe_R2025/per-country/)
- **Technical publication:** [JRC142133](https://publications.jrc.ec.europa.eu/repository/handle/JRC142133) (DOI: 10.2760/0629989)

To download individual countries via the command line:

```bash
# v1 — Malta (example)
wget https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/DBSM/DBSM_Europe_R2023/per-country/dbsm-v1-malta-merge.gpkg \
     -P ./datasets/

# v2 — Malta (example) — note the filename does NOT include "v2-", rename is required (see below)
wget https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/DBSM/DBSM_Europe_R2025/per-country/dbsm-malta-R2025.gpkg \
     -P ./datasets/
```

---

### File Naming Convention

The import pipeline (`import_data.sh`) and the `task import` command expect files in `./datasets/` to follow this naming convention:

| Version | Expected filename pattern | Example |
|---------|--------------------------|---------|
| v1 | `dbsm-v1-{country}-merge.gpkg` | `dbsm-v1-malta-merge.gpkg` |
| v2 | `dbsm-v2-{country}-R2025.gpkg` | `dbsm-v2-malta-R2025.gpkg` |

v1 files downloaded from the JRC FTP already follow this pattern. **v2 files from the FTP are named `dbsm-{country}-R2025.gpkg` (without `v2-`) and must be renamed** before importing:

```bash
cd datasets/
# Rename all R2025 files to include the v2- prefix
for f in dbsm-*-R2025.gpkg; do
  mv "$f" "dbsm-v2-${f#dbsm-}"
done
# dbsm-malta-R2025.gpkg  →  dbsm-v2-malta-R2025.gpkg
```

The `{country}` component must be the lowercase country name as it will become the PostgreSQL table name (e.g. `spain` → `v2.spain`).

---

### Licence

Both DBSM versions are released under the **Open Database Licence (ODbL) v1.0**.

Key terms:
- Commercial use is permitted
- Attribution required — include the licence text and maintain copyright notices
- Share-alike — derivative databases distributed publicly must carry ODbL or a compatible licence

Full licence text: [https://opendatacommons.org/licenses/odbl/1-0/](https://opendatacommons.org/licenses/odbl/1-0/)

---

## Prerequisites

| Tool | Minimum version | Purpose | Installation |
|------|-----------------|---------|-------------|
| Docker Engine | 24 | Container runtime | [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) |
| Docker Compose | 2 | Multi-container orchestration | Included with Docker Desktop |
| Task | any | CLI task runner | `sh -c "$(curl -sL https://taskfile.dev/install.sh)" -- -d -b /usr/local/bin` |
| GDAL / ogr2ogr | 3.x | GeoPackage → PostGIS import | `sudo apt install gdal-bin` |
| Python 3 + requests | 3.8+ | GeoServer REST automation | `pip install requests` |

**QGIS 3.x** is optional — required only for the desktop client integration.

### Hardware recommendations

| Scope | RAM | Disk |
|-------|-----|------|
| Malta (37 MB) + Luxembourg (92 MB) — recommended for first test | 4 GB | < 1 GB in PostgreSQL |
| Spain (10 GB) + Italy (23 GB) v2 only | 16–32 GB | ~50 GB in PostgreSQL |
| All 27 countries, v2 only (~208 GB GeoPackage) | 32–64 GB | ~310 GB in PostgreSQL |
| All 27 countries, v1 + v2 (~258 GB GeoPackage) | 64+ GB | ~390 GB in PostgreSQL |

---

## Deployment Guide

This section covers the complete deployment process from a fresh machine with no prior setup. Follow the steps in order.

---

### Step 1 — Clone the repository

```bash
git clone git@github.com:fundacionctic/1530_MODERATE_DBSM_R2023_GeoService_HE_Oferta_21_00209.git
cd 1530_MODERATE_DBSM_R2023_GeoService_HE_Oferta_21_00209
```

---

### Step 2 — Configure the environment

All runtime configuration is controlled by the `.env` file. A template with default values is committed as `.env.default`.

```bash
cp .env.default .env
```

Open `.env` in a text editor. For a first deployment on a local machine you can use the defaults as-is. For any shared or production-like environment, change the passwords before running anything else — see [Environment Variables Reference](#environment-variables-reference) for a description of every variable.

**Minimum edits for a non-default deployment:**

```bash
# .env — change at minimum these five values
POSTGRES_PASSWORD=<strong-password>
PGRST_DB_AUTHENTICATOR_PASSWORD=<same-strong-password>   # must match POSTGRES_PASSWORD for PostgREST
PGADMIN_DEFAULT_EMAIL=you@yourorg.com
PGADMIN_DEFAULT_PASSWORD=<another-strong-password>
GEOSERVER_ADMIN_PASSWORD=<another-strong-password>
```

> `PGRST_DB_AUTHENTICATOR_PASSWORD` and `POSTGRES_PASSWORD` do not need to be the same value, but the `authenticator` database role created during init will use whatever is set in `PGRST_DB_AUTHENTICATOR_PASSWORD`. Ensure consistency — both values come from the same `.env`.

---

### Step 3 — Build and start the stack

Make the database init script executable (required by the PostgreSQL Docker entrypoint):

```bash
chmod +x initdb/02_postgrest.sh
```

Build the custom PostgreSQL image and start all five services:

```bash
task up
```

Wait 30–60 seconds for all containers to initialise, then verify their health:

```bash
task ps
```

Expected output — all services should show `healthy` or `running`:

```
NAME             STATUS
dbsm_postgres    Up (healthy)
dbsm_postgrest   Up
dbsm_pgadmin     Up
dbsm_swagger     Up
dbsm_geoserver   Up (healthy)
```

> GeoServer takes 60–90 seconds on first boot. If it shows `starting` initially, wait a moment and re-run `task ps`.

If a container does not reach `healthy`, stream its logs:

```bash
docker logs dbsm_postgres   # or dbsm_geoserver, dbsm_postgrest, etc.
```

Verify the API responds:

```bash
curl -s http://localhost:3501/ | python3 -m json.tool | head -10
# Should return the PostgREST OpenAPI description
```

---

### Step 4 — Initialise GeoServer

Create shared GeoServer resources (workspaces, datastores, SLD styles). This step is idempotent and only needs to run once per clean deployment, or after a `task clean:nuke`.

```bash
task geoserver:init VERSION=v2
task geoserver:init VERSION=v1
```

Each command creates: workspace → datastore (PostGIS connection) → SLD style. GeoServer must be healthy before running these.

---

### Step 5 — Download datasets

Create the datasets directory if it does not exist:

```bash
mkdir -p datasets
```

Download the countries you want to work with. **Malta and Luxembourg are recommended for an initial test** — they are the smallest datasets and complete quickly.

```bash
# v2 — Malta (37 MB, fastest import, good for testing)
wget https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/DBSM/DBSM_Europe_R2025/per-country/dbsm-malta-R2025.gpkg \
     -O datasets/dbsm-v2-malta-R2025.gpkg

# v2 — Luxembourg (~200 MB)
wget https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/DBSM/DBSM_Europe_R2025/per-country/dbsm-luxembourg-R2025.gpkg \
     -O datasets/dbsm-v2-luxembourg-R2025.gpkg

# v2 — Spain (~9 GB, large — download in background)
wget https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/DBSM/DBSM_Europe_R2025/per-country/dbsm-spain-R2025.gpkg \
     -O datasets/dbsm-v2-spain-R2025.gpkg

# v2 — Italy (~22 GB, very large)
wget https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/DBSM/DBSM_Europe_R2025/per-country/dbsm-italy-R2025.gpkg \
     -O datasets/dbsm-v2-italy-R2025.gpkg
```

Note: files are downloaded directly with the correct name using `-O`. If you download without specifying the output name, rename them afterward (see [File Naming Convention](#file-naming-convention)).

For v1 files (optional — only needed for version comparison):

```bash
wget https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/DBSM/DBSM_Europe_R2023/per-country/dbsm-v1-malta-merge.gpkg \
     -P datasets/
```

---

### Step 6 — Import data

Import a single country (recommended order: Malta first to validate the pipeline):

```bash
task import CITY=malta VERSION=v2
```

This single command runs three steps automatically:
1. **Import** — `ogr2ogr` converts `./datasets/dbsm-v2-malta-R2025.gpkg` into table `v2.malta` in PostgreSQL and grants SELECT permissions to `web_anon`.
2. **Publish** — `gsconfig.py` creates the GeoServer FeatureType, recalculates the bounding box, assigns the SLD style, and rebuilds the LayerGroup.
3. **Reload** — PostgREST is signalled to refresh its schema cache, making `v2.malta` immediately accessible via the API.

Verify the import was successful:

```bash
# Check the layer is visible in GeoServer
task geoserver:verify CITY=malta VERSION=v2

# Check the API returns data
curl -s -X POST http://localhost:3501/rpc/country_statistics \
     -H "Content-Type: application/json" \
     -d '{"country_table":"malta"}'
```

Import additional countries one by one:

```bash
task import CITY=luxembourg VERSION=v2
task import CITY=spain VERSION=v2
task import CITY=italy VERSION=v2
```

Or bulk-import all `.gpkg` files present in `./datasets/` at once:

```bash
task import:all VERSION=v2
```

In `CITY=all` mode the schema is inferred from the filename (`dbsm-v2-…` → schema `v2`, `dbsm-v1-…` → schema `v1`). The `VERSION` argument only controls which GeoServer workspace is used for the publish step.

---

### Step 7 — Set up the QGIS desktop client

The repository includes a ready-to-open QGIS project at `qgis_project/dbsm_demo.qgs`. It comes pre-configured for Malta, Luxembourg, Spain, and Italy.

#### 7.1 Install QGIS

Download and install **QGIS 3.x LTR** (Long Term Release) from [qgis.org/download](https://qgis.org/download/). The project was saved with QGIS 3.44; any 3.x version should work.

| Platform | Command / Link |
|----------|---------------|
| Ubuntu / Debian | `sudo apt install qgis qgis-plugin-grass` |
| Fedora / RHEL | `sudo dnf install qgis` |
| macOS | Download `.dmg` from qgis.org |
| Windows | Download installer from qgis.org |

#### 7.2 Download the Eurostat GISCO boundary files

The project uses two external reference layers published by [Eurostat GISCO](https://ec.europa.eu/eurostat/web/gisco/geodata/administrative-units) (Geographical Information and Statistical Data). Both are official EU administrative boundary datasets distributed via the GISCO services API.

| Layer | File | Scale | CRS | Source | Purpose in project |
|-------|------|-------|-----|--------|--------------------|
| Country boundaries | `CNTR_RG_01M_2016_3035.gpkg` | 1:1M | EPSG:3035 | GISCO Countries 2016 | Triggers country-level load actions |
| Commune boundaries | `COMM_RG_01M_2016_3035.geojson` | 1:1M | EPSG:3035 | GISCO Communes 2016 | Triggers commune-level load actions |

**Licence:** © EuroGeographics for the administrative boundaries. Non-commercial use; source attribution required. Commercial use requires contacting [EuroGeographics](https://www.eurogeographics.org/) directly.

**Option A — Command line (recommended, no browser needed):**

```bash
# Country boundaries GeoPackage (~4 MB)
wget "https://gisco-services.ec.europa.eu/distribution/v2/countries/gpkg/CNTR_RG_01M_2016_3035.gpkg" \
     -P qgis_project/

# Commune boundaries GeoJSON (~80 MB)
wget "https://gisco-services.ec.europa.eu/distribution/v2/communes/geojson/COMM_RG_01M_2016_3035.geojson" \
     -P qgis_project/
```

**Option B — Web interface:** Open the GISCO [Administrative Units download page](https://ec.europa.eu/eurostat/web/gisco/geodata/administrative-units), select the section (**Countries** or **Communes**) and apply the following filter values exactly — the interface does not indicate which combination produces a valid file, so all five parameters must match:

| Parameter | Value for `CNTR_RG_01M_2016_3035.gpkg` | Value for `COMM_RG_01M_2016_3035.geojson` |
|-----------|----------------------------------------|-------------------------------------------|
| **Year** | 2016 | 2016 |
| **File format** | GeoPackage | GeoJSON |
| **Geometry type** | Polygons (RG) | Polygons (RG) |
| **Scale** | 01M | 01M |
| **Coordinate reference system** | EPSG: 3035 | EPSG: 3035 |

Save the downloaded files into `qgis_project/` (the same directory as `dbsm_demo.qgs`). The project references them with a relative path, so placing them there means QGIS will find them automatically without any manual repair step.

If the files end up elsewhere, or if QGIS reports missing layers for `CNTR_RG_01M_2016_3035` or `COMM_RG_01M_2016_3035`, right-click the broken layer → **Repair Data Source** and point to where you saved the files.

#### 7.3 Configure macro permissions (first time only)

The project uses a Python macro to automatically apply interactive actions to all v2 building layers. QGIS blocks macros by default. Configure this before opening the project:

1. In QGIS, open **Settings → Options → General**
2. Find the **"Enable macros"** dropdown
3. Set it to **"Ask"** (shows a confirmation dialog on each open) or **"Always"** (loads macros silently without asking)
4. Click **OK**

If this setting is left at **"Never"**, QGIS will silently skip the macro and building-level actions will not be available.

#### 7.4 Open the project

1. Go to **Project → Open…**
2. Navigate to `qgis_project/dbsm_demo.qgs` and open it
3. If macros are set to **"Ask"**, a security dialog will appear — click **Enable macros**
4. QGIS will prompt for a database password if connections are not stored — enter `postgres` (or the value of `POSTGRES_PASSWORD` from your `.env`)

> **Note on loading time:** Opening the project for the first time may take 30–60 seconds while QGIS connects to PostGIS and loads layer metadata. This is normal, especially for large datasets like Spain or Italy. Subsequent opens are faster.

If the connection parameters in your `.env` differ from the defaults (different host, port, password), update the layer connections: right-click a layer → **Properties → Source** → edit the connection URI.

See the full [QGIS — Desktop Client Guide](#qgis--desktop-client-guide) section for usage instructions.

---

## Service Access

All services are deployed on `localhost` by default. Ports are defined in `.env` and can be changed before the first startup. For remote access, set `SERVER_HOST` in `.env` to the server's IP address or hostname (see [Environment Variables Reference](#environment-variables-reference)).

| Service | URL / connection | Default credentials | Purpose |
|---------|-----------------|---------------------|---------|
| **PostgREST API** | http://localhost:3501 | Public — no authentication | REST API for querying building data |
| **Swagger UI** | http://localhost:3504 | Public — no authentication | Interactive API documentation and testing |
| **GeoServer** | http://localhost:3503/geoserver/web | `admin` / `geoserver` | WMS/WFS map server, layer management |
| **PgAdmin** | http://localhost:3502 | `user@domain.com` / `postgres` | PostgreSQL web GUI |
| **PostgreSQL** | `localhost:3500`, db `dbsm` | `dbsm_admin` / `postgres` | Direct database access (psql, pgAdmin, etc.) |
| **QGIS project** | `localhost:3500`, db `dbsm` | `dbsm_admin` / `postgres` | Desktop client — connects directly to PostGIS |

> All credentials shown are the defaults from `.env.default`. If you edited `.env` before starting, use those values instead. Credentials are **never stored in the repository** — only `.env.default` (with placeholder-level defaults) is committed.
>
> **QGIS note:** When opening `qgis_project/dbsm_demo.qgs`, QGIS may prompt for the database password on startup (for layers whose datasource URI does not embed it). Enter the value of `POSTGRES_PASSWORD` from your `.env` — `postgres` by default. If you changed the password, update each layer's datasource via **Layer → Properties → Source** or re-save the project with the new credentials stored.

---

## Environment Variables Reference

All variables live in `.env`. The file is loaded by both Docker Compose and the Taskfile automatically. Copy `.env.default` to `.env` and edit before the first `task up`.

### Stack

| Variable | Default | Description |
|----------|---------|-------------|
| `STACK_NAME` | `dbsm-geoservice` | Docker Compose project name and network prefix |
| `SERVER_HOST` | `localhost` | Public hostname or IP used by Swagger UI to reach the API. Set to the server's address when deploying on a shared or remote host |

### PostgreSQL

| Variable | Default | Description |
|----------|---------|-------------|
| `PG_VERSION` | `16` | PostgreSQL image version |
| `PG_PORT` | `3500` | Host port mapped to the container's 5432 |
| `PG_HOST` | `localhost` | Host used by `import_data.sh` to reach PostgreSQL |
| `PG_CONTAINER` | `dbsm_postgres` | Docker container name |
| `POSTGRES_USER` | `dbsm_admin` | Superuser created on DB init |
| `POSTGRES_PASSWORD` | `postgres` | Superuser password — **change for any shared deployment** |
| `POSTGRES_DB` | `dbsm` | Database name |

### PgAdmin

| Variable | Default | Description |
|----------|---------|-------------|
| `PGADMIN_VERSION` | `9.2` | PgAdmin image version |
| `PGADMIN_PORT` | `3502` | Host port for the PgAdmin web UI |
| `PGADMIN_DEFAULT_EMAIL` | `user@domain.com` | Login e-mail for PgAdmin — **change this** |
| `PGADMIN_DEFAULT_PASSWORD` | `postgres` | PgAdmin login password — **change this** |

### PostgREST

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGREST_VERSION` | `v12.2.8` | PostgREST image version |
| `POSTGREST_PORT` | `3501` | Host port for the REST API |
| `PGRST_DB_AUTHENTICATOR_PASSWORD` | `postgres` | Password for the `authenticator` database role. **Must match the value stored in the database** (set during `02_postgrest.sh` init). Change both together using `task db:apply-sql` |
| `PGRST_DB_ANON_ROLE` | `web_anon` | Database role used for unauthenticated API requests |
| `PGRST_DB_SCHEMA` | `v2` | Schema exposed as REST resources (direct table access) |
| `PGRST_OPENAPI_MODE` | `follow-privileges` | OpenAPI generation mode |

### Swagger UI

| Variable | Default | Description |
|----------|---------|-------------|
| `SWAGGER_VERSION` | `v5.21.0` | Swagger UI image version |
| `SWAGGER_PORT` | `3504` | Host port for the Swagger UI |

### GeoServer

| Variable | Default | Description |
|----------|---------|-------------|
| `GEOSERVER_VERSION` | `2.24.2` | GeoServer image version |
| `GEOSERVER_PORT` | `3503` | Host port for GeoServer |
| `GEOSERVER_ADMIN_USER` | `admin` | GeoServer admin username |
| `GEOSERVER_ADMIN_PASSWORD` | `geoserver` | GeoServer admin password — **change this** |

### Changing passwords after first deployment

The PostgreSQL `authenticator` role password is set once during database init from `PGRST_DB_AUTHENTICATOR_PASSWORD`. If you change the password in `.env` after the database already exists, you must also update the role in the live database:

```bash
# Update the role password without destroying data
docker exec -i dbsm_postgres psql -U dbsm_admin -d dbsm \
  -c "ALTER ROLE authenticator PASSWORD 'your-new-password';"

# Then restart PostgREST so it reconnects with the new password
docker restart dbsm_postgrest
```

---

## Repository Structure

```
.
├── docker-compose.yml          # Service definitions, network, volumes
├── Dockerfile.postgis          # Custom PostgreSQL 16 + PostGIS 3 image
├── Taskfile.yml                # CLI task automation (loads .env automatically)
├── import_data.sh              # ogr2ogr pipeline: GeoPackage → PostGIS
├── gsconfig.py                 # GeoServer REST API automation (idempotent)
├── .env.default                # Environment template (committed, safe to share)
├── .env                        # Active environment — gitignored, never commit
├── servers.json                # PgAdmin server auto-discovery preset
├── pg_service.conf             # PostgreSQL libpq service alias (for psql CLI)
│
├── initdb/
│   ├── 01_postgis.sql          # Creates PostGIS extension + v1/v2 schemas
│   ├── 02_postgrest.sh         # Creates web_anon and authenticator roles (reads password from env)
│   └── 03_api_functions.sql    # Seven PL/pgSQL RPC functions for PostgREST
│
├── styles/
│   ├── dbsm_buildings.sld      # v2 SLD style: 5-band height classification
│   └── dbsm_buildings_v1.sld   # v1 SLD style: flat colour (no height)
│
├── qgis_project/
│   └── dbsm_demo.qgs           # QGIS 3 demo project (Malta, Luxembourg, Spain, Italy)
│
├── datasets/                   # GeoPackage source files — gitignored, ~240 GB total
├── postgres_data/              # PostgreSQL persistent volume — gitignored
├── geoserver_data/             # GeoServer persistent volume — gitignored
└── pgadmin_data/               # PgAdmin persistent volume — gitignored
```

**`docker-compose.yml`** — Five services on a shared bridge network (`dbsm-geoservice-net`). PostgreSQL has a health check; all other services wait for it before starting. The `initdb/` scripts are bind-mounted into the PostgreSQL init directory and run automatically on the first boot of an empty volume.

**`Taskfile.yml`** — Single-command interface for all operations. Reads `.env` via `dotenv: ['.env']`. See [Task Reference](#task-reference).

**`import_data.sh`** — Validates prerequisites (ogr2ogr, PostgreSQL connectivity, datasets directory), runs `ogr2ogr` to import one GeoPackage or all of them, then grants permissions to `web_anon`.

**`gsconfig.py`** — Idempotent GeoServer automation: workspace, datastore, SLD upload, FeatureType publication, bounding-box recalculation, LayerGroup rebuild. Uses DELETE + POST for LayerGroups to work around a bug in GeoServer 2.24.x.

**`initdb/01_postgis.sql`** — Activates the PostGIS extension and creates `v1` and `v2` schemas owned by `dbsm_admin`. Executed once on first container startup.

**`initdb/02_postgrest.sh`** — Creates the `web_anon` (read-only, no login) and `authenticator` (login) roles. The `authenticator` password is read from the `PGRST_DB_AUTHENTICATOR_PASSWORD` environment variable — no hardcoded credentials. Uses `CREATE ROLE IF NOT EXISTS` so it is safe to re-run.

**`initdb/03_api_functions.sql`** — Seven PL/pgSQL functions exposed as HTTP POST endpoints by PostgREST. All functions use `SECURITY DEFINER` with an explicit `search_path` to prevent privilege escalation.

**`qgis_project/dbsm_demo.qgs`** — Ready-to-open QGIS 3 project (saved with 3.44). Connects to `localhost:3500` / `dbsm` and provides pre-configured layers and Python actions for interactive exploration.

---

## Workflows

### 1. Initial Setup

```bash
task up                          # Build images and start all services
task geoserver:init VERSION=v2   # Create workspace, datastore, style for v2
task geoserver:init VERSION=v1   # Same for v1
```

`geoserver:init` is idempotent — safe to re-run if interrupted.

### 2. Importing a Country

```bash
task import CITY=malta VERSION=v2
```

This runs three steps in sequence:
1. **Import** — converts `./datasets/dbsm-v2-malta-R2025.gpkg` into `v2.malta` in PostgreSQL
2. **Publish** — creates or updates the GeoServer layer, recalculates bbox, assigns SLD, rebuilds LayerGroup
3. **Reload** — signals PostgREST to refresh its schema cache

### 3. Bulk Import

```bash
task import:all VERSION=v2
```

Iterates over all `.gpkg` files in `./datasets/`. Schema (`v1` or `v2`) is inferred from the filename prefix. The `VERSION` argument controls only the GeoServer publish step.

### 4. Updating SQL Functions

After modifying any file in `initdb/`:

```bash
task db:apply-sql
```

Re-applies all init files in order and reloads PostgREST. Idempotent — `CREATE ROLE IF NOT EXISTS` prevents errors on an existing database.

### 5. Verifying a Publication

```bash
task geoserver:verify CITY=malta VERSION=v2   # Check WMS GetCapabilities
task geoserver:status VERSION=v2              # List all published layers
```

### 6. Full Reset

```bash
task db:reset   # WARNING: destroys all imported data and volumes
```

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

Base URL: `http://localhost:3501`

PostgREST exposes two types of endpoints:

- **RPC functions** — `POST /rpc/<function_name>` — custom queries defined in `initdb/03_api_functions.sql`
- **Direct table access** — `GET /<table_name>` — auto-generated from the `v2` schema (configured by `PGRST_DB_SCHEMA`)

Interactive documentation and live testing: **Swagger UI at http://localhost:3504**

The OpenAPI specification is auto-generated by PostgREST at `http://localhost:3501/openapi.json`.

### HTTP conventions

| Convention | Value |
|-----------|-------|
| Request content-type (POST) | `application/json` |
| Response format | `application/json` (default) or `application/geo+json` |
| Authentication | None — all endpoints are public (`web_anon` role) |
| Geometry encoding | Base64 WKB by default; use `Accept: application/geo+json` for GeoJSON |

### RPC Endpoints

| Endpoint | Input | Returns | Use case |
|----------|-------|---------|----------|
| `/rpc/buildings_in_bbox` | bbox (WGS84), country | features + geom | Map viewport load |
| `/rpc/buildings_nearby` | lat/lon, radius_m, country | features + distance | Proximity search |
| `/rpc/country_statistics` | country | aggregate stats | Dashboard KPIs |
| `/rpc/buildings_by_use` | country, use_type | features + geom | Filter by residential/other |
| `/rpc/compare_versions` | country | fid + status (NEW/MODIFIED/UNCHANGED) | v1 vs v2 diff |
| `/rpc/building_by_id` | country, unique_id | full record | Detail view |
| `/rpc/buildings_similar` | country, unique_id, tolerances | ranked matches + score | Morphological similarity |
| `/rpc/age_distribution` | country | epoch breakdown + % | Construction age profile |

---

#### `POST /rpc/buildings_in_bbox`

Returns buildings within a geographic bounding box. Input coordinates are **WGS84 (EPSG:4326)**; the function transforms internally to EPSG:3035 for the spatial query. Maximum 5,000 features.

**Request body:**
```json
{
  "country_table": "malta",
  "min_lon": 14.507,
  "min_lat": 35.894,
  "max_lon": 14.516,
  "max_lat": 35.901
}
```

**Response columns:** `fid`, `unique_id`, `source`, `area`, `height`, `use`, `geom`

```bash
curl -s -X POST http://localhost:3501/rpc/buildings_in_bbox \
     -H "Content-Type: application/json" \
     -d '{"country_table":"malta","min_lon":14.507,"min_lat":35.894,"max_lon":14.516,"max_lat":35.901}'
```

---

#### `POST /rpc/buildings_nearby`

Returns buildings within a radius around a GPS coordinate, ordered by distance ascending. Maximum 1,000 features.

**Request body:**
```json
{
  "country_table": "malta",
  "lat": 35.8989,
  "lon": 14.5146,
  "radius_m": 300
}
```

**Response columns:** `fid`, `unique_id`, `area`, `height`, `use`, `distance_m`, `geom`

```bash
curl -s -X POST http://localhost:3501/rpc/buildings_nearby \
     -H "Content-Type: application/json" \
     -d '{"country_table":"malta","lat":35.8989,"lon":14.5146,"radius_m":300}'
```

---

#### `POST /rpc/country_statistics`

Returns a single row with aggregated metrics for an entire country dataset. Useful for quick data validation after import.

**Request body:**
```json
{ "country_table": "malta" }
```

**Response columns:** `total_buildings`, `avg_area`, `total_area`, `avg_height`, `avg_shapefactor`, `min_epoch`, `max_epoch`

**Example response:**
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

#### `POST /rpc/buildings_by_use`

Filters buildings by use classification. Maximum 2,000 features.

**Request body:**
```json
{ "country_table": "malta", "use_type": 1 }
```

Use codes: `0` = unknown, `1` = residential, `2` = non-residential.

**Response columns:** `fid`, `unique_id`, `area`, `height`, `geom`

---

#### `POST /rpc/compare_versions`

Detects differences between v1 (R2023) and v2 (R2025) for the same country. Requires the country to be imported in **both** schemas. Supports pagination.

**Request body:**
```json
{
  "country_table": "malta",
  "limit_rows": 500,
  "offset_rows": 0
}
```

**Response columns:** `fid`, `status` (`NEW` / `MODIFIED` / `UNCHANGED`)

> If only v2 is imported, all rows return `"NEW"` — there are no v1 records to compare against.

---

#### `POST /rpc/building_by_id`

Returns all columns for a single building, identified by its `unique_id`. Includes the raw JSON source metadata.

**Request body:**
```json
{
  "country_table": "spain",
  "uid": "ES120_N239E37_Y2277.3078_X9323.5932"
}
```

**Response columns:** all v2 schema columns including `eub_json`, `osm_json`, `msb_json`.

To find a valid `unique_id` for any building, run `buildings_in_bbox` first and copy a value from the response.

---

#### `POST /rpc/buildings_similar`

Finds buildings similar to a reference building by footprint area and height, within a configurable radius. Returns a composite similarity score (0–1).

**Request body:**
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

| Parameter | Default | Description |
|-----------|---------|-------------|
| `radius_m` | 5000 | Search radius in metres |
| `area_pct` | 0.30 | Tolerance for area match (0.30 = ±30%) |
| `height_pct` | 0.30 | Tolerance for height match |
| `max_results` | 200 | Maximum rows returned |

**Response columns:** `fid`, `unique_id`, `area`, `height`, `use`, `epoch`, `shapefactor`, `distance_m`, `similarity`, `geom`

Results are ordered by `similarity DESC`, then `distance_m ASC`.

**Similarity score interpretation:**

| Score | Meaning |
|-------|---------|
| 0.90 – 1.00 | Very similar — nearly identical area and height |
| 0.70 – 0.89 | Similar — within ~15% on both dimensions |
| 0.50 – 0.69 | Loosely similar — at or approaching the tolerance boundary |
| < 0.50 | Should not appear — filtered out by the tolerance conditions |

---

#### `POST /rpc/age_distribution`

Returns the number of buildings per construction period for a country, with human-readable labels and percentage breakdown. Useful for analysing the age profile of the building stock (key input for energy efficiency assessments in the MODERATE project context).

**Request body:**
```json
{"country_table": "malta"}
```

**Response columns:** `epoch_code`, `epoch_label`, `building_count`, `pct_total`

**Example response:**
```json
[
  {"epoch_code": 0, "epoch_label": "Unknown",     "building_count": 1114,  "pct_total": 1.48},
  {"epoch_code": 1, "epoch_label": "Before 1980", "building_count": 50307, "pct_total": 66.74},
  {"epoch_code": 2, "epoch_label": "1980–1989",   "building_count": 15117, "pct_total": 20.05},
  {"epoch_code": 3, "epoch_label": "1990–1999",   "building_count": 2949,  "pct_total": 3.91},
  {"epoch_code": 4, "epoch_label": "2000–2009",   "building_count": 3329,  "pct_total": 4.42},
  {"epoch_code": 5, "epoch_label": "2010+",       "building_count": 2564,  "pct_total": 3.40}
]
```

```bash
curl -s -X POST http://localhost:3501/rpc/age_distribution \
  -H "Content-Type: application/json" \
  -d '{"country_table": "spain"}'
```

---

### Direct Table Access

PostgREST exposes each country table in the `v2` schema as a REST resource. This provides flexible filtering without custom functions.

```bash
# First 10 buildings in Malta
GET http://localhost:3501/malta?limit=10

# Buildings taller than 20 m
GET http://localhost:3501/spain?height=gt.20&limit=100

# Residential buildings, only specific columns
GET http://localhost:3501/malta?use=eq.1&select=unique_id,area,height&limit=50

# Buildings with area between 50 and 200 m²
GET http://localhost:3501/malta?area=gte.50&area=lte.200&limit=100
```

PostgREST [filtering operators](https://docs.postgrest.org/en/v12/references/api/tables_views.html#operators): `eq`, `neq`, `lt`, `lte`, `gt`, `gte`, `like`, `is`, `in`, and more.

> **Note:** `v1` tables are not exposed via direct table access — `PGRST_DB_SCHEMA=v2` in `.env` limits direct access to the v2 schema. Use the `compare_versions` RPC function to query v1 data.

---

## Swagger UI — Verified Call Examples

Open **http://localhost:3504**, locate the function in the list, click **Try it out**, paste the body shown, and click **Execute**.

> **Geometry and Swagger rendering:** Functions that return a `geom` column can produce very large responses. To exclude geometry in Swagger UI, append `?select=` to the request URL:
> ```
> http://localhost:3501/rpc/buildings_in_bbox?select=fid,unique_id,source,area,height,use
> ```

All examples below have been tested with Malta, Luxembourg, Spain and Italy imported.

### `buildings_in_bbox`

**Swagger URL:** `http://localhost:3501/rpc/buildings_in_bbox?select=fid,unique_id,source,area,height,use`

**Malta — Valletta city block (~50 buildings)**
```json
{ "country_table": "malta", "min_lon": 14.507, "min_lat": 35.894, "max_lon": 14.516, "max_lat": 35.901 }
```

**Spain — Villaviciosa city centre (~80 buildings)**
```json
{ "country_table": "spain", "min_lon": -5.432, "min_lat": 43.481, "max_lon": -5.421, "max_lat": 43.488 }
```

### `buildings_nearby`

**Swagger URL:** `http://localhost:3501/rpc/buildings_nearby?select=fid,unique_id,area,height,use,distance_m`

**Malta — Valletta centre, 150 m radius**
```json
{ "country_table": "malta", "lat": 35.8989, "lon": 14.5146, "radius_m": 150 }
```

**Spain — Gijón centre, 200 m radius**
```json
{ "country_table": "spain", "lat": 43.5453, "lon": -5.6615, "radius_m": 200 }
```

### `country_statistics`

```json
{ "country_table": "malta" }
```

### `buildings_by_use`

**Swagger URL:** `http://localhost:3501/rpc/buildings_by_use?select=fid,unique_id,area,height`

**Malta — residential:**
```json
{ "country_table": "malta", "use_type": 1 }
```

**Spain — non-residential:**
```json
{ "country_table": "spain", "use_type": 2 }
```

### `compare_versions`

Requires both v1 and v2 imported for the same country.

```json
{ "country_table": "malta", "limit_rows": 500, "offset_rows": 0 }
```

### `building_by_id`

```json
{ "country_table": "spain", "uid": "ES120_N239E37_Y2277.3078_X9323.5932" }
```

### `buildings_similar`

**Swagger URL:** `http://localhost:3501/rpc/buildings_similar?select=fid,unique_id,area,height,use,distance_m,similarity`

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

---

## Data Schema

### v2 schema (DBSM R2025)

All tables in `v2` share this structure. Each imported country becomes a table: `v2.malta`, `v2.spain`, etc.

| Column | Type | Description |
|--------|------|-------------|
| `fid` | integer | Primary key |
| `unique_id` | varchar | Global ID: `{NUTS3}_{grid}_{lon}_{lat}` |
| `source` | varchar | `eub` / `osm` / `msb` — highest-priority source used |
| `area` | float | Footprint area in m² |
| `height` | float | Building height in metres |
| `shapefactor` | float | Surface-to-volume ratio (m²/m³); lower values indicate more compact buildings |
| `epoch` | bigint | Construction period: 0=unknown, 1=pre-1980, 2=1980–1989, 3=1990–1999, 4=2000–2009, 5=2010+ |
| `use` | bigint | 0=unknown, 1=residential, 2=non-residential |
| `eub_json` | varchar | EuroBuildings JSON: `height`, `age`, `type`, `building`, `levels`, `roof-shape` |
| `osm_json` | varchar | OpenStreetMap JSON metadata |
| `msb_json` | varchar | Microsoft Buildings JSON metadata |
| `geom` | geometry(MultiPolygon, 3035) | Building footprint, ETRS89-LAEA |

### v1 schema (DBSM R2023)

Minimal schema — geometry and source only.

| Column | Type | Description |
|--------|------|-------------|
| `fid` | integer | Feature identifier |
| `source` | varchar | Data source code |
| `geom` | geometry(MultiPolygon, 3035) | Building footprint, ETRS89-LAEA |

### JSON metadata example

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

Field availability varies by country and building. The `age` field (exact year) is more precise than `epoch` (decade bin) when available.

---

## GeoServer

GeoServer publishes the PostGIS tables as OGC-compliant WMS and WFS services.

### Published resources

| Resource | Name | Description |
|----------|------|-------------|
| Workspace (v2) | `dbsm_v2` | Groups all v2 layers |
| Workspace (v1) | `dbsm_v1` | Groups all v1 layers |
| DataStore (v2) | `postgis_v2` | PostGIS connection → schema `v2` |
| DataStore (v1) | `postgis_v1` | PostGIS connection → schema `v1` |
| Style (v2) | `dbsm_buildings` | Height-classified SLD (5 colour bands) |
| Style (v1) | `dbsm_buildings_v1` | Flat-colour SLD |
| Layer | `dbsm_v2:<country>` | One per imported country |
| LayerGroup | `dbsm_v2_all` | All v2 countries aggregated into one layer |
| LayerGroup | `dbsm_v1_all` | All v1 countries aggregated |

### WMS / WFS endpoints

```
# WMS — view maps in any GIS client
WMS GetCapabilities (v2):
http://localhost:3503/geoserver/dbsm_v2/ows?service=WMS&version=1.3.0&request=GetCapabilities

WFS GetCapabilities (v2):
http://localhost:3503/geoserver/dbsm_v2/ows?service=WFS&version=2.0.0&request=GetCapabilities

# Direct WMS map image (example — Malta at country scale)
http://localhost:3503/geoserver/dbsm_v2/ows?service=WMS&version=1.3.0&request=GetMap
  &layers=dbsm_v2:malta
  &bbox=3427938,1370068,3463898,1401302
  &width=800&height=600
  &srs=EPSG:3035&format=image/png
```

### Symbology

The v2 SLD style (`dbsm_buildings`) classifies buildings by height:

| Colour | Height range | Meaning |
|--------|-------------|---------|
| Grey | `height = 0` or null | No height data available |
| Yellow | 0 < height ≤ 6 m | Low buildings (sheds, garages, single-floor) |
| Orange | 6 < height ≤ 15 m | Medium-rise (2–5 floors) |
| Red | 15 < height ≤ 30 m | High-rise (5–10 floors) |
| Dark red | height > 30 m | Tall buildings (10+ floors) |

The v1 SLD style uses a single flat beige fill — no height attribute exists in v1.

### Automation

All GeoServer configuration is managed by `gsconfig.py`. Manual intervention via the web UI is not required for normal operations. `geoserver:init` and `geoserver:publish` (called internally by `task import`) are safe to re-run at any time.

---

## QGIS — Desktop Client Guide

The file `qgis_project/dbsm_demo.qgs` is a ready-to-use QGIS 3 project for interactive exploration of the DBSM data. It connects directly to the running PostGIS stack and provides pre-built Python actions that would otherwise require manual queries or custom code.

### What the project includes

The project is pre-configured for four countries: **Italy, Spain, Malta, Luxembourg**. It includes base layers plus country-specific building footprint layers for those four countries.

#### Layer panel structure

| Layer | Type | Source | Licence | Description |
|-------|------|--------|---------|-------------|
| `OpenStreetMap` | XYZ tiles | [openstreetmap.org](https://www.openstreetmap.org) | © OpenStreetMap contributors, ODbL | Basemap for geographical context |
| `CNTR_RG_01M_2016_3035` | GeoPackage (external) | [Eurostat GISCO — Countries 2016](https://gisco-services.ec.europa.eu/distribution/v2/countries/gpkg/CNTR_RG_01M_2016_3035.gpkg) | © EuroGeographics, non-commercial | Country boundaries at 1:1M scale, EPSG:3035 — triggers country-level load actions |
| `COMM_RG_01M_2016_3035` | GeoJSON (external) | [Eurostat GISCO — Communes 2016](https://gisco-services.ec.europa.eu/distribution/v2/communes/geojson/COMM_RG_01M_2016_3035.geojson) | © EuroGeographics, non-commercial | Commune/municipality boundaries at 1:1M, EPSG:3035 — triggers commune-level load actions |
| `spain.v2` | PostGIS `v2.spain` | DBSM R2025 (JRC) | ODbL | Full Spain building footprint (v2) — 10 GB, may be slow at country scale |
| `spain.v2 — vista actual` | PostGIS `v2.spain` (view-filtered) | DBSM R2025 (JRC) | ODbL | Spain buildings intersecting the current map extent only |
| `luxembourg.v2` | PostGIS `v2.luxembourg` | DBSM R2025 (JRC) | ODbL | Luxembourg building footprint (v2) |
| `malta.v2` | PostGIS `v2.malta` | DBSM R2025 (JRC) | ODbL | Malta building footprint (v2) |
| `malta.v1` | PostGIS `v1.malta` | DBSM R2023 (JRC) | ODbL | Malta building footprint (v1) — for comparison with v2 |

**"Vista actual" layers** (current view layers) load only the buildings visible in the current map canvas — use these instead of the full country layers when working with large datasets like Spain or Italy.

#### Colour symbology

Layers connected to the v2 schema use the same height-based colour classification as GeoServer:

| Colour | Height | Typical building type |
|--------|--------|-----------------------|
| Grey | 0 / unknown | Agricultural buildings, ruins, unclassified |
| Yellow | ≤ 6 m | Garages, sheds, single-floor commercial |
| Orange | 6–15 m | Residential blocks (2–5 floors) |
| Red | 15–30 m | Urban residential / office (5–10 floors) |
| Dark red | > 30 m | High-rise towers |

v1 layers are rendered in a flat beige colour.

---

### Opening the project

1. Start the Docker stack: `task up`
2. Open QGIS 3.x
3. **Project → Open…** → navigate to `qgis_project/dbsm_demo.qgs`
4. If QGIS prompts for a password, enter the value of `POSTGRES_PASSWORD` from your `.env` (default: `postgres`)
5. If the GISCO boundary layers show as broken (red exclamation mark), right-click → **Repair Data Source** → point to the downloaded files

> If you changed `POSTGRES_PASSWORD` in `.env`, update the layer connections: select a layer → right-click → **Properties → Source → Edit** → update the password in the connection URI.

---

### Using the Python actions

Python actions are QGIS scripts attached to specific layers. They run when you click on a feature and execute an action from the popup menu. Each action is self-contained and works through the database connection.

> **Prerequisite — macros must be enabled.** When you open the project, QGIS shows a security dialog asking whether to enable Python macros. Click **Enable macros** (or set **Always** in _Settings → Options → General → Enable macros_). The project macro is responsible for automatically wiring the building-level actions to every v2 layer (including any filtered "vista actual" layers you create during your session). If macros are disabled, only the country and commune boundary actions will be available.
>
> The macro source lives in `qgis_project/dbsm_macro.py`. To modify an action, edit that file and then re-run `python3 qgis_project/inject_macro.py` from the repository root to embed the updated code into `dbsm_demo.qgs`.

#### How to run an action

1. In the **Layers panel**, select the layer whose action you want to use (e.g. `CNTR_RG_01M_2016_3035`)
2. Click the **Identify Features** tool in the toolbar (shortcut: `Ctrl+Shift+I`, or the **ⓘ** button)
3. Click on a feature on the map — the **Identify Results** panel opens on the right
4. At the top of the Identify Results panel, click the **Run Feature Action** dropdown (the arrow icon)
5. Select the desired action from the list

> Alternatively: with the selection tool active, select a feature → **Layer menu → Run Feature Action → [action name]**.

---

#### Actions on the country boundaries layer (`CNTR_RG_01M_2016_3035`)

These actions read the `NAME_ENGL` field of the clicked country polygon to identify the PostGIS table name.

**Action: Load v2 country footprints**

Adds the full `v2.<country>` table as a new layer. The layer name is in the format `<country>.v2`.

- Click on any country polygon
- Run the action
- A new layer appears in the Layers panel containing all buildings for that country in v2 (R2025)
- A green confirmation message appears in the QGIS message bar

> This only works for countries that have been imported via `task import`. If the country has not been imported, the layer will fail to load and you will see an error message.

**Action: Load v1 country footprints**

Same behaviour as above, but loads from the `v1` schema (R2023, geometry only). Useful for visual comparison with v2.

---

#### Actions on the communes layer (`COMM_RG_01M_2016_3035`)

Click on a municipality/commune polygon to load only the buildings that fall within that administrative boundary.

**Action: Load commune footprints**

- Click on any commune polygon
- Run the action
- A new layer appears named `<country>.v2 — <commune_name>` with only the buildings intersecting that commune
- Any previously loaded layer with the same name is replaced automatically

This action uses a spatial `ST_Intersects` filter, so it efficiently loads only the relevant subset without scanning the full country table.

> The action includes a country lookup table mapping ISO2 codes to PostGIS table names. Currently pre-wired for: Spain (ES), Malta (MT), Luxembourg (LU), Italy (IT), Austria (AT), Belgium (BE), Germany (DE), France (FR), Portugal (PT). See [Extending the project to new countries](#extending-the-project-to-new-countries) to add more.

---

#### Actions on building layers (`<country>.v2`)

These actions are available on any v2 building layer. Select a layer in the Layers panel, then identify or select a specific building.

**Action: Get similar buildings**

Calls the `buildings_similar` PostgREST function for the clicked building, then applies a subset filter to the current layer showing only the reference building and its similar matches. The map zooms to the filtered result extent.

- Click on a building with the Identify tool
- Run **Get similar buildings**
- The layer is filtered to show only buildings within 5 km with similar area (±30%) and height (±30%)
- The message bar shows the number of similar buildings found
- To return to the full view, run the **Restore view** action

**Action: Show buildings in bbox**

Adds a new layer containing only the buildings visible in the current map canvas. Useful for large datasets (Spain, Italy) where loading the entire country table would be too slow.

- Navigate to the area of interest and zoom in to the desired level
- Select the country layer (e.g. `spain.v2`)
- Run **Show buildings in bbox**
- A new layer `spain.v2 — current view` appears with only the buildings in the visible area
- This layer can be freely zoomed and queried without affecting the original layer

**Action: Restore view**

Clears the active subset filter on the current layer and zooms to the full layer extent. Use this to undo the filter applied by **Get similar buildings**.

---

### Extending the project to new countries

When you import a new country (e.g. `task import CITY=portugal VERSION=v2`), it becomes available via the API and GeoServer automatically. To use it in QGIS:

**Add the layer manually:**
1. **Layer → Data Source Manager → PostgreSQL**
2. Select the `dbsm` connection (or create one if this is the first time)
3. Browse to schema `v2`, select the `portugal` table
4. Click **Add**

**Enable commune-level loading for the new country:**

Open the `COMM_RG_01M_2016_3035` layer properties → **Actions → Load commune footprints** → click **Edit**. In the Python code, find the `COUNTRY_MAP` dictionary and add the new entry:

```python
COUNTRY_MAP = {
    'ES': 'spain', 'MT': 'malta', 'LU': 'luxembourg',
    'IT': 'italy', 'AT': 'austria', 'BE': 'belgium',
    'DE': 'germany', 'FR': 'france', 'PT': 'portugal',
    'SE': 'sweden',   # ← new entry example
}
```

Click **OK** and save the project.

**Enable country-level loading:** The **Load v2 country footprints** action on the country boundaries layer reads `NAME_ENGL` from the clicked polygon and maps it to a table name via `.lower()`. As long as the table name in PostgreSQL matches the lowercase English country name (which it will if you used `task import`), this action works for any imported country without modification.

---

### Direct PostgreSQL connection from QGIS

To add layers manually without using the pre-configured project:

1. **Layer → Data Source Manager → PostgreSQL**
2. Click **New** to create a connection:

| Parameter | Value |
|-----------|-------|
| Name | `DBSM local` |
| Host | `localhost` |
| Port | `5432` |
| Database | `dbsm` |
| Username | `dbsm_admin` |
| Password | value of `POSTGRES_PASSWORD` from `.env` |
| SSL mode | `disable` |

3. Click **Test Connection**, then **OK**
4. Browse the schema (`v2` or `v1`), select a table, and click **Add**

Alternatively, use the `pg_service.conf` file as a libpq service definition (configure your OS to point to the file, then use `service=dbsm_service` as the connection string).

---

## Performance Considerations

Performance degrades significantly with large national datasets. The five heaviest v2 GeoPackages are Germany (49 GB), France (27 GB), Netherlands (24 GB), Italy (23 GB) and Spain (10 GB), totalling ~133 GB — approximately 200 GB once loaded into PostgreSQL. The following improvements are ordered by impact-to-effort ratio.

### 1. PostgreSQL configuration tuning ✅ implemented

The `postgres` service in `docker-compose.yml` passes a tuned `command:` block to PostgreSQL. Memory parameters are configurable via `.env` — set them according to your hardware before starting the stack:

| Variable | Default (`.env.default`) | Recommended (32 GB machine) | What it controls |
|---|---|---|---|
| `PG_SHARED_BUFFERS` | `512MB` | `2GB` | Data page cache (~25% of RAM) |
| `PG_WORK_MEM` | `64MB` | `128MB` | Per-sort/hash memory (spatial sorts, ORDER BY distance) |
| `PG_MAINTENANCE_WORK_MEM` | `256MB` | `512MB` | VACUUM and index creation memory |
| `PG_EFFECTIVE_CACHE_SIZE` | `2GB` | `8GB` | Planner hint for OS cache (no allocation) |

The following parameters are hardcoded because they don't depend on RAM size:

| Parameter | Value | Why |
|---|---|---|
| `random_page_cost` | `1.1` | Assumes SSD — tells the planner to prefer GiST spatial index scans over sequential scans |
| `effective_io_concurrency` | `200` | SSD-level parallelism for bitmap index scans |
| `default_statistics_target` | `250` | More detailed column statistics → better query plans for complex spatial filters |
| `max_parallel_workers_per_gather` | `4` | Sequential scans over large tables use 4 cores |
| `checkpoint_completion_target` | `0.9` | Spread checkpoint I/O smoothly |
| `wal_buffers` | `32MB` | Larger WAL buffer for write-heavy imports |

**To apply after changing `.env` values:** no rebuild required, just recreate the postgres container:
```bash
docker compose up -d --no-deps postgres
```

### 2. CLUSTER and VACUUM ANALYZE (high impact, low effort)

Physically reorders table pages on disk to match the spatial index, significantly reducing I/O for bounding-box queries:

```sql
CLUSTER v2.spain USING spain_geom_idx;
VACUUM ANALYZE v2.spain;
```

Can be added as an optional post-import step.

### 3. GeoWebCache tile seeding ✅ implemented

The `task import` pipeline automatically enqueues a GeoWebCache tile seed job after publishing each layer. Seeding runs asynchronously — the import command returns immediately and GeoServer generates tiles in the background.

**Default zoom range:** 10–14 (configurable via `GWC_ZOOM_START` / `GWC_ZOOM_STOP` in `.env`)

| Zoom range | SLD visibility | Tile content | Approx time (Malta) | Approx time (Spain) |
|---|---|---|---|---|
| 10–12 | Hidden (scale > 1:100 000) | Empty — very fast to generate | < 1 min | ~2 min |
| 13–14 | **Visible** — buildings rendered | Data tiles — slower | ~1 min | ~2 h |
| 15–16 | Visible — street level | Data tiles | ~5 min | impractical |

For small countries (Malta, Luxembourg), seeding zoom 10–16 is fast and gives full coverage:
```bash
GWC_ZOOM_STOP=16 task import CITY=malta VERSION=v2
# or after import:
GWC_ZOOM_STOP=16 task geoserver:gwc-seed CITY=malta VERSION=v2
```

**Monitor and control seeding:**
```bash
task geoserver:gwc-status CITY=malta VERSION=v2   # show tiles done/total + ETA
task geoserver:gwc-kill   CITY=malta VERSION=v2   # cancel running jobs
```

### 4. Scale-dependent rendering in SLD ✅ implemented

The SLD styles (`styles/dbsm_buildings.sld` and `styles/dbsm_buildings_v1.sld`) include a `<MaxScaleDenominator>100000</MaxScaleDenominator>` limit on every rule. GeoServer skips the PostGIS query entirely at scales coarser than **1:100 000** (roughly city-district level and above), eliminating the expensive full-table scan that would otherwise occur when viewing Spain or Italy at regional/national scale.

| Scale range | Behaviour |
|---|---|
| Coarser than 1:100 000 | Layer appears empty — no query issued |
| 1:100 000 and finer | Full height-classified rendering (v2) or flat beige (v1) |

If you update an SLD file, push the change to a running GeoServer with:
```bash
task geoserver:update-style VERSION=v2   # or v1
```

### 5. Vector tiles (very high impact, high effort)

Replacing WMS with vector tiles (served by `pg_tileserv` or `Martin`) moves rendering to the client. This is the most scalable long-term solution but requires adding a new service to the stack.

---

## Known Issues & Troubleshooting

### Known issues

| Issue | Status | Workaround |
|-------|--------|-----------|
| GeoServer 2.24.x `PUT /layergroups` does not replace `<publishables>` | Open upstream bug | `gsconfig.py` uses DELETE + POST instead |
| PostgREST returns geometry as base64 WKB by default | By design | Use `Accept: application/geo+json` header or `ST_AsText()` in functions |
| Large datasets (Spain, Italy) cause slow WMS renders | Infrastructure limitation | See [Performance Considerations](#performance-considerations) |

### Common deployment problems

**Problem: PostgREST returns `{"code":"PGRST001","message":"...connection..."}` or no response**

PostgREST cannot connect to PostgreSQL. Possible causes:
1. PostgreSQL is not healthy yet — wait a few seconds and retry
2. `PGRST_DB_AUTHENTICATOR_PASSWORD` in `.env` does not match the password stored in the `authenticator` database role. Re-apply the init script: `task db:apply-sql`

**Problem: `task import` fails with `File ./datasets/dbsm-v2-malta-R2025.gpkg not found`**

The file name does not match the expected pattern. For v2 files downloaded from JRC, the filename is `dbsm-malta-R2025.gpkg` (without `v2-`). Rename it:
```bash
mv datasets/dbsm-malta-R2025.gpkg datasets/dbsm-v2-malta-R2025.gpkg
```

**Problem: GeoServer web UI is unreachable at http://localhost:3503**

GeoServer takes 60–120 seconds to start. Check its status with:
```bash
docker logs dbsm_geoserver --tail 50
task ps
```

If the container shows `unhealthy`, the healthcheck failed. This usually resolves after a full restart: `task restart`.

**Problem: `task geoserver:init` fails with authentication error**

`GEOSERVER_ADMIN_PASSWORD` in `.env` does not match what GeoServer was started with. If you changed the password in `.env` after the first start, GeoServer's stored credentials (in `./geoserver_data/`) still use the old value. Either restore the old password in `.env` or do a full reset: `task clean:nuke && task up`.

**Problem: QGIS layer fails to load — "Unable to open datasource"**

1. Confirm the stack is running: `task ps`
2. Check the password matches: the QGIS connection URI uses `password='postgres'` by default. If you changed `POSTGRES_PASSWORD`, update the layer source.
3. Confirm the country was imported: `task geoserver:status VERSION=v2`

**Problem: QGIS action "Load commune footprints" shows error for a country**

The country's ISO2 code is not in the `COUNTRY_MAP` dictionary in the action. Edit the action and add the mapping — see [Extending the project to new countries](#extending-the-project-to-new-countries).

**Problem: `task db:apply-sql` shows `ERROR: role "web_anon" already exists`**

This is expected and harmless — `02_postgrest.sh` uses `CREATE ROLE IF NOT EXISTS` so the error is not raised for roles. If you see it, check your script version (`initdb/02_postgrest.sh`, not the old `02_postgrest.sql`).

**Problem: All API calls return an empty array `[]`**

The requested country table exists in PostgreSQL but PostgREST's schema cache is stale. Reload it:
```bash
task api:reload
```

If the table does not exist at all, import the country first: `task import CITY=malta VERSION=v2`.

---

## References

| Resource | Link |
|----------|------|
| DBSM data collection (JRC) | [data.jrc.ec.europa.eu/collection/id-00382](https://data.jrc.ec.europa.eu/collection/id-00382) |
| DBSM R2023 dataset page | [data.jrc.ec.europa.eu/dataset/60c6b14d…](https://data.jrc.ec.europa.eu/dataset/60c6b14d-3dda-4034-b461-390dc8ed8665) |
| DBSM R2025 dataset page | [data.jrc.ec.europa.eu/dataset/a601a4a8…](https://data.jrc.ec.europa.eu/dataset/a601a4a8-9289-4fc4-983a-25d54f957f3a) |
| DBSM R2023 technical publication | [JRC135616](https://publications.jrc.ec.europa.eu/repository/handle/JRC135616) |
| DBSM R2025 technical publication | [JRC142133](https://publications.jrc.ec.europa.eu/repository/handle/JRC142133) |
| MODERATE project | [moderate-project.eu](https://moderate-project.eu/) |
| Eurostat GISCO — administrative units | [ec.europa.eu/eurostat/web/gisco/geodata/administrative-units](https://ec.europa.eu/eurostat/web/gisco/geodata/administrative-units) |
| Eurostat GISCO distribution API | [gisco-services.ec.europa.eu/distribution/v2](https://gisco-services.ec.europa.eu/distribution/v2/) |
| GDAL / ogr2ogr | [gdal.org/programs/ogr2ogr](https://gdal.org/en/stable/programs/ogr2ogr.html) |
| PostgREST documentation | [docs.postgrest.org/en/v12](https://docs.postgrest.org/en/v12/) |
| GeoServer REST API | [docs.geoserver.org/stable/en/user/rest](https://docs.geoserver.org/stable/en/user/rest/) |
| Kartoza GeoServer Docker image | [github.com/kartoza/docker-geoserver](https://github.com/kartoza/docker-geoserver) |
| Task runner | [taskfile.dev](https://taskfile.dev) |
| ODbL licence | [opendatacommons.org/licenses/odbl](https://opendatacommons.org/licenses/odbl/1-0/) |
| OGC SLD specification | [ogc.org/standard/sld](https://www.ogc.org/standard/sld/) |
