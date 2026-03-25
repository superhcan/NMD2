#!/usr/bin/env python3
"""
steg_4_filter_lakes.py — Steg 4: Ta bort små sjöar (vattenytor < MMU_ISLAND px) och fyller med omgivande mark.

Använder scipy.ndimage för connected-component labeling för att identifiera
små sjöar och vattenytor (klasser 61, 62), tar bort dem och fyller tomrummen
med majoriteten från omkringliggande område (samma approach som steg 3).

Läser från landscape/ (Steg 3), skriver filled/ 

Kör: python3 src/steg_4_filter_lakes.py

Kräver: scipy, rasterio, numpy
"""

import logging
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

from config import QML_RECLASSIFY, OUT_BASE, MMU_ISLAND, COMPRESS, ISLAND_FILL_SURROUNDS

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")


def copy_qml(tif_path: Path):
    """Kopiera referens-QML-fil till TIF-filen."""
    if QML_RECLASSIFY.exists():
        shutil.copy2(QML_RECLASSIFY, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def fill_water_islands(tile_paths: list[Path]) -> list[Path]:
    """Ta bort små sjöar < MMU_ISLAND px och fylla tomrummen med omkringliggande majoritet."""
    t0_step   = time.time()
    out_dir   = OUT_BASE / "steg_4_filter_lakes"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_paths = []
    
    info.info("Steg 4: Tar bort små sjöar < %d px (%.2f ha) och fyller med  omkringliggande ...",
              MMU_ISLAND, MMU_ISLAND * 100 / 10000)
    
    for tile in tile_paths:
        out_path = out_dir / tile.name
        if not out_path.exists():
            t0 = time.time()
            
            try:
                with rasterio.open(tile) as src:
                    meta = src.meta.copy()
                    data = src.read(1)
                
                water_mask = np.isin(data, list(ISLAND_FILL_SURROUNDS))
                
                if np.sum(water_mask) == 0:
                    # Ingen vatten - kopiera bara filen
                    log.debug("Ingen vatten i %s", tile.name)
                    output_data = data.copy()
                else:
                    # Connected-component labeling med scipy (4-connectivity)
                    structure = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)
                    labeled_water, num_components = ndimage.label(water_mask, structure=structure)
                    component_sizes = ndimage.sum(water_mask, labeled_water, range(num_components + 1))
                    
                    # Identifiera STORA komponenter (>= MMU_ISLAND)
                    large_components = set(np.where(component_sizes >= MMU_ISLAND)[0])
                    small_count = num_components - len(large_components)
                    
                    log.debug("Komponenter: totalt=%d, stora=>=%dpx:%d, små:%d",
                              num_components, MMU_ISLAND, len(large_components), small_count)
                    
                    # Kopiera BARA stora sjöar + all landskap. Små sjöar = 0 (tas bort)
                    output_data = np.where(water_mask, 0, data)  # Sätt vatten till 0
                    
                    # Restore stora sjöar
                    for comp_id in large_components:
                        if comp_id != 0:  # Skip background
                            comp_mask = labeled_water == comp_id
                            output_data[comp_mask] = data[comp_mask]
                    
                    # Fyll tomrummen (små sjöar) med majoriteten från omkringliggande (steg 3-stil)
                    zero_mask = output_data == 0
                    for i, j in np.argwhere(zero_mask):
                        # Försök först 3x3 omkringliggande
                        found = False
                        for di in [-1, 0, 1]:
                            for dj in [-1, 0, 1]:
                                if di == 0 and dj == 0:
                                    continue
                                ni, nj = i + di, j + dj
                                if 0 <= ni < output_data.shape[0] and 0 <= nj < output_data.shape[1]:
                                    if output_data[ni, nj] != 0:
                                        output_data[i, j] = output_data[ni, nj]
                                        found = True
                                        break
                            if found:
                                break
                        
                        # Om ingen granne hittades, försök större område och använd majoritet
                        if not found:
                            neighbors = []
                            for di in range(-3, 4):
                                for dj in range(-3, 4):
                                    ni, nj = i + di, j + dj
                                    if 0 <= ni < output_data.shape[0] and 0 <= nj < output_data.shape[1]:
                                        if output_data[ni, nj] != 0:
                                            neighbors.append(output_data[ni, nj])
                            if neighbors:
                                # Använd majority värdet
                                output_data[i, j] = max(set(neighbors), key=neighbors.count)
                    
                    log.debug("Små sjöar borttagna: %d komponenter", small_count)
                
                # Skriv resultat
                meta.update(compress=COMPRESS)
                with rasterio.open(out_path, "w", **meta) as dst:
                    dst.write(output_data, 1)
                
                # Kopiera QML
                copy_qml(out_path)
                
                elapsed = time.time() - t0
                log.debug("Steg 4: %s → klart  %.1fs", tile.name, elapsed)
                info.info("  %-45s  klart  %.1fs", tile.name, elapsed)
                result_paths.append(out_path)
                
            except Exception as e:
                log.error("Misslyckades för %s: %s", tile.name, str(e))
                info.error("  %-45s  MISSLYCKADES", tile.name)
                raise
        else:
            log.debug("Hoppar %s (finns redan)", tile.name)
            result_paths.append(out_path)
    
    info.info("Steg 4 klar: %d tiles behandlade  %.1fs",
              len(result_paths), time.time() - t0_step)
    
    return result_paths


if __name__ == "__main__":
    import os
    from logging_setup import setup_logging, log_step_header
    
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)
    
    log_step_header(info, 4, "Ta bort små sjöar",
                    str(OUT_BASE / "steg_3_dissolve"),
                    str(OUT_BASE / "steg_4_filter_lakes"))
    
    # Läs tiles från Steg 3, eller fallback till Steg 1 om Steg 3 är inaktiverat
    tiles_dir = OUT_BASE / "steg_3_dissolve"
    if not tiles_dir.exists():
        fallback = OUT_BASE / "steg_1_reclassify"
        if fallback.exists():
            info.info(f"steg_3_dissolve/ saknas – använder steg_1_reclassify/ som indata")
            tiles_dir = fallback
        else:
            info.error(f"Fel: {tiles_dir} finns ej. Kör Steg 1-3 först")
            exit(1)
    
    tiles = sorted(tiles_dir.glob("*.tif"))
    if not tiles:
        info.error(f"Fel: Inga TIF-filer i {tiles_dir}")
        exit(1)
    
    info.info(f"Hittade {len(tiles)} tiles från Steg 3")
    fill_water_islands(tiles)
    info.info("Steg 4 klart: %d tiles behandlade", len(tiles))
