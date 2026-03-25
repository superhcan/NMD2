"""
steg_0_verify_tiles.py — Steg 0: Verifikation - Tileluppdelning utan omklassificering.

Delar original-raster (NMD2023bas_v2_0.tif) i 1024x1024 px tiles
UTAN att applicera någon omklassificering. Används för verifikation
av originaldata innan produktions-omklassificering i steg 1.

Output:
  - NMD2023bas_tile_r{rad:03d}_c{kol:03d}.tif (original NMD-koder, ingen ändring)

Namnkonvention: NMD2023bas_tile_r{rad:03d}_c{kol:03d}.tif
Varje tile får en kopia av .qml-filen så att QGIS läser in paletten automatiskt.

Kör: python3 steg_0_verify_tiles.py
"""

import logging
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import rasterio

from config import SRC, QML_SRC, OUT_BASE, COMPRESS, TILE_SIZE, PARENT_TILES

# Två separata loggers: 'debug' för detaljerade meddelanden, 'summary' för pipeline-översikten
log = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")

# Reservera 2 kärnor för OS och övriga processer; minst 1 worker alltid
N_WORKERS = max(1, (os.cpu_count() or 1) - 2)

# ──────────────────────────────────────────────────────────────────────────────

# Utmapp för detta steg – skapas automatiskt av process_tiles() om den saknas
OUT_DIR = OUT_BASE / "steg_0_verify_tiles"


def _tile_worker(args):
    """Top-level worker för ProcessPoolExecutor.

    Måste vara en top-level-funktion (inte lambda eller nästlad) för att
    kunna serialiseras med pickle mellan processer.
    """
    src_str, out_str, row, col, tile_size, src_width, src_height, meta_dict, compress, qml_str = args
    out = Path(out_str)

    # Hoppa över redan genererade tiles för att stödja återupptagen körning
    if out.exists():
        return out_str, 0.0

    t0 = time.time()

    # Beräkna pixeloffset för denna tile i källrastern
    x_off = col * tile_size
    y_off = row * tile_size

    # Klipp bredden/höjden vid rasterets kant så att kanttilesarna inte blir för stora
    w = min(tile_size, src_width  - x_off)
    h = min(tile_size, src_height - y_off)

    # rasterio.windows.Window(col_off, row_off, width, height)
    window = rasterio.windows.Window(x_off, y_off, w, h)

    with rasterio.open(src_str) as src:
        # Beräkna georeferensen (transform) specifik för detta fönster
        transform = src.window_transform(window)
        # Läs endast band 1 – NMD har ett enda klassificeringsband
        tile_data = src.read(1, window=window)
        dtype = src.dtypes[0]

    # Kopiera källans metadata och uppdatera dimensioner för den aktuella tile:n
    tile_meta = dict(meta_dict)
    tile_meta.update(width=w, height=h, transform=transform, compress=compress)

    # Skriv tile till disk; dtype-cast säkerställer att datatypen matchar metadata
    with rasterio.open(out, "w", **tile_meta) as dst:
        dst.write(tile_data.astype(dtype), 1)

    # Kopiera QML-stilfil bredvid .tif-filen så att QGIS laddar paletten automatiskt
    qml = Path(qml_str)
    if qml.exists():
        shutil.copy2(qml, out.with_suffix(".qml"))

    return out_str, time.time() - t0


def process_tiles():
    """Delar upp NMD-källrastern i tiles utan omklassificering.

    Returnerar total körtid i sekunder.
    """
    # Säkerställ att utmappen finns innan worker-processer startar
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    total = len(PARENT_TILES)

    # Kompakt statusutskrift som är läsbar i terminalen och i loggfiler
    print(f"Källbild : {SRC.name}")
    print(f"Tile-size: {TILE_SIZE} × {TILE_SIZE} px")
    print(f"Tiles    : {total} st (PARENT_TILES)")
    print(f"Utmapp   : {OUT_DIR}")
    print(f"Workers  : {N_WORKERS}")
    print(f"Klassif. : INGEN omklassificering (verifikation av original)\n")

    # Läs metadata EN gång i main-tråden – undviker att varje worker öppnar filen
    with rasterio.open(SRC) as src:
        meta = dict(src.meta)
        src_width  = src.width
        src_height = src.height

    # Bygg en lista med alla argument-tupler; en tuple per tile
    # Allt skickas som primitiva typer så att pickle kan serialisera dem till worker-processer
    task_args = [
        (
            str(SRC),
            str(OUT_DIR / f"NMD2023bas_tile_r{row:03d}_c{col:03d}.tif"),
            row, col, TILE_SIZE, src_width, src_height,
            meta, COMPRESS, str(QML_SRC)
        )
        for row, col in PARENT_TILES
    ]

    t_start = time.time()
    done = 0
    with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
        # executor.map bevarar ordning men returnerar resultat i takt med att de är klara
        for _out_str, elapsed in executor.map(_tile_worker, task_args):
            done += 1
            # Skriv ut progress var 50:e tile samt på sista tile
            if done % 50 == 0 or done == total:
                pct = done / total * 100
                print(f"  {done}/{total} ({pct:.0f}%)", flush=True)

    total_elapsed = time.time() - t_start
    print(f"\nKlart! ({total_elapsed:.1f}s)")
    print(f"Tiles sparade i: {OUT_DIR}")
    print(f"Dessa tiles innehåller ORIGINAL NMD-koder (ingen omklassificering)")
    return total_elapsed


# Körs direkt när skriptet anropas av run_all_steps.py (utanför __main__-blocket)
elapsed = process_tiles()


if __name__ == "__main__":
    # Blocket körs enbart vid direkt anrop: python3 steg_0_verify_tiles.py
    # run_all_steps.py kör skriptet via exec() och når inte hit
    from logging_setup import setup_logging, log_step_header

    # Steg- och namninformation injiceras av run_all_steps.py via miljövariabler
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")

    # Initialisera fil- och konsol-loggning för detta steg
    setup_logging(OUT_BASE, step_num, step_name)
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")

    # Skriv en tydlig rubrik i loggfilen med käll- och utdata-sökvägar
    log_step_header(info, 0, "Verifikation - Tileluppdelning (original)",
                    str(SRC),
                    str(OUT_DIR))

    # Summera resultatet: antal genererade .tif-filer och total körtid
    info.info("Steg 0 klart: %d tiles skapade  %.1f min (%.0fs)",
              len(list(OUT_DIR.glob("*.tif"))), elapsed / 60, elapsed)
