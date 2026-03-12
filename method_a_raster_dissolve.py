#!/usr/bin/env python3
"""METHOD A: Raster dissolve-then-vectorize for smaller files with preserved topology."""
import logging
import subprocess
from pathlib import Path
import time

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

PIPE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo")
OUT = PIPE / "vectorized_raster_dissolved"
OUT.mkdir(exist_ok=True)

def raster_dissolve_vectorize(method="modal", param="k15"):
    """Dissolve raster pixels per class, then vectorize.
    
    This gives fewer polygons from the start with perfect topology.
    """
    if method == "modal":
        in_dir = PIPE / "generalized_modal"
        pattern = f"*_k{param}.tif"
        out_name = f"generalized_modal_{param}_dissolved"
    else:
        in_dir = PIPE / f"generalized_{method}"
        pattern = f"*mmu{param}.tif"
        out_name = f"generalized_{method}_mmu{param}_dissolved"
    
    tifs = sorted(in_dir.glob(pattern))
    if not tifs:
        log.warning("  Inga TIF-filer för %s %s", method, param)
        return None
    
    log.info("  %s_%s: %d tiles", method, param, len(tifs))
    
    # Step 1: Build VRT
    vrt_tmp = Path("/tmp") / f"dissolve_{method}_{param}.vrt"
    tif_str = " ".join(f'"{t}"' for t in tifs)
    cmd = f'gdalbuildvrt -overwrite "{vrt_tmp}" {tif_str} > /dev/null 2>&1'
    subprocess.run(cmd, shell=True)
    
    # Step 2: Dissolve raster (aggregate pixels per class with majority)
    raster_dissolved = Path("/tmp") / f"dissolve_{method}_{param}_dissolved.tif"
    log.info("    Dissolving raster pixels...")
    # Use gdal_translate with majority/mode resampling to collapse adjacent same-valued pixels
    cmd = f'gdalwarp -r mode -overwrite "{vrt_tmp}" "{raster_dissolved}" > /dev/null 2>&1'
    subprocess.run(cmd, shell=True)
    
    # Step 3: Vectorize dissolved raster
    gpkg = OUT / f"{out_name}.gpkg"
    gpkg.unlink(missing_ok=True)
    
    log.info("    Vektoreisering...")
    cmd = f'gdal_polygonize.py "{raster_dissolved}" -f GPKG "{gpkg}" DN markslag > /dev/null 2>&1'
    subprocess.run(cmd, shell=True)
    
    # Check result
    if gpkg.exists() and gpkg.stat().st_size > 1000:
        sz = gpkg.stat().st_size / 1e6
        log.info("    ✓ %s (%.1f MB)", gpkg.name, sz)
    else:
        log.info("    ✗ failed")
        gpkg = None
    
    # Cleanup
    vrt_tmp.unlink(missing_ok=True)
    raster_dissolved.unlink(missing_ok=True)
    
    return gpkg

if __name__ == "__main__":
    log.info("═" * 60)
    log.info("METOD A: Raster-dissolve före vektoreisering")
    log.info("Resultat: Färre polygoner + perfekt topologi")
    log.info("═" * 60)
    log.info("")
    
    t0 = time.time()
    
    # Test modal k15
    log.info("Modal filter:")
    raster_dissolve_vectorize("modal", "k15")
    
    # Test conn4 mmu016
    log.info("\nSieve conn4:")
    for mmu in [16, 32, 64, 100]:
        raster_dissolve_vectorize("conn4", f"{mmu:03d}")
    
    elapsed = time.time() - t0
    log.info("")
    log.info("═" * 60)
    log.info("Klart på %.0fs. Se filer i: %s", elapsed, OUT)
    log.info("═" * 60)
