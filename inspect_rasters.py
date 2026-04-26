#!/usr/bin/env python3
"""
Inspektera rastren för att förstå struktur, koordinatsystem och nodata-värden
"""

import rasterio
import numpy as np
from rasterio.windows import Window

raster_2018 = "/home/hcn/NMD_workspace/NMD2018_basskikt_ogeneraliserad_Sverige_v1_1/nmd2018bas_ogeneraliserad_v1_1.tif"
raster_2023 = "/home/hcn/NMD_workspace/NMD2023_basskikt_v2_1/NMD2023bas_v2_1.tif"

print("=" * 80)
print("2018-RASTER")
print("=" * 80)
with rasterio.open(raster_2018) as src:
    print(f"Shape: {src.shape}")
    print(f"CRS: {src.crs}")
    print(f"Transform: {src.transform}")
    print(f"Dtype: {src.dtypes}")
    print(f"Nodata (profile): {src.profile.get('nodata')}")
    print(f"Nodata (property): {src.nodata}")
    print(f"Count (bands): {src.count}")
    print(f"Colormap: {src.colormap(1) is not None}")
    
    # Läs ett litet window för att se värdena
    window = Window(0, 0, 10, 10)
    data_sample = src.read(1, window=window)
    print(f"\nSampel data (första 10x10 pixlar):")
    print(data_sample)
    print(f"Unika värden i sampel: {np.unique(data_sample)}")
    
    # Läs ett större område från mitten av raster
    row_mid = src.shape[0] // 2
    col_mid = src.shape[1] // 2
    window2 = Window(col_mid, row_mid, 20, 20)
    data_mid = src.read(1, window=window2)
    print(f"\nSampel från mitten:")
    print(f"Unika värden: {np.unique(data_mid)}")

print("\n" + "=" * 80)
print("2023-RASTER")
print("=" * 80)
with rasterio.open(raster_2023) as src:
    print(f"Shape: {src.shape}")
    print(f"CRS: {src.crs}")
    print(f"Transform: {src.transform}")
    print(f"Dtype: {src.dtypes}")
    print(f"Nodata (profile): {src.profile.get('nodata')}")
    print(f"Nodata (property): {src.nodata}")
    print(f"Count (bands): {src.count}")
    print(f"Colormap: {src.colormap(1) is not None}")
    
    # Läs ett litet window
    window = Window(0, 0, 10, 10)
    data_sample = src.read(1, window=window)
    print(f"\nSampel data (första 10x10 pixlar):")
    print(data_sample)
    print(f"Unika värden i sampel: {np.unique(data_sample)}")
    
    # Läs ett större område från mitten
    row_mid = src.shape[0] // 2
    col_mid = src.shape[1] // 2
    window2 = Window(col_mid, row_mid, 20, 20)
    data_mid = src.read(1, window=window2)
    print(f"\nSampel från mitten:")
    print(f"Unika värden: {np.unique(data_mid)}")

print("\n" + "=" * 80)
print("JÄMFÖRELSE")
print("=" * 80)
with rasterio.open(raster_2018) as src1, rasterio.open(raster_2023) as src2:
    bbox1 = src1.bounds
    bbox2 = src2.bounds
    print(f"2018 bbox: {bbox1}")
    print(f"2023 bbox: {bbox2}")
    print(f"Samma CRS: {src1.crs == src2.crs}")
    print(f"Samma transform: {src1.transform == src2.transform}")
