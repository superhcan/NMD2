"""
steg_0_verify_tiles.py — Steg 0: Verifikation - Tileluppdelning utan omklassificering.

Delar original-raster (NMD2023bas_v2_0.tif) i 1024×1024 px tiles
UTAN att applicera någon omklassificering. Används för verifikation
av originaldata innan produktions-omklassificering i steg 1.

Output:
  - NMD2023bas_tile_r{rad:03d}_c{kol:03d}.tif (original NMD-koder, ingen ändring)

Namnkonvention: NMD2023bas_tile_r{rad:03d}_c{kol:03d}.tif
Varje tile får en kopia av .qml-filen så att QGIS läser in paletten automatiskt.

Kör: python3 steg_0_verify_tiles.py
"""

import logging
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import rasterio

from config import SRC, QML_SRC, OUT_BASE, COMPRESS, TILE_SIZE, get_active_tiles

log = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")

# ──────────────────────────────────────────────────────────────────────────────

OUT_DIR = OUT_BASE / "steg0_verify_tiles"  # Output-mapp för steg 0 tiles

OUT_DIR.mkdir(parents=True, exist_ok=True)

if not QML_SRC.exists():
    print(f"VARNING: Hittade inte {QML_SRC} – palett-filer kopieras inte.")
    copy_qml = False
else:
    copy_qml = True

t_start = time.time()

active_tiles = get_active_tiles()
total = len(active_tiles)
print(f"Källbild : {SRC.name}")
print(f"Tile-size: {TILE_SIZE} × {TILE_SIZE} px")
print(f"Tiles    : {total} st")
print(f"Utmapp   : {OUT_DIR}")
print(f"Klassif. : INGEN omklassificering (verifikation av original)\n")

with rasterio.open(SRC) as src:
    meta = src.meta.copy()

    for count, (row, col) in enumerate(active_tiles, 1):
        x_off = col * TILE_SIZE
        y_off = row * TILE_SIZE
        w     = min(TILE_SIZE, src.width  - x_off)
        h     = min(TILE_SIZE, src.height - y_off)

        window    = rasterio.windows.Window(x_off, y_off, w, h)
        transform = src.window_transform(window)

        tile_name = f"NMD2023bas_tile_r{row:03d}_c{col:03d}.tif"
        tile_path = OUT_DIR / tile_name

        # Läs original data
        tile_data = src.read(1, window=window)  # uint8 från källan

        tile_meta = meta.copy()
        tile_meta.update(width=w, height=h, transform=transform,
                         compress=COMPRESS)

        # Skriv original data UTAN någon omklassificering
        with rasterio.open(tile_path, "w", **tile_meta) as dst:
            dst.write(tile_data.astype(src.dtypes[0]), 1)

        # Kopiera QML så QGIS hittar paletten automatiskt
        if copy_qml:
            shutil.copy2(QML_SRC, tile_path.with_suffix(".qml"))

        print(f"  {count}/{total} ({count/total*100:.0f}%)", flush=True)

elapsed = time.time() - t_start
print(f"\nKlart! ({elapsed:.1f}s)")
print(f"Tiles sparade i: {OUT_DIR}")
print(f"Dessa tiles innehåller ORIGINAL NMD-koder (ingen omklassificering)")


if __name__ == "__main__":
    import os
    from logging_setup import setup_logging, log_step_header
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    log_step_header(info, 0, "Verifikation - Tileluppdelning (original)",
                    str(SRC),
                    str(OUT_DIR))
    
    info.info("Steg 0 klar: %d tiles skapade (%.1fs)", len(list(OUT_DIR.glob("*.tif"))), elapsed)
