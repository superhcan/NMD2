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

from config import OUT_BASE, GENERALIZATION_METHODS, MMU_STEPS, KERNEL_SIZES, MORPH_SMOOTH_METHOD, MORPH_SMOOTH_RADIUS, MORPH_ONLY

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
OUT = PIPE / "steg_7_vectorize"
LN = "markslag"

def vectorize_sieve(conn):
    log = logging.getLogger("pipeline.vectorize")
    method = f"conn{conn}"
    in_dir = PIPE / "steg_6_generalize" / method
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
        
        vrt_tmp = f"/tmp/_vect_{method}_mmu{mmu_str}.vrt"
        file_list_tmp = f"/tmp/_vect_{method}_mmu{mmu_str}.txt"
        with open(file_list_tmp, "w") as fh:
            fh.write("\n".join(str(t) for t in mmu_tifs))
        conn_flag = "-8" if conn == 8 else ""
        subprocess.run(["gdalbuildvrt", "-input_file_list", file_list_tmp, vrt_tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        polygonize_cmd = ["gdal_polygonize.py", vrt_tmp]
        if conn_flag:
            polygonize_cmd.append(conn_flag)
        polygonize_cmd += ["-f", "GPKG", str(gpkg), "DN", LN]
        subprocess.run(polygonize_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import os as _os; _os.unlink(vrt_tmp) if _os.path.exists(vrt_tmp) else None; _os.unlink(file_list_tmp) if _os.path.exists(file_list_tmp) else None
        if gpkg.exists() and gpkg.stat().st_size > 1000:
            sz = gpkg.stat().st_size / 1e6
            log.info("    ✓ %s (%.1f MB)", gpkg.name, sz)
        else:
            log.info("    ✗ failed")

def vectorize_modal():
    log = logging.getLogger("pipeline.vectorize")
    in_dir = PIPE / "steg_6_generalize" / "modal"
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
        
        vrt_tmp = f"/tmp/_vect_modal_k{k_str}.vrt"
        file_list_tmp = f"/tmp/_vect_modal_k{k_str}.txt"
        with open(file_list_tmp, "w") as fh:
            fh.write("\n".join(str(t) for t in k_tifs))
        subprocess.run(["gdalbuildvrt", "-input_file_list", file_list_tmp, vrt_tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["gdal_polygonize.py", vrt_tmp, "-f", "GPKG", str(gpkg), "DN", LN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import os as _os; _os.unlink(vrt_tmp) if _os.path.exists(vrt_tmp) else None; _os.unlink(file_list_tmp) if _os.path.exists(file_list_tmp) else None
        if gpkg.exists() and gpkg.stat().st_size > 1000:
            sz = gpkg.stat().st_size / 1e6
            log.info("    ✓ %s (%.1f MB)", gpkg.name, sz)
        else:
            log.info("    ✗ failed")

def vectorize_semantic():
    log = logging.getLogger("pipeline.vectorize")
    in_dir = PIPE / "steg_6_generalize" / "semantic"
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
        
        vrt_tmp = f"/tmp/_vect_semantic_mmu{mmu_str}.vrt"
        file_list_tmp = f"/tmp/_vect_semantic_mmu{mmu_str}.txt"
        with open(file_list_tmp, "w") as fh:
            fh.write("\n".join(str(t) for t in mmu_tifs))
        subprocess.run(["gdalbuildvrt", "-input_file_list", file_list_tmp, vrt_tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["gdal_polygonize.py", vrt_tmp, "-f", "GPKG", str(gpkg), "DN", LN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import os as _os; _os.unlink(vrt_tmp) if _os.path.exists(vrt_tmp) else None; _os.unlink(file_list_tmp) if _os.path.exists(file_list_tmp) else None
        if gpkg.exists() and gpkg.stat().st_size > 1000:
            sz = gpkg.stat().st_size / 1e6
            log.info("    ✓ %s (%.1f MB)", gpkg.name, sz)
        else:
            log.info("    ✗ failed")


def vectorize_morph_dirs():
    """Auto-detekterar alla *_morph_* undermappar i steg_6_generalize/ och
    vektoriserar dem. GPKG-namn och lagernamn encodar morph-metod+radie.

    Exempel:
      steg_6_generalize/conn4_morph_disk_r02/  →
        steg_7_vectorize/generalized_conn4_mmu050_morph_disk_r02.gpkg
        lagernamn: markslag_morph_disk_r02
    """
    log = logging.getLogger("pipeline.vectorize")
    gen6_dir = PIPE / "steg_6_generalize"
    if not gen6_dir.exists():
        return

    morph_dirs = sorted(d for d in gen6_dir.iterdir()
                        if d.is_dir() and "_morph_" in d.name)
    if not morph_dirs:
        return

    for morph_dir in morph_dirs:
        tifs = sorted(morph_dir.glob("*.tif"))
        if not tifs:
            continue

        # Extrahera morph-suffixet (t.ex. "morph_disk_r02")
        # Katalognamnet är t.ex. "conn4_morph_disk_r02"
        morph_match = re.search(r'_(morph_[a-z0-9_]+)$', morph_dir.name)
        morph_suffix = morph_match.group(1) if morph_match else morph_dir.name
        layer_name = f"markslag_{morph_suffix}"

        log.info("\nMorph: %s (%d tiles)", morph_dir.name, len(tifs))

        gpkg = OUT / f"generalized_{morph_dir.name}.gpkg"
        if gpkg.exists():
            gpkg.unlink()

        vrt_tmp = f"/tmp/_vect_{morph_dir.name}.vrt"
        file_list_tmp = f"/tmp/_vect_{morph_dir.name}.txt"
        with open(file_list_tmp, "w") as fh:
            fh.write("\n".join(str(t) for t in tifs))
        subprocess.run(["gdalbuildvrt", "-input_file_list", file_list_tmp, vrt_tmp],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["gdal_polygonize.py", vrt_tmp, "-f", "GPKG",
                        str(gpkg), "DN", layer_name],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import os as _os
        _os.unlink(vrt_tmp) if _os.path.exists(vrt_tmp) else None
        _os.unlink(file_list_tmp) if _os.path.exists(file_list_tmp) else None

        if gpkg.exists() and gpkg.stat().st_size > 1000:
            sz = gpkg.stat().st_size / 1e6
            log.info("    ✓ %s (%.1f MB)  lager: %s", gpkg.name, sz, layer_name)
        else:
            log.info("    ✗ misslyckades: %s", gpkg.name)


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
    if MORPH_ONLY and MORPH_SMOOTH_METHOD != "none":
        log.info("MORPH_ONLY=True — hoppar över bas-vektorisering (conn4/conn8/modal/semantic)")
    else:
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

    # Morfologiska undermappar — auto-detekterade
    vectorize_morph_dirs()

    elapsed = time.time() - t0
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 7 KLART: %.0fs (%.1f min)", elapsed, elapsed / 60)
    log.info("GeoPackage-filer: %s", OUT)
    log.info("══════════════════════════════════════════════════════════")
