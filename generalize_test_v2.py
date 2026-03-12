"""
generalize_test_v2.py — Kumulativ MMU-generalisering med skyddade klasser.

Skyddade klasser (53=väg, 61=sjö, 62=vatten) maskeras som nodata innan gdal_sieve
kör, och återställs efteråt. Konnektivitet: 4 (jämnare kanter).

Kräver: rasterio, numpy (i venv) + gdal_sieve.py (systeminstallerat)
"""

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
import rasterio

# ── Inställningar ─────────────────────────────────────────────────────────────
TILE    = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/tiles/NMD2023bas_tile_r000_c010.tif")
QML_SRC = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/NMD2023bas_v2_0.qml")
OUT_DIR = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/generalized_test_v2")

PROTECTED = {53, 61, 62}
NODATA_TMP = 65535          # temporärt nodata-värde för sieve (används ej i NMD)
MMU_STEPS = [2, 4, 8, 16, 32, 64, 100]
# ──────────────────────────────────────────────────────────────────────────────

OUT_DIR.mkdir(parents=True, exist_ok=True)

with rasterio.open(TILE) as src:
    meta = src.meta.copy()
    orig = src.read(1)

meta.update(compress="lzw")
# Meta för temporär sieve-fil: nodata satt så sieve skippar skyddade pixlar
meta_tmp = meta.copy()
meta_tmp.update(compress=None, nodata=NODATA_TMP)

print(f"Testtile  : {TILE.name}  ({orig.shape[1]}×{orig.shape[0]} px)")
print(f"Skyddade  : {sorted(PROTECTED)}")
print(f"Utmapp    : {OUT_DIR}")
print()

prev_data = orig.copy()     # data från föregående steg

for mmu in MMU_STEPS:
    t0      = time.time()
    outname = f"NMD2023bas_tile_r000_c010_mmu{mmu:03d}.tif"
    outpath = OUT_DIR / outname

    print(f"MMU={mmu:4d} px  ({mmu * 100 / 10000:.2f} ha) ... ", end="", flush=True)

    prot_mask = np.isin(prev_data, list(PROTECTED))

    # Skriv en temp-fil där skyddade klasser = nodata → sieve rör dem inte
    masked = prev_data.copy()
    masked[prot_mask] = NODATA_TMP

    with tempfile.NamedTemporaryFile(suffix="_in.tif",  delete=False) as f1, \
         tempfile.NamedTemporaryFile(suffix="_out.tif", delete=False) as f2:
        in_path  = Path(f1.name)
        tmp_path = Path(f2.name)

    try:
        with rasterio.open(in_path, "w", **meta_tmp) as dst:
            dst.write(masked, 1)

        subprocess.run(
            ["gdal_sieve.py", "-st", str(mmu), "-4", str(in_path), str(tmp_path)],
            capture_output=True, check=True
        )

        with rasterio.open(tmp_path) as src:
            sieved = src.read(1)

        # Återställ skyddade pixlar med värden från föregående steg
        sieved[prot_mask] = prev_data[prot_mask]

        with rasterio.open(outpath, "w", **meta) as dst:
            dst.write(sieved, 1)

        prev_data = sieved.copy()
    finally:
        in_path.unlink(missing_ok=True)
        tmp_path.unlink(missing_ok=True)

    if QML_SRC.exists():
        shutil.copy2(QML_SRC, outpath.with_suffix(".qml"))

    elapsed = time.time() - t0
    changed = int(np.sum(orig != sieved))
    n_after = len(np.unique(sieved))
    print(f"klar på {elapsed:.1f}s  |  {changed:,} px ändrade vs orig  |  {n_after} unika klasser")

print("\nKlart!")
