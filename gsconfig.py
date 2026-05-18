import os
import sys
import requests
from requests.auth import HTTPBasicAuth

# ---------------------------------------------------------------------------
# 1. Arguments
# ---------------------------------------------------------------------------
if len(sys.argv) < 3:
    print("Usage: python gsconfig.py <city|all|_init_only> <version> [seed-only|gwc-status|gwc-kill]")
    sys.exit(1)

CITY_ARG = sys.argv[1].lower()
VERSION  = sys.argv[2].lower()
MODE     = sys.argv[3].lower() if len(sys.argv) > 3 else "publish"

# ---------------------------------------------------------------------------
# 2. Environment variables (injected by Taskfile / .env)
# ---------------------------------------------------------------------------
GEOSERVER_USER     = os.environ.get('GEOSERVER_ADMIN_USER', 'admin')
GEOSERVER_PASS     = os.environ.get('GEOSERVER_ADMIN_PASSWORD', 'geoserver')
GEOSERVER_PORT     = os.environ.get('GEOSERVER_PORT', '8081')
PG_CONTAINER       = os.environ.get('PG_CONTAINER', 'dbsm_postgres')
POSTGRES_DB        = os.environ.get('POSTGRES_DB', 'dbsm')
POSTGRES_USER      = os.environ.get('POSTGRES_USER', 'dbsm_admin')
POSTGRES_PASSWORD  = os.environ.get('POSTGRES_PASSWORD', 'postgres')

BASE_URL  = f"http://localhost:{GEOSERVER_PORT}/geoserver/rest"
GWC_URL   = f"http://localhost:{GEOSERVER_PORT}/geoserver/gwc/rest"
AUTH      = HTTPBasicAuth(GEOSERVER_USER, GEOSERVER_PASS)
XML_HDR   = {'Content-type': 'text/xml'}
JSON_HDR  = {'Content-type': 'application/json', 'Accept': 'application/json'}

WS_NAME    = f"dbsm_{VERSION}"
DS_NAME    = f"postgis_{VERSION}"
STYLE_NAME = "dbsm_buildings" if VERSION == "v2" else "dbsm_buildings_v1"
SLD_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "styles", f"{STYLE_NAME}.sld")

GWC_ZOOM_START = int(os.environ.get('GWC_ZOOM_START', '10'))
GWC_ZOOM_STOP  = int(os.environ.get('GWC_ZOOM_STOP',  '14'))

# ---------------------------------------------------------------------------
# 3. Helpers
# ---------------------------------------------------------------------------

def resource_exists(url: str) -> bool:
    """Return True if GeoServer responds 200 to a GET on *url*."""
    r = requests.get(url, auth=AUTH, headers=JSON_HDR)
    return r.status_code == 200


def check_auth():
    r = requests.get(f"{BASE_URL}/workspaces", auth=AUTH, headers=JSON_HDR)
    if r.status_code in (401, 403):
        print("ERROR: GeoServer authentication failed. Check GEOSERVER_ADMIN_USER/PASSWORD.")
        sys.exit(1)


def list_tables_in_schema(version: str) -> list[str]:
    """Query PostgreSQL for table names in the given schema via docker exec."""
    import subprocess
    cmd = [
        "docker", "exec", PG_CONTAINER,
        "psql", "-U", POSTGRES_USER, "-d", POSTGRES_DB,
        "-tAc",
        f"SELECT tablename FROM pg_tables WHERE schemaname = '{version}' ORDER BY tablename;"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: Could not query tables in schema {version}: {result.stderr.strip()}")
        sys.exit(1)
    tables = [t.strip() for t in result.stdout.splitlines() if t.strip()]
    return tables


# ---------------------------------------------------------------------------
# 4. GeoServer configuration steps
# ---------------------------------------------------------------------------

def ensure_workspace():
    url = f"{BASE_URL}/workspaces/{WS_NAME}"
    if resource_exists(url):
        print(f"  Workspace '{WS_NAME}' already exists.")
        return
    ws_xml = f"<workspace><name>{WS_NAME}</name></workspace>"
    r = requests.post(f"{BASE_URL}/workspaces", auth=AUTH, headers=XML_HDR, data=ws_xml)
    if r.status_code == 201:
        print(f"  Workspace '{WS_NAME}' created.")
    else:
        print(f"ERROR: Could not create workspace. HTTP {r.status_code}: {r.text}")
        sys.exit(1)


def ensure_datastore():
    url = f"{BASE_URL}/workspaces/{WS_NAME}/datastores/{DS_NAME}"
    if resource_exists(url):
        print(f"  DataStore '{DS_NAME}' already exists.")
        return
    ds_xml = f"""<dataStore>
  <name>{DS_NAME}</name>
  <connectionParameters>
    <entry key="host">{PG_CONTAINER}</entry>
    <entry key="port">5432</entry>
    <entry key="database">{POSTGRES_DB}</entry>
    <entry key="user">{POSTGRES_USER}</entry>
    <entry key="passwd">{POSTGRES_PASSWORD}</entry>
    <entry key="dbtype">postgis</entry>
    <entry key="schema">{VERSION}</entry>
    <entry key="Expose primary keys">true</entry>
  </connectionParameters>
</dataStore>"""
    r = requests.post(
        f"{BASE_URL}/workspaces/{WS_NAME}/datastores",
        auth=AUTH, headers=XML_HDR, data=ds_xml
    )
    if r.status_code == 201:
        print(f"  DataStore '{DS_NAME}' created.")
    else:
        print(f"ERROR: Could not create datastore. HTTP {r.status_code}: {r.text}")
        sys.exit(1)


def ensure_style():
    """Upload or update the SLD style in GeoServer from the local file."""
    sld_path = SLD_FILE
    if not os.path.isfile(sld_path):
        print(f"  WARNING: SLD file not found at {sld_path}. Skipping style upload.")
        return

    with open(sld_path, "r", encoding="utf-8") as fh:
        sld_content = fh.read()

    url = f"{BASE_URL}/styles/{STYLE_NAME}"
    sld_headers = {'Content-type': 'application/vnd.ogc.sld+xml'}

    if resource_exists(url):
        r = requests.put(url, auth=AUTH, headers=sld_headers,
                         data=sld_content.encode("utf-8"))
        if r.status_code in (200, 201):
            print(f"  Style '{STYLE_NAME}' updated.")
        else:
            print(f"  WARNING: Could not update style. HTTP {r.status_code}: {r.text}")
    else:
        r = requests.post(
            f"{BASE_URL}/styles",
            auth=AUTH,
            headers=sld_headers,
            params={'name': STYLE_NAME},
            data=sld_content.encode("utf-8")
        )
        if r.status_code == 201:
            print(f"  Style '{STYLE_NAME}' uploaded.")
        else:
            print(f"  WARNING: Could not upload style. HTTP {r.status_code}: {r.text}")


def publish_layer(city: str):
    """Publish a FeatureType for *city*, recalculate bbox, assign style."""
    ft_url = f"{BASE_URL}/workspaces/{WS_NAME}/datastores/{DS_NAME}/featuretypes/{city}"

    if resource_exists(ft_url):
        print(f"  Layer '{city}' already published — recalculating bbox and reassigning style.")
        _recalculate_bbox(city)
        _assign_style(city)
        return

    ft_xml = f"""<featureType>
  <name>{city}</name>
  <nativeName>{city}</nativeName>
  <title>DBSM {VERSION.upper()} - {city.capitalize()}</title>
  <abstract>Building footprints for {city.capitalize()} from the DBSM {VERSION.upper()} dataset.</abstract>
  <srs>EPSG:3035</srs>
  <projectionPolicy>REPROJECT_TO_DECLARED</projectionPolicy>
  <enabled>true</enabled>
</featureType>"""

    r = requests.post(
        f"{BASE_URL}/workspaces/{WS_NAME}/datastores/{DS_NAME}/featuretypes",
        auth=AUTH, headers=XML_HDR, data=ft_xml
    )
    if r.status_code == 201:
        print(f"  Layer '{city}' published.")
        _recalculate_bbox(city)
        _assign_style(city)
    else:
        print(f"ERROR: Could not publish layer '{city}'. HTTP {r.status_code}: {r.text}")
        sys.exit(1)


def _recalculate_bbox(city: str):
    """Tell GeoServer to recompute native + lat/lon bounding boxes."""
    ft_url = f"{BASE_URL}/workspaces/{WS_NAME}/datastores/{DS_NAME}/featuretypes/{city}"
    r = requests.put(
        ft_url,
        auth=AUTH,
        headers=XML_HDR,
        params={"recalculate": "nativebbox,latlonbbox"},
        data=f"<featureType><name>{city}</name></featureType>"
    )
    if r.status_code in (200, 201):
        print(f"  Bounding box recalculated for '{city}'.")
    else:
        print(f"  WARNING: bbox recalculation returned HTTP {r.status_code}: {r.text}")


def _assign_style(city: str):
    """Set the default style on the published layer."""
    layer_url = f"{BASE_URL}/layers/{WS_NAME}:{city}"
    if not resource_exists(layer_url):
        print(f"  WARNING: Layer {WS_NAME}:{city} not found for style assignment.")
        return

    style_xml = f"""<layer>
  <defaultStyle>
    <name>{STYLE_NAME}</name>
  </defaultStyle>
</layer>"""
    r = requests.put(layer_url, auth=AUTH, headers=XML_HDR, data=style_xml)
    if r.status_code == 200:
        print(f"  Style '{STYLE_NAME}' assigned to layer '{city}'.")
    else:
        print(f"  WARNING: Could not assign style. HTTP {r.status_code}: {r.text}")


def seed_gwc(city: str, zoom_start: int = GWC_ZOOM_START, zoom_stop: int = GWC_ZOOM_STOP) -> None:
    """Enqueue a GeoWebCache tile seed job for a layer — returns immediately."""
    layer_id = f"{WS_NAME}:{city}"

    # Fetch the layer's geographic bbox (calculated by _recalculate_bbox earlier)
    ft_url = f"{BASE_URL}/workspaces/{WS_NAME}/datastores/{DS_NAME}/featuretypes/{city}.json"
    r = requests.get(ft_url, auth=AUTH, headers=JSON_HDR)
    if r.status_code != 200:
        print(f"  WARNING: Could not fetch bbox for '{city}'. Skipping GWC seed.")
        return

    bb = r.json().get('featureType', {}).get('latLonBoundingBox', {})
    if not bb:
        print(f"  WARNING: Empty bbox for '{city}'. Skipping GWC seed.")
        return

    payload = {
        "seedRequest": {
            "name": layer_id,
            "bounds": {
                "coords": {"double": [bb['minx'], bb['miny'], bb['maxx'], bb['maxy']]}
            },
            "srs": {"number": 4326},
            "gridSetId": "EPSG:4326",
            "zoomStart": zoom_start,
            "zoomStop": zoom_stop,
            "format": "image/png",
            "type": "seed",
            "threadCount": 2,
        }
    }

    r = requests.post(f"{GWC_URL}/seed/{layer_id}.json", auth=AUTH, json=payload)
    if r.status_code == 200:
        print(f"  GWC seed enqueued: '{layer_id}' zoom {zoom_start}–{zoom_stop}.")
        print(f"  Monitor: task geoserver:gwc-status CITY={city} VERSION={VERSION}")
        print(f"  Cancel:  task geoserver:gwc-kill   CITY={city} VERSION={VERSION}")
    else:
        print(f"  WARNING: GWC seed failed. HTTP {r.status_code}: {r.text[:300]}")


def gwc_status(city: str) -> None:
    """Print running/queued GWC seed tasks for a layer."""
    layer_id = f"{WS_NAME}:{city}"
    r = requests.get(f"{GWC_URL}/seed/{layer_id}.json", auth=AUTH,
                     headers={"Accept": "application/json"})
    if r.status_code != 200:
        print(f"  ERROR: HTTP {r.status_code}: {r.text[:200]}")
        return

    try:
        tasks = r.json().get("long-array-array", [])
    except Exception:
        # GWC sometimes returns a truncated response when the task list is empty.
        # Treat any parse failure as "no active tasks".
        print(f"  No active seed tasks for '{layer_id}'.")
        return
    if not tasks:
        print(f"  No active seed tasks for '{layer_id}'.")
        return

    status_labels = {-1: "ABORTED", 0: "PENDING", 1: "RUNNING", 2: "DONE", 3: "QUEUED"}
    print(f"  GWC tasks for '{layer_id}':")
    for t in tasks:
        if len(t) >= 5:
            done, total, eta, tid, status = t[0], t[1], t[2], t[3], t[4]
            pct = f"{done / max(total, 1) * 100:.1f}%" if total > 0 else "?"
            label = status_labels.get(status, str(status))
            print(f"    task {tid}: {label} — {done:,}/{total:,} tiles ({pct}), ETA {eta}s")


def gwc_kill(city: str) -> None:
    """Cancel all running GWC seed tasks for a layer."""
    layer_id = f"{WS_NAME}:{city}"
    r = requests.post(
        f"{GWC_URL}/seed/{layer_id}",
        auth=AUTH,
        data="kill_all=running",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if r.status_code == 200:
        print(f"  All running seed tasks for '{layer_id}' cancelled.")
    else:
        print(f"  WARNING: Could not cancel. HTTP {r.status_code}: {r.text[:200]}")


def update_layer_group(cities: list[str]):
    """Create or update a LayerGroup that aggregates all published layers."""
    group_name = f"dbsm_{VERSION}_all"
    group_url  = f"{BASE_URL}/workspaces/{WS_NAME}/layergroups/{group_name}"

    published = [
        c for c in cities
        if resource_exists(
            f"{BASE_URL}/workspaces/{WS_NAME}/datastores/{DS_NAME}/featuretypes/{c}"
        )
    ]

    if not published:
        print("  No layers published yet — skipping LayerGroup update.")
        return

    layers_xml = "\n".join(
        f'    <published type="layer"><name>{WS_NAME}:{c}</name></published>'
        for c in published
    )
    styles_xml = "\n".join(
        f"    <style><name>{STYLE_NAME}</name></style>"
        for _ in published
    )

    group_xml = f"""<layerGroup>
  <name>{group_name}</name>
  <title>DBSM {VERSION.upper()} — All Countries</title>
  <workspace><name>{WS_NAME}</name></workspace>
  <mode>SINGLE</mode>
  <publishables>
{layers_xml}
  </publishables>
  <styles>
{styles_xml}
  </styles>
</layerGroup>"""

    # GeoServer 2.24.x does not reliably replace <publishables> on PUT.
    # Delete and recreate to guarantee the layer list is always up to date.
    if resource_exists(group_url):
        del_r = requests.delete(group_url, auth=AUTH)
        if del_r.status_code not in (200, 404):
            print(f"  WARNING: Could not delete existing LayerGroup. HTTP {del_r.status_code}")

    r = requests.post(
        f"{BASE_URL}/workspaces/{WS_NAME}/layergroups",
        auth=AUTH, headers=XML_HDR, data=group_xml.encode("utf-8")
    )

    if r.status_code == 201:
        print(f"  LayerGroup '{group_name}' rebuilt ({len(published)} layers: {', '.join(published)}).")
    else:
        print(f"  WARNING: LayerGroup creation returned HTTP {r.status_code}: {r.text}")


# ---------------------------------------------------------------------------
# 5. Main
# ---------------------------------------------------------------------------

def main():
    check_auth()

    # GWC standalone modes: python3 gsconfig.py <city> <version> <mode>
    if MODE == "seed-only":
        seed_gwc(CITY_ARG)
        return
    if MODE == "gwc-status":
        gwc_status(CITY_ARG)
        return
    if MODE == "gwc-kill":
        gwc_kill(CITY_ARG)
        return

    # Init-only mode: set up shared resources without publishing any layer
    if CITY_ARG == "_init_only":
        print(f"\nInitialising GeoServer shared resources for {VERSION.upper()}\n")
        print("[1/3] Workspace")
        ensure_workspace()
        print("[2/3] DataStore")
        ensure_datastore()
        print("[3/3] Style")
        ensure_style()
        print(f"\nDone. Workspace '{WS_NAME}' is ready. Use 'task geoserver:publish' to add layers.")
        return

    # Resolve city list
    if CITY_ARG == "all":
        cities = list_tables_in_schema(VERSION)
        if not cities:
            print(f"No tables found in schema '{VERSION}'. Import data first.")
            sys.exit(1)
        print(f"Found {len(cities)} tables in schema '{VERSION}': {', '.join(cities)}")
    else:
        cities = [CITY_ARG]

    print(f"\nConfiguring GeoServer for {VERSION.upper()} — {len(cities)} dataset(s)\n")

    # Shared resources (workspace, datastore, style) — idempotent
    print("[1/6] Workspace")
    ensure_workspace()

    print("[2/6] DataStore")
    ensure_datastore()

    print("[3/6] Style")
    ensure_style()

    # Per-city layer publication + tile cache seeding
    print(f"[4/6] Layers ({len(cities)})")
    for city in cities:
        print(f"  -> {city}")
        publish_layer(city)

    print(f"[5/6] GeoWebCache tile seeding (zoom {GWC_ZOOM_START}–{GWC_ZOOM_STOP}, async)")
    for city in cities:
        seed_gwc(city)

    # LayerGroup aggregating all layers in the schema
    print("[6/6] LayerGroup")
    all_tables = list_tables_in_schema(VERSION) if CITY_ARG != "all" else cities
    update_layer_group(all_tables)

    print(f"\nDone. GeoServer workspace '{WS_NAME}' is fully configured.")
    print(f"Tile seeding is running in the background.")
    print(f"Check progress: task geoserver:gwc-status CITY={cities[0] if len(cities)==1 else '<city>'} VERSION={VERSION}")


if __name__ == "__main__":
    main()
