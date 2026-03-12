#!/usr/bin/env python3
"""Respixla generaliserade raster INNAN vektoreisering."""
import logging
import subprocess
import time
from pathlib import Path
import re

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

PIPE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo")
OUT_RASTER = PIPE / "generalized_respixeled_2m"
OUT_VECTOR = PIPE / "vectorized_smooth"
OUT_RASTER.mkdir(exist_ok=True)
OUT_VECTOR.mkdir(exist_ok=True)

def respixel_and_vectorize(in_dir, method_name, pattern, param_key, pixel_size=2):
    """Respixla raster från 1m till större pixel, sedan vektoreisera.
    
    Args:
        in_dir: Indatakatalog med 1m raster
        method_name: Method name (conn4, conn8, modal, semantic)
        pattern: Filnamn-pattern (e.g. "*mmu*.tif")
        param_key: Parameter key (mmu eller k)
        pixel_size: Target pixel size (2, 5, etc)
    """
    tifs = sorted(in_dir.glob(pattern))
    if not tifs:
        return 0
    
    # Extract parameter values
    params = set()
    for tif in tifs:
        m = re.search(f'{param_key}(\\d+)', tif.stem)
        if m:
            params.add(m.group(1))
    
    processed = 0
    for param in sorted(params):
        param_tifs = [t for t in tifs if f'{param_key}{param}' in t.name]
        if not param_tifs:
            continue
        
        out_name = f"{method_name}_{param_key}{param}"
        log.info("  %s: %d tiles, respixlar till %dm, vektoreiserar...", out_name, len(param_tifs), pixel_size)
        
        # Step 1: Build VRT from original tiles
        vrt_tmp = Path("/tmp") / f"vect_{method_name}_{param}.vrt"
        tif_str = " ".join(f'"{t}"' for t in param_tifs)
        subprocess.run(f'gdalbuildvrt -overwrite "{vrt_tmp}" {tif_str} > /dev/null 2>&1', shell=True)
        
        # Step 2: Respixela (resample to larger pixel size using mode/majority)
        raster_respix = OUT_RASTER / f"{out_name}_respix.tif"
        raster_respix.unlink(missing_ok=True)
        
        # Calculate scale factor: original 1m → target pixel_size
        scale = pixel_size
        subprocess.run(
            f'gdalwarp -r mode -ts {int(1024*scale)} {int(1024*scale)} -overwrite "{vrt_tmp}" "{raster_respix}" > /dev/null 2>&1',
            shell=True
        )
        
        # Step 3: Vektoreisera respixlad raster
        gpkg = OUT_VECTOR / f"{out_name}_smooth.gpkg"
        gpkg.unlink(missing_ok=True)
        
        subprocess.run(
            f'gdal_polygonize.py "{raster_respix}" -f GPKG "{gpkg}" DN markslag > /dev/null 2>&1',
            shell=True
        )
        
        # Check result
        if gpkg.exists() and gpkg.stat().st_size > 1000:
            orig_sz = sum(t.stat().st_size for t in param_tifs) / 1e6
            gpkg_sz = gpkg.stat().st_size / 1e6
            reduction = (1 - gpkg_sz / orig_sz) * 100
            log.info("    ✓ %s (%.1f MB, %.0f%% mindre än rastersum)", gpkg.name, gpkg_sz, reduction)
            processed += 1
        else:
            log.info("    ✗ misslyckades")
        
        # Cleanup
        vrt_tmp.unlink(missing_ok=True)
    
    return processed

if __name__ == "__main__":
    log.info("═" * 60)
    log.info("RESPIXLA RASTER → VEKTOREISERA (glada gränser!)")
    log.info("1m raster → 2m pixlar → færre noder → smooth grensar")
    log.info("═" * 60)
    log.info("")
    
    t0 = time.time()
    
    # Conn4
    log.info("Sieve conn4:")
    n = respixel_and_vectorize(
        PIPE / "generalized_conn4", "conn4", "*mmu*.tif", "mmu", pixel_size=2
    )
    log.info("  → %d filer klara\n", n)
    
    # Conn8
    log.info("Sieve conn8:")
    n = respixel_and_vectorize(
        PIPE / "generalized_conn8", "conn8", "*mmu*.tif", "mmu", pixel_size=2
    )
    log.info("  → %d filer klara\n", n)
    
    # Modal
    log.info("Modal filter:")
    n = respixel_and_vectorize(
        PIPE / "generalized_modal", "modal", "*_k*.tif", "k", pixel_size=2
    )
    log.info("  → %d filer klara\n", n)
    
    # Semantic
    log.info("Semantic:")
    n = respixel_and_vectorize(
        PIPE / "generalized_semantic", "semantic", "*mmu*.tif", "mmu", pixel_size=2
    )
    log.info("  → %d filer klara\n", n)
    
    elapsed = time.time() - t0
    log.info("═" * 60)
    log.info("KLART på %.0fs", elapsed)
    log.info("Vektorer: %s", OUT_VECTOR)
    log.info("═" * 60)
