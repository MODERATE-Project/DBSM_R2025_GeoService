
# DBSM R2023 - GeoService

## Introduction

A containerized geospatial microservice architecture that integrates PostGIS, PostgREST, GeoServer, and Swagger UI into a modular stack. It’s designed to serve, visualize, and manage large-scale geospatial datasets using a combination of vector and raster formats, optimized for GeoPackage imports.

## Interesting Techniques

- **Service Health Checks** using Docker Compose `healthcheck` to manage container readiness and dependency resolution across Postgres, GeoServer, and PostgREST.
- **Automated Data Import** with `ogr2ogr` from `.gpkg` files, using `PROMOTE_TO_MULTI` and schema-aware layer creation.
- **Dynamic Shell Feedback** with ANSI escape codes for clear user output in `import_data.sh`.
- **Scoped Permissions** using SQL `GRANT`s post-import to expose specific schemas to anonymous users through PostgREST.
- **Schema Namespacing** with PostgreSQL’s native `SCHEMA` support for clear separation of data versions.
- **Declarative Task Automation** with `Taskfile` to run and orchestrate services with `.env` support and simple developer commands.

## Notable Tools & Libraries

- **PostgREST** – Automatic RESTful API over PostgreSQL based on roles and views.
- **GeoServer (Kartoza)** – Production-ready GeoServer Docker image supporting WMS/WFS.
- **GDAL** – Used for `ogr2ogr`, which is required locally to import data via CLI.
- **Swagger UI** – Visual API browser for the PostgREST endpoint.
- **pgAdmin** – Web-based GUI for PostgreSQL admin and debugging.

## Project Structure

```
.
├── datasets/
├── initdb/
├── postgres_data/
├── pgadmin_data/
├── geoserver_data/
├── import_data.sh
├── docker-compose.yml
├── Taskfile.yml
```

### Directory Overview

- **datasets/**: Place `.gpkg` GeoPackage files here for import. Each file is expected to follow the naming convention `dbsm-v1-<city>-merge.gpkg`.
- **initdb/**: SQL and XML files for initializing PostGIS, PostgREST, and GeoServer configs.
- **postgres_data/**, **pgadmin_data/**, **geoserver_data/**: Named Docker volumes for persistent service storage.

---

## Technologies Used

| Tool            | Role                                                              |
|-----------------|-------------------------------------------------------------------|
| **PostgreSQL**  | Core relational database                                          |
| **PostGIS**     | Geospatial extension for advanced spatial queries                 |
| **PgAdmin**     | GUI to manage PostgreSQL/PostGIS instance                         |
| **PostgREST**   | Automatically exposes database tables as RESTful endpoints        |
| **GeoServer**   | Visualizes spatial data and publishes it via WMS/WFS              |
| **Swagger UI**  | Frontend to interact with the PostgREST API                       |
| **Docker** / **Docker Compose** | Containerized, reproducible setup for all services |

---

## Endpoints and Access

Here are the default endpoints and credentials exposed by the services (as defined in `docker-compose.yml`):

| Service       | URL                                                         | Credentials                            |
|---------------|-------------------------------------------------------------|-----------------------------------------|
| **PgAdmin**   | [http://localhost:5050](http://localhost:5050)              | Email: `user@domain.com`<br>Password: `postgres` |
| **PostgREST** | [http://localhost:3000](http://localhost:3000)              | No auth (public access enabled)         |
| **Swagger UI**| [http://localhost:8081](http://localhost:8081)              | No auth (PostgREST schema preview)      |
| **GeoServer** | [http://localhost:8082/geoserver](http://localhost:8082/geoserver) | User: `admin`<br>Password: `geoserver` |

---

## GeoServer load data

Para cargar uno de los conjuntos de datos de PostgreSQL a GeoServer:

1. Crear un espacio de trabajo Data -> Workspaces

    1.1. Add a new workspace

    1.2. Enter the name as dbsm and Namespace URI as http://localhost:8081/geoserver/dbsm

2. Crear un store

    2.1. Add a new store

    2.2. 

3. Crear una capa

    3.1. Add new layer

    3.2. 

4. Previsualización de capas


---

## References:

[GDAL/OGR - ogr2ogr documentation](https://gdal.org/en/stable/programs/ogr2ogr.html)

[MODERATE Project - PoC repository](https://github.com/MODERATE-Project/poc-dbsm-r2023)

[GeoServer Docker Compose setup (Kartoza)](https://github.com/kartoza/docker-geoserver/blob/develop/docker-compose.yml)

[PostgREST Tutorials](https://docs.postgrest.org/en/v12/tutorials/tut0.html)

[WebGIS.dev: Setting up GeoServer with Docker](https://www.webgis.dev/posts/setting-up-geoserver-with-docker)



