#!/usr/bin/env python3
"""
steg_3_extract_landscape.py — Steg 3: Extrahera landskapets rasterbild för generalisering.

Läser från tiles/ (Steg 1), skriver landscape/ där vägar (53) och byggnader (51)
ersätts med omkringliggande värden genom morphological dilation för att kunna 
generaliseeras tillsammans med övrig landskap.

Kör: python3 src/steg_3_extract_landscape.py
"""

import logging
import shutil
import time
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

from config import QML_SRC, OUT_BASE, ROADS_BUILDINGS, STRUCT_4, COMPRESS

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")


def copy_qml(tif_path: Path):
    """Kopiera referens-QML-fil till TIF-filen."""
    if QML_SRC.exists():
        shutil.copy2(QML_SRC, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def extract_landscape(tile_paths: list[Path]) -> list[Path]:
    """Extrahera landskapet genom att ersätta vägar/byggnader med omkringliggande värden."""
    t0_step = time.time()
    out_dir = OUT_BASE / "steg3_landscape"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_paths = []
    total_px_replaced = 0
    
    info.info("Steg 3: Extraherar landskapet (ersätter vägar(53) och byggnader(51)) ...")
    
    roads_buildings_uint16 = np.array(list(ROADS_BUILDINGS), dtype=np.uint16)
    
    for tile in tile_paths:
        out_path = out_dir / tile.name
        if not out_path.exists():
            t0 = time.time()
            with rasterio.open(tile) as src:
                meta = src.meta.copy()
                data = src.read(1)
            meta.update(compress=COMPRESS)
            
            # Identifiera vägar/byggnader
            roads_mask = np.isin(data, roads_buildings_uint16)
            px_replaced = int(roads_mask.sum())
            
            if px_replaced > 0:
                # Använd morphological filling: för varje väg/byggnad-pixel,
                # ersätt med värde från närmaste granne via distance transform
                landscape_data = data.copy()
                
                # Använd scipy.ndimage.distance_transform_edt för att fylla vägar/byggnader
                # med värden från närmaste icke-väg/byggnad pixel
                dist_transform = ndimage.distance_transform_edt(~roads_mask)
                
                # För varje väg/byggnad-pixel, hitta närmaste granne och kopiera dess värde
                for i, j in np.argwhere(roads_mask):
                    # Sök omkringliggande pixlar för att hitta icke-väg värde
                    found = False
                    for di in [-1, 0, 1]:
                        for dj in [-1, 0, 1]:
                            if di == 0 and dj == 0:
                                continue
                            ni, nj = i + di, j + dj
                            if 0 <= ni < data.shape[0] and 0 <= nj < data.shape[1]:
                                if not roads_mask[ni, nj]:
                                    landscape_data[i, j] = data[ni, nj]
                                    found = True
                                    break
                        if found:
                            break
                    if not found:
                        # Om ingen granne hittades, försöka widare
                        neighbors = []
                        for di in range(-3, 4):
                            for dj in range(-3, 4):
                                ni, nj = i + di, j + dj
                                if 0 <= ni < data.shape[0] and 0 <= nj < data.shape[1]:
                                    if not roads_mask[ni, nj]:
                                        neighbors.append(data[ni, nj])
                        if neighbors:
                            landscape_data[i, j] = max(set(neighbors), 
                                                       key=neighbors.count)
            else:
                landscape_data = data.copy()
                px_replaced = 0
            
            with rasterio.open(out_path, "w", **meta) as dst:
                dst.write(landscape_data, 1)
            copy_qml(out_path)
            
            total_px_replaced += px_replaced
            elapsed = time.time() - t0
            log.debug("extract_landscape: %s → %d px ersatta  %.1fs",
                      tile.name, px_replaced, elapsed)
            info.info("  %-45s  %9d px ersatta  %.1fs", tile.name, px_replaced, elapsed)
        else:
            log.debug("extract_landscape: hoppar %s (finns redan)", tile.name)
        result_paths.append(out_path)
    
    info.info("Steg 3 klar: totalt %d px vägar/byggnader ersatta  %.1fs",
              total_px_replaced, time.time() - t0_step)
    
    return result_paths


if __name__ == "__main__":
    import os
    from logging_setup import setup_logging
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)
    
    # Läs tiles från Steg 1
    tiles_dir = OUT_BASE / "steg1_tiles"
    if not tiles_dir.exists():
        print(f"Fel: {tiles_dir} finns ej. Kör Steg 1 först (split_tiles.py)")
        exit(1)
    
    tile_paths = sorted(tiles_dir.glob("*.tif"))
    print(f"Hittade {len(tile_paths)} tiles från Steg 1")
    
    landscape = extract_landscape(tile_paths)
    print(f"Steg 3 klar: {len(landscape)} landskapslager skapade")
