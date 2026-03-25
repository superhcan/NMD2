"""
steg_1_reclassify.py — Steg 1: Omklassificering av tiles från steg 0.

Läser redan uppdelade tiles från steg0_verify_tiles/ och applicerar
CLASS_REMAP för omklassificering från NMD-koder till slutklasser.

Input:  steg0_verify_tiles/*.tif (original NMD-koder, uppdelade av steg 0)
Output: steg1_tiles/*.tif (omklassificerade tiles)

Namnkonvention: NMD2023bas_tile_r{rad:03d}_c{kol:03d}.tif
Varje tile får en kopia av .qml-filen så att QGIS hittar paletten automatiskt.

Kör: python3 steg_1_reclassify.py
"""

import logging
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import rasterio

from config import QML_SRC, OUT_BASE, COMPRESS, CLASS_REMAP

# QML-fil som stämmer med de reklassificerade koderna.
# Genereras av generate_reclassify_qml.py; faller tillbaka på original-QML om den saknas.
_RECLASSIFY_QML = Path(__file__).parent / "steg_1_reclassify.qml"
QML_RECLASSIFY = _RECLASSIFY_QML if _RECLASSIFY_QML.exists() else QML_SRC

# Två separata loggers: 'debug' för detaljerade meddelanden, 'summary' för pipeline-översikten
log = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")

# Reservera 2 kärnor för OS och övriga processer; minst 1 worker alltid
N_WORKERS = max(1, (os.cpu_count() or 1) - 2)

# Bygg en uint16-LUT (65536 poster) för O(N) vektoriserad omklassificering.
# lut[gammalkod] = nykod. Allt som inte finns i CLASS_REMAP förblir oförändrat.
# uint16 täcker NMD-kodrymd 0–65535; arange initierar identitetsmappning
# så att koder utan explicit regel kopieras oförändrade.
_LUT = np.arange(65536, dtype=np.uint16)
for _old, _new in CLASS_REMAP.items():
    # None i CLASS_REMAP tolkas som "ta bort" → mappas till 0 (NoData)
    _LUT[_old] = _new if _new is not None else 0

# ──────────────────────────────────────────────────────────────────────────────

# Indatamapp: output från steg 0 (original NMD-koder, ej omklassificerade)
STEG0_DIR = OUT_BASE / "steg_0_verify_tiles"
# Utdatamapp: omklassificerade tiles som följande steg konsumerar
OUT_DIR   = OUT_BASE / "steg_1_reclassify"


def _remap_worker(args):
    """Top-level worker för ProcessPoolExecutor.

    Måste vara en top-level-funktion (inte lambda eller nästlad) för att
    kunna serialiseras med pickle och skickas till worker-processer.
    Tar ett enda argument-tuple för att vara kompatibel med executor.map.
    """
    src_str, out_str = args
    src = Path(src_str)
    out = Path(out_str)

    # Stöd för återupptagen körning: hoppa över tiles som redan är klara.
    if out.exists():
        return out_str, 0.0

    t0 = time.time()

    # Läs källtile och dess metadata; meta används för att skriva output med samma projektion
    with rasterio.open(src) as f:
        meta = f.meta.copy()
        # Läs band 1 – NMD har ett enda klassificeringsband
        data = f.read(1)

    # Uppdatera komprimeringsalgoritm enligt pipeline-konfigurationen (t.ex. DEFLATE)
    meta.update(compress=COMPRESS)

    # Vektoriserad LUT-uppslag: en enda numpy-indexering istället för
    # N separata np.where-anrop (ett per kod i CLASS_REMAP).
    # Cast till uint16 krävs för att indexera LUT korrekt oavsett källans dtype.
    remapped = _LUT[data.astype(np.uint16)]

    # Skriv omklassificerad tile; metadata (projektion, nodata m.m.) ärvs från källan
    with rasterio.open(out, "w", **meta) as f:
        f.write(remapped, 1)

    # Kopiera QML-stilfil (reklassificeringspalett) så att QGIS laddar rätt färger automatiskt
    if QML_RECLASSIFY.exists():
        shutil.copy2(QML_RECLASSIFY, out.with_suffix(".qml"))

    return out_str, time.time() - t0


def process_tiles():
    """Omklassificerar alla tiles från steg 0 med CLASS_REMAP-LUT.

    Returnerar total körtid i sekunder.
    """
    # Säkerställ att utmappen finns innan worker-processer startar
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Avbryt tidigt om steg 0 inte körts – ger tydligt felmeddelande
    if not STEG0_DIR.exists():
        print(f"FEL: {STEG0_DIR} saknas — kör steg 0 först.")
        sys.exit(1)

    # Filtrera bort eventuella _original_class-filer som steg 0 kan ha skapat
    # vid verifiering; dessa ska inte omklassificeras
    src_tiles = sorted(
        p for p in STEG0_DIR.glob("*.tif")
        if "_original_class" not in p.name
    )
    total = len(src_tiles)

    if total == 0:
        print(f"FEL: Inga tiles hittades i {STEG0_DIR} — kör steg 0 först.")
        sys.exit(1)

    # Kompakt statusutskrift läsbar i terminal och loggfil
    print(f"Källmapp : {STEG0_DIR}")
    print(f"Tiles    : {total} st")
    print(f"Utmapp   : {OUT_DIR}")
    print(f"Workers  : {N_WORKERS}\n")

    t_start = time.time()

    # Argument-tupler med strängar (inte Path-objekt) så att pickle kan serialisera dem
    task_args = [(str(t), str(OUT_DIR / t.name)) for t in src_tiles]

    done = 0
    with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
        # executor.map skickar tasks till workers och returnerar resultat i inskickad ordning
        for _out_str, elapsed in executor.map(_remap_worker, task_args):
            done += 1
            # Skriv progress var 50:e tile samt på sista tile
            if done % 50 == 0 or done == total:
                pct = done / total * 100
                print(f"  {done}/{total} ({pct:.0f}%)", flush=True)

    total_elapsed = time.time() - t_start
    print(f"\nKlart! ({total_elapsed:.1f}s)")
    print(f"Tiles sparade i: {OUT_DIR}")
    return total_elapsed


# Körs direkt när skriptet anropas av run_all_steps.py (utanför __main__-blocket)
elapsed = process_tiles()


if __name__ == "__main__":
    # Blocket körs enbart vid direkt anrop: python3 steg_1_reclassify.py
    # run_all_steps.py kör skriptet via exec() och når inte hit
    from logging_setup import setup_logging, log_step_header

    # Steg- och namninformation injiceras av run_all_steps.py via miljövariabler
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")

    # Initialisera fil- och konsol-loggning för detta steg
    setup_logging(OUT_BASE, step_num, step_name)
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")

    # Skriv tydlig rubrik i loggfilen med käll- och utdata-sökvägar
    log_step_header(info, 1, "Omklassificering av tiles",
                    str(STEG0_DIR),
                    str(OUT_DIR))

    # Summera resultatet: antal genererade .tif-filer och total körtid
    info.info("Steg 1 klart: %d tiles skapade  %.1f min (%.0fs)",
              len(list(OUT_DIR.glob("*.tif"))), elapsed / 60, elapsed)
