#!/usr/bin/env python3
"""
Test: Använd QGIS Python API för att bygga QGIS-projekt
"""

import os
import sys
from pathlib import Path

# Setup QGIS environment
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from qgis.core import (
    QgsApplication, QgsProject, QgsRasterLayer, QgsLayerTree,
    QgsCategorizedSymbolRenderer, QgsRasterRenderer, QgsPalettedRasterRenderer
)

# Initialize QGIS
QgsApplication.setPrefixPath("/usr", True)
qgs = QgsApplication([], False)
qgs.initQgisResources()

OUT_BASE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v5")
OUT_BASE.mkdir(parents=True, exist_ok=True)

# Create project
project_path = OUT_BASE / "test_qgis_api.qgz"
project = QgsProject.instance()
project.setFileName(str(project_path))

print(f"📁 Creating project: {project_path}")

# Get first tile
tile_dir = OUT_BASE / "tiles"
if not tile_dir.exists():
    print("❌ Tiles directory not found!")
    sys.exit(1)

tiles = sorted(tile_dir.glob("*.tif"))[:1]
if not tiles:
    print("❌ No tiles found!")
    sys.exit(1)

tile_path = tiles[0]
print(f"📄 Loading tile: {tile_path.name}")

# Add raster layer
layer = QgsRasterLayer(str(tile_path), tile_path.stem)
if not layer.isValid():
    print(f"❌ Layer is not valid!")
    sys.exit(1)

print(f"✓ Layer loaded: {layer.name()}")
print(f"  Extent: {layer.extent().toString()}")
print(f"  CRS: {layer.crs().authid()}")

# Add to project
project.addMapLayer(layer)

# Save project
project.write()
print(f"✅ Project saved: {project_path}")

# Check if file exists
if not project_path.exists():
    print(f"❌ Project file was not created!")
    sys.exit(1)

print(f"✓ Project file size: {project_path.stat().st_size} bytes")

# Cleanup
qgs.exitQgis()
print("\n✅ Test completed!")
