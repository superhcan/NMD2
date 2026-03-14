#!/usr/bin/env python3
"""Build complete QGIS project with all 7 steps in reverse order (7 at top, 1 at bottom)."""
import sys
sys.path.insert(0, '/usr/lib/python3/dist-packages')
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from qgis.core import QgsApplication, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsLayerTreeGroup, QgsLayerTreeLayer, QgsCoordinateReferenceSystem
from pathlib import Path

# Initialize QGIS
QgsApplication.setPrefixPath('/usr', True)
qgs_app = QgsApplication([], False)

# Paths
base_path = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v6")
project_path = base_path / "Pipeline.qgs"

# Open existing project (or create new one)
project = QgsProject()
if project_path.exists():
    project.read(str(project_path))
else:
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:3006"))

# Get root and clear it
root = project.layerTreeRoot()
root.setName("Pipeline")
root.setExpanded(False)  # Minimera rootgruppen

# Remove old groups
for child in list(root.children()):
    root.removeChildNode(child)

# Define step names and directories
steps = [
    (7, "Step 7 - Simplified (Mapshaper)", base_path / "simplified"),
    (6, "Step 6 - Vectorized", base_path / "vectorized"),
    (5, "Step 5 - Generalized", base_path / "generalized_modal"),  # Show modal k=15
    (4, "Step 4a - Fill Islands", base_path / "filled"),
    (3, "Step 3 - Landscape Extract", base_path / "landscape"),
    (2, "Step 2 - Extract Protected", base_path / "protected"),
    (1, "Step 1 - Split Tiles", base_path / "tiles"),
]

print("Bygger QGIS-projekt med alla 7 steg (omvänd ordning)...\n")

for step_num, step_name, step_dir in steps:
    print(f"Arbetar med {step_name}...")
    
    if not step_dir.exists():
        print(f"  ⚠ Katalog finns inte: {step_dir}")
        continue
    
    # Create group (collapsed)
    group = QgsLayerTreeGroup(step_name)
    group.setExpanded(False)  # Minimize/collapse group
    root.addChildNode(group)
    
    # Determine file type
    if step_num <= 5:
        # Raster files
        layer_files = sorted(step_dir.glob("*.tif"))
    else:
        # Vector files (gpkg, shp, etc)
        layer_files = sorted(step_dir.glob("*.gpkg")) + sorted(step_dir.glob("*.shp"))
    
    if not layer_files:
        print(f"  ✗ Inga filer hittade")
        continue
    
    # Add layers (max 16 per group for performance)
    for layer_file in layer_files[:16]:
        layer_name = layer_file.stem
        
        if layer_file.suffix == ".tif":
            # Raster layer
            raster = QgsRasterLayer(str(layer_file), layer_name, "gdal")
            if raster.isValid():
                project.addMapLayer(raster, addToLegend=False)
                tree_layer = QgsLayerTreeLayer(raster)
                tree_layer.setExpanded(True)  # Expandera lagret
                group.addChildNode(tree_layer)
                print(f"  ✓ {layer_name}")
            else:
                print(f"  ✗ {layer_name} (invalid)")
        else:
            # Vector layer
            vec = QgsVectorLayer(str(layer_file), layer_name, "ogr")
            if vec.isValid():
                project.addMapLayer(vec, addToLegend=False)
                tree_layer = QgsLayerTreeLayer(vec)
                tree_layer.setExpanded(True)  # Expandera lagret
                group.addChildNode(tree_layer)
                print(f"  ✓ {layer_name}")
            else:
                print(f"  ✗ {layer_name} (invalid)")
    
    print()

# Save
project.write(str(project_path))

# Minimize legend in XML
import xml.etree.ElementTree as ET
tree = ET.parse(str(project_path))
root = tree.getroot()
legend = root.find("legend")
if legend is not None:
    legend.set("openPanel", "false")
    # Also hide the legend panel by default
tree.write(str(project_path), encoding='utf-8', xml_declaration=True)

size_kb = project_path.stat().st_size / 1024

print(f"✅ Projekt sparad: {project_path.name} ({size_kb:.1f} KB)")
print(f"Steg ordning: 7 (top) → 1 (bottom)")

# Cleanup
qgs_app.exitQgis()
