#!/usr/bin/env python3
"""Use GRASS v.generalize for topology-aware vector simplification."""
import logging
import subprocess
import tempfile
import shutil
from pathlib import Path
import os

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

VECT_IN = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/vectorized/generalized_modal_k15.gpkg")
OUT = VECT_IN.parent / "generalized_modal_k15_grass.gpkg"

def grass_simplify(gpkg_path, threshold=25, method="douglas"):
    """Use GRASS v.generalize for topology-aware simplification.
    
    method: douglas (Douglas-Peucker), reduction, langford, reumann, boyle
    threshold: simplification threshold in map units (meters)
    """
    log.info("GRASS v.generalize: %s", gpkg_path.name)
    log.info("  Method: %s, Threshold: %d m", method, threshold)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        grass_db = Path(tmpdir) / "grassdb"
        grass_db.mkdir()
        
        # Create location with EPSG:3006 (SWEREF99 TM)
        location = grass_db / "sweref99tm"
        
        log.info("  1. Initialiserar GRASS location...")
        result = subprocess.run(
            ["grass", "-c", "EPSG:3006", "-e", str(location)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            log.error("  GRASS init misslyckades: %s", result.stderr[:200])
            return False
        
        # Set environment
        env = os.environ.copy()
        env["GISDBASE"] = str(grass_db)
        env["LOCATION_NAME"] = "sweref99tm"
        env["MAPSET"] = "PERMANENT"
        
        # Import vector
        log.info("  2. Importerar vektor...")
        result = subprocess.run(
            ["grass", str(location) + "/PERMANENT", "--exec", 
             "v.import", f"input={gpkg_path}", "output=modal_k15", "--overwrite", "-q"],
            capture_output=True,
            text=True,
            env=env
        )
        if result.returncode != 0:
            log.error("  Import misslyckades: %s", result.stderr[:200])
            return False
        
        # Simplify
        log.info("  3. Generaliserar med v.generalize...")
        result = subprocess.run(
            ["grass", str(location) + "/PERMANENT", "--exec",
             "v.generalize", "input=modal_k15", "output=modal_k15_gen",
             f"method={method}", f"threshold={threshold}", 
             "--overwrite", "-q"],
            capture_output=True,
            text=True,
            env=env
        )
        if result.returncode != 0:
            log.error("  Generalisering misslyckades: %s", result.stderr[:200])
            return False
        
        # Export
        log.info("  4. Exporterar...")
        out_path = Path(tmpdir) / "modal_k15_gen.gpkg"
        result = subprocess.run(
            ["grass", str(location) + "/PERMANENT", "--exec",
             "v.out.ogr", "input=modal_k15_gen", f"output={out_path}",
             "format=GPKG", "--overwrite", "-q"],
            capture_output=True,
            text=True,
            env=env
        )
        if result.returncode != 0:
            log.error("  Export misslyckades: %s", result.stderr[:200])
            return False
        
        # Copy result
        if out_path.exists():
            shutil.copy(out_path, OUT)
            sz = OUT.stat().st_size / 1e6
            orig_sz = gpkg_path.stat().st_size / 1e6
            reduction = (1 - sz / orig_sz) * 100
            log.info("  ✓ %s (%.1f MB, %.0f%% mindre)", OUT.name, sz, reduction)
            return True
        else:
            log.error("  Output file not created")
            return False

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("GRASS v.generalize: Topologi-medveten förenkling")
    log.info("=" * 60)
    log.info("")
    
    if not VECT_IN.exists():
        log.error("Input file not found: %s", VECT_IN)
        exit(1)
    
    log.info("Input: %.1f MB", VECT_IN.stat().st_size / 1e6)
    log.info("")
    
    if grass_simplify(VECT_IN, threshold=25, method="douglas"):
        log.info("")
        log.info("=" * 60)
        log.info("Klart! Se resultat: %s", OUT)
        log.info("=" * 60)
    else:
        log.error("Misslyckades")
        exit(1)
