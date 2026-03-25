"""
steg_6_generalize.py — Steg 6: Generalisering med halo-teknik.

Använder halo/överlapp vid generaliseringför att säkerställa att ytor som korsar 
tilekanter generaliseras korrekt.

HALO = 100 px på varje tilekant säkerställer att ytor ses som sammanhängande patch 
istället för två separata när de ligger på tilegränser.

Kör: python3 src/steg_6_generalize.py

Kräver: rasterio, numpy, scipy (i venv) + gdal_sieve.py + gdalbuildvrt (system)
"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window
from scipy import ndimage
from scipy.ndimage import uniform_filter

from config import OUT_BASE, SRC, QML_RECLASSIFY, GENERALIZE_PROTECTED as PROTECTED, COMPRESS, HALO, MMU_STEPS, KERNEL_SIZES, GENERALIZATION_METHODS, MORPH_SMOOTH_METHOD, MORPH_SMOOTH_RADIUS

# ══════════════════════════════════════════════════════════════════════════════
# Logging – två loggers + console
# ══════════════════════════════════════════════════════════════════════════════

_LOGGERS = {}

def _setup_logging(out_base: Path):
    """Skapar två loggfiler:
      debug   – alla level (DEBUG+)  → log/debug_steg_N_namn_ts.log
      summary – INFO+                → summary/summary_steg_N_namn_ts.log + console
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
# Dessa värden importeras från config.py och bör inte omdefinieras här

NODATA_TMP    = 65535

STRUCT_4 = np.array([[0, 1, 0],
                     [1, 1, 1],
                     [0, 1, 0]], dtype=bool)

# ══════════════════════════════════════════════════════════════════════════════
# Hjälpfunktioner
# ══════════════════════════════════════════════════════════════════════════════

def copy_qml(tif_path: Path):
    if QML_RECLASSIFY.exists():
        shutil.copy2(QML_RECLASSIFY, tif_path.with_suffix(".qml"))
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


# ── Steg 3e: Morfologisk utjämning ───────────────────────────────────────────

def morph_label() -> str:
    """Returnerar katalog-/lagernamnssuffix för aktiv morph-konfiguration.
    Ex: 'morph_disk_r02', 'morph_close_r02', eller '' om metod='none'.
    """
    if MORPH_SMOOTH_METHOD == "none":
        return ""
    _short = {"disk_modal": "disk", "closing": "close"}
    m = _short.get(MORPH_SMOOTH_METHOD, MORPH_SMOOTH_METHOD)
    return f"morph_{m}_r{MORPH_SMOOTH_RADIUS:02d}"


def _create_disk_footprint(radius: int) -> np.ndarray:
    """Skapar ett cirkulärt bool-strukturelement med angiven radie."""
    r = radius
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    return (x ** 2 + y ** 2 <= r ** 2)


def apply_morph_smooth(data: np.ndarray) -> np.ndarray:
    """Applicerar morfologisk utjämning på ett klassificerat raster.

    Metod styrs av MORPH_SMOOTH_METHOD och MORPH_SMOOTH_RADIUS (config).

    disk_modal:
        Disk-formad majority-filter. Varje pixel tilldelas den klass som
        dominerar inom en cirkelformad grannskapsradie. Snabb (konvolution
        per klass), naturligt rundar pixeltrappor.

    closing:
        Binär morphologisk closing per klass (sorterat stigande area →
        den störste klass vinner vid konflikter). Fyller konkava notchar
        längs klassgränser utan att ta bort konvexa utskjutningar.
    """
    method = MORPH_SMOOTH_METHOD
    radius = MORPH_SMOOTH_RADIUS
    log.debug("apply_morph_smooth: method=%s radius=%d  data=%s", method, radius, data.shape)
    prot_mask = np.isin(data, list(PROTECTED))

    if method == "disk_modal":
        from scipy.ndimage import convolve
        footprint = _create_disk_footprint(radius).astype(np.float32)
        vote_data = data.copy()
        vote_data[prot_mask] = 0
        classes = [int(c) for c in np.unique(vote_data) if c > 0]
        best_count = np.full(data.shape, -1.0, dtype=np.float32)
        best_class = np.zeros(data.shape, dtype=np.int32)
        for cls in classes:
            mask = (vote_data == cls).astype(np.float32)
            count = convolve(mask, footprint, mode="nearest")
            # Liten bonus för befintlig klass → undviker onödig ändring
            count = count + mask * 1e-4
            upd = count > best_count
            best_count = np.where(upd, count, best_count)
            best_class = np.where(upd, cls, best_class)
        result = best_class.astype(data.dtype)
        result[prot_mask] = data[prot_mask]
        result[data == 0] = 0

    elif method == "closing":
        from scipy.ndimage import binary_closing
        footprint = _create_disk_footprint(radius)
        result = data.copy()
        # Sortera stigande på area → stor klass skrivs sist och vinner konflikter
        classes = sorted(
            [int(c) for c in np.unique(data) if c > 0 and c not in PROTECTED],
            key=lambda c: int(np.sum(data == c))
        )
        for cls in classes:
            mask = (data == cls)
            closed = binary_closing(mask, structure=footprint)
            # Nyupptagna pixlar: closing expanderade hit men originalet hade inte cls
            new_px = closed & ~mask & ~prot_mask
            result[new_px] = cls
        result[prot_mask] = data[prot_mask]
        result[data == 0] = 0

    else:
        return data.copy()

    changed = int(np.sum(result != data))
    log.debug("apply_morph_smooth klar: %d px ändrade (%.2f%%)", changed, changed / data.size * 100)
    return result


def _morph_tile_worker(args):
    """Worker för ProcessPoolExecutor: kör morfologisk utjämning på en tile."""
    prev_vrt, tile, out_path = Path(args[0]), Path(args[1]), Path(args[2])
    if out_path.exists():
        return str(out_path), 0
    padded, tile_meta, inner = read_with_halo(prev_vrt, tile)
    tile_meta.update(compress=COMPRESS)
    with rasterio.open(tile) as _src:
        orig = _src.read(1)
    result = apply_morph_smooth(padded)[inner]
    changed = int(np.sum(result != orig))
    with rasterio.open(out_path, "w", **tile_meta) as dst:
        dst.write(result, 1)
    copy_qml(out_path)
    return str(out_path), changed


def step5_morph_halo(base_method_dir: str, tile_paths: list):
    """Applicerar morfologisk utjämning på output från en generaliserings-
    metod (t.ex. 'conn4' eller 'modal'). Output sparas i
    steg_6_generalize/{base_method_dir}_{morph_label()}/
    """
    label = morph_label()
    if not label:
        return

    src_dir = OUT_BASE / "steg_6_generalize" / base_method_dir
    if not src_dir.exists():
        log.warning("step5_morph_halo: källkatalog saknas: %s", src_dir)
        return

    src_tifs = sorted(src_dir.glob("*.tif"))
    if not src_tifs:
        log.warning("step5_morph_halo: inga tif-filer i %s", src_dir)
        return

    out_dir = OUT_BASE / "steg_6_generalize" / f"{base_method_dir}_{label}"
    out_dir.mkdir(parents=True, exist_ok=True)

    vrt_src = OUT_BASE / f"_morph_{base_method_dir}_src.vrt"
    build_vrt(src_tifs, vrt_src)

    t0 = time.time()
    info.info("Steg 6 Morph (%s → %s_%s): %d tiles (halo=%dpx, radius=%dpx)",
              MORPH_SMOOTH_METHOD, base_method_dir, label, len(tile_paths), HALO, MORPH_SMOOTH_RADIUS)

    task_args = [
        (str(vrt_src), str(tile),
         str(out_dir / f"{tile.stem}_{label}.tif"))
        for tile in tile_paths
    ]
    total_changed = 0
    with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
        for out_path_str, changed in executor.map(_morph_tile_worker, task_args):
            total_changed += changed

    vrt_src.unlink(missing_ok=True)
    elapsed = time.time() - t0
    info.info("Steg 6 Morph %s_%s KLAR: %d px ändrade  %.1fs",
              base_method_dir, label, total_changed, elapsed)


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
# Steg 4: Generalisering med halo – steg-för-steg över alla tiles
# ══════════════════════════════════════════════════════════════════════════════

# Antal parallella processer — lämna 2 kärnor fria för OS/IO
N_WORKERS = max(1, (os.cpu_count() or 1) - 2)


def _sieve_tile_worker(args):
    """Worker för ProcessPoolExecutor: kör ett sieve-pass på en tile."""
    prev_vrt, tile, out_path = Path(args[0]), Path(args[1]), Path(args[2])
    mmu, conn = args[3], args[4]
    if out_path.exists():
        with rasterio.open(tile) as _src:
            orig = _src.read(1)
        return str(out_path), 0, orig.shape
    padded, tile_meta, inner = read_with_halo(prev_vrt, tile)
    tile_meta.update(compress=COMPRESS)
    with rasterio.open(tile) as _src:
        orig = _src.read(1)
    result  = run_sieve(padded, mmu, conn)[inner]
    changed = int(np.sum(result != orig))
    tile_meta.update(compress=COMPRESS)
    with rasterio.open(out_path, "w", **tile_meta) as dst:
        dst.write(result, 1)
    copy_qml(out_path)
    return str(out_path), changed, orig.shape


def _modal_tile_worker(args):
    """Worker för ProcessPoolExecutor: kör ett modal-pass på en tile."""
    prev_vrt, tile, out_path = Path(args[0]), Path(args[1]), Path(args[2])
    k = args[3]
    if out_path.exists():
        return str(out_path), 0
    padded, tile_meta, inner = read_with_halo(prev_vrt, tile)
    tile_meta.update(compress=COMPRESS)
    with rasterio.open(tile) as _src:
        orig = _src.read(1)
    result  = modal_filter_once(padded, k)[inner]
    changed = int(np.sum(result != orig))
    with rasterio.open(out_path, "w", **tile_meta) as dst:
        dst.write(result, 1)
    copy_qml(out_path)
    return str(out_path), changed


def _semantic_tile_worker(args):
    """Worker för ProcessPoolExecutor: kör ett semantic-pass på en tile."""
    prev_vrt, tile, out_path = Path(args[0]), Path(args[1]), Path(args[2])
    mmu = args[3]
    if out_path.exists():
        return str(out_path), 0
    padded, tile_meta, inner = read_with_halo(prev_vrt, tile)
    tile_meta.update(compress=COMPRESS)
    with rasterio.open(tile) as _src:
        orig = _src.read(1)
    result  = eliminate_small_semantic(padded, mmu)[inner]
    changed = int(np.sum(result != orig))
    with rasterio.open(out_path, "w", **tile_meta) as dst:
        dst.write(result, 1)
    copy_qml(out_path)
    return str(out_path), changed


def step5_sieve_halo(tile_paths: list[Path], filled_paths: list[Path], conn: int):
    label    = f"conn{conn}"
    out_dir = OUT_BASE / "steg_6_generalize" / label
    out_dir.mkdir(parents=True, exist_ok=True)
    t0_step  = time.time()

    src_dir  = filled_paths[0].parent.name if filled_paths else "input"
    prev_vrt = OUT_BASE / f"{src_dir}_mosaic.vrt"
    if not prev_vrt.exists():
        build_vrt(filled_paths, prev_vrt)

    info.info("Steg 6 Sieve-%s: %d MMU-steg x %d tiles (halo=%dpx)",
              label, len(MMU_STEPS), len(tile_paths), HALO)

    for mmu in MMU_STEPS:
        step_outputs  = []
        t0            = time.time()
        total_changed = 0
        log.debug("%s mmu=%d: startar", label, mmu)

        task_args = [
            (str(prev_vrt), str(tile),
             str(out_dir / f"{tile.stem}_{label}_mmu{mmu:03d}.tif"),
             mmu, conn)
            for tile in tile_paths
        ]
        with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
            for out_path_str, changed, _ in executor.map(_sieve_tile_worker, task_args):
                step_outputs.append(Path(out_path_str))
                total_changed += changed

        step_vrt = out_dir / f"_vrt_mmu{mmu:03d}.vrt"
        build_vrt(step_outputs, step_vrt)
        prev_vrt = step_vrt
        elapsed  = time.time() - t0
        info.info("  %-10s mmu=%3dpx  totalt %9d px ändrade  %.1fs",
                  label, mmu, total_changed, elapsed)

    # Rensa intermediära filer — behåll bara det högsta MMU-steget
    last_mmu = max(MMU_STEPS)
    for tif in out_dir.glob("*.tif"):
        if f"_mmu{last_mmu:03d}" not in tif.stem:
            tif.unlink()
            log.debug("  Rensat intermediate: %s", tif.name)
    for vrt in out_dir.glob("_vrt_mmu*.vrt"):
        vrt.unlink()
    log.debug("  Behåller endast mmu%03d", last_mmu)

    _elapsed = time.time() - t0_step
    info.info("Steg 6 Sieve-%s KLAR  %.1f min (%.0fs)", label, _elapsed / 60, _elapsed)


def step5_modal_halo(tile_paths: list[Path], filled_paths: list[Path]):
    out_dir  = OUT_BASE / "steg_6_generalize" / "modal"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0_step = time.time()

    src_dir  = filled_paths[0].parent.name if filled_paths else "input"
    prev_vrt = OUT_BASE / f"{src_dir}_mosaic.vrt"
    if not prev_vrt.exists():
        build_vrt(filled_paths, prev_vrt)

    info.info("Steg 6 Modal: %d kernelstorlekar × %d tiles (halo=%dpx)",
              len(KERNEL_SIZES), len(tile_paths), HALO)

    for k in KERNEL_SIZES:
        step_outputs  = []
        t0            = time.time()
        total_changed = 0
        log.debug("modal k=%d: startar", k)

        task_args = [
            (str(prev_vrt), str(tile),
             str(out_dir / f"{tile.stem}_modal_k{k:02d}.tif"),
             k)
            for tile in tile_paths
        ]
        with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
            for out_path_str, changed in executor.map(_modal_tile_worker, task_args):
                step_outputs.append(Path(out_path_str))
                total_changed += changed

        step_vrt = out_dir / f"_vrt_k{k:02d}.vrt"
        build_vrt(step_outputs, step_vrt)
        prev_vrt = step_vrt
        elapsed  = time.time() - t0
        info.info("  modal      k=%2d          totalt %9d px ändrade  %.1fs",
                  k, total_changed, elapsed)

    for vrt in out_dir.glob("_vrt_k*.vrt"):
        vrt.unlink()

    _elapsed = time.time() - t0_step
    info.info("Steg 6 Modal KLAR  %.1f min (%.0fs)", _elapsed / 60, _elapsed)


def step5_semantic_halo(tile_paths: list[Path], filled_paths: list[Path]):
    out_dir = OUT_BASE / "steg_6_generalize" / "semantic"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0_step = time.time()

    src_dir  = filled_paths[0].parent.name if filled_paths else "input"
    prev_vrt = OUT_BASE / f"{src_dir}_mosaic.vrt"
    if not prev_vrt.exists():
        build_vrt(filled_paths, prev_vrt)

    info.info("Steg 6 Semantisk: %d MMU-steg × %d tiles (halo=%dpx)",
              len(MMU_STEPS), len(tile_paths), HALO)

    for mmu in MMU_STEPS:
        step_outputs  = []
        t0            = time.time()
        total_changed = 0
        log.debug("semantic mmu=%d: startar", mmu)

        task_args = [
            (str(prev_vrt), str(tile),
             str(out_dir / f"{tile.stem}_semantic_mmu{mmu:03d}.tif"),
             mmu)
            for tile in tile_paths
        ]
        with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
            for out_path_str, changed in executor.map(_semantic_tile_worker, task_args):
                step_outputs.append(Path(out_path_str))
                total_changed += changed

        step_vrt = out_dir / f"_vrt_mmu{mmu:03d}.vrt"
        build_vrt(step_outputs, step_vrt)
        prev_vrt = step_vrt
        elapsed  = time.time() - t0
        info.info("  semantic   mmu=%3dpx  totalt %9d px ändrade  %.1fs",
                  mmu, total_changed, elapsed)

    _elapsed = time.time() - t0_step
    info.info("Steg 6 Semantisk KLAR  %.1f min (%.0fs)", _elapsed / 60, _elapsed)


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
    info.info("Steg 6: Generalisering (halo-teknik)")
    info.info("Källmapp  : %s", SRC)
    info.info("Utmapp    : %s", OUT_BASE)
    info.info("Halo      : %d px", HALO)
    info.info("Skyddade klasser: %s", sorted(PROTECTED))
    info.info("MMU-steg  : %s px", MMU_STEPS)
    info.info("Kernelstorlekar (modal): %s", KERNEL_SIZES)
    info.info("Aktiva generaliseringsmetoder: %s", sorted(GENERALIZATION_METHODS))
    info.info("Morfologisk utjämning : metod=%s  radie=%d px", MORPH_SMOOTH_METHOD, MORPH_SMOOTH_RADIUS)
    info.info("══════════════════════════════════════════════════════════")

    # Rensa inaktuella metod-mappar (metoder som tagits bort från config)
    import shutil
    all_methods = {"conn4", "conn8", "modal", "semantic"}
    for method in all_methods - GENERALIZATION_METHODS:
        stale_dir = OUT_BASE / "steg_6_generalize" / method
        if stale_dir.exists():
            shutil.rmtree(stale_dir)
            info.info("  Raderat inaktuell metod-mapp: %s", stale_dir.name)

    # Rensa inaktuella MMU-filer inom aktiva sieve-mappar
    active_mmu_labels = {f"_mmu{mmu:03d}" for mmu in MMU_STEPS}
    for conn in ("conn4", "conn8"):
        if conn not in GENERALIZATION_METHODS:
            continue
        sieve_dir = OUT_BASE / "steg_6_generalize" / conn
        if not sieve_dir.exists():
            continue
        for tif in sieve_dir.glob("*.tif"):
            if not any(lbl in tif.stem for lbl in active_mmu_labels):
                tif.unlink()
                info.info("  Raderat inaktuell MMU-fil: %s", tif.name)

    # Rensa inaktuella kernel-filer inom aktiv modal-mapp
    active_k_labels = {f"_k{k:02d}" for k in KERNEL_SIZES}
    modal_dir = OUT_BASE / "steg_6_generalize" / "modal"
    if modal_dir.exists():
        for tif in modal_dir.glob("*.tif"):
            if not any(lbl in tif.stem for lbl in active_k_labels):
                tif.unlink()
                info.info("  Raderat inaktuell kernel-fil: %s", tif.name)

    # Steg 6 (Generalisering) läser från steg_4_filter_lakes eller steg_5_filter_islands (efter att små områden togs bort)
    # Kolla först om steg 5 (fylla öar) kördes
    landscape_dir = OUT_BASE / "steg_5_filter_islands"
    if not landscape_dir.exists():
        landscape_dir = OUT_BASE / "steg_4_filter_lakes"
    if not landscape_dir.exists():
        landscape_dir = OUT_BASE / "steg_3_dissolve"

    if not landscape_dir.exists():
        info.error("❌ Ingen input-katalog hittad. Kör Steg 1-5 först.")
        raise FileNotFoundError(f"Varken steg_4_filter_lakes/ eller steg_5_filter_islands/")

    landscape_paths = sorted(landscape_dir.glob("*.tif"))
    tile_paths = sorted((OUT_BASE / "steg_1_reclassify").glob("*.tif")) if (OUT_BASE / "steg_1_reclassify").exists() else []

    # Kör bara aktiverade generaliseringsmetoder
    if "conn4" in GENERALIZATION_METHODS:
        info.info("\nSteg 6: Sieve conn4 (med halo)")
        step5_sieve_halo(tile_paths, landscape_paths, conn=4)

    if "conn8" in GENERALIZATION_METHODS:
        info.info("\nSteg 6: Sieve conn8 (med halo)")
        step5_sieve_halo(tile_paths, landscape_paths, conn=8)

    if "modal" in GENERALIZATION_METHODS:
        info.info("\nSteg 6: Modal filter (med halo)")
        step5_modal_halo(tile_paths, landscape_paths)

    if "semantic" in GENERALIZATION_METHODS:
        info.info("\nSteg 6: Semantisk eliminering (med halo)")
        step5_semantic_halo(tile_paths, landscape_paths)

    # ── Morfologisk utjämning (sista pass, om aktiverad) ─────────────────
    if MORPH_SMOOTH_METHOD != "none":
        info.info("\nSteg 6: Morfologisk utjämning (%s, r=%d px)", MORPH_SMOOTH_METHOD, MORPH_SMOOTH_RADIUS)
        # Kör på varje aktiverad metods slutoutput
        _morph_sources = []
        if "conn4" in GENERALIZATION_METHODS:
            _morph_sources.append("conn4")
        if "conn8" in GENERALIZATION_METHODS:
            _morph_sources.append("conn8")
        if "modal" in GENERALIZATION_METHODS:
            _morph_sources.append("modal")
        if "semantic" in GENERALIZATION_METHODS:
            _morph_sources.append("semantic")
        for src in _morph_sources:
            step5_morph_halo(src, tile_paths)

    elapsed = time.time() - t_total
    info.info("══════════════════════════════════════════════════════════")
    info.info("Steg 6 KLART  totaltid: %.0fs (%.1f min)", elapsed, elapsed / 60)
    info.info("Utdata: %s", OUT_BASE)
    info.info("════════════════════════════════════════════════════════════")
