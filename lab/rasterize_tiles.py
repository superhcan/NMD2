"""
rasterize_tiles.py — Steg 1: Dela upp källbilden i 1024×1024 px sub-tiles.

Läser från fullbild, skriver tiles till tiles/-mappen.
"""

import logging
import shutil
import time
from pathlib import Path

import rasterio
from rasterio.windows import Window

from config import (
    SRC, QML_SRC, OUT_BASE, PARENT_TILES, PARENT_TILE_SIZE, SUB_TILE_SIZE, COMPRESS
)

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")


def copy_qml(tif_path: Path):
    """Kopiera referens-QML-fil till TIF-filen."""
    if QML_SRC.exists():
        shutil.copy2(QML_SRC, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def rasterize_tiles() -> list[Path]:
    """Dela upp källbilden i 1024×1024 px sub-tiles (från 2048×2048 parent-tiles)."""
    t0      = time.time()
    out_dir = OUT_BASE / "tiles"
    out_dir.mkdir(parents=True, exist_ok=True)
    created  = []
    new_tiles = 0
    
    log.debug("rasterize_tiles: källbild %s", SRC.name)
    
    with rasterio.open(SRC) as src:
        meta  = src.meta.copy()
        meta.update(compress=COMPRESS)
        src_w = src.width
        src_h = src.height
        log.debug("  källbild storlek: %d × %d px", src_w, src_h)
        
        for p_row, p_col in PARENT_TILES:
            px_off = p_col * PARENT_TILE_SIZE
            py_off = p_row * PARENT_TILE_SIZE
            
            for sub_r in range(2):
                for sub_c in range(2):
                    x_off = px_off + sub_c * SUB_TILE_SIZE
                    y_off = py_off + sub_r * SUB_TILE_SIZE
                    w     = min(SUB_TILE_SIZE, src_w - x_off)
                    h     = min(SUB_TILE_SIZE, src_h - y_off)
                    
                    if w <= 0 or h <= 0:
                        log.warning("rasterize_tiles: tom tile vid (%d,%d) hoppas",
                                    p_row * 2 + sub_r, p_col * 2 + sub_c)
                        continue
                    
                    t_row = p_row * 2 + sub_r
                    t_col = p_col * 2 + sub_c
                    name  = f"NMD2023bas_tile_r{t_row:03d}_c{t_col:03d}.tif"
                    path  = out_dir / name
                    
                    if not path.exists():
                        win   = Window(x_off, y_off, w, h)
                        tmeta = meta.copy()
                        tmeta.update(width=w, height=h,
                                     transform=src.window_transform(win))
                        with rasterio.open(path, "w", **tmeta) as dst:
                            dst.write(src.read(window=win))
                        copy_qml(path)
                        new_tiles += 1
                        log.debug("  Ny tile: %s  (%d×%d px)", name, w, h)
                    else:
                        log.debug("  Hoppas (finns redan): %s", name)
                    
                    created.append(path)
    
    elapsed = time.time() - t0
    info.info("Steg 1 klar: %d tiles (%d nya, %d redan existerande)  %.1fs",
              len(created), new_tiles, len(created) - new_tiles, elapsed)
    
    return created


if __name__ == "__main__":
    # För standalone-körning
    from logging_setup import setup_logging
    setup_logging(OUT_BASE)
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    tiles = rasterize_tiles()
    print(f"Skapade {len(tiles)} tiles")
