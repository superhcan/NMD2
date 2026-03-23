"""
replace_roads_buildings.py — Steg 3: Extrahera landskapet och ersätt vägar/byggnader.

Läser från tiles/, skriver landscape/ där vägar (53) och byggnader (51) är ersatta
med närliggande landskapsklasser via iterativ neighbor-matching.
"""

import logging
import shutil
import time
from pathlib import Path

import numpy as np
import rasterio

from config import QML_SRC, OUT_BASE, DISSOLVE_CLASSES as ROADS_BUILDINGS, COMPRESS, NODATA_TMP

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")


def copy_qml(tif_path: Path):
    """Kopiera referens-QML-fil till TIF-filen."""
    if QML_SRC.exists():
        shutil.copy2(QML_SRC, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def replace_roads_buildings(tile_paths: list[Path]) -> list[Path]:
    """
    Extrahera landskapet: ta bort vägar (53) och byggnader (51) och ersätt 
    med omkringliggande landskapsklasser via morphological dilation.
    """
    from scipy import ndimage
    
    t0_step = time.time()
    out_dir = OUT_BASE / "landscape"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_paths = []
    
    info.info("Steg 3: Ersätter vägar 53 och byggnader 51 med omkringliggande klasser...")
    
    # Konvertera till numpy uint16 för att matcha data-typen
    roads_buildings_uint16 = np.array(list(ROADS_BUILDINGS), dtype=np.uint16)
    
    struct = np.array([[1, 1, 1],
                       [1, 1, 1],
                       [1, 1, 1]], dtype=bool)  # 8-connected dilation
    
    for tile in tile_paths:
        out_path = out_dir / tile.name
        if not out_path.exists():
            t0 = time.time()
            with rasterio.open(tile) as src:
                meta = src.meta.copy()
                data = src.read(1)
            meta.update(compress=COMPRESS)
            
            landscape_data = data.copy()
            
            # Iterativ ersättning: expandera icke-väg/byggnad-områden in i vägar/byggnader
            for iteration in range(100):  # Max 100 iterationer (ökat från 30)
                mask_rb = np.isin(landscape_data, roads_buildings_uint16)
                if not np.any(mask_rb):
                    break  # Inga vägar/byggnader kvar
                
                mask_not_rb = ~mask_rb
                
                # Expandera områdena utan vägar/byggnader
                expanded = ndimage.binary_dilation(mask_not_rb, structure=struct, iterations=1)
                
                # Hitta nya pixlar som nu täcker vägar/byggnader
                new_pixels = expanded & mask_rb
                
                if not np.any(new_pixels):
                    break
                
                # För varje ny pixel, ta värdet från närmaste granne
                for i, j in zip(*np.where(new_pixels)):
                    # Hitta värdena på omkringliggande icke-väg/byggnad-pixlar
                    neighbors = []
                    for di in [-1, 0, 1]:
                        for dj in [-1, 0, 1]:
                            if di == 0 and dj == 0:
                                continue
                            ni, nj = i + di, j + dj
                            if 0 <= ni < landscape_data.shape[0] and 0 <= nj < landscape_data.shape[1]:
                                if not np.isin(landscape_data[ni, nj], roads_buildings_uint16):
                                    neighbors.append(landscape_data[ni, nj])
                    
                    if neighbors:
                        # Använd mest vanlig grannklass
                        neighbors_arr = np.array(neighbors, dtype=np.uint16)
                        vals, counts = np.unique(neighbors_arr, return_counts=True)
                        landscape_data[i, j] = vals[np.argmax(counts)]
            
            # Fallback: fyll återstående vägar/byggnader (om några) med mest vanlig omkringliggande klass
            mask_rb = np.isin(landscape_data, roads_buildings_uint16)
            if np.any(mask_rb):
                all_neighbors = []
                for i, j in zip(*np.where(mask_rb)):
                    for di in [-1, 0, 1]:
                        for dj in [-1, 0, 1]:
                            if di == 0 and dj == 0:
                                continue
                            ni, nj = i + di, j + dj
                            if 0 <= ni < landscape_data.shape[0] and 0 <= nj < landscape_data.shape[1]:
                                if not np.isin(landscape_data[ni, nj], roads_buildings_uint16):
                                    all_neighbors.append(landscape_data[ni, nj])
                
                if all_neighbors:
                    neighbors_arr = np.array(all_neighbors, dtype=np.uint16)
                    vals, counts = np.unique(neighbors_arr, return_counts=True)
                    fallback_class = vals[np.argmax(counts)]
                    landscape_data[mask_rb] = fallback_class
            
            with rasterio.open(out_path, "w", **meta) as dst:
                dst.write(landscape_data, 1)
            copy_qml(out_path)
            
            elapsed = time.time() - t0
            log.debug("replace_roads_buildings: %s → vägar/byggnader ersatta  %.1fs",
                      tile.name, elapsed)
            info.info("  %-45s  vägar/byggnader ersatta med omkringliggande klasser  %.1fs", tile.name, elapsed)
        else:
            log.debug("replace_roads_buildings: hoppar %s (finns redan)", tile.name)
        result_paths.append(out_path)
    
    info.info("Steg 3 klar: vägar/byggnader ersatta från landskapet  %.1fs",
              time.time() - t0_step)
    
    return result_paths


if __name__ == "__main__":
    from logging_setup import setup_logging
    setup_logging(OUT_BASE)
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    from rasterize_tiles import rasterize_tiles
    tiles = rasterize_tiles()
    
    landscape = replace_roads_buildings(tiles)
    print(f"Ersatte vägar/byggnader i {len(landscape)} tiles")
