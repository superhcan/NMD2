"""
pipeline_1024.py — Fullständig pipeline för NMD-generalisering, 1024 px tiles.

Bearbetar de fyra 2048 px-tiles som angränsar varandra (testtile + höger +
nedre + höger-nedre), delar om dem i 1024 px sub-tiles och kör:

  Steg 1: Dela upp i 1024 px tiles
  Steg 2: Fyll landöar < MMU_ISLAND px omringade av vatten (klass 61, 62)
  Steg 3: Generalisering – fyra metoder parallellt:
            a) gdal_sieve  konnektivitet 4
            b) gdal_sieve  konnektivitet 8
            c) Modal filter (majority)
            d) Semantisk likhet

Utdata sparas i:
  OUT_BASE/tiles/               – råa 1024 px tiles
  OUT_BASE/filled/              – efter öfyllnad
  OUT_BASE/generalized_conn4/   – sieve conn4
  OUT_BASE/generalized_conn8/   – sieve conn8
  OUT_BASE/generalized_modal/   – modal filter
  OUT_BASE/generalized_semantic/– semantisk generalisering

Kräver: rasterio, numpy, scipy (i venv) + gdal_sieve.py (systeminstallerat)
"""

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window
from scipy import ndimage
from scipy.ndimage import uniform_filter

# ══════════════════════════════════════════════════════════════════════════════
# Inställningar
# ══════════════════════════════════════════════════════════════════════════════

SRC = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/NMD2023bas_v2_0.tif")
QML_SRC = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/NMD2023bas_v2_0.qml")

# De fyra 2048 px-tiles som ska bearbetas (rad, kol i 2048 px-grid)
PARENT_TILES = [
    (0, 10),   # testtile (r000_c010)
    (0, 11),   # höger    (r000_c011)
    (1, 10),   # nedre    (r001_c010)
    (1, 11),   # höger-nedre (r001_c011)
]
PARENT_TILE_SIZE = 2048   # px för de befintliga tiles
SUB_TILE_SIZE    = 1024   # px för nya sub-tiles

OUT_BASE   = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024")
COMPRESS   = "lzw"

PROTECTED      = {51, 52, 53, 54, 61, 62}
WATER_CLASSES  = {61, 62}
NODATA_TMP     = 65535
MMU_ISLAND     = 100   # px (1 ha)
MMU_STEPS      = [2, 4, 8, 16, 32, 64, 100]
KERNEL_SIZES   = [3, 5, 7, 11, 13, 15]

# ══════════════════════════════════════════════════════════════════════════════
# Hjälpfunktioner
# ══════════════════════════════════════════════════════════════════════════════

STRUCT_4 = np.array([[0, 1, 0],
                     [1, 1, 1],
                     [0, 1, 0]], dtype=bool)

def copy_qml(tif_path: Path):
    if QML_SRC.exists():
        shutil.copy2(QML_SRC, tif_path.with_suffix(".qml"))


# ── Steg 2: Öfyllnad ──────────────────────────────────────────────────────────

def fill_small_islands(data: np.ndarray, water_classes: set, mmu: int) -> np.ndarray:
    """Fyller landöar < mmu px som är helt omringade av vatten-klasser."""
    data     = data.copy()
    water    = np.isin(data, list(water_classes))
    land     = ~water
    labeled, n = ndimage.label(land, structure=STRUCT_4)
    filled   = 0
    for i in range(1, n + 1):
        comp = labeled == i
        if comp.sum() >= mmu:
            continue
        dilated   = ndimage.binary_dilation(comp, structure=STRUCT_4)
        neighbors = data[dilated & ~comp]
        if not np.all(np.isin(neighbors, list(water_classes))):
            continue
        vals, counts = np.unique(neighbors, return_counts=True)
        data[comp]   = int(vals[counts.argmax()])
        filled      += 1
    return data, filled


# ── Steg 3a/b: gdal_sieve ─────────────────────────────────────────────────────

def run_sieve(data: np.ndarray, meta: dict, mmu: int, conn: int) -> np.ndarray:
    """Kör gdal_sieve med angiven konnektivitet. Skyddade klasser maskeras."""
    meta_tmp  = meta.copy()
    meta_tmp.update(compress=None, nodata=NODATA_TMP)
    prot_mask = np.isin(data, list(PROTECTED))
    masked    = data.copy()
    masked[prot_mask] = NODATA_TMP

    with tempfile.NamedTemporaryFile(suffix="_in.tif",  delete=False) as f1, \
         tempfile.NamedTemporaryFile(suffix="_out.tif", delete=False) as f2:
        in_p  = Path(f1.name)
        out_p = Path(f2.name)
    try:
        with rasterio.open(in_p, "w", **meta_tmp) as dst:
            dst.write(masked, 1)
        flag = "-4" if conn == 4 else "-8"
        subprocess.run(
            ["gdal_sieve.py", "-st", str(mmu), flag, str(in_p), str(out_p)],
            capture_output=True, check=True
        )
        with rasterio.open(out_p) as src:
            sieved = src.read(1)
        sieved[prot_mask] = data[prot_mask]
        return sieved
    finally:
        in_p.unlink(missing_ok=True)
        out_p.unlink(missing_ok=True)


# ── Steg 3c: Modal filter ─────────────────────────────────────────────────────

def modal_filter_once(data: np.ndarray, kernel: int) -> np.ndarray:
    """Majoritetsfiltret. Skyddade klasser röstar ej och återställs."""
    prot_mask = np.isin(data, list(PROTECTED))
    vote_data = data.copy()
    vote_data[prot_mask] = 0
    classes    = [int(c) for c in np.unique(vote_data) if c > 0]
    best_count = np.full(data.shape, -1.0, dtype=np.float32)
    best_class = np.zeros(data.shape,  dtype=np.int32)
    for cls in classes:
        mask  = (vote_data == cls).astype(np.float32)
        count = uniform_filter(mask, size=kernel, mode="nearest")
        count = count + mask * 1e-4
        upd        = count > best_count
        best_count = np.where(upd, count, best_count)
        best_class = np.where(upd, cls,   best_class)
    best_class[prot_mask]  = data[prot_mask].astype(np.int32)
    best_class[data == 0]  = 0
    return best_class.astype(data.dtype)


# ── Steg 3d: Semantisk generalisering ────────────────────────────────────────

def nmd_group(v: int) -> int:
    if v <= 0:   return -1
    if v < 10:   return v
    if v < 100:  return v // 10
    if v < 100:  return v // 100
    return v // 1000

_GDIST = {
    (1, 2): 2, (1, 3): 3, (1, 4): 3, (1, 5): 4, (1, 6): 5,
    (2, 3): 2, (2, 4): 1, (2, 5): 3, (2, 6): 4,
    (3, 4): 3, (3, 5): 4, (3, 6): 3,
    (4, 5): 3, (4, 6): 4,
    (5, 6): 4,
}

def sem_dist(a: int, b: int) -> int:
    if a == b: return 0
    ga, gb = nmd_group(a), nmd_group(b)
    if ga == gb: return 1
    return _GDIST.get((min(ga, gb), max(ga, gb)), 5)

def _build_labels(data, protected):
    prot   = np.isin(data, list(protected))
    active = ~prot & (data > 0)
    labels = np.zeros(data.shape, dtype=np.int32)
    lbl_cls = {}
    cur = 1
    for cls in np.unique(data[active]):
        cls = int(cls)
        cm  = active & (data == cls)
        lb, n = ndimage.label(cm, structure=STRUCT_4)
        if n > 0:
            labels[cm] = lb[cm] + (cur - 1)
            for i in range(n):
                lbl_cls[cur + i] = cls
            cur += n
    return labels, lbl_cls

def _build_adjacency(labels, lbl_cls):
    N = int(labels.max()) + 1
    def coded(a_f, b_f):
        mask = (a_f != b_f) & (a_f > 0) & (b_f > 0)
        a, b = a_f[mask].astype(np.int64), b_f[mask].astype(np.int64)
        swap = a > b
        a2, b2 = a.copy(), b.copy()
        a2[swap], b2[swap] = b[swap], a[swap]
        return np.unique(a2 * N + b2)
    codes = np.unique(np.concatenate([
        coded(labels[:, :-1].ravel(), labels[:, 1:].ravel()),
        coded(labels[:-1, :].ravel(), labels[1:, :].ravel()),
    ]))
    if len(codes) == 0:
        return {l: set() for l in lbl_cls}
    pa = (codes // N).astype(np.int32)
    pb = (codes %  N).astype(np.int32)
    adj = {}
    for src_arr, tgt_arr in [(pa, pb), (pb, pa)]:
        order = np.argsort(src_arr, kind="stable")
        ss, ts = src_arr[order], tgt_arr[order]
        _, first, cnt = np.unique(ss, return_index=True, return_counts=True)
        for idx, c in zip(first, cnt):
            key = int(ss[idx])
            tgt = ts[idx:idx + c].tolist()
            if key in adj:
                adj[key].update(tgt)
            else:
                adj[key] = set(tgt)
    return adj

def eliminate_small_semantic(data: np.ndarray, min_px: int) -> np.ndarray:
    import heapq
    if min_px <= 1:
        return data.copy()
    labels, patch_cls = _build_labels(data, PROTECTED)
    if not patch_cls:
        return data.copy()
    max_lbl  = int(labels.max())
    counts   = np.bincount(labels.ravel(), minlength=max_lbl + 1)
    patch_sz = {l: int(counts[l]) for l in patch_cls}
    adj      = _build_adjacency(labels, patch_cls)
    merge_parent: dict = {}

    def find(lbl):
        path = []
        while lbl in merge_parent:
            path.append(lbl)
            lbl = merge_parent[lbl]
        for p in path:
            merge_parent[p] = lbl
        return lbl

    heap = [(patch_sz[l], l) for l in patch_cls if patch_sz[l] < min_px]
    heapq.heapify(heap)
    while heap:
        _, lbl_id = heapq.heappop(heap)
        root = find(lbl_id)
        if root not in patch_cls or patch_sz.get(root, 0) >= min_px:
            continue
        lbl_id = root
        cls    = patch_cls[lbl_id]
        best_nb, best_score = None, (999, -1)
        seen: set = set()
        for nb in adj.get(lbl_id, set()):
            nr = find(nb)
            if nr == lbl_id or nr in seen or nr not in patch_cls:
                continue
            seen.add(nr)
            score = (sem_dist(cls, patch_cls[nr]), -patch_sz.get(nr, 0))
            if score < best_score:
                best_score = score
                best_nb    = nr
        if best_nb is None:
            continue
        merge_parent[lbl_id]  = best_nb
        patch_sz[best_nb]    += patch_sz.pop(lbl_id)
        del patch_cls[lbl_id]

    lbl2cls     = np.zeros(max_lbl + 1, dtype=data.dtype)
    for lbl in range(1, max_lbl + 1):
        root        = find(lbl)
        lbl2cls[lbl] = patch_cls.get(root, 0)
    result = lbl2cls[labels]
    prot   = np.isin(data, list(PROTECTED))
    result[prot]    = data[prot]
    result[data==0] = 0
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Steg 1: Dela upp i 1024 px sub-tiles
# ══════════════════════════════════════════════════════════════════════════════

def step1_split(src_meta: dict) -> list[Path]:
    """Delar upp ROI i 1024 px tiles. Returnerar lista med skapade tif-filer."""
    out_dir = OUT_BASE / "tiles"
    out_dir.mkdir(parents=True, exist_ok=True)
    created = []
    src_w   = src_meta["width"]
    src_h   = src_meta["height"]

    with rasterio.open(SRC) as src:
        meta = src.meta.copy()
        meta.update(compress=COMPRESS)

        for p_row, p_col in PARENT_TILES:
            px_off = p_col * PARENT_TILE_SIZE
            py_off = p_row * PARENT_TILE_SIZE

            for sub_r in range(2):
                for sub_c in range(2):
                    x_off = px_off + sub_c * SUB_TILE_SIZE
                    y_off = py_off + sub_r * SUB_TILE_SIZE
                    w     = min(SUB_TILE_SIZE, src_w - x_off)
                    h     = min(SUB_TILE_SIZE, src_h - y_off)
                    if w <= 0 or h <= 0:
                        continue

                    t_row = p_row * 2 + sub_r
                    t_col = p_col * 2 + sub_c
                    name  = f"NMD2023bas_tile_r{t_row:03d}_c{t_col:03d}.tif"
                    path  = out_dir / name
                    if path.exists():
                        created.append(path)
                        continue

                    win  = Window(x_off, y_off, w, h)
                    tmeta = meta.copy()
                    tmeta.update(width=w, height=h,
                                 transform=src.window_transform(win))
                    with rasterio.open(path, "w", **tmeta) as dst:
                        dst.write(src.read(window=win))
                    copy_qml(path)
                    created.append(path)
    return created


# ══════════════════════════════════════════════════════════════════════════════
# Steg 2: Fyll öar
# ══════════════════════════════════════════════════════════════════════════════

def step2_fill(tile_paths: list[Path]) -> list[Path]:
    out_dir = OUT_BASE / "filled"
    out_dir.mkdir(parents=True, exist_ok=True)
    filled_paths = []
    for tile in tile_paths:
        out_path = out_dir / tile.name
        if out_path.exists():
            filled_paths.append(out_path)
            continue
        with rasterio.open(tile) as src:
            meta = src.meta.copy()
            data = src.read(1)
        meta.update(compress=COMPRESS)
        result, n_filled = fill_small_islands(data, WATER_CLASSES, MMU_ISLAND)
        with rasterio.open(out_path, "w", **meta) as dst:
            dst.write(result, 1)
        copy_qml(out_path)
        filled_paths.append(out_path)
        print(f"  fill  {tile.name}: {n_filled} öar fyllda")
    return filled_paths


# ══════════════════════════════════════════════════════════════════════════════
# Steg 3: Generalisering
# ══════════════════════════════════════════════════════════════════════════════

def step3_sieve(filled_paths: list[Path], conn: int):
    label = f"conn{conn}"
    out_dir = OUT_BASE / f"generalized_{label}"
    out_dir.mkdir(parents=True, exist_ok=True)
    for tile in filled_paths:
        stem = tile.stem   # NMD2023bas_tile_r000_c020
        with rasterio.open(tile) as src:
            meta = src.meta.copy()
            orig = src.read(1)
        meta.update(compress=COMPRESS)
        prev = orig.copy()
        print(f"  sieve {label}  {tile.name}")
        for mmu in MMU_STEPS:
            out_path = out_dir / f"{stem}_{label}_mmu{mmu:03d}.tif"
            if out_path.exists():
                # Läs föreg. om den finns, för kumulativt beteende
                with rasterio.open(out_path) as s:
                    prev = s.read(1)
                continue
            t0     = time.time()
            sieved = run_sieve(prev, meta, mmu, conn)
            with rasterio.open(out_path, "w", **meta) as dst:
                dst.write(sieved, 1)
            copy_qml(out_path)
            prev = sieved
            print(f"    mmu={mmu:3d}px  {time.time()-t0:.1f}s  "
                  f"{np.sum(orig!=sieved):,} px ändrade")


def step3_modal(filled_paths: list[Path]):
    out_dir = OUT_BASE / "generalized_modal"
    out_dir.mkdir(parents=True, exist_ok=True)
    for tile in filled_paths:
        stem = tile.stem
        with rasterio.open(tile) as src:
            meta = src.meta.copy()
            orig = src.read(1)
        meta.update(compress=COMPRESS)
        prev = orig.copy()
        print(f"  modal  {tile.name}")
        for k in KERNEL_SIZES:
            out_path = out_dir / f"{stem}_modal_k{k:02d}.tif"
            if out_path.exists():
                with rasterio.open(out_path) as s:
                    prev = s.read(1)
                continue
            t0     = time.time()
            result = modal_filter_once(prev, k)
            with rasterio.open(out_path, "w", **meta) as dst:
                dst.write(result, 1)
            copy_qml(out_path)
            prev = result
            print(f"    k={k:2d}  {time.time()-t0:.1f}s  "
                  f"{np.sum(orig!=result):,} px ändrade")


def step3_semantic(filled_paths: list[Path]):
    out_dir = OUT_BASE / "generalized_semantic"
    out_dir.mkdir(parents=True, exist_ok=True)
    for tile in filled_paths:
        stem = tile.stem
        with rasterio.open(tile) as src:
            meta = src.meta.copy()
            orig = src.read(1)
        meta.update(compress=COMPRESS)
        prev = orig.copy()
        print(f"  semantic  {tile.name}")
        for mmu in MMU_STEPS:
            out_path = out_dir / f"{stem}_semantic_mmu{mmu:03d}.tif"
            if out_path.exists():
                with rasterio.open(out_path) as s:
                    prev = s.read(1)
                continue
            t0     = time.time()
            result = eliminate_small_semantic(prev, mmu)
            with rasterio.open(out_path, "w", **meta) as dst:
                dst.write(result, 1)
            copy_qml(out_path)
            prev = result
            print(f"    mmu={mmu:3d}px  {time.time()-t0:.1f}s  "
                  f"{np.sum(orig!=result):,} px ändrade")


# ══════════════════════════════════════════════════════════════════════════════
# Huvudprogram
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    t_total = time.time()
    OUT_BASE.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Steg 1: Dela upp i 1024 px tiles")
    print("=" * 60)
    with rasterio.open(SRC) as src:
        src_meta = src.meta.copy()
    tile_paths = step1_split(src_meta)
    print(f"  {len(tile_paths)} tiles skapade/hittade → {OUT_BASE / 'tiles'}")

    print()
    print("=" * 60)
    print("Steg 2: Fyll landöar < 1 ha i vatten")
    print("=" * 60)
    filled_paths = step2_fill(tile_paths)

    print()
    print("=" * 60)
    print("Steg 3a: Generalisering – sieve konnektivitet 4")
    print("=" * 60)
    step3_sieve(filled_paths, conn=4)

    print()
    print("=" * 60)
    print("Steg 3b: Generalisering – sieve konnektivitet 8")
    print("=" * 60)
    step3_sieve(filled_paths, conn=8)

    print()
    print("=" * 60)
    print("Steg 3c: Generalisering – modal filter")
    print("=" * 60)
    step3_modal(filled_paths)

    print()
    print("=" * 60)
    print("Steg 3d: Generalisering – semantisk")
    print("=" * 60)
    step3_semantic(filled_paths)

    print()
    print(f"Totalt: {time.time() - t_total:.0f}s")
    print(f"Utdata: {OUT_BASE}")
