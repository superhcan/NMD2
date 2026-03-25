"""
steg_5_filter_islands.py — Steg 5: Fyller små öar < MMU_ISLAND px omringade av vatten.

En "ö" är ett sammanhängande landområde (klass ≠ 61, 62) vars samtliga grannar
(ortogonalt, konnektivitet 4) är vatten (61, 62). Ersätts med dominant vattenklass.

Körs efter steg 4 (filled/) för att rensa upp små öar i sjöar innan generalisering.

Kör: python3 src/steg_5_filter_islands.py
"""

import logging
import shutil
import time
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

from config import QML_RECLASSIFY, OUT_BASE, MMU_ISLAND, ISLAND_FILL_SURROUNDS, STRUCT_4, COMPRESS

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")

def copy_qml(tif_path: Path):
    """Kopiera referens-QML-fil till TIF-filen."""
    if QML_RECLASSIFY.exists():
        shutil.copy2(QML_RECLASSIFY, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def fill_small_islands(data: np.ndarray, water_classes: set, mmu: int) -> tuple[np.ndarray, int]:
    """Fyll öar < mmu px som är helt omringade av vatten.

    Optimerad: använder ndimage.find_objects för att dilation ska köras på ett
    litet bounding box per komponent (t.ex. 7×7 px) istället för hela 1024×1024-
    arrayen. Ger ~40 000× snabbare dilation per komponent vid MMU=50.
    """
    data_out = data.copy()
    water_list = list(water_classes)
    water = np.isin(data_out, water_list)
    land = ~water

    labeled, n_comp = ndimage.label(land, structure=STRUCT_4)
    log.debug("fill_small_islands: %d landkomponenter hittade", n_comp)
    if n_comp == 0:
        return data_out, 0

    # Hämta alla komponentstorlekar på en gång (undviker np.sum per komponent)
    comp_ids = np.arange(1, n_comp + 1)
    sizes = np.array(ndimage.sum(land, labeled, comp_ids))
    small_ids = comp_ids[sizes < mmu]

    if len(small_ids) == 0:
        return data_out, 0

    # Bounding box för varje komponent — en enda O(n)-svep över labeled
    objects = ndimage.find_objects(labeled)
    h, w = data.shape
    filled = 0
    skipped_land = 0

    for comp_id in small_ids:
        sl = objects[comp_id - 1]
        if sl is None:
            continue

        # Expandera bounding box med 1 px för att fånga grannpixlar
        r0 = max(0, sl[0].start - 1); r1 = min(h, sl[0].stop + 1)
        c0 = max(0, sl[1].start - 1); c1 = min(w, sl[1].stop + 1)

        sub_labeled = labeled[r0:r1, c0:c1]
        sub_data    = data_out[r0:r1, c0:c1]

        local_mask    = (sub_labeled == comp_id)
        local_dilated = ndimage.binary_dilation(local_mask, structure=STRUCT_4)
        local_ring    = local_dilated & ~local_mask

        neighbors = sub_data[local_ring]

        # Kolla om ALLA grannar är vatten
        if not np.all(np.isin(neighbors, water_list)):
            skipped_land += 1
            continue

        # Hitta dominant vattenklass bland grannar
        vals, counts = np.unique(neighbors, return_counts=True)
        fill_val = int(vals[counts.argmax()])

        local_rows, local_cols = np.where(local_mask)
        data_out[r0 + local_rows, c0 + local_cols] = fill_val
        filled += 1

    log.debug("fill_small_islands klar: %d öar fyllda, %d delvis omringade hoppades",
              filled, skipped_land)
    return data_out, filled


def fill_islands(tile_paths: list[Path]) -> list[Path]:
    """Fyller öar < MMU_ISLAND px omringade av vatten i alla tiles."""
    t0_step = time.time()
    out_dir = OUT_BASE / "steg_5_filter_islands"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_paths = []
    total_islands = 0
    
    info.info("Steg 5: Fyller små öar < %d px (%.2f ha) omringade av %s ...",
              MMU_ISLAND, MMU_ISLAND * 100 / 10000, sorted(ISLAND_FILL_SURROUNDS))
    
    for tile in tile_paths:
        out_path = out_dir / tile.name
        if not out_path.exists():
            t0 = time.time()
            
            with rasterio.open(tile) as src:
                data = src.read(1)
                profile = src.profile
            
            log.debug("fill_islands: bearbetar %s", tile.name)
            filled_data, n_islands = fill_small_islands(data, ISLAND_FILL_SURROUNDS, MMU_ISLAND)
            
            profile.update(compress=COMPRESS)
            with rasterio.open(out_path, 'w', **profile) as dst:
                dst.write(filled_data, 1)
            copy_qml(out_path)
            
            px_changed = int(np.sum(filled_data != data))
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
    
    # Läs tiles från Steg 4, fallback till steg3_dissolved om steg 4 är inaktiverat
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
