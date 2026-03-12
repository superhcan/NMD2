#!/usr/bin/env python3
"""
Simplest approach: use Shapely's simplify() directly.
- Roads (DN=53): keep as-is
- Other features: simplify with tolerance
"""
import subprocess
import tempfile
import shutil
from pathlib import Path
import pandas as pd
import geopandas as gpd
from shapely.geometry import shape

# Paths
base_dir = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo")
raster_dir = base_dir / "generalized_modal"
output_dir = base_dir / "vectorized"
output_file = output_dir / "generalized_modal_k15_roads_preserved.gpkg"

tmpdir = Path(tempfile.mkdtemp(prefix="roads_sep_"))
print(f"Working in: {tmpdir}")

try:
    # Step 1: Build VRT
    print("\n1. Building VRT of modal_k15 rasters...")
    tif_files = sorted(raster_dir.glob("*_k15.tif"))
    vrt_all = tmpdir / "modal_k15_all.vrt"
    subprocess.run(
        ["gdalbuildvrt", "-overwrite", str(vrt_all)] + [str(f) for f in tif_files],
        check=True,
        capture_output=True
    )
    print(f"   ✓ Created VRT with {len(tif_files)} tiles")

    # Step 2: Vectorize
    print("\n2. Vectorizing all features...")
    all_gpkg = tmpdir / "all_modal_k15.gpkg"
    subprocess.run(
        ["gdal_polygonize.py", str(vrt_all), "-f", "GPKG", str(all_gpkg), "DN", "value"],
        check=True,
        capture_output=True
    )
    print(f"   ✓ Vectorized")

    # Step 3: Load
    print("\n3. Loading vectorized data...")
    gdf = gpd.read_file(all_gpkg)
    print(f"   ✓ Loaded {len(gdf)} polygons")
    
    # Step 4: Separate roads (value=53)
    print("\n4. Separating roads (value=53)...")
    roads = gdf[gdf['value'] == 53].copy() if 53 in gdf['value'].values else gpd.GeoDataFrame()
    other = gdf[gdf['value'] != 53].copy()
    print(f"   ✓ Roads: {len(roads)} polygons")
    print(f"   ✓ Other: {len(other)} polygons")

    # Step 5: Simplify other features with Shapely
    print("\n5. Simplifying non-road features (tolerance=10m)...")
    # Tolerance in map units (10m for EPSG:3006)
    other['geometry'] = other['geometry'].simplify(tolerance=10, preserve_topology=True)
    print(f"   ✓ Simplified {len(other)} polygons")

    # Step 6: Combine
    print("\n6. Combining roads (preserved) + simplified features...")
    combined = gpd.GeoDataFrame(
        pd.concat([roads, other], ignore_index=True),
        crs=gdf.crs
    )
    print(f"   ✓ Total: {len(combined)} polygons")
    print(f"      - Roads (DN=53): {len(roads)}")
    print(f"      - Other (simplified): {len(other)}")

    # Step 7: Save
    print(f"\n7. Saving to {output_file.name}...")
    combined.to_file(output_file, driver='GPKG', index=False)
    file_size = output_file.stat().st_size / (1024 * 1024)
    print(f"   ✓ Size: {file_size:.1f} MB")
    print(f"\n✓ KLART!")

finally:
    print(f"\nCleaning up...")
    shutil.rmtree(tmpdir)
    print("Done!")
