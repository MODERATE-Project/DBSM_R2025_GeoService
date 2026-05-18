#!/usr/bin/env python3
"""
Inject the DBSM project macro into dbsm_demo.qgs.

What it does:
  1. Reads dbsm_macro.py for the macro source.
  2. Removes the three managed building actions from every layer that has them
     (they are re-applied by the macro at runtime for all v2 layers).
  3. Writes the macro into <properties><Macros><pythonCode type="QString">,
     the location QGIS 3.x reads for project macros.
  4. Saves the modified project file (overwrites in-place).

IMPORTANT: run with QGIS closed (or at least with the project not open).
QGIS rewrites the file on close/save, which would discard changes made here
while the project was open.

Run from the qgis_project/ directory:
  python3 inject_macro.py
Or from the repo root:
  python3 qgis_project/inject_macro.py
"""

import pathlib
import xml.etree.ElementTree as ET

# ── paths ─────────────────────────────────────────────────────────────────────

HERE  = pathlib.Path(__file__).parent
QGS   = HERE / "dbsm_demo.qgs"
MACRO = HERE / "dbsm_macro.py"

MANAGED = {'Get similar buildings', 'Restore view', 'Show buildings in bbox'}

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

# ── inject macro into <properties><Macros><pythonCode type="QString"> ─────────
# This is the location QGIS 3.x reads project macros from.

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

props2 = root2.find("properties")
macros2 = props2.find("Macros") if props2 is not None else None
py_code2 = macros2.find("pythonCode") if macros2 is not None else None

if py_code2 is not None and py_code2.text:
    print(f"Verification OK — <properties><Macros><pythonCode> present "
          f"({len(py_code2.text)} chars, type='{py_code2.get('type')}').")
else:
    print("ERROR: macro not found in <properties><Macros> after write!")

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
