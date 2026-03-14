#!/usr/bin/env python3
"""
Create minimal valid QGIS project using simple XML structure.
"""

import sys
import shutil
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import rasterio

OUT_BASE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v5")
OUT_BASE.mkdir(parents=True, exist_ok=True)

tile_dir = OUT_BASE / "tiles"
project_file = OUT_BASE / "Pipeline.qgz"

if not tile_dir.exists():
    print("❌ Tiles directory not found!")
    sys.exit(1)

tiles = sorted(tile_dir.glob("*.tif"))[:3]  # Just first 3 tiles
if not tiles:
    print("❌ No tiles found!")
    sys.exit(1)

print(f"📁 Found {len(tiles)} tiles")

# Read actual extent from first tile
with rasterio.open(tiles[0]) as src:
    bounds = src.bounds
    crs = src.crs
    print(f"✓ Extent from first tile: {bounds}")
    print(f"✓ CRS: {crs}")
    xmin, ymin, xmax, ymax = bounds.left, bounds.bottom, bounds.right, bounds.top

# Create minimal QGIS project XML
root = ET.Element("qgis")
root.set("version", "3.44.0")
root.set("projectname", "NMD Pipeline")

# Title
title = ET.SubElement(root, "title")
title.text = "NMD2 Pipeline"

# CRS (EPSG:3006)
crs_elem = ET.SubElement(root, "crs")
spatial_ref = ET.SubElement(crs_elem, "spatialrefsys")
ET.SubElement(spatial_ref, "proj4").text = "+proj=rt90 +lat_0=0 +lon_0=15.80827824305556 +ellps=bessel +units=m +no_defs"
ET.SubElement(spatial_ref, "srsid").text = "3006"
ET.SubElement(spatial_ref, "srid").text = "3006"
ET.SubElement(spatial_ref, "authid").text = "EPSG:3006"
ET.SubElement(spatial_ref, "description").text = "RT90 2.5 gon V"

# Extent
extent_elem = ET.SubElement(root, "extent")
ET.SubElement(extent_elem, "xmin").text = str(int(xmin))
ET.SubElement(extent_elem, "ymin").text = str(int(ymin))
ET.SubElement(extent_elem, "xmax").text = str(int(xmax))
ET.SubElement(extent_elem, "ymax").text = str(int(ymax))

# Maplayers
maplayers = ET.SubElement(root, "maplayers")

for tile_path in tiles:
    rel_path = f"tiles/{tile_path.name}"
    
    maplayer = ET.SubElement(maplayers, "maplayer")
    maplayer.set("type", "raster")
    maplayer.set("refreshOnNotifyEnabled", "0")
    maplayer.set("refreshNotifyInterval", "0")
    maplayer.set("hasScaleBasedVisibilityFlag", "0")
    maplayer.set("autoRefreshEnabled", "0")
    maplayer.set("autoRefreshInterval", "0")
    maplayer.set("maxScale", "0")
    maplayer.set("minScale", "1e+08")
    maplayer.set("styleCategories", "AllStyleCategories")
    maplayer.set("validate", "1")
    
    # Name
    name = ET.SubElement(maplayer, "name")
    name.text = tile_path.stem
    
    # Path/source
    datasource = ET.SubElement(maplayer, "datasource")
    datasource.text = rel_path
    
    # Provider
    provider = ET.SubElement(maplayer, "provider")
    provider.text = "gdal"
    
    # Extent (from actual data)
    extent = ET.SubElement(maplayer, "extent")
    ET.SubElement(extent, "xmin").text = str(int(xmin))
    ET.SubElement(extent, "ymin").text = str(int(ymin))
    ET.SubElement(extent, "xmax").text = str(int(xmax))
    ET.SubElement(extent, "ymax").text = str(int(ymax))
    
    # CRS
    srs = ET.SubElement(maplayer, "srs")
    spatial_ref = ET.SubElement(srs, "spatialrefsys")
    ET.SubElement(spatial_ref, "authid").text = "EPSG:3006"
    
    # Opacity
    opacity = ET.SubElement(maplayer, "layerOpacity")
    opacity.text = "1"

# Save to temporary location
temp_dir = tempfile.mkdtemp()
temp_qgs = Path(temp_dir) / "project.qgs"

tree = ET.ElementTree(root)
tree.write(temp_qgs, encoding="utf-8", xml_declaration=True)
print(f"\n✓ XML created: {temp_qgs}")

# Create .qgz (which is just a .zip with .qgs inside)
if project_file.exists():
    project_file.unlink()

with zipfile.ZipFile(project_file, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.write(temp_qgs, arcname="project.qgs")

print(f"✅ QGIS project saved: {project_file}")
print(f"   Size: {project_file.stat().st_size} bytes")

# Cleanup
shutil.rmtree(temp_dir)

print("\n✅ Test completed!")
print(f"\nTo open in QGIS:")
print(f"  cd {OUT_BASE}")
print(f"  qgis Pipeline.qgz")
