#!/usr/bin/env python3
"""vectorize_pipeline_1024_halo.py — Simple shell-based vekt."""
import logging
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

_LOG = None

def _setup_logging(out_base):
    global _LOG
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = out_base / f"vectorize_summary_{ts}.log"
    log = logging.getLogger("")
    log.setLevel(logging.INFO)
    h1 = logging.FileHandler(log_path)
    h2 = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s [%(levelname)-6s] %(message)s", datefmt="%H:%M:%S")
    h1.setFormatter(fmt)
    h2.setFormatter(fmt)
    log.addHandler(h1)
    log.addHandler(h2)
    _LOG = log
    return log

PIPE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo")
OUT = PIPE / "vectorized"
LN = "markslag"

def vectorize_sieve(conn):
    log = logging.getLogger("")
    method = f"conn{conn}"
    in_dir = PIPE / f"generalized_{method}"
    if not in_dir.exists():
        return
    tifs = sorted(in_dir.glob("*.tif"))
    mmu_set = set()
    for tif in tifs:
        m = re.search(r'mmu(\d+)', tif.stem)
        if m:
            mmu_set.add(int(m.group(1)))
    for mmu in sorted(mmu_set):
        if mmu < 16:  # Skip small MMU values
            continue
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
    log = logging.getLogger("")
    in_dir = PIPE / "generalized_modal"
    if not in_dir.exists():
        return
    tifs = sorted(in_dir.glob("*.tif"))
    kernel_set = set()
    for tif in tifs:
        m = re.search(r'_k(\d+)', tif.stem)
        if m:
            kernel_set.add(int(m.group(1)))
    for k in sorted(kernel_set):
        if k != 15:  # Only process kernel 15
            continue
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
    log = logging.getLogger("")
    in_dir = PIPE / "generalized_semantic"
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
    log = _setup_logging(OUT)
    t0 = time.time()
    
    log.info("══════════════════════════════════════════════════════════")
    log.info("Vektorisering av pipeline_1024_halo-resultat")
    log.info("Källmapp: %s", PIPE)
    log.info("Utmapp  : %s", OUT)
    log.info("══════════════════════════════════════════════════════════")
    
    log.info("\nModal filter k15")
    vectorize_modal()
    
    elapsed = time.time() - t0
    log.info("══════════════════════════════════════════════════════════")
    log.info("KLAR: %.0fs (%.1f min)", elapsed, elapsed / 60)
    log.info("GeoPackage-filer: %s", OUT)
    log.info("══════════════════════════════════════════════════════════")
