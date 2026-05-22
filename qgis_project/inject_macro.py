#!/usr/bin/env python3
"""
Inject the DBSM project macro into dbsm_demo.qgs and optionally patch
all PostgreSQL datasource connections.

What it does:
  1. Reads dbsm_macro.py for the macro source.
  2. Removes all macro-managed actions from every layer in the XML
     (they are re-applied at runtime by openProject()).
  3. Writes the macro into <properties><Macros><pythonCode>.
  4. If connection.cfg exists in the same directory, patches every
     PostgreSQL <datasource> and layer-tree source attribute to use the
     configured host, port, user, password, and database. This avoids
     QGIS prompting for credentials on project open because the correct
     connection is already embedded in the file.
  5. Saves the modified project file (overwrites in-place).

IMPORTANT: run with QGIS closed (or at least with the project not open).
QGIS rewrites the file on close/save, which would discard changes made here
while the project was open.

Workflow for a new environment:
  cp connection.default.cfg connection.cfg
  # edit connection.cfg with the correct host/port/password
  python3 inject_macro.py
  # open dbsm_demo.qgs in QGIS — no credential prompts

Run from the qgis_project/ directory:
  python3 inject_macro.py
Or from the repo root:
  python3 qgis_project/inject_macro.py
"""

import configparser
import pathlib
import re
import xml.etree.ElementTree as ET

# ── paths ─────────────────────────────────────────────────────────────────────

HERE  = pathlib.Path(__file__).parent
QGS   = HERE / "dbsm_demo.qgs"
MACRO = HERE / "dbsm_macro.py"
CFG   = HERE / "connection.cfg"

MANAGED = {
    'Get similar buildings', 'Restore view', 'Show buildings in bbox',
    'Load v2 country footprints', 'Load v1 country footprints',
    'Load commune footprints',
}

# ── load connection config (optional) ────────────────────────────────────────

conn = None
if CFG.exists():
    cfg = configparser.ConfigParser()
    cfg.read(str(CFG))
    conn = {
        'host':     cfg.get('connection', 'host',     fallback='localhost'),
        'port':     cfg.get('connection', 'port',     fallback='3500'),
        'user':     cfg.get('connection', 'user',     fallback='dbsm_admin'),
        'password': cfg.get('connection', 'password', fallback='postgres'),
        'database': cfg.get('connection', 'database', fallback='dbsm'),
    }
    print(f"connection.cfg found — will patch datasources to {conn['host']}:{conn['port']}")
else:
    print("connection.cfg not found — datasources will not be patched.")

# ── load macro source ─────────────────────────────────────────────────────────

macro_src = MACRO.read_text(encoding="utf-8")

# ── parse project XML ─────────────────────────────────────────────────────────

tree = ET.parse(QGS)
root = tree.getroot()

# ── remove managed actions from all layers ────────────────────────────────────

removed_total = 0
for layer in root.iter("maplayer"):
    actions_el = layer.find("attributeactions")
    if actions_el is None:
        continue
    to_remove = [
        act for act in actions_el.findall("actionsetting")
        if act.get("name") in MANAGED
    ]
    for act in to_remove:
        actions_el.remove(act)
        removed_total += 1

print(f"Removed {removed_total} managed action(s) from layer XML.")

# ── patch PostgreSQL datasources ──────────────────────────────────────────────

def _patch_uri(uri_str, conn):
    """Replace host, port, user, password, and dbname in a PostGIS URI string."""
    uri_str = re.sub(r"host=\S+",         f"host={conn['host']}",         uri_str)
    uri_str = re.sub(r"port=\d+",         f"port={conn['port']}",         uri_str)
    uri_str = re.sub(r"user='[^']*'",     f"user='{conn['user']}'",       uri_str)
    uri_str = re.sub(r"password='[^']*'", f"password='{conn['password']}'", uri_str)
    uri_str = re.sub(r"dbname='[^']*'",   f"dbname='{conn['database']}'", uri_str)
    return uri_str

patched_ds = 0
patched_lt = 0

if conn:
    # Patch <datasource> elements inside <maplayer> that look like PostGIS URIs
    for layer in root.iter("maplayer"):
        ds_el = layer.find("datasource")
        if ds_el is not None and ds_el.text and "host=" in ds_el.text and "dbname=" in ds_el.text:
            ds_el.text = _patch_uri(ds_el.text, conn)
            patched_ds += 1

    # Patch source= attribute in <layer-tree-layer> elements
    for lt_layer in root.iter("layer-tree-layer"):
        src = lt_layer.get("source", "")
        if "host=" in src and "dbname=" in src:
            lt_layer.set("source", _patch_uri(src, conn))
            patched_lt += 1

    print(f"Patched {patched_ds} <datasource> element(s) and "
          f"{patched_lt} layer-tree source attribute(s).")

# ── inject macro into <properties><Macros><pythonCode type="QString"> ─────────

props = root.find("properties")
if props is None:
    props = ET.SubElement(root, "properties")

macros_el = props.find("Macros")
if macros_el is not None:
    props.remove(macros_el)
    print("Replaced existing <Macros> element in <properties>.")
else:
    print("Inserted new <Macros> element in <properties>.")

macros_el = ET.SubElement(props, "Macros")
py_code_el = ET.SubElement(macros_el, "pythonCode")
py_code_el.set("type", "QString")
py_code_el.text = macro_src

# ── write back ────────────────────────────────────────────────────────────────

DOCTYPE = "<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n"

xml_str = ET.tostring(root, encoding="unicode", xml_declaration=False)
with open(QGS, "w", encoding="utf-8") as fh:
    fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    fh.write(DOCTYPE)
    fh.write(xml_str)

print(f"Saved: {QGS}")

# ── verify ────────────────────────────────────────────────────────────────────

tree2 = ET.parse(QGS)
root2 = tree2.getroot()

props2   = root2.find("properties")
macros2  = props2.find("Macros") if props2 is not None else None
py_code2 = macros2.find("pythonCode") if macros2 is not None else None

if py_code2 is not None and py_code2.text:
    print(f"Verification OK — macro present ({len(py_code2.text)} chars).")
else:
    print("ERROR: macro not found after write!")

remaining = sum(
    1
    for layer in root2.iter("maplayer")
    for actions_el in [layer.find("attributeactions")] if actions_el is not None
    for act in actions_el.findall("actionsetting")
    if act.get("name") in MANAGED
)
if remaining == 0:
    print("Verification OK — no managed actions remain in layer XML.")
else:
    print(f"WARNING: {remaining} managed action(s) still present in layer XML.")

if conn:
    # Spot-check one datasource to confirm patching
    sample = next(
        (ds.text
         for layer in root2.iter("maplayer")
         for ds in [layer.find("datasource")]
         if ds is not None and ds.text and "host=" in ds.text and "dbname=" in ds.text),
        None
    )
    if sample and conn['host'] in sample:
        print(f"Verification OK — datasources patched to {conn['host']}:{conn['port']}.")
    else:
        print("WARNING: datasource spot-check failed — check the output manually.")
