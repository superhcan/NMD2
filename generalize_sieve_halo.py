"""
generalize_sieve_halo.py — Steg 5a/5b: Sieve-generalisering med halo.

Kör gdal_sieve med 4- eller 8-connectedness över alla MMU-steg, med halo-overlap
för korrekt generalisering över tilekanter.
"""

import logging
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from config import (
    OUT_BASE, HALO, COMPRESS, NODATA_TMP, PROTECTED, MMU_STEPS, STRUCT_4
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


def run_sieve(data: np.ndarray, mmu: int, conn: int) -> np.ndarray:
    """Kör gdal_sieve på data-array. Skyddade klasser maskeras."""
    log.debug("run_sieve: mmu=%d conn=%d  data=%s", mmu, conn, data.shape)
    
    from rasterio.transform import from_bounds
    dummy_transform = from_bounds(0, 0, data.shape[1], data.shape[0],
                                  data.shape[1], data.shape[0])
    meta_tmp = {
        "driver": "GTiff", "dtype": data.dtype, "count": 1,
        "height": data.shape[0], "width": data.shape[1],
        "crs": "EPSG:3006", "transform": dummy_transform,
        "compress": None, "nodata": NODATA_TMP,
    }
    prot_mask = np.isin(data, list(PROTECTED))
    masked    = data.copy()
    masked[prot_mask] = NODATA_TMP

    with tempfile.NamedTemporaryFile(suffix="_in.tif",  delete=False) as f1, \
         tempfile.NamedTemporaryFile(suffix="_out.tif", delete=False) as f2:
        in_p  = Path(f1.name)
        out_p = Path(f2.name)
    try:
        with rasterio.open(in_p, "w", **meta_tmp) as dst:
            dst.write(masked, 1)
        flag = "-4" if conn == 4 else "-8"
        subprocess.run(
            ["gdal_sieve.py", "-st", str(mmu), flag, str(in_p), str(out_p)],
            capture_output=True, check=True
        )
        with rasterio.open(out_p) as src:
            sieved = src.read(1)
        sieved[prot_mask] = data[prot_mask]
        changed = int(np.sum(sieved != data))
        log.debug("run_sieve klar: %d px ändrade (%.1f%%)",
                  changed, changed / data.size * 100)
        return sieved
    finally:
        in_p.unlink(missing_ok=True)
        out_p.unlink(missing_ok=True)


def generalize_sieve_halo(filled_paths: list[Path], conn: int):
    """Köra sieve-generalisering med halo interaction over tiles."""
    label    = f"conn{conn}"
    out_dir  = OUT_BASE / f"generalized_{label}"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0_step  = time.time()

    prev_vrt = OUT_BASE / "filled_mosaic.vrt"
    if not prev_vrt.exists():
        build_vrt(filled_paths, prev_vrt)

    info.info("Steg 5 sieve-%s: %d MMU-steg × %d tiles (halo=%dpx)",
              label, len(MMU_STEPS), len(filled_paths), HALO)

    for mmu in MMU_STEPS:
        step_outputs  = []
        t0            = time.time()
        total_changed = 0
        log.debug("%s mmu=%d: startar", label, mmu)

        for tile in filled_paths:
            stem     = tile.stem
            out_path = out_dir / f"{stem}_{label}_mmu{mmu:03d}.tif"
            if out_path.exists():
                log.debug("  %s hoppar (finns redan)", out_path.name)
                step_outputs.append(out_path)
                continue

            t1 = time.time()
            padded, tile_meta, inner = read_with_halo(prev_vrt, tile)
            tile_meta.update(compress=COMPRESS)

            # Läs originaltilen för att räkna ändrade pixlar
            with rasterio.open(tile) as _src:
                orig_inner = _src.read(1)

            sieved_padded = run_sieve(padded, mmu, conn)
            result        = sieved_padded[inner]
            changed       = int(np.sum(result != orig_inner))
            total_changed += changed

            with rasterio.open(out_path, "w", **tile_meta) as dst:
                dst.write(result, 1)
            copy_qml(out_path)
            step_outputs.append(out_path)
            log.debug("  %s: %d px ändrade vs orig  %.1fs",
                      out_path.name, changed, time.time() - t1)

        step_vrt = out_dir / f"_vrt_mmu{mmu:03d}.vrt"
        build_vrt(step_outputs, step_vrt)
        prev_vrt = step_vrt
        elapsed  = time.time() - t0
        info.info("  %-10s mmu=%3dpx  totalt %9d px ändrade  %.1fs",
                  label, mmu, total_changed, elapsed)

    info.info("Steg 5 sieve-%s KLAR  %.1fs", label, time.time() - t0_step)


if __name__ == "__main__":
    from logging_setup import setup_logging
    setup_logging(OUT_BASE)
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    # Exempel på standalone-körning
    print("Denna modul anropas från pipeline.py")
