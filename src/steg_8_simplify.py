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
import re as _re
import json
import os
import logging
from pathlib import Path
from datetime import datetime
import sys
from config import OUT_BASE, SIMPLIFICATION_TOLERANCES

# Filer större än detta förenklas i rader för att undvika Node.js minnesgräns
LARGE_FILE_THRESHOLD_MB = 400
# Antal rader att dela upp i (välj ett rimligt tal; 7 ger ~200 MB per rad för 10%-körningen)
N_CHUNKS = 7


def _get_gpkg_extent(gpkg_path):
    """Returnerar (xmin, ymin, xmax, ymax) för ett GeoPackage-lager."""
    r = subprocess.run(["ogrinfo", "-al", "-so", str(gpkg_path)], capture_output=True, text=True)
    m = _re.search(r'Extent: \(([0-9.]+), ([0-9.]+)\) - \(([0-9.]+), ([0-9.]+)\)', r.stdout)
    if m:
        return float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))
    return None


def _simplify_chunked(input_path, output_path, variant_name, tolerances, log):
    """Förenklar ett stort GeoPackage genom att dela upp det i N horisontella rader."""
    ext = _get_gpkg_extent(input_path)
    if not ext:
        log.error("Kunde inte hämta extent från %s", input_path)
        return

    xmin, ymin, xmax, ymax = ext
    chunk_height = (ymax - ymin) / N_CHUNKS
    log.info("Stor fil (%.0f MB) — processar i %d rader à %.0f m",
             input_path.stat().st_size / 1e6, N_CHUNKS, chunk_height)

    for tolerance in tolerances:
        print(f"  p{tolerance}%: ", end="", flush=True)
        chunk_gpkgs = []

        for i in range(N_CHUNKS):
            chunk_ymin = ymin + i * chunk_height
            chunk_ymax = ymin + (i + 1) * chunk_height
            base = f"/tmp/_steg8_{variant_name}_p{tolerance}_c{i:02d}"

            # 1. Extrahera spatial subset
            raw_gpkg = Path(f"{base}_raw.gpkg")
            subprocess.run(
                ["ogr2ogr", "-f", "GPKG", "-spat",
                 str(xmin), str(chunk_ymin), str(xmax), str(chunk_ymax),
                 str(raw_gpkg), str(input_path)],
                capture_output=True
            )
            if not raw_gpkg.exists() or raw_gpkg.stat().st_size < 1000:
                raw_gpkg.unlink(missing_ok=True)
                continue

            # 2. GPkg → GeoJSON
            raw_geojson = Path(f"{base}_raw.geojson")
            subprocess.run(
                ["ogr2ogr", "-f", "GeoJSON", str(raw_geojson), str(raw_gpkg)],
                capture_output=True
            )
            raw_gpkg.unlink(missing_ok=True)
            if not raw_geojson.exists():
                continue

            # 3. Mapshaper-förenkling
            simp_geojson = Path(f"{base}_simp.geojson")
            r = subprocess.run(
                ["mapshaper", str(raw_geojson),
                 "-simplify", f"percentage={tolerance}%", "planar", "keep-shapes",
                 "-o", "format=geojson", str(simp_geojson)],
                capture_output=True, text=True
            )
            raw_geojson.unlink(missing_ok=True)
            if r.returncode != 0 or not simp_geojson.exists():
                simp_geojson.unlink(missing_ok=True)
                continue

            # 4. GeoJSON → GPkg
            simp_gpkg = Path(f"{base}_simp.gpkg")
            subprocess.run(
                ["ogr2ogr", "-f", "GPKG", "-a_srs", "EPSG:3006",
                 str(simp_gpkg), str(simp_geojson)],
                capture_output=True
            )
            simp_geojson.unlink(missing_ok=True)
            if simp_gpkg.exists() and simp_gpkg.stat().st_size > 1000:
                chunk_gpkgs.append(simp_gpkg)

        # 5. Slå ihop alla rad-GPkg till slut-fil
        output_gpkg = output_path / f"{variant_name}_simplified_p{tolerance}.gpkg"
        if output_gpkg.exists():
            output_gpkg.unlink()

        if not chunk_gpkgs:
            print("❌ inga rader lyckades")
            continue

        subprocess.run(
            ["ogr2ogr", "-f", "GPKG", str(output_gpkg), str(chunk_gpkgs[0])],
            capture_output=True
        )
        for c in chunk_gpkgs[1:]:
            subprocess.run(
                ["ogr2ogr", "-f", "GPKG", "-update", "-append", str(output_gpkg), str(c)],
                capture_output=True
            )
        for c in chunk_gpkgs:
            c.unlink(missing_ok=True)

        if output_gpkg.exists():
            sz = output_gpkg.stat().st_size / 1e6
            print(f"  GeoPackage: {sz:.1f} MB ✓")
        else:
            print("❌ merge misslyckades")

    log.info("Simplification complete!")
    log.info("Output files in: %s", output_path)

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
    Stora filer (> LARGE_FILE_THRESHOLD_MB) delas upp i rader för att undvika
    Node.js minnesgränsen.
    """

    if log is None:
        log = logging.getLogger("pipeline.simplify")

    input_path = Path(input_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        log.error(f"Input file not found: {input_file}")
        sys.exit(1)

    log.info(f"Input: {input_path}")
    log.info(f"Output: {output_path}")

    file_size_mb = input_path.stat().st_size / 1e6

    if file_size_mb > LARGE_FILE_THRESHOLD_MB:
        log.info(f"Simplifying {variant_name} with Mapshaper (chunked, topology-preserving):")
        log.info(f"(percentage = %% of removable vertices to retain)")
        _simplify_chunked(input_path, output_path, variant_name, tolerances, log)
        return

    # ── Liten fil: befintlig metod ──────────────────────────────────────────

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
    tolerances = SIMPLIFICATION_TOLERANCES  # From config
    
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 8: Mapshaper-förenkling av vektoriserade data")
    log.info("Källmapp : %s", vectorized_dir)
    log.info("Utmapp   : %s", output_dir)
    log.info("══════════════════════════════════════════════════════════")

    # Rensa inaktuella gpkg-filer (metoder som tagits bort från config)
    import shutil
    from config import GENERALIZATION_METHODS
    all_methods = {"conn4", "conn8", "modal", "semantic"}
    if output_dir.exists():
        for method in all_methods - GENERALIZATION_METHODS:
            for stale in output_dir.glob(f"{method}_*_simplified_*.gpkg"):
                stale.unlink()
                log.info("  Raderat inaktuell fil: %s", stale.name)

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
