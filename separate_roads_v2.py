#!/usr/bin/env python3
"""
Simple approach: Separate roads, generalize everything else with GRASS,
then merge with geopandas.
"""
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
import pandas as pd
import geopandas as gpd

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

    # Step 2: Vectorize everything
    print("\n2. Vectorizing all features...")
    all_gpkg = tmpdir / "all_modal_k15.gpkg"
    subprocess.run(
        ["gdal_polygonize.py", str(vrt_all), "-f", "GPKG", str(all_gpkg), "DN", "value"],
        check=True,
        capture_output=True
    )
    print(f"   ✓ Vectorized")

    # Step 3: Load with geopandas
    print("\n3. Loading vectorized data...")
    gdf = gpd.read_file(all_gpkg)
    print(f"   ✓ Loaded {len(gdf)} polygons")
    print(f"   Columns: {list(gdf.columns)}")
    
    # Find the raster value column (might be 'value' or 'DN')
    value_col = 'value' if 'value' in gdf.columns else 'DN'
    print(f"   Value column: {value_col}")
    print(f"   Values: {sorted(gdf[value_col].unique())}")

    # Step 4: Separate roads (DN=53)
    print("\n4. Separating roads (DN=53) and other features...")
    roads = gdf[gdf[value_col] == 53].copy()
    other = gdf[gdf[value_col] != 53].copy()
    print(f"   ✓ Roads: {len(roads)} polygons")
    print(f"   ✓ Other: {len(other)} polygons")

    # Step 5: Export other features to temp file for GRASS
    if len(other) > 0:
        print("\n5. Exporting non-road features for generalization...")
        other_gpkg = tmpdir / "other_features.gpkg"
        other.to_file(other_gpkg, driver='GPKG')
        print(f"   ✓ Exported {len(other)} polygons")

        # Step 6: Create GRASS database and import
        print("\n6. Setting up GRASS database...")
        grass_dir = tmpdir / "grassdb"
        grass_dir.mkdir()
        
        # Create location with EPSG:3006
        subprocess.run(
            [
                "grass",
                "-c",
                "EPSG:3006",
                str(grass_dir / "project"),
                "--exec",
                "exit"
            ],
            check=True,
            capture_output=True
        )
        print(f"   ✓ Created GRASS location")

        # Import other features
        print("\n7. Importing features into GRASS...")
        grass_location = str(grass_dir / "project")
        subprocess.run(
            [
                "grass",
                grass_location,
                "--exec",
                f"v.in.ogr input={other_gpkg} output=features layer=0 --overwrite"
            ],
            check=True,
            capture_output=True
        )
        print("   ✓ Imported")

        # Step 8: Generalize
        print("\n8. Generalizing with threshold=10m...")
        subprocess.run(
            [
                "grass",
                grass_location,
                "--exec",
                "v.generalize input=features output=features_gen method=douglas threshold=10"
            ],
            check=True,
            capture_output=True
        )
        print("   ✓ Generalized")

        # Step 9: Export generalized
        print("\n9. Exporting generalized features...")
        gen_gpkg = tmpdir / "features_generalized.gpkg"
        subprocess.run(
            [
                "grass",
                grass_location,
                "--exec",
                f"v.out.ogr input=features_gen output={gen_gpkg} format=GPKG"
            ],
            check=True,
            capture_output=True
        )
        print("   ✓ Exported")

        # Step 10: Load and merge
        print("\n10. Merging roads and generalized features...")
        gen_gdf = gpd.read_file(gen_gpkg)
        print(f"    ✓ Loaded {len(gen_gdf)} generalized polygons")

        # Combine: roads (unmodified) + generalized other features
        combined = gpd.GeoDataFrame(
            pd.concat([roads, gen_gdf], ignore_index=True),
            crs=roads.crs
        )
        print(f"    ✓ Combined: {len(combined)} total polygons")

        # Save
        print(f"\n11. Saving final output...")
        combined.to_file(output_file, driver='GPKG')
        file_size = output_file.stat().st_size / (1024 * 1024)
        print(f"    ✓ Saved to {output_file.name}")
        print(f"    Size: {file_size:.1f} MB")

    else:
        print("   WARNING: No other features found!")

finally:
    print(f"\nCleaning up temporary files...")
    shutil.rmtree(tmpdir)
    print("Done!")
