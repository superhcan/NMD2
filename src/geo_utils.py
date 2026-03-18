"""
geo_utils.py — Gemensamma geospatiala hjälpfunktioner för NMD2-pipelinen.

Innehåller VRT-byggande och halo-läsning som delas av steg 4, 5 och 6.
"""

import logging
import subprocess
from pathlib import Path

import rasterio
from rasterio.windows import Window

from config import OUT_BASE, OUT_BASE_ROOT, HALO

log = logging.getLogger("pipeline.debug")


def build_vrt(paths: list[Path], vrt_path: Path):
    """Bygger en GDAL VRT av angiven lista tif-filer."""
    log.debug("Bygger VRT %s av %d filer", vrt_path.name, len(paths))
    subprocess.run(
        ["gdalbuildvrt", str(vrt_path), *[str(p) for p in paths]],
        capture_output=True, check=True
    )
    log.debug("VRT klar: %s", vrt_path.name)


def build_cross_batch_vrt(current_paths, vrt_path, src_subdir,
                           neighbour_subdir=None, step_suffix=None, final_suffix=None):
    """Bygger en VRT som inkluderar tiles från alla tillgängliga batch-kataloger.

    Säkerställer att halo-kontexten spänner över batch-gränser.
    För varje syskonbatch används (i prioritetsordning):
      1. neighbour_subdir-output vid aktuellt steg  (step_suffix)
      2. neighbour_subdir-slutresultat              (final_suffix)
      3. src_subdir (fallback till osproceserade tiles)

    I testläge (OUT_BASE == OUT_BASE_ROOT) används enbart current_paths.
    """
    all_paths = list(current_paths)
    if OUT_BASE == OUT_BASE_ROOT:
        # Testläge — inga syskonbatchar att söka i
        build_vrt(all_paths, vrt_path)
        return

    for batch_dir in sorted(OUT_BASE_ROOT.iterdir()):
        if not batch_dir.is_dir() or batch_dir == OUT_BASE:
            continue
        if not batch_dir.name.startswith("batch_"):
            continue
        added = False
        if neighbour_subdir:
            nb_dir = batch_dir / neighbour_subdir
            if nb_dir.exists():
                if step_suffix:
                    tiles = [t for t in nb_dir.glob("*.tif") if step_suffix in t.name]
                    if tiles:
                        all_paths.extend(tiles)
                        added = True
                if not added and final_suffix:
                    tiles = [t for t in nb_dir.glob("*.tif") if final_suffix in t.name]
                    if tiles:
                        all_paths.extend(tiles)
                        added = True
        # Fallback: src_subdir (osproceserade tiles från syskonbatch)
        if not added:
            s_dir = batch_dir / src_subdir
            if s_dir.exists():
                all_paths.extend(s_dir.glob("*.tif"))

    unique_paths = sorted(set(all_paths))
    n_extra = len(unique_paths) - len(current_paths)
    log.debug("Cross-batch VRT %s: %d egna + %d syskonbatch-tiles",
              vrt_path.name, len(current_paths), n_extra)
    build_vrt(unique_paths, vrt_path)


def read_with_halo(vrt_path: Path, tile_path: Path):
    """Läser tile + HALO px kant från VRT.

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
