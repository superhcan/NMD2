"""
steg_10_overlay_external.py — Steg 10: Lägg extern vektorfil ovanpå steg 9 (eller 8).

Läser en extern vektor (GPKG/SHP) konfigurerad via OVERLAY_EXTERNAL_PATH i config.py
och integrerar polygonerna topologiskt korrekt via GRASS v.overlay i varje GPKG från
föregående steg (steg 9 om det körts, annars steg 8):

  1. Reprojektion — extern fil reprojecteras till mållagrets CRS vid behov.
  2. Klippning    — GRASS v.overlay op=not: bygger gemensamt arc-nät → inga sömglapp.
  3. Sammanslagning — klippt mark + externa polygoner med original precision → GPKG.

Vattenpolygonerna behåller exakt sin ursprungliga LM-precision (ingen förenkling).
Marksömmarna mot vatten är exakt delade kanter i GRASS topologi.

Klassvärdet på externa polygoner styrs av OVERLAY_EXTERNAL_CLASS i config.py:
  - Heltal : skriver detta värde i kolumnen "markslag" för alla externa polygoner.
  - None   : försöker läsa "markslag"-kolumnen från den externa filen; faller
             tillbaka på 0 om kolumnen saknas.

Kör: python3 src/steg_10_overlay_external.py
"""

import logging
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box as shapely_box, Polygon, MultiPolygon

from config import (OUT_BASE, OVERLAY_EXTERNAL_PATH, OVERLAY_EXTERNAL_CLASS,
                    OVERLAY_EXTERNAL_LAYER, GRASS_VECTOR_MEMORY, GRASS_OMP_THREADS,
                    VECTOR_MIN_AREA_M2, VECTOR_FILL_HOLE_M2)

LN = "markslag"

_GRASS_HEADER = """\
#!/usr/bin/env python3
import subprocess, sys

def run(cmd, desc=""):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.stderr.strip():
        print(r.stderr.strip(), file=sys.stderr)
    if r.returncode != 0:
        print(f"FAILED: {desc or cmd[0]}", file=sys.stderr)
        sys.exit(r.returncode)
    if desc:
        print(f"  OK: {desc}")
"""


def setup_logging(out_base):
    """Konfigurerar loggning för steg 10 med tre handlers."""
    log_dir = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    step_num = os.getenv("STEP_NUMBER", "10")
    step_name = os.getenv("STEP_NAME", "overlay_external").lower()
    step_suffix = f"steg_{step_num}_{step_name}_{ts}"

    fmt_detail = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fmt_summary = logging.Formatter(
        "%(asctime)s [%(levelname)-6s] %(message)s", datefmt="%H:%M:%S"
    )

    log = logging.getLogger("pipeline.overlay_external")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    log.handlers.clear()

    dbg = logging.FileHandler(str(log_dir / f"debug_{step_suffix}.log"))
    dbg.setLevel(logging.DEBUG)
    dbg.setFormatter(fmt_detail)
    log.addHandler(dbg)

    fh = logging.FileHandler(str(summary_dir / f"summary_{step_suffix}.log"))
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt_summary)
    log.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt_summary)
    log.addHandler(ch)

    return log


def load_external(path: Path, target_crs, log) -> gpd.GeoDataFrame:
    """Läser den externa vektorfilen, reprojecterar vid behov och sätter klassvärde.

    OVERLAY_EXTERNAL_LAYER: None = första lagret, str = ett lager, list = flera lager.
    Returnerar GeoDataFrame med kolumnerna 'geometry' och LN.
    """
    if OVERLAY_EXTERNAL_LAYER is None:
        layers = [None]
    elif isinstance(OVERLAY_EXTERNAL_LAYER, str):
        layers = [OVERLAY_EXTERNAL_LAYER]
    else:
        layers = list(OVERLAY_EXTERNAL_LAYER)

    gdfs = []
    for layer in layers:
        log.info("  Läser lager: %s från %s", layer or "(första)", path)
        read_kwargs = {"filename": str(path)}
        if layer is not None:
            read_kwargs["layer"] = layer
        gdf_part = gpd.read_file(**read_kwargs)
        log.info("    %d polygoner inlästa, CRS: %s", len(gdf_part), gdf_part.crs)
        gdfs.append(gdf_part)

    gdf = pd.concat(gdfs, ignore_index=True) if len(gdfs) > 1 else gdfs[0]
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry")
    log.info("  Totalt %d polygoner (lager: %s)", len(gdf),
             ", ".join(str(l) for l in layers))

    if gdf.crs is None:
        log.warning("  Extern fil saknar CRS — antar att den matchar mållagret")
    elif gdf.crs != target_crs:
        log.info("  Reprojecterar %s → %s", gdf.crs, target_crs)
        gdf = gdf.to_crs(target_crs)

    if OVERLAY_EXTERNAL_CLASS is not None:
        gdf[LN] = OVERLAY_EXTERNAL_CLASS
    elif LN not in gdf.columns:
        log.warning("  Kolumnen '%s' saknas i extern fil — fyller med 0", LN)
        gdf[LN] = 0

    return gdf[["geometry", LN]].copy()


def _run_grass_overlay(land_gpkg: Path, water_gpkg: Path, land_cut_gpkg: Path,
                       variant_name: str, min_area_m2: float, log) -> bool:
    """Kör GRASS v.overlay op=not + v.clean rmarea för topologiskt korrekt klippning
    och eliminering av små polygoner.

    land_gpkg      : input landskapspolygoner (steg 8/9)
    water_gpkg     : input externa vattenpolygoner (klippta till extent)
    land_cut_gpkg  : output — mark minus vatten, GRASS topologi garanterar inga sömglapp
    min_area_m2    : polygoner under denna area absorberas av största granne (0 = av)
    variant_name   : för loggning
    """
    rmarea_step = f"""
run(["v.clean", "input=land_cut", "output=land_clean",
     "tool=rmarea", "threshold={min_area_m2}",
     "--overwrite", "--quiet"], "v.clean rmarea")
run(["v.out.ogr", "input=land_clean", "output={land_cut_gpkg}",
     "output_layer=land_cut",
     "format=GPKG", "--overwrite"], "v.out.ogr")
""" if min_area_m2 > 0 else f"""
run(["v.out.ogr", "input=land_cut", "output={land_cut_gpkg}",
     "output_layer=land_cut",
     "format=GPKG", "--overwrite"], "v.out.ogr")
"""

    script = _GRASS_HEADER + f"""
run(["v.in.ogr", "input={land_gpkg}", "output=land_vect",
     "--overwrite", "--quiet"], "v.in.ogr land")
run(["v.in.ogr", "input={water_gpkg}", "output=water_vect",
     "--overwrite", "--quiet"], "v.in.ogr water")
run(["v.overlay", "ainput=land_vect", "binput=water_vect",
     "operator=not", "output=land_cut",
     "--overwrite", "--verbose"], "v.overlay not")
""" + rmarea_step

    tmpbase = None
    shm = Path("/dev/shm")
    if shm.exists():
        try:
            if shutil.disk_usage(str(shm)).free > 4 * 2**30:
                tmpbase = str(shm)
        except OSError:
            pass
    gtmp = Path(tempfile.mkdtemp(prefix=f"grass10_{variant_name}_", dir=tmpbase))

    try:
        script_path = gtmp / "run.py"
        script_path.write_text(script)
        genv = {
            **os.environ,
            "GRASS_VECTOR_MEMORY": str(GRASS_VECTOR_MEMORY),
            "OMP_NUM_THREADS":     str(GRASS_OMP_THREADS),
        }
        proc = subprocess.Popen(
            ["grass", "--tmp-project", "EPSG:3006", "--exec", "python3", str(script_path)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=genv,
        )
        for ln in proc.stdout:
            ln = ln.strip()
            if ln:
                log.info(f"  [grass] {ln}")
        proc.wait()
    finally:
        shutil.rmtree(gtmp, ignore_errors=True)

    if proc.returncode != 0:
        log.error(f"[{variant_name}] GRASS v.overlay returnerade kod {proc.returncode}")
        return False
    if not land_cut_gpkg.exists():
        log.error(f"[{variant_name}] v.out.ogr producerade ingen fil")
        return False
    return True


def _fill_small_holes(gdf: gpd.GeoDataFrame, min_area_m2: float, log) -> gpd.GeoDataFrame:
    """Fyller hål (interior rings) < min_area_m2 i vattenpolygonerna.

    Hål i vattenpolygoner motsvarar öar. Små öar under tröskeln absorberas
    direkt i vattengeometrin — utan att påverka topologin i overlay-steget.
    """
    if min_area_m2 <= 0:
        return gdf

    def _fill(geom):
        if geom.geom_type == "Polygon":
            kept = [ring for ring in geom.interiors if Polygon(ring).area >= min_area_m2]
            return Polygon(geom.exterior, kept)
        if geom.geom_type == "MultiPolygon":
            return MultiPolygon([_fill(p) for p in geom.geoms])
        return geom

    n_holes_before = sum(
        len(list(g.interiors)) if g.geom_type == "Polygon"
        else sum(len(list(p.interiors)) for p in g.geoms) if g.geom_type == "MultiPolygon"
        else 0
        for g in gdf.geometry
    )
    gdf = gdf.copy()
    gdf[gdf.geometry.name] = gdf.geometry.apply(_fill)
    n_holes_after = sum(
        len(list(g.interiors)) if g.geom_type == "Polygon"
        else sum(len(list(p.interiors)) for p in g.geoms) if g.geom_type == "MultiPolygon"
        else 0
        for g in gdf.geometry
    )
    filled = n_holes_before - n_holes_after
    if filled:
        log.info("    Fyllde %d hål < %.0f m² i externa vattenpolygoner", filled, min_area_m2)
    return gdf


def integrate_external(
        ext_path: Path, src_dir: Path, out_dir: Path, log):
    """Integrerar externa vattenpolygoner i varje GPKG i src_dir via GRASS v.overlay.

    För varje GPKG:
      1. Läs landskapspolygoner och klipp extern fil till extent.
      2. Spara dels landscape.gpkg, dels water_clip.gpkg till tmpdir.
      3. Kör GRASS: v.overlay op=not → land_cut.gpkg (topologiskt korrekt).
      4. Läs land_cut.gpkg, städa kolumnnamn (v.overlay prefixar med 'a_').
      5. Concat land_cut + water (original precision) → spara output GPKG.

    Returnerar antal producerade filer.
    """
    gpkgs = sorted(src_dir.glob("*.gpkg"))
    if not gpkgs:
        log.warning("  Inga GPKG-filer i %s", src_dir)
        return 0

    count = 0
    for gpkg in gpkgs:
        variant = gpkg.stem
        log.info("  Läser %s...", gpkg.name)
        landscape = gpd.read_file(str(gpkg))
        log.info("    %d landskapspolygoner (CRS: %s)", len(landscape), landscape.crs)

        ext_gdf = load_external(ext_path, landscape.crs, log)

        # Klipp externa polygoner till GPKG-lagrets extent
        landscape_bbox = shapely_box(*landscape.total_bounds)
        n_before = len(ext_gdf)
        ext_gdf = gpd.clip(ext_gdf, landscape_bbox)
        log.info("    %d externa polygoner inom extent (var %d totalt)", len(ext_gdf), n_before)
        ext_gdf = _fill_small_holes(ext_gdf, VECTOR_FILL_HOLE_M2, log)

        if ext_gdf.empty:
            log.info("    Inga externa polygoner i extent — kopierar GPKG oförändrad")
            import shutil as _sh
            out_gpkg = out_dir / gpkg.name
            _sh.copy2(str(gpkg), str(out_gpkg))
            count += 1
            continue

        # Spara temporära indatafiler för GRASS
        tmpdir = Path(tempfile.mkdtemp(prefix=f"steg10_{variant}_"))
        try:
            land_tmp   = tmpdir / "land.gpkg"
            water_tmp  = tmpdir / "water.gpkg"
            cut_tmp    = tmpdir / "land_cut.gpkg"

            # Säkerställ att klass-kolumnen heter LN ("markslag") i GRASS-indata
            land_out = landscape.copy()
            if LN not in land_out.columns and "DN" in land_out.columns:
                land_out = land_out.rename(columns={"DN": LN})
                log.debug("    Döpt om DN → %s i landscape inför GRASS", LN)
            land_out.to_file(str(land_tmp), driver="GPKG", layer="land")
            ext_gdf.to_file(str(water_tmp), driver="GPKG", layer="water")

            t_g = time.time()
            log.info("    Kör GRASS v.overlay op=not + v.clean rmarea (%.0f m²)...", VECTOR_MIN_AREA_M2)
            ok = _run_grass_overlay(land_tmp, water_tmp, cut_tmp, variant, VECTOR_MIN_AREA_M2, log)
            if not ok:
                log.error("    GRASS misslyckades — hoppar över %s", gpkg.name)
                continue
            log.info("    v.overlay klar  (%.1fs)", time.time() - t_g)

            # Läs GRASS-output och städa kolumnnamn
            # v.overlay op=not prefixar A-lagrets attribut med 'a_' och B med 'b_'
            land_cut = gpd.read_file(str(cut_tmp))
            # Byt a_markslag → markslag, ta bort a_cat, b_cat
            rename_map = {c: c[2:] for c in land_cut.columns if c.startswith("a_")}
            land_cut = land_cut.rename(columns=rename_map)
            drop_cols = [c for c in land_cut.columns
                         if c.startswith("b_") or c in ("cat", "cat_", "label", "DN")]
            land_cut = land_cut.drop(columns=drop_cols, errors="ignore")
            # Säkerställ att LN-kolumnen finns
            if LN not in land_cut.columns:
                log.warning("    Kolumnen '%s' saknas efter v.overlay — fyller med 0", LN)
                land_cut[LN] = 0
            log.info("    %d mark-polygoner efter klippning", len(land_cut))

            # Justera ext_gdf till samma kolumnschema som land_cut
            geom_col = land_cut.geometry.name
            e_out = ext_gdf.copy()
            if e_out.geometry.name != geom_col:
                e_out = e_out.rename_geometry(geom_col)
            for col in land_cut.columns:
                if col != geom_col and col not in e_out.columns:
                    e_out[col] = None
            e_out = e_out[land_cut.columns].copy()

            result = pd.concat([land_cut, e_out], ignore_index=True)
            result = gpd.GeoDataFrame(result, geometry=geom_col, crs=landscape.crs)

            # Validera geometrier (GEOS-säkerhetsnät)
            result[geom_col] = result.geometry.buffer(0)
            result = result[~result.geometry.is_empty & result.geometry.notna()]

            # Dela upp multipart till single-part
            n_pre = len(result)
            result = result.explode(index_parts=False).reset_index(drop=True)
            if len(result) > n_pre:
                log.info("    explode: %d → %d features", n_pre, len(result))

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        out_gpkg = out_dir / gpkg.name
        if out_gpkg.exists():
            out_gpkg.unlink()
        log.info("    Skriver %s...", out_gpkg.name)
        result.to_file(str(out_gpkg), driver="GPKG", layer=variant)

        sz = out_gpkg.stat().st_size / 1e6
        log.info("  ✓ %s — %d polygoner  %.1f MB", out_gpkg.name, len(result), sz)
        count += 1

    return count


if __name__ == "__main__":
    log = setup_logging(OUT_BASE)
    t0 = time.time()

    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 10: Overlay extern vektorfil")

    if not OVERLAY_EXTERNAL_PATH:
        log.error("OVERLAY_EXTERNAL_PATH är inte satt i config.py — avslutar")
        raise SystemExit(1)

    ext_path = Path(OVERLAY_EXTERNAL_PATH)
    if not ext_path.exists():
        log.error("Extern fil saknas: %s", ext_path)
        raise SystemExit(1)

    # Välj källkatalog: steg 9 om det körts, annars steg 8
    src_steg9 = OUT_BASE / "steg_9_overlay_buildings"
    src_steg8 = OUT_BASE / "steg_8_simplify"
    if src_steg9.exists() and any(src_steg9.glob("*.gpkg")):
        src_dir = src_steg9
        src_label = "steg_9_overlay_buildings"
    elif src_steg8.exists() and any(src_steg8.glob("*.gpkg")):
        src_dir = src_steg8
        src_label = "steg_8_simplify"
    else:
        log.error("Varken steg_9_overlay_buildings/ eller steg_8_simplify/ finns med GPKG-filer")
        raise SystemExit(1)

    out_dir = OUT_BASE / "steg_10_overlay_external"
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Extern fil   : %s", ext_path)
    layers_label = OVERLAY_EXTERNAL_LAYER or "(första lagret)"
    if isinstance(layers_label, list):
        layers_label = ", ".join(layers_label)
    log.info("Lager        : %s", layers_label)
    log.info("Källkatalog  : %s", src_dir)
    log.info("Utmapp       : %s", out_dir)
    if OVERLAY_EXTERNAL_CLASS is not None:
        log.info("Klass        : %d (OVERLAY_EXTERNAL_CLASS)", OVERLAY_EXTERNAL_CLASS)
    else:
        log.info("Klass        : läses från extern fils 'markslag'-kolumn (OVERLAY_EXTERNAL_CLASS=None)")
    log.info("══════════════════════════════════════════════════════════")

    n = integrate_external(ext_path, src_dir, out_dir, log)

    elapsed = time.time() - t0
    log.info("")
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 10 klart — %d filer skapade från %s  %.1f min (%.0fs)",
             n, src_label, elapsed / 60, elapsed)
    log.info("══════════════════════════════════════════════════════════")
