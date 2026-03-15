#!/usr/bin/env python3
"""
steg_8_simplify.py — Steg 8: Mapshaper-baserad vektorförenkling med topologibevarand.

Läser vektoriserade GeoPackage-filer från Steg 7 och förenklar dem med Mapshaper CLI
med topologibevarand (shared arcs istället för individ polygoner).

Processas:
  - generalized_conn4_mmu008.gpkg
  - generalized_conn8_mmu008.gpkg
  - generalized_modal_k15.gpkg

Tolerances: [90, 75, 50, 25, 15]% of removable vertices to retain

Kör: python3 src/steg_8_simplify.py

Kräver: Mapshaper installerat och i PATH
	npm install -g mapshaper
"""

import subprocess
import json
import os
import logging
from pathlib import Path
from datetime import datetime
import sys
from config import OUT_BASE

def setup_logging(out_base):
    """Setup logging with step-aware filenames."""
    log_dir = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Läs steg-info från miljövariabler
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    
    # Skapa loggfilnamn med eventuell steg-referens
    if step_num and step_name:
        step_suffix = f"steg_{step_num}_{step_name}_{ts}"
    else:
        step_suffix = f"{ts}"
    
    debug_log = log_dir / f"debug_{step_suffix}.log"
    summary_log = summary_dir / f"summary_{step_suffix}.log"
    
    fmt_detail = logging.Formatter("%(asctime)s [%(levelname)-8s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fmt_summary = logging.Formatter("%(asctime)s [%(levelname)-6s] %(message)s", datefmt="%H:%M:%S")
    
    # Root logger for both debug and summary
    log = logging.getLogger("pipeline.simplify")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    
    # Clear handlers to avoid duplicates
    log.handlers.clear()
    
    # Debug handler
    dbg_handler = logging.FileHandler(debug_log)
    dbg_handler.setLevel(logging.DEBUG)
    dbg_handler.setFormatter(fmt_detail)
    log.addHandler(dbg_handler)
    
    # File handler
    h1 = logging.FileHandler(summary_log)
    h1.setLevel(logging.INFO)
    h1.setFormatter(fmt_summary)
    log.addHandler(h1)
    
    # Console handler
    h2 = logging.StreamHandler()
    h2.setLevel(logging.INFO)
    h2.setFormatter(fmt_summary)
    log.addHandler(h2)
    
    return log

def simplify_with_mapshaper(input_file, output_dir, variant_name, tolerances=[90, 75, 50, 25, 15], log=None):
    """
    Simplify GeoPackage using Mapshaper CLI with topology preservation.
    
    Args:
        input_file: Path to input GeoPackage
        output_dir: Directory for output files
        variant_name: Name of variant (e.g. 'conn4_mmu008', 'conn8_mmu008', 'modal_k15')
        tolerances: List of percentage values (% of removable vertices to retain)
                   90% = minimal simplification, 15% = very aggressive
        log: Logger instance
    """
    
    if log is None:
        log = logging.getLogger("pipeline.simplify")
    """
    Simplify GeoPackage using Mapshaper CLI with topology preservation.
    
    Args:
        input_file: Path to input GeoPackage
        output_dir: Directory for output files
        tolerances: List of percentage values (% of removable vertices to retain)
                   90% = minimal simplification, 25% = aggressive simplification
    """
    
    input_path = Path(input_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    if not input_path.exists():
        log.error(f"Input file not found: {input_file}")
        sys.exit(1)
    
    log.info(f"Input: {input_path}")
    log.info(f"Output: {output_path}")
    
    # Convert GeoPackage to GeoJSON for Mapshaper
    geojson_file = output_path / "temp_input.geojson"
    log.info(f"Converting GeoPackage to GeoJSON...")
    ogr_cmd = [
        "ogr2ogr",
        "-f", "GeoJSON",
        str(geojson_file),
        str(input_path)
    ]
    result = subprocess.run(ogr_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error(f"GeoJSON conversion failed: {result.stderr}")
        sys.exit(1)
    log.info(f"GeoJSON created: {geojson_file.stat().st_size / 1024 / 1024:.1f} MB")
    
    # Simplify with Mapshaper for each tolerance
    log.info(f"Simplifying {variant_name} with Mapshaper (topology-preserving):")
    log.info(f"(percentage = %% of removable vertices to retain)")
    
    for tolerance in tolerances:
        output_geojson = output_path / f"{variant_name}_simplified_p{tolerance}.geojson"
        output_gpkg = output_path / f"{variant_name}_simplified_p{tolerance}.gpkg"
        
        # Mapshaper command with topology preservation
        # percentage=X retains X% of removable vertices
        # Higher percentage = less simplification, Lower percentage = more simplification
        # 90% = minimal simplification, 25% = aggressive simplification
        mapshaper_cmd = [
            "mapshaper",
            str(geojson_file),
            "-simplify",
            f"percentage={tolerance}%",  # Keep X% of removable vertices
            "planar",                     # Use planar projection (2D)
            "keep-shapes",                # Preserve polygon shapes
            "-o",
            "format=geojson",
            str(output_geojson)
        ]
        
        print(f"  p{tolerance}%: ", end="", flush=True)
        result = subprocess.run(mapshaper_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ Failed")
            print(f"     Error: {result.stderr}")
            continue
        
        geojson_size = output_geojson.stat().st_size / 1024 / 1024
        print(f"  GeoJSON: {geojson_size:.1f} MB", end="", flush=True)
        
        # Convert back to GeoPackage with correct CRS (EPSG:3006)
        # The GeoJSON coordinates are already in EPSG:3006, so use -a_srs to assign the CRS
        ogr_cmd = [
            "ogr2ogr",
            "-f", "GPKG",
            "-a_srs", "EPSG:3006",      # Assign CRS without reprojection
            str(output_gpkg),
            str(output_geojson)
        ]
        result = subprocess.run(ogr_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f" ❌ GeoPackage conversion failed")
            print(f"     stderr: {result.stderr}")
            print(f"     stdout: {result.stdout}")
            continue
        
        gpkg_size = output_gpkg.stat().st_size / 1024 / 1024
        print(f" → GeoPackage: {gpkg_size:.1f} MB ✓")
        
        # Clean up GeoJSON (only keep final GPKG)
        output_geojson.unlink()
    
    # Clean up temp GeoJSON
    geojson_file.unlink()
    
    log.info(f"Simplification complete!")
    log.info(f"Output files in: {output_path}")

if __name__ == "__main__":
    # Setup logging with step-aware filename
    log = setup_logging(OUT_BASE)
    
    vectorized_dir = OUT_BASE / "steg7_vectorized"
    output_dir = OUT_BASE / "steg8_simplified"
    tolerances = [90, 75, 50, 25, 15]  # Updated: added p15
    
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 8: Mapshaper-förenkling av vektoriserade data")
    log.info("Källmapp : %s", vectorized_dir)
    log.info("Utmapp   : %s", output_dir)
    log.info("══════════════════════════════════════════════════════════")
    
    # Dynamiskt hämta alla GeoPackage-filer från steg 7 (skapade av de aktiva metoderna)
    if vectorized_dir.exists():
        gpkg_files = sorted(vectorized_dir.glob("generalized_*.gpkg"))
        if not gpkg_files:
            log.warning("Inga GeoPackage-filer hittades i %s", vectorized_dir)
        else:
            for input_file in gpkg_files:
                variant_name = input_file.stem.replace("generalized_", "")
                log.info(f"\n➤ {variant_name.upper()}")
                simplify_with_mapshaper(input_file, output_dir, variant_name, tolerances, log)
    else:
        log.error("❌ Vektoriserad katalog saknas: %s", vectorized_dir)
    
    log.info("\n══════════════════════════════════════════════════════════")
    log.info(f"Steg 8 KLAR: Output i {output_dir}")
    log.info("══════════════════════════════════════════════════════════")
