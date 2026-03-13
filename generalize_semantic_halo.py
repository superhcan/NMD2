"""
generalize_semantic_halo.py — Steg 5d: Semantisk generalisering med halo.

Kör semantiskt-medveten generalisering över alla MMU-steg, med halo-overlap
för korrekt generalisering över tilekanter.
"""

import logging
import subprocess
import time
from pathlib import Path
import heapq

import numpy as np
import rasterio
from rasterio.windows import Window
from scipy import ndimage

from config import (
    OUT_BASE, HALO, COMPRESS, PROTECTED, MMU_STEPS, STRUCT_4
)

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")


def copy_qml(tif_path: Path):
    """Kopiera referens-QML-fil till TIF-filen."""
    from config import QML_SRC
    import shutil
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
    """
    with rasterio.open(vrt_path) as vrt, rasterio.open(tile_path) as tile:
        vt = vrt.transform
        tt = tile.transform
        px = vt.a
        py = vt.e

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


# ── Semantisk klassificering ──

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
    """Eliminera små patches via semantisk sampling."""
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


def generalize_semantic_halo(filled_paths: list[Path]):
    """Köra semantisk generalisering med halo over tiles."""
    out_dir = OUT_BASE / "generalized_semantic"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0_step = time.time()

    prev_vrt = OUT_BASE / "filled_mosaic.vrt"
    if not prev_vrt.exists():
        build_vrt(filled_paths, prev_vrt)

    info.info("Steg 5d semantisk: %d MMU-steg × %d tiles (halo=%dpx)",
              len(MMU_STEPS), len(filled_paths), HALO)

    for mmu in MMU_STEPS:
        step_outputs  = []
        t0            = time.time()
        total_changed = 0
        log.debug("semantic mmu=%d: startar", mmu)

        for filled_tile in filled_paths:
            stem     = filled_tile.stem
            out_path = out_dir / f"{stem}_semantic_mmu{mmu:03d}.tif"
            if out_path.exists():
                log.debug("  %s hoppar (finns redan)", out_path.name)
                step_outputs.append(out_path)
                continue

            t1 = time.time()
            padded, tile_meta, inner = read_with_halo(prev_vrt, filled_tile)
            tile_meta.update(compress=COMPRESS)

            with rasterio.open(filled_tile) as _src:
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

    info.info("Steg 5d semantisk KLAR  %.1fs", time.time() - t0_step)


if __name__ == "__main__":
    from logging_setup import setup_logging
    setup_logging(OUT_BASE)
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    print("Denna modul anropas från pipeline.py")
