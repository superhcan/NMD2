"""
steg_8_simplify.py — Steg 8: Mapshaper-baserad vektorförenkling med topologibevarand.

Läser vektoriserade GeoPackage-filer från Steg 7 och förenklar dem med Mapshaper CLI
med topologibevarand (shared arcs istället för individ polygoner).

Processas:
  - generalized_conn4_mmu008.gpkg
  - generalized_conn8_mmu008.gpkg
  - generalized_majority_k15.gpkg

Tolerances: [90, 75, 50, 25, 15]% of removable vertices to retain

Kör: python3 src/steg_8_simplify.py

Kräver: Mapshaper installerat och i PATH
	npm install -g mapshaper
"""

import subprocess
import os
import logging
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
import sys
from config import (
    OUT_BASE, SIMPLIFICATION_TOLERANCES, SIMPLIFY_PROTECTED, SIMPLIFY_BACKEND,
    GRASS_SIMPLIFY_THRESHOLD, GRASS_SIMPLIFY_METHOD,
    GRASS_CHAIKEN_THRESHOLD, GRASS_DOUGLAS_THRESHOLD,
    GRASS_VECTOR_MEMORY, GRASS_PARALLEL_GPKG, GRASS_OMP_THREADS,
    SRC, TILE_SIZE, PARENT_TILES,
    GRASS_USE_TILED, GRASS_TILE_ROWS, GRASS_TILE_ROW_OVERLAP,
    GRASS_SNAP_TOLERANCE, GRASS_MERGE_BEFORE_GENERALIZE,
)

def setup_logging(out_base):
    """Skapar en logger med tre handlers: debug-fil, summary-fil och console.

    Debug-filen tar emot alla nivåer (DEBUG+); summary-fil och console tar
    bara INFO+. Loggernamnet är 'pipeline.simplify'.
    Loggfilnamnen inkluderar steginfo (STEP_NUMBER/STEP_NAME) från miljövariabler
    om de finns, annars bara en tidsstampel.
    """
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
        variant_name: Name of variant (e.g. 'conn4_mmu008', 'conn8_mmu008', 'majority_k15')
        tolerances: List of percentage values (% of removable vertices to retain)
                   90% = minimal simplification, 15% = very aggressive
        log: Logger instance
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


def simplify_with_grass(
    input_file, output_dir, variant_name,
    method=None, chaiken_threshold=None, douglas_threshold=None, log=None
):
    """
    Förenkla GeoPackage med GRASS v.generalize.

    GRASS håller ett internt topologinät — angränsande polygoner delar exakt
    samma förenklade kanter → inga luckor eller överlapp längs sömmar.
    Diskbaserad bearbetning: ingen Node.js string-gräns.

    Args:
        input_file:         Path till käll-GPKG (från steg 7)
        output_dir:         Katalog för output-filer
        variant_name:       t.ex. 'conn4_mmu050'
        method:             "douglas", "chaiken" eller "douglas+chaiken"
                            Default: GRASS_SIMPLIFY_METHOD från config
        chaiken_threshold:  Meter — min avstånd mellan punkter i Chaikin-output
                            Default: GRASS_CHAIKEN_THRESHOLD från config
        douglas_threshold:  Meter — Douglas-tolerans för förpass eller douglas-only
                            Default: GRASS_DOUGLAS_THRESHOLD från config
        log:                Logger
    """
    if log is None:
        log = logging.getLogger("pipeline.simplify")

    # Fyll i defaults från config om inget angetts
    if method is None:
        method = GRASS_SIMPLIFY_METHOD
    if chaiken_threshold is None:
        chaiken_threshold = GRASS_CHAIKEN_THRESHOLD
    if douglas_threshold is None:
        douglas_threshold = GRASS_DOUGLAS_THRESHOLD

    input_path = Path(input_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        log.error(f"Input-fil saknas: {input_file}")
        sys.exit(1)

    log.info(f"GRASS v.generalize: {input_path.name}")
    log.info(f"  Metod           : {method}")
    if method in ("chaiken", "douglas+chaiken"):
        log.info(f"  Chaikin tröskel : {chaiken_threshold:.1f} m")
    if method in ("douglas", "douglas+chaiken"):
        log.info(f"  Douglas tröskel : {douglas_threshold:.1f} m")
    log.info(f"  Output          : {output_path}")

    # Detektera exakt lagernamn i GPKG (kan skilja sig från filnamnet, t.ex. "DN")
    r = subprocess.run(
        ["ogrinfo", "-q", str(input_path)],
        capture_output=True, text=True
    )
    layer_name = None
    for line in r.stdout.splitlines():
        parts = line.strip().split(":", 1)
        if len(parts) == 2 and parts[0].strip().isdigit():
            layer_name = parts[1].strip().split(" ")[0]
            break
    if not layer_name:
        log.error(f"Kunde inte detektera lagernamn i {input_path.name}: {r.stdout}")
        return
    log.info(f"  Lagernamn i GPKG: '{layer_name}'")

    def _run_grass(grass_script_text, output_gpkg, label):
        """Hjälpfunktion: skriv skript, kör GRASS, logga resultat."""
        # Föredra /dev/shm (RAM-disk) för GRASS tempfiler om tillräckligt ledigt
        tmpbase = None
        shm = Path("/dev/shm")
        if shm.exists():
            try:
                free_shm = shutil.disk_usage(str(shm)).free
                if free_shm > 10 * 2**30:  # >10 GB ledigt i /dev/shm
                    tmpbase = str(shm)
            except OSError:
                pass
        grass_tmp = Path(tempfile.mkdtemp(prefix="grass_nmd_", dir=tmpbase))
        script_path = grass_tmp / "run_grass.py"
        script_path.write_text(grass_script_text)
        try:
            cmd = [
                "grass", "--tmp-project", "EPSG:3006",
                "--exec", "python3", str(script_path)
            ]
            # Sätt GRASS_VECTOR_MEMORY så topologinätet hålls i RAM.
            # OMP_NUM_THREADS låter OpenMP-stödda delar använda flera kärnor.
            grass_env = {
                **os.environ,
                "GRASS_VECTOR_MEMORY": str(GRASS_VECTOR_MEMORY),
                "OMP_NUM_THREADS": str(GRASS_OMP_THREADS),
            }
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=grass_env
            )
            for line in proc.stdout:
                line = line.strip()
                if line:
                    log.info(f"  [grass] {line}")
            proc.wait()

            if proc.returncode != 0:
                log.error(f"  {label}: ❌ GRASS misslyckades (rc={proc.returncode})")
                return False

            if output_gpkg.exists():
                gpkg_size = output_gpkg.stat().st_size / 1024 / 1024
                log.info(f"  {label}: ✓ {output_gpkg.name} ({gpkg_size:.1f} MB)")
                return True
            else:
                log.error(f"  {label}: ❌ Output GPKG saknas")
                return False
        finally:
            shutil.rmtree(grass_tmp, ignore_errors=True)

    grass_script_header = """\
#!/usr/bin/env python3
import subprocess, sys

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.stderr.strip():
        print(r.stderr.strip(), file=sys.stderr)
    if r.returncode != 0:
        sys.exit(r.returncode)
"""

    if method == "douglas":
        dp = int(round(douglas_threshold))
        output_gpkg = output_path / f"{variant_name}_dp{dp}.gpkg"
        label = f"douglas {douglas_threshold:.1f} m"
        log.info(f"  {label}: Startar GRASS...")

        script = grass_script_header + f"""
run(["v.in.ogr", "input={input_path}", "layer={layer_name}",
     "output={layer_name}", "--overwrite", "--quiet"])
run(["v.generalize", "input={layer_name}", "output=simplified",
     "method=douglas", "threshold={douglas_threshold:.2f}", "--overwrite", "--quiet"])
run(["v.clean", "input=simplified", "output=cleaned",
     "tool=bpol,rmdupl", "--overwrite", "--quiet"])
run(["v.out.ogr", "input=cleaned", "output={output_gpkg}",
     "format=GPKG", "--overwrite", "--quiet"])
print("OK")
"""
        _run_grass(script, output_gpkg, label)

    elif method == "chaiken":
        # Enkelt pass — ett utfilnamn, ingen tolerance-loop
        t = int(round(chaiken_threshold))
        output_gpkg = output_path / f"{variant_name}_chaiken_t{t}.gpkg"
        label = f"chaiken (threshold={chaiken_threshold:.1f} m)"
        log.info(f"  {label}: Startar GRASS...")

        script = grass_script_header + f"""
run(["v.in.ogr", "input={input_path}", "layer={layer_name}",
     "output={layer_name}", "--overwrite", "--quiet"])
run(["v.generalize", "input={layer_name}", "output=simplified",
     "method=chaiken", "threshold={chaiken_threshold:.2f}", "--overwrite", "--quiet"])
run(["v.clean", "input=simplified", "output=cleaned",
     "tool=bpol,rmdupl", "--overwrite", "--quiet"])
run(["v.out.ogr", "input=cleaned", "output={output_gpkg}",
     "format=GPKG", "--overwrite", "--quiet"])
print("OK")
"""
        _run_grass(script, output_gpkg, label)

    elif method == "douglas+chaiken":
        # Två pass i samma GRASS-session: Douglas städar bort kolineära punkter,
        # Chaikin rundar sedan hörnen.
        dp = int(round(douglas_threshold))
        ch = int(round(chaiken_threshold))
        output_gpkg = output_path / f"{variant_name}_dp{dp}_chaiken_t{ch}.gpkg"
        label = f"douglas({douglas_threshold:.1f} m) + chaiken({chaiken_threshold:.1f} m)"
        log.info(f"  {label}: Startar GRASS...")

        script = grass_script_header + f"""
run(["v.in.ogr", "input={input_path}", "layer={layer_name}",
     "output={layer_name}", "--overwrite", "--quiet"])
run(["v.generalize", "input={layer_name}", "output=after_douglas",
     "method=douglas", "threshold={douglas_threshold:.2f}", "--overwrite", "--quiet"])
run(["v.generalize", "input=after_douglas", "output=simplified",
     "method=chaiken", "threshold={chaiken_threshold:.2f}", "--overwrite", "--quiet"])
run(["v.clean", "input=simplified", "output=cleaned",
     "tool=bpol,rmdupl", "--overwrite", "--quiet"])
run(["v.out.ogr", "input=cleaned", "output={output_gpkg}",
     "format=GPKG", "--overwrite", "--quiet"])
print("OK")
"""
        _run_grass(script, output_gpkg, label)

    else:
        log.error(f"Okänd GRASS_SIMPLIFY_METHOD: '{method}'. Välj 'douglas', 'chaiken' eller 'douglas+chaiken'.")
        return

    log.info(f"GRASS-förenkling klar! Output i: {output_path}")


def simplify_with_grass_tiled(
    input_file, output_dir, variant_name,
    method=None, chaiken_threshold=None, douglas_threshold=None,
    tile_rows_per_chunk=1, row_overlap=1, log=None
):
    """
    Tilebaserad GRASS-förenkling med rad-baserat överlapp.

    Delar input-GPKG:n i horisontella bands (hela tile-rader), kör GRASS
    parallellt på varje band med row_overlap raders buffert ovanför/nedanför,
    klipper sedan tillbaka till ägda rader och sätter ihop till en slutfil.

    Överlapp per hela rader garanterar att polygoner som sträcker sig över
    tile-gränserna alltid ses i sin helhet av GRASS → DP-algoritmen ger
    identisk förenkling → sömmarna matchar pixelperfekt efter klippning.

    Args:
        input_file:           Path till käll-GPKG (från steg 7)
        output_dir:           Katalog för output-filer
        variant_name:         t.ex. 'conn4_morph_disk_r02'
        method/thresholds:    Se simplify_with_grass()
        tile_rows_per_chunk:  Antal tile-rader per GRASS-jobb
        row_overlap:          Extra buff-rader ovanför och nedanför (hel tile-rader)
        log:                  Logger
    """
    import json as _json

    if log is None:
        log = logging.getLogger("pipeline.simplify")
    if method is None:
        method = GRASS_SIMPLIFY_METHOD
    if chaiken_threshold is None:
        chaiken_threshold = GRASS_CHAIKEN_THRESHOLD
    if douglas_threshold is None:
        douglas_threshold = GRASS_DOUGLAS_THRESHOLD

    input_path = Path(input_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        log.error(f"Input-fil saknas: {input_file}")
        return

    # ── Geotransform från källrastern via gdalinfo ─────────────────────────
    _gi = subprocess.run(
        ["gdalinfo", "-json", str(SRC)],
        capture_output=True, text=True
    )
    if _gi.returncode != 0:
        log.error(f"gdalinfo misslyckades: {_gi.stderr[:200]}")
        return
    _info = _json.loads(_gi.stdout)
    _gt = _info["geoTransform"]   # [x_origin, px_w, 0, y_origin, 0, -px_h]
    x_origin = _gt[0]             # Vänster X
    y_origin = _gt[3]             # Övre Y (rasterets nordkant)
    px_w     = _gt[1]             # Pixelbredd (m)
    px_h     = abs(_gt[5])        # Pixelhöjd (m, positivt)
    ts = TILE_SIZE           # px per tile-rad

    # ── Bygg chunk-lista ───────────────────────────────────────────────────
    parent_rows = sorted(set(r for r, c in PARENT_TILES))
    parent_cols = sorted(set(c for r, c in PARENT_TILES))
    x_min = x_origin + parent_cols[0] * ts * px_w
    x_max = x_origin + (parent_cols[-1] + 1) * ts * px_w

    def _row_y_top(rno):
        return y_origin - rno * ts * px_h

    def _row_y_bot(rno):
        return y_origin - (rno + 1) * ts * px_h

    chunks = []
    n = len(parent_rows)
    for i in range(0, n, tile_rows_per_chunk):
        owned_idxs   = list(range(i, min(i + tile_rows_per_chunk, n)))
        ov_start_idx = max(0, i - row_overlap)
        ov_end_idx   = min(n - 1, i + tile_rows_per_chunk - 1 + row_overlap)
        overlap_idxs = list(range(ov_start_idx, ov_end_idx + 1))

        owned_rows   = [parent_rows[j] for j in owned_idxs]
        overlap_rows = [parent_rows[j] for j in overlap_idxs]

        chunks.append({
            "idx":        i // tile_rows_per_chunk,
            "owned_rows": owned_rows,
            "y_ow_max":   _row_y_top(owned_rows[0]),
            "y_ow_min":   _row_y_bot(owned_rows[-1]),
            "y_ov_max":   _row_y_top(overlap_rows[0]),
            "y_ov_min":   _row_y_bot(overlap_rows[-1]),
        })

    # Bestäm output-filnamn (samma konvention som simplify_with_grass)
    if method == "douglas":
        dp = int(round(douglas_threshold))
        final_gpkg = output_path / f"{variant_name}_dp{dp}.gpkg"
    elif method == "chaiken":
        t = int(round(chaiken_threshold))
        final_gpkg = output_path / f"{variant_name}_chaiken_t{t}.gpkg"
    elif method == "douglas+chaiken":
        dp = int(round(douglas_threshold))
        ch = int(round(chaiken_threshold))
        final_gpkg = output_path / f"{variant_name}_dp{dp}_chaiken_t{ch}.gpkg"
    else:
        log.error(f"Okänd GRASS_SIMPLIFY_METHOD: '{method}'")
        return

    # Detektera lagernamn i input-GPKG
    r_info = subprocess.run(["ogrinfo", "-q", str(input_path)], capture_output=True, text=True)
    input_layer = None
    for line in r_info.stdout.splitlines():
        parts = line.strip().split(":", 1)
        if len(parts) == 2 and parts[0].strip().isdigit():
            input_layer = parts[1].strip().split(" ")[0]
            break
    if not input_layer:
        log.error(f"Kunde inte detektera lagernamn i {input_path.name}")
        sys.exit(1)

    log.info(f"GRASS tileförenkling: {input_path.name}")
    log.info(f"  Metod   : {method}")
    log.info(f"  Chunks  : {len(chunks)} st (à {tile_rows_per_chunk} tilerad(er), ±{row_overlap} rad överlapp)")
    log.info(f"  Lager   : '{input_layer}'")
    log.info(f"  X-extent: {x_min:.0f} – {x_max:.0f}")

    work_dir = output_path / f"_tiles_tmp_{variant_name}"
    work_dir.mkdir(exist_ok=True)

    # ── GRASS-skript-mall ──────────────────────────────────────────────────
    _grass_header = """\
#!/usr/bin/env python3
import subprocess, sys

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.stderr.strip():
        print(r.stderr.strip(), file=sys.stderr)
    if r.returncode != 0:
        sys.exit(r.returncode)
"""

    # ══════════════════════════════════════════════════════════════════════
    # MERGE-FIRST-LÄGE: centroid-extraktion → enskild GRASS-session
    # Generaliseringen sker på hela datasetet → inga topologiska sömglapp.
    # ══════════════════════════════════════════════════════════════════════
    if GRASS_MERGE_BEFORE_GENERALIZE:
        # Detektera geometrikolumn i input-GPKG
        _r_schema = subprocess.run(
            ["ogrinfo", "-al", "-so", str(input_path)],
            capture_output=True, text=True
        )
        _input_geom_col = "geometry"
        for _l in _r_schema.stdout.splitlines():
            if _l.strip().lower().startswith("geometry column"):
                _p = _l.split("=", 1)
                if len(_p) == 2:
                    _input_geom_col = _p[1].strip()
                    break

        def _extract_owned(chunk):
            """Extraherar polygoner vars centroid ligger inom chunk:ens ägda rader.

            Använder ST_Centroid-filter i steg för centroid-ägarskap så att
            varje polygon tilldelas exakt en chunk oavsett hur stor den är.
            Ingen geometri klipps — fullständiga polygoner skickas vidare
            till GRASS så att topologin byggs korrekt.
            """
            ci       = chunk["idx"]
            y_ow_min = chunk["y_ow_min"]
            y_ow_max = chunk["y_ow_max"]
            rows_lbl = str(chunk["owned_rows"])
            cdir     = work_dir / f"chunk_{ci:03d}"
            cdir.mkdir(exist_ok=True)
            part_lyr = f"part_{ci:03d}"
            ex_gpkg  = cdir / "owned.gpkg"
            own_wkt  = (
                f"POLYGON(("
                f"{x_min:.2f} {y_ow_min:.2f},"
                f"{x_max:.2f} {y_ow_min:.2f},"
                f"{x_max:.2f} {y_ow_max:.2f},"
                f"{x_min:.2f} {y_ow_max:.2f},"
                f"{x_min:.2f} {y_ow_min:.2f}"
                f"))"
            )
            _sql = (
                f'SELECT * FROM "{input_layer}" '
                f'WHERE ST_Intersects(ST_Centroid("{_input_geom_col}"), '
                f"ST_GeomFromText('{own_wkt}'))"
            )
            _r = subprocess.run([
                "ogr2ogr", "-f", "GPKG",
                "-nln", part_lyr,
                "-dialect", "SQLite",
                "-sql", _sql,
                str(ex_gpkg), str(input_path),
            ], capture_output=True, text=True)
            if _r.returncode != 0 or not ex_gpkg.exists():
                log.error(f"  chunk {ci}: ❌ ogr2ogr: {_r.stderr[:300]}")
                return None
            log.info(f"  chunk {ci} rader={rows_lbl}: extraherat {ex_gpkg.stat().st_size/1024**2:.1f} MB")
            return (ci, part_lyr, ex_gpkg)

        log.info(f"Phase 1: centroid-extraktion — {len(chunks)} chunks "
                 f"(max {min(len(chunks), GRASS_PARALLEL_GPKG)} parallellt)")
        with ThreadPoolExecutor(max_workers=min(len(chunks), GRASS_PARALLEL_GPKG)) as _pool:
            _res = list(_pool.map(_extract_owned, chunks))
        _res = sorted([r for r in _res if r is not None], key=lambda x: x[0])
        if not _res:
            log.error("❌ Ingen chunk extraherades!")
            sys.exit(1)
        log.info(f"  ✓ {len(_res)}/{len(chunks)} chunks extraherade")

        log.info("Phase 2: enskild GRASS-session "
                 "— v.in.ogr × N → v.patch → v.generalize → v.clean → v.out.ogr")

        _glines  = [_grass_header]
        _maplist = []
        for _ci, _lyr, _gpkg in _res:
            _mname = f"m{_ci:03d}"
            _maplist.append(_mname)
            _glines.append(
                f'run(["v.in.ogr", "input={_gpkg}", "layer={_lyr}", '
                f'"output={_mname}", "--overwrite", "--quiet"])\n'
                f'print("  v.in.ogr chunk {_ci}: OK")'
            )

        _maps_csv = ",".join(_maplist)
        _glines.append(
            f'run(["v.patch", "input={_maps_csv}", "output=merged", "-e", "--overwrite", "--quiet"])\n'
            f'print("  v.patch: OK")'
        )

        if method == "douglas":
            _glines.append(
                f'run(["v.generalize", "input=merged", "output=simplified", '
                f'"method=douglas", "threshold={douglas_threshold:.2f}", "--overwrite", "--quiet"])\n'
                f'print("  v.generalize (douglas): OK")'
            )
        elif method == "chaiken":
            _glines.append(
                f'run(["v.generalize", "input=merged", "output=simplified", '
                f'"method=chaiken", "threshold={chaiken_threshold:.2f}", "--overwrite", "--quiet"])\n'
                f'print("  v.generalize (chaiken): OK")'
            )
        elif method == "douglas+chaiken":
            _glines.append(
                f'run(["v.generalize", "input=merged", "output=after_dp", '
                f'"method=douglas", "threshold={douglas_threshold:.2f}", "--overwrite", "--quiet"])\n'
                f'run(["v.generalize", "input=after_dp", "output=simplified", '
                f'"method=chaiken", "threshold={chaiken_threshold:.2f}", "--overwrite", "--quiet"])\n'
                f'print("  v.generalize (douglas+chaiken): OK")'
            )

        _glines.append(
            'run(["v.clean", "input=simplified", "output=cleaned", '
            '"tool=snap,rmdupl,bpol", "threshold=0.01,0,0", "--overwrite", "--quiet"])\n'
            'print("  v.clean: OK")'
        )
        _glines.append(
            f'run(["v.out.ogr", "input=cleaned", "output={final_gpkg}", '
            f'"format=GPKG", "--overwrite", "--quiet"])\n'
            f'print("  v.out.ogr: OK")'
        )

        _gs = "\n".join(_glines)
        _tmpbase = None
        _shm = Path("/dev/shm")
        if _shm.exists():
            try:
                if shutil.disk_usage(str(_shm)).free > 8 * 2**30:
                    _tmpbase = str(_shm)
            except OSError:
                pass
        _gtmp = Path(tempfile.mkdtemp(prefix="grass_merge_", dir=_tmpbase))
        try:
            _script = _gtmp / "run.py"
            _script.write_text(_gs)
            _genv = {
                **os.environ,
                "GRASS_VECTOR_MEMORY": str(GRASS_VECTOR_MEMORY),
                "OMP_NUM_THREADS":     str(GRASS_OMP_THREADS),
            }
            _proc = subprocess.Popen(
                ["grass", "--tmp-project", "EPSG:3006", "--exec", "python3", str(_script)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=_genv
            )
            for _ln in _proc.stdout:
                _ln = _ln.strip()
                if _ln:
                    log.info(f"  [grass] {_ln}")
            _proc.wait()
        finally:
            shutil.rmtree(_gtmp, ignore_errors=True)

        if not final_gpkg.exists():
            log.error("❌ GRASS merge-first: v.out.ogr producerade ingen fil!")
            sys.exit(1)

        log.info(f"  ✓ Slutfil: {final_gpkg.name} ({final_gpkg.stat().st_size/1024**2:.1f} MB)")
        shutil.rmtree(work_dir, ignore_errors=True)
        log.info(f"GRASS merge-first klar! Output: {output_path}")
        return  # ← hoppa över gammal per-chunk-kod nedan

    # ══════════════════════════════════════════════════════════════════════
    # GAMMAL PER-CHUNK-KOD (GRASS_MERGE_BEFORE_GENERALIZE = False)
    # ══════════════════════════════════════════════════════════════════════
    def process_chunk(chunk):
        """Bearbetar ett enskilt band-chunk i tre steg:

          A) Extrahera överlappszon (spatial filter, geometrier klipps EJ) → extract.gpkg
          B) Kör GRASS v.generalize på extraherad GPKG → simplified.gpkg
          C) Centroid-filter: behåll bara polygoner vars centroid ligger inom
             ägda rader (y_ow_min … y_ow_max) → owned.gpkg

        Returnerar Path till owned.gpkg, eller None vid fel.
        """
        ci        = chunk["idx"]
        y_ov_min  = chunk["y_ov_min"]
        y_ov_max  = chunk["y_ov_max"]
        y_ow_min  = chunk["y_ow_min"]
        y_ow_max  = chunk["y_ow_max"]
        rows_lbl  = str(chunk["owned_rows"])

        chunk_dir = work_dir / f"chunk_{ci:03d}"
        chunk_dir.mkdir(exist_ok=True)

        # A) Extrahera överlappszonen (spatial filter — geometrierna klipps EJ här,
        #    så GRASS ser kompletta polygoner och kan bygga korrekt topologi)
        extract_gpkg = chunk_dir / "extract.gpkg"
        r1 = subprocess.run([
            "ogr2ogr", "-f", "GPKG",
            "-spat", f"{x_min:.2f}", f"{y_ov_min:.2f}", f"{x_max:.2f}", f"{y_ov_max:.2f}",
            str(extract_gpkg), str(input_path),
        ], capture_output=True, text=True)
        if r1.returncode != 0 or not extract_gpkg.exists():
            log.error(f"  chunk {ci}: ❌ ogr2ogr extract: {r1.stderr[:300]}")
            return None
        ex_mb = extract_gpkg.stat().st_size / 1024**2
        log.info(f"  chunk {ci} rader={rows_lbl}: extraherat {ex_mb:.1f} MB")

        # Detektera lagernamn i extraherad GPKG
        r_il = subprocess.run(["ogrinfo", "-q", str(extract_gpkg)], capture_output=True, text=True)
        chunk_layer = input_layer
        for line in r_il.stdout.splitlines():
            parts = line.strip().split(":", 1)
            if len(parts) == 2 and parts[0].strip().isdigit():
                chunk_layer = parts[1].strip().split(" ")[0]
                break

        # B) Bygg GRASS-skript
        simplified_gpkg = chunk_dir / "simplified.gpkg"
        grass_body = f"""
run(["v.in.ogr", "input={extract_gpkg}", "layer={chunk_layer}",
     "output={chunk_layer}", "--overwrite", "--quiet"])
"""
        if method == "douglas":
            grass_body += f"""
run(["v.generalize", "input={chunk_layer}", "output=simplified",
     "method=douglas", "threshold={douglas_threshold:.2f}", "--overwrite", "--quiet"])
"""
        elif method == "chaiken":
            grass_body += f"""
run(["v.generalize", "input={chunk_layer}", "output=simplified",
     "method=chaiken", "threshold={chaiken_threshold:.2f}", "--overwrite", "--quiet"])
"""
        elif method == "douglas+chaiken":
            grass_body += f"""
run(["v.generalize", "input={chunk_layer}", "output=after_dp",
     "method=douglas", "threshold={douglas_threshold:.2f}", "--overwrite", "--quiet"])
run(["v.generalize", "input=after_dp", "output=simplified",
     "method=chaiken", "threshold={chaiken_threshold:.2f}", "--overwrite", "--quiet"])
"""
        grass_body += f"""
run(["v.clean", "input=simplified", "output=cleaned",
     "tool=bpol,rmdupl", "--overwrite", "--quiet"])
run(["v.out.ogr", "input=cleaned", "output={simplified_gpkg}",
     "format=GPKG", "--overwrite", "--quiet"])
print("OK")
"""
        # Välj tempkatalog — föredra /dev/shm om tillräckligt ledigt
        tmpbase = None
        shm = Path("/dev/shm")
        if shm.exists():
            try:
                if shutil.disk_usage(str(shm)).free > 2 * 2**30:
                    tmpbase = str(shm)
            except OSError:
                pass
        grass_tmp = Path(tempfile.mkdtemp(prefix=f"grass_c{ci}_", dir=tmpbase))
        script_path = grass_tmp / "run.py"
        script_path.write_text(_grass_header + grass_body)

        # Fördela GRASS_VECTOR_MEMORY jämnt mellan alla chunk-jobb
        chunk_mem = max(4000, GRASS_VECTOR_MEMORY // len(chunks))
        grass_env = {
            **os.environ,
            "GRASS_VECTOR_MEMORY": str(chunk_mem),
            "OMP_NUM_THREADS":     str(GRASS_OMP_THREADS),
        }
        try:
            cmd = ["grass", "--tmp-project", "EPSG:3006", "--exec", "python3", str(script_path)]
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=grass_env
            )
            for line in proc.stdout:
                line = line.strip()
                if line:
                    log.info(f"  [grass c{ci}] {line}")
            proc.wait()
        finally:
            shutil.rmtree(grass_tmp, ignore_errors=True)

        if not simplified_gpkg.exists():
            log.error(f"  chunk {ci}: ❌ GRASS-output saknas")
            return None
        log.info(f"  chunk {ci}: GRASS klar → {simplified_gpkg.stat().st_size/1024**2:.1f} MB")

        # C) Filtrera med centroid-ägarskap — ingen polygon klipps.
        #    Vi behåller bara polygoner vars centroid ligger inom ägda rader.
        clipped_gpkg = chunk_dir / "owned.gpkg"
        # Detektera lagernamn i simplified_gpkg
        r_sl = subprocess.run(["ogrinfo", "-q", str(simplified_gpkg)], capture_output=True, text=True)
        simp_layer = chunk_layer
        for line in r_sl.stdout.splitlines():
            parts = line.strip().split(":", 1)
            if len(parts) == 2 and parts[0].strip().isdigit():
                simp_layer = parts[1].strip().split(" ")[0]
                break
        # Detektera geometrikolumnens exakta namn (GRASS v.out.ogr använder ofta "geom")
        r_schema = subprocess.run(
            ["ogrinfo", "-al", "-so", str(simplified_gpkg)],
            capture_output=True, text=True
        )
        geom_col = "geometry"  # fallback
        for line in r_schema.stdout.splitlines():
            if line.strip().lower().startswith("geometry column"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    geom_col = parts[1].strip()
                    break
        own_wkt = (
            f"POLYGON(("
            f"{x_min:.2f} {y_ow_min:.2f},"
            f"{x_max:.2f} {y_ow_min:.2f},"
            f"{x_max:.2f} {y_ow_max:.2f},"
            f"{x_min:.2f} {y_ow_max:.2f},"
            f"{x_min:.2f} {y_ow_min:.2f}"
            f"))"
        )
        sql = (
            f"SELECT * FROM \"{simp_layer}\" "
            f"WHERE ST_Intersects(ST_Centroid(\"{geom_col}\"), "
            f"ST_GeomFromText('{own_wkt}'))"
        )
        r3 = subprocess.run([
            "ogr2ogr", "-f", "GPKG",
            "-dialect", "SQLite",
            "-sql", sql,
            str(clipped_gpkg), str(simplified_gpkg),
        ], capture_output=True, text=True)
        if r3.returncode != 0 or not clipped_gpkg.exists():
            log.error(f"  chunk {ci}: ❌ centroid-filter: {r3.stderr[:300]}")
            return None
        log.info(f"  chunk {ci}: ✓ centroid-filtrerat → {clipped_gpkg.stat().st_size/1024**2:.1f} MB")
        return clipped_gpkg

    # ── Kör alla chunks parallellt ─────────────────────────────────────────
    n_workers = min(len(chunks), GRASS_PARALLEL_GPKG)
    log.info(f"Startar {len(chunks)} chunk-jobb (max {n_workers} parallellt)")
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        clipped_files = list(ex.map(process_chunk, chunks))

    # Filtrera bort chunks som returnerade None (misslyckade)
    clipped_files = [f for f in clipped_files if f is not None]
    if not clipped_files:
        log.error("❌ Inga chunks slutfördes!")
        sys.exit(1)

    # ── Sätt ihop alla klippta delar ──────────────────────────────────────
    log.info(f"Sätter ihop {len(clipped_files)} chunks → {final_gpkg.name}")
    if final_gpkg.exists():
        final_gpkg.unlink()
    for i, cfile in enumerate(clipped_files):
        if i == 0:
            # Första chunk skapar filen och sätter schema
            r_m = subprocess.run(
                ["ogr2ogr", "-f", "GPKG", str(final_gpkg), str(cfile)],
                capture_output=True, text=True
            )
        else:
            # Följande chunks läggs till med -append -update (schema måste matcha)
            r_m = subprocess.run(
                ["ogr2ogr", "-f", "GPKG", "-append", "-update", str(final_gpkg), str(cfile)],
                capture_output=True, text=True
            )
        if r_m.returncode != 0:
            log.error(f"  ❌ Merge chunk {i}: {r_m.stderr[:200]}")

    if not final_gpkg.exists():
        log.error("❌ Merge producerade ingen fil!")
        shutil.rmtree(work_dir, ignore_errors=True)
        sys.exit(1)

    log.info(f"  ✓ Slutfil: {final_gpkg.name} ({final_gpkg.stat().st_size/1024**2:.1f} MB)")

    # ── D) Glapp-läkning via ST_Buffer(+δ) ────────────────────────────────
    # Varje polygon expanderas med GRASS_SNAP_TOLERANCE meter. Glapp < 2δ
    # ersätts av mikroöverlapp (<1 m) som är osynliga i rendering.
    # Ingen GRASS-session behövs — ren ogr2ogr/SpatiaLite SQL. ~sekunder.
    if GRASS_SNAP_TOLERANCE and GRASS_SNAP_TOLERANCE > 0:
        log.info(f"Glapp-läkning: ST_Buffer +{GRASS_SNAP_TOLERANCE}m på varje polygon")
        healed_gpkg = output_path / final_gpkg.name.replace(".gpkg", "_healed.gpkg")

        # Detektera lagernamn i final_gpkg
        r_fl = subprocess.run(["ogrinfo", "-q", str(final_gpkg)], capture_output=True, text=True)
        final_layer = variant_name
        for line in r_fl.stdout.splitlines():
            parts = line.strip().split(":", 1)
            if len(parts) == 2 and parts[0].strip().isdigit():
                final_layer = parts[1].strip().split(" ")[0]
                break

        # Detektera geometrikolumnens namn
        r_schema = subprocess.run(
            ["ogrinfo", "-al", "-so", str(final_gpkg)],
            capture_output=True, text=True
        )
        geom_col_final = "geom"
        for line in r_schema.stdout.splitlines():
            if line.strip().lower().startswith("geometry column"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    geom_col_final = parts[1].strip()
                    break

        sql_heal = (
            f'SELECT DN, ST_Buffer("{geom_col_final}", {GRASS_SNAP_TOLERANCE:.4f}) AS geom '
            f'FROM "{final_layer}"'
        )
        r_heal = subprocess.run([
            "ogr2ogr", "-f", "GPKG",
            "-dialect", "SQLite",
            "-sql", sql_heal,
            str(healed_gpkg), str(final_gpkg),
        ], capture_output=True, text=True)

        if r_heal.returncode == 0 and healed_gpkg.exists():
            final_gpkg.unlink()
            healed_gpkg.rename(final_gpkg)
            log.info(f"  ✓ Glapp-läkning klar: {final_gpkg.name} ({final_gpkg.stat().st_size/1024**2:.1f} MB)")
        else:
            log.warning(f"  ⚠ Glapp-läkning misslyckades — behåller oreparerad merge-fil")
            if r_heal.stderr:
                log.warning(f"  {r_heal.stderr[:200]}")
            if healed_gpkg.exists():
                healed_gpkg.unlink()

    shutil.rmtree(work_dir, ignore_errors=True)
    log.info(f"GRASS tileförenkling klar! Output i: {output_path}")


if __name__ == "__main__":
    import time as _time
    _t0 = _time.time()
    log = setup_logging(OUT_BASE)

    vectorized_dir = OUT_BASE / "steg_7_vectorize"
    output_dir = OUT_BASE / "steg_8_simplify"
    tolerances = SIMPLIFICATION_TOLERANCES

    # Välj backend
    backend = SIMPLIFY_BACKEND.lower()
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 8: Vektorförenkling (backend: %s)", backend.upper())
    log.info("Källmapp : %s", vectorized_dir)
    log.info("Utmapp   : %s", output_dir)
    if backend in ("grass", "auto"):
        log.info("── GRASS-konfiguration ───────────────────────────────")
        log.info("  Metod              : %s", GRASS_SIMPLIFY_METHOD)
        if GRASS_SIMPLIFY_METHOD in ("chaiken", "douglas+chaiken"):
            log.info("  Chaikin tröskel    : %.1f m", GRASS_CHAIKEN_THRESHOLD)
        if GRASS_SIMPLIFY_METHOD in ("douglas", "douglas+chaiken"):
            log.info("  Douglas tröskel    : %.1f m", GRASS_DOUGLAS_THRESHOLD)
        if GRASS_USE_TILED:
            log.info("  Tileläge           : PÅ (%d rad/chunk, ±%d rads överlapp)",
                     GRASS_TILE_ROWS, GRASS_TILE_ROW_OVERLAP)
        else:
            log.info("  Tileläge           : AV (ett jobb per GPKG)")
    if backend in ("mapshaper", "auto"):
        log.info("── Mapshaper-konfiguration ───────────────────────────")
        log.info("  Tolerance-nivåer   : %s %%", SIMPLIFICATION_TOLERANCES)
        if SIMPLIFY_PROTECTED:
            log.info("  Skyddade klasser   : %s (förenklas ej)", sorted(SIMPLIFY_PROTECTED))
    log.info("══════════════════════════════════════════════════════════")

    # Rensa inaktuella gpkg-filer (metoder som tagits bort från config)
    from config import GENERALIZATION_METHODS
    all_methods = {"conn4", "conn8", "majority", "semantic"}
    if output_dir.exists():
        for method in all_methods - GENERALIZATION_METHODS:
            for stale in output_dir.glob(f"{method}_*_simplified_*.gpkg"):
                stale.unlink()
                log.info("  Raderat inaktuell fil: %s", stale.name)

    # Hämta alla GeoPackage-filer från steg 7
    if vectorized_dir.exists():
        gpkg_files = sorted(vectorized_dir.glob("generalized_*.gpkg"))
        if not gpkg_files:
            log.warning("Inga GeoPackage-filer hittades i %s", vectorized_dir)
        else:
            def _process_gpkg(input_file):
                """Behandlar en enstaka GPKG från steg 7.

                Väljer backend (mapshaper eller GRASS) baserat på SIMPLIFY_BACKEND:
                  'mapshaper' : alltid Mapshaper
                  'grass'     : alltid GRASS
                  'auto'      : GRASS om filen är > 800 MB, annars Mapshaper

                Vid GRASS avgjör GRASS_USE_TILED om tilebaserad (simplify_with_grass_tiled)
                eller enkel (simplify_with_grass) körning används.
                """
                variant_name = input_file.stem.replace("generalized_", "")
                log.info(f"\n➤ {variant_name.upper()}")

                # auto: välj grass om filen är stor
                use_grass = False
                if backend == "grass":
                    use_grass = True
                elif backend == "auto":
                    size_mb = input_file.stat().st_size / 1024 / 1024
                    use_grass = size_mb > 800  # GeoJSON blir ~2.5x → ~2 GB = riskzon
                    log.info(f"  AUTO: {size_mb:.0f} MB GPKG → {'grass' if use_grass else 'mapshaper'}")

                if use_grass:
                    if GRASS_USE_TILED:
                        simplify_with_grass_tiled(
                            input_file, output_dir, variant_name,
                            method=GRASS_SIMPLIFY_METHOD,
                            chaiken_threshold=GRASS_CHAIKEN_THRESHOLD,
                            douglas_threshold=GRASS_DOUGLAS_THRESHOLD,
                            tile_rows_per_chunk=GRASS_TILE_ROWS,
                            row_overlap=GRASS_TILE_ROW_OVERLAP,
                            log=log,
                        )
                    else:
                        simplify_with_grass(
                            input_file, output_dir, variant_name,
                            method=GRASS_SIMPLIFY_METHOD,
                            chaiken_threshold=GRASS_CHAIKEN_THRESHOLD,
                            douglas_threshold=GRASS_DOUGLAS_THRESHOLD,
                            log=log,
                        )
                else:
                    simplify_with_mapshaper(input_file, output_dir, variant_name, tolerances, log)

            # Starta en eller flera workers beroende på hur många GPKG:er som finns.
            # GRASS_PARALLEL_GPKG begränsar hur många GRASS-sessioner som körs samtidigt
            # (var och en kan vara minnesintensiv).
            n_workers = min(len(gpkg_files), GRASS_PARALLEL_GPKG)
            if n_workers > 1:
                log.info(f"Kör {len(gpkg_files)} GPKG:er parallellt (max {n_workers} jobb)")
                with ThreadPoolExecutor(max_workers=n_workers) as ex:
                    list(ex.map(_process_gpkg, gpkg_files))
            else:
                # Sekventiell körning vid enbart ett jobb
                for input_file in gpkg_files:
                    _process_gpkg(input_file)
    else:
        log.error("❌ Vektoriserad katalog saknas: %s", vectorized_dir)

    _elapsed = _time.time() - _t0
    log.info("\n══════════════════════════════════════════════════════════")
    log.info(f"Steg 8 klart: {_elapsed:.0f}s ({_elapsed/60:.1f} min)")
    log.info(f"Output i {output_dir}")
    log.info("══════════════════════════════════════════════════════════")
