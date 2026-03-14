#!/usr/bin/env python3
"""Add Step 2 (protected classes) layers to QGIS project."""
import sys
import os
sys.path.insert(0, '/usr/lib/python3/dist-packages')

# Initialize QGIS application without GUI
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from qgis.core import QgsApplication, QgsProject, QgsRasterLayer, QgsLayerTreeGroup, QgsLayerTreeLayer
from pathlib import Path

# Initialize QGIS
QgsApplication.setPrefixPath('/usr', True)
qgs_app = QgsApplication([], False)

# Paths
project_path = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v5/Pipeline.qgs")
protected_dir = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v5/protected")

# Open existing project
print("Öppnar projektet...")
project = QgsProject()
project.read(str(project_path))

# Get root
root = project.layerTreeRoot()

# Find or create Step 2 group
step2_group = None
for child in root.children():
    if hasattr(child, 'name') and child.name() == "Step 2 - Extract Protected":
        step2_group = child
        break

if step2_group is None:
    print("Skapar Step 2-grupp...")
    step2_group = QgsLayerTreeGroup("Step 2 - Extract Protected")
    root.addChildNode(step2_group)
else:
    print("Step 2-grupp hittad, rensar gamla lager...")
    # Remove old layers
    for child in list(step2_group.children()):
        step2_group.removeChildNode(child)

# Add protected tiles
protected_paths = sorted(protected_dir.glob("NMD2023bas_tile_*.tif"))
print(f"Lägger till {len(protected_paths)} skyddade klassttiles...")

for tile_path in protected_paths:
    layer_name = tile_path.stem
    raster = QgsRasterLayer(str(tile_path), layer_name, "gdal")
    
    if raster.isValid():
        project.addMapLayer(raster, addToLegend=False)
        tree_layer = QgsLayerTreeLayer(raster)
        step2_group.addChildNode(tree_layer)
        print(f"  ✓ {layer_name}")
    else:
        print(f"  ✗ {layer_name} (invänd)")

# Save
print("Sparar projektet...")
project.write(str(project_path))

size_kb = project_path.stat().st_size / 1024
print(f"\n✅ Step 2 tillagd: {len(protected_paths)} lager ({size_kb:.1f} KB)")

# Cleanup
qgs_app.exitQgis()

