#!/usr/bin/env python3
"""Minimize legend in QGIS project using API."""
import sys
sys.path.insert(0, '/usr/lib/python3/dist-packages')
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from qgis.core import QgsApplication, QgsProject
from pathlib import Path

# Initialize QGIS
QgsApplication.setPrefixPath('/usr', True)
qgs_app = QgsApplication([], False)

project_path = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v5/Pipeline.qgs")

print(f"Läser projekt: {project_path.name}")

# Open project
project = QgsProject()
project.read(str(project_path))

# Get the root layer tree
root = project.layerTreeRoot()

# Collapse all groups recursively
def collapse_all_groups(node):
    """Collapse all layer tree groups."""
    if hasattr(node, 'children'):
        for child in node.children():
            if hasattr(child, 'setExpanded'):
                child.setExpanded(False)
            # Recursively collapse nested groups
            if hasattr(child, 'children'):
                collapse_all_groups(child)

print("Kollapsar alla lagergrupper...")
collapse_all_groups(root)

# Save project
project.write(str(project_path))
print("✅ Projekt sparad med alla grupper kollapsade")

# Cleanup
qgs_app.exitQgis()

