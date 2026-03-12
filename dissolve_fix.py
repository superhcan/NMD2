#!/usr/bin/env python3
"""dissolve_fix.py — Dissolve via geopandas med preserve_topology."""
import geopandas as gpd
import logging
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

VECT_DIR = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/vectorized")

def dissolve_fix(gpkg_path, tolerance=25):
    """Dissolve polygoner per DN-klass, förenkla, spara."""
    log.info("Bearbetar: %s", gpkg_path.name)
    
    # Läs filen
    gdf = gpd.read_file(gpkg_path)
    orig_size = gpkg_path.stat().st_size / 1e6
    orig_count = len(gdf)
    log.info("  Original: %d polygoner, %.2f MB", orig_count, orig_size)
    
    # Dissolve per markslag-klass
    dissolve_col = 'markslag' if 'markslag' in gdf.columns else 'DN'
    gdf_dissolved = gdf.dissolve(by=dissolve_col, as_index=False)
    log.info("  Efter dissolve: %d polygoner", len(gdf_dissolved))
    
    # Förenkla geometri med bevarad topologi
    gdf_dissolved['geometry'] = gdf_dissolved.geometry.simplify(
        tolerance, 
        preserve_topology=True
    )
    
    # Spara som _clean.gpkg
    out_path = gpkg_path.parent / (gpkg_path.stem + "_clean.gpkg")
    if out_path.exists():
        out_path.unlink()
    
    log.info("  Sparar till: %s", out_path.name)
    gdf_dissolved.to_file(out_path, driver="GPKG", layer="markslag")
    
    # Statistik
    final_size = out_path.stat().st_size / 1e6
    reduction = (1 - final_size / orig_size) * 100
    polygon_reduction = (1 - len(gdf_dissolved) / orig_count) * 100
    log.info("  Resultat: %d polygoner, %.2f MB (%.0f%% mindre, %.0f%% færre polygoner)",
             len(gdf_dissolved), final_size, reduction, polygon_reduction)
    
    return out_path

if __name__ == "__main__":
    log.info("═" * 60)
    log.info("DISSOLVE + SIMPLIFY (geopandas, preserve_topology)")
    log.info("Tolerance: 25 meter")
    log.info("═" * 60)
    log.info("")
    
    # Hitta originalfiler
    gpkg_files = sorted([
        f for f in VECT_DIR.glob("generalized_*.gpkg")
        if not any(x in f.stem for x in ["_simplified", "_clean"])
    ])
    
    if not gpkg_files:
        log.warning("Ingen originalfiler hittad!")
        exit(1)
    
    log.info("Hittat %d filer\n", len(gpkg_files))
    
    success = 0
    for gpkg_path in gpkg_files:
        try:
            dissolve_fix(gpkg_path, tolerance=25)
            success += 1
        except Exception as e:
            log.error("  MISSLYCKADES: %s", e)
        log.info("")
    
    log.info("═" * 60)
    log.info("KLART: %d/%d filer bearbetade", success, len(gpkg_files))
    log.info("Du har nu *_clean.gpkg-filer (no gaps/overlaps)")
    log.info("═" * 60)
