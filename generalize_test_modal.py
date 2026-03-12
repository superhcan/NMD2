"""
generalize_test_modal.py — Majoritetsfiltret (modal filter) för MMU-generalisering.

Ersätter varje pixel med den vanligaste klassen i ett N×N-fönster.
Kumulativ: varje steg använder föregående stegs utdata.

Vectoriserad implementation: en scipy uniform_filter per klass.
Skyddade klasser (53=väg, 61=sjö, 62=vatten) påverkar röstningen men ändras aldrig.
"""

import shutil
import time
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import uniform_filter

# ── Inställningar ─────────────────────────────────────────────────────────────
TILE      = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/tiles/NMD2023bas_tile_r000_c010.tif")
QML_SRC   = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/NMD2023bas_v2_0.qml")
OUT_DIR   = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/generalized_test_modal")
PROTECTED = {51, 52, 53, 54, 61, 62}

# Udda fönsterstorlekar (pixlar). Effektiv MMU ≈ k²/2
#   k= 3 →  ~4 px   k= 5 → ~12 px   k= 7 → ~24 px
#   k=11 → ~60 px   k=13 → ~84 px   k=15 → ~112 px
KERNEL_SIZES = [3, 5, 7, 11, 13, 15]
# ──────────────────────────────────────────────────────────────────────────────


def modal_filter_once(data: np.ndarray, kernel: int, protected: set) -> np.ndarray:
    """
    Ersätter varje icke-skyddad pixel med vanligaste klassen i kernel×kernel-fönster.

    Skyddade klasser (53=väg, 61=sjö, 62=vatten):
      - Röstar INTE i grannfönster (maskeras bort innan voting)
      - Återställs alltid till originalvärdet efteråt
    """
    prot_mask = np.isin(data, list(protected))

    # Ersätt skyddade pixlar med 0 i röstningsindata → de bidrar inte till något klass-fönster
    vote_data = data.copy()
    vote_data[prot_mask] = 0

    classes = [int(c) for c in np.unique(vote_data) if c > 0]

    best_count = np.full(data.shape, -1.0, dtype=np.float32)
    best_class = np.zeros(data.shape, dtype=np.int32)

    for cls in classes:
        mask  = (vote_data == cls).astype(np.float32)
        count = uniform_filter(mask, size=kernel, mode="nearest")
        # Liten bonus för befintlig klass → vinner vid lika röstetal (ingen onödig ändring)
        count = count + mask * 1e-4
        update     = count > best_count
        best_count = np.where(update, count, best_count)
        best_class = np.where(update, cls,   best_class)

    # Återställ skyddade klasser och bakgrund
    best_class[prot_mask] = data[prot_mask].astype(np.int32)
    best_class[data == 0] = 0

    return best_class.astype(data.dtype)


# ── Huvudloop ─────────────────────────────────────────────────────────────────
OUT_DIR.mkdir(parents=True, exist_ok=True)

with rasterio.open(TILE) as src:
    meta = src.meta.copy()
    orig = src.read(1)

meta.update(compress="lzw")

print(f"Testtile  : {TILE.name}  ({orig.shape[1]}×{orig.shape[0]} px)")
print(f"Skyddade  : {sorted(PROTECTED)}")
print(f"Metod     : modal filter (majority, vectorized)")
print(f"Utmapp    : {OUT_DIR}")
print()

prev_data = orig.copy()

for k in KERNEL_SIZES:
    t0      = time.time()
    eff_mmu = k * k // 2          # approximation för rektangulärt fönster
    outname = f"NMD2023bas_tile_r000_c010_modal_k{k:02d}.tif"
    outpath = OUT_DIR / outname

    print(f"Kernel {k:2d}×{k:2d}  (eff. MMU ≈ {eff_mmu:4d} px) … ", end="", flush=True)

    result = modal_filter_once(prev_data, k, PROTECTED)

    with rasterio.open(outpath, "w", **meta) as dst:
        dst.write(result, 1)

    if QML_SRC.exists():
        shutil.copy2(QML_SRC, outpath.with_suffix(".qml"))

    prev_data = result.copy()

    elapsed = time.time() - t0
    changed = int(np.sum(orig != result))
    n_after = len(np.unique(result))
    print(f"klar på {elapsed:.1f}s  |  {changed:,} px ändrade vs orig  |  {n_after} unika klasser")

print("\nKlart!")
