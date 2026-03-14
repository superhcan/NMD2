#!/usr/bin/env python3
"""
Test: Bara Step 1 + QGIS-projekt
"""

import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from pipeline_1024_halo import step1_split, OUT_BASE
from qgis_project_builder import create_pipeline_project

# Create output directory
OUT_BASE.mkdir(parents=True, exist_ok=True)

print(f"📁 Output directory: {OUT_BASE}")
print()

# Initialize QGIS project
print("📦 Initializing QGIS project...")
project_builder = create_pipeline_project(OUT_BASE)

# Step 1: Split tiles
print("\n🔄 Step 1: Split tiles")
tile_paths = step1_split()
print(f"✓ Created {len(tile_paths)} tiles")

# Add to QGIS project
project_builder.add_step_group(1, "Split Tiles")
for i, tile in enumerate(tile_paths):
    print(f"  Adding layer {i+1}/{len(tile_paths)}: {tile.name}")
    project_builder.add_raster_layer(tile, tile.stem, opacity=0.7)

project_builder.save()
print(f"\n✅ QGIS project saved: {project_builder.project_path}")

# Inspect XML
print("\n📄 Inspecting XML structure...")
import zipfile
from xml.etree import ElementTree as ET

with zipfile.ZipFile(project_builder.project_path, 'r') as z:
    with z.open('project.qgs') as f:
        tree = ET.parse(f)
        root = tree.getroot()
        
        # Check extent
        extent = root.find('.//extent')
        if extent is not None:
            xmin = extent.find('xmin').text if extent.find('xmin') is not None else 'N/A'
            xmax = extent.find('xmax').text if extent.find('xmax') is not None else 'N/A'
            print(f"  Extent: xmin={xmin}, xmax={xmax}")
        
        # Check CRS
        crs = root.find('.//crs')
        if crs is not None:
            authid = crs.find('.//authid')
            if authid is not None:
                print(f"  CRS: {authid.text}")
        
        # Check layer-tree
        layer_tree = root.find('.//layer-tree-group')
        if layer_tree is not None:
            print(f"  Layer tree root name: {layer_tree.get('name')}")
            
            # Count layers
            layers = layer_tree.findall('.//layer-tree-layer')
            print(f"  Total layers: {len(layers)}")
            
            # Show first few layer paths
            print("\n  First 3 layer sources:")
            for layer in layers[:3]:
                source = layer.get('source')
                name = layer.get('name')
                print(f"    {name}: {source}")

project_builder.cleanup()
print("\n✅ Test completed!")
