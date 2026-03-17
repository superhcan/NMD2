#!/usr/bin/env python3
"""
steg_9_overlay_buildings.py — Step 9: Overlay buildings from steg 2 onto steg 8.

Extracts building pixels (class 51) from steg2_extracted rasters, vectorizes them
and merges the building polygons into each steg8_simplified GPKG, producing
combined landscape + buildings output in steg9_with_buildings/.

Run: python3 src/steg_9_overlay_buildings.py
"""

import logging
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio

from config import OUT_BASE

BUILDING_CLASS = 51
LN = "markslag"


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
    """
    tifs = sorted(steg2_dir.glob("*.tif"))
    if not tifs:
        log.warning("No TIF files found in steg2_extracted")
        return None

    log.info("  Masking %d tiles to class %d...", len(tifs), BUILDING_CLASS)
    masked_tifs = []
    for tif in tifs:
        masked = tmp_dir / f"mask_{tif.name}"
        with rasterio.open(tif) as src:
            data = src.read(1)
            out_data = np.where(data == BUILDING_CLASS, BUILDING_CLASS, 0).astype(np.uint16)
            profile = src.profile.copy()
            profile.update(dtype=rasterio.uint16, nodata=0)
            with rasterio.open(masked, "w", **profile) as dst:
                dst.write(out_data, 1)
        masked_tifs.append(masked)

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


def merge_buildings(buildings_gpkg, steg8_dir, out_dir, log):
    """
    For each GPKG in steg8_dir: copy → out_dir, then append building polygons
    to the same layer. Returns number of successfully produced files.
    """
    gpkgs = sorted(steg8_dir.glob("*.gpkg"))
    if not gpkgs:
        log.warning("No GPKG files found in steg8_simplified")
        return 0

    count = 0
    for gpkg in gpkgs:
        out_gpkg = out_dir / gpkg.name
        if out_gpkg.exists():
            out_gpkg.unlink()
        shutil.copy2(gpkg, out_gpkg)

        r = subprocess.run(
            [
                "ogr2ogr", "-f", "GPKG", "-append",
                "-nln", gpkg.stem,
                str(out_gpkg), str(buildings_gpkg),
            ],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            sz = out_gpkg.stat().st_size / 1e6
            log.info("  ✓ %s (%.1f MB)", out_gpkg.name, sz)
            count += 1
        else:
            log.warning("  ✗ %s: %s", out_gpkg.name, r.stderr.strip())

    return count


if __name__ == "__main__":
    log = setup_logging(OUT_BASE)
    t0 = time.time()

    steg2_dir = OUT_BASE / "steg2_extracted"
    steg8_dir = OUT_BASE / "steg8_simplified"
    out_dir   = OUT_BASE / "steg9_with_buildings"
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

        log.info("Step 2: Merge buildings into steg 8 outputs...")
        n = merge_buildings(buildings_gpkg, steg8_dir, out_dir, log)

        elapsed = time.time() - t0
        log.info("")
        log.info("══════════════════════════════════════════════════════════")
        log.info("Step 9 DONE — %d files created (%.1fs)", n, elapsed)
        log.info("══════════════════════════════════════════════════════════")

    finally:
        shutil.rmtree(tmp_dir)
