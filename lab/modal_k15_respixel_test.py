#!/usr/bin/env python3
"""Respixla modal_k15 raster, vektoreisera, jämför filstorlèk."""
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
OUT = PIPE / "vectorized_modal_tests"
OUT.mkdir(exist_ok=True)

def test_respixel(pixel_sizes=[10, 20, 50]):
    """Test olika pixelupplösningar för modal_k15."""
    
    # Finn original raster-filer för k15
    in_dir = PIPE / "generalized_modal"
    tifs = sorted(in_dir.glob("*_k15.tif"))
    
    if not tifs:
        log.error("Ingen *_k15.tif-filer hittade!")
        return
    
    log.info("Hittat %d rasterbandar för k15", len(tifs))
    log.info("")
    
    for target_px in pixel_sizes:
        log.info("TEST: Target pixel size = %d m", target_px)
        
        # Step 1: Build VRT
        vrt_tmp = Path("/tmp") / f"modal_k15_vrt.vrt"
        tif_str = " ".join(f'"{t}"' for t in tifs)
        subprocess.run(f'gdalbuildvrt -overwrite "{vrt_tmp}" {tif_str} > /dev/null 2>&1', shell=True)
        
        # Beräkna ny pixelstorlek (från 1024x1024@10m → XIxYI@target_px)
        # På en 1024x1024 tile med 10m pixlar = 10240m x 10240m område
        # Vid target_px pixlar = (10240 / target_px) x (10240 / target_px) pixels
        new_dim = int(10240 / target_px)
        
        # Step 2: Respixla (resample to target pixel size, mode/majority)
        raster_respix = Path("/tmp") / f"modal_k15_respix_{target_px}m.tif"
        raster_respix.unlink(missing_ok=True)
        
        log.info("  Respixlar till %dx%d (%dm pixlar)...", new_dim, new_dim, target_px)
        subprocess.run(
            f'gdalwarp -r mode -ts {new_dim} {new_dim} -overwrite "{vrt_tmp}" "{raster_respix}" > /dev/null 2>&1',
            shell=True
        )
        
        # Step 3: Vektoreisera
        gpkg = OUT / f"modal_k15_{target_px}m.gpkg"
        gpkg.unlink(missing_ok=True)
        
        log.info("  Vektoreiserar...")
        subprocess.run(
            f'gdal_polygonize.py "{raster_respix}" -f GPKG "{gpkg}" DN markslag > /dev/null 2>&1',
            shell=True
        )
        
        # Resultat
        if gpkg.exists() and gpkg.stat().st_size > 1000:
            gpkg_sz = gpkg.stat().st_size / 1e6
            log.info("  ✓ %s (%.1f MB)", gpkg.name, gpkg_sz)
        else:
            log.info("  ✗ misslyckades")
        
        # Cleanup
        raster_respix.unlink(missing_ok=True)
        log.info("")

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("MODAL K15: Respixla-test för glada gränser!")
    log.info("=" * 60)
    log.info("")
    
    # Show original
    orig_gpkg = PIPE / "vectorized" / "generalized_modal_k15.gpkg"
    if orig_gpkg.exists():
        orig_sz = orig_gpkg.stat().st_size / 1e6
        log.info("ORIGINAL (1m pixlar): %.1f MB", orig_sz)
        log.info("")
    
    t0 = time.time()
    test_respixel(pixel_sizes=[20, 50, 100])
    elapsed = time.time() - t0
    
    log.info("=" * 60)
    log.info("Klart på %.0fs. Se tester i: %s", elapsed, OUT)
    log.info("Jämför filstorlèk och polyg-glatthet i QGIS!")
    log.info("=" * 60)
