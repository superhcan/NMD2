#!/usr/bin/env python3
"""
steg_5_filter_lakes.py — Steg 5 (valfritt): Fyller små landöar < MMU_ISLAND px omringade av vatten.

En "ö" är ett sammanhängande landområde (klass ≠ 61, 62) vars samtliga grannar
(ortogonalt, konnektivitet 4) är vatten (61, 62). Ersätts med dominant vattenklass.

Körs efter steg 4 (filled/) för att rensa upp små landöar i sjöar innan generalisering.

Kör: python3 src/steg_5_filter_lakes.py
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


def fill_small_islands(data: np.ndarray, water_classes: set, mmu: int) -> tuple[np.ndarray, int]:
    """Fyll landöar < mmu px som är helt omringade av vatten."""
    data_out = data.copy()
    water = np.isin(data_out, list(water_classes))
    land = ~water
    
    # Märk alla landkomponenter
    labeled, n_comp = ndimage.label(land, structure=STRUCT_4)
    log.debug("fill_small_islands: %d landkomponenter hittade", n_comp)
    
    filled = 0
    skipped_land = 0
    
    for comp_id in range(1, n_comp + 1):
        comp_mask = (labeled == comp_id)
        comp_size = np.sum(comp_mask)
        
        # Skippa stora komponenter
        if comp_size >= mmu:
            continue
        
        # Expandera för att hitta grannar
        dilated = ndimage.binary_dilation(comp_mask, structure=STRUCT_4)
        neighbor_mask = dilated & ~comp_mask
        neighbors = data_out[neighbor_mask]
        
        # Kolla om ALLA grannar är vatten
        if not np.all(np.isin(neighbors, list(water_classes))):
            # Inte helt omringad av vatten - skippa
            skipped_land += 1
            continue
        
        # Hitta dominant vattenklass bland grannar
        vals, counts = np.unique(neighbors, return_counts=True)
        fill_val = int(vals[counts.argmax()])
        
        log.debug("  Ö %d: %d px → ersatt med vattenklass %d", comp_id, int(comp_size), fill_val)
        data_out[comp_mask] = fill_val
        filled += 1
    
    log.debug("fill_small_islands klar: %d öar fyllda, %d delvis omringade hoppades",
              filled, skipped_land)
    
    return data_out, filled


def fill_islands(tile_paths: list[Path]) -> list[Path]:
    """Fyller landöar < MMU_ISLAND px omringade av vatten i alla tiles."""
    t0_step = time.time()
    out_dir = OUT_BASE / "steg5_islands_filled"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_paths = []
    total_islands = 0
    
    info.info("Steg 5: Fyller små landöar < %d px (%.2f ha) omringade av vatten ...",
              MMU_ISLAND, MMU_ISLAND * 100 / 10000)
    
    for tile in tile_paths:
        out_path = out_dir / tile.name
        if not out_path.exists():
            t0 = time.time()
            
            with rasterio.open(tile) as src:
                data = src.read(1)
                profile = src.profile
            
            log.debug("fill_islands: bearbetar %s", tile.name)
            filled_data, n_islands = fill_small_islands(data, WATER_CLASSES, MMU_ISLAND)
            
            profile.update(compress=COMPRESS)
            with rasterio.open(out_path, 'w', **profile) as dst:
                dst.write(filled_data, 1)
            copy_qml(out_path)
            
            px_changed = int(np.sum(filled_data != data))
            elapsed = time.time() - t0
            total_islands += n_islands
            
            log.debug("fill_islands: %s → %d öar fyllda (%d px)  %.1fs",
                      tile.name, n_islands, px_changed, elapsed)
            info.info("  %-45s  %3d öar fyllda  %6d px ändrade  %.1fs",
                      tile.name, n_islands, px_changed, elapsed)
        else:
            log.debug("fill_islands: hoppar %s (finns redan)", tile.name)
        
        result_paths.append(out_path)
    
    info.info("Steg 5 klar: totalt %d öar fyllda  %.1fs",
              total_islands, time.time() - t0_step)
    
    return result_paths

if __name__ == "__main__":
    from logging_setup import setup_logging, log_step_header
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    import os
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)
    
    log_step_header(info, 5, "Fylla små landöar",
                    str(OUT_BASE / "steg4_filled"),
                    str(OUT_BASE / "steg5_islands_filled"))
    
    # Läs tiles från Steg 4 (steg4_filled/)
    filled_dir = OUT_BASE / "steg4_filled"
    if not filled_dir.exists():
        print(f"Fel: {filled_dir} finns ej. Kör Steg 4 först")
        exit(1)
    
    tile_paths = sorted(filled_dir.glob("*.tif"))
    print(f"Hittade {len(tile_paths)} tiles från Steg 4")
    
    result_paths = fill_islands(tile_paths)
    print(f"Steg 5 klar: {len(result_paths)} lager bearbetade")
