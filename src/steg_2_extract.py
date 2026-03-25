"""
steg_2_extract.py — Steg 2: Extrahera skyddade klasser till separat lager.

Klasser som vägar och byggnader (EXTRACT_CLASSES) ska INTE generaliseras i
steg 6-8. De sparas undan här och läggs ev tillbaka ovanpå det generaliserade
resultatet i steg 9 (overlay).

Input:  steg_1_reclassify/*.tif (omklassificerade tiles)
Output: steg_2_extract/*.tif (enbart EXTRACT_CLASSES, övriga pixlar = 0)

Varje tile får en kopia av .qml-filen så att QGIS laddar paletten automatiskt.

Kör: python3 src/steg_2_extract.py
"""

import logging
import os
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import rasterio

# QML_RECLASSIFY — reklassificerad stilfil (samma som steg 1 använder)
# OUT_BASE       — rotkatalog för all pipeline-output
# EXTRACT_CLASSES — mängd med klasskoder att bevara, t.ex. {51, 53, 61, 62}
# COMPRESS        — GeoTIFF-komprimering, t.ex. "lzw"
from config import QML_RECLASSIFY, OUT_BASE, EXTRACT_CLASSES, COMPRESS

# Antal parallella processer: alla kärnor minus 2 (för OS och I/O)
N_WORKERS = max(1, (os.cpu_count() or 1) - 2)

# Två loggers: debug-logg (detaljerad per tile) och summary-logg (stegsummeringar)
log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")


def copy_qml(tif_path: Path):
    """Kopiera reklassificerings-QML bredvid TIF-filen så att QGIS laddar rätt palett."""
    if QML_RECLASSIFY.exists():
        shutil.copy2(QML_RECLASSIFY, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def _extract_tile_worker(args):
    """Top-level worker för ProcessPoolExecutor.

    Måste vara en top-level-funktion (inte lambda eller nästlad) för att
    kunna serialiseras med pickle mellan processer.
    """
    tile_str, out_path_str, extract_classes_frozen = args
    tile = Path(tile_str)
    out_path = Path(out_path_str)

    # Inkrementell körning: hoppa över redan skapade tiles
    if out_path.exists():
        return out_path_str, 0, 0.0

    t0 = time.time()

    # Konvertera frozen tuple → numpy-array för np.isin
    extract_set = np.array(list(extract_classes_frozen), dtype=np.uint16)

    with rasterio.open(tile) as src:
        meta = src.meta.copy()
        data = src.read(1)      # Band 1: klassvärden (uint16)
    meta.update(compress=COMPRESS)

    # mask=True där pixeln tillhör EXTRACT_CLASSES, annars False
    mask = np.isin(data, extract_set)

    # Behåll originalvärde för extraherade pixlar, sätt övriga till 0
    protected_data = np.where(mask, data, np.uint16(0)).astype(data.dtype)
    n_px = int(np.count_nonzero(protected_data))

    with rasterio.open(out_path, "w", **meta) as dst:
        dst.write(protected_data, 1)

    # Kopiera QML-stilfil för korrekt visualisering i QGIS
    if QML_RECLASSIFY.exists():
        shutil.copy2(QML_RECLASSIFY, out_path.with_suffix(".qml"))

    elapsed = time.time() - t0
    return out_path_str, n_px, elapsed


def extract_protected_classes(tile_paths: list[Path]) -> list[Path]:
    """Extraherar EXTRACT_CLASSES från alla tiles parallellt till steg_2_extract/.

    Returnerar lista med sökvägar i samma ordning som tile_paths.
    """
    t0_step = time.time()
    out_dir = OUT_BASE / "steg_2_extract"
    out_dir.mkdir(parents=True, exist_ok=True)

    info.info("Steg 2: Extracting classes %s from original tiles (%d workers)...",
              sorted(EXTRACT_CLASSES), N_WORKERS)

    # Frys till tuple för pickle-säker överföring till worker-processer
    extract_frozen = tuple(sorted(EXTRACT_CLASSES))
    task_args = [
        (str(tile), str(out_dir / tile.name), extract_frozen)
        for tile in tile_paths
    ]

    total_px_extracted = 0
    result_paths = []

    # Kör alla tiles parallellt; executor.map ger resultat i inleveransordning
    with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
        for out_path_str, n_px, elapsed in executor.map(_extract_tile_worker, task_args):
            result_paths.append(Path(out_path_str))
            total_px_extracted += n_px
            if elapsed > 0:
                log.debug("extract: %s → %d px  %.1fs",
                          Path(out_path_str).name, n_px, elapsed)

    _elapsed = time.time() - t0_step
    info.info("Steg 2 klart: totalt %d px extracted  %.1f min (%.0fs)",
              total_px_extracted, _elapsed / 60, _elapsed)

    return result_paths


if __name__ == "__main__":
    import os
    from logging_setup import setup_logging, log_step_header
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")

    # Steg-nummer och namn sätts av run_all_steps.py via miljövariabler
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)

    log_step_header(info, 2, "Extract classes",
                    str(OUT_BASE / "steg_1_reclassify"),
                    str(OUT_BASE / "steg_2_extract"))

    # Läs tiles från Steg 1
    tiles_dir = OUT_BASE / "steg_1_reclassify"
    if not tiles_dir.exists():
        info.error(f"Fel: {tiles_dir} finns ej. Kör Steg 1 först (steg_1_reclassify.py)")
        exit(1)

    tile_paths = sorted(tiles_dir.glob("*.tif"))
    info.info(f"Hittade {len(tile_paths)} tiles från Steg 1")
    
    protected = extract_protected_classes(tile_paths)
    info.info(f"Steg 2 klart: {len(protected)} tiles skapade")
