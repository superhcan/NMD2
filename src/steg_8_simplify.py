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
    GRASS_VECTOR_MEMORY, GRASS_PARALLEL_GPKG,
)

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
            # Sätt GRASS_VECTOR_MEMORY så topologinätet hålls i RAM
            grass_env = {**os.environ, "GRASS_VECTOR_MEMORY": str(GRASS_VECTOR_MEMORY)}
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
run(["v.out.ogr", "input=simplified", "output={output_gpkg}",
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
run(["v.out.ogr", "input=simplified", "output={output_gpkg}",
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
run(["v.out.ogr", "input=simplified", "output={output_gpkg}",
     "format=GPKG", "--overwrite", "--quiet"])
print("OK")
"""
        _run_grass(script, output_gpkg, label)

    else:
        log.error(f"Okänd GRASS_SIMPLIFY_METHOD: '{method}'. Välj 'douglas', 'chaiken' eller 'douglas+chaiken'.")
        return

    log.info(f"GRASS-förenkling klar! Output i: {output_path}")


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
    if backend in ("mapshaper", "auto"):
        log.info("── Mapshaper-konfiguration ───────────────────────────")
        log.info("  Tolerance-nivåer   : %s %%", SIMPLIFICATION_TOLERANCES)
        if SIMPLIFY_PROTECTED:
            log.info("  Skyddade klasser   : %s (förenklas ej)", sorted(SIMPLIFY_PROTECTED))
    log.info("══════════════════════════════════════════════════════════")

    # Rensa inaktuella gpkg-filer (metoder som tagits bort från config)
    from config import GENERALIZATION_METHODS
    all_methods = {"conn4", "conn8", "modal", "semantic"}
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
                    simplify_with_grass(
                        input_file, output_dir, variant_name,
                        method=GRASS_SIMPLIFY_METHOD,
                        chaiken_threshold=GRASS_CHAIKEN_THRESHOLD,
                        douglas_threshold=GRASS_DOUGLAS_THRESHOLD,
                        log=log,
                    )
                else:
                    simplify_with_mapshaper(input_file, output_dir, variant_name, tolerances, log)

            n_workers = min(len(gpkg_files), GRASS_PARALLEL_GPKG)
            if n_workers > 1:
                log.info(f"Kör {len(gpkg_files)} GPKG:er parallellt (max {n_workers} jobb)")
                with ThreadPoolExecutor(max_workers=n_workers) as ex:
                    list(ex.map(_process_gpkg, gpkg_files))
            else:
                for input_file in gpkg_files:
                    _process_gpkg(input_file)
    else:
        log.error("❌ Vektoriserad katalog saknas: %s", vectorized_dir)

    _elapsed = _time.time() - _t0
    log.info("\n══════════════════════════════════════════════════════════")
    log.info(f"Steg 8 KLART: {_elapsed:.0f}s ({_elapsed/60:.1f} min)")
    log.info(f"Output i {output_dir}")
    log.info("══════════════════════════════════════════════════════════")
