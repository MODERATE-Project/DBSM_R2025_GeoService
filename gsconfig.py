import os
import sys
import requests
from requests.auth import HTTPBasicAuth

# 1. Capture arguments
if len(sys.argv) < 3:
    print("❌ Usage: python gsconfig.py <city> <version> (e.g., malta v2)")
    sys.exit(1)

CITY = sys.argv[1].lower()
VERSION = sys.argv[2].lower()

# 2. Read environment variables (Injected by Taskfile/.env)
GEOSERVER_USER = os.environ.get('GEOSERVER_ADMIN_USER', 'admin')
GEOSERVER_PASS = os.environ.get('GEOSERVER_ADMIN_PASSWORD', 'geoserver')
GEOSERVER_PORT = os.environ.get('GEOSERVER_PORT', '8081')
PG_CONTAINER = os.environ.get('PG_CONTAINER', 'dbsm_postgres')
POSTGRES_DB = os.environ.get('POSTGRES_DB', 'dbsm')
POSTGRES_USER = os.environ.get('POSTGRES_USER', 'dbsm_admin')
POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'postgres')

# 3. Base configuration
BASE_URL = f"http://localhost:{GEOSERVER_PORT}/geoserver/rest"
AUTH = HTTPBasicAuth(GEOSERVER_USER, GEOSERVER_PASS)
HEADERS = {'Content-type': 'text/xml'}

WS_NAME = f"dbsm_{VERSION}"
DS_NAME = f"postgis_{VERSION}"

print(f"🌍 Starting GeoServer configuration for {VERSION}.{CITY}...")

# --- STEP 1: Create Workspace ---
ws_xml = f"<workspace><name>{WS_NAME}</name></workspace>"
res_ws = requests.post(f"{BASE_URL}/workspaces", auth=AUTH, headers=HEADERS, data=ws_xml)

if res_ws.status_code == 201:
    print(f"✅ Workspace '{WS_NAME}' created.")
elif res_ws.status_code in [401, 403]:
    print("❌ Authentication failed. Check GEOSERVER_ADMIN_USER/PASSWORD.")
    sys.exit(1)

# --- STEP 2: Create DataStore (PostGIS Connection) ---
ds_xml = f"""
<dataStore>
  <name>{DS_NAME}</name>
  <connectionParameters>
    <host>{PG_CONTAINER}</host>
    <port>5432</port>
    <database>{POSTGRES_DB}</database>
    <user>{POSTGRES_USER}</user>
    <passwd>{POSTGRES_PASSWORD}</passwd>
    <dbtype>postgis</dbtype>
    <schema>{VERSION}</schema>
  </connectionParameters>
</dataStore>
"""
res_ds = requests.post(f"{BASE_URL}/workspaces/{WS_NAME}/datastores", auth=AUTH, headers=HEADERS, data=ds_xml)

if res_ds.status_code == 201:
    print(f"✅ DataStore '{DS_NAME}' created and connected to PostGIS.")

# --- STEP 3: Publish the Layer (FeatureType) ---
ft_xml = f"""
<featureType>
  <name>{CITY}</name>
  <nativeName>{CITY}</nativeName>
  <title>DBSM {VERSION.upper()} - {CITY.capitalize()}</title>
  <srs>EPSG:3035</srs>
  <projectionPolicy>REPROJECT_TO_DECLARED</projectionPolicy>
</featureType>
"""
res_ft = requests.post(f"{BASE_URL}/workspaces/{WS_NAME}/datastores/{DS_NAME}/featuretypes", auth=AUTH, headers=HEADERS, data=ft_xml)

if res_ft.status_code == 201:
    print(f"🎉 Layer '{CITY}' successfully published to GeoServer!")
elif res_ft.status_code in [500, 409]:
    # GeoServer returns 500 or 409 if the resource already exists
    print(f"⚠️  Layer '{CITY}' already exists. Skipping creation.")
else:
    print(f"❌ Error publishing layer. HTTP Status: {res_ft.status_code}")
    print(res_ft.text)
    sys.exit(1)