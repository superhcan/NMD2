#!/usr/bin/env python3
"""
Super-simple: Read both rasters and extract 2018 pixels missing in 2023.
"""

import rasterio
import numpy as np
from pathlib import Path

# Paths
raster_2018 = "/home/hcn/NMD_workspace/NMD2018_basskikt_ogeneraliserad_Sverige_v1_1/nmd2018bas_ogeneraliserad_v1_1.tif"
raster_2023 = "/home/hcn/NMD_workspace/NMD2023_basskikt_v2_1/NMD2023bas_v2_1.tif"
output_path = "/home/hcn/NMD_workspace/difference_2018_not_in_2023.tif"

print("Reading 2018...")
with rasterio.open(raster_2018) as src_2018:
    data_2018 = src_2018.read(1)
    profile = src_2018.profile
    gt_2018 = src_2018.transform

print(f"2018 shape: {data_2018.shape}")

print("Reading 2023...")
with rasterio.open(raster_2023) as src_2023:
    data_2023 = src_2023.read(1)
    gt_2023 = src_2023.transform

print(f"2023 shape: {data_2023.shape}")

# Calculate offset
offset_x = round((gt_2023.c - gt_2018.c) / gt_2018.a)
offset_y = round((gt_2023.f - gt_2018.f) / gt_2018.e)
print(f"Offset: x={offset_x}, y={offset_y}")

# Create result with same size as 2018
result = np.zeros_like(data_2018)

print("Processing...")
h, w = data_2018.shape

for y in range(h):
    if y % 10000 == 0:
        print(f"  Row {y}/{h}")
    
    for x in range(w):
        if data_2018[y, x] != 0:  # Valid in 2018
            # Check if valid in 2023 at offset position
            y_2023 = y + offset_y
            x_2023 = x + offset_x
            
            if 0 <= y_2023 < data_2023.shape[0] and 0 <= x_2023 < data_2023.shape[1]:
                if data_2023[y_2023, x_2023] == 0:  # Missing in 2023
                    result[y, x] = data_2018[y, x]
            else:
                # Outside 2023 bounds - include it
                result[y, x] = data_2018[y, x]

print("\nWriting output...")
with rasterio.open(output_path, 'w', **profile) as dst:
    dst.write(result, 1)

print(f"Done! Output: {output_path}")
