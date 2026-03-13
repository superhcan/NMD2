"""
generalize_modal_halo.py — Steg 5c: Modal filter-generalisering med halo.

Kör modal filter över alla kernelstorlekar, med halo-overlap
för korrekt generalisering över tilekanter.
"""

import logging
import subprocess
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window
from scipy.ndimage import uniform_filter

from config import (
    OUT_BASE, HALO, COMPRESS, PROTECTED, KERNEL_SIZES
)

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")


def copy_qml(tif_path: Path):
    """Kopiera referens-QML-fil till TIF-filen."""
    from config import QML_SRC
    import shutil
    if QML_SRC.exists():
        shutil.copy2(QML_SRC, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def build_vrt(paths: list[Path], vrt_path: Path):
    """Bygger en GDAL VRT av angiven lista tif-filer."""
    log.debug("Bygger VRT %s av %d filer", vrt_path.name, len(paths))
    subprocess.run(
        ["gdalbuildvrt", str(vrt_path), *[str(p) for p in paths]],
        capture_output=True, check=True
    )
    log.debug("VRT klar: %s", vrt_path.name)


def read_with_halo(vrt_path: Path, tile_path: Path):
    """
    Läser tile + HALO px kant från VRT.

    Returnerar:
      padded_data  – numpy array (h+2*halo, w+2*halo) klippt mot VRT-gränser
      tile_meta    – meta dict för originaltilen (för skrivning av utdata)
      inner_slice  – (row_slice, col_slice) som plockar ut tile-kärnan
    """
    with rasterio.open(vrt_path) as vrt, rasterio.open(tile_path) as tile:
        vt = vrt.transform
        tt = tile.transform
        px = vt.a    # pixelbredd (positiv)
        py = vt.e    # pixelhöjd  (negativ)

        tile_col = round((tt.c - vt.c) / px)
        tile_row = round((tt.f - vt.f) / py)
        tile_w   = tile.width
        tile_h   = tile.height
        tile_meta = tile.meta.copy()

        x0 = max(0, tile_col - HALO)
        y0 = max(0, tile_row - HALO)
        x1 = min(vrt.width,  tile_col + tile_w + HALO)
        y1 = min(vrt.height, tile_row + tile_h + HALO)

        win  = Window(x0, y0, x1 - x0, y1 - y0)
        data = vrt.read(1, window=win)

    inner_row = tile_row - y0
    inner_col = tile_col - x0
    inner_slice = (
        slice(inner_row, inner_row + tile_h),
        slice(inner_col, inner_col + tile_w),
    )
    return data, tile_meta, inner_slice


def modal_filter_once(data: np.ndarray, kernel: int) -> np.ndarray:
    """En iteration av modal filter (majoritetsvoting)."""
    log.debug("modal_filter_once: kernel=%d  data=%s", kernel, data.shape)
    prot_mask  = np.isin(data, list(PROTECTED))
    vote_data  = data.copy()
    vote_data[prot_mask] = 0
    classes    = [int(c) for c in np.unique(vote_data) if c > 0]
    log.debug("  %d klasser i röstningen", len(classes))
    best_count = np.full(data.shape, -1.0, dtype=np.float32)
    best_class = np.zeros(data.shape,  dtype=np.int32)
    for cls in classes:
        mask  = (vote_data == cls).astype(np.float32)
        count = uniform_filter(mask, size=kernel, mode="nearest")
        count = count + mask * 1e-4
        upd        = count > best_count
        best_count = np.where(upd, count, best_count)
        best_class = np.where(upd, cls,   best_class)
    best_class[prot_mask] = data[prot_mask].astype(np.int32)
    best_class[data == 0] = 0
    result = best_class.astype(data.dtype)
    changed = int(np.sum(result != data))
    log.debug("modal_filter_once klar: %d px ändrade (%.1f%%)",
              changed, changed / data.size * 100)
    return result


def generalize_modal_halo(filled_paths: list[Path]):
    """Kör modal filter-generalisering med halo over tiles."""
    out_dir = OUT_BASE / "generalized_modal"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0_step = time.time()

    prev_vrt = OUT_BASE / "filled_mosaic.vrt"
    if not prev_vrt.exists():
        build_vrt(filled_paths, prev_vrt)

    info.info("Steg 5c modal: %d kernelstorlekar × %d tiles (halo=%dpx)",
              len(KERNEL_SIZES), len(filled_paths), HALO)

    for k in KERNEL_SIZES:
        step_outputs  = []
        t0            = time.time()
        total_changed = 0
        log.debug("modal k=%d: startar", k)

        for filled_tile in filled_paths:
            stem     = filled_tile.stem
            out_path = out_dir / f"{stem}_modal_k{k:02d}.tif"
            if out_path.exists():
                log.debug("  %s hoppar (finns redan)", out_path.name)
                step_outputs.append(out_path)
                continue

            t1 = time.time()
            padded, tile_meta, inner = read_with_halo(prev_vrt, filled_tile)
            tile_meta.update(compress=COMPRESS)

            with rasterio.open(filled_tile) as _src:
                orig_inner = _src.read(1)

            result  = modal_filter_once(padded, k)[inner]
            changed = int(np.sum(result != orig_inner))
            total_changed += changed

            with rasterio.open(out_path, "w", **tile_meta) as dst:
                dst.write(result, 1)
            copy_qml(out_path)
            step_outputs.append(out_path)
            log.debug("  %s: %d px ändrade vs orig  %.1fs",
                      out_path.name, changed, time.time() - t1)

        step_vrt = out_dir / f"_vrt_k{k:02d}.vrt"
        build_vrt(step_outputs, step_vrt)
        prev_vrt = step_vrt
        final_outputs = step_outputs
        elapsed  = time.time() - t0
        info.info("  modal      k=%2d          totalt %9d px ändrade  %.1fs",
                  k, total_changed, elapsed)

    info.info("Steg 5c modal KLAR  %.1fs", time.time() - t0_step)
    return final_outputs


if __name__ == "__main__":
    from logging_setup import setup_logging
    setup_logging(OUT_BASE)
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    print("Denna modul anropas från pipeline.py")
