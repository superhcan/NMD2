#!/usr/bin/env python3
"""
steg_4b_filter_lakes.py — Steg 4b (valfritt): Tar bort små sjöar < MMU från filled/ rasterdata.

Motsvarar steg 4a men ENDAST för sjöar/vatten (klasser 61, 62).
Små sjöar ersätts med omkringliggande majoritets-värde.

Kör: python3 src/steg_4b_filter_lakes.py
"""

import logging
import shutil
import time
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

from config import QML_SRC, OUT_BASE, MMU_ISLAND, COMPRESS

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")

def copy_qml(tif_path: Path):
    """Kopiera referens-QML-fil till TIF-filen."""
    if QML_SRC.exists():
        shutil.copy2(QML_SRC, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def filter_small_lakes(tile_paths: list[Path]) -> list[Path]:
    """
    Ta bort små sjöar (klasser 61, 62) < MMU_ISLAND px från alla tiles.
    Ersätt med omkringliggande majoritets-värde.
    """
    t0_step = time.time()
    out_dir = OUT_BASE / "steg4b_filled_filtered"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_paths = []
    total_removed = 0
    total_areas = 0
    
    info.info("Steg 4b: Filtrerar små sjöar < %d px (%.2f ha)...",
              MMU_ISLAND, MMU_ISLAND * 100 / 10000)
    
    struct_4conn = np.array([[0,1,0],[1,1,1],[0,1,0]], dtype=bool)
    water_classes = np.array([61, 62], dtype=np.uint16)
    
    for tile in tile_paths:
        out_path = out_dir / tile.name
        if not out_path.exists():
            t0 = time.time()
            
            # Läs original
            with rasterio.open(tile) as src:
                original_data = src.read(1)
                profile = src.profile
            
            output_data = original_data.copy()
            n_removed = 0
            
            # Bearbeta ENDAST vattenklasser (61, 62)
            for class_val in water_classes:
                class_mask = (original_data == class_val)
                
                if not class_mask.any():
                    continue
                
                # Labela sammanhängande sjöar av denna klass
                labeled, num_features = ndimage.label(class_mask, structure=struct_4conn)
                
                if num_features == 0:
                    continue
                
                # Beräkna storlek på varje sjö-komponent
                component_sizes = ndimage.sum(class_mask, labeled, range(num_features + 1))
                
                # Identifiera små sjöar (exkludera label 0 = bakgrund)
                for comp_id in range(1, num_features + 1):
                    comp_size = component_sizes[comp_id]
                    
                    if comp_size < MMU_ISLAND:
                        comp_mask = (labeled == comp_id)
                        
                        # Expandera masken för att hitta grannar
                        expanded = ndimage.binary_dilation(comp_mask, structure=struct_4conn, iterations=1)
                        neighbor_mask = expanded & ~comp_mask
                        
                        # Hitta majoritets-värde bland grannar
                        if neighbor_mask.any():
                            neighbor_vals = original_data[neighbor_mask]
                            if len(neighbor_vals) > 0:
                                counts = np.bincount(neighbor_vals.astype(int))
                                replacement_class = np.argmax(counts)
                                output_data[comp_mask] = replacement_class
                                n_removed += 1
                                total_areas += comp_size
                                log.debug(f"  Sjö {comp_id} ({comp_size}px) → ersatt med klass {replacement_class}")
            
            # Spara resultat
            profile.update(compress=COMPRESS)
            with rasterio.open(out_path, 'w', **profile) as dst:
                dst.write(output_data, 1)
            copy_qml(out_path)
            
            elapsed = time.time() - t0
            total_removed += n_removed
            log.debug("filter_lakes: %s → %d sjöar borttagna  %.1fs",
                      tile.name, n_removed, elapsed)
            info.info("  %-45s  %9d sjöar borttagna  %.1fs",
                      tile.name, n_removed, elapsed)
                
        else:
            log.debug("filter_lakes: hoppar %s (finns redan)", tile.name)
        
        result_paths.append(out_path)
    
    info.info("Steg 4b klar: totalt %d sjöar borttagna (%d px)  %.1fs",
              total_removed, total_areas, time.time() - t0_step)
    
    return result_paths

if __name__ == "__main__":
    from logging_setup import setup_logging
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    import os
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)
    
    # Läs tiles från Steg 4a (filled/)
    filled_dir = OUT_BASE / "steg4_filled"
    if not filled_dir.exists():
        print(f"Fel: {filled_dir} finns ej. Kör Steg 4a först")
        exit(1)
    
    tile_paths = sorted(filled_dir.glob("*.tif"))
    print(f"Hittade {len(tile_paths)} tiles från Steg 4a")
    
    filtered = filter_small_lakes(tile_paths)
    print(f"Steg 4b klar: {len(filtered)} lager filtrerade")
