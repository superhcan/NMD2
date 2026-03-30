"""
steg_4_filter_lakes.py — Steg 4: Ta bort små sjöar och fyll med omgivande mark.

Vattenobjekt under MMU_ISLAND pixlar generaliseras bort. Tomrummen fylls med
närmaste icke-noll-granne (3x3 fönster, fallback 7x7 med majoritetsröstning).

Input:  steg_3_dissolve/*.tif (vägar/bygg upplösta, vatten intakt)
Output: steg_4_filter_lakes/*.tif (små vattenytor borttagna och fyllda)

OBS: Steg 4 körs seriellt (en tile i taget) — algoritmen innehåller en
pixel-för-pixel-loop som inte lämpar sig för multiprocessing utan refaktorering.

Kör: python3 src/steg_4_filter_lakes.py
"""

import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

# QML_RECLASSIFY     — reklassificerad stilfil (samma som steg 1–3 använder)
# OUT_BASE           — rotkatalog för pipeline-körningen
# MMU_ISLAND         — minsta karteringsenhet för vatten i pixlar; komponenter
#                      under detta tröskelvärde tas bort
# COMPRESS           — GeoTIFF-komprimering, t.ex. "deflate"
# ISLAND_FILL_SURROUNDS — set med vattenkoderna som ska filtreras, t.ex. {61, 62}
from config import QML_RECLASSIFY, OUT_BASE, MMU_ISLAND, COMPRESS, ISLAND_FILL_SURROUNDS

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")


def copy_qml(tif_path: Path):
    """Kopiera reklassificerings-QML bredvid TIF-filen så att QGIS laddar rätt palett."""
    if QML_RECLASSIFY.exists():
        shutil.copy2(QML_RECLASSIFY, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def fill_water_islands(tile_paths: list[Path]) -> list[Path]:
    """Tar bort vattenytor < MMU_ISLAND px och fyller tomrummen med omgivande mark.

    Returnerar lista med sökvägar till output-tiles i samma ordning som tile_paths.
    """
    t0_step   = time.time()
    out_dir   = OUT_BASE / "steg_4_filter_lakes"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_paths = []

    info.info("Steg 4: Tar bort små sjöar < %d px (%.2f ha) och fyller med omkringliggande ...",
              MMU_ISLAND, MMU_ISLAND * 100 / 10000)

    for tile in tile_paths:
        out_path = out_dir / tile.name

        # Inkrementell körning: hoppa över redan skapade tiles
        if not out_path.exists():
            t0 = time.time()

            try:
                with rasterio.open(tile) as src:
                    meta = src.meta.copy()
                    data = src.read(1)      # band 1, uint16 pixelkoder

                # Boolesk mask för alla vattenpixlar (ISLAND_FILL_SURROUNDS).
                water_mask = np.isin(data, list(ISLAND_FILL_SURROUNDS))

                if np.sum(water_mask) == 0:
                    # Tile saknar vatten helt — hoppa över all bearbetning.
                    log.debug("Ingen vatten i %s", tile.name)
                    output_data = data.copy()
                else:
                    # ── Steg A: Connected-component labeling ──────────────────
                    # Identifiera sammanhängande vattenpixlar med 4-connectivity
                    # (enbart upp/ner/vänster/höger, inte diagonaler). ndimage.label
                    # numrerar varje komponent med ett unikt heltal 1..num_components.
                    structure = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)
                    labeled_water, num_components = ndimage.label(water_mask, structure=structure)

                    # Räkna antal True-pixlar per komponent (index 0 = bakgrund).
                    component_sizes = ndimage.sum(water_mask, labeled_water, range(num_components + 1))

                    # Vilka komponent-id:n är tillräckligt stora för att behållas?
                    large_components = set(np.where(component_sizes >= MMU_ISLAND)[0])
                    small_count = num_components - len(large_components)

                    log.debug("Komponenter: totalt=%d, stora=>=%dpx:%d, små:%d",
                              num_components, MMU_ISLAND, len(large_components), small_count)

                    # ── Steg B: Ta bort alla vattenpixlar ────────────────────
                    # Sätt hela water_mask till 0; stora sjöar återställs i nästa steg.
                    output_data = np.where(water_mask, 0, data)

                    # ── Steg C: Återställ stora sjöar ────────────────────────
                    # Kom ihåg att comp_id == 0 är bakgrunden — skippa den.
                    for comp_id in large_components:
                        if comp_id != 0:
                            comp_mask = labeled_water == comp_id
                            output_data[comp_mask] = data[comp_mask]

                    # ── Steg D: Fyll tomrummen (nollpixlar från borttagna sjöar) ─
                    # Pixel-för-pixel-fill i två omgångar:
                    #   Omgång 1 (3×3): ta första icke-noll-grannen i 8-riktningar.
                    #   Omgång 2 (7×7 fallback): majoritetsröstning bland icke-noll
                    #     grannar i ett 7×7-fönster — används när sjön är stor nog
                    #     att inga 3×3-grannar är kända ännu (t.ex. i mitten av sjön).
                    zero_mask = output_data == 0
                    for i, j in np.argwhere(zero_mask):
                        # Omgång 1: leta närmaste icke-noll granne i 3×3
                        found = False
                        for di in [-1, 0, 1]:
                            for dj in [-1, 0, 1]:
                                if di == 0 and dj == 0:
                                    continue
                                ni, nj = i + di, j + dj
                                if 0 <= ni < output_data.shape[0] and 0 <= nj < output_data.shape[1]:
                                    if output_data[ni, nj] != 0:
                                        output_data[i, j] = output_data[ni, nj]
                                        found = True
                                        break
                            if found:
                                break

                        # Omgång 2: fallback 7×7 med majoritetsval
                        if not found:
                            neighbors = []
                            for di in range(-3, 4):
                                for dj in range(-3, 4):
                                    ni, nj = i + di, j + dj
                                    if 0 <= ni < output_data.shape[0] and 0 <= nj < output_data.shape[1]:
                                        if output_data[ni, nj] != 0:
                                            neighbors.append(output_data[ni, nj])
                            if neighbors:
                                # Välj det värde som förekommer flest gånger bland grannarna.
                                output_data[i, j] = max(set(neighbors), key=neighbors.count)

                    log.debug("Små sjöar borttagna: %d komponenter", small_count)

                # ── Skriv output-tile ──────────────────────────────────────────
                meta.update(compress=COMPRESS)
                with rasterio.open(out_path, "w", **meta) as dst:
                    dst.write(output_data, 1)

                copy_qml(out_path)

                elapsed = time.time() - t0
                log.debug("Steg 4: %s → klart  %.1fs", tile.name, elapsed)
                info.info("  %-45s  klart  %.1fs", tile.name, elapsed)
                result_paths.append(out_path)

            except Exception as e:
                log.error("Misslyckades för %s: %s", tile.name, str(e))
                info.error("  %-45s  MISSLYCKADES", tile.name)
                raise
        else:
            log.debug("Hoppar %s (finns redan)", tile.name)
            result_paths.append(out_path)

    info.info("Steg 4 klar: %d tiles behandlade  %.1fs",
              len(result_paths), time.time() - t0_step)

    # Bygg en mosaic-VRT så att steget kan öppnas i QGIS direkt
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
    import os
    from logging_setup import setup_logging, log_step_header

    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")

    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)

    log_step_header(info, 4, "Ta bort små sjöar",
                    str(OUT_BASE / "steg_3_dissolve"),
                    str(OUT_BASE / "steg_4_filter_lakes"))

    # Försök läsa tiles från steg 3; om steg 3 hoppades över används steg 1 som fallback.
    # (ENABLE_STEPS[3] = False i config.py → steg_3_dissolve/ skapas aldrig.)
    tiles_dir = OUT_BASE / "steg_3_dissolve"
    if not tiles_dir.exists():
        fallback = OUT_BASE / "steg_1_reclassify"
        if fallback.exists():
            info.info(f"steg_3_dissolve/ saknas – använder steg_1_reclassify/ som indata")
            tiles_dir = fallback
        else:
            info.error(f"Fel: {tiles_dir} finns ej. Kör Steg 1-3 först")
            exit(1)

    tiles = sorted(tiles_dir.glob("*.tif"))
    if not tiles:
        info.error(f"Fel: Inga TIF-filer i {tiles_dir}")
        exit(1)

    info.info(f"Hittade {len(tiles)} tiles från Steg 3")
    fill_water_islands(tiles)
    info.info("Steg 4 klart: %d tiles behandlade", len(tiles))
