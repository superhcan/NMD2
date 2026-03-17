"""
steg_1_split_tiles.py — Steg 1: Klassomklassificering från steg 0 tiles.

Läser redan uppdelade tiles från steg0_verify_tiles/ och applicerar
CLASS_REMAP för omklassificering från NMD-koder till slutklasser.

Input:  steg0_verify_tiles/*.tif (original NMD-koder, uppdelade av steg 0)
Output: steg1_tiles/*.tif (omklassificerade tiles)

Namnkonvention: NMD2023bas_tile_r{rad:03d}_c{kol:03d}.tif
Varje tile får en kopia av .qml-filen så att QGIS hittar paletten automatiskt.

Kör: python3 steg_1_split_tiles.py
"""

import logging
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import rasterio

from config import QML_SRC, OUT_BASE, COMPRESS, CLASS_REMAP

log = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")

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

STEG0_DIR = OUT_BASE / "steg0_verify_tiles"  # Indata: original tiles från steg 0
OUT_DIR   = OUT_BASE / "steg1_tiles"           # Output-mapp för steg 1 tiles

OUT_DIR.mkdir(parents=True, exist_ok=True)

if not STEG0_DIR.exists():
    print(f"FEL: {STEG0_DIR} saknas — kör steg 0 först.")
    sys.exit(1)

if not QML_SRC.exists():
    print(f"VARNING: Hittade inte {QML_SRC} – palett-filer kopieras inte.")
    copy_qml = False
else:
    copy_qml = True

t_start = time.time()

# Hämta alla source-tiles (exkludera _original_class om sådana finns)
src_tiles = sorted(
    p for p in STEG0_DIR.glob("*.tif")
    if "_original_class" not in p.name
)
total = len(src_tiles)

if total == 0:
    print(f"FEL: Inga tiles hittades i {STEG0_DIR} — kör steg 0 först.")
    sys.exit(1)

print(f"Källmapp : {STEG0_DIR}")
print(f"Tiles    : {total} st")
print(f"Utmapp   : {OUT_DIR}")
print(f"Klassom- : {len(CLASS_REMAP)} omklassificeringar\n")

for count, src_tile_path in enumerate(src_tiles, 1):
    tile_name = src_tile_path.name
    tile_path = OUT_DIR / tile_name

    with rasterio.open(src_tile_path) as src:
        tile_data = src.read(1)
        tile_meta = src.meta.copy()
        tile_meta.update(compress=COMPRESS)

    # Applicera omklassificering
    tile_remapped = remap_classes(tile_data, CLASS_REMAP)

    # Skriv omklassificerad tile
    with rasterio.open(tile_path, "w", **tile_meta) as dst:
        dst.write(tile_remapped.astype(tile_data.dtype), 1)

    # Kopiera QML så QGIS hittar paletten automatiskt
    if copy_qml:
        shutil.copy2(QML_SRC, tile_path.with_suffix(".qml"))

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
                    str(STEG0_DIR),
                    str(OUT_DIR))
    
    info.info("Steg 1 klar: %d tiles skapade (%.1fs)", len(list(OUT_DIR.glob("*.tif"))), elapsed)
