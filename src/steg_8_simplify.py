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
import shutil
import os
import logging
from pathlib import Path
from datetime import datetime
import sys
from config import OUT_BASE, SIMPLIFICATION_TOLERANCES


def _find_node_path():
    """
    Hittar NODE_PATH för 'require("mapshaper")' baserat på var mapshaper-binären finns.
    Returnerar sträng (env-värde) eller None om mapshaper inte hittas.
    """
    mapshaper_bin = shutil.which("mapshaper")
    if not mapshaper_bin:
        return None
    real = subprocess.run(["realpath", mapshaper_bin], capture_output=True, text=True).stdout.strip()
    # real = …/lib/node_modules/mapshaper/bin/mapshaper  → parent×3 = node_modules
    return str(Path(real).parent.parent.parent)


def _find_node_bin():
    """Returnerar sökväg till node-binären (följer nvm-symlänkar)."""
    node_bin = shutil.which("node")
    return node_bin or "node"


NODE_PATH = _find_node_path()
NODE_BIN = _find_node_bin()
_JS_SCRIPT = Path(__file__).parent / "mapshaper_ndjson_simplify.js"

# Features per batch: ~500K ≈ 340 MB ndjson ≈ 1.5 GB som Node.js-objekt.
# Passar på 6.4 GB RAM-system med 3 GB Node-heap.
FEATURES_PER_BATCH = 500_000
NODE_HEAP_MB = 3000


def _count_lines(path):
    """Räknar antal rader i en fil (= antalet features i en ndjson-fil)."""
    n = 0
    with open(path, "rb") as f:
        for _ in f:
            n += 1
    return n


def _write_batch(src_path, batch_path, start, count):
    """Skriver ut 'count' rader från rad 'start' i src_path till batch_path."""
    with open(src_path, "rb") as src, open(batch_path, "wb") as dst:
        for i, line in enumerate(src):
            if i < start:
                continue
            if i >= start + count:
                break
            dst.write(line)


def simplify_with_mapshaper(input_file, output_dir, variant_name, tolerances=None, log=None):
    """
    Förenklar ett GeoPackage med Mapshaper via Node.js-API:t.

    Flöde:
      1. GPkg → GeoJSONSeq (ndjson, en feature/rad)                 [ogr2ogr]
      2. Dela ndjson i batchar om FEATURES_PER_BATCH rader           [Python]
      3. Per batch: ndjson → Node.js API → GeoJSON-buffer → GPkg temp   [Node.js]
      4. Slå ihop alla batch-GPkg till en fil med korrekt lagernamn  [ogr2ogr]

    Fördel: hela datasetet (oavsett storlek) passar i minnet batch-vis.
    Topologin bevaras INOM varje batch (shared arcs).  Seam-artefakter vid
    batch-gränser är sub-pixel vid typiska visningsskalor (1:50 000+).
    """
    if tolerances is None:
        tolerances = [90, 75, 50, 25, 15]
    if log is None:
        log = logging.getLogger("pipeline.simplify")

    if NODE_PATH is None:
        log.error("mapshaper hittades inte i PATH — installera med: npm install -g mapshaper")
        sys.exit(1)

    input_path = Path(input_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        log.error("Input-fil saknas: %s", input_file)
        sys.exit(1)

    file_size_mb = input_path.stat().st_size / 1e6
    log.info("Input : %s (%.0f MB)", input_path, file_size_mb)
    log.info("Output: %s", output_path)

    # ── Steg 1: GPkg → GeoJSONSeq (ndjson) ────────────────────────────────
    ndjson_file = Path(f"/tmp/_steg8_{variant_name}.geojsonl")
    ndjson_file.unlink(missing_ok=True)
    log.info("Konverterar GeoPackage → GeoJSONSeq (WGS84, ogr2ogr-standard)...")
    r = subprocess.run(
        ["ogr2ogr", "-f", "GeoJSONSeq",
         # GeoJSONSeq reprojicerar alltid till WGS84. Koordinaterna är i grader.
         # Mapshaper förenklar med planar (flat 2D), liten anisotropi vid 58°N —
         # osynlig vid normal kartvisning (1:50 000+).
         # Slutkonverteringen reprojicerar WGS84 → EPSG:3006.
         str(ndjson_file), str(input_path)],
        capture_output=True, text=True
    )
    if r.returncode != 0 or not ndjson_file.exists():
        log.error("ogr2ogr GeoJSONSeq misslyckades: %s", r.stderr)
        sys.exit(1)
    ndjson_mb = ndjson_file.stat().st_size / 1e6
    total_features = _count_lines(ndjson_file)
    n_batches = max(1, (total_features + FEATURES_PER_BATCH - 1) // FEATURES_PER_BATCH)
    log.info("GeoJSONSeq: %.0f MB, %d features → %d batch(ar) à %d",
             ndjson_mb, total_features, n_batches, FEATURES_PER_BATCH)

    # ── Steg 2: Förenkla varje toleransnivå ───────────────────────────────
    env = {**os.environ, "NODE_PATH": NODE_PATH}
    log.info("Förenklar %s med Mapshaper Node.js-API (topologibevarand):", variant_name)
    log.info("(percentage = %% kvarvarande borttagbara hörn)")

    for tolerance in tolerances:
        print(f"  p{tolerance}%: ", end="", flush=True)
        output_gpkg = output_path / f"{variant_name}_simplified_p{tolerance}.gpkg"
        output_gpkg.unlink(missing_ok=True)

        batch_gpkgs = []
        ok = True

        for b in range(n_batches):
            start = b * FEATURES_PER_BATCH
            batch_ndjson = Path(f"/tmp/_steg8_{variant_name}_p{tolerance}_b{b:03d}.geojsonl")
            batch_geojson = Path(f"/tmp/_steg8_{variant_name}_p{tolerance}_b{b:03d}.geojson")
            batch_gpkg = Path(f"/tmp/_steg8_{variant_name}_p{tolerance}_b{b:03d}.gpkg")

            _write_batch(ndjson_file, batch_ndjson, start, FEATURES_PER_BATCH)

            # Node.js: ndjson → Mapshaper API → Buffer → fil
            r = subprocess.run(
                [NODE_BIN, f"--max-old-space-size={NODE_HEAP_MB}",
                 str(_JS_SCRIPT),
                 str(batch_ndjson), str(batch_geojson), str(tolerance)],
                capture_output=True, text=True, env=env
            )
            batch_ndjson.unlink(missing_ok=True)

            if r.returncode != 0 or not batch_geojson.exists():
                print(f"\n    ❌ batch {b} misslyckades")
                log.error("Node.js stderr batch %d: %s", b, r.stderr)
                batch_geojson.unlink(missing_ok=True)
                ok = False
                break

            # GeoJSON (WGS84) → GPkg (EPSG:3006): reprojicera från WGS84
            r2 = subprocess.run(
                ["ogr2ogr", "-f", "GPKG", "-t_srs", "EPSG:3006",
                 str(batch_gpkg), str(batch_geojson)],
                capture_output=True, text=True
            )
            batch_geojson.unlink(missing_ok=True)
            if r2.returncode != 0 or not batch_gpkg.exists():
                print(f"\n    ❌ batch {b} GPkg-konvertering misslyckades")
                log.error("ogr2ogr batch %d: %s", b, r2.stderr)
                ok = False
                break
            batch_gpkgs.append(batch_gpkg)
            print(".", end="", flush=True)

        if not ok or not batch_gpkgs:
            for g in batch_gpkgs:
                g.unlink(missing_ok=True)
            print(" ❌")
            continue

        # ── Slå ihop batch-GPkg till en enda fil med rätt lagernamn ───────
        # Första batch skapar filen, sedan -append med -nln för enhetligt lagernamn
        r0 = subprocess.run(
            ["ogr2ogr", "-f", "GPKG", "-a_srs", "EPSG:3006",
             "-nln", variant_name,
             str(output_gpkg), str(batch_gpkgs[0])],
            capture_output=True, text=True
        )
        for g in batch_gpkgs[1:]:
            subprocess.run(
                ["ogr2ogr", "-f", "GPKG", "-update", "-append",
                 "-nln", variant_name,
                 str(output_gpkg), str(g)],
                capture_output=True, text=True
            )
        for g in batch_gpkgs:
            g.unlink(missing_ok=True)

        if not output_gpkg.exists():
            print(" ❌ sammanslagning misslyckades")
            continue

        gpkg_size_mb = output_gpkg.stat().st_size / 1e6
        print(f" → {gpkg_size_mb:.0f} MB ✓")

    # ── Städa upp ndjson-tempfilen ─────────────────────────────────────────
    ndjson_file.unlink(missing_ok=True)

    log.info("Förenkling klar!")
    log.info("Utdata i: %s", output_path)


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
