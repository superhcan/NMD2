"""
fill_islands.py — Steg 4: Fyller landöar < MMU_ISLAND px som är helt omringade av vatten.

En "ö" definieras som ett sammanhängande landområde (klass ≠ 61, 62) vars
samtliga grannar (ortogonalt, konnektivitet 4) tillhör klass 61 eller 62.
Sådana öar ersätts med den dominerande vattenklass som omger dem.

Bör köras FÖRE generaliseringssteget (gdal_sieve / modal / semantic).

Kräver: rasterio, numpy, scipy (i venv)
"""

import logging
import shutil
import time
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

from config import QML_SRC, OUT_BASE, WATER_CLASSES, MMU_ISLAND, STRUCT_4, COMPRESS

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")


def copy_qml(tif_path: Path):
    """Kopiera referens-QML-fil till TIF-filen."""
    if QML_SRC.exists():
        shutil.copy2(QML_SRC, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def fill_small_islands(data: np.ndarray, water_classes: set, mmu: int):
    """Fyll landöar < mmu px som är helt omringade av vatten."""
    data   = data.copy()
    water  = np.isin(data, list(water_classes))
    land   = ~water
    labeled, n_comp = ndimage.label(land, structure=STRUCT_4)
    log.debug("fill_small_islands: %d landkomponenter hittade", n_comp)
    filled = 0
    skipped_land = 0
    for i in range(1, n_comp + 1):
        comp = labeled == i
        if comp.sum() >= mmu:
            continue
        dilated   = ndimage.binary_dilation(comp, structure=STRUCT_4)
        neighbors = data[dilated & ~comp]
        if not np.all(np.isin(neighbors, list(water_classes))):
            skipped_land += 1
            continue
        vals, counts = np.unique(neighbors, return_counts=True)
        fill_val     = int(vals[counts.argmax()])
        log.debug("  Ö %d: %d px → ersatt med klass %d", i, int(comp.sum()), fill_val)
        data[comp]   = fill_val
        filled      += 1
    log.debug("fill_small_islands klar: %d öar fyllda, %d delvis omringade hoppades",
              filled, skipped_land)
    return data, filled


def fill_islands(tile_paths: list[Path]) -> list[Path]:
    """Fyller landöar < MMU_ISLAND px i alla tiles."""
    t0_step   = time.time()
    out_dir   = OUT_BASE / "filled"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_paths  = []
    total_islands = 0
    
    info.info("Steg 4: Fyller landöar < %d px (%.2f ha) i vatten ...",
              MMU_ISLAND, MMU_ISLAND * 100 / 10000)
    
    for tile in tile_paths:
        out_path = out_dir / tile.name
        if not out_path.exists():
            t0 = time.time()
            with rasterio.open(tile) as src:
                meta = src.meta.copy()
                data = src.read(1)
            meta.update(compress=COMPRESS)
            log.debug("fill_islands: bearbetar %s", tile.name)
            filled_data, n = fill_small_islands(data, WATER_CLASSES, MMU_ISLAND)
            with rasterio.open(out_path, "w", **meta) as dst:
                dst.write(filled_data, 1)
            copy_qml(out_path)
            px_changed = int(np.sum(filled_data != data))
            elapsed    = time.time() - t0
            total_islands += n
            info.info("  %-45s  %3d öar fyllda  %6d px ändrade  %.1fs",
                      tile.name, n, px_changed, elapsed)
        else:
            log.debug("fill_islands: hoppar %s (finns redan)", tile.name)
        result_paths.append(out_path)
    
    info.info("Steg 4 klar: totalt %d öar fyllda  %.1fs",
              total_islands, time.time() - t0_step)
    
    return result_paths


# ── Standalone-körning för test ────────────────────────────────────────────────

if __name__ == "__main__":
    from logging_setup import setup_logging
    setup_logging(OUT_BASE)
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    from rasterize_tiles import rasterize_tiles
    tiles = rasterize_tiles()
    
    filled = fill_islands(tiles)
    print(f"Fyllde öar i {len(filled)} tiles")
