#!/usr/bin/env python3
"""Debug steg 4: Jämför sjöar före/efter"""
import numpy as np
import rasterio
from pathlib import Path

OUT_BASE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles_v8")
WATER_CLASSES = {61, 62}

tile_name = "NMD2023bas_tile_r000_c019.tif"
steg3_path = OUT_BASE / "steg3_landscape" / tile_name
steg4_path = OUT_BASE / "steg4_filled" / tile_name

print(f"\n📊 Jämför {tile_name}")
print("=" * 60)

with rasterio.open(steg3_path) as src:
    data3 = src.read(1)
    
water3 = np.isin(data3, list(WATER_CLASSES))
water3_count = np.sum(water3)
water3_lakes = len(data3[water3])

print(f"\nSteg 3 (original landscape):")
print(f"  Vattenpixlar totalt: {water3_count:,}")
print(f"  Unika vattenklasser: {sorted(set(data3[water3]))}")
print(f"  Största sjö: {water3.shape} raster")

# Hitta sammanhängande sjökomponenter
from scipy import ndimage
labeled, num_lakes = ndimage.label(water3)
lake_sizes = np.bincount(labeled[water3])  # Storlek på varje sjö

print(f"  Antal sjöar (sammanhängande komponenter): {num_lakes}")
print(f"  Sjöstorlekar (pixlar):")
sizes = sorted([s for s in lake_sizes if s > 0], reverse=True)[:10]
for i, size in enumerate(sizes[:5], 1):
    ha = size * 100 / 10000
    print(f"    {i}. {size:5d} px = {ha:.2f} ha")

print("\n" + "-" * 60)

with rasterio.open(steg4_path) as src:
    data4 = src.read(1)
    
water4 = np.isin(data4, list(WATER_CLASSES))    
water4_count = np.sum(water4)

print(f"\nSteg 4 (filled):")
print(f"  Vattenpixlar totalt: {water4_count:,}")
print(f"  Unika vattenklasser: {sorted(set(data4[water4]))}")

# Hitta sjöar efter
labeled4, num_lakes4 = ndimage.label(water4)
lake_sizes4 = np.bincount(labeled4[water4]) if np.any(water4) else np.array([])

print(f"  Antal sjöar (sammanhängande): {num_lakes4}")
if len(lake_sizes4) > 1:
    sizes4 = sorted([s for s in lake_sizes4 if s > 0], reverse=True)[:5]
    print(f"  Sjöstorlekar (pixlar):")
    for i, size in enumerate(sizes4, 1):
        ha = size * 100 / 10000
        print(f"    {i}. {size:5d} px = {ha:.2f} ha")

print("\n" + "=" * 60)
print(f"Differens:")
print(f"  Vattenpixlar borttagna: {water3_count - water4_count:,} px")
print(f"  Reduktion: {(1 - water4_count/water3_count)*100:.1f}%")
print(f"  Sjöar borttagna: {num_lakes - num_lakes4}")

# Visa vilka sjöar som står kvar
if num_lakes4 > 0:
    print(f"\n❌ PROBLEM: {num_lakes4} sjöar kvar! (Borde vara 0)")
    print(f"  MMU_ISLAND = 100 px = 1.0 ha")
    print(f"  Återstående sjöstorlekar: {sorted([s for s in lake_sizes4 if s > 0], reverse=True)[:5]}")
