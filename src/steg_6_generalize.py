"""
steg_6_generalize.py — Steg 6: Landskapsgeneralisering med halo-teknik.

Som pipeline_1024_halo.py men nu som separat steg. Använder halo/överlapp vid generalisering
för att säkerställa att ytor som korsar tilekanter generaliseras korrekt.

HALO = 100 px på varje tilekant säkerställer att ytor ses som sammanhängande patch 
istället för två separata när de ligger på tilegrä.

Nyckelskillnad mot tidigare pipeline:
  - Generaliseringen körs STEG-FÖR-STEG (inte tile-för-tile):
      Alla tiles → MMU=2 → bygg VRT → alla tiles → MMU=4 → bygg VRT → ...
  - Varje steg läser HALO px extra från granntilesna via VRT.
  - Bara den inre kärnan (utan halo) skrivs till utfilen.

Kör: python3 src/steg_6_generalize.py

Kräver: rasterio, numpy, scipy (i venv) + gdal_sieve.py + gdalbuildvrt (system)
"""

import logging
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window
from scipy import ndimage
from scipy.ndimage import uniform_filter

from config import OUT_BASE, SRC, QML_SRC, PARENT_TILES, PARENT_TILE_SIZE, SUB_TILE_SIZE, PROTECTED, WATER_CLASSES, COMPRESS

# ══════════════════════════════════════════════════════════════════════════════
# Logging – två loggers + console
# ══════════════════════════════════════════════════════════════════════════════

_LOGGERS = {}

def _setup_logging(out_base: Path):
    """Skapar två loggfiler:
      debug   – alla level (DEBUG+)  → log/debug_stegN_namn_<ts>.log
      summary – INFO+                → summary/summary_stegN_namn_<ts>.log + console
    """
    import os
    log_dir = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Läs steg-info från miljövariabler
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    
    # Skapa loggfilnamn med eventuell steg-referens
    if step_num and step_name:
        step_suffix = f"steg_{step_num}_{step_name}_{ts}"
    else:
        step_suffix = f"{ts}"
    
    debug_log   = log_dir / f"debug_{step_suffix}.log"
    summary_log = summary_dir / f"summary_{step_suffix}.log"

    fmt_detail  = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    fmt_summary = logging.Formatter(
        "%(asctime)s [%(levelname)-6s] %(message)s",
        datefmt="%H:%M:%S"
    )

    # ── Debug-logg (DEBUG+) ──
    dbg = logging.getLogger("pipeline.debug")
    dbg.setLevel(logging.DEBUG)
    dbg_handler = logging.FileHandler(debug_log)
    dbg_handler.setLevel(logging.DEBUG)
    dbg_handler.setFormatter(fmt_detail)
    dbg.addHandler(dbg_handler)

    # ── Summary-logg (INFO+) – både fil och console ──
    summary = logging.getLogger("pipeline.summary")
    summary.setLevel(logging.INFO)

    # Fil-handler
    summary_file_handler = logging.FileHandler(summary_log)
    summary_file_handler.setLevel(logging.INFO)
    summary_file_handler.setFormatter(fmt_summary)
    summary.addHandler(summary_file_handler)

    # Console-handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt_summary)
    summary.addHandler(console_handler)

    _LOGGERS["debug"] = dbg
    _LOGGERS["summary"] = summary
    
    summary.info(f"Pipeline startat")
    summary.info(f"Debug-logg: {debug_log}")
    summary.info(f"Summary-logg: {summary_log}")

# Placeholders – ersätts i __main__ efter OUT_BASE skapats
log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")

# ══════════════════════════════════════════════════════════════════════════════
# HALO-parameters
# ══════════════════════════════════════════════════════════════════════════════

HALO = 100
NODATA_TMP    = 65535
MMU_ISLAND    = 100
MMU_STEPS     = [2, 4, 8, 16, 32, 64, 100]
KERNEL_SIZES  = [3, 5, 7, 11, 13, 15]
HALO          = 100   # px – kant på varje sida, >= max(MMU_STEPS)

STRUCT_4 = np.array([[0, 1, 0],
                     [1, 1, 1],
                     [0, 1, 0]], dtype=bool)

# ══════════════════════════════════════════════════════════════════════════════
# Hjälpfunktioner
# ══════════════════════════════════════════════════════════════════════════════

def copy_qml(tif_path: Path):
    if QML_SRC.exists():
        shutil.copy2(QML_SRC, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def build_vrt(paths: list[Path], vrt_path: Path):
    """Bygger en GDAL VRT av angiven lista tif-filer."""
    log.debug("Bygger VRT %s av %d filer", vrt_path.name, len(paths))
    subprocess.run(
        ["gdalbuildvrt", str(vrt_path), *[str(p) for p in paths]],
        capture_output=True, check=True
    )
    log.debug("VRT klar: %s", vrt_path.name)


def read_with_halo(vrt_path: Path, tile_path: Path):
    """
    Läser tile + HALO px kant från VRT.

    Returnerar:
      padded_data  – numpy array (h+2*halo, w+2*halo) klippt mot VRT-gränser
      tile_meta    – meta dict för originaltilen (för skrivning av utdata)
      inner_slice  – (row_slice, col_slice) som plockar ut tile-kärnan
    """
    with rasterio.open(vrt_path) as vrt, rasterio.open(tile_path) as tile:
        vt = vrt.transform
        tt = tile.transform
        px = vt.a    # pixelbredd (positiv)
        py = vt.e    # pixelhöjd  (negativ)

        tile_col = round((tt.c - vt.c) / px)
        tile_row = round((tt.f - vt.f) / py)
        tile_w   = tile.width
        tile_h   = tile.height
        tile_meta = tile.meta.copy()

        x0 = max(0, tile_col - HALO)
        y0 = max(0, tile_row - HALO)
        x1 = min(vrt.width,  tile_col + tile_w + HALO)
        y1 = min(vrt.height, tile_row + tile_h + HALO)

        win  = Window(x0, y0, x1 - x0, y1 - y0)
        data = vrt.read(1, window=win)

    inner_row = tile_row - y0
    inner_col = tile_col - x0
    inner_slice = (
        slice(inner_row, inner_row + tile_h),
        slice(inner_col, inner_col + tile_w),
    )
    return data, tile_meta, inner_slice


# ── Steg 2: Öfyllnad ──────────────────────────────────────────────────────────

def fill_small_islands(data: np.ndarray, water_classes: set, mmu: int):
    data   = data.copy()
    water  = np.isin(data, list(water_classes))
    land   = ~water
    labeled, n_comp = ndimage.label(land, structure=STRUCT_4)
    log.debug("fill_small_islands: %d landkomponenter hittade", n_comp)
    filled = 0
    skipped_land = 0
    for i in range(1, n_comp + 1):
        comp = labeled == i
        if comp.sum() >= mmu:
            continue
        dilated   = ndimage.binary_dilation(comp, structure=STRUCT_4)
        neighbors = data[dilated & ~comp]
        if not np.all(np.isin(neighbors, list(water_classes))):
            skipped_land += 1
            continue
        vals, counts = np.unique(neighbors, return_counts=True)
        fill_val     = int(vals[counts.argmax()])
        log.debug("  Ö %d: %d px → ersatt med klass %d", i, int(comp.sum()), fill_val)
        data[comp]   = fill_val
        filled      += 1
    log.debug("fill_small_islands klar: %d öar fyllda, %d delvis omringade hoppades",
              filled, skipped_land)
    return data, filled


# ── Steg 3a/b: gdal_sieve ─────────────────────────────────────────────────────

def run_sieve(data: np.ndarray, mmu: int, conn: int) -> np.ndarray:
    """Kör gdal_sieve på data-array. Skyddade klasser maskeras."""
    log.debug("run_sieve: mmu=%d conn=%d  data=%s", mmu, conn, data.shape)
    # Bygg en minimal meta för temp-filen (transform spelar ingen roll för sieve)
    from rasterio.transform import from_bounds
    dummy_transform = from_bounds(0, 0, data.shape[1], data.shape[0],
                                  data.shape[1], data.shape[0])
    meta_tmp = {
        "driver": "GTiff", "dtype": data.dtype, "count": 1,
        "height": data.shape[0], "width": data.shape[1],
        "crs": "EPSG:3006", "transform": dummy_transform,
        "compress": None, "nodata": NODATA_TMP,
    }
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
        changed = int(np.sum(sieved != data))
        log.debug("run_sieve klar: %d px ändrade (%.1f%%)",
                  changed, changed / data.size * 100)
        return sieved
    finally:
        in_p.unlink(missing_ok=True)
        out_p.unlink(missing_ok=True)


# ── Steg 3c: Modal filter ─────────────────────────────────────────────────────

def modal_filter_once(data: np.ndarray, kernel: int) -> np.ndarray:
    log.debug("modal_filter_once: kernel=%d  data=%s", kernel, data.shape)
    prot_mask  = np.isin(data, list(PROTECTED))
    vote_data  = data.copy()
    vote_data[prot_mask] = 0
    classes    = [int(c) for c in np.unique(vote_data) if c > 0]
    log.debug("  %d klasser i röstningen", len(classes))
    best_count = np.full(data.shape, -1.0, dtype=np.float32)
    best_class = np.zeros(data.shape,  dtype=np.int32)
    for cls in classes:
        mask  = (vote_data == cls).astype(np.float32)
        count = uniform_filter(mask, size=kernel, mode="nearest")
        count = count + mask * 1e-4
        upd        = count > best_count
        best_count = np.where(upd, count, best_count)
        best_class = np.where(upd, cls,   best_class)
    best_class[prot_mask] = data[prot_mask].astype(np.int32)
    best_class[data == 0] = 0
    result = best_class.astype(data.dtype)
    changed = int(np.sum(result != data))
    log.debug("modal_filter_once klar: %d px ändrade (%.1f%%)",
              changed, changed / data.size * 100)
    return result


# ── Steg 3d: Semantisk generalisering ────────────────────────────────────────

def nmd_group(v: int) -> int:
    if v <= 0:   return -1
    if v < 10:   return v
    if v < 100:  return v // 10
    if v < 1000: return v // 100
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

def _build_labels(data):
    prot   = np.isin(data, list(PROTECTED))
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
            for i in range(n): lbl_cls[cur + i] = cls
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
            adj[key] = adj.get(key, set()) | set(tgt)
    return adj

def eliminate_small_semantic(data: np.ndarray, min_px: int) -> np.ndarray:
    import heapq
    log.debug("eliminate_small_semantic: min_px=%d  data=%s", min_px, data.shape)
    if min_px <= 1:
        return data.copy()
    labels, patch_cls = _build_labels(data)
    if not patch_cls:
        log.warning("eliminate_small_semantic: inga patches hittade")
        return data.copy()
    max_lbl  = int(labels.max())
    log.debug("  %d patches totalt", len(patch_cls))
    counts   = np.bincount(labels.ravel(), minlength=max_lbl + 1)
    patch_sz = {l: int(counts[l]) for l in patch_cls}
    adj      = _build_adjacency(labels, patch_cls)
    merge_parent: dict = {}

    def find(lbl):
        path = []
        while lbl in merge_parent:
            path.append(lbl); lbl = merge_parent[lbl]
        for p in path: merge_parent[p] = lbl
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
            if nr == lbl_id or nr in seen or nr not in patch_cls: continue
            seen.add(nr)
            score = (sem_dist(cls, patch_cls[nr]), -patch_sz.get(nr, 0))
            if score < best_score:
                best_score = score; best_nb = nr
        if best_nb is None: continue
        merge_parent[lbl_id] = best_nb
        patch_sz[best_nb]   += patch_sz.pop(lbl_id)
        del patch_cls[lbl_id]

    lbl2cls = np.zeros(max_lbl + 1, dtype=data.dtype)
    for lbl in range(1, max_lbl + 1):
        lbl2cls[lbl] = patch_cls.get(find(lbl), 0)
    result = lbl2cls[labels]
    prot   = np.isin(data, list(PROTECTED))
    result[prot]    = data[prot]
    result[data==0] = 0
    changed = int(np.sum(result != data))
    log.debug("eliminate_small_semantic klar: %d px ändrade (%.1f%%)",
              changed, changed / data.size * 100)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Steg 1: Dela upp i 1024 px sub-tiles
# ══════════════════════════════════════════════════════════════════════════════

def step1_split() -> list[Path]:
    t0      = time.time()
    out_dir = OUT_BASE / "steg1_tiles"
    out_dir.mkdir(parents=True, exist_ok=True)
    created  = []
    new_tiles = 0
    log.debug("step1_split: källbild %s", SRC.name)
    with rasterio.open(SRC) as src:
        meta  = src.meta.copy()
        meta.update(compress=COMPRESS)
        src_w = src.width
        src_h = src.height
        log.debug("  källbild storlek: %d × %d px", src_w, src_h)
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
                        log.warning("step1_split: tom tile vid (%d,%d) hoppas",
                                    p_row * 2 + sub_r, p_col * 2 + sub_c)
                        continue
                    t_row = p_row * 2 + sub_r
                    t_col = p_col * 2 + sub_c
                    name  = f"NMD2023bas_tile_r{t_row:03d}_c{t_col:03d}.tif"
                    path  = out_dir / name
                    if not path.exists():
                        win   = Window(x_off, y_off, w, h)
                        tmeta = meta.copy()
                        tmeta.update(width=w, height=h,
                                     transform=src.window_transform(win))
                        with rasterio.open(path, "w", **tmeta) as dst:
                            dst.write(src.read(window=win))
                        copy_qml(path)
                        new_tiles += 1
                        log.debug("  Ny tile: %s  (%d×%d px)", name, w, h)
                    else:
                        log.debug("  Hoppas (finns redan): %s", name)
                    created.append(path)
    elapsed = time.time() - t0
    info.info("Steg 1 klar: %d tiles (%d nya, %d redan existerande)  %.1fs",
              len(created), new_tiles, len(created) - new_tiles, elapsed)
    return created


# ══════════════════════════════════════════════════════════════════════════════
# Steg 2: Extrahera skyddade klasser (51, 52, 53, 54, 61, 62)
# ══════════════════════════════════════════════════════════════════════════════

def step2_extract_protected(tile_paths: list[Path]) -> list[Path]:
    """Extrahera BARA skyddade klasser från original-tiles."""
    t0_step = time.time()
    out_dir = OUT_BASE / "steg2_protected"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_paths = []
    total_px_extracted = 0
    
    info.info("Steg 2: Extraherar skyddade klasser %s från original-tiles...", sorted(PROTECTED))
    
    for tile in tile_paths:
        out_path = out_dir / tile.name
        if not out_path.exists():
            t0 = time.time()
            with rasterio.open(tile) as src:
                meta = src.meta.copy()
                data = src.read(1)
            meta.update(compress=COMPRESS)
            
            # Skapa mask för skyddade klasser, sätt allt annat till 0
            protected_data = np.where(np.isin(data, list(PROTECTED)), data, 0).astype(data.dtype)
            n_px = int(np.count_nonzero(protected_data))
            total_px_extracted += n_px
            
            with rasterio.open(out_path, "w", **meta) as dst:
                dst.write(protected_data, 1)
            copy_qml(out_path)
            
            elapsed = time.time() - t0
            log.debug("step2_extract_protected: %s → %d px skyddade klasser  %.1fs",
                      tile.name, n_px, elapsed)
            info.info("  %-45s  %9d px extraherade  %.1fs", tile.name, n_px, elapsed)
        else:
            log.debug("step2_extract_protected: hoppar %s (finns redan)", tile.name)
        result_paths.append(out_path)
    
    info.info("Steg 2 klar: totalt %d px skyddade klasser extraherade  %.1fs",
              total_px_extracted, time.time() - t0_step)
    return result_paths


# ══════════════════════════════════════════════════════════════════════════════
# Steg 3: Extrahera landskapet (allt utom skyddade klasser)
# ══════════════════════════════════════════════════════════════════════════════

def step3_extract_landscape(tile_paths: list[Path]) -> list[Path]:
    """Extrahera landskapet: ta bort vägar (53) och byggnader (51) och ersätt med närliggande lanskapklasser."""
    t0_step = time.time()
    out_dir = OUT_BASE / "steg3_landscape"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_paths = []
    
    ROADS_BUILDINGS = {51, 53}  # 51=Byggnad, 53=Väg/järnväg
    
    info.info("Steg 3: Extraherar landskapet (ersätter vägar 53 och byggnader 51 med grannande klasser)...")
    
    for tile in tile_paths:
        out_path = out_dir / tile.name
        if not out_path.exists():
            t0 = time.time()
            with rasterio.open(tile) as src:
                meta = src.meta.copy()
                data = src.read(1)
            meta.update(compress=COMPRESS)
            
            landscape_data = data.copy()
            
            # Iterativ ersättning: för varje väg/byggnad-pixel, ersätt med mest vanlig grannklass
            mask_roads_buildings = np.isin(landscape_data, ROADS_BUILDINGS)
            
            for iteration in range(10):  # Max 10 iterationer
                if not np.any(mask_roads_buildings):
                    break
                
                # För varje väg/byggnad-pixel, hitta grannarnas klasser
                for i in range(landscape_data.shape[0]):
                    for j in range(landscape_data.shape[1]):
                        if mask_roads_buildings[i, j]:
                            # Sammla grannarnas klassificeringar (8-connectedness)
                            neighbors = []
                            for di in [-1, 0, 1]:
                                for dj in [-1, 0, 1]:
                                    if di == 0 and dj == 0:
                                        continue
                                    ni, nj = i + di, j + dj
                                    if 0 <= ni < landscape_data.shape[0] and 0 <= nj < landscape_data.shape[1]:
                                        if not np.isin(landscape_data[ni, nj], ROADS_BUILDINGS):
                                            neighbors.append(landscape_data[ni, nj])
                            
                            # Ersätt med mest vanlig grannklass
                            if neighbors:
                                most_common = np.bincount(neighbors).argmax()
                                landscape_data[i, j] = most_common
                                mask_roads_buildings[i, j] = False
            
            with rasterio.open(out_path, "w", **meta) as dst:
                dst.write(landscape_data, 1)
            copy_qml(out_path)
            
            elapsed = time.time() - t0
            log.debug("step3_extract_landscape: %s → vägar/byggnader ersatta  %.1fs",
                      tile.name, elapsed)
            info.info("  %-45s  vägar/byggnader ersatta med grannklasser  %.1fs", tile.name, elapsed)
        else:
            log.debug("step3_extract_landscape: hoppar %s (finns redan)", tile.name)
        result_paths.append(out_path)
    
    info.info("Steg 3 klar: landskapet extraherat med vägar/byggnader ersatta  %.1fs",
              time.time() - t0_step)
    return result_paths


# ══════════════════════════════════════════════════════════════════════════════
# Steg 4a: Filtrera små öar (ingen halo behövs – öar som stöter mot tilekant
#          är per definition inte helt omringade av vatten)
# ══════════════════════════════════════════════════════════════════════════════

def step4_fill(tile_paths: list[Path]) -> list[Path]:
    t0_step   = time.time()
    out_dir   = OUT_BASE / "steg4_filled"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_paths  = []
    total_islands = 0
    info.info("Steg 4a: Fyller landöar < %d px (%.2f ha) i vatten ...",
              MMU_ISLAND, MMU_ISLAND * 100 / 10000)
    for tile in tile_paths:
        out_path = out_dir / tile.name
        if not out_path.exists():
            t0 = time.time()
            with rasterio.open(tile) as src:
                meta = src.meta.copy(); data = src.read(1)
            meta.update(compress=COMPRESS)
            log.debug("step2_fill: bearbetar %s", tile.name)
            filled_data, n = fill_small_islands(data, WATER_CLASSES, MMU_ISLAND)
            with rasterio.open(out_path, "w", **meta) as dst:
                dst.write(filled_data, 1)
            copy_qml(out_path)
            px_changed = int(np.sum(filled_data != data))
            elapsed    = time.time() - t0
            total_islands += n
            info.info("  %-45s  %3d öar fyllda  %6d px ändrade  %.1fs",
                      tile.name, n, px_changed, elapsed)
        else:
            log.debug("step2_fill: hoppar %s (finns redan)", tile.name)
        result_paths.append(out_path)
    info.info("Steg 4a klar: totalt %d öar fyllda  %.1fs",
              total_islands, time.time() - t0_step)
    return result_paths


# ══════════════════════════════════════════════════════════════════════════════
# Steg 4: Generalisering med halo – steg-för-steg över alla tiles
# ══════════════════════════════════════════════════════════════════════════════

def step5_sieve_halo(tile_paths: list[Path], filled_paths: list[Path], conn: int):
    label    = f"conn{conn}"
    out_dir = OUT_BASE / f"steg6_generalized_{label}"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0_step  = time.time()

    prev_vrt = OUT_BASE / "steg4_filled_mosaic.vrt"
    if not prev_vrt.exists():
        build_vrt(filled_paths, prev_vrt)

    info.info("Steg 6 Sieve-%s: %d MMU-steg × %d tiles (halo=%dpx)",
              label, len(MMU_STEPS), len(tile_paths), HALO)

    for mmu in MMU_STEPS:
        step_outputs  = []
        t0            = time.time()
        total_changed = 0
        log.debug("%s mmu=%d: startar", label, mmu)

        for tile in tile_paths:
            stem     = tile.stem
            out_path = out_dir / f"{stem}_{label}_mmu{mmu:03d}.tif"
            if out_path.exists():
                log.debug("  %s hoppar (finns redan)", out_path.name)
                step_outputs.append(out_path)
                continue

            t1 = time.time()
            padded, tile_meta, inner = read_with_halo(prev_vrt, tile)
            tile_meta.update(compress=COMPRESS)

            # Läs originaltilen för att räkna ändrade pixlar
            with rasterio.open(tile) as _src:
                orig_inner = _src.read(1)

            sieved_padded = run_sieve(padded, mmu, conn)
            result        = sieved_padded[inner]
            changed       = int(np.sum(result != orig_inner))
            total_changed += changed

            with rasterio.open(out_path, "w", **tile_meta) as dst:
                dst.write(result, 1)
            copy_qml(out_path)
            step_outputs.append(out_path)
            log.debug("  %s: %d px ändrade vs orig  %.1fs",
                      out_path.name, changed, time.time() - t1)

        step_vrt = out_dir / f"_vrt_mmu{mmu:03d}.vrt"
        build_vrt(step_outputs, step_vrt)
        prev_vrt = step_vrt
        elapsed  = time.time() - t0
        info.info("  %-10s mmu=%3dpx  totalt %9d px ändrade  %.1fs",
                  label, mmu, total_changed, elapsed)

    info.info("Steg 6 Sieve-%s KLAR  %.1fs", label, time.time() - t0_step)


def step5_modal_halo(tile_paths: list[Path], filled_paths: list[Path]):
    out_dir  = OUT_BASE / f"steg6_generalized_modal"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0_step = time.time()

    prev_vrt = OUT_BASE / "steg4_filled_mosaic.vrt"
    if not prev_vrt.exists():
        build_vrt(filled_paths, prev_vrt)

    info.info("Steg 6 Modal: %d kernelstorlekar × %d tiles (halo=%dpx)",
              len(KERNEL_SIZES), len(tile_paths), HALO)

    for k in KERNEL_SIZES:
        step_outputs  = []
        t0            = time.time()
        total_changed = 0
        log.debug("modal k=%d: startar", k)

        for tile in tile_paths:
            stem     = tile.stem
            out_path = out_dir / f"{stem}_modal_k{k:02d}.tif"
            if out_path.exists():
                log.debug("  %s hoppar (finns redan)", out_path.name)
                step_outputs.append(out_path)
                continue

            t1 = time.time()
            padded, tile_meta, inner = read_with_halo(prev_vrt, tile)
            tile_meta.update(compress=COMPRESS)

            with rasterio.open(tile) as _src:
                orig_inner = _src.read(1)

            result  = modal_filter_once(padded, k)[inner]
            changed = int(np.sum(result != orig_inner))
            total_changed += changed

            with rasterio.open(out_path, "w", **tile_meta) as dst:
                dst.write(result, 1)
            copy_qml(out_path)
            step_outputs.append(out_path)
            log.debug("  %s: %d px ändrade vs orig  %.1fs",
                      out_path.name, changed, time.time() - t1)

        step_vrt = out_dir / f"_vrt_k{k:02d}.vrt"
        build_vrt(step_outputs, step_vrt)
        prev_vrt = step_vrt
        elapsed  = time.time() - t0
        info.info("  modal      k=%2d          totalt %9d px ändrade  %.1fs",
                  k, total_changed, elapsed)

    info.info("Steg 6 Modal KLAR  %.1fs", time.time() - t0_step)


def step5_semantic_halo(tile_paths: list[Path], filled_paths: list[Path]):
    out_dir = OUT_BASE / f"steg6_generalized_semantic"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0_step = time.time()

    prev_vrt = OUT_BASE / "steg4_filled_mosaic.vrt"
    if not prev_vrt.exists():
        build_vrt(filled_paths, prev_vrt)

    info.info("Steg 6 Semantisk: %d MMU-steg × %d tiles (halo=%dpx)",
              len(MMU_STEPS), len(tile_paths), HALO)

    for mmu in MMU_STEPS:
        step_outputs  = []
        t0            = time.time()
        total_changed = 0
        log.debug("semantic mmu=%d: startar", mmu)

        for tile in tile_paths:
            stem     = tile.stem
            out_path = out_dir / f"{stem}_semantic_mmu{mmu:03d}.tif"
            if out_path.exists():
                log.debug("  %s hoppar (finns redan)", out_path.name)
                step_outputs.append(out_path)
                continue

            t1 = time.time()
            padded, tile_meta, inner = read_with_halo(prev_vrt, tile)
            tile_meta.update(compress=COMPRESS)

            with rasterio.open(tile) as _src:
                orig_inner = _src.read(1)

            result  = eliminate_small_semantic(padded, mmu)[inner]
            changed = int(np.sum(result != orig_inner))
            total_changed += changed

            with rasterio.open(out_path, "w", **tile_meta) as dst:
                dst.write(result, 1)
            copy_qml(out_path)
            step_outputs.append(out_path)
            log.debug("  %s: %d px ändrade vs orig  %.1fs",
                      out_path.name, changed, time.time() - t1)

        step_vrt = out_dir / f"_vrt_mmu{mmu:03d}.vrt"
        build_vrt(step_outputs, step_vrt)
        prev_vrt = step_vrt
        elapsed  = time.time() - t0
        info.info("  semantic   mmu=%3dpx  totalt %9d px ändrade  %.1fs",
                  mmu, total_changed, elapsed)

    info.info("Steg 6 Semantisk KLAR  %.1fs", time.time() - t0_step)


# ══════════════════════════════════════════════════════════════════════════════
# Huvudprogram
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    OUT_BASE.mkdir(parents=True, exist_ok=True)
    _setup_logging(OUT_BASE)
    log  = _LOGGERS["debug"]
    info = _LOGGERS["summary"]
    
    # ── QGIS-projektet bygges nu separat i Steg 8 ──

    t_total = time.time()
    ts_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    info.info("══════════════════════════════════════════════════════════")
    info.info("Steg 6: Landskapsgeneralisering (halo-teknik)")
    info.info("Källmapp  : %s", SRC)
    info.info("Utmapp    : %s", OUT_BASE)
    info.info("Halo      : %d px", HALO)
    info.info("Skyddade klasser: %s", sorted(PROTECTED))
    info.info("Vattenkl. (öfyllnad): %s", sorted(WATER_CLASSES))
    info.info("MMU-steg  : %s px", MMU_STEPS)
    info.info("Kernelstorlekar (modal): %s", KERNEL_SIZES)
    info.info("══════════════════════════════════════════════════════════")

    info.info("\nSteg 6a: Sieve conn4 (med halo)")
    # Steg 6 (Generalisering) läser från steg4_filled eller steg5_islands_filled (efter att små områden togs bort)
    # Kolla först om steg 5 (fylla öar) kördes
    landscape_dir = OUT_BASE / "steg5_islands_filled"
    if not landscape_dir.exists():
        landscape_dir = OUT_BASE / "steg4_filled"
    
    if not landscape_dir.exists():
        info.error("❌ Ingen input-katalog hittad. Kör Steg 1-5 först.")
        raise FileNotFoundError(f"Varken steg4_filled/ eller steg5_islands_filled/")
    
    landscape_paths = sorted(landscape_dir.glob("*.tif"))
    tile_paths = sorted((OUT_BASE / "steg1_tiles").glob("*.tif")) if (OUT_BASE / "steg1_tiles").exists() else []
    
    step5_sieve_halo(tile_paths, landscape_paths, conn=4)

    info.info("\nSteg 4b: Sieve conn8 (med halo)")
    step5_sieve_halo(tile_paths, landscape_paths, conn=8)

    info.info("\nSteg 4c: Modal filter (med halo)")
    step5_modal_halo(tile_paths, landscape_paths)

    info.info("\nSteg 4d: Semantisk generalisering (med halo)")
    step5_semantic_halo(tile_paths, landscape_paths)

    elapsed = time.time() - t_total
    info.info("══════════════════════════════════════════════════════════")
    info.info("Steg 6 KLAR  totaltid: %.0fs (%.1f min)", elapsed, elapsed / 60)
    info.info("Utdata: %s", OUT_BASE)
    info.info("════════════════════════════════════════════════════════════")
