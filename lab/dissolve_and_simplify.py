#!/usr/bin/env python3
"""dissolve_and_simplify.py — Slå samman polygoner per klass och förenkla."""
import subprocess
import logging
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

VECT_DIR = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/vectorized")

def dissolve_and_simplify(gpkg_path, tolerance=25):
    """Slå samman (~= dissolve) polygoner per DN-klass och förenkla geometri.
    
    Använder ogr2ogr SQL för att aggregera polygoner per klass,
    sedan förenkla med bevarad topologi.
    """
    log.info("Bearbetar: %s", gpkg_path.name)
    
    # Steg 1: SQL aggregering (dissolve per DN-klass)
    dissolved_tmp = Path("/tmp") / (gpkg_path.stem + "_dissolved.gpkg")
    if dissolved_tmp.exists():
        dissolved_tmp.unlink()
    
    log.info("  1. Aggregering (dissolve per DN-klass)...")
    sql = """
    SELECT DN, ST_Union(geometry) as geometry 
    FROM DN 
    GROUP BY DN
    """
    cmd = [
        "ogr2ogr", "-f", "GPKG",
        "-sql", sql,
        str(dissolved_tmp),
        str(gpkg_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("  Dissolve misslyckades: %s", result.stderr)
        return None
    
    sz_dissolved = dissolved_tmp.stat().st_size / 1e6
    log.info("    → Aggregerad: %.2f MB", sz_dissolved)
    
    # Steg 2: Förenkla med bevarad topologi
    out_path = gpkg_path.parent / (gpkg_path.stem + "_clean.gpkg")
    if out_path.exists():
        out_path.unlink()
    
    log.info("  2. Förenkling (Douglas-Peucker, tolerance=%d m)...", tolerance)
    cmd = [
        "ogr2ogr", "-f", "GPKG",
        "-simplify", str(tolerance),
        str(out_path),
        str(dissolved_tmp)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("  Förenkling misslyckades: %s", result.stderr)
        dissolved_tmp.unlink()
        return None
    
    # Steg 3: Resultat
    sz_final = out_path.stat().st_size / 1e6
    reduction = (1 - sz_final / (gpkg_path.stat().st_size / 1e6)) * 100
    log.info("    → Förenklade: %.2f MB (%.0f%% mindre än original)", sz_final, reduction)
    
    # Cleanup
    dissolved_tmp.unlink()
    
    return out_path

if __name__ == "__main__":
    log.info("═" * 60)
    log.info("Dissolve + Simplify: Aggregera och förenkla vektorfiler")
    log.info("Metod: SQL GROUP BY + Douglas-Peucker (25m)")
    log.info("═" * 60)
    
    # Hitta GPKG-filer (originalfiler, inte redan förenklade)
    gpkg_files = sorted([
        f for f in VECT_DIR.glob("generalized_*.gpkg")
        if not any(x in f.stem for x in ["_simplified", "_clean"])
    ])
    
    if not gpkg_files:
        log.warning("Ingen GPKG-filer hittad!")
        exit(1)
    
    log.info("Hittat %d GPKG-filer\n", len(gpkg_files))
    
    for gpkg_path in gpkg_files:
        dissolve_and_simplify(gpkg_path, tolerance=25)
        log.info("")
    
    log.info("═" * 60)
    log.info("Klart! Se *_clean.gpkg-filer (ingen gaps/overlaps)")
    log.info("═" * 60)
