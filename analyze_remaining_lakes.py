#!/usr/bin/env python3
"""Vad är de återstående sjöarna?"""
import numpy as np
import rasterio
from pathlib import Path
from scipy import ndimage

OUT_BASE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles_v8")
WATER_CLASSES = {61, 62}

tile_name = "NMD2023bas_tile_r000_c019.tif"
steg4_path = OUT_BASE / "steg4_filled" / tile_name

with rasterio.open(steg4_path) as src:
    data4 = src.read(1)

water4 = np.isin(data4, list(WATER_CLASSES))
structure = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)
labeled4, num_lakes4 = ndimage.label(water4, structure=structure)
lake_sizes4 = ndimage.sum(water4, labeled4, range(num_lakes4 + 1))

print(f"Återstående sjöar efter steg 4 (scipy):")
print(f"Totalt: {num_lakes4} sjöar (komponenter)")
print(f"\nStorlek på alla sjöar:")

# Sortera
sizes_with_ids = [(i, s) for i, s in enumerate(lake_sizes4) if i > 0]  # Skip background
sizes_with_ids.sort(key=lambda x: x[1], reverse=True)

for lake_id, size in sizes_with_ids[:20]:
    ha = size * 100 / 10000
    status = "✓ STOR" if size >= 100 else "❌ LITEN"
    print(f"  {lake_id:3d}. {int(size):5d} px = {ha:6.2f} ha  {status}")

print(f"\n🔍 Analys:")
small_count = sum(1 for _, s in sizes_with_ids if s < 100)
large_count = sum(1 for _, s in sizes_with_ids if s >= 100)
print(f"  Små sjöar (< 100px): {small_count}")
print(f"  Stora sjöar (>= 100px): {large_count}")

if small_count > 0:
    print(f"\n❌ AH! Det är fortfarande {small_count} små sjöar kvar!")
    print("Möjliga orsaker:")
    print("  1. scipy-komponenter räknas inte rätt?")
    print("  2. Algoritmen fylls inte små sjöar helt?")
    print("  3. Konfiguration MMU_ISLAND feltolkad?")
