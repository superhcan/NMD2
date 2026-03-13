"""
vectorize_generalized.py — Steg 6: Vektorisera generaliserade tiles.

Läser från generalized_modal/, bygger VRT, och polygoniserar med gdal_polygonize.py
"""

import logging
import subprocess
import time
from pathlib import Path
import glob

from config import OUT_BASE, SRC

log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")


def vectorize_generalized(kernel_size: int = 15) -> Path:
    """
    Vektorisera finala generaliserade raster (modal k={kernel_size}).
    
    Steg:
      1. Samla k15-tiles från generalized_modal/
      2. Bygga VRT av alla k15-tiles
      3. Kör gdal_polygonize.py
      4. Spara resultat som GeoPackage
    
    Returnerar: Path till output GeoPackage
    """
    t0_step = time.time()
    
    # Hitta alla k15-tiles
    generalized_dir = OUT_BASE / "generalized_modal"
    k15_tiles = sorted(glob.glob(str(generalized_dir / f"*_modal_k{kernel_size:02d}.tif")))
    
    if not k15_tiles:
        raise FileNotFoundError(f"Ingen modal k{kernel_size:02d} tiles hittade i {generalized_dir}")
    
    log.info("Vektorisering: Hitta %d k%d-tiles", len(k15_tiles), kernel_size)
    info.info("Steg 6: Vektorisera %d generaliserade tiles (k=%d)...", len(k15_tiles), kernel_size)
    
    # Bygga VRT
    vrt_path = OUT_BASE / f"generalized_modal_k{kernel_size:02d}.vrt"
    log.debug("Bygger VRT: %s", vrt_path.name)
    
    subprocess.run(
        ["gdalbuildvrt", str(vrt_path), *k15_tiles],
        capture_output=True, check=True
    )
    log.debug("VRT klar: %s", vrt_path.name)
    
    # Vektorisera med gdal_polygonize
    out_dir = OUT_BASE / "vectorized"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    output_gpkg = out_dir / f"modal_k{kernel_size:02d}_generalized.gpkg"
    
    # Ta bort om den redan existerar
    if output_gpkg.exists():
        output_gpkg.unlink()
        log.debug("Removed existing: %s", output_gpkg.name)
    
    log.info("Vektoriserar: %s → %s", vrt_path.name, output_gpkg.name)
    t0_vec = time.time()
    
    # Kör gdal_polygonize.py
    try:
        result = subprocess.run(
            ["gdal_polygonize.py", str(vrt_path), "-f", "GPKG", str(output_gpkg), "DN", "markslag"],
            capture_output=True, check=True, text=True
        )
        log.debug("gdal_polygonize output: %s", result.stdout[:200])
    except subprocess.CalledProcessError as e:
        log.error("gdal_polygonize misslyckades: %s", e.stderr)
        raise
    
    elapsed_vec = time.time() - t0_vec
    
    # Verifiera output
    if not output_gpkg.exists():
        raise FileNotFoundError(f"Output GeoPackage skapades inte: {output_gpkg}")
    
    file_size_mb = output_gpkg.stat().st_size / 1e6
    log.info("Vektorisering klar: %s (%.1f MB) %.1fs", output_gpkg.name, file_size_mb, elapsed_vec)
    info.info("  Vektoriserad → %s (%.1f MB)  %.1fs", output_gpkg.name, file_size_mb, elapsed_vec)
    
    elapsed_total = time.time() - t0_step
    info.info("Steg 6 klar: Vektorisering färdig  %.1fs", elapsed_total)
    
    return output_gpkg


if __name__ == "__main__":
    from logging_setup import setup_logging
    setup_logging(OUT_BASE)
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    output = vectorize_generalized()
    print(f"✅ Vektorisering färdig: {output}")
