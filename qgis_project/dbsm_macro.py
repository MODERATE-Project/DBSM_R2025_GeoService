# QGIS Project Macro — DBSM Demo
# Canonical source. Content is injected into <ProjectMacros><pythonCode>
# by inject_macro.py; edit here and re-run inject_macro.py to update the .qgs.
#
# openProject()   – applies building actions to every v2 layer already in the
#                   project and connects the layerWasAdded signal so future
#                   layers (e.g. "vista actual") are handled automatically.
# closeProject()  – disconnects the signal to avoid stale references.

from qgis.core import QgsProject, QgsDataSourceUri, QgsVectorLayer, QgsAction

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
            "Sin resultados", f"No hay edificios similares en {RADIUS_M}m",
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
            "Filtro activo",
            f"{len(fids)} similares en radio {RADIUS_M}m — usa 'Restablecer vista' para volver",
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

iface.messageBar().pushMessage("OK", "Vista restablecida", level=0, duration=3)
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

nueva_capa = QgsVectorLayer(uri.uri(), f"{country}.v2 — vista actual", "postgres")

if not nueva_capa.isValid():
    iface.messageBar().pushMessage(
        "Error", f"No se pudo cargar v2.{country}", level=3
    )
else:
    QgsProject.instance().addMapLayer(nueva_capa)
    n = nueva_capa.featureCount()
    iface.messageBar().pushMessage(
        "OK", f"{n} edificios cargados en la vista actual", level=0, duration=5
    )
"""

# (name, code, shortTitle, scopes)
_ACTIONS = [
    ('Get similar buildings', _GET_SIMILAR,  'Similar buildings', {'Feature', 'Canvas'}),
    ('Restore view',          _RESTORE_VIEW, 'Restore view',      {'Feature', 'Canvas'}),
    ('Show buildings in bbox', _SHOW_BBOX,   'Buildings in bbox', {'Feature', 'Canvas'}),
]

_MANAGED_NAMES = {name for name, *_ in _ACTIONS}


def _is_v2_building_layer(layer):
    if not isinstance(layer, QgsVectorLayer):
        return False
    try:
        uri = QgsDataSourceUri(layer.dataProvider().dataSourceUri())
        return uri.schema() == 'v2' and bool(uri.table())
    except Exception:
        return False


def _apply_building_actions(layer):
    mgr = layer.actions()
    for act in list(mgr.actions()):
        if act.name() in _MANAGED_NAMES:
            mgr.removeAction(act.id())
    for name, code, short_title, scopes in _ACTIONS:
        action = QgsAction(
            QgsAction.GenericPython, name, code, '', False, short_title, scopes
        )
        mgr.addAction(action)


def _on_layer_added(layer):
    if _is_v2_building_layer(layer):
        _apply_building_actions(layer)


def openProject():
    QgsProject.instance().layerWasAdded.connect(_on_layer_added)
    for layer in QgsProject.instance().mapLayers().values():
        if _is_v2_building_layer(layer):
            _apply_building_actions(layer)


def saveProject():
    pass


def closeProject():
    try:
        QgsProject.instance().layerWasAdded.disconnect(_on_layer_added)
    except Exception:
        pass
