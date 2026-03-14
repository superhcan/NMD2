#!/usr/bin/env python3
"""
steg_4b_filter_lakes.py — Steg 4b (valfritt): Tar bort små sjöar < 1 ha från filled/ rasterdata.

Motsvarar steg 4a men för sjöar/vatten (klasser 61, 62) istället för landöar.

Optimerad: Använder GDAL's gdal_sieve.py (mycket snabbare än scipy.ndimage).

Kör: python3 src/steg_4b_filter_lakes.py
"""

import logging
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import rasterio

from config import QML_SRC, OUT_BASE, MMU_ISLAND, COMPRESS

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")

def copy_qml(tif_path: Path):
    """Kopiera referens-QML-fil till TIF-filen."""
    if QML_SRC.exists():
        shutil.copy2(QML_SRC, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def filter_small_lakes_gdal_sieve(input_raster: Path, output_raster: Path, mmu: int):
    """
    Filtrera små sjöar från binär water mask med GDAL sieve.
    
    Returnerar True om framgångsrik.
    """
    try:
        # gdal_sieve.py syntax: gdal_sieve.py -st threshold [-4] srcfile dstfile
        cmd = [
            "gdal_sieve.py",
            "-st", str(mmu),  # Threshold i pixlar
            "-4",  # 4-connected
            str(input_raster),
            str(output_raster)
        ]
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=300,
            check=False
        )
        
        if result.returncode != 0:
            if "not found" in result.stderr.lower():
                raise FileNotFoundError("gdal_sieve.py hittades inte")
            log.warning(f"gdal_sieve varning: {result.stderr[:200]}")
        
        return output_raster.exists() and output_raster.stat().st_size > 0
        
    except FileNotFoundError:
        log.error("❌ gdal_sieve.py hittades inte. Installera: apt install gdal-bin")
        return False
    except subprocess.TimeoutExpired:
        log.error("❌ gdal_sieve.py timeout (>300s)")
        return False


def filter_small_lakes(tile_paths: list[Path]) -> list[Path]:
    """
    Ta bort små sjöar < MMU_ISLAND px från alla tiles i filled/ katalogen.
    """
    t0_step = time.time()
    out_dir = OUT_BASE / "steg4b_filled_filtered"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_paths = []
    total_removed = 0
    
    info.info("Steg 4b: Filtrerar små sjöar < %d px (%.2f ha)...",
              MMU_ISLAND, MMU_ISLAND * 100 / 10000)
    
    for tile in tile_paths:
        out_path = out_dir / tile.name
        if not out_path.exists():
            t0 = time.time()
            
            try:
                # Läs original
                with rasterio.open(tile) as src:
                    original_data = src.read(1)
                    profile = src.profile
                
                # Skapa binär water mask (klasser 61, 62)
                water_classes = [61, 62]
                water_mask = np.isin(original_data, water_classes)
                
                # Temp files
                temp_mask_path = out_dir / f"{tile.stem}_water_temp.tif"
                temp_sieved_path = out_dir / f"{tile.stem}_water_sieved_temp.tif"
                
                # Skriv binär water mask för GDAL
                with rasterio.open(temp_mask_path, 'w', **profile) as dst:
                    dst.write((water_mask * 1).astype(np.uint8), 1)
                
                # Kör GDAL sieve
                success = filter_small_lakes_gdal_sieve(temp_mask_path, temp_sieved_path, MMU_ISLAND)
                
                if not success:
                    log.warning(f"GDAL sieve misslyckades för {tile.name}, kopierar original")
                    shutil.copy2(tile, out_path)
                    n_removed = 0
                else:
                    # Läs sieved water mask
                    with rasterio.open(temp_sieved_path) as src:
                        sieved_mask = src.read(1).astype(bool)
                    
                    # Identifiera sjöar som försvunnit
                    removed_lakes = water_mask & ~sieved_mask
                    n_removed = int(np.sum(removed_lakes))
                    
                    # Kopiera original och ersätt borttagna sjöar
                    output_data = original_data.copy()
                    
                    if removed_lakes.any():
                        # Ersätt med omkringliggande värde
                        for i, j in np.argwhere(removed_lakes):
                            neighbors = []
                            for di in [-1, 0, 1]:
                                for dj in [-1, 0, 1]:
                                    if di == 0 and dj == 0:
                                        continue
                                    ni, nj = i + di, j + dj
                                    if 0 <= ni < original_data.shape[0] and 0 <= nj < original_data.shape[1]:
                                        if not removed_lakes[ni, nj]:
                                            neighbors.append(original_data[ni, nj])
                            
                            if neighbors:
                                output_data[i, j] = max(set(neighbors), key=neighbors.count)
                    
                    # Spara resultat
                    profile.update(compress=COMPRESS)
                    with rasterio.open(out_path, 'w', **profile) as dst:
                        dst.write(output_data, 1)
                    copy_qml(out_path)
                    
                    total_removed += n_removed
                
                elapsed = time.time() - t0
                log.debug("filter_lakes: %s → %d sjöar borttagna  %.1fs",
                          tile.name, n_removed, elapsed)
                info.info("  %-45s  %9d sjöar borttagna  %.1fs",
                          tile.name, n_removed, elapsed)
                
                # Rensa temp-filer
                if temp_mask_path.exists():
                    temp_mask_path.unlink()
                if temp_sieved_path.exists():
                    temp_sieved_path.unlink()
                    
            except Exception as e:
                log.error(f"filter_lakes: ERROR {tile.name}: {e}")
                shutil.copy2(tile, out_path)
        else:
            log.debug("filter_lakes: hoppar %s (finns redan)", tile.name)
        
        result_paths.append(out_path)
    
    info.info("Steg 4b klar: totalt %d sjöar borttagna  %.1fs",
              total_removed, time.time() - t0_step)
    
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
