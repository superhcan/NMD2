"""
fill_islands.py — Fyller landöar < MMU_ISLAND px som är helt omringade av vatten.

En "ö" definieras som ett sammanhängande landområde (klass ≠ 61, 62) vars
samtliga grannar (ortogonalt, konnektivitet 4) tillhör klass 61 eller 62.
Sådana öar ersätts med den dominerande vattenklass som omger dem.

Bör köras FÖRE generaliseringssteget (gdal_sieve / modal / semantic).

Kräver: rasterio, numpy, scipy (i venv)
"""

import shutil
import time
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

# ── Inställningar ─────────────────────────────────────────────────────────────
TILE      = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/tiles/NMD2023bas_tile_r000_c010.tif")
QML_SRC   = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/NMD2023bas_v2_0.qml")
OUT_DIR   = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/filled_islands")

WATER_CLASSES = {61, 62}    # klasser som definierar "vatten" (omgivning för en ö)
MMU_ISLAND    = 100         # px; öar < detta antal px tas bort (100 px = 1 ha)
# konnektivitet 4 = ortogonalt, ger striktare definition av "omringad"
STRUCT_4 = np.array([[0, 1, 0],
                     [1, 1, 1],
                     [0, 1, 0]], dtype=bool)
# ──────────────────────────────────────────────────────────────────────────────

OUT_DIR.mkdir(parents=True, exist_ok=True)

t0 = time.time()
print(f"Läser  : {TILE.name}")

with rasterio.open(TILE) as src:
    meta      = src.meta.copy()
    orig      = src.read(1)

meta.update(compress="lzw")
data = orig.copy()

water_mask = np.isin(data, list(WATER_CLASSES))
land_mask  = ~water_mask

# Märk upp sammanhängande landkomponenter
labeled, n_components = ndimage.label(land_mask, structure=STRUCT_4)
print(f"Landkomponenter: {n_components:,}")

filled = 0
for i in range(1, n_components + 1):
    comp = labeled == i
    size = int(comp.sum())

    if size >= MMU_ISLAND:
        continue  # tillräckligt stor → behåll

    # Finn grannpixlar via dilatering (ortogonalt)
    dilated   = ndimage.binary_dilation(comp, structure=STRUCT_4)
    neighbors = data[dilated & ~comp]

    # Ön är omringad ENBART av vatten → fyll med dominerande vattenklass
    if not np.all(np.isin(neighbors, list(WATER_CLASSES))):
        continue  # delvis i kontakt med land → hoppa över

    vals, counts = np.unique(neighbors, return_counts=True)
    fill_val     = int(vals[counts.argmax()])
    data[comp]   = fill_val
    filled      += 1

elapsed = time.time() - t0
changed = int(np.sum(orig != data))
print(f"Öar fyllda : {filled:,}  ({changed:,} px ändrade)  |  {elapsed:.1f}s")

# ── Skriv utdata ──────────────────────────────────────────────────────────────
outname = TILE.stem + "_filled.tif"
outpath = OUT_DIR / outname

with rasterio.open(outpath, "w", **meta) as dst:
    dst.write(data, 1)

if QML_SRC.exists():
    shutil.copy2(QML_SRC, outpath.with_suffix(".qml"))

print(f"Utdata : {outpath}")
print("\nKlart!")
