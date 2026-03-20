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
import os
import logging
from pathlib import Path
from datetime import datetime
import sys
from config import OUT_BASE, SIMPLIFICATION_TOLERANCES, SIMPLIFY_PROTECTED

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

    # Konvertera GPKG till GeoJSON för Mapshaper.
    # COORDINATE_PRECISION=0 ger heltal (data är SWEREF99TM på 10 m-rasterrutnät)
    # vilket minskar filstorleken ~35% jämfört med precision=3.
    geojson_file = output_path / "temp_input.geojson"

    if geojson_file.exists() and geojson_file.stat().st_size > 1024 * 1024 * 100:
        # Återanvänd befintlig GeoJSON (t.ex. från avbruten körning)
        log.info(f"Återanvänder befintlig GeoJSON: {geojson_file.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        if geojson_file.exists():
            geojson_file.unlink()
        log.info(f"Konverterar GPKG → GeoJSON (heltalskoordinater) ...")
        ogr_conv = [
            "ogr2ogr", "-f", "GeoJSON",
            "-lco", "COORDINATE_PRECISION=0",
            str(geojson_file), str(input_path)
        ]
        result = subprocess.run(ogr_conv, capture_output=True, text=True)
        if result.returncode != 0:
            log.error(f"GeoJSON-konvertering misslyckades: {result.stderr}")
            sys.exit(1)
        log.info(f"GeoJSON klar: {geojson_file.stat().st_size / 1024 / 1024:.1f} MB")

    log.info(f"Simplifying {variant_name} with Mapshaper (topology-preserving):")
    log.info(f"(percentage = %% of removable vertices to retain)")

    env = os.environ.copy()

    # Använd mapshaper-xl om installerat (optimerat för stora filer), annars mapshaper
    # mapshaper-xl tar GB som första arg (default 8 GB) — måste anges explicit
    import shutil as _shutil
    if _shutil.which("mapshaper-xl"):
        mapshaper_bin = "mapshaper-xl"
        mapshaper_prefix = ["mapshaper-xl", "48"]  # 48 GB heap
    else:
        mapshaper_bin = "mapshaper"
        mapshaper_prefix = ["mapshaper"]
        env["NODE_OPTIONS"] = "--max-old-space-size=49152"
    log.info(f"Mapshaper-binär: {mapshaper_bin} (heap: 48 GB)")

    for tolerance in tolerances:
        output_geojson = output_path / f"{variant_name}_simplified_p{tolerance}.geojson"
        output_gpkg = output_path / f"{variant_name}_simplified_p{tolerance}.gpkg"

        log.info(f"  p{tolerance}%: Startar Mapshaper-förenkling...")

        if SIMPLIFY_PROTECTED:
            # Variabel förenkling i EN gemensam topologi:
            # SIMPLIFY_PROTECTED-klasser får sp=1.0 (noll förenkling), landskap får sp=tolerance/100.
            # Mapshaper väljer automatiskt max(sp) för delade arcs → skyddade
            # klassgränser förenklas aldrig, även från landskapssidan. Ingen
            # topologibrytning längs klassgränser.
            js_array = "[" + ", ".join(str(c) for c in sorted(SIMPLIFY_PROTECTED)) + "]"
            each_expr = f"sp = {js_array}.includes(markslag) ? 1 : {tolerance / 100}"
            cmd = mapshaper_prefix + [
                str(geojson_file),
                "-verbose",
                "-each", each_expr,
                "-simplify", "percentage=sp", "variable", "planar", "keep-shapes",
                "-o", "format=geojson", "precision=0.001", str(output_geojson)
            ]
        else:
            cmd = mapshaper_prefix + [
                str(geojson_file),
                "-verbose",
                "-simplify", f"percentage={tolerance}%", "planar", "keep-shapes",
                "-o", "format=geojson", "precision=0.001", str(output_geojson)
            ]

        # Popen med realtidsloggning så att Mapshaper-progress syns löpande
        import re as _re
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env, bufsize=1
        )
        for raw in proc.stdout:
            for part in _re.split(r'[\r\n]+', raw):
                if part.strip():
                    log.info(f"  [mapshaper] {part}")
        proc.wait()

        if proc.returncode != 0:
            log.error(f"  p{tolerance}%: ❌ Mapshaper misslyckades (returncode={proc.returncode})")
            continue

        if not output_geojson.exists():
            log.error(f"  p{tolerance}%: ❌ Output GeoJSON saknas")
            continue

        geojson_size = output_geojson.stat().st_size / 1024 / 1024
        log.info(f"  p{tolerance}%: GeoJSON klar: {geojson_size:.1f} MB, konverterar till GPKG...")

        ogr_cmd = [
            "ogr2ogr",
            "-f", "GPKG",
            "-a_srs", "EPSG:3006",
            str(output_gpkg),
            str(output_geojson)
        ]
        result = subprocess.run(ogr_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error(f"  p{tolerance}%: ❌ GPKG-konvertering misslyckades: {result.stderr}")
            continue

        gpkg_size = output_gpkg.stat().st_size / 1024 / 1024
        log.info(f"  p{tolerance}%: ✓ {output_gpkg.name} ({gpkg_size:.1f} MB)")

        output_geojson.unlink()

    geojson_file.unlink(missing_ok=True)
    log.info(f"Simplification complete!")
    log.info(f"Output files in: {output_path}")

if __name__ == "__main__":
    import time as _time
    _t0 = _time.time()
    # Setup logging with step-aware filename
    log = setup_logging(OUT_BASE)
    
    vectorized_dir = OUT_BASE / "steg_7_vectorize"
    output_dir = OUT_BASE / "steg_8_simplify"
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
    
    _elapsed = _time.time() - _t0
    log.info("\n══════════════════════════════════════════════════════════")
    log.info(f"Steg 8 KLART: {_elapsed:.0f}s ({_elapsed/60:.1f} min)")
    log.info(f"Output i {output_dir}")
    log.info("══════════════════════════════════════════════════════════")
