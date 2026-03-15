#!/usr/bin/env python3
"""
extract_test_4tiles.py — Extrahera 4 tiles (2×2) från originalbilden för testning
"""

import sys
from pathlib import Path
import rasterio
from rasterio.windows import Window

# Originalbilden
SRC = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/NMD2023bas_v2_0.tif")
QML_SRC = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/NMD2023bas_v2_0.qml")

# Test-outputmapp
OUT_DIR = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles_v8/steg1_tiles")
OUT_DIR.mkdir(parents=True, exist_ok=True)

TILE_SIZE = 1024

# 4 tiles med riklig landmassa i södra Sverige (matchar PARENT_TILES i config.py)
TILE_COORDS = [
    (0, 19),  # Rad 0, Col 19
    (0, 20),  # Rad 0, Col 20
    (1, 19),  # Rad 1, Col 19
    (1, 20),  # Rad 1, Col 20
]

print("="*70)
print("🧪 EXTRAHERAR 4 TEST-TILES (2×2)")
print("="*70)

with rasterio.open(SRC) as src:
    meta = src.meta.copy()
    
    for row, col in TILE_COORDS:
        # Beräkna pixel-offset
        x_off = col * TILE_SIZE
        y_off = row * TILE_SIZE
        
        # Läs window
        window = Window(x_off, y_off, TILE_SIZE, TILE_SIZE)
        data = src.read(1, window=window)
        
        # Namn på output-tile
        tile_name = f"NMD2023bas_tile_r{row:03d}_c{col:03d}.tif"
        out_path = OUT_DIR / tile_name
        
        # Uppdatera meta för denna tile
        tile_meta = meta.copy()
        tile_meta.update(
            width=TILE_SIZE,
            height=TILE_SIZE,
            transform=rasterio.windows.transform(window, src.transform)
        )
        
        # Skriv tile
        with rasterio.open(out_path, 'w', **tile_meta) as dst:
            dst.write(data, 1)
        
        # Kopiera QML
        if QML_SRC.exists():
            import shutil
            shutil.copy2(QML_SRC, out_path.with_suffix(".qml"))
        
        print(f"  ✓ {tile_name} extraherad")

print(f"\n✅ 4 test-tiles sparade i: {OUT_DIR}")
print(f"\nKör pipelinen med:")
print(f"  export OUT_BASE=/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles_v8")
print(f"  python3 run_test_4tiles_v8.py")
