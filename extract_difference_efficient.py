#!/usr/bin/env python3
"""
Extract pixels from 2018 raster that don't exist in 2023 raster.
Block-wise processing to minimize memory usage.
"""

import rasterio
import numpy as np
from pathlib import Path
from rasterio.windows import Window

# Paths
raster_2018 = "/home/hcn/NMD_workspace/NMD2018_basskikt_ogeneraliserad_Sverige_v1_1/nmd2018bas_ogeneraliserad_v1_1.tif"
raster_2023 = "/home/hcn/NMD_workspace/NMD2023_basskikt_v2_1/NMD2023bas_v2_1.tif"
output_path = "/home/hcn/NMD_workspace/difference_2018_not_in_2023.tif"

print(f"2018 raster: {raster_2018}")
print(f"2023 raster: {raster_2023}")
print(f"Output: {output_path}")

BLOCK_SIZE = 512  # Process 512x512 blocks

with rasterio.open(raster_2018) as src_2018, rasterio.open(raster_2023) as src_2023:
    h_2018, w_2018 = src_2018.shape
    h_2023, w_2023 = src_2023.shape
    
    print(f"\n2018: {h_2018} x {w_2018}")
    print(f"2023: {h_2023} x {w_2023}")
    
    # Calculate offset between the two rasters (based on geotransform)
    gt_2018 = src_2018.transform
    gt_2023 = src_2023.transform
    
    # Pixel offset
    offset_x = round((gt_2023.c - gt_2018.c) / gt_2018.a)
    offset_y = round((gt_2023.f - gt_2018.f) / gt_2018.e)
    
    print(f"Offset: x={offset_x}, y={offset_y}")
    
    # Create output raster
    profile_out = src_2018.profile.copy()
    
    with rasterio.open(output_path, 'w', **profile_out) as dst:
        block_count = 0
        total_blocks = ((h_2018 + BLOCK_SIZE - 1) // BLOCK_SIZE) * \
                      ((w_2018 + BLOCK_SIZE - 1) // BLOCK_SIZE)
        
        # Process in blocks
        for row in range(0, h_2018, BLOCK_SIZE):
            for col in range(0, w_2018, BLOCK_SIZE):
                block_count += 1
                
                # Define window in 2018
                w_height = min(BLOCK_SIZE, h_2018 - row)
                w_width = min(BLOCK_SIZE, w_2018 - col)
                window_2018 = Window(col, row, w_width, w_height)
                
                # Read block from 2018
                block_2018 = src_2018.read(1, window=window_2018)
                
                # Initialize output block
                output_block = np.zeros(block_2018.shape, dtype=block_2018.dtype)
                
                # For each pixel in 2018 block
                for dy in range(w_height):
                    for dx in range(w_width):
                        val_2018 = block_2018[dy, dx]
                        
                        if val_2018 != 0:  # Valid pixel in 2018
                            # Calculate position in 2023
                            y_2023 = row + dy + offset_y
                            x_2023 = col + dx + offset_x
                            
                            # Check if within 2023 bounds
                            if 0 <= y_2023 < h_2023 and 0 <= x_2023 < w_2023:
                                # Read single pixel from 2023
                                pixel_window = Window(x_2023, y_2023, 1, 1)
                                val_2023 = src_2023.read(1, window=pixel_window)[0, 0]
                                
                                # Include if missing in 2023
                                if val_2023 == 0:
                                    output_block[dy, dx] = val_2018
                            else:
                                # Outside 2023 bounds - include it
                                output_block[dy, dx] = val_2018
                
                # Write block to output
                dst.write(output_block, 1, window=window_2018)
                
                if block_count % 10 == 0:
                    print(f"Processed block {block_count}/{total_blocks}")
        
        print(f"\nDone! Output: {output_path}")
