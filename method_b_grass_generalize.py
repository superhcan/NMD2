#!/usr/bin/env python3
"""METHOD B: GRASS GIS v.generalize for topologically-correct vector simplification."""
import logging
import subprocess
import tempfile
import time
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

OUT = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/vectorized_grass_generalized")
OUT.mkdir(exist_ok=True)

VECT_IN = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/vectorized")

def grass_generalize(gpkg_path, method="douglas", threshold=25):
    """Use GRASS v.generalize for topology-aware simplification.
    
    method: douglas, reduction, langford, reumann, boyle
    threshold: simplification threshold in map units (meters)
    """
    log.info("Bearbetar: %s", gpkg_path.name)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        grass_db = Path(tmpdir) / "grassdb"
        grass_location = grass_db / "test"
        grass_mapset = grass_location / "PERMANENT"
        
        # Initialize GRASS location with SWEREF99 TM (EPSG:3006)
        log.info("  Initialiserar GRASS...")
        cmd = f"""
        grass -c EPSG:3006 -e {grass_location}
        """
        subprocess.run(cmd, shell=True, capture_output=True)
        
        # Import vector layer
        log.info("  Importerar vektorer...")
        mapname = gpkg_path.stem
        cmd = f"""
        export GISDBASE={grass_db}
        export LOCATION_NAME=test
        export MAPSET=PERMANENT
        grass exec v.import input={gpkg_path} output={mapname} --overwrite -q
        """
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            log.error("  Import misslyckades: %s", result.stderr[:200])
            return None
        
        # Generalize
        log.info("  Generaliserar (method=%s, threshold=%d)...", method, threshold)
        out_map = f"{mapname}_gen"
        cmd = f"""
        export GISDBASE={grass_db}
        export LOCATION_NAME=test
        export MAPSET=PERMANENT
        grass exec v.generalize input={mapname} output={out_map} method={method} threshold={threshold} --overwrite -q
        """
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            log.error("  Generalisering misslyckades: %s", result.stderr[:200])
            return None
        
        # Export to GPKG
        log.info("  Exporterar...")
        out_gpkg = OUT / (gpkg_path.stem + "_grass.gpkg")
        out_gpkg.unlink(missing_ok=True)
        cmd = f"""
        export GISDBASE={grass_db}
        export LOCATION_NAME=test
        export MAPSET=PERMANENT
        grass exec v.out.ogr input={out_map} output={out_gpkg} format=GPKG --overwrite -q
        """
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            log.error("  Export misslyckades: %s", result.stderr[:200])
            return None
    
    if out_gpkg.exists() and out_gpkg.stat().st_size > 1000:
        sz = out_gpkg.stat().st_size / 1e6
        orig_sz = gpkg_path.stat().st_size / 1e6
        reduction = (1 - sz / orig_sz) * 100
        log.info("  ✓ %s (%.1f MB, %.0f%% mindre)", out_gpkg.name, sz, reduction)
        return out_gpkg
    else:
        log.error("  ✗ Export file empty")
        return None

if __name__ == "__main__":
    log.info("═" * 60)
    log.info("METOD B: GRASS v.generalize (topologi-medveten)")
    log.info("Method: douglas, Threshold: 25m")
    log.info("═" * 60)
    log.info("")
    
    t0 = time.time()
    
    # Test modal k15
    log.info("Modal filter:")
    grass_generalize(VECT_IN / "generalized_modal_k15.gpkg", method="douglas", threshold=25)
    
    # Test conn4 mmu016
    log.info("\nSieve conn4 (större MMU):")
    for mmu_str in ["016", "032", "064", "100"]:
        grass_generalize(VECT_IN / f"generalized_conn4_mmu{mmu_str}.gpkg", method="douglas", threshold=25)
    
    elapsed = time.time() - t0
    log.info("")
    log.info("═" * 60)
    log.info("Klart på %.0fs. Se filer i: %s", elapsed, OUT)
    log.info("═" * 60)
