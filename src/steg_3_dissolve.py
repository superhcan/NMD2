"""
steg_3_dissolve.py — Steg 3: Lös upp utvalda klasser i omgivande mark.

Klasser som vägar (51) och bebyggelse (53) ersätts med närmaste icke-väg/bebyggelse-pixel 
via distance transform (scipy.ndimage.distance_transform_edt) — O(N), linjär i pixelantal.

Input:  steg_1_reclassify/*.tif (omklassificerade tiles)
Output: steg_3_dissolve/*.tif (DISSOLVE_CLASSES utbytta mot omgivande mark)

Kör: python3 src/steg_3_dissolve.py
"""

import logging
import os
import shutil
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

# QML_RECLASSIFY — färgpalett för de reklassificerade koderna (från steg 1).
#   Kopieras bredvid varje output-TIF så QGIS visar rätt färger direkt.
# OUT_BASE       — rotkatalog för denna pipeline-körning (t.ex. pipeline_test_1proc_v03/).
# DISSOLVE_CLASSES — set med pixelkoder som ska lösas upp, t.ex. {51, 53}.
# STRUCT_4       — 4-sammanhängande strukturelement (används ej direkt här men
#                  importeras av run_all_steps för att verifiera config).
# COMPRESS       — komprimeringsmetod för output-TIF (t.ex. "deflate").
from config import QML_RECLASSIFY, OUT_BASE, DISSOLVE_CLASSES, DISSOLVE_EMPTY_CLASSES, DISSOLVE_MAX_DIST, STRUCT_4, COMPRESS

# Reservera två kärnor för OS och QGIS/interaktivt arbete.
N_WORKERS = max(1, (os.cpu_count() or 1) - 2)

# Två separata loggers: "pipeline.debug" för täta per-tile-meddelanden,
# "pipeline.summary" för de rader som alltid visas i sammanfattningen.
log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")


def copy_qml(tif_path: Path):
    """Kopiera reklassificerings-QML bredvid TIF-filen så att QGIS laddar rätt palett."""
    if QML_RECLASSIFY.exists():
        shutil.copy2(QML_RECLASSIFY, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def _dissolve_tile_worker(args):
    """Top-level worker för ProcessPoolExecutor.

    Måste vara en top-level-funktion (inte lambda eller nästlad) för att
    kunna serialiseras med pickle mellan processer.
    """
    tile_str, out_path_str, dissolve_classes_frozen, empty_classes_frozen = args
    tile = Path(tile_str)
    out_path = Path(out_path_str)

    # Hoppa över om output redan finns — möjliggör restart utan omräkning.
    if out_path.exists():
        return out_path_str, 0, 0, 0.0

    t0 = time.time()
    dissolve_set = np.array(list(dissolve_classes_frozen), dtype=np.uint16)
    empty_set    = np.array(list(empty_classes_frozen),   dtype=np.uint16)

    with rasterio.open(tile) as src:
        meta = src.meta.copy()
        data = src.read(1)          # band 1, uint16 pixelkoder
    meta.update(compress=COMPRESS)

    # replace_mask: pixlar som ska ersättas med närmaste omgivande klass
    # empty_mask:   pixlar som ska nollställas (lämnas tomma)
    replace_mask = np.isin(data, dissolve_set) if dissolve_set.size else np.zeros(data.shape, dtype=bool)
    empty_mask   = np.isin(data, empty_set)   if empty_set.size   else np.zeros(data.shape, dtype=bool)
    all_dissolve_mask = replace_mask | empty_mask

    px_replaced = int(replace_mask.sum())
    px_emptied  = int(empty_mask.sum())

    landscape_data = data.copy()

    if replace_mask.any():
        # Distance transform: hitta närmaste källpixel som VARKEN är replace ELLER empty.
        # På så vis "flödar" inte tomma klasser in i replace-klassernas fill.
        distances, indices = ndimage.distance_transform_edt(all_dissolve_mask, return_indices=True)

        if DISSOLVE_MAX_DIST > 0:
            fill_mask = replace_mask & (distances <= DISSOLVE_MAX_DIST)
        else:
            fill_mask = replace_mask

        landscape_data[fill_mask] = data[indices[0][fill_mask], indices[1][fill_mask]]

    # Nollställ empty-klasser efter replace-fill (override ev. fill-rester).
    if empty_mask.any():
        landscape_data[empty_mask] = 0

    with rasterio.open(out_path, "w", **meta) as dst:
        dst.write(landscape_data, 1)

    if QML_RECLASSIFY.exists():
        shutil.copy2(QML_RECLASSIFY, out_path.with_suffix(".qml"))

    elapsed = time.time() - t0
    return out_path_str, px_replaced, px_emptied, elapsed


def extract_landscape(tile_paths: list[Path]) -> list[Path]:
    """Löser upp DISSOLVE_CLASSES i omgivande mark och skriver till steg_3_dissolve/.

    Returnerar lista med sökvägar i samma ordning som tile_paths.
    """
    t0_step = time.time()
    out_dir = OUT_BASE / "steg_3_dissolve"
    out_dir.mkdir(parents=True, exist_ok=True)

    info.info("Steg 3: Ersätter klasser %s med omgivande mark, tömmer klasser %s (%d workers) ...",
              DISSOLVE_CLASSES, DISSOLVE_EMPTY_CLASSES, N_WORKERS)

    # Frys båda klasslistorna till sorterade tupler — hashbara och picklingbara.
    dissolve_frozen = tuple(sorted(DISSOLVE_CLASSES))
    empty_frozen    = tuple(sorted(DISSOLVE_EMPTY_CLASSES))
    task_args = [
        (str(tile), str(out_dir / tile.name), dissolve_frozen, empty_frozen)
        for tile in tile_paths
    ]

    total_px_replaced = 0
    total_px_emptied  = 0
    result_paths = []

    with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
        for out_path_str, px_replaced, px_emptied, elapsed in executor.map(_dissolve_tile_worker, task_args):
            result_paths.append(Path(out_path_str))
            total_px_replaced += px_replaced
            total_px_emptied  += px_emptied
            if elapsed > 0:
                log.debug("dissolve: %s → %d px ersatta, %d px tömda  %.1fs",
                          Path(out_path_str).name, px_replaced, px_emptied, elapsed)

    _elapsed = time.time() - t0_step
    info.info("Steg 3 klar: %d px ersatta av omgivning, %d px tömda  %.1f min (%.0fs)",
              total_px_replaced, total_px_emptied, _elapsed / 60, _elapsed)

    # Bygg en mosaic-VRT så att steget kan öppnas i QGIS direkt
    out_dir = OUT_BASE / "steg_3_dissolve"
    tifs = sorted(out_dir.glob("*.tif"))
    if tifs:
        vrt_path = out_dir / "_mosaic.vrt"
        subprocess.run(
            ["gdalbuildvrt", str(vrt_path), *[str(t) for t in tifs]],
            capture_output=True,
        )
        log.info("VRT: %s", vrt_path)

    return result_paths


if __name__ == "__main__":
    # Körs direkt (inte som modul via run_all_steps.py).
    # STEP_NUMBER och STEP_NAME sätts normalt av run_all_steps.py så att
    # loggfilen hamnar rätt — vid direktkörning kan de vara None, vilket
    # logging_setup hanterar med ett standardnamn.
    import os
    from logging_setup import setup_logging, log_step_header
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")

    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)

    log_step_header(info, 3, "Lös upp klasser i omgivande mark",
                    str(OUT_BASE / "steg_1_reclassify"),
                    str(OUT_BASE / "steg_3_dissolve"))

    # Läs tiles från Steg 1 — förutsätter att steg 1 redan körts.
    tiles_dir = OUT_BASE / "steg_1_reclassify"
    if not tiles_dir.exists():
        info.error(f"Fel: {tiles_dir} finns ej. Kör Steg 1 först (split_tiles.py)")
        exit(1)

    tile_paths = sorted(tiles_dir.glob("*.tif"))
    info.info(f"Hittade {len(tile_paths)} tiles från Steg 1")

    landscape = extract_landscape(tile_paths)
    info.info(f"Steg 3 klar: {len(landscape)} tiles skapade")
