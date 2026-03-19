#!/usr/bin/env python3
"""
steg_10_merge_batches.py — Steg 10: Sammanslagning av alla batch-resultat.

Körs EFTER att alla batchar (batch_000 ... batch_NNN) är klara.
Skriver till OUT_BASE_ROOT/steg10_merged/ (ej inuti någon batch-subdirektory).

Strategi: Arbetar på RASTRET (steg6), inte vektorn.
  Steg 7 (polygonize) och steg 8 (simplify) görs PER BATCH → polygoner
  som korsar batch-gränsen förenklas separat på varje sida → seam kvarstår
  oavsett hur vi försöker merga vektorerna i efterhand.

  Rätt lösning: samla ALLA steg6-raster-tiles från alla batchar, bygg en
  enda VRT, kör gdal_polygonize ETT GÅNG på hela rastret, kör Mapshaper
  simplify. Inga batch-gränser existerar längre.

För varje variant (conn4/conn8/modal + MMU/kernel):
  1. Samla alla steg6-tiles från batch_*/steg6_generalized_<metod>/
  2. Bygg en gemensam VRT
  3. Kör gdal_polygonize → sammanslagen GPKG (inga seams)
  4. Kör Mapshaper simplify per toleransnivå → slutlig GPKG (EPSG:3006)

Kör: python3 src/steg_10_merge_batches.py
     (batch-index spelar ingen roll — läser från alla batch_* kataloger)
"""

import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from config import OUT_BASE_ROOT, PARENT_TILES, SIMPLIFICATION_TOLERANCES, SIMPLIFY_PROTECTED, MAPSHAPER_MAX_HEAP_MB

log  = logging.getLogger("pipeline.merge")
info = logging.getLogger("pipeline.merge")


def _setup_logging(out_dir: Path):
    step_num  = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    log_dir     = out_dir / "log"
    summary_dir = out_dir / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)

    suffix = f"steg_{step_num}_{step_name}_{ts}" if (step_num and step_name) else ts

    fmt_d = logging.Formatter("%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
                               datefmt="%Y-%m-%d %H:%M:%S")
    fmt_s = logging.Formatter("%(asctime)s [%(levelname)-6s] %(message)s",
                               datefmt="%H:%M:%S")

    logger = logging.getLogger("pipeline.merge")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.handlers.clear()

    fh = logging.FileHandler(log_dir / f"debug_{suffix}.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt_d)
    logger.addHandler(fh)

    sh = logging.FileHandler(summary_dir / f"summary_{suffix}.log")
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt_s)
    logger.addHandler(sh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt_s)
    logger.addHandler(ch)

    return logger


def find_batch_dirs() -> list[Path]:
    """Returnerar alla batch_NNN-kataloger i OUT_BASE_ROOT, sorterade."""
    return sorted(d for d in OUT_BASE_ROOT.iterdir()
                  if d.is_dir() and d.name.startswith("batch_"))


def collect_raster_variants(batch_dirs: list[Path]) -> dict[str, list[Path]]:
    """Samlar alla steg6-raster-tiles från alla batchar.

    Returnerar dict: variant_key → sorterad lista av .tif-filer.
    variant_key exempel: "conn4_mmu050", "conn8_mmu008", "modal_k15"

    Söker i batch_*/steg6_generalized_<metod>/ efter *.tif.
    Tile-filnamnen är unika (innehåller r/c-koordinater) → inga kollisioner.
    """
    import re
    variants: dict[str, list[Path]] = {}
    for bd in batch_dirs:
        for s6_dir in sorted(bd.glob("steg6_generalized_*")):
            if not s6_dir.is_dir():
                continue
            method = s6_dir.name.replace("steg6_generalized_", "")  # conn4 / conn8 / modal
            for tif in sorted(s6_dir.glob("*.tif")):
                # Extrahera mmu/kernel-suffix: conn4_mmu050 eller modal_k15
                m = re.search(r'_((?:conn\d+|modal|semantic)_(?:mmu\d+|k\d+))\.tif$', tif.name)
                if m:
                    key = m.group(1)
                else:
                    # Fallback: method + filstam utan prefix
                    key = method
                variants.setdefault(key, []).append(tif)
    return variants


def polygonize_and_simplify(variant_key: str, tif_files: list[Path], out_dir: Path) -> bool:
    """
    1. Bygg en enda VRT av alla steg6-raster-tiles (från alla batchar).
    2. Kör gdal_polygonize.py på hela VRT:en → GPKG utan batch-seams.
    3. Kör Mapshaper simplify per toleransnivå → slutliga GPKG:er.
    """
    conn_flag = "-8" if "conn8" in variant_key else ""
    vrt_path   = out_dir / f"_tmp_{variant_key}.vrt"
    raw_gpkg   = out_dir / f"_tmp_{variant_key}_raw.gpkg"

    try:
        # ── 1. gdalbuildvrt ──────────────────────────────────────────────────
        vrt_cmd = ["gdalbuildvrt", str(vrt_path)] + [str(t) for t in tif_files]
        r = subprocess.run(vrt_cmd, capture_output=True, text=True)
        if r.returncode != 0:
            log.error("gdalbuildvrt misslyckades för %s: %s", variant_key, r.stderr)
            return False
        log.debug("  VRT byggd: %d tiles", len(tif_files))

        # ── 2. gdal_polygonize ───────────────────────────────────────────────
        if raw_gpkg.exists():
            raw_gpkg.unlink()
        poly_cmd = ["gdal_polygonize.py", str(vrt_path)]
        if conn_flag:
            poly_cmd.append(conn_flag)
        poly_cmd += ["-f", "GPKG", str(raw_gpkg), "DN", "markslag"]
        r = subprocess.run(poly_cmd, capture_output=True, text=True)
        if r.returncode != 0 or not raw_gpkg.exists() or raw_gpkg.stat().st_size < 1000:
            log.error("gdal_polygonize misslyckades för %s: %s", variant_key, r.stderr)
            return False
        sz_raw = raw_gpkg.stat().st_size / 1e6
        log.debug("  Polygonize klar: %.1f MB", sz_raw)

        # ── 3. GPKG → GeoJSON ────────────────────────────────────────────────
        raw_json = out_dir / f"_tmp_{variant_key}_raw.geojson"
        r = subprocess.run(
            ["ogr2ogr", "-f", "GeoJSON", str(raw_json), str(raw_gpkg)],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            log.error("ogr2ogr → GeoJSON misslyckades: %s", r.stderr)
            return False
        sz_json = raw_json.stat().st_size / 1e6
        log.debug("  GeoJSON: %.1f MB", sz_json)

        # ── 4. Mapshaper simplify per toleransnivå ───────────────────────────
        ok_count = 0
        for tolerance in SIMPLIFICATION_TOLERANCES:
            out_geojson = out_dir / f"_tmp_{variant_key}_p{tolerance}.geojson"
            out_gpkg    = out_dir / f"{variant_key}_simplified_p{tolerance}.gpkg"

            if SIMPLIFY_PROTECTED:
                js_array  = "[" + ", ".join(str(c) for c in sorted(SIMPLIFY_PROTECTED)) + "]"
                each_expr = f"sp = {js_array}.includes(markslag) ? 1 : {tolerance / 100}"
                mapshaper_cmd = [
                    "mapshaper", str(raw_json),
                    "-each", each_expr,
                    "-simplify", "percentage=sp", "variable", "planar", "keep-shapes",
                    "-o", "format=geojson", str(out_geojson),
                ]
            else:
                mapshaper_cmd = [
                    "mapshaper", str(raw_json),
                    "-simplify", f"percentage={tolerance}%", "planar", "keep-shapes",
                    "-o", "format=geojson", str(out_geojson),
                ]

            mapshaper_env = os.environ.copy()
            if MAPSHAPER_MAX_HEAP_MB > 0:
                mapshaper_env["NODE_OPTIONS"] = f"--max-old-space-size={MAPSHAPER_MAX_HEAP_MB}"

            r = subprocess.run(mapshaper_cmd, capture_output=True, text=True, env=mapshaper_env)
            if r.returncode != 0:
                log.error("Mapshaper misslyckades (p%d): %s", tolerance, r.stderr)
                out_geojson.unlink(missing_ok=True)
                continue

            sz_out = out_geojson.stat().st_size / 1e6
            log.debug("  p%d: %.1f MB  (%.0f%%)", tolerance, sz_out,
                      sz_out / sz_json * 100 if sz_json > 0 else 0)

            if out_gpkg.exists():
                out_gpkg.unlink()
            r = subprocess.run(
                ["ogr2ogr", "-f", "GPKG", "-a_srs", "EPSG:3006",
                 str(out_gpkg), str(out_geojson)],
                capture_output=True, text=True
            )
            out_geojson.unlink(missing_ok=True)
            if r.returncode != 0:
                log.error("ogr2ogr → GPKG misslyckades (p%d): %s", tolerance, r.stderr)
                continue

            sz_gpkg = out_gpkg.stat().st_size / 1e6
            info.info("  ✓ %-50s  %.1f MB  (%d tiles, %d batchar)",
                      out_gpkg.name, sz_gpkg, len(tif_files),
                      len({t.parts[-3] for t in tif_files}))
            ok_count += 1

        return ok_count == len(SIMPLIFICATION_TOLERANCES)

    finally:
        for tmp in [vrt_path, raw_gpkg, raw_json if 'raw_json' in dir() else None]:
            if tmp and Path(tmp).exists():
                Path(tmp).unlink(missing_ok=True)
    """
    1. Mergar alla batch-steg7-GPKG:er till en temporär sammanslagd fil.
    2. Konverterar till GeoJSON.
    3. Kör Mapshaper i ett svep per förenklingstolerans:
         -dissolve markslag   (seam-linjerna försvinner)
         -simplify            (förenkling med samma parametrar som steg 8)
         -explode             (multipolygoner → enskilda polygoner)
    4. Konverterar tillbaka till GPKG (EPSG:3006) per tolerans.
    """
    # Härledd basnamn: "generalized_conn4_mmu050" → "conn4_mmu050"
    base = variant_name.replace("generalized_", "").replace(".gpkg", "")

    merged_gpkg = out_dir / f"_tmp_merged_{variant_name}"
    merged_json = out_dir / "_tmp_merged.geojson"

    try:
        # ── Steg 1: ogr2ogr-merge ────────────────────────────────────────────
        if merged_gpkg.exists():
            merged_gpkg.unlink()
        for i, src in enumerate(sources):
            if i == 0:
                cmd = ["ogr2ogr", "-f", "GPKG", str(merged_gpkg), str(src)]
            else:
                cmd = ["ogr2ogr", "-f", "GPKG", "-append", "-update",
                       str(merged_gpkg), str(src)]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                log.error("ogr2ogr merge misslyckades för %s: %s", src.name, r.stderr)
                return False

        # ── Steg 2: GPKG → GeoJSON ───────────────────────────────────────────
        r = subprocess.run(
            ["ogr2ogr", "-f", "GeoJSON", str(merged_json), str(merged_gpkg)],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            log.error("ogr2ogr → GeoJSON misslyckades: %s", r.stderr)
            return False
        sz_in = merged_json.stat().st_size / 1e6
        log.debug("Sammanslagen GeoJSON: %.1f MB", sz_in)

        # ── Steg 3: Mapshaper per toleransnivå ───────────────────────────────
        ok_count = 0
        for tolerance in SIMPLIFICATION_TOLERANCES:
            out_geojson = out_dir / f"_tmp_{base}_p{tolerance}.geojson"
            out_gpkg    = out_dir / f"{base}_simplified_p{tolerance}.gpkg"

            if SIMPLIFY_PROTECTED:
                js_array  = "[" + ", ".join(str(c) for c in sorted(SIMPLIFY_PROTECTED)) + "]"
                each_expr = f"sp = {js_array}.includes(markslag) ? 1 : {tolerance / 100}"
                mapshaper_cmd = [
                    "mapshaper", str(merged_json),
                    "-dissolve", "markslag",
                    "-each", each_expr,
                    "-simplify", "percentage=sp", "variable", "planar", "keep-shapes",
                    "-explode",
                    "-o", "format=geojson", str(out_geojson),
                ]
            else:
                mapshaper_cmd = [
                    "mapshaper", str(merged_json),
                    "-dissolve", "markslag",
                    "-simplify", f"percentage={tolerance}%", "planar", "keep-shapes",
                    "-explode",
                    "-o", "format=geojson", str(out_geojson),
                ]

            mapshaper_env = os.environ.copy()
            if MAPSHAPER_MAX_HEAP_MB > 0:
                mapshaper_env["NODE_OPTIONS"] = f"--max-old-space-size={MAPSHAPER_MAX_HEAP_MB}"

            r = subprocess.run(mapshaper_cmd, capture_output=True, text=True, env=mapshaper_env)
            if r.returncode != 0:
                log.error("Mapshaper misslyckades (p%d): %s", tolerance, r.stderr)
                out_geojson.unlink(missing_ok=True)
                continue

            sz_out = out_geojson.stat().st_size / 1e6
            log.debug("  p%d: dissolved+simplified GeoJSON %.1f MB  (%.0f%% av input)",
                      tolerance, sz_out, sz_out / sz_in * 100 if sz_in > 0 else 0)

            # ── GeoJSON → GPKG (EPSG:3006) ───────────────────────────────────
            layer_name = f"{variant_key}_simplified_p{tolerance}"
            if out_gpkg.exists():
                out_gpkg.unlink()
            r = subprocess.run(
                ["ogr2ogr", "-f", "GPKG", "-a_srs", "EPSG:3006",
                 "-nln", layer_name,
                 str(out_gpkg), str(out_geojson)],
                capture_output=True, text=True
            )
            out_geojson.unlink(missing_ok=True)
            if r.returncode != 0:
                log.error("ogr2ogr → GPKG misslyckades (p%d): %s", tolerance, r.stderr)
                continue

            sz_gpkg = out_gpkg.stat().st_size / 1e6
            info.info("  ✓ %-55s  %.1f MB  (%d batchar)",
                      out_gpkg.name, sz_gpkg, len(sources))
            ok_count += 1

        return ok_count == len(SIMPLIFICATION_TOLERANCES)

    finally:
        for tmp in (merged_gpkg, merged_json):
            tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    out_dir = OUT_BASE_ROOT / "steg10_merged"
    out_dir.mkdir(parents=True, exist_ok=True)

    log = info = _setup_logging(out_dir)

    t0 = time.time()
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 10: Sammanslagning av batch-resultat (VRT → polygonize → simplify)")
    log.info("Root   : %s", OUT_BASE_ROOT)
    log.info("Utmapp : %s", out_dir)
    log.info("══════════════════════════════════════════════════════════")

    batch_dirs = find_batch_dirs()
    if not batch_dirs:
        log.error("Inga batch_*-kataloger hittades i %s.", OUT_BASE_ROOT)
        sys.exit(1)
    log.info("Hittade %d batchar: %s … %s",
             len(batch_dirs), batch_dirs[0].name, batch_dirs[-1].name)

    variants = collect_raster_variants(batch_dirs)
    if not variants:
        log.error("Inga steg6-raster-tiles hittades.")
        sys.exit(1)
    log.info("Varianter: %s", sorted(variants))
    log.info("Förenklingstoleranser: %s\n", SIMPLIFICATION_TOLERANCES)

    ok = 0
    fail = 0
    for key, tifs in sorted(variants.items()):
        t1 = time.time()
        log.info("➤ %s  (%d tiles)", key, len(tifs))
        if polygonize_and_simplify(key, tifs, out_dir):
            ok += 1
        else:
            log.error("  ✗ %s misslyckades", key)
            fail += 1
        log.debug("  %.1fs", time.time() - t1)

    elapsed = time.time() - t0
    log.info("")
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 10 KLAR: %d OK, %d misslyckade  totaltid: %.0fs (%.1f min)",
             ok, fail, elapsed, elapsed / 60)
    log.info("Utdata: %s", out_dir)
    log.info("══════════════════════════════════════════════════════════")

    sys.exit(0 if fail == 0 else 1)
