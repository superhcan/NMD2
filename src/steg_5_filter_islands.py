"""
steg_5_filter_islands.py — Steg 5: Fyll små öar omringade av vatten.

En "ö" definieras som ett sammanhängande landområde (klass ≠ 61, 62) vars
samtliga ortogonala grannar (4-connectivity) är vatten (61, 62). Öar under
MMU_ISLAND pixlar ersätts med den dominerande vattenklassen bland grannarna.

Steg 5 körs efter steg 3 eller 4 för att rensa upp små öar i
sjöar innan generaliseringen i steg 6-8.

Input:  steg_4_filter_lakes/*.tif  — om steg 4 körts (ENABLE_STEPS[4] = True)
        steg_3_dissolve/*.tif     — fallback om steg 4 hoppades över
Output: steg_5_filter_islands/*.tif (landöar < MMU_ISLAND borttagna)

Varje tile får en kopia av .qml-filen så att QGIS laddar paletten automatiskt.

Kör: python3 src/steg_5_filter_islands.py
"""

import logging
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window
from scipy import ndimage

# QML_RECLASSIFY        — reklassificerad stilfil (samma som steg 1–4 använder)
# OUT_BASE              — rotkatalog för pipeline-körningen
# MMU_ISLAND            — minsta karteringsenhet i pixlar; öar under detta tas bort
# ISLAND_FILL_SURROUNDS — set med vattenkoder som definierar "omgivande vatten", t.ex. {61, 62}
# STRUCT_4              — 3×3 strukturelement för 4-connectivity (kors-form, inga diagonaler)
# COMPRESS              — GeoTIFF-komprimering, t.ex. "deflate"
from config import QML_RECLASSIFY, OUT_BASE, MMU_ISLAND, ISLAND_FILL_SURROUNDS, STRUCT_4, COMPRESS, HALO

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")

def copy_qml(tif_path: Path):
    """Kopiera reklassificerings-QML bredvid TIF-filen så att QGIS laddar rätt palett."""
    if QML_RECLASSIFY.exists():
        shutil.copy2(QML_RECLASSIFY, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def fill_small_islands(data: np.ndarray, water_classes: set, mmu: int) -> tuple[np.ndarray, int]:
    """Fyller öar < mmu px som är helt omringade av vatten.

    Returnerar (modifierad array, antal fyllda öar).

    Optimering: ndimage.find_objects ger ett bounding box per komponent.
    binary_dilation körs sedan på det lilla bounding boxet (~7×7 px) i stället
    för hela 1024×1024-arrayen — ger ~40 000× snabbare dilation per komponent
    vid MMU=50.
    """
    data_out = data.copy()
    water_list = list(water_classes)

    # Boolesk mask: True = landpixel (allt som inte är vatten).
    water = np.isin(data_out, water_list)
    land = ~water

    # Etikettera sammanhängande landkomponenter med 4-connectivity.
    # labeled[i,j] == k betyder att pixeln tillhör komponent k (1-indexerat).
    # n_comp = totalt antal distinkta landkomponenter i tilen.
    labeled, n_comp = ndimage.label(land, structure=STRUCT_4)
    log.debug("fill_small_islands: %d landkomponenter hittade", n_comp)
    if n_comp == 0:
        return data_out, 0

    # Räkna storleken på alla komponenter i ett enda O(N)-pass.
    # ndimage.sum(land, labeled, ids) summerar land-pixlarna per komponent-id.
    comp_ids = np.arange(1, n_comp + 1)
    sizes = np.array(ndimage.sum(land, labeled, comp_ids))

    # Bara komponenter under MMU-tröskeln är kandidater för borttagning.
    small_ids = comp_ids[sizes < mmu]

    if len(small_ids) == 0:
        return data_out, 0

    # ndimage.find_objects returnerar en lista med slice-par (rad-slice, kol-slice)
    # för varje komponent (index 0 = komponent 1). O(N) svep.
    objects = ndimage.find_objects(labeled)
    h, w = data.shape
    filled = 0
    skipped_land = 0

    for comp_id in small_ids:
        sl = objects[comp_id - 1]
        if sl is None:
            continue

        # Expandera bounding boxet med 1 px i alla riktningar för att inkludera
        # grannpixlarna utanför komponenten (behövs för ring-detektion nedan).
        r0 = max(0, sl[0].start - 1); r1 = min(h, sl[0].stop + 1)
        c0 = max(0, sl[1].start - 1); c1 = min(w, sl[1].stop + 1)

        # Jobba på den lilla submatrisen istället för hela tilen.
        sub_labeled = labeled[r0:r1, c0:c1]
        sub_data    = data_out[r0:r1, c0:c1]

        # Mask för just den här komponenten inom sub-matrisen.
        local_mask    = (sub_labeled == comp_id)
        # binary_dilation expanderar masken ett steg i varje riktning (upp/ner/vänster/höger).
        # Resultatet = komponenten + dess direkta 4-grannar.
        local_dilated = ndimage.binary_dilation(local_mask, structure=STRUCT_4)
        # "Ringen" = grannpixlarna runt komponenten (den expanderade masken minus komponenten själv).
        local_ring    = local_dilated & ~local_mask

        neighbors = sub_data[local_ring]

        # Krav: ALLA grannar måste vara vatten — annars är det inte en full isolerad ö.
        if not np.all(np.isin(neighbors, water_list)):
            skipped_land += 1
            continue

        # Dominant vattenklass = den vattenkod som förekommer flest gånger i ringen.
        vals, counts = np.unique(neighbors, return_counts=True)
        fill_val = int(vals[counts.argmax()])

        # Skriv fill-värdet tillbaka till alla pixlar i komponenten.
        local_rows, local_cols = np.where(local_mask)
        data_out[r0 + local_rows, c0 + local_cols] = fill_val
        filled += 1

    log.debug("fill_small_islands klar: %d öar fyllda, %d delvis omringade hoppades",
              filled, skipped_land)
    return data_out, filled


def fill_islands(tile_paths: list[Path]) -> list[Path]:
    """Fyller öar < MMU_ISLAND px omringade av vatten i alla tiles.

    Ett VRT byggs av alla input-tiles, och varje tile läses med 1 px
    halo från angränsande tiles. Det eliminerar edge-artefakter vid
    tilekanter (öar som sträcker sig över gränsen detekteras korrekt).

    Returnerar lista med sökvägar till output-tiles i samma ordning som tile_paths.
    """
    t0_step = time.time()
    out_dir = OUT_BASE / "steg_5_filter_islands"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_paths = []
    total_islands = 0

    info.info("Steg 5: Fyller små öar < %d px (%.2f ha) omringade av %s ...",
              MMU_ISLAND, MMU_ISLAND * 100 / 10000, sorted(ISLAND_FILL_SURROUNDS))

    # Bygg ett VRT av alla input-tiles så att halo-läsning kan spänna
    # över tilekanter (öar längs kanterna detekteras korrekt).
    # HALO (från config) är >= MMU_ISLAND — garanterar att en ö som sträcker
    # sig över tilekanten syns i sin fulla storlek innan storlekskontroll.
    vrt_in = out_dir / "_input_mosaic.vrt"
    subprocess.run(
        ["gdalbuildvrt", str(vrt_in), *[str(p) for p in tile_paths]],
        capture_output=True, check=True,
    )
    log.debug("Input VRT: %s", vrt_in)

    for tile in tile_paths:
        out_path = out_dir / tile.name

        # Inkrementell körning: hoppa över redan skapade tiles.
        if not out_path.exists():
            t0 = time.time()

            # Läs tile + HALO px kant från VRT
            with rasterio.open(vrt_in) as vrt, rasterio.open(tile) as src:
                vt = vrt.transform
                tt = src.transform
                px = vt.a
                py = vt.e

                tile_col = round((tt.c - vt.c) / px)
                tile_row = round((tt.f - vt.f) / py)
                tile_w   = src.width
                tile_h   = src.height
                profile  = src.meta.copy()

                x0 = max(0, tile_col - HALO)
                y0 = max(0, tile_row - HALO)
                x1 = min(vrt.width,  tile_col + tile_w + HALO)
                y1 = min(vrt.height, tile_row + tile_h + HALO)

                padded = vrt.read(1, window=Window(x0, y0, x1 - x0, y1 - y0))

            inner_row = tile_row - y0
            inner_col = tile_col - x0
            inner = (
                slice(inner_row, inner_row + tile_h),
                slice(inner_col, inner_col + tile_w),
            )

            log.debug("fill_islands: bearbetar %s (padded %s, inner %s)",
                      tile.name, padded.shape, (tile_h, tile_w))
            filled_padded, n_islands = fill_small_islands(
                padded, ISLAND_FILL_SURROUNDS, MMU_ISLAND)

            # Kärnan ur det fyllda padded-lagret
            filled_data = filled_padded[inner]
            data_orig   = padded[inner]  # original kärna för px_changed

            profile.update(compress=COMPRESS)
            with rasterio.open(out_path, 'w', **profile) as dst:
                dst.write(filled_data, 1)
            copy_qml(out_path)

            px_changed = int(np.sum(filled_data != data_orig))
            elapsed = time.time() - t0
            total_islands += n_islands

            log.debug("fill_islands: %s → %d öar fyllda (%d px)  %.1fs",
                      tile.name, n_islands, px_changed, elapsed)
            info.info("  %-45s  %3d öar fyllda  %6d px ändrade  %.1fs",
                      tile.name, n_islands, px_changed, elapsed)
        else:
            log.debug("fill_islands: hoppar %s (finns redan)", tile.name)

        result_paths.append(out_path)

    _elapsed = time.time() - t0_step
    info.info("Steg 5 klart: totalt %d öar fyllda  %.1f min (%.0fs)",
              total_islands, _elapsed / 60, _elapsed)

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
    from logging_setup import setup_logging, log_step_header
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")

    import os
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)

    log_step_header(info, 5, "Fyller små öar",
                    str(OUT_BASE / "steg_4_filter_lakes"),
                    str(OUT_BASE / "steg_5_filter_islands"))

    # Läs tiles från steg 4. Om steg 4 hoppades över (ENABLE_STEPS[4] = False)
    # faller vi tillbaka till steg 3. Prioritetsordning: steg4 > steg3.
    filled_dir = OUT_BASE / "steg_4_filter_lakes"
    if not filled_dir.exists():
        filled_dir = OUT_BASE / "steg_3_dissolve"
    if not filled_dir.exists():
        info.error(f"Fel: varken steg_4_filter_lakes/ eller steg_3_dissolve/ finns. Kör Steg 3+ först")
        exit(1)

    tile_paths = sorted(filled_dir.glob("*.tif"))
    info.info(f"Hittade {len(tile_paths)} tiles från Steg 4")

    result_paths = fill_islands(tile_paths)
    info.info(f"Steg 5 klart: {len(result_paths)} tiles bearbetade")
