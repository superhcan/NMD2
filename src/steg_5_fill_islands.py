#!/usr/bin/env python3
"""
steg_4a_fill_islands.py — Steg 4: Ta bort alla sammanhängande områden < MMU_ISLAND px.

Tar bort både små öar (land < 100px) och små sjöar (vatten < 100px).
Alla små objektkällor ersätts med majoritets-omkringliggande värde.

Läser från landscape/ (Steg 3), skriver filled/ 

Kör: python3 src/steg_4a_fill_islands.py

Kräver: scipy, rasterio
"""

import logging
import shutil
import time
from pathlib import Path

import rasterio
import numpy as np
from scipy import ndimage

from config import QML_SRC, OUT_BASE, MMU_ISLAND, COMPRESS

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")


def copy_qml(tif_path: Path):
    """Kopiera referens-QML-fil till TIF-filen."""
    if QML_SRC.exists():
        shutil.copy2(QML_SRC, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def fill_islands(tile_paths: list[Path]) -> list[Path]:
    """Ta bort ALLA sammanhängande områden < MMU_ISLAND px inkl öar, sjöar, etc."""
    t0_step   = time.time()
    out_dir   = OUT_BASE / "steg5_filled"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_paths = []
    total_filled = 0
    
    info.info("Steg 4: Ta bort alla små områden < %d px (%.2f ha) - både öar och sjöar...",
              MMU_ISLAND, MMU_ISLAND * 100 / 10000)
    
    for tile in tile_paths:
        out_path = out_dir / tile.name
        if not out_path.exists():
            t0 = time.time()
            
            # Läs original landscape
            with rasterio.open(tile) as src:
                data = src.read(1)
                meta = src.meta.copy()
            
            # Börja med original data
            filled_data = data.copy()
            
            # Identifiera ALLA områden (både land och vatten) genom att labela
            # alla pixlar >= 0 (hela rasterdata är klassificerad)
            all_mask = data > 0  # Alla klassificerade pixlar
            
            n_filled = 0
            if all_mask.any():
                # Hitta sammanhängande komponenter i HELA rasterdata
                labeled, num_features = ndimage.label(all_mask)
                
                # Beräkna storlek på varje komponent
                component_sizes = ndimage.sum(all_mask, labeled, range(num_features + 1))
                
                # Identifiera små komponenter
                small_mask = component_sizes < MMU_ISLAND
                small_components = np.where(small_mask)[0]
                small_components = small_components[small_components > 0]  # Exkludera bakgrund
                
                # För varje liten komponent, ersätt med majoritets-omkringliggande värde
                struct = np.array([[0,1,0],[1,1,1],[0,1,0]], dtype=bool)
                
                for comp_id in small_components:
                    comp_mask = (labeled == comp_id)
                    
                    # Expandera masken en gång för att hitta grannar
                    expanded = ndimage.binary_dilation(comp_mask, structure=struct, iterations=1)
                    neighbor_mask = expanded & ~comp_mask
                    
                    # Hitta majoritets-värde bland grannar
                    if neighbor_mask.any():
                        neighbor_vals = data[neighbor_mask]
                        if len(neighbor_vals) > 0:
                            counts = np.bincount(neighbor_vals.astype(int))
                            replacement_class = np.argmax(counts)
                            filled_data[comp_mask] = replacement_class
                            n_filled += 1
                            total_filled += component_sizes[comp_id]
            
            # Spara resultat
            meta.update(compress=COMPRESS)
            with rasterio.open(out_path, "w", **meta) as dst:
                dst.write(filled_data, 1)
            copy_qml(out_path)
            
            elapsed = time.time() - t0
            log.debug("remove_small_areas: %s → %d små områden borttagna  %.1fs",
                      tile.name, n_filled, elapsed)
            info.info("  %-45s  %9d områden borttagna  %.1fs",
                      tile.name, n_filled, elapsed)
            
        else:
            log.debug("remove_small_areas: hoppar %s (finns redan)", tile.name)
        result_paths.append(out_path)
    
    info.info("Steg 4 klar: totalt %d små områden borttagna  %.1fs",
              total_filled, time.time() - t0_step)
    
    return result_paths


if __name__ == "__main__":
    import os
    from logging_setup import setup_logging
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)
    
    # Läs tiles från Steg 3
    tiles_dir = OUT_BASE / "steg4_generalized_modal"
    if not tiles_dir.exists():
        print(f"Fel: {tiles_dir} finns ej. Kör Steg 3 först (steg_3_extract_landscape.py)")
        exit(1)
    
    tile_paths = sorted(tiles_dir.glob("*.tif"))
    print(f"Hittade {len(tile_paths)} landskapslager från Steg 3")
    
    filled = fill_islands(tile_paths)
    print(f"Steg 4 klar: {len(filled)} lager behandlade")
