#!/usr/bin/env python3
"""
steg_7_vectorize.py — Steg 7: Vektorisering av generaliserat raster.

Läser generaliserade raster från Steg 6 (CONN4, CONN8, modal, semantic) 
och konverterar dem till GeoPackage-vektorer med GDAL.

Processas:
  - CONN4 MMU008
  - CONN8 MMU008
  - MODAL K15

Kör: python3 src/steg_7_vectorize.py

Kräver: GDAL/OGR, rasterio, shapely
"""
import logging
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

from config import OUT_BASE, GENERALIZATION_METHODS, MMU_STEPS, KERNEL_SIZES

_LOG = None

def _setup_logging(out_base):
    global _LOG
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
    
    debug_log = log_dir / f"debug_{step_suffix}.log"
    summary_log = summary_dir / f"summary_{step_suffix}.log"
    
    fmt_detail = logging.Formatter("%(asctime)s [%(levelname)-8s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fmt_summary = logging.Formatter("%(asctime)s [%(levelname)-6s] %(message)s", datefmt="%H:%M:%S")
    
    # Root logger for both debug and summary
    log = logging.getLogger("pipeline.vectorize")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    
    # Clear ALL handlers first
    log.handlers.clear()
    
    # Debug handler
    dbg_handler = logging.FileHandler(debug_log)
    dbg_handler.setLevel(logging.DEBUG)
    dbg_handler.setFormatter(fmt_detail)
    log.addHandler(dbg_handler)
    
    # Summary logger
    h1 = logging.FileHandler(summary_log)
    h1.setLevel(logging.INFO)
    h1.setFormatter(fmt_summary)
    log.addHandler(h1)
    
    h2 = logging.StreamHandler()
    h2.setLevel(logging.INFO)
    h2.setFormatter(fmt_summary)
    log.addHandler(h2)
    _LOG = log
    return log

PIPE = OUT_BASE
OUT = PIPE / "steg7_vectorized"
LN = "markslag"

def vectorize_sieve(conn):
    log = logging.getLogger("pipeline.vectorize")
    method = f"conn{conn}"
    in_dir = PIPE / f"steg6_generalized_{method}"
    if not in_dir.exists():
        return
    tifs = sorted(in_dir.glob("*.tif"))
    mmu_set = set()
    for tif in tifs:
        m = re.search(r'mmu(\d+)', tif.stem)
        if m:
            mmu_set.add(int(m.group(1)))
    for mmu in sorted(mmu_set):
        mmu_str = f"{mmu:03d}"
        mmu_ha = mmu * 100 / 10000
        mmu_tifs = [t for t in tifs if f"mmu{mmu_str}" in t.name]
        if not mmu_tifs:
            continue
        gpkg = OUT / f"generalized_{method}_mmu{mmu_str}.gpkg"
        if gpkg.exists():
            gpkg.unlink()
        log.info("  %s mmu=%d px (%.2f ha): %d tiles", method, mmu, mmu_ha, len(mmu_tifs))
        
        tif_str = " ".join(f'"{t}"' for t in mmu_tifs)
        vrt_tmp = f"/tmp/_vect_{method}_mmu{mmu_str}.vrt"
        shell_cmd = f'gdalbuildvrt "{vrt_tmp}" {tif_str} > /dev/null 2>&1 && gdal_polygonize.py "{vrt_tmp}" -f GPKG "{gpkg}" DN {LN} > /dev/null 2>&1; rm -f "{vrt_tmp}"'
        subprocess.run(shell_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if gpkg.exists() and gpkg.stat().st_size > 1000:
            sz = gpkg.stat().st_size / 1e6
            log.info("    ✓ %s (%.1f MB)", gpkg.name, sz)
        else:
            log.info("    ✗ failed")

def vectorize_modal():
    log = logging.getLogger("pipeline.vectorize")
    in_dir = PIPE / "steg6_generalized_modal"
    if not in_dir.exists():
        return
    tifs = sorted(in_dir.glob("*.tif"))
    kernel_set = set()
    for tif in tifs:
        m = re.search(r'_k(\d+)', tif.stem)
        if m:
            kernel_set.add(int(m.group(1)))
    for k in sorted(kernel_set):
        k_str = f"{k:02d}"
        eff_mmu = k * k // 2
        k_tifs = [t for t in tifs if f"_k{k_str}" in t.name and t.name.endswith('.tif')]
        if not k_tifs:
            continue
        gpkg = OUT / f"generalized_modal_k{k_str}.gpkg"
        if gpkg.exists():
            gpkg.unlink()
        log.info("  modal k=%d (eff. MMU ≈ %d px): %d tiles", k, eff_mmu, len(k_tifs))
        
        tif_str = " ".join(f'"{t}"' for t in k_tifs)
        vrt_tmp = f"/tmp/_vect_modal_k{k_str}.vrt"
        shell_cmd = f'gdalbuildvrt "{vrt_tmp}" {tif_str} > /dev/null 2>&1 && gdal_polygonize.py "{vrt_tmp}" -f GPKG "{gpkg}" DN {LN} > /dev/null 2>&1; rm -f "{vrt_tmp}"'
        subprocess.run(shell_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if gpkg.exists() and gpkg.stat().st_size > 1000:
            sz = gpkg.stat().st_size / 1e6
            log.info("    ✓ %s (%.1f MB)", gpkg.name, sz)
        else:
            log.info("    ✗ failed")

def vectorize_semantic():
    log = logging.getLogger("pipeline.vectorize")
    in_dir = PIPE / "steg6_generalized_semantic"
    if not in_dir.exists():
        return
    tifs = sorted(in_dir.glob("*.tif"))
    mmu_set = set()
    for tif in tifs:
        m = re.search(r'mmu(\d+)', tif.stem)
        if m:
            mmu_set.add(int(m.group(1)))
    for mmu in sorted(mmu_set):
        mmu_str = f"{mmu:03d}"
        mmu_ha = mmu * 100 / 10000
        mmu_tifs = [t for t in tifs if f"semantic_mmu{mmu_str}" in t.name]
        if not mmu_tifs:
            continue
        gpkg = OUT / f"generalized_semantic_mmu{mmu_str}.gpkg"
        if gpkg.exists():
            gpkg.unlink()
        log.info("  semantic mmu=%d px (%.2f ha): %d tiles", mmu, mmu_ha, len(mmu_tifs))
        
        tif_str = " ".join(f'"{t}"' for t in mmu_tifs)
        vrt_tmp = f"/tmp/_vect_semantic_mmu{mmu_str}.vrt"
        shell_cmd = f'gdalbuildvrt "{vrt_tmp}" {tif_str} > /dev/null 2>&1 && gdal_polygonize.py "{vrt_tmp}" -f GPKG "{gpkg}" DN {LN} > /dev/null 2>&1; rm -f "{vrt_tmp}"'
        subprocess.run(shell_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if gpkg.exists() and gpkg.stat().st_size > 1000:
            sz = gpkg.stat().st_size / 1e6
            log.info("    ✓ %s (%.1f MB)", gpkg.name, sz)
        else:
            log.info("    ✗ failed")

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    log = _setup_logging(OUT_BASE)
    t0 = time.time()
    
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 7: Vektorisering av generaliserat raster")
    log.info("Källmapp : %s", PIPE)
    log.info("Utmapp   : %s", OUT)
    log.info("Aktiva metoder: %s", sorted(GENERALIZATION_METHODS))
    log.info("══════════════════════════════════════════════════════════")

    # Rensa inaktuella gpkg-filer (metoder som tagits bort från config)
    import shutil
    all_methods = {"conn4", "conn8", "modal", "semantic"}
    for method in all_methods - GENERALIZATION_METHODS:
        for stale in OUT.glob(f"generalized_{method}_*.gpkg"):
            stale.unlink()
            log.info("  Raderat inaktuell metod-fil: %s", stale.name)

    # Rensa gpkg för inaktuella MMU-värden inom aktiva sieve-metoder
    active_mmu_labels = {f"mmu{mmu:03d}" for mmu in MMU_STEPS}
    for conn in ("conn4", "conn8"):
        if conn not in GENERALIZATION_METHODS:
            continue
        for gpkg in OUT.glob(f"generalized_{conn}_mmu*.gpkg"):
            mmu_part = re.search(r'mmu(\d+)', gpkg.stem)
            if mmu_part and f"mmu{int(mmu_part.group(1)):03d}" not in active_mmu_labels:
                gpkg.unlink()
                log.info("  Raderat inaktuell MMU-fil: %s", gpkg.name)

    # Rensa gpkg för inaktuella kernel-värden inom aktiv modal
    active_k_labels = {f"k{k:02d}" for k in KERNEL_SIZES}
    if "modal" in GENERALIZATION_METHODS:
        for gpkg in OUT.glob("generalized_modal_k*.gpkg"):
            k_part = re.search(r'_k(\d+)', gpkg.stem)
            if k_part and f"k{int(k_part.group(1)):02d}" not in active_k_labels:
                gpkg.unlink()
                log.info("  Raderat inaktuell kernel-fil: %s", gpkg.name)

    # Vektorisera endast aktiverade metoder
    if "conn4" in GENERALIZATION_METHODS:
        log.info("\nCONN4")
        vectorize_sieve(4)
    
    if "conn8" in GENERALIZATION_METHODS:
        log.info("\nCONN8")
        vectorize_sieve(8)
    
    if "modal" in GENERALIZATION_METHODS:
        log.info("\nModal filter")
        vectorize_modal()
    
    if "semantic" in GENERALIZATION_METHODS:
        log.info("\nSemantisk generalisering")
        # Denna funktion är bara en stub i nuläget - modal är prioriterad
        log.warning("  ⚠ Semantic vektorisering ännu ej implementerad")
    
    elapsed = time.time() - t0
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 7 KLAR: %.0fs (%.1f min)", elapsed, elapsed / 60)
    log.info("GeoPackage-filer: %s", OUT)
    log.info("══════════════════════════════════════════════════════════")
