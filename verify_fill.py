#!/usr/bin/env python3
"""Verifiera att tomrummen är fyllda"""
import numpy as np
import rasterio
from pathlib import Path

OUT_BASE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles_v8")
WATER_CLASSES = {61, 62}

tile_name = "NMD2023bas_tile_r000_c019.tif"
steg4_path = OUT_BASE / "steg4_filled" / tile_name

with rasterio.open(steg4_path) as src:
    data4 = src.read(1)

# Kolla på värdefördelning
print(f"🔍 Verifierar att tomrummen är fyllda:\n")
print(f"Unika värden i steg 4 output (sorterat):")
unique_vals = np.unique(data4)
print(f"  {sorted(unique_vals)[:20]}")

zero_count = np.sum(data4 == 0)
print(f"\nPixlar med värde 0: {zero_count:,}")

if zero_count > 0:
    print(f"❌ PROBLEM: Fortfarande {zero_count} tomma pixlar (värde 0)!")
else:
    print(f"✅ SUP! Alla tomrummen är nu fyllda - ingen 0:or!")

# Kolla på vattenpixlar  
water_mask = np.isin(data4, list(WATER_CLASSES))
water_count = np.sum(water_mask)
print(f"\nVattenpixlar (61, 62): {water_count:,}")

# Nya värden som inte är vatten
non_water_mask = ~water_mask
non_water_unique = np.unique(data4[non_water_mask])
print(f"Landskapsvärden (fyllning): {sorted(non_water_unique)}")
