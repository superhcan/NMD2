#!/usr/bin/env python3
"""
steg_3_dissolve.py — Steg 3: Lös upp utvalda klasser i omgivande mark.

Läser från tiles/ (Steg 1), skriver steg3_dissolved/ där DISSOLVE_CLASSES (51, 53)
ersätts med omkringliggande värden genom morphological dilation för att kunna
generaliseras tillsammans med övrig mark.

Kör: python3 src/steg_3_dissolve.py
"""

import logging
import os
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

from config import QML_SRC, OUT_BASE, DISSOLVE_CLASSES, STRUCT_4, COMPRESS

N_WORKERS = max(1, (os.cpu_count() or 1) - 2)

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")


def copy_qml(tif_path: Path):
    """Kopiera referens-QML-fil till TIF-filen."""
    if QML_SRC.exists():
        shutil.copy2(QML_SRC, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def _dissolve_tile_worker(args):
    """Top-level worker för ProcessPoolExecutor (måste vara picklingbar)."""
    tile_str, out_path_str, dissolve_classes_frozen = args
    tile = Path(tile_str)
    out_path = Path(out_path_str)

    if out_path.exists():
        return out_path_str, 0, 0.0

    t0 = time.time()
    dissolve_set = np.array(list(dissolve_classes_frozen), dtype=np.uint16)

    with rasterio.open(tile) as src:
        meta = src.meta.copy()
        data = src.read(1)
    meta.update(compress=COMPRESS)

    roads_mask = np.isin(data, dissolve_set)
    px_replaced = int(roads_mask.sum())

    if px_replaced > 0:
        # Vektoriserad nearest-neighbour fill:
        # distance_transform_edt med return_indices ger för varje pixel
        # koordinaterna till närmaste icke-väg/byggnad-pixel. O(N) istället
        # för O(N²) pixel-för-pixel-loopen.
        _, indices = ndimage.distance_transform_edt(roads_mask, return_indices=True)
        landscape_data = data.copy()
        landscape_data[roads_mask] = data[indices[0][roads_mask], indices[1][roads_mask]]
    else:
        landscape_data = data

    with rasterio.open(out_path, "w", **meta) as dst:
        dst.write(landscape_data, 1)

    if QML_SRC.exists():
        shutil.copy2(QML_SRC, out_path.with_suffix(".qml"))

    elapsed = time.time() - t0
    return out_path_str, px_replaced, elapsed


def extract_landscape(tile_paths: list[Path]) -> list[Path]:
    """Lös upp DISSOLVE_CLASSES i omgivande mark och skriv till steg3_dissolved/."""
    t0_step = time.time()
    out_dir = OUT_BASE / "steg_3_dissolve"
    out_dir.mkdir(parents=True, exist_ok=True)

    info.info("Steg 3: Löser upp klasser %s i omgivande mark (%d workers) ...",
              DISSOLVE_CLASSES, N_WORKERS)

    dissolve_frozen = tuple(sorted(DISSOLVE_CLASSES))
    task_args = [
        (str(tile), str(out_dir / tile.name), dissolve_frozen)
        for tile in tile_paths
    ]

    total_px_replaced = 0
    result_paths = []

    with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
        for out_path_str, px_replaced, elapsed in executor.map(_dissolve_tile_worker, task_args):
            result_paths.append(Path(out_path_str))
            total_px_replaced += px_replaced
            if elapsed > 0:
                log.debug("dissolve: %s → %d px ersatta  %.1fs",
                          Path(out_path_str).name, px_replaced, elapsed)

    _elapsed = time.time() - t0_step
    info.info("Steg 3 klar: totalt %d px vägar/byggnader ersätta  %.1f min (%.0fs)",
              total_px_replaced, _elapsed / 60, _elapsed)

    return result_paths


if __name__ == "__main__":
    import os
    from logging_setup import setup_logging, log_step_header
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)
    
    log_step_header(info, 3, "Lös upp klasser i omgivande mark",
                    str(OUT_BASE / "steg_1_reclassify"),
                    str(OUT_BASE / "steg_3_dissolve"))
    
    # Läs tiles från Steg 1
    tiles_dir = OUT_BASE / "steg_1_reclassify"
    if not tiles_dir.exists():
        info.error(f"Fel: {tiles_dir} finns ej. Kör Steg 1 först (split_tiles.py)")
        exit(1)
    
    tile_paths = sorted(tiles_dir.glob("*.tif"))
    info.info(f"Hittade {len(tile_paths)} tiles från Steg 1")
    
    landscape = extract_landscape(tile_paths)
    info.info(f"Steg 3 klar: {len(landscape)} tiles skapade")
