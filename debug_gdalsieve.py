#!/usr/bin/env python3
"""Debug: Vad returnerar gdal_sieve egentligen?"""
import numpy as np
import rasterio
import subprocess
import tempfile
from pathlib import Path

OUT_BASE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles_v8")
WATER_CLASSES = {61, 62}
MMU_ISLAND = 100

tile_name = "NMD2023bas_tile_r000_c019.tif"
steg3_path = OUT_BASE / "steg3_landscape" / tile_name

print("🔍 Testa gdal_sieve output format\n")

with rasterio.open(steg3_path) as src:
    meta = src.meta.copy()
    data = src.read(1)
    
water_mask = np.isin(data, list(WATER_CLASSES))
print(f"Vattenmask info:")
print(f"  dtype: {water_mask.dtype}")
print(f"  unika värden: {np.unique(water_mask)}")
print(f"  True pixels: {np.sum(water_mask)}")

with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)
    tmp_water = tmpdir / "water_mask.tif"
    tmp_filled = tmpdir / "water_filled.tif"
    
    # Spara vattenmask som uint8 (0=icke vatten, 255=vatten)
    with rasterio.open(tmp_water, "w", **meta) as dst:
        dst.write(water_mask.astype(np.uint8), 1)
    
    print(f"\nVattenmask sparad till {tmp_water.name}")
    
    # Kör gdal_sieve
    cmd = [
        "gdal_sieve.py",
        "-st", str(MMU_ISLAND),
        "-4",
        str(tmp_water),
        str(tmp_filled)
    ]
    
    print(f"\nKör: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    print(result.stdout)
    
    # Läs resultat
    with rasterio.open(tmp_filled) as src_filled:
        filled_water = src_filled.read(1)
    
    print(f"\nFiltered water result info:")
    print(f"  dtype: {filled_water.dtype}")
    print(f"  unika värden: {np.unique(filled_water)}")
    print(f"  shape: {filled_water.shape}")
    
    # Undersök värdena
    print(f"\nValue-fördelning:")
    for val in np.unique(filled_water):
        count = np.sum(filled_water == val)
        print(f"  Värde {val}: {count:,} pixels")
    
    # VIKTIGT: Kontrollera vad som är borttaget
    filtered_binary = filled_water.astype(bool)
    print(f"\nOm vi cast till bool (filled_water.astype(bool)):")
    print(f"  True pixels: {np.sum(filtered_binary)}")
    print(f"  False pixels: {np.sum(~filtered_binary)}")
    
    # Jämför med original
    removed = water_mask & ~filtered_binary
    print(f"\nRemoved mask (original & ~filtered):")
    print(f"  Removed pixels: {np.sum(removed)}")
    
    # ÅH NEJ! Problemet kan vara att gdal_sieve fyller sjöarna med ett annat värde, inte 0!
    # Kolla om värdet 0 betyder "bort" eller något annat
    print(f"\n🔴 PROBLEM: gdal_sieve returnerar värde {0}" if 0 in np.unique(filled_water) else "\n✓ Värde 0 finns i resultat")
