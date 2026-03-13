"""
extract_protected_classes.py — Steg 2: Extrahera endast skyddade klasser.

Läser från tiles/, skriver protected/ där bara klasserna {51,52,53,54,61,62} är bevarade.
"""

import logging
import shutil
import time
from pathlib import Path

import numpy as np
import rasterio

from config import QML_SRC, OUT_BASE, PROTECTED, COMPRESS

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")


def copy_qml(tif_path: Path):
    """Kopiera referens-QML-fil till TIF-filen."""
    if QML_SRC.exists():
        shutil.copy2(QML_SRC, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def extract_protected_classes(tile_paths: list[Path]) -> list[Path]:
    """Extrahera BARA skyddade klasser från original-tiles."""
    t0_step = time.time()
    out_dir = OUT_BASE / "protected"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_paths = []
    total_px_extracted = 0
    
    info.info("Steg 2: Extraherar skyddade klasser %s från original-tiles...", sorted(PROTECTED))
    
    # Konvertera till numpy uint16 för att matcha data-typen
    protected_uint16 = np.array(list(PROTECTED), dtype=np.uint16)
    
    for tile in tile_paths:
        out_path = out_dir / tile.name
        if not out_path.exists():
            t0 = time.time()
            with rasterio.open(tile) as src:
                meta = src.meta.copy()
                data = src.read(1)
            meta.update(compress=COMPRESS)
            
            # Skapa mask för skyddade klasser, sätt allt annat till 0
            mask = np.isin(data, protected_uint16)
            protected_data = data.copy()
            protected_data[~mask] = 0
            protected_data = protected_data.astype(data.dtype)
            
            n_px = int(np.count_nonzero(protected_data))
            total_px_extracted += n_px
            
            with rasterio.open(out_path, "w", **meta) as dst:
                dst.write(protected_data, 1)
            copy_qml(out_path)
            
            elapsed = time.time() - t0
            log.debug("extract_protected_classes: %s → %d px skyddade klasser  %.1fs",
                      tile.name, n_px, elapsed)
            info.info("  %-45s  %9d px extraherade  %.1fs", tile.name, n_px, elapsed)
        else:
            log.debug("extract_protected_classes: hoppar %s (finns redan)", tile.name)
        result_paths.append(out_path)
    
    info.info("Steg 2 klar: totalt %d px skyddade klasser extraherade  %.1fs",
              total_px_extracted, time.time() - t0_step)
    
    return result_paths


if __name__ == "__main__":
    from logging_setup import setup_logging
    setup_logging(OUT_BASE)
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    from rasterize_tiles import rasterize_tiles
    tiles = rasterize_tiles()
    
    protected = extract_protected_classes(tiles)
    print(f"Extraherade {len(protected)} protected-tiles")
