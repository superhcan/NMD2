#!/usr/bin/env python3
"""simplify_vector.py — Douglas-Peucker simplification för vektorfiler."""
import geopandas as gpd
import logging
from pathlib import Path
from datetime import datetime

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

VECT_DIR = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/vectorized")

def simplify_layer(gpkg_path, tolerance=25):
    """Förenkla geometri i GeoPackage-fil.
    
    Args:
        gpkg_path: Sökväg till GPKG-fil
        tolerance: Douglas-Peucker tolerance i meter (default 25m)
    """
    log.info("Läser: %s", gpkg_path.name)
    gdf = gpd.read_file(gpkg_path)
    
    log.info("  Ursprung: %d polygoner, %.2f MB", len(gdf), gpkg_path.stat().st_size / 1e6)
    
    # Tillämpa Douglas-Peucker simplification
    gdf['geometry'] = gdf.geometry.simplify(tolerance, preserve_topology=True)
    
    # Spara till ny fil
    out_path = gpkg_path.parent / (gpkg_path.stem + "_simplified.gpkg")
    log.info("  Sparar förenklade geometrier...")
    gdf.to_file(out_path, driver="GPKG", layer=gdf.name if hasattr(gdf, 'name') else 'DN')
    
    new_size = out_path.stat().st_size / 1e6
    reduction = (1 - new_size / (gpkg_path.stat().st_size / 1e6)) * 100
    log.info("  Förenklade: %d polygoner, %.2f MB (%.0f%% mindre)", len(gdf), new_size, reduction)
    
    return out_path

if __name__ == "__main__":
    log.info("═" * 60)
    log.info("Douglas-Peucker simplification av vektorfiler")
    log.info("Tolerance: 25 meter")
    log.info("═" * 60)
    
    # Hitta alla GPKG-filer som inte redan är förenklade
    gpkg_files = [f for f in VECT_DIR.glob("generalized_*.gpkg") 
                  if not f.stem.endswith("_simplified")]
    
    if not gpkg_files:
        log.warning("Ingen GPKG-filer hittad!")
        exit(1)
    
    for gpkg_path in sorted(gpkg_files):
        simplify_layer(gpkg_path, tolerance=25)
    
    log.info("═" * 60)
    log.info("Klart! Se *_simplified.gpkg-filer")
    log.info("═" * 60)
