#!/usr/bin/env python3
"""Morphological filtering för glada raster-gränser."""
import logging
import subprocess
from pathlib import Path
import time
import numpy as np
import rasterio
from scipy import ndimage

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

PIPE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo")
OUT = PIPE / "vectorized_modal_morphological"
OUT.mkdir(exist_ok=True)

def apply_morphology(in_dir, kernel_size=3, operation="opening"):
    """Applicera morphological filtering på modal_k15 raster-tiles."""
    
    tifs = sorted(in_dir.glob("*_k15.tif"))
    if not tifs:
        log.error("Ingen *_k15.tif-filer!")
        return
    
    log.info("Applicerar %s (kernel=%d) på %d tiles", operation, kernel_size, len(tifs))
    
    # Skapa output VRT
    vrt_input = Path("/tmp") / "modal_k15_orig.vrt"
    tif_str = " ".join(f'"{t}"' for t in tifs)
    subprocess.run(f'gdalbuildvrt -overwrite "{vrt_input}" {tif_str} > /dev/null 2>&1', shell=True)
    
    # Konvertera VRT → GeoTIFF för att kunna läsa/skriva
    raster_orig = Path("/tmp") / "modal_k15_orig.tif"
    raster_orig.unlink(missing_ok=True)
    subprocess.run(
        f'gdal_translate "{vrt_input}" "{raster_orig}" -of GTiff > /dev/null 2>&1',
        shell=True
    )
    
    # Läs original raster
    log.info("  Läser rasterdata...")
    with rasterio.open(raster_orig) as src:
        data = src.read(1)
        profile = src.profile.copy()
    
    # Skapa en struturelement för morphology
    struct = ndimage.generate_binary_structure(2, 2)
    
    # Applicera morphological operations
    log.info("  Applicerar morphological %s...", operation)
    
    if operation == "opening":
        # Opening = Erosion + Dilation (tar bort små detaljer)
        bin_data = data > 0
        for _ in range(kernel_size):
            bin_data = ndimage.binary_erosion(bin_data, struct)
        for _ in range(kernel_size):
            bin_data = ndimage.binary_dilation(bin_data, struct)
        data_filt = data * bin_data
    elif operation == "closing":
        # Closing = Dilation + Erosion (fyller glipor)
        bin_data = data > 0
        for _ in range(kernel_size):
            bin_data = ndimage.binary_dilation(bin_data, struct)
        for _ in range(kernel_size):
            bin_data = ndimage.binary_erosion(bin_data, struct)
        data_filt = data * bin_data
    elif operation == "erosion":
        # Erosion (minskar alla regioner)
        bin_data = data > 0
        for _ in range(kernel_size):
            bin_data = ndimage.binary_erosion(bin_data, struct)
        data_filt = data * bin_data
    else:
        data_filt = data
    
    # Skriv filtrerad raster
    raster_filt = Path("/tmp") / f"modal_k15_morpho_{operation}_{kernel_size}.tif"
    raster_filt.unlink(missing_ok=True)
    
    profile.update(dtype=data.dtype)
    with rasterio.open(raster_filt, 'w', **profile) as dst:
        dst.write(data_filt, 1)
    
    log.info("  Vektoreiserar filtrerad raster...")
    gpkg = OUT / f"modal_k15_{operation}_k{kernel_size}.gpkg"
    gpkg.unlink(missing_ok=True)
    
    subprocess.run(
        f'gdal_polygonize.py "{raster_filt}" -f GPKG "{gpkg}" DN markslag > /dev/null 2>&1',
        shell=True
    )
    
    # Resultat
    if gpkg.exists() and gpkg.stat().st_size > 1000:
        gpkg_sz = gpkg.stat().st_size / 1e6
        orig_sz = 42.6  # från tidigare test
        reduction = (1 - gpkg_sz / orig_sz) * 100
        log.info("  ✓ %s (%.1f MB, %.0f%% mindre än original)", gpkg.name, gpkg_sz, reduction)
        return gpkg
    else:
        log.info("  ✗ misslyckades")
        return None
    
    # Cleanup
    raster_filt.unlink(missing_ok=True)
    raster_orig.unlink(missing_ok=True)

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("MORPHOLOGICAL FILTERING för glada gränser!")
    log.info("=" * 60)
    log.info("")
    
    # Show original
    orig_gpkg = PIPE / "vectorized" / "generalized_modal_k15.gpkg"
    if orig_gpkg.exists():
        orig_sz = orig_gpkg.stat().st_size / 1e6
        log.info("ORIGINAL: %.1f MB", orig_sz)
        log.info("")
    
    t0 = time.time()
    
    in_dir = PIPE / "generalized_modal"
    
    # Testa olika kernels och operationer
    kernels = [2, 3, 5]
    
    for kernel in kernels:
        log.info("Kernel size: %d", kernel)
        apply_morphology(in_dir, kernel_size=kernel, operation="opening")
        log.info("")
    
    elapsed = time.time() - t0
    log.info("=" * 60)
    log.info("Klart på %.0fs. Se resultat i: %s", elapsed, OUT)
    log.info("Jämför: glada gränser vs original taggiga gränser!")
    log.info("=" * 60)
