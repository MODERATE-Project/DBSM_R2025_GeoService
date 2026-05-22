#!/bin/bash

# ANSI
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m' # Reset color

# Load environment variables from .env file
echo -e "${YELLOW} Loading environment variables from .env file...${NC}"
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo -e "${RED} .env file not found. Please create it with the necessary environment variables.${NC}"
    exit 1
fi
echo -e "${GREEN} Environment variables loaded.${NC}"

# Get city parameter
CITY="$1"
# Get version parameter
VERSION="$2"

if [ -z "$CITY" ]; then
    echo -e "${RED} No city provided. Usage: $0 <city|all>${NC}"
    exit 1
fi

if [ -z "$VERSION" ]; then
    echo -e "${RED} No version provided. Usage: $0 <v1|v2>${NC}"
    exit 1
fi

# This script imports data from ./datasets/ in .gpkg format into a PostgreSQL database using the `ogr2ogr` command.
echo -e "${BLUE} Starting data import...${NC}"

# Check if the PostgreSQL database is accessible
echo -e "${YELLOW} Checking PostgreSQL database connection...${NC}"
if ! docker exec -u postgres "$PG_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\q'; then
    echo -e "${RED} PostgreSQL database is not accessible. Please check your connection settings.${NC}"
    exit 1
fi
echo -e "${GREEN} PostgreSQL database is accessible.${NC}"

# Check if the datasets directory exists
echo -e "${YELLOW} Checking if datasets directory exists...${NC}"
if [ ! -d "./datasets" ]; then
    echo -e "${RED} Datasets directory does not exist. Please create it and add your .gpkg files.${NC}"
    exit 1
fi
echo -e "${GREEN} Datasets directory exists.${NC}"

# Check if ogr2ogr is available inside the database container
echo -e "${YELLOW} Checking if ogr2ogr command is available...${NC}"
if ! docker exec "$PG_CONTAINER" ogr2ogr --version &> /dev/null; then
    echo -e "${RED} ogr2ogr not found in container $PG_CONTAINER. Rebuild with: docker compose up -d --build postgres${NC}"
    exit 1
fi
echo -e "${GREEN} ogr2ogr command is available.${NC}"

# Load GPKG files
start_time=$(date +%s)

import_and_grant() {
    local target_file=$1
    local target_city=$2
    local target_version=$3

    local file_size
    file_size=$(du -sh "$target_file" 2>/dev/null | cut -f1)
    echo -e "${YELLOW} Processing: ${target_city} (${target_version}) — file size: ${file_size}${NC}"

    # A. Asegurar que el esquema existe y tiene permisos base ANTES de importar
    docker exec -u postgres "$PG_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE SCHEMA IF NOT EXISTS \"$target_version\"; GRANT USAGE ON SCHEMA \"$target_version\" TO web_anon;" > /dev/null

    # B. Importar con ogr2ogr (runs inside the container where GDAL is installed)
    echo -e "${BLUE} Importing into ${target_version}.${target_city}...${NC}"
    docker exec "$PG_CONTAINER" ogr2ogr -progress \
    -overwrite -f PostgreSQL "PG:host=localhost port=5432 user=$POSTGRES_USER password=$POSTGRES_PASSWORD dbname=$POSTGRES_DB" \
    "/datasets/$(basename "$target_file")" \
    -nlt PROMOTE_TO_MULTI \
    -nln "$target_city" \
    -lco SCHEMA="$target_version" \
    -lco OVERWRITE=YES

    # Capturamos el error de ogr2ogr inmediatamente
    if [ $? -ne 0 ]; then
        echo -e "${RED} Failed to import ${target_file}.${NC}"
        return 1
    fi

    # C. Dar permisos explícitos a la tabla recién creada (usando comillas dobles para evitar errores de sintaxis)
    docker exec -u postgres "$PG_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "GRANT SELECT ON \"$target_version\".\"$target_city\" TO web_anon;" > /dev/null
    
    # D. Revocar permisos de escritura a la tabla recién creada
    docker exec -u postgres "$PG_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON \"$target_version\".\"$target_city\" FROM web_anon;" > /dev/null

    echo -e "${GREEN} Successfully imported and granted permissions for ${target_version}.${target_city}${NC}"
    return 0
}

if [ "$CITY" = "all" ]; then
    echo -e "${YELLOW} Importing all .gpkg files in ./datasets...${NC}"
    for file in ./datasets/*.gpkg; do
        echo -e "${BLUE} Importing ${file}...${NC}"
        CITY_NAME=$(basename -s .gpkg "$file" | cut -d '-' -f 3)
        VERSION_DATASET=$(basename -s .gpkg "$file" | cut -d '-' -f 2)
        import_and_grant "$file" "$CITY_NAME" "$VERSION_DATASET"
    done
else
    if [ "$VERSION" != "v1" ] && [ "$VERSION" != "v2" ]; then
        echo -e "${RED} Invalid version. Please use 'v1' or 'v2'.${NC}"
        exit 1
    fi
    
    if [ "$VERSION" = "v1" ]; then
        FILE="./datasets/dbsm-v1-${CITY}-merge.gpkg"
    elif [ "$VERSION" = "v2" ]; then
        FILE="./datasets/dbsm-v2-${CITY}-R2025.gpkg"
    fi

    
    if [ ! -f "$FILE" ]; then
        echo -e "${RED} File $FILE not found.${NC}"
        exit 1
    fi

    import_and_grant "$FILE" "$CITY" "$VERSION" || exit 1
fi
end_time=$(date +%s)
duration=$((end_time - start_time))

echo -e "${GREEN} Data import completed successfully.${NC}"
echo -e "${BLUE} Data import completed in ${duration} seconds.${NC}"