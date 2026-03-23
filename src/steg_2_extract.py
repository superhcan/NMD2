#!/usr/bin/env python3
"""
steg_2_extract.py — Steg 2: Extract classes to separate layer.

Läser från tiles/ (output från Steg 1), skriver steg2_extracted/ där bara
EXTRACT_CLASSES är kvar. Dessa klasser generaliseras ej och vektoriseras
separat i ett senare steg.

Kör: python3 src/steg_2_extract.py
"""

import logging
import os
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import rasterio

from config import QML_SRC, OUT_BASE, EXTRACT_CLASSES, COMPRESS

N_WORKERS = max(1, (os.cpu_count() or 1) - 2)

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")


def copy_qml(tif_path: Path):
    """Kopiera referens-QML-fil till TIF-filen."""
    if QML_SRC.exists():
        shutil.copy2(QML_SRC, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def _extract_tile_worker(args):
    """Top-level worker för ProcessPoolExecutor (måste vara picklingbar)."""
    tile_str, out_path_str, extract_classes_frozen = args
    tile = Path(tile_str)
    out_path = Path(out_path_str)

    if out_path.exists():
        return out_path_str, 0, 0.0

    t0 = time.time()
    extract_set = np.array(list(extract_classes_frozen), dtype=np.uint16)

    with rasterio.open(tile) as src:
        meta = src.meta.copy()
        data = src.read(1)
    meta.update(compress=COMPRESS)

    mask = np.isin(data, extract_set)
    protected_data = np.where(mask, data, np.uint16(0)).astype(data.dtype)
    n_px = int(np.count_nonzero(protected_data))

    with rasterio.open(out_path, "w", **meta) as dst:
        dst.write(protected_data, 1)

    if QML_SRC.exists():
        shutil.copy2(QML_SRC, out_path.with_suffix(".qml"))

    elapsed = time.time() - t0
    return out_path_str, n_px, elapsed


def extract_protected_classes(tile_paths: list[Path]) -> list[Path]:
    """Extract EXTRACT_CLASSES from original tiles to steg2_extracted/."""
    t0_step = time.time()
    out_dir = OUT_BASE / "steg_2_extract"
    out_dir.mkdir(parents=True, exist_ok=True)

    info.info("Steg 2: Extracting classes %s from original tiles (%d workers)...",
              sorted(EXTRACT_CLASSES), N_WORKERS)

    extract_frozen = tuple(sorted(EXTRACT_CLASSES))
    task_args = [
        (str(tile), str(out_dir / tile.name), extract_frozen)
        for tile in tile_paths
    ]

    total_px_extracted = 0
    result_paths = []

    with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
        for out_path_str, n_px, elapsed in executor.map(_extract_tile_worker, task_args):
            result_paths.append(Path(out_path_str))
            total_px_extracted += n_px
            if elapsed > 0:
                log.debug("extract: %s → %d px  %.1fs",
                          Path(out_path_str).name, n_px, elapsed)

    _elapsed = time.time() - t0_step
    info.info("Steg 2 klart: totalt %d px extracted  %.1f min (%.0fs)",
              total_px_extracted, _elapsed / 60, _elapsed)

    return result_paths


if __name__ == "__main__":
    import os
    from logging_setup import setup_logging, log_step_header
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)
    
    log_step_header(info, 2, "Extract classes",
                    str(OUT_BASE / "steg_1_split_tiles"),
                    str(OUT_BASE / "steg_2_extract"))
    
    # Läs tiles från Steg 1
    tiles_dir = OUT_BASE / "steg_1_split_tiles"
    if not tiles_dir.exists():
        info.error(f"Fel: {tiles_dir} finns ej. Kör Steg 1 först (steg_1_split_tiles.py)")
        exit(1)
    
    tile_paths = sorted(tiles_dir.glob("*.tif"))
    info.info(f"Hittade {len(tile_paths)} tiles från Steg 1")
    
    protected = extract_protected_classes(tile_paths)
    info.info(f"Steg 2 klart: {len(protected)} tiles skapade")
