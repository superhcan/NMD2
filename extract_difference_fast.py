#!/usr/bin/env python3
"""
Extract pixels from 2018 raster that don't exist in 2023 raster.
FAST version: reads corresponding blocks from both rasters simultaneously.
"""

import rasterio
import numpy as np
from pathlib import Path
from rasterio.windows import Window

# Paths
raster_2018 = "/home/hcn/NMD_workspace/NMD2018_basskikt_ogeneraliserad_Sverige_v1_1/nmd2018bas_ogeneraliserad_v1_1.tif"
raster_2023 = "/home/hcn/NMD_workspace/NMD2023_basskikt_v2_1/NMD2023bas_v2_1.tif"
output_path = "/home/hcn/NMD_workspace/difference_2018_not_in_2023_fast.tif"

print(f"2018 raster: {raster_2018}")
print(f"2023 raster: {raster_2023}")
print(f"Output: {output_path}")

BLOCK_SIZE = 1024  # Process 1024x1024 blocks

with rasterio.open(raster_2018) as src_2018, rasterio.open(raster_2023) as src_2023:
    h_2018, w_2018 = src_2018.shape
    h_2023, w_2023 = src_2023.shape
    
    print(f"\n2018: {h_2018} x {w_2018}")
    print(f"2023: {h_2023} x {w_2023}")
    
    # Calculate offset between the two rasters
    gt_2018 = src_2018.transform
    gt_2023 = src_2023.transform
    
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
                
                # Define corresponding window in 2023
                col_2023 = col + offset_x
                row_2023 = row + offset_y
                
                # Only read from 2023 if the window overlaps
                if col_2023 >= 0 and row_2023 >= 0 and col_2023 < w_2023 and row_2023 < h_2023:
                    # Calculate overlapping region
                    col_start = max(0, col_2023)
                    row_start = max(0, row_2023)
                    col_end = min(w_2023, col_2023 + w_width)
                    row_end = min(h_2023, row_2023 + w_height)
                    
                    if col_end > col_start and row_end > row_start:
                        # Calculate offsets within blocks
                        offset_start_col = col_start - col_2023
                        offset_start_row = row_start - row_2023
                        offset_end_col = offset_start_col + (col_end - col_start)
                        offset_end_row = offset_start_row + (row_end - row_start)
                        
                        # Read corresponding block from 2023
                        read_width = col_end - col_start
                        read_height = row_end - row_start
                        window_2023 = Window(col_start, row_start, read_width, read_height)
                        block_2023 = src_2023.read(1, window=window_2023)
                        
                        # Compare: include pixels in 2018 that are NOT in 2023
                        output_region = output_block[offset_start_row:offset_end_row, 
                                                    offset_start_col:offset_end_col]
                        input_region = block_2018[offset_start_row:offset_end_row, 
                                                 offset_start_col:offset_end_col]
                        
                        # Include pixels where 2018 has data but 2023 doesn't
                        mask = (input_region != 0) & (block_2023 == 0)
                        output_region[mask] = input_region[mask]
                else:
                    # Entire block is outside 2023 - include all valid pixels from 2018
                    output_block[block_2018 != 0] = block_2018[block_2018 != 0]
                
                # Write block to output
                dst.write(output_block, 1, window=window_2018)
                
                if block_count % 10 == 0:
                    print(f"Processed block {block_count}/{total_blocks}")
        
        print(f"\nDone! Output: {output_path}")
