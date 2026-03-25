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

log = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")

N_WORKERS = max(1, (os.cpu_count() or 1) - 2)

# Bygg en uint16-LUT (65536 poster) för O(N) vektoriserad omklassificering.
# lut[gammalkod] = nykod. Allt som inte finns i CLASS_REMAP förblir oförändrat.
_LUT = np.arange(65536, dtype=np.uint16)
for _old, _new in CLASS_REMAP.items():
    _LUT[_old] = _new if _new is not None else 0

# ──────────────────────────────────────────────────────────────────────────────

STEG0_DIR = OUT_BASE / "steg_0_verify_tiles"
OUT_DIR   = OUT_BASE / "steg_1_reclassify"


def _remap_worker(args):
    """Top-level worker för ProcessPoolExecutor."""
    src_str, out_str = args
    src = Path(src_str)
    out = Path(out_str)

    if out.exists():
        return out_str, 0.0

    t0 = time.time()
    with rasterio.open(src) as f:
        meta = f.meta.copy()
        data = f.read(1)
    meta.update(compress=COMPRESS)

    # Vektoriserad LUT-uppslag: en enda numpy-indexering istället för
    # N separata np.where-anrop (ett per kod i CLASS_REMAP).
    remapped = _LUT[data.astype(np.uint16)]

    with rasterio.open(out, "w", **meta) as f:
        f.write(remapped, 1)

    if QML_SRC.exists():
        shutil.copy2(QML_SRC, out.with_suffix(".qml"))

    return out_str, time.time() - t0


def process_tiles():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not STEG0_DIR.exists():
        print(f"FEL: {STEG0_DIR} saknas — kör steg 0 först.")
        sys.exit(1)

    src_tiles = sorted(
        p for p in STEG0_DIR.glob("*.tif")
        if "_original_class" not in p.name
    )
    total = len(src_tiles)

    if total == 0:
        print(f"FEL: Inga tiles hittades i {STEG0_DIR} — kör steg 0 först.")
        sys.exit(1)

    print(f"Källmapp : {STEG0_DIR}")
    print(f"Tiles    : {total} st")
    print(f"Utmapp   : {OUT_DIR}")
    print(f"Workers  : {N_WORKERS}\n")

    t_start = time.time()
    task_args = [(str(t), str(OUT_DIR / t.name)) for t in src_tiles]

    done = 0
    with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
        for _out_str, elapsed in executor.map(_remap_worker, task_args):
            done += 1
            if done % 50 == 0 or done == total:
                pct = done / total * 100
                print(f"  {done}/{total} ({pct:.0f}%)", flush=True)

    total_elapsed = time.time() - t_start
    print(f"\nKlart! ({total_elapsed:.1f}s)")
    print(f"Tiles sparade i: {OUT_DIR}")
    return total_elapsed


# Anropas direkt av run_all_steps.py via subprocess
elapsed = process_tiles()


if __name__ == "__main__":
    from logging_setup import setup_logging, log_step_header
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")

    log_step_header(info, 1, "Tileluppdelning",
                    str(STEG0_DIR),
                    str(OUT_DIR))

    info.info("Steg 1 klart: %d tiles skapade  %.1f min (%.0fs)",
              len(list(OUT_DIR.glob("*.tif"))), elapsed / 60, elapsed)
