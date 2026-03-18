#!/usr/bin/env python3
"""
steg_10_merge_batches.py — Steg 10: Sammanslagning av alla batch-resultat.

Körs EFTER att alla batchar (batch_000 ... batch_NNN) är klara.
Skriver till OUT_BASE_ROOT/steg10_merged/ (ej inuti någon batch-subdirektory).

För varje GPKG-variant i steg8_simplified/:
  1. Slår ihop alla batch-versioner med ogr2ogr
  2. Kör Mapshaper -dissolve markslag för att lösa upp batch-gräns-artefakter
  3. Konverterar tillbaka till GPKG (EPSG:3006)

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

from config import OUT_BASE_ROOT, PARENT_TILES

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


def collect_variants(batch_dirs: list[Path]) -> dict[str, list[Path]]:
    """Samlar alla steg8-GPKG-varianter och mappar variant-namn → lista av filer."""
    variants: dict[str, list[Path]] = {}
    for bd in batch_dirs:
        s8 = bd / "steg8_simplified"
        if not s8.exists():
            log.debug("Saknar steg8_simplified i %s — hoppar", bd.name)
            continue
        for gpkg in sorted(s8.glob("*.gpkg")):
            variants.setdefault(gpkg.name, []).append(gpkg)
    return variants


def merge_and_dissolve(variant_name: str, sources: list[Path], out_dir: Path) -> bool:
    """
    1. Mergar alla batch-GPKG:er till en temporär sammanslagd fil.
    2. Konverterar till GeoJSON.
    3. Kör Mapshaper -dissolve markslag.
    4. Konverterar tillbaka till GPKG (EPSG:3006).
    """
    merged_gpkg = out_dir / f"_tmp_merged_{variant_name}"
    merged_json = out_dir / "_tmp_merged.geojson"
    dissolved_json = out_dir / "_tmp_dissolved.geojson"
    out_gpkg    = out_dir / variant_name

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

        # ── Steg 3: Mapshaper dissolve ────────────────────────────────────────
        r = subprocess.run(
            ["mapshaper", str(merged_json),
             "-dissolve", "markslag",
             "-o", "format=geojson", str(dissolved_json)],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            log.error("Mapshaper dissolve misslyckades: %s", r.stderr)
            return False
        sz_out = dissolved_json.stat().st_size / 1e6
        log.debug("Dissolved GeoJSON: %.1f MB  (%.0f%% av input)", sz_out,
                  sz_out / sz_in * 100 if sz_in > 0 else 0)

        # ── Steg 4: GeoJSON → GPKG (EPSG:3006) ───────────────────────────────
        if out_gpkg.exists():
            out_gpkg.unlink()
        r = subprocess.run(
            ["ogr2ogr", "-f", "GPKG", "-a_srs", "EPSG:3006",
             str(out_gpkg), str(dissolved_json)],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            log.error("ogr2ogr → GPKG misslyckades: %s", r.stderr)
            return False

        sz_gpkg = out_gpkg.stat().st_size / 1e6
        info.info("  ✓ %-50s  %.1f MB  (%d batchar)", variant_name, sz_gpkg, len(sources))
        return True

    finally:
        for tmp in (merged_gpkg, merged_json, dissolved_json):
            tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    # Utmapp är alltid root-nivå, inte inuti en enskild batch
    out_dir = OUT_BASE_ROOT / "steg10_merged"
    out_dir.mkdir(parents=True, exist_ok=True)

    log = info = _setup_logging(out_dir)

    t0 = time.time()
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 10: Sammanslagning av batch-resultat")
    log.info("Root   : %s", OUT_BASE_ROOT)
    log.info("Utmapp : %s", out_dir)
    log.info("══════════════════════════════════════════════════════════")

    if PARENT_TILES is not None:
        log.info("Testläge (PARENT_TILES satt) — steg 10 körs ändå på alla batch_*-mappar.")

    batch_dirs = find_batch_dirs()
    if not batch_dirs:
        log.error("Inga batch_*-kataloger hittades i %s.", OUT_BASE_ROOT)
        sys.exit(1)
    log.info("Hittade %d batchar: %s … %s",
             len(batch_dirs), batch_dirs[0].name, batch_dirs[-1].name)

    variants = collect_variants(batch_dirs)
    if not variants:
        log.error("Inga GPKG-filer hittades i steg8_simplified/.")
        sys.exit(1)
    log.info("Varianter att slå samman: %s\n", sorted(variants))

    ok = 0
    fail = 0
    for variant_name, sources in sorted(variants.items()):
        t1 = time.time()
        log.info("➤ %s  (%d batchar)", variant_name, len(sources))
        if merge_and_dissolve(variant_name, sources, out_dir):
            ok += 1
        else:
            log.error("  ✗ %s misslyckades", variant_name)
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
