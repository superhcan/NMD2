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
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import rasterio

from config import SRC, QML_SRC, OUT_BASE, COMPRESS, TILE_SIZE, PARENT_TILES

log = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")

N_WORKERS = max(1, (os.cpu_count() or 1) - 2)

# ──────────────────────────────────────────────────────────────────────────────

OUT_DIR = OUT_BASE / "steg_0_verify_tiles"


def _tile_worker(args):
    """Top-level worker för ProcessPoolExecutor."""
    src_str, out_str, row, col, tile_size, src_width, src_height, meta_dict, compress, qml_str = args
    out = Path(out_str)

    if out.exists():
        return out_str, 0.0

    t0 = time.time()
    x_off = col * tile_size
    y_off = row * tile_size
    w = min(tile_size, src_width  - x_off)
    h = min(tile_size, src_height - y_off)

    window = rasterio.windows.Window(x_off, y_off, w, h)

    with rasterio.open(src_str) as src:
        transform = src.window_transform(window)
        tile_data = src.read(1, window=window)
        dtype = src.dtypes[0]

    tile_meta = dict(meta_dict)
    tile_meta.update(width=w, height=h, transform=transform, compress=compress)

    with rasterio.open(out, "w", **tile_meta) as dst:
        dst.write(tile_data.astype(dtype), 1)

    qml = Path(qml_str)
    if qml.exists():
        shutil.copy2(qml, out.with_suffix(".qml"))

    return out_str, time.time() - t0


def process_tiles():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    total = len(PARENT_TILES)
    print(f"Källbild : {SRC.name}")
    print(f"Tile-size: {TILE_SIZE} × {TILE_SIZE} px")
    print(f"Tiles    : {total} st (PARENT_TILES)")
    print(f"Utmapp   : {OUT_DIR}")
    print(f"Workers  : {N_WORKERS}")
    print(f"Klassif. : INGEN omklassificering (verifikation av original)\n")

    # Läs metadata en gång i main thread
    with rasterio.open(SRC) as src:
        meta = dict(src.meta)
        src_width  = src.width
        src_height = src.height

    task_args = [
        (
            str(SRC),
            str(OUT_DIR / f"NMD2023bas_tile_r{row:03d}_c{col:03d}.tif"),
            row, col, TILE_SIZE, src_width, src_height,
            meta, COMPRESS, str(QML_SRC)
        )
        for row, col in PARENT_TILES
    ]

    t_start = time.time()
    done = 0
    with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
        for _out_str, elapsed in executor.map(_tile_worker, task_args):
            done += 1
            if done % 50 == 0 or done == total:
                pct = done / total * 100
                print(f"  {done}/{total} ({pct:.0f}%)", flush=True)

    total_elapsed = time.time() - t_start
    print(f"\nKlart! ({total_elapsed:.1f}s)")
    print(f"Tiles sparade i: {OUT_DIR}")
    print(f"Dessa tiles innehåller ORIGINAL NMD-koder (ingen omklassificering)")
    return total_elapsed


elapsed = process_tiles()


if __name__ == "__main__":
    from logging_setup import setup_logging, log_step_header
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")

    log_step_header(info, 0, "Verifikation - Tileluppdelning (original)",
                    str(SRC),
                    str(OUT_DIR))

    info.info("Steg 0 klart: %d tiles skapade  %.1f min (%.0fs)",
              len(list(OUT_DIR.glob("*.tif"))), elapsed / 60, elapsed)
