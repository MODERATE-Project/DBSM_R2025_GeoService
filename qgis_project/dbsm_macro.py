# QGIS Project Macro — DBSM Demo
# Canonical source. Content is injected into <ProjectMacros><pythonCode>
# by inject_macro.py; edit here and re-run inject_macro.py to update the .qgs.
#
# Connection configuration is read from connection.cfg (gitignored) in the
# same directory as the project file. Copy connection.default.cfg to
# connection.cfg and set the correct host, port, user, password, and database
# for your environment. If the file is absent, the .qgs datasource values
# are used as-is (no patching occurs).
#
# openProject()  – patches all PostgreSQL layer connections from connection.cfg,
#                  applies building actions to every v2 layer, and applies
#                  country/commune loading actions to boundary layers.
# closeProject() – disconnects signals to avoid stale references.

import configparser
import pathlib
from qgis.core import QgsProject, QgsDataSourceUri, QgsVectorLayer, QgsAction, QgsDataProvider


# ── connection helper ─────────────────────────────────────────────────────────

def _read_connection():
    """Read connection.cfg from the project directory. Returns a dict of
    connection parameters, or None if the file does not exist."""
    cfg_path = pathlib.Path(QgsProject.instance().fileName()).parent / 'connection.cfg'
    if not cfg_path.exists():
        return None
    cfg = configparser.ConfigParser()
    cfg.read(str(cfg_path))
    return {
        'host':     cfg.get('connection', 'host',     fallback='localhost'),
        'port':     cfg.get('connection', 'port',     fallback='3500'),
        'user':     cfg.get('connection', 'user',     fallback='dbsm_admin'),
        'password': cfg.get('connection', 'password', fallback='postgres'),
        'database': cfg.get('connection', 'database', fallback='dbsm'),
    }


def _patch_layer_connections(conn):
    """Update every PostgreSQL layer's datasource to use the given connection."""
    for layer in QgsProject.instance().mapLayers().values():
        if not isinstance(layer, QgsVectorLayer):
            continue
        if layer.providerType() != 'postgres':
            continue
        uri = QgsDataSourceUri(layer.dataProvider().dataSourceUri())
        uri.setConnection(
            conn['host'], conn['port'], conn['database'],
            conn['user'], conn['password']
        )
        layer.setDataSource(
            uri.uri(), layer.name(), 'postgres',
            QgsDataProvider.ProviderOptions()
        )


# ── building actions (applied to all v2 PostgreSQL layers) ───────────────────

_GET_SIMILAR = """\
from qgis.utils import iface
from qgis.core import QgsProviderRegistry, QgsDataSourceUri

unique_id = '[% "unique_id" %]'

layer   = iface.activeLayer()
src_uri = QgsDataSourceUri(layer.dataProvider().dataSourceUri())
country = src_uri.table()

RADIUS_M   = 5000
AREA_PCT   = 0.30
HEIGHT_PCT = 0.30

try:
    md   = QgsProviderRegistry.instance().providerMetadata('postgres')
    conn = md.createConnection(src_uri.connectionInfo(False), {})

    sql = (
        f"SELECT fid FROM v2.buildings_similar("
        f"{repr(country)}, {repr(unique_id)}, {RADIUS_M}, {AREA_PCT}, {HEIGHT_PCT})"
    )
    rows = conn.executeSql(sql)
    fids = [str(row[0]) for row in rows]

    if not fids:
        iface.messageBar().pushMessage(
            "No results", f"No similar buildings within {RADIUS_M}m",
            level=1, duration=5
        )
    else:
        filter_str = f'"unique_id" = \\'{unique_id}\\' OR "fid" IN ({", ".join(fids)})'
        layer.setSubsetString(filter_str)
        layer.triggerRepaint()

        canvas = iface.mapCanvas()
        layer.updateExtents()
        canvas.setExtent(layer.extent())
        canvas.zoomByFactor(1.3)
        canvas.refresh()

        iface.messageBar().pushMessage(
            "Filter active",
            f"{len(fids)} similar buildings within {RADIUS_M}m — use 'Restore view' to reset",
            level=0, duration=8
        )

except Exception as e:
    iface.messageBar().pushMessage("Error", str(e), level=2, duration=10)
"""

_RESTORE_VIEW = """\
from qgis.utils import iface

layer = iface.activeLayer()
layer.setSubsetString("")
layer.triggerRepaint()

canvas = iface.mapCanvas()
layer.updateExtents()
canvas.setExtent(layer.extent())
canvas.refresh()

iface.messageBar().pushMessage("OK", "View restored", level=0, duration=3)
"""

_SHOW_BBOX = """\
from qgis.utils import iface
from qgis.core import (
    QgsVectorLayer, QgsProject,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsDataSourceUri
)

layer    = iface.activeLayer()
src_uri  = QgsDataSourceUri(layer.dataProvider().dataSourceUri())
country  = src_uri.table()

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

uri = QgsDataSourceUri()
uri.setConnection(src_uri.host(), src_uri.port(), src_uri.database(),
                  src_uri.username(), src_uri.password())
uri.setDataSource("v2", country, "geom", sql, "fid")
uri.setSrid("3035")
uri.setWkbType(6)  # MultiPolygon

new_layer = QgsVectorLayer(uri.uri(), f"{country}.v2 — current view", "postgres")

if not new_layer.isValid():
    iface.messageBar().pushMessage(
        "Error", f"Could not load v2.{country}", level=3
    )
else:
    QgsProject.instance().addMapLayer(new_layer)
    n = new_layer.featureCount()
    iface.messageBar().pushMessage(
        "OK", f"{n} buildings loaded in current view", level=0, duration=5
    )
"""

_BUILDING_ACTIONS = [
    ('Get similar buildings',  _GET_SIMILAR,  'Similar buildings', {'Feature', 'Canvas'}),
    ('Restore view',           _RESTORE_VIEW, 'Restore view',      {'Feature', 'Canvas'}),
    ('Show buildings in bbox', _SHOW_BBOX,    'Buildings in bbox', {'Feature', 'Canvas'}),
]


# ── country boundary actions (applied to CNTR_RG_01M layer) ──────────────────

_LOAD_V2 = """\
import configparser, pathlib
from qgis.utils import iface
from qgis.core import QgsProject, QgsVectorLayer

cfg = configparser.ConfigParser()
cfg.read(str(pathlib.Path(QgsProject.instance().fileName()).parent / 'connection.cfg'))
host     = cfg.get('connection', 'host',     fallback='localhost')
port     = cfg.get('connection', 'port',     fallback='3500')
user     = cfg.get('connection', 'user',     fallback='dbsm_admin')
password = cfg.get('connection', 'password', fallback='postgres')
database = cfg.get('connection', 'database', fallback='dbsm')

country = '[% "NAME_ENGL" %]'.lower()
uri = (
    f"dbname='{database}' host={host} port={port} "
    f"user='{user}' password='{password}' "
    f"sslmode=disable key='fid' srid=3035 "
    f'type=MultiPolygon table="v2"."{country}" (geom) sql='
)
layer = QgsVectorLayer(uri, f"{country}.v2", "postgres")
if not layer.isValid():
    iface.messageBar().pushMessage(
        "Error", f"Could not load v2.{country} — is the dataset imported?", level=3
    )
else:
    QgsProject.instance().addMapLayer(layer)
    iface.messageBar().pushMessage("OK", f"Layer v2.{country} loaded", level=0)
"""

_LOAD_V1 = """\
import configparser, pathlib
from qgis.utils import iface
from qgis.core import QgsProject, QgsVectorLayer

cfg = configparser.ConfigParser()
cfg.read(str(pathlib.Path(QgsProject.instance().fileName()).parent / 'connection.cfg'))
host     = cfg.get('connection', 'host',     fallback='localhost')
port     = cfg.get('connection', 'port',     fallback='3500')
user     = cfg.get('connection', 'user',     fallback='dbsm_admin')
password = cfg.get('connection', 'password', fallback='postgres')
database = cfg.get('connection', 'database', fallback='dbsm')

country = '[% "NAME_ENGL" %]'.lower()
uri = (
    f"dbname='{database}' host={host} port={port} "
    f"user='{user}' password='{password}' "
    f"sslmode=disable key='fid' srid=3035 "
    f'type=MultiPolygon table="v1"."{country}" (geom) sql='
)
layer = QgsVectorLayer(uri, f"{country}.v1", "postgres")
if not layer.isValid():
    iface.messageBar().pushMessage(
        "Error", f"Could not load v1.{country} — is the dataset imported?", level=3
    )
else:
    QgsProject.instance().addMapLayer(layer)
    iface.messageBar().pushMessage("OK", f"Layer v1.{country} loaded", level=0)
"""

_COUNTRY_ACTIONS = [
    ('Load v2 country footprints', _LOAD_V2, 'Load v2', {'Feature'}),
    ('Load v1 country footprints', _LOAD_V1, 'Load v1', {'Feature'}),
]


# ── commune actions (applied to COMM_RG_01M layer) ───────────────────────────

_LOAD_COMMUNE = """\
import configparser, pathlib
from qgis.utils import iface
from qgis.core import QgsProject, QgsVectorLayer

cfg = configparser.ConfigParser()
cfg.read(str(pathlib.Path(QgsProject.instance().fileName()).parent / 'connection.cfg'))
host     = cfg.get('connection', 'host',     fallback='localhost')
port     = cfg.get('connection', 'port',     fallback='3500')
user     = cfg.get('connection', 'user',     fallback='dbsm_admin')
password = cfg.get('connection', 'password', fallback='postgres')
database = cfg.get('connection', 'database', fallback='dbsm')

COUNTRY_MAP = {
    'ES': 'spain',
    'MT': 'malta',
    'LU': 'luxembourg',
    'IT': 'italy',
    'AT': 'austria',
    'BE': 'belgium',
    'DE': 'germany',
    'FR': 'france',
    'PT': 'portugal',
}

feature_id  = [% $id %]
bounds_layer = iface.activeLayer()
feature      = bounds_layer.getFeature(feature_id)

country_code = feature['TRUE_FLAG']
zone_name    = feature['COMM_NAME'] or feature['NUTS_CODE'] or country_code
country      = COUNTRY_MAP.get(str(country_code).upper())

if not country:
    iface.messageBar().pushMessage(
        "Error", f"Country '{country_code}' has no imported table in v2",
        level=2, duration=6
    )
else:
    geom     = feature.geometry().simplify(10)
    geom_wkt = geom.asWkt()
    sql = f"ST_Intersects(geom, ST_GeomFromText('{geom_wkt}', 3035))"

    uri = (
        f"dbname='{database}' host={host} port={port} "
        f"user='{user}' password='{password}' "
        f"sslmode=disable key='fid' srid=3035 "
        f'type=MultiPolygon table="v2"."{country}" (geom) '
        f"sql={sql}"
    )
    layer_name = f"{country}.v2 — {zone_name}"

    for lyr in QgsProject.instance().mapLayers().values():
        if lyr.name() == layer_name:
            QgsProject.instance().removeMapLayer(lyr)
            break

    new_layer = QgsVectorLayer(uri, layer_name, "postgres")
    if not new_layer.isValid():
        iface.messageBar().pushMessage(
            "Error", f"Could not load v2.{country}", level=3, duration=6
        )
    else:
        QgsProject.instance().addMapLayer(new_layer)
        n = new_layer.featureCount()
        iface.messageBar().pushMessage(
            "OK", f"{n} buildings loaded — {zone_name}", level=0, duration=5
        )
"""

_COMMUNE_ACTIONS = [
    ('Load commune footprints', _LOAD_COMMUNE, 'Load communes', {'Feature'}),
]


# ── layer detection ───────────────────────────────────────────────────────────

def _is_v2_building_layer(layer):
    if not isinstance(layer, QgsVectorLayer):
        return False
    try:
        uri = QgsDataSourceUri(layer.dataProvider().dataSourceUri())
        return uri.schema() == 'v2' and bool(uri.table())
    except Exception:
        return False


def _is_country_boundary_layer(layer):
    return isinstance(layer, QgsVectorLayer) and 'CNTR_RG_01M' in layer.name()


def _is_commune_layer(layer):
    return isinstance(layer, QgsVectorLayer) and 'COMM_RG_01M' in layer.name()


# ── action application ────────────────────────────────────────────────────────

def _apply_actions(layer, action_list):
    mgr = layer.actions()
    managed = {name for name, *_ in action_list}
    for act in list(mgr.actions()):
        if act.name() in managed:
            mgr.removeAction(act.id())
    for name, code, short_title, scopes in action_list:
        action = QgsAction(
            QgsAction.GenericPython, name, code, '', False, short_title, scopes
        )
        mgr.addAction(action)


# ── signal handler ────────────────────────────────────────────────────────────

def _on_layer_added(layer):
    if _is_v2_building_layer(layer):
        _apply_actions(layer, _BUILDING_ACTIONS)
    elif _is_country_boundary_layer(layer):
        _apply_actions(layer, _COUNTRY_ACTIONS)
    elif _is_commune_layer(layer):
        _apply_actions(layer, _COMMUNE_ACTIONS)


# ── project lifecycle ─────────────────────────────────────────────────────────

def openProject():
    conn = _read_connection()
    if conn:
        _patch_layer_connections(conn)

    QgsProject.instance().layerWasAdded.connect(_on_layer_added)

    for layer in QgsProject.instance().mapLayers().values():
        if _is_v2_building_layer(layer):
            _apply_actions(layer, _BUILDING_ACTIONS)
        elif _is_country_boundary_layer(layer):
            _apply_actions(layer, _COUNTRY_ACTIONS)
        elif _is_commune_layer(layer):
            _apply_actions(layer, _COMMUNE_ACTIONS)


def saveProject():
    pass


def closeProject():
    try:
        QgsProject.instance().layerWasAdded.disconnect(_on_layer_added)
    except Exception:
        pass
