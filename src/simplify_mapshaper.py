#!/usr/bin/env python3
"""
Simplify vector data using Mapshaper with topology preservation.
Mapshaper preserves topology by working with shared arcs, not individual polygons.
"""

import subprocess
import json
import os
from pathlib import Path
import sys

def simplify_with_mapshaper(input_file, output_dir, tolerances=[90, 75, 50, 25]):
    """
    Simplify GeoPackage using Mapshaper CLI with topology preservation.
    
    Args:
        input_file: Path to input GeoPackage
        output_dir: Directory for output files
        tolerances: List of percentage values (% of removable vertices to retain)
                   90% = minimal simplification, 25% = aggressive simplification
    """
    
    input_path = Path(input_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    if not input_path.exists():
        print(f"❌ Input file not found: {input_file}")
        sys.exit(1)
    
    print(f"📁 Input: {input_path}")
    print(f"📁 Output: {output_path}")
    print()
    
    # Convert GeoPackage to GeoJSON for Mapshaper
    geojson_file = output_path / "temp_input.geojson"
    print(f"🔄 Converting GeoPackage to GeoJSON...")
    ogr_cmd = [
        "ogr2ogr",
        "-f", "GeoJSON",
        str(geojson_file),
        str(input_path)
    ]
    result = subprocess.run(ogr_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ GeoJSON conversion failed: {result.stderr}")
        sys.exit(1)
    print(f"✓ GeoJSON created: {geojson_file.stat().st_size / 1024 / 1024:.1f} MB")
    print()
    
    # Simplify with Mapshaper for each tolerance
    print(f"⚙️  Simplifying with Mapshaper (topology-preserving):")
    print(f"    (percentage = % of removable vertices to retain)")
    print()
    
    for tolerance in tolerances:
        output_geojson = output_path / f"modal_k15_simplified_p{tolerance}.geojson"
        output_gpkg = output_path / f"modal_k15_simplified_p{tolerance}.gpkg"
        
        # Mapshaper command with topology preservation
        # percentage=X retains X% of removable vertices
        # Higher percentage = less simplification, Lower percentage = more simplification
        # 90% = minimal simplification, 25% = aggressive simplification
        mapshaper_cmd = [
            "mapshaper",
            str(geojson_file),
            "-simplify",
            f"percentage={tolerance}%",  # Keep X% of removable vertices
            "planar",                     # Use planar projection (2D)
            "keep-shapes",                # Preserve polygon shapes
            "-o",
            "format=geojson",
            str(output_geojson)
        ]
        
        print(f"  p{tolerance}%: ", end="", flush=True)
        result = subprocess.run(mapshaper_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ Failed")
            print(f"     Error: {result.stderr}")
            continue
        
        geojson_size = output_geojson.stat().st_size / 1024 / 1024
        print(f"  GeoJSON: {geojson_size:.1f} MB", end="", flush=True)
        
        # Convert back to GeoPackage with correct CRS (EPSG:3006)
        # The GeoJSON coordinates are already in EPSG:3006, so use -a_srs to assign the CRS
        ogr_cmd = [
            "ogr2ogr",
            "-f", "GPKG",
            "-a_srs", "EPSG:3006",      # Assign CRS without reprojection
            str(output_gpkg),
            str(output_geojson)
        ]
        result = subprocess.run(ogr_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f" ❌ GeoPackage conversion failed")
            print(f"     stderr: {result.stderr}")
            print(f"     stdout: {result.stdout}")
            continue
        
        gpkg_size = output_gpkg.stat().st_size / 1024 / 1024
        print(f" → GeoPackage: {gpkg_size:.1f} MB ✓")
        
        # Clean up GeoJSON (only keep final GPKG)
        output_geojson.unlink()
    
    # Clean up temp GeoJSON
    geojson_file.unlink()
    
    print()
    print("✓ Simplification complete!")
    print(f"📁 Output files in: {output_path}")

if __name__ == "__main__":
    # Update these paths as needed
    input_file = "/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v2/vectorized/modal_k15_generalized.gpkg"
    output_dir = "/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v2/simplified/"
    
    simplify_with_mapshaper(input_file, output_dir)
