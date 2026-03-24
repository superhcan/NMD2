#!/usr/bin/env python3
"""
steg_9_overlay_buildings.py — Step 9: Overlay buildings from steg 2 onto steg 8.

Extracts building pixels (class 51) from steg_2_extract rasters, vectorizes them
and integrerar byggnadspolygonerna i landskapslagret utan överlapp:
  1. Klipper ut byggnadsytan ur landskapspolygonerna (difference)
  2. Slår ihop det klippta landskapet + byggnadspolygonerna → ett sömlöst lager

Parallellisering:
  - Tile-maskning:   multiprocessing.Pool (N kärnor)
  - Difference-steg: STRtree (lokala kandidater per polygon) + multiprocessing.Pool
                     Globals delas via Linux fork/COW utan kopiering.

Run: python3 src/steg_9_overlay_buildings.py
"""

import logging
import multiprocessing as mp
import os
import subprocess
import tempfile
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from shapely.ops import unary_union
from shapely.strtree import STRtree

from config import OUT_BASE

BUILDING_CLASS = 51
LN = "markslag"
N_WORKERS = mp.cpu_count()

# ─── Module-level globals — sätts i main-processen INNAN Pool skapas. ───────
# Med fork (Linux default) ärvs de COW i worker-processer utan kopiering.
_BGEOMS: np.ndarray | None = None      # numpy-array av shapely-byggnadsgeometrier
_LGEOMS: np.ndarray | None = None      # numpy-array av shapely-landskapsgeometrier
_CANDIDATES: list | None = None        # lista av np.int64-arrays, en per landskapspolygon


# ─── Parallella worker-funktioner (modul-nivå → picklable) ──────────────────

def _mask_tile(args: tuple) -> str:
    """Worker: maskerar ett raster-tile till BUILDING_CLASS, nollställer övrigt."""
    tif_str, masked_str, building_class = args
    import numpy as _np
    import rasterio as _rio
    with _rio.open(tif_str) as src:
        data = src.read(1)
        out = _np.where(data == building_class, building_class, 0).astype(_np.uint16)
        profile = src.profile.copy()
        profile.update(dtype=_rio.uint16, nodata=0)
    with _rio.open(masked_str, "w", **profile) as dst:
        dst.write(out, 1)
    return masked_str


def _clip_chunk(span: tuple) -> list:
    """Worker: beräknar difference för landscape[start:end].

    Läser globals _LGEOMS, _BGEOMS, _CANDIDATES (ärvda via fork, ingen kopiering).
    Returnerar lista av shapely-geometrier (klipta/oförändrade).
    """
    start, end = span
    out = []
    for i in range(start, end):
        geom = _LGEOMS[i]
        b_idxs = _CANDIDATES[i]
        if len(b_idxs) > 0:
            out.append(geom.difference(unary_union(_BGEOMS[b_idxs])))
        else:
            out.append(geom)
    return out


def setup_logging(out_base):
    """Setup step-labelled logging for Step 9."""
    log_dir = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    step_num = os.getenv("STEP_NUMBER", "9")
    step_name = os.getenv("STEP_NAME", "overlay_buildings").lower()
    step_suffix = f"steg_{step_num}_{step_name}_{ts}"

    fmt_detail = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fmt_summary = logging.Formatter(
        "%(asctime)s [%(levelname)-6s] %(message)s", datefmt="%H:%M:%S"
    )

    log = logging.getLogger("pipeline.overlay_buildings")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    log.handlers.clear()

    dbg = logging.FileHandler(str(log_dir / f"debug_{step_suffix}.log"))
    dbg.setLevel(logging.DEBUG)
    dbg.setFormatter(fmt_detail)
    log.addHandler(dbg)

    fh = logging.FileHandler(str(summary_dir / f"summary_{step_suffix}.log"))
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt_summary)
    log.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt_summary)
    log.addHandler(ch)

    return log


def vectorize_buildings(steg2_dir, tmp_dir, log):
    """
    Mask steg2 rasters to class 51 only, then vectorize to a buildings GPKG.
    Returns Path to the filtered buildings GPKG, or None on failure.
    Tile-maskningen körs parallellt med N_WORKERS processer.
    """
    tifs = sorted(steg2_dir.glob("*.tif"))
    if not tifs:
        log.warning("No TIF files found in steg2_extracted")
        return None

    log.info("  Maskar %d tiles till klass %d (%d kärnor)...", len(tifs), BUILDING_CLASS, N_WORKERS)
    mask_args = [
        (str(tif), str(tmp_dir / f"mask_{tif.name}"), BUILDING_CLASS)
        for tif in tifs
    ]
    with mp.Pool(N_WORKERS) as pool:
        masked_paths = pool.map(_mask_tile, mask_args)
    masked_tifs = [Path(p) for p in masked_paths]

    # Build VRT over all masked tiles
    vrt = tmp_dir / "buildings.vrt"
    tif_str = " ".join(f'"{t}"' for t in masked_tifs)
    r = subprocess.run(
        f'gdalbuildvrt "{vrt}" {tif_str}',
        shell=True, capture_output=True, text=True,
    )
    if r.returncode != 0:
        log.error("gdalbuildvrt failed: %s", r.stderr)
        return None

    # Vectorize
    raw_gpkg = tmp_dir / "buildings_raw.gpkg"
    r = subprocess.run(
        f'gdal_polygonize.py "{vrt}" -f GPKG "{raw_gpkg}" DN {LN}',
        shell=True, capture_output=True, text=True,
    )
    if r.returncode != 0:
        log.error("gdal_polygonize failed: %s", r.stderr)
        return None

    # Remove background (class 0) polygons
    buildings_gpkg = tmp_dir / "buildings.gpkg"
    r = subprocess.run(
        [
            "ogr2ogr", "-f", "GPKG",
            str(buildings_gpkg), str(raw_gpkg),
            "-where", f"{LN} = {BUILDING_CLASS}",
        ],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        log.error("ogr2ogr filter failed: %s", r.stderr)
        return None

    # Count features
    info = subprocess.run(
        ["ogrinfo", "-al", "-so", str(buildings_gpkg)],
        capture_output=True, text=True,
    ).stdout
    n = 0
    for line in info.splitlines():
        if "Feature Count:" in line:
            n = int(line.split(":")[-1].strip())
            break
    log.info("  ✓ %d building polygons vectorized", n)
    return buildings_gpkg


def integrate_buildings(buildings_gpkg, steg8_dir, out_dir, log):
    """
    För varje GPKG i steg8_dir:
      1. Läs byggnadspolygoner → bygg STRtree-index
      2. Läs landskapspolygoner (steg 8)
      3. Bulk-query STRtree: hitta kandidat-byggnader per landskapspolygon
      4. Parallell difference med N_WORKERS processer (globals delas via fork/COW)
      5. Konkatenera klippt landskap + byggnader → spara
    Returns antal producerade filer.
    """
    global _BGEOMS, _LGEOMS, _CANDIDATES

    gpkgs = sorted(steg8_dir.glob("*.gpkg"))
    if not gpkgs:
        log.warning("No GPKG files found in steg_8_simplify")
        return 0

    log.info("  Läser byggnadspolygoner...")
    buildings = gpd.read_file(str(buildings_gpkg))
    if LN in buildings.columns and "DN" not in buildings.columns:
        buildings = buildings.rename(columns={LN: "DN"})
    buildings = buildings[["DN", "geometry"]].copy()
    log.info("  %d byggnadspolygoner inlästa", len(buildings))

    # Bygg rumsligt index — sätts som global INNAN Pool skapas (Linux fork/COW)
    _BGEOMS = buildings.geometry.values
    tree = STRtree(_BGEOMS)
    log.info("  STRtree byggt (%d noder)", len(_BGEOMS))

    count = 0
    for gpkg in gpkgs:
        log.info("  Läser %s...", gpkg.name)
        landscape = gpd.read_file(str(gpkg))
        log.info("    %d landskapspolygoner", len(landscape))
        geom_col = landscape.geometry.name

        # Sätt global landscape-array INNAN pool-skapande
        _LGEOMS = landscape.geometry.values
        n = len(_LGEOMS)

        # Bulk STRtree-query: hitta alla (l_idx, b_idx)-par på en gång
        t_q = time.time()
        log.info("    Bulk STRtree-query (%d × %d byggnader)...", n, len(_BGEOMS))
        l_idx, b_idx = tree.query(_LGEOMS, predicate="intersects")
        log.info("    %d par funna  (%.1fs)", len(l_idx), time.time() - t_q)

        # Gruppera byggnadsindex per landskapspolygon
        groups: dict[int, list] = defaultdict(list)
        for li, bi in zip(l_idx, b_idx):
            groups[li].append(bi)
        _CANDIDATES = [
            np.array(groups[i], dtype=np.int64) if i in groups else np.empty(0, dtype=np.int64)
            for i in range(n)
        ]
        n_with_buildings = sum(1 for c in _CANDIDATES if len(c) > 0)
        log.info("    %d av %d polygoner berör byggnader", n_with_buildings, n)

        # Dela upp i lika stora chunk-intervall för Pool.map
        chunk_size = max(1, (n + N_WORKERS - 1) // N_WORKERS)
        spans = [(s, min(s + chunk_size, n)) for s in range(0, n, chunk_size)]
        log.info("    Klipper geometrier parallellt (%d chunks × %d kärnor)...", len(spans), N_WORKERS)

        t_d = time.time()
        with mp.Pool(N_WORKERS) as pool:
            chunk_results = pool.map(_clip_chunk, spans)
        new_geoms = [g for chunk in chunk_results for g in chunk]
        log.info("    Difference klar  (%.1fs)", time.time() - t_d)

        # Uppdatera landskapets geometrikolumn
        landscape_cut = landscape.copy()
        landscape_cut[geom_col] = new_geoms
        landscape_cut = landscape_cut[~landscape_cut.geometry.is_empty]
        landscape_cut = landscape_cut[landscape_cut.geometry.notna()]
        log.info("    %d polygoner efter klippning", len(landscape_cut))

        # Anpassa byggnadslagret till landskapets kolumnstruktur
        b_gdf = buildings[["DN", "geometry"]].copy()
        if geom_col != "geometry":
            b_gdf = b_gdf.rename_geometry(geom_col)
        for col in landscape_cut.columns:
            if col != geom_col and col not in b_gdf.columns:
                b_gdf[col] = None
        b_gdf = b_gdf[landscape_cut.columns].copy()

        result = pd.concat([landscape_cut, b_gdf], ignore_index=True)
        result = gpd.GeoDataFrame(result, geometry=geom_col, crs=landscape.crs)

        out_gpkg = out_dir / gpkg.name
        if out_gpkg.exists():
            out_gpkg.unlink()
        log.info("    Skriver %s...", out_gpkg.name)
        result.to_file(str(out_gpkg), driver="GPKG", layer=gpkg.stem)

        sz = out_gpkg.stat().st_size / 1e6
        log.info("  ✓ %s — %d polygoner  %.1f MB", out_gpkg.name, len(result), sz)
        count += 1

    return count


if __name__ == "__main__":
    log = setup_logging(OUT_BASE)
    t0 = time.time()

    steg2_dir = OUT_BASE / "steg_2_extract"
    steg8_dir = OUT_BASE / "steg_8_simplify"
    out_dir   = OUT_BASE / "steg_9_overlay_buildings"
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("══════════════════════════════════════════════════════════")
    log.info("Step 9: Overlay buildings from steg 2 onto steg 8")
    log.info("Source steg2 : %s", steg2_dir)
    log.info("Source steg8 : %s", steg8_dir)
    log.info("Output       : %s", out_dir)
    log.info("══════════════════════════════════════════════════════════")

    tmp_dir = Path(tempfile.mkdtemp(prefix="steg9_"))
    try:
        log.info("Step 1: Vectorize buildings (class 51) from steg 2...")
        buildings_gpkg = vectorize_buildings(steg2_dir, tmp_dir, log)
        if buildings_gpkg is None:
            log.error("Vectorization failed — aborting")
            raise SystemExit(1)

        log.info("Step 2: Integrera byggnader i steg 8 (difference + concat)...")
        n = integrate_buildings(buildings_gpkg, steg8_dir, out_dir, log)

        elapsed = time.time() - t0
        log.info("")
        log.info("══════════════════════════════════════════════════════════")
        log.info("Step 9 KLART — %d filer skapade  %.1f min (%.0fs)", n, elapsed / 60, elapsed)
        log.info("══════════════════════════════════════════════════════════")

    finally:
        import shutil
        shutil.rmtree(tmp_dir)
