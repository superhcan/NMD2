#!/usr/bin/env python3
"""Debug: Vad händer i scipy-algoritmen?"""
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

print("🔍 Debug scipy-algoritm\n")
print(f"Original vattendata: {np.sum(water_mask)} pixlar")

structure = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)
labeled_water, num_components = ndimage.label(water_mask, structure=structure)

print(f"Efter label: {num_components} komponenter")

# Beräkna storlek för varje komponent
component_sizes = ndimage.sum(water_mask, labeled_water, range(num_components + 1))

print(f"component_sizes shape: {component_sizes.shape}")
print(f"component_sizes dtype: {component_sizes.dtype}")
print(f"component_sizes[:10]: {component_sizes[:10]}")

# Identifiera STORA komponenter
large_components = np.where(component_sizes >= MMU_ISLAND)[0]
print(f"\nStora komponenter (>={MMU_ISLAND}px): {len(large_components)}")
print(f"Large component IDs: {sorted(large_components)[:10]}")

# Identifiera små
small_components = np.where(component_sizes < MMU_ISLAND)[0]
print(f"Små komponenter (<{MMU_ISLAND}px): {len(small_components)}")
print(f"Små component storlekar: {sorted([int(component_sizes[i]) for i in small_components if i > 0])[:15]}")

# STEP 1: Identifiera och ta bort små sjöpixlar
output_data = data.copy()
removed_count = 0
for i in range(num_components + 1):
    if i not in large_components and i != 0:  # Små komponenter (och inte background)
        small_sjoe_mask = labeled_water == i
        pixels_in_component = np.sum(small_sjoe_mask)
        output_data[small_sjoe_mask] = 0  # Markera som "ta bort"
        removed_count += pixels_in_component

print(f"\nSTEP 1 - After marking small lakes as 0:")
print(f"  Pixlar markerade för removal: {removed_count}")
print(f"  Pixlar med värde 0 i output_data: {np.sum(output_data == 0)}")

# Check: Ska vi fyllfinnit dessa?
to_fill_mask = output_data == 0
print(f"  to_fill_mask True count: {np.sum(to_fill_mask)}")

# Test filling för första pixel
print(f"\nTest filling första pixel:")
fill_coords = np.argwhere(to_fill_mask)
if len(fill_coords) > 0:
    i, j = fill_coords[0]
    print(f"  Pixel ({i}, {j})")
    
    # Sök omkringliggande
    for radius in range(1, 5):
        i_min = max(0, i - radius)
        i_max = min(data.shape[0], i + radius + 1)
        j_min = max(0, j - radius)
        j_max = min(data.shape[1], j + radius + 1)
        
        search_window = data[i_min:i_max, j_min:j_max]
        non_water_mask = ~np.isin(search_window, WATER_CLASSES)
        
        print(f"    Radius {radius}: non-water pixels = {np.sum(non_water_mask)}")
        
        if np.any(non_water_mask):
            land_values = search_window[non_water_mask]
            if len(land_values) > 0:
                fill_value = np.bincount(land_values.flat).argmax()
                print(f"      -> Fill with {fill_value}")
            break
