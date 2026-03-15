#!/usr/bin/env python3
"""Test different gdal_sieve approaches"""
import numpy as np
import rasterio
import subprocess
import tempfile
from pathlib import Path
from scipy import ndimage

OUT_BASE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles_v8")
WATER_CLASSES = {61, 62}
MMU_ISLAND = 100

tile_name = "NMD2023bas_tile_r000_c019.tif"
steg3_path = OUT_BASE / "steg3_landscape" / tile_name

with rasterio.open(steg3_path) as src:
    meta = src.meta.copy()
    data = src.read(1)

print("🧪 Testa olika gdal_sieve strategier\n")
print("=" * 60)

with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)
    
    # TEST 1: Current approach (binary mask)
    print("\n1️⃣ CURRENT: Binary mask (0=non-water, 1=water)")
    water_mask = np.isin(data, list(WATER_CLASSES))
    tmp_water1 = tmpdir / "water_mask_1.tif"
    tmp_out1 = tmpdir / "water_out_1.tif"
    
    with rasterio.open(tmp_water1, "w", **meta) as dst:
        dst.write(water_mask.astype(np.uint8), 1)
    
    result = subprocess.run([
        "gdal_sieve.py", "-st", "100", "-4",
        str(tmp_water1), str(tmp_out1)
    ], capture_output=True, text=True)
    
    with rasterio.open(tmp_out1) as src:
        result1 = src.read(1)
    water1_count = np.sum(result1 > 0)
    removed1 = np.sum(water_mask) - water1_count
    print(f"   Input: {np.sum(water_mask)} water pixels")
    print(f"   Output: {water1_count} water pixels")
    print(f"   Removed: {removed1} pixels")
    
    # TEST 2: Try with -nomask
    print("\n2️⃣ TRY: Binary mask + -nomask flag")
    tmp_water2 = tmpdir / "water_mask_2.tif"
    tmp_out2 = tmpdir / "water_out_2.tif"
    
    with rasterio.open(tmp_water2, "w", **meta) as dst:
        dst.write(water_mask.astype(np.uint8), 1)
    
    result = subprocess.run([
        "gdal_sieve.py", "-nomask", "-st", "100", "-4",
        str(tmp_water2), str(tmp_out2)
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        with rasterio.open(tmp_out2) as src:
            result2 = src.read(1)
        water2_count = np.sum(result2 > 0)
        removed2 = np.sum(water_mask) - water2_count
        print(f"   Input: {np.sum(water_mask)} water pixels")
        print(f"   Output: {water2_count} water pixels")
        print(f"   Removed: {removed2} pixels")
    else:
        print(f"   ❌ Error: {result.stderr}")
    
    # TEST 3: Use original raster with all classes, keep only water
    print("\n3️⃣ TRY: Run on full landscape, then extract water/non-water")
    tmp_full = tmpdir / "full_landscape.tif"
    tmp_full_sieve = tmpdir / "full_sieved.tif"
    
    # Create raster where water=1, other=0
    mask_full = np.where(water_mask, 1, 0).astype(np.uint8)
    with rasterio.open(tmp_full, "w", **meta) as dst:
        dst.write(mask_full, 1)
    
    result = subprocess.run([
        "gdal_sieve.py", "-st", "100", "-4",
        str(tmp_full), str(tmp_full_sieve)
    ], capture_output=True, text=True)
    
    with rasterio.open(tmp_full_sieve) as src:
        result3 = src.read(1)
    water3_count = np.sum(result3 > 0)
    removed3 = np.sum(mask_full) - water3_count
    print(f"   Input: {np.sum(mask_full)} water pixels")
    print(f"   Output: {water3_count} water pixels")
    print(f"   Removed: {removed3} pixels")
    
    # TEST 4: Use SCIPY to properly handle connected components
    print("\n4️⃣ SCIPY APPROACH: Label and remove < 100px")
    labeled, num_features = ndimage.label(water_mask)
    sizes = ndimage.sum(water_mask, labeled, range(num_features + 1))
    small_mask = sizes < MMU_ISLAND
    small_component_mask = small_mask[labeled]
    
    water4_removed = np.sum(small_component_mask)
    water4_kept = np.sum(water_mask) - water4_removed
    print(f"   Input: {np.sum(water_mask)} water pixels")
    print(f"   Output: ~{water4_kept} water pixels (components >= {MMU_ISLAND}px removed)")
    print(f"   Removed: {water4_removed} pixels (exact)")
    print(f"   Components removed: {np.sum(small_mask) - 1}")  # -1 för background

print("\n" + "=" * 60)
print("🔍 SUMMARY:")
print("   Approach 1 (gdal_sieve binary): ", f"removed {removed1}" if 'removed1' in locals() else "ERROR")
print("   Approach 2 (gdal_sieve +nomask):", f"removed {removed2}" if 'removed2' in locals() else "Not tested")
print("   Approach 3 (gdal_sieve full): ", f"removed {removed3}" if 'removed3' in locals() else "ERROR")  
print("   Approach 4 (scipy correct):   ", f"removed {water4_removed} ✓")
