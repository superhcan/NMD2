"""
steg_6b_expand_water.py — Steg 6b: Utvidga mark in i vattenytor.

Läser de generaliserade rasterytorna från steg 6 (steg_6_generalize/{method}/)
och applicerar en kantzonsoperation:

  * Vattenpixlar (EXPAND_WATER_CLASSES) inom EXPAND_WATER_PX px avstånd
    från närmaste landpixel ersätts med den närmaste landklassen
    (mark "flyter ut" in i strandkanten).

  * Vattenpixlar som ligger djupare än EXPAND_WATER_PX från land sätts
    till 0 (nodata/transparent) — vattenytans inre är tom.

Effekten: byggnadslagret (eller LM-hydrografi via steg 10) kan sedan
klippas in i de tomma ytorna utan att klassificeringsvärden kolliderar.

Indata : steg_6_generalize/{method}/*_mmu050.tif   (ett TIF per tile)
Utdata : steg_6b_expand_water/{method}/*.tif        (ett TIF per tile)

Steg 7+8 (steg_78_grass.py) läser automatiskt från steg_6b_expand_water/
om den katalogen finns, annars från steg_6_generalize/.

Kör   : python3 src/steg_6b_expand_water.py
Kräver: rasterio, numpy, scipy (i venv)
"""

import logging
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
from config import (
    OUT_BASE, QML_RECLASSIFY, COMPRESS, HALO,
    GENERALIZATION_METHODS,
    EXPAND_WATER_CLASSES, EXPAND_WATER_PX,
    BUILD_OVERVIEWS, OVERVIEW_LEVELS,
)
from steg_6_generalize import read_with_halo, build_vrt

# ══════════════════════════════════════════════════════════════════════════════
# Logging
# ══════════════════════════════════════════════════════════════════════════════

_LOGGERS: dict = {}


def _setup_logging(out_base: Path):
    log_dir     = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)

    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    step_num  = os.getenv("STEP_NUMBER", "6b")
    step_name = os.getenv("STEP_NAME",  "expand_water")
    suffix    = f"steg_{step_num}_{step_name}_{ts}"

    fmt_detail  = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fmt_summary = logging.Formatter(
        "%(asctime)s [%(levelname)-6s] %(message)s",
        datefmt="%H:%M:%S",
    )

    dbg = logging.getLogger("pipeline.debug")
    dbg.setLevel(logging.DEBUG)
    dbg_h = logging.FileHandler(log_dir / f"debug_{suffix}.log")
    dbg_h.setLevel(logging.DEBUG)
    dbg_h.setFormatter(fmt_detail)
    dbg.addHandler(dbg_h)

    summary = logging.getLogger("pipeline.summary")
    summary.setLevel(logging.INFO)
    sfh = logging.FileHandler(summary_dir / f"summary_{suffix}.log")
    sfh.setLevel(logging.INFO)
    sfh.setFormatter(fmt_summary)
    summary.addHandler(sfh)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt_summary)
    summary.addHandler(ch)

    _LOGGERS["debug"]   = dbg
    _LOGGERS["summary"] = summary
    summary.info("Steg 6b startat")


# Placeholders — byts ut i __main__
log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")

N_WORKERS = max(1, (os.cpu_count() or 1) - 2)

# ══════════════════════════════════════════════════════════════════════════════
# Hjälpfunktioner
# ══════════════════════════════════════════════════════════════════════════════


def _copy_qml(tif_path: Path):
    if QML_RECLASSIFY.exists():
        shutil.copy2(QML_RECLASSIFY, tif_path.with_suffix(".qml"))


def _build_overviews(path: Path) -> None:
    if not BUILD_OVERVIEWS:
        return
    try:
        with rasterio.open(path, "r+") as ds:
            ds.build_overviews(OVERVIEW_LEVELS, rasterio.enums.Resampling.nearest)
            ds.update_tags(ns="rio_overview", resampling="nearest")
    except Exception as exc:
        log.warning("Kunde inte bygga overviews för %s: %s", path.name, exc)


# ══════════════════════════════════════════════════════════════════════════════
# Worker (körs i subprocess via ProcessPoolExecutor — måste vara top-level)
# ══════════════════════════════════════════════════════════════════════════════

def _expand_worker(args):
    """
    Utför expand-water-operationen för en tile.

    args = (vrt_path_str, tile_path_str, out_path_str, water_classes_tuple, expand_px)

    Returnerar (out_path_str, changed_pixels).
    """
    vrt_path_str, tile_path_str, out_path_str, water_classes_tuple, expand_px = args
    vrt_path  = Path(vrt_path_str)
    tile_path = Path(tile_path_str)
    out_path  = Path(out_path_str)

    if out_path.exists():
        return str(out_path), 0

    padded, tile_meta, inner = read_with_halo(vrt_path, tile_path)
    tile_meta.update(compress=COMPRESS)

    water_arr  = np.array(list(water_classes_tuple), dtype=padded.dtype)
    water_mask = np.isin(padded, water_arr)

    result = padded.copy()
    if water_mask.any():
        # distance_transform_edt på water_mask:
        #   för varje True-pixel = avstånd till närmaste False-pixel (land).
        distances, indices = ndimage.distance_transform_edt(
            water_mask, return_indices=True
        )

        # Kantzon (distance <= expand_px) → fyll med närmaste landklass
        fill_mask = water_mask & (distances <= expand_px)
        result[fill_mask] = padded[indices[0][fill_mask], indices[1][fill_mask]]
        # Inre vatten (distance > expand_px) → 0 (nodata/tomt, klipps mot externt lager)
        result[water_mask & ~fill_mask] = 0

    tile_result  = result[inner]
    tile_original = padded[inner]
    changed = int(np.sum(tile_result != tile_original))

    with rasterio.open(out_path, "w", **tile_meta) as dst:
        dst.write(tile_result, 1)

    _copy_qml(out_path)
    _build_overviews(out_path)
    return str(out_path), changed


# ══════════════════════════════════════════════════════════════════════════════
# Huvudlogik per method-katalog
# ══════════════════════════════════════════════════════════════════════════════

def process_method(method_name: str) -> bool:
    """
    Kör expand-water för en generaliserings-metod.

    Läser:  steg_6_generalize/{method_name}/*_mmu050.tif
    Skriver: steg_6b_expand_water/{method_name}/*.tif
    """
    src_dir = OUT_BASE / "steg_6_generalize" / method_name
    if not src_dir.exists():
        info.warning("Steg 6b: källkatalog saknas: %s", src_dir)
        return False

    src_tifs = sorted(src_dir.glob("*_mmu050.tif"))
    if not src_tifs:
        info.warning("Steg 6b: inga *_mmu050.tif-filer i %s", src_dir)
        return False

    out_dir = OUT_BASE / "steg_6b_expand_water" / method_name
    out_dir.mkdir(parents=True, exist_ok=True)

    # VRT-mosaic av källfilerna (för halo-läsning)
    vrt_path = OUT_BASE / f"_6b_{method_name}_src.vrt"
    build_vrt(src_tifs, vrt_path)

    water_tuple = tuple(sorted(EXPAND_WATER_CLASSES))
    task_args = [
        (str(vrt_path), str(tif), str(out_dir / tif.name), water_tuple, EXPAND_WATER_PX)
        for tif in src_tifs
    ]

    t0 = time.time()
    info.info(
        "Steg 6b: %s — %d tiles  (expand=%dpx%s, klasser=%s, halo=%dpx)",
        method_name, len(src_tifs), EXPAND_WATER_PX,
        " = ta bort hela vattenytan" if EXPAND_WATER_PX == 0 else "",
        EXPAND_WATER_CLASSES, HALO,
    )

    total_changed = 0
    with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
        for out_path_str, changed in executor.map(_expand_worker, task_args):
            total_changed += changed

    vrt_path.unlink(missing_ok=True)

    # Bygg VRT-mosaic av resultaten för enkel QGIS-visning
    result_tifs = sorted(out_dir.glob("*.tif"))
    if result_tifs:
        build_vrt(result_tifs, out_dir / "_mosaic.vrt")

    elapsed = time.time() - t0
    info.info(
        "Steg 6b: %s KLAR — %d px ändrade  (%.1f s)",
        method_name, total_changed, elapsed,
    )
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    OUT_BASE.mkdir(parents=True, exist_ok=True)
    _setup_logging(OUT_BASE)
    log  = _LOGGERS["debug"]
    info = _LOGGERS["summary"]

    if not EXPAND_WATER_CLASSES:
        info.info("Steg 6b: EXPAND_WATER_CLASSES är tomt — inget att göra.")
        sys.exit(0)

    t_total = time.time()
    info.info("══════════════════════════════════════════════════════════")
    info.info("Steg 6b: Expand water  (expand=%dpx, klasser=%s)",
              EXPAND_WATER_PX, EXPAND_WATER_CLASSES)
    info.info("Källa   : %s/steg_6_generalize/", OUT_BASE)
    info.info("Utdata  : %s/steg_6b_expand_water/", OUT_BASE)
    info.info("══════════════════════════════════════════════════════════")

    # Hitta vilka metodkataloger som finns och matchar GENERALIZATION_METHODS
    gen6_dir = OUT_BASE / "steg_6_generalize"
    if not gen6_dir.exists():
        info.error("steg_6_generalize/ saknas — kör steg 6 först")
        sys.exit(1)

    methods_to_run = []
    for method in sorted(GENERALIZATION_METHODS):
        method_dir = gen6_dir / method
        if method_dir.exists():
            methods_to_run.append(method)
        else:
            info.warning("  metodkatalog saknas: %s", method_dir)

    # Kör även eventuella morph-varianter (conn4_morph_*, etc.)
    for d in sorted(gen6_dir.iterdir()):
        if d.is_dir() and "_morph_" in d.name and d.name not in methods_to_run:
            methods_to_run.append(d.name)

    if not methods_to_run:
        info.error("Inga generaliserings-metodkataloger hittades i %s", gen6_dir)
        sys.exit(1)

    ok_count = 0
    for method_name in methods_to_run:
        if process_method(method_name):
            ok_count += 1

    elapsed_total = time.time() - t_total
    info.info("══════════════════════════════════════════════════════════")
    info.info("Steg 6b klart: %d/%d metoder OK  (%.1f min, %.0f s)",
              ok_count, len(methods_to_run), elapsed_total / 60, elapsed_total)
    info.info("Utdata: %s/steg_6b_expand_water/", OUT_BASE)
    info.info("══════════════════════════════════════════════════════════")

    sys.exit(0 if ok_count == len(methods_to_run) else 1)
