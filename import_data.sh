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

# This script imports data from ./datasets/ in .gpkg format into a PostgreSQL database using the `ogr2ogr` command.
echo -e "${BLUE} Starting data import...${NC}"

# Check if the PostgreSQL database is accessible
echo -e "${YELLOW} Checking PostgreSQL database connection...${NC}"
if ! docker exec -u postgres "$PG_CONTAINER" psql -U postgres -c '\q'; then
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

# Load ./datasets/dbsm-v1-malta-merge.gpkg file
echo -e "${YELLOW} Importing data from ./datasets/dbsm-v1-malta-merge.gpkg into PostgreSQL...${NC}"

ogr2ogr \
    -f PostgreSQL "PG:host=$PG_HOST port=$PG_PORT user=$POSTGRES_USER password=$POSTGRES_PASSWORD dbname=$POSTGRES_DB"  \
    ./datasets/dbsm-v1-malta-merge.gpkg

# Check if the import was successful
if [ $? -ne 0 ]; then
    echo -e "${RED} Data import failed. Please check the error messages above.${NC}"
    exit 1
fi

echo -e "${GREEN} Data import completed successfully.${NC}"