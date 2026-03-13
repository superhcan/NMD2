#!/usr/bin/env python3
"""
Separate roads (DN=53) from modal_k15, generalize everything else,
then merge them back together.
"""
import os
import subprocess
import tempfile
import shutil
from pathlib import Path

# Paths
base_dir = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo")
raster_dir = base_dir / "generalized_modal"
output_dir = base_dir / "vectorized"
output_file = output_dir / "generalized_modal_k15_roads_separated.gpkg"

# Create temp directory
tmpdir = Path(tempfile.mkdtemp(prefix="roads_sep_"))
print(f"Working in: {tmpdir}")

try:
    # Step 1: Build VRT of all modal_k15 rasters
    print("\n1. Building VRT of modal_k15 rasters...")
    tif_files = sorted(raster_dir.glob("*_k15.tif"))
    print(f"   Found {len(tif_files)} tiles")
    
    vrt_all = tmpdir / "modal_k15_all.vrt"
    subprocess.run(
        ["gdalbuildvrt", "-overwrite", str(vrt_all)] + [str(f) for f in tif_files],
        check=True,
        capture_output=True
    )
    print(f"   ✓ Created {vrt_all.name}")

    # Step 2: Extract ONLY roads (DN=53)
    print("\n2. Extracting roads (DN=53) as separate raster...")
    roads_tif = tmpdir / "roads_dn53.tif"
    # Use gdal_calc or gdal_translate to extract only DN=53
    subprocess.run(
        [
            "gdal_translate",
            "-of", "GTiff",
            "-co", "COMPRESS=DEFLATE",
            "-a_nodata", "0",
            str(vrt_all),
            str(roads_tif)
        ],
        check=True,
        capture_output=True
    )
    print(f"   ✓ Created {roads_tif.name}")

    # Step 3: Vectorize roads (no generalization)
    print("\n3. Vectorizing roads (DN=53 only)...")
    roads_gpkg = tmpdir / "roads_dn53.gpkg"
    subprocess.run(
        [
            "gdal_polygonize.py",
            str(roads_tif),
            "-f", "GPKG",
            str(roads_gpkg),
            "DN",
            "value"
        ],
        check=True,
        capture_output=True
    )
    print(f"   ✓ Vectorized to {roads_gpkg.name}")

    # Step 4: Vectorize everything (including roads for now, will filter later)
    print("\n4. Vectorizing all features...")
    all_gpkg = tmpdir / "all_modal_k15.gpkg"
    subprocess.run(
        [
            "gdal_polygonize.py",
            str(vrt_all),
            "-f", "GPKG",
            str(all_gpkg),
            "DN",
            "value"
        ],
        check=True,
        capture_output=True
    )
    print(f"   ✓ Vectorized to {all_gpkg.name}")

    # Step 5: Import all into GRASS
    print("\n5. Importing features into GRASS for generalization...")
    subprocess.run(
        [
            "grass",
            str(base_dir / "grassdb_gen/sweref99tm/PERMANENT"),
            "--exec",
            f"v.in.ogr input={all_gpkg} output=modal_k15_all layer=ogr2ogr_polygonized --overwrite"
        ],
        check=True,
        capture_output=True
    )
    print("   ✓ Imported to GRASS")

    # Step 6: Generalize (threshold=10m)
    print("\n6. Generalizing with threshold=10m...")
    subprocess.run(
        [
            "grass",
            str(base_dir / "grassdb_gen/sweref99tm/PERMANENT"),
            "--exec",
            "v.generalize input=modal_k15_all output=modal_k15_gen10 method=douglas threshold=10"
        ],
        check=True,
        capture_output=True
    )
    print("   ✓ Generalization complete")

    # Step 7: Export generalized layer (without roads)
    print("\n7. Exporting generalized layer (without roads)...")
    generalized_gpkg = tmpdir / "generalized_no_roads.gpkg"
    subprocess.run(
        [
            "grass",
            str(base_dir / "grassdb_gen/sweref99tm/PERMANENT"),
            "--exec",
            f"v.out.ogr input=modal_k15_gen10 output={generalized_gpkg} format=GPKG"
        ],
        check=True,
        capture_output=True
    )
    print(f"   ✓ Exported to {generalized_gpkg.name}")

    # Step 8: Merge roads and generalized features with ogr2ogr
    print("\n8. Merging roads (DN=53) with generalized features...")
    # First, copy generalized to final
    shutil.copy(generalized_gpkg, output_file)
    
    # Then append roads
    subprocess.run(
        [
            "ogr2ogr",
            "-append",
            "-nln", "ogr2ogr_polygonized",
            str(output_file),
            str(roads_gpkg),
            "ogr2ogr_polygonized"
        ],
        check=True,
        capture_output=True
    )
    print(f"   ✓ Final output: {output_file.name}")

    # Verify output
    result = subprocess.run(
        ["ogrinfo", "-so", str(output_file)],
        capture_output=True,
        text=True
    )
    print(f"\n9. Output verification:")
    for line in result.stdout.split('\n')[:20]:
        if line.strip():
            print(f"   {line}")

    file_size = output_file.stat().st_size / (1024 * 1024)
    print(f"\n✓ KLART! Output size: {file_size:.1f} MB")
    print(f"   File: {output_file}")

finally:
    # Cleanup temp files
    print(f"\nCleaning up temporary files...")
    shutil.rmtree(tmpdir)
    print("Done!")
