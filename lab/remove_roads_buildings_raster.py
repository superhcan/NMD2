#!/usr/bin/env python3
"""
Ta bort vägar (53) och byggnader (51) från raster-tiles genom modal filter.

Ersätter dessa pixlar med mestförekommande värde från omkringliggande pixlar,
så att landskapet fyller på naturligt innan generalisering.
"""

import logging
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import Affine
from scipy.ndimage import maximum_filter
from collections import Counter
import time

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

def modal_fill(data, mask, window_size=5):
    """
    Ersätt pixlar i mask med modal värde från omkringliggande pixlar.
    
    Args:
        data: Raster data (2D array)
        mask: Boolean array där True = pixlar att ersätta
        window_size: Filterstorlek (måste vara udda)
    
    Returns:
        Modified data array
    """
    result = data.copy()
    coords = np.where(mask)
    
    if len(coords[0]) == 0:
        return result
    
    pad = window_size // 2
    
    for y, x in zip(coords[0], coords[1]):
        # Hämta omkringliggande pixlar
        y_min = max(0, y - pad)
        y_max = min(data.shape[0], y + pad + 1)
        x_min = max(0, x - pad)
        x_max = min(data.shape[1], x + pad + 1)
        
        window = data[y_min:y_max, x_min:x_max].copy()
        
        # Exkludera de vägar/byggnader vi helt vill ta bort
        other_values = window[~np.isin(window, [51, 53])]
        
        if len(other_values) > 0:
            # Hitta moden
            mode_value = Counter(other_values).most_common(1)[0][0]
            result[y, x] = mode_value
    
    return result

def main():
    log.info("╔" + "═" * 58 + "╗")
    log.info("║ Tar bort vägar och byggnader från raster-tiles")
    log.info("║ Ersätter med modal värde från omgivning")
    log.info("╚" + "═" * 58 + "╝")
    
    TILE_DIR = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/tiles")
    QML_DIR = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/tiles")  # Original QML-filer
    OUT_DIR = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/tiles_no_roads")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # TEST: bara de 4 testiles
    test_tiles = [
        "NMD2023bas_tile_r000_c020.tif",
        "NMD2023bas_tile_r000_c021.tif",
        "NMD2023bas_tile_r001_c020.tif",
        "NMD2023bas_tile_r001_c021.tif",
    ]
    
    tiles = [TILE_DIR / name for name in test_tiles if (TILE_DIR / name).exists()]
    
    if not tiles:
        log.error(f"   ✗ Inga tiles hittades i {TILE_DIR}")
        return False
    
    log.info(f"\n1️⃣  Bearbetar {len(tiles)} testiles...")
    
    removed_total = 0
    t0 = time.time()
    
    for i, tile_file in enumerate(tiles, 1):
        log.info(f"\n   Tile {i}/{len(tiles)}: {tile_file.name}")
        
        with rasterio.open(tile_file) as src:
            data = src.read(1)
            profile = src.profile
            transform = src.transform
            
            # Identifiera vägar (53) och byggnader (51)
            mask = np.isin(data, [51, 53])
            removed_count = np.count_nonzero(mask)
            removed_total += removed_count
            
            if removed_count == 0:
                log.info(f"      • Inga vägar/byggnader att ta bort")
                continue
            
            log.info(f"      • Hittat {removed_count:,} väg-/byggnad-pixlar")
            
            # Ersätt med modal värde från omkringliggande
            log.info(f"      • Fyller med modal värde från omgivning...")
            data_filled = modal_fill(data, mask, window_size=5)
            
            # Verifiering
            mask_after = np.isin(data_filled, [51, 53])
            remaining = np.count_nonzero(mask_after)
            log.info(f"      • Efter filling: {remaining:,} pixlar återstår")
            
            # Spara modifierad tile
            out_file = OUT_DIR / tile_file.name
            
            with rasterio.open(
                out_file, 'w',
                driver='GTiff',
                height=data_filled.shape[0],
                width=data_filled.shape[1],
                count=1,
                dtype=data_filled.dtype,
                crs=src.crs,
                transform=transform,
                compress='lzw'
            ) as dst:
                dst.write(data_filled, 1)
            
            log.info(f"      ✓ Sparad: {out_file.name}")
            
            # Kopiera motsvarande QML-fil om den finns
            # QML-filer ligger i /tiles/ och heter utan ".tif"
            base_name = tile_file.stem  # NMD2023bas_tile_r000_c020
            qml_file = QML_DIR / f"{base_name}.qml"
            if qml_file.exists():
                out_qml = out_file.parent / f"{base_name}.qml"
                import shutil
                shutil.copy2(qml_file, out_qml)
                log.info(f"      ✓ QML-fil kopierad: {out_qml.name}")
            else:
                log.info(f"      ⚠ QML-fil inte hittad: {qml_file.name}")
    
    t1 = time.time()
    log.info(f"\n✅ Klart!")
    log.info(f"   • {removed_total:,} väg-/byggnad-pixlar totalt")
    log.info(f"   • Tid: {t1-t0:.1f}s")
    log.info(f"   • Modifierade tiles i: {OUT_DIR}")
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
