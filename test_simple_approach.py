#!/usr/bin/env python3
"""Testa simplified fill-logic"""
import numpy as np
import rasterio
from pathlib import Path
from scipy import ndimage

OUT_BASE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles_v8")
WATER_CLASSES = {61, 62}
MMU_ISLAND = 100

tile_name = "NMD2023bas_tile_r000_c019.tif"
steg3_path = OUT_BASE / "steg3_landscape" / tile_name

with rasterio.open(steg3_path) as src:
    data = src.read(1)

water_mask = np.isin(data, list(WATER_CLASSES))

print("✓ Test enkel approach: Ta bort små sjöar helt\n")

structure = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)
labeled_water, num_components = ndimage.label(water_mask, structure=structure)
component_sizes = ndimage.sum(water_mask, labeled_water, range(num_components + 1))

# Identifiera STORA komponenter
large_components = set(np.where(component_sizes >= MMU_ISLAND)[0])
print(f"Total komponenter: {num_components}")
print(f"Stor komponenter (>={MMU_ISLAND}px): {len(large_components)}")

# APPROACH: Kopiera bara de STORA sjöarna!
output_data = np.zeros_like(data)
for i in large_components:
    if i != 0:  # Skip background
        mask = labeled_water == i
        output_data[mask] = data[mask]

water_after = np.isin(output_data, list(WATER_CLASSES))
print(f"\nResult - Apenas de mjukvarukomponenterna som är >= {MMU_ISLAND}px:")
print(f"  Vatten före: {np.sum(water_mask):,} pixlar")
print(f"  Vatten efter: {np.sum(water_after):,} pixlar")  
print(f"  Borttaget: {np.sum(water_mask) - np.sum(water_after):,} pixlar ({100*(1-np.sum(water_after)/np.sum(water_mask)):.1f}%)")

# Verifiera att bara stora sjöar kvar
labeled_after, num_after = ndimage.label(water_after, structure=structure)
sizes_after = ndimage.sum(water_after, labeled_after, range(num_after + 1))
small_after = np.sum(sizes_after < MMU_ISLAND) - 1  # -1 för background

print(f"  Sjöar efter: {num_after}")
print(f"  Små sjöar (<{MMU_ISLAND}px) kvar: {small_after}")

if small_after == 0:
    print(f"\n✅ PERFEKT! Alla små sjöar är borttagna!")
else:
    print(f"\n❌ Fortfarande {small_after} små sjöar kvar")
    # Show which
    for i in range(1, num_after + 1):
        sz = sizes_after[i]
        if sz < MMU_ISLAND:
            print(f"   - {int(sz)} px")
