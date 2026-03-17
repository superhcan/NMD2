"""
steg_1_split_tiles.py — Steg 1: Tileluppdelning + klassomklassificering.

Delar original-raster (NMD2023bas_v2_0.tif) i 1024×1024 px tiles och
applicerar CLASS_REMAP för omklassificering från NMD-koder till slutklasser.

Sparar två versioner per tile:
  - NMD2023bas_tile_r{rad:03d}_c{kol:03d}.tif (omklassificerad)
  - NMD2023bas_tile_r{rad:03d}_c{kol:03d}_original_class.tif (original NMD-koder)

Namnkonvention: NMD2023bas_tile_r{rad:03d}_c{kol:03d}.tif
Varje tile får en kopia av .qml-filen så att QGIS läser in paletten automatiskt.

Kör: python3 steg_1_split_tiles.py
"""

import logging
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from config import SRC, QML_SRC, OUT_BASE, COMPRESS, CLASS_REMAP

log = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")

# ──────────────────────────────────────────────────────────────────────────────

TILE_SIZE = 1024  # pixlar per sida

# ──────────────────────────────────────────────────────────────────────────────

def remap_classes(tile_data, class_remap):
    """
    Applicerar CLASS_REMAP på en tile.
    
    Args:
        tile_data: np.ndarray med pixelvärden
        class_remap: dict {old_code: new_code}
    
    Returns:
        Omklassificerad tile
    """
    remapped = tile_data.copy()
    for old_code, new_code in class_remap.items():
        if new_code is not None:  # None betyder kod elimineras (sätts till 0)
            remapped[tile_data == old_code] = new_code
        else:
            remapped[tile_data == old_code] = 0
    return remapped

# ──────────────────────────────────────────────────────────────────────────────

OUT_DIR = OUT_BASE / "steg1_tiles"  # Output-mapp för steg 1 tiles

OUT_DIR.mkdir(parents=True, exist_ok=True)

if not QML_SRC.exists():
    print(f"VARNING: Hittade inte {QML_SRC} – palett-filer kopieras inte.")
    copy_qml = False
else:
    copy_qml = True

t_start = time.time()

with rasterio.open(SRC) as src:
    meta = src.meta.copy()
    width = src.width
    height = src.height

    n_cols = (width  + TILE_SIZE - 1) // TILE_SIZE
    n_rows = (height + TILE_SIZE - 1) // TILE_SIZE
    total  = n_rows * n_cols

    print(f"Källbild : {width} × {height} px")
    print(f"Tile-size: {TILE_SIZE} × {TILE_SIZE} px")
    print(f"Tiles    : {n_cols} kolumner × {n_rows} rader = {total} st")
    print(f"Utmapp   : {OUT_DIR}")
    print(f"Klassom- : {len(CLASS_REMAP)} omklassificeringar\n")

    count = 0
    for row in range(n_rows):
        for col in range(n_cols):
            x_off = col * TILE_SIZE
            y_off = row * TILE_SIZE
            w     = min(TILE_SIZE, width  - x_off)
            h     = min(TILE_SIZE, height - y_off)

            window    = Window(x_off, y_off, w, h)
            transform = src.window_transform(window)

            tile_name = f"NMD2023bas_tile_r{row:03d}_c{col:03d}.tif"
            tile_path = OUT_DIR / tile_name

            # Läs original data
            tile_original = src.read(1, window=window)  # uint8 från källan
            
            # Spara en kopia av original-klasserna för referens
            original_class_path = tile_path.with_stem(tile_path.stem + "_original_class")
            
            tile_meta = meta.copy()
            tile_meta.update(width=w, height=h, transform=transform,
                             compress=COMPRESS)

            # Skriv originalklasser
            with rasterio.open(original_class_path, "w", **tile_meta) as dst:
                dst.write(tile_original, 1)
            
            # Applicera omklassificering
            tile_remapped = remap_classes(tile_original, CLASS_REMAP)
            
            # Skriv omklassificerad tile
            with rasterio.open(tile_path, "w", **tile_meta) as dst:
                dst.write(tile_remapped.astype(src.dtypes[0]), 1)

            # Kopiera QML så QGIS hittar paletten automatiskt
            if copy_qml:
                shutil.copy2(QML_SRC, tile_path.with_suffix(".qml"))

            count += 1
            if count % 50 == 0 or count == total:
                pct = count / total * 100
                print(f"  {count}/{total} ({pct:.0f}%)", flush=True)

elapsed = time.time() - t_start
print(f"\nKlart! ({elapsed:.1f}s)")
print(f"Tiles sparade i: {OUT_DIR}")


if __name__ == "__main__":
    import os
    from logging_setup import setup_logging, log_step_header
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    log_step_header(info, 1, "Tileluppdelning",
                    str(SRC),
                    str(OUT_DIR))
    
    info.info("Steg 1 klar: %d tiles skapade (%.1fs)", len(list(OUT_DIR.glob("*.tif"))), elapsed)
