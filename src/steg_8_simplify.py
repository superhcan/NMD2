"""
steg_8_simplify.py — Steg 8: Topologisk vektorförenkling med GRASS v.generalize.

Delar upp körningen i STRIP_N Y-band. Varje band körs parallellt (max STRIP_WORKERS
stycken) som en oberoende GRASS-session. Band-resultaten sparas i:

  steg_8_simplify/{variant}/strip_000.gpkg
  steg_8_simplify/{variant}/strip_001.gpkg
  ...

Steg 11 (steg_11_merge.py) slår sedan ihop banden per variant till en slutlig GPKG.

Källa väljs automatiskt:
  1. steg_6_generalize/ (eller steg_6b_expand_water/) finns
     -> rasterbaserad körning (r.external -> r.patch -> r.to.vect -> v.generalize)
  2. FULLSWEDEN_RAW_GPKG finns och steg 6 saknas
     -> direkt GPKG-körning (v.in.ogr -> v.generalize per strip)
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from config import (
    OUT_BASE, SRC, TILE_SIZE,
    MORPH_ONLY, MORPH_SMOOTH_METHOD,
    GRASS_SIMPLIFY_METHOD,
    GRASS_CHAIKEN_THRESHOLD, GRASS_DOUGLAS_THRESHOLD,
    GRASS_SLIDING_ITERATIONS, GRASS_SLIDING_THRESHOLD, GRASS_SLIDING_SLIDE,
    GRASS_VECTOR_MEMORY, GRASS_OMP_THREADS,
    STRIP_N, STRIP_OVERLAP_M, STRIP_WORKERS, STRIP_ONLY,
    FULLSWEDEN_RAW_GPKG,
)
from strips import compute_strips, strip_name, src_extent


# ==============================================================================
# Logging
# ==============================================================================

def setup_logging(out_base):
    log_dir     = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    step_num  = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    suffix    = f"steg_{step_num}_{step_name}_{ts}" if (step_num and step_name) else ts
    fmt_d = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fmt_s = logging.Formatter(
        "%(asctime)s [%(levelname)-6s] %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("pipeline.simplify")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    log.handlers.clear()
    h_d = logging.FileHandler(log_dir / f"debug_{suffix}.log")
    h_d.setLevel(logging.DEBUG); h_d.setFormatter(fmt_d); log.addHandler(h_d)
    h_s = logging.FileHandler(summary_dir / f"summary_{suffix}.log")
    h_s.setLevel(logging.INFO);  h_s.setFormatter(fmt_s); log.addHandler(h_s)
    h_c = logging.StreamHandler()
    h_c.setLevel(logging.INFO);  h_c.setFormatter(fmt_s); log.addHandler(h_c)
    return log


# ==============================================================================
# GRASS script-mall
# ==============================================================================

_GRASS_HEADER = """\
#!/usr/bin/env python3
import subprocess, sys

def run(cmd, desc=""):
    r = subprocess.run(cmd, capture_output=True, text=True)
    _ignore = "no valid pixels found in sampling"
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.stderr.strip():
        filtered = "\\n".join(l for l in r.stderr.splitlines() if _ignore not in l)
        if filtered.strip():
            print(filtered.strip(), file=sys.stderr)
    if r.returncode != 0:
        print(f"FAILED: {desc or cmd[0]}", file=sys.stderr)
        sys.exit(r.returncode)
    if desc:
        print(f"  OK: {desc}")
"""


# ==============================================================================
# Hjälpfunktioner
# ==============================================================================

def _detect_layer_info(gpkg: Path) -> tuple:
    """Returnera (layer_name, geom_col) för första lagret i en GPKG."""
    r = subprocess.run(
        ["ogrinfo", "-al", "-so", str(gpkg)], capture_output=True, text=True)
    layer_name = None
    geom_col   = "geom"
    for line in r.stdout.splitlines():
        ls = line.strip()
        if ls.lower().startswith("layer name:"):
            layer_name = ls.split(":", 1)[1].strip()
        elif ls.lower().startswith("geometry column"):
            pts = ls.split("=", 1)
            if len(pts) == 2:
                geom_col = pts[1].strip()
    if not layer_name:
        r2 = subprocess.run(
            ["ogrinfo", "-q", str(gpkg)], capture_output=True, text=True)
        for line in r2.stdout.splitlines():
            parts = line.strip().split(":", 1)
            if len(parts) == 2 and parts[0].strip().isdigit():
                layer_name = parts[1].strip().split(" ")[0]
                break
    return layer_name, geom_col


def _build_gen_cmds(in_map, out_map, method, dp_thresh, ch_thresh):
    """Returnerar lista med GRASS-skriptrader för v.generalize."""
    if method == "douglas":
        return [
            f'run(["v.generalize", "input={in_map}", "output={out_map}", '
            f'"method=douglas", "threshold={dp_thresh:.2f}", '
            f'"--overwrite", "--quiet"], "v.generalize (douglas)")',
        ]
    if method == "chaiken":
        return [
            f'run(["v.generalize", "input={in_map}", "output={out_map}", '
            f'"method=chaiken", "threshold={ch_thresh:.2f}", '
            f'"--overwrite", "--quiet"], "v.generalize (chaiken)")',
        ]
    if method == "douglas+chaiken":
        return [
            f'run(["v.generalize", "input={in_map}", "output=after_dp", '
            f'"method=douglas", "threshold={dp_thresh:.2f}", '
            f'"--overwrite", "--quiet"], "v.generalize (douglas)")',
            f'run(["v.generalize", "input=after_dp", "output={out_map}", '
            f'"method=chaiken", "threshold={ch_thresh:.2f}", '
            f'"--overwrite", "--quiet"], "v.generalize (chaiken)")',
        ]
    if method == "chaiken+douglas":
        return [
            f'run(["v.generalize", "input={in_map}", "output=after_chaiken", '
            f'"method=chaiken", "threshold={ch_thresh:.2f}", '
            f'"--overwrite", "--quiet"], "v.generalize (chaiken)")',
            f'run(["v.generalize", "input=after_chaiken", "output={out_map}", '
            f'"method=douglas", "threshold={dp_thresh:.2f}", '
            f'"--overwrite", "--quiet"], "v.generalize (douglas)")',
        ]
    if method == "sliding_avg":
        return [
            f'run(["v.generalize", "input={in_map}", "output={out_map}", '
            f'"method=sliding_averaging", "threshold={GRASS_SLIDING_THRESHOLD:.2f}", '
            f'"iterations={GRASS_SLIDING_ITERATIONS}", "slide={GRASS_SLIDING_SLIDE:.2f}", '
            f'"--overwrite", "--quiet"], "v.generalize (sliding_avg)")',
        ]
    if method == "douglas+sliding_avg":
        return [
            f'run(["v.generalize", "input={in_map}", "output=after_dp", '
            f'"method=douglas", "threshold={dp_thresh:.2f}", '
            f'"--overwrite", "--quiet"], "v.generalize (douglas)")',
            f'run(["v.generalize", "input=after_dp", "output={out_map}", '
            f'"method=sliding_averaging", "threshold={GRASS_SLIDING_THRESHOLD:.2f}", '
            f'"iterations={GRASS_SLIDING_ITERATIONS}", "slide={GRASS_SLIDING_SLIDE:.2f}", '
            f'"--overwrite", "--quiet"], "v.generalize (sliding_avg)")',
        ]
    raise ValueError(f"Okänd GRASS-metod: {method}")


def _run_grass(script_text, label, strip_mem, omp, log):
    """Kör ett GRASS --tmp-project-skript. Returnerar True om OK."""
    # Välj tmpbase för GRASS-projektmappen (skript + GRASS LOCATION):
    # Använd /dev/shm om > 4 GB fri, annars fallback till OUT_BASE/grass_tmp
    # där OUT_BASE-disken har gott om utrymme.
    tmpbase = None
    shm = Path("/dev/shm")
    if shm.exists():
        try:
            if shutil.disk_usage(str(shm)).free > 4 * 2**30:
                tmpbase = str(shm)
        except OSError:
            pass
    if tmpbase is None:
        fallback = OUT_BASE / "grass_tmp"
        fallback.mkdir(parents=True, exist_ok=True)
        tmpbase = str(fallback)

    # GRASS_TMPDIR styr var GRASS skapar sin interna sessions-tempkatalog
    # (grass8-hcn-PID). Pekar vi den till OUT_BASE-disken undviker vi att
    # fylla /tmp (tmpfs, 28 GB) vid parallella körningar.
    grass_tmp_dir = OUT_BASE / "grass_tmp"
    grass_tmp_dir.mkdir(parents=True, exist_ok=True)

    gtmp = Path(tempfile.mkdtemp(prefix=f"grass_{label}_", dir=tmpbase))
    try:
        script = gtmp / "run.py"
        script.write_text(script_text)
        genv = {**os.environ,
                "GRASS_VECTOR_MEMORY": str(strip_mem),
                "OMP_NUM_THREADS":     str(omp),
                "GRASS_TMPDIR":        str(grass_tmp_dir)}
        proc = subprocess.Popen(
            ["grass", "--tmp-project", "EPSG:3006", "--exec", "python3", str(script)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=genv)
        for ln in proc.stdout:
            ln = ln.strip()
            if ln:
                log.info(f"  [grass {label}] {ln}")
        proc.wait()
    finally:
        shutil.rmtree(gtmp, ignore_errors=True)
    if proc.returncode != 0:
        log.error(f"  [{label}] GRASS returnerade kod {proc.returncode}")
        return False
    return True


def _centroid_filter(in_gpkg, out_gpkg, layer, geom_col,
                     x_min, x_max, y_own_min, y_own_max, log):
    """Centroid-filter: behåll polygoner vars centroid är inuti det ägda Y-bandet."""
    own_wkt = (
        f"POLYGON(("
        f"{x_min:.2f} {y_own_min:.2f},"
        f"{x_max:.2f} {y_own_min:.2f},"
        f"{x_max:.2f} {y_own_max:.2f},"
        f"{x_min:.2f} {y_own_max:.2f},"
        f"{x_min:.2f} {y_own_min:.2f}"
        f"))"
    )
    sql = (
        f'SELECT * FROM "{layer}" '
        f'WHERE ST_Intersects(ST_Centroid("{geom_col}"), '
        f"ST_GeomFromText('{own_wkt}'))"
    )
    r = subprocess.run([
        "ogr2ogr", "-f", "GPKG", "-dialect", "SQLite", "-sql", sql,
        str(out_gpkg), str(in_gpkg),
    ], capture_output=True, text=True)
    if r.returncode != 0 or not out_gpkg.exists():
        log.error(f"  centroid-filter misslyckades: {r.stderr[:300]}")
        return False
    return True


def _tile_row(tif):
    """Extraherar radnummer ur filnamnet, t.ex. 'conn4_r043_c016.tif' -> 43."""
    m = re.search(r'_r(\d+)_', tif.name)
    return int(m.group(1)) if m else None


# ==============================================================================
# Per-strip: rasterbaserat flöde (r.external -> r.patch -> r.to.vect -> v.generalize)
# ==============================================================================

def process_strip_from_raster(strip, tif_files, variant_name, variant_out,
                               strip_mem, omp_per_job, log):
    """
    Kör ett band i rasterbaserat läge.

    strip       -- band-dict från compute_strips()
    tif_files   -- alla TIF-filer för den aktuella varianten (filtreras hit)
    variant_out -- katalog steg_8_simplify/{variant}/
    """
    si        = strip["idx"]
    y_ov_min  = strip["y_ov_min"]
    y_ov_max  = strip["y_ov_max"]
    y_own_min = strip["y_own_min"]
    y_own_max = strip["y_own_max"]
    sname     = strip_name(si)

    strip_out  = variant_out / sname
    strip_out.mkdir(parents=True, exist_ok=True)
    owned_gpkg = variant_out / f"{sname}.gpkg"

    if owned_gpkg.exists():
        log.info(f"  [{variant_name}] {sname}: checkpoint finns -- hoppar")
        return owned_gpkg

    # Beräkna tile Y-extent från SRC-geotransform
    r_gi = subprocess.run(
        ["gdalinfo", "-json", str(SRC)],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    gt       = json.loads(r_gi.stdout)["geoTransform"]
    y_origin = gt[3]
    px_h     = abs(gt[5])
    px_w     = gt[1]
    x_origin = gt[0]

    # Filtrera tiles vars Y-extent överlappar med överlappszonen
    band_tifs = []
    for tif in tif_files:
        row = _tile_row(tif)
        if row is None:
            continue
        t_top = y_origin - row * TILE_SIZE * px_h
        t_bot = y_origin - (row + 1) * TILE_SIZE * px_h
        if t_top > y_ov_min and t_bot < y_ov_max:
            band_tifs.append(tif)

    if not band_tifs:
        log.warning(f"  [{variant_name}] {sname}: inga tiles i "
                    f"Y {y_ov_min/1000:.0f}--{y_ov_max/1000:.0f} km")
        return None

    # X-extent täcker alla tile-kolumner
    col_nums = []
    for tif in band_tifs:
        m = re.search(r'_c(\d+)', tif.name)
        if m:
            col_nums.append(int(m.group(1)))
    if col_nums:
        x_min = x_origin + min(col_nums) * TILE_SIZE * px_w
        x_max = x_origin + (max(col_nums) + 1) * TILE_SIZE * px_w
    else:
        x_min, _, x_max, _ = src_extent()

    simplified_gpkg = strip_out / "simplified.gpkg"
    raw_vect_gpkg   = strip_out / "raw_vect.gpkg"
    have_checkpoint = raw_vect_gpkg.exists()

    lines = [_GRASS_HEADER]

    if have_checkpoint:
        log.info(f"  [{variant_name}] {sname}: raw_vect checkpoint -- hoppar r.to.vect")
        lines.append(
            f'run(["v.in.ogr", "input={raw_vect_gpkg}", "output=raw_vect", '
            f'"--overwrite", "--quiet"], "v.in.ogr checkpoint")'
        )
    else:
        rmap_names = [f"tile_{i:05d}" for i in range(len(band_tifs))]
        for i, tif in enumerate(sorted(band_tifs)):
            lines.append(
                f'run(["r.external", "input={tif}", "output={rmap_names[i]}", '
                f'"--overwrite", "--quiet"], "r.external {i}")'
            )
        maps_csv = ",".join(rmap_names)
        lines.append(
            f'run(["g.region", "raster={maps_csv}", "--verbose"], "g.region")'
        )
        if len(rmap_names) == 1:
            lines.append(
                f'run(["g.rename", "raster={rmap_names[0]},mosaic", "--overwrite"], "r.patch (single)")'
            )
        else:
            lines.append(
                f'run(["r.patch", "input={maps_csv}", "output=mosaic", '
                f'"--overwrite", "--verbose"], "r.patch")'
            )
        lines.append(
            'run(["r.to.vect", "input=mosaic", "output=raw_vect", '
            '"type=area", "column=DN", "--overwrite", "--verbose"], "r.to.vect")'
        )
        lines.append(
            f'run(["v.out.ogr", "input=raw_vect", "output={raw_vect_gpkg}", '
            f'"output_layer=raw_vect", "format=GPKG", "--overwrite", "--quiet"], "checkpoint raw_vect")'
        )

    lines.extend(_build_gen_cmds(
        "raw_vect", "simplified",
        GRASS_SIMPLIFY_METHOD, GRASS_DOUGLAS_THRESHOLD, GRASS_CHAIKEN_THRESHOLD,
    ))
    lines.append(
        f'run(["v.out.ogr", "input=simplified", "output={simplified_gpkg}", '
        f'"output_layer={variant_name}", "format=GPKG", "--overwrite", "--quiet"], "v.out.ogr")'
    )

    ok = _run_grass("\n".join(lines), f"{variant_name}-{sname}", strip_mem, omp_per_job, log)
    if not ok or not simplified_gpkg.exists():
        log.error(f"  [{variant_name}] {sname}: GRASS producerade ingen fil")
        return None

    log.info(f"  [{variant_name}] {sname}: GRASS klar -> "
             f"{simplified_gpkg.stat().st_size/1024**2:.1f} MB")

    simp_layer, simp_geom = _detect_layer_info(simplified_gpkg)
    if not simp_layer:
        log.error(f"  [{variant_name}] {sname}: kan inte detektera lager i simplified.gpkg")
        simplified_gpkg.unlink(missing_ok=True)
        return None

    ok_cf = _centroid_filter(
        simplified_gpkg, owned_gpkg, simp_layer, simp_geom,
        x_min, x_max, y_own_min, y_own_max, log,
    )
    simplified_gpkg.unlink(missing_ok=True)
    if not ok_cf:
        return None

    log.info(f"  [{variant_name}] {sname}: done {owned_gpkg.stat().st_size/1024**2:.1f} MB")
    return owned_gpkg


# ==============================================================================
# Per-strip: GPKG-baserat flöde (v.in.ogr -> v.generalize)
# ==============================================================================

def process_strip_from_gpkg(strip, input_gpkg, input_layer, input_geom_col,
                             x_min, x_max, variant_out, strip_mem, omp_per_job, log):
    """
    Kör ett band i GPKG-baserat läge (FULLSWEDEN_RAW_GPKG-stigen).

    Extraherar överlappszonen med ogr2ogr -spat, kör GRASS v.generalize,
    filtrerar sedan med centroid-ägarskap till det ägda Y-bandet.
    """
    si        = strip["idx"]
    y_ov_min  = strip["y_ov_min"]
    y_ov_max  = strip["y_ov_max"]
    y_own_min = strip["y_own_min"]
    y_own_max = strip["y_own_max"]
    sname     = strip_name(si)

    strip_out  = variant_out / sname
    strip_out.mkdir(parents=True, exist_ok=True)
    owned_gpkg = variant_out / f"{sname}.gpkg"

    if owned_gpkg.exists():
        log.info(f"  [{sname}]: checkpoint finns -- hoppar")
        return owned_gpkg

    # A) Extrahera överlappszonen (geometrier klipps EJ -- GRASS ser hela polygoner)
    extract_gpkg = strip_out / "extract.gpkg"
    if not extract_gpkg.exists():
        r_ex = subprocess.run([
            "ogr2ogr", "-f", "GPKG",
            "-spat", f"{x_min:.2f}", f"{y_ov_min:.2f}", f"{x_max:.2f}", f"{y_ov_max:.2f}",
            str(extract_gpkg), str(input_gpkg),
        ], capture_output=True, text=True)
        if r_ex.returncode != 0 or not extract_gpkg.exists():
            log.error(f"  [{sname}]: ogr2ogr extract misslyckades: {r_ex.stderr[:300]}")
            return None

    ex_mb = extract_gpkg.stat().st_size / 1024**2
    log.info(
        f"  [{sname}]: {ex_mb:.1f} MB extraherat "
        f"(Y {y_ov_min/1000:.0f}--{y_ov_max/1000:.0f} km inkl. överlapp)"
    )

    simplified_gpkg = strip_out / "simplified.gpkg"
    lines = [_GRASS_HEADER]
    lines.append(
        f'run(["v.in.ogr", "input={extract_gpkg}", "layer={input_layer}", '
        f'"output={input_layer}", "--overwrite", "--quiet"], "v.in.ogr")'
    )
    lines.extend(_build_gen_cmds(
        input_layer, "simplified",
        GRASS_SIMPLIFY_METHOD, GRASS_DOUGLAS_THRESHOLD, GRASS_CHAIKEN_THRESHOLD,
    ))
    lines.append(
        f'run(["v.out.ogr", "input=simplified", "output={simplified_gpkg}", '
        f'"output_layer={input_layer}", "format=GPKG", "--overwrite", "--quiet"], "v.out.ogr")'
    )

    ok = _run_grass("\n".join(lines), sname, strip_mem, omp_per_job, log)
    extract_gpkg.unlink(missing_ok=True)

    if not ok or not simplified_gpkg.exists():
        log.error(f"  [{sname}]: GRASS producerade ingen fil")
        return None

    log.info(f"  [{sname}]: GRASS klar -> {simplified_gpkg.stat().st_size/1024**2:.1f} MB")

    simp_layer, simp_geom = _detect_layer_info(simplified_gpkg)
    if not simp_layer:
        log.error(f"  [{sname}]: kan inte detektera lager i simplified.gpkg")
        simplified_gpkg.unlink(missing_ok=True)
        return None

    ok_cf = _centroid_filter(
        simplified_gpkg, owned_gpkg, simp_layer, simp_geom,
        x_min, x_max, y_own_min, y_own_max, log,
    )
    simplified_gpkg.unlink(missing_ok=True)
    if not ok_cf:
        return None

    log.info(f"  [{sname}]: done {owned_gpkg.stat().st_size/1024**2:.1f} MB")
    return owned_gpkg


# ==============================================================================
# Orkestrerare: kör alla strip parallellt för en variant
# ==============================================================================

def run_variant_from_raster(variant_name, tif_files, output_dir, log):
    """Kör steg 8 per strip för en rastervariant (r.external -> v.generalize)."""
    strips      = compute_strips()
    if STRIP_ONLY:
        strips = [s for s in strips if s["idx"] in STRIP_ONLY]
        log.info(f"[{variant_name}] STRIP_ONLY={STRIP_ONLY} → {len(strips)} band filtrerat")
    variant_out = output_dir / variant_name
    variant_out.mkdir(parents=True, exist_ok=True)

    strip_mem   = max(4000, GRASS_VECTOR_MEMORY // max(1, STRIP_WORKERS))
    omp_per_job = max(1, GRASS_OMP_THREADS // max(1, STRIP_WORKERS))

    log.info(f"[{variant_name}] {len(strips)} band, {STRIP_WORKERS} parallellt, "
             f"{strip_mem} MB/jobb, {omp_per_job} OMP-trad/jobb")

    with ThreadPoolExecutor(max_workers=STRIP_WORKERS) as ex:
        futures = {
            ex.submit(
                process_strip_from_raster,
                s, tif_files, variant_name, variant_out,
                strip_mem, omp_per_job, log,
            ): s["idx"]
            for s in strips
        }
        ok = sum(1 for fut in as_completed(futures) if fut.result() is not None)

    log.info(f"[{variant_name}] {ok}/{len(strips)} band klara")
    return ok == len(strips)


def run_from_gpkg(input_gpkg, output_dir, log):
    """Kör steg 8 per strip för en hel-Sverige-GPKG (FULLSWEDEN_RAW_GPKG-stigen)."""
    input_gpkg = Path(input_gpkg)
    if not input_gpkg.exists():
        log.error(f"FULLSWEDEN_RAW_GPKG saknas: {input_gpkg}")
        sys.exit(1)

    input_layer, input_geom_col = _detect_layer_info(input_gpkg)
    if not input_layer:
        log.error(f"Kunde inte detektera lagernamn i {input_gpkg.name}")
        sys.exit(1)

    log.info(f"GPKG-källa: {input_gpkg.name}  lager='{input_layer}', geomkol='{input_geom_col}'")

    variant_name = re.sub(r'_raw_vect$', '', input_gpkg.stem)
    variant_out  = output_dir / variant_name
    variant_out.mkdir(parents=True, exist_ok=True)

    x_min, _, x_max, _ = src_extent()
    strips      = compute_strips()
    if STRIP_ONLY:
        strips = [s for s in strips if s["idx"] in STRIP_ONLY]
        log.info(f"[{variant_name}] STRIP_ONLY={STRIP_ONLY} → {len(strips)} band filtrerat")
    strip_mem   = max(4000, GRASS_VECTOR_MEMORY // max(1, STRIP_WORKERS))
    omp_per_job = max(1, GRASS_OMP_THREADS // max(1, STRIP_WORKERS))

    log.info(f"[{variant_name}] {len(strips)} band, {STRIP_WORKERS} parallellt, "
             f"{strip_mem} MB/jobb, {omp_per_job} OMP-trad/jobb")

    with ThreadPoolExecutor(max_workers=STRIP_WORKERS) as ex:
        futures = {
            ex.submit(
                process_strip_from_gpkg,
                s, input_gpkg, input_layer, input_geom_col,
                x_min, x_max, variant_out, strip_mem, omp_per_job, log,
            ): s["idx"]
            for s in strips
        }
        ok = sum(1 for fut in as_completed(futures) if fut.result() is not None)

    log.info(f"[{variant_name}] {ok}/{len(strips)} band klara")
    return ok == len(strips)


# ==============================================================================
# Main
# ==============================================================================

if __name__ == "__main__":
    t0  = time.time()
    log = setup_logging(OUT_BASE)

    output_dir = OUT_BASE / "steg_8_simplify"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Välj källa
    _gen6b = OUT_BASE / "steg_6b_expand_water"
    _gen6  = OUT_BASE / "steg_6_generalize"
    if _gen6b.exists() and any(d.is_dir() for d in _gen6b.iterdir()):
        gen6_dir = _gen6b
        log.info("Källa: steg_6b_expand_water/ (expand-water kördes)")
    elif _gen6.exists():
        gen6_dir = _gen6
        log.info("Källa: steg_6_generalize/")
    else:
        gen6_dir = None

    method = GRASS_SIMPLIFY_METHOD
    dp     = int(round(GRASS_DOUGLAS_THRESHOLD))
    ch     = int(round(GRASS_CHAIKEN_THRESHOLD))
    if method == "douglas":
        sfx = f"dp{dp}"
    elif method == "chaiken":
        sfx = f"chaiken_t{ch}"
    elif method == "sliding_avg":
        sfx = f"sliding_i{GRASS_SLIDING_ITERATIONS}_s{int(GRASS_SLIDING_SLIDE*10)}"
    elif method == "douglas+sliding_avg":
        sfx = f"dp{dp}_sliding_i{GRASS_SLIDING_ITERATIONS}_s{int(GRASS_SLIDING_SLIDE*10)}"
    else:
        sfx = f"dp{dp}_chaiken_t{ch}"

    _ext = src_extent()
    _y_range_km = (_ext[3] - _ext[1]) / 1000
    _band_km    = _y_range_km / STRIP_N

    log.info("=" * 58)
    log.info("Steg 8: Vektorförenkling (GRASS v.generalize, strip-parallell)")
    log.info("Utmapp  : %s", output_dir)
    log.info("Metod   : %s  dp=%.1f m  ch=%.1f m", method, GRASS_DOUGLAS_THRESHOLD, GRASS_CHAIKEN_THRESHOLD)
    log.info("Band    : %d st a %.0f km, +/-%.0f km overlapp",
             STRIP_N, _band_km, STRIP_OVERLAP_M / 1000)
    log.info("Workers : %d", STRIP_WORKERS)
    log.info("=" * 58)

    if gen6_dir is not None:
        # Rasterbaserat läge: en variant per undermapp i steg_6
        subdirs = sorted(d for d in gen6_dir.iterdir() if d.is_dir())
        if MORPH_ONLY and MORPH_SMOOTH_METHOD != "none":
            subdirs = [d for d in subdirs if "_morph_" in d.name]

        if not subdirs:
            log.error("Inga undermappar i %s", gen6_dir)
            sys.exit(1)

        log.info("Rasterläge: %d variant(er) i %s", len(subdirs), gen6_dir.name)
        for subdir in subdirs:
            tifs = sorted(subdir.glob("*.tif"))
            if not tifs:
                log.warning("  %s: inga TIF-filer, hoppar", subdir.name)
                continue
            log.info("")
            log.info("VARIANT: %s  (%d tiles)", subdir.name, len(tifs))
            run_variant_from_raster(subdir.name, tifs, output_dir, log)

    elif FULLSWEDEN_RAW_GPKG and Path(FULLSWEDEN_RAW_GPKG).exists():
        # GPKG-baserat läge: direktingång från hel-Sverige-GPKG
        log.info("GPKG-läge: %s", FULLSWEDEN_RAW_GPKG)
        run_from_gpkg(Path(FULLSWEDEN_RAW_GPKG), output_dir, log)

    else:
        log.error(
            "Varken steg_6-katalog eller FULLSWEDEN_RAW_GPKG hittades.\n"
            "  steg_6_generalize/  : %s\n"
            "  FULLSWEDEN_RAW_GPKG : %s",
            _gen6, FULLSWEDEN_RAW_GPKG,
        )
        sys.exit(1)

    elapsed = time.time() - t0
    log.info("")
    log.info("=" * 58)
    log.info("Steg 8 klart: %.0f s (%.1f min)", elapsed, elapsed / 60)
    log.info("Output i %s", output_dir)
    log.info("=" * 58)
