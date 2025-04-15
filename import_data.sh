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

if [ -z "$CITY" ]; then
    echo -e "${RED} No city provided. Usage: $0 <city|all>${NC}"
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

# Check if the ogr2ogr command is available
echo -e "${YELLOW} Checking if ogr2ogr command is available...${NC}"
if ! command -v ogr2ogr &> /dev/null; then
    echo -e "${RED} ogr2ogr command not found. Please install GDAL and try again.${NC}"
    exit 1
fi
echo -e "${GREEN} ogr2ogr command is available.${NC}"

# Load GPKG files
start_time=$(date +%s.%N)
if [ "$CITY" = "all" ]; then
    echo -e "${YELLOW} Importing all .gpkg files in ./datasets...${NC}"
    for file in ./datasets/*.gpkg; do
        echo -e "${BLUE} Importing ${file}...${NC}"
        ogr2ogr -f PostgreSQL "PG:host=$PG_HOST port=$PG_PORT user=$POSTGRES_USER password=$POSTGRES_PASSWORD dbname=$POSTGRES_DB" \
        "$file" \
        -nlt PROMOTE_TO_MULTI \
        -nln v1."$CITY" \
        -lco SCHEMA=v1
        
        if [ $? -ne 0 ]; then
            echo -e "${RED} Failed to import ${file}.${NC}"
        fi
    done
    docker exec -u postgres "$PG_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA v1 GRANT SELECT ON TABLES TO web_anon;"
else
    FILE="./datasets/dbsm-v1-${CITY}-merge.gpkg"
    if [ ! -f "$FILE" ]; then
        echo -e "${RED} File $FILE not found.${NC}"
        exit 1
    fi

    echo -e "${YELLOW} Importing data from ${FILE}...${NC}"
    ogr2ogr -f PostgreSQL "PG:host=$PG_HOST port=$PG_PORT user=$POSTGRES_USER password=$POSTGRES_PASSWORD dbname=$POSTGRES_DB" \
    "$FILE" \
    -nlt PROMOTE_TO_MULTI \
    -nln v1."$CITY" \
    -lco SCHEMA=v1
    docker exec -u postgres "$PG_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "GRANT SELECT ON v1.$CITY TO web_anon;"

    if [ $? -ne 0 ]; then
        echo -e "${RED} Data import failed.${NC}"
        exit 1
    fi
fi
end_time=$(date +%s.%N)
duration=$(echo "$end_time - $start_time" | bc)

# Check if the import was successful
if [ $? -ne 0 ]; then
    echo -e "${RED} Data import failed. Please check the error messages above.${NC}"
    exit 1
fi

echo -e "${GREEN} Data import completed successfully.${NC}"
echo -e "${BLUE} Data import completed in ${duration} seconds.${NC}"