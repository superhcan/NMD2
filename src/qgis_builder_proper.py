#!/usr/bin/env python3
"""
QGIS Project Builder - Using Official QGIS Python API
Kör med: python3 -c "import sys; sys.path.insert(0, '/usr/lib/python3/dist-packages'); exec(open('qgis_builder_proper.py').read())"
"""

import sys
sys.path.insert(0, '/usr/lib/python3/dist-packages')

from pathlib import Path
from qgis.core import (
    QgsProject, QgsRasterLayer, QgsLayerTree, 
    QgsLayerTreeGroup, QgsLayerTreeLayer, QgsCoordinateReferenceSystem
)


def create_qgis_project(out_path: Path, tile_paths: list):
    """Create QGIS project using official API"""
    
    print(f"🚀 Skapar QGIS projekt med officiell API")
    
    # Create project
    project = QgsProject()
    
    # Set CRS (SWEREF99 TM)
    crs = QgsCoordinateReferenceSystem("EPSG:3006")
    project.setCrs(crs)
    
    print(f"✓ CRS: SWEREF99 TM (EPSG:3006)")
    
    # Create root layer tree group
    root = project.layerTreeRoot()
    root.setName("Pipeline")
    
    # Create Step 1 group
    step1_group = QgsLayerTreeGroup("Step 1 - Split Tiles")
    root.addChildNode(step1_group)
    
    print(f"✓ Step 1 grupp skapad")
    
    # Add raster layers
    added_count = 0
    for tile_path in sorted(tile_paths):
        tile_path = Path(tile_path)
        layer_name = tile_path.stem
        
        # Create raster layer
        raster_layer = QgsRasterLayer(str(tile_path), layer_name, "gdal")
        
        if raster_layer.isValid():
            # Add to project
            project.addMapLayer(raster_layer, addToLegend=False)
            
            # Add to layer tree
            tree_layer = QgsLayerTreeLayer(raster_layer)
            step1_group.addChildNode(tree_layer)
            
            added_count += 1
            print(f"   ✓ {layer_name}")
        else:
            print(f"   ❌ Invalid: {layer_name}")
    
    print(f"✓ {added_count} lager adderade")
    
    # Save project
    project.write(str(out_path))
    
    size_kb = out_path.stat().st_size / 1024
    print(f"✅ Projekt sparad: {out_path.name} ({size_kb:.1f} KB)")
    
    return out_path


def main():
    from pipeline_1024_halo import step1_split, OUT_BASE
    
    tile_paths = step1_split()
    print(f"📊 Hittat {len(tile_paths)} tiles")
    
    out_file = OUT_BASE / "Pipeline.qgs"
    create_qgis_project(out_file, tile_paths)


if __name__ == "__main__":
    main()
