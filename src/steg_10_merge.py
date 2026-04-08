"""
steg_10_merge.py — Steg 10: Slå ihop strip-GPKGs till en slutlig GPKG per variant.

Läser strip_000.gpkg … strip_NNN.gpkg från steg_9_overlay_buildings/{variant}/
(eller steg_8_simplify/{variant}/ om steg 9 saknas) och skapar:

  steg_10_merge/{variant}.gpkg

med ogr2ogr -append. Varje strips lager läggs till med -nln {variant} så att
alla strips hamnar i ett enda lager i slutfilen.

Körordning: sekventiell per variant (merge är disk-I/O-bound, inte CPU-bound).
"""

import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from config import OUT_BASE
from strips import compute_strips, src_extent


# ══════════════════════════════════════════════════════════════════════════════
# Logging
# ══════════════════════════════════════════════════════════════════════════════

def setup_logging(out_base):
    log_dir     = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    step_num  = os.getenv("STEP_NUMBER", "10")
    step_name = os.getenv("STEP_NAME", "merge").lower()
    suffix    = f"steg_{step_num}_{step_name}_{ts}"
    fmt_d = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fmt_s = logging.Formatter(
        "%(asctime)s [%(levelname)-6s] %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("pipeline.merge")
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


# ══════════════════════════════════════════════════════════════════════════════
# Merge-funktion
# ══════════════════════════════════════════════════════════════════════════════

def merge_variant(variant_dir: Path, out_gpkg: Path, log) -> bool:
    """
    Slår ihop alla strip_NNN.gpkg i variant_dir till en enda out_gpkg.

    Använder ogr2ogr -append med -nln {variant_name} för att alla strips
    hamnar i ett enda lager med variantnamnet som lagernamn.

    Returnerar True om OK, False vid fel.
    """
    strip_files = sorted(variant_dir.glob("strip_???.gpkg"))
    if not strip_files:
        log.warning("  Inga strip_NNN.gpkg i %s", variant_dir)
        return False

    variant_name = variant_dir.name
    log.info("  %s: %d strip(s) → %s", variant_name, len(strip_files), out_gpkg.name)

    if out_gpkg.exists():
        out_gpkg.unlink()

    for i, strip_gpkg in enumerate(strip_files):
        cmd = [
            "ogr2ogr", "-f", "GPKG",
            "-nln", variant_name,
        ]
        if i > 0:
            cmd += ["-append", "-update"]
        cmd += [str(out_gpkg), str(strip_gpkg)]

        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            log.error("  [%s] strip %d ogr2ogr misslyckades: %s",
                      variant_name, i, r.stderr[:300])
            return False

    if not out_gpkg.exists():
        log.error("  [%s] ingen output-fil skapades", variant_name)
        return False

    sz_mb = out_gpkg.stat().st_size / 1024**2
    log.info("  ✓ %s — %.1f MB (%d strips)", out_gpkg.name, sz_mb, len(strip_files))
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    t0  = time.time()
    log = setup_logging(OUT_BASE)

    out_dir = OUT_BASE / "steg_10_merge"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Välj källrot: steg 9 om det körts, annars steg 8
    _steg9 = OUT_BASE / "steg_9_overlay_buildings"
    _steg8 = OUT_BASE / "steg_8_simplify"
    if _steg9.exists() and any(_steg9.iterdir()):
        src_root  = _steg9
        src_label = "steg_9_overlay_buildings"
    elif _steg8.exists() and any(_steg8.iterdir()):
        src_root  = _steg8
        src_label = "steg_8_simplify"
    else:
        log.error("Varken steg_9_overlay_buildings/ eller steg_8_simplify/ finns")
        sys.exit(1)

    log.info("═" * 58)
    log.info("Steg 10: Slå ihop strip-GPKGs till slutlig GPKG per variant")
    log.info("Källrot : %s", src_root)
    log.info("Utmapp  : %s", out_dir)
    log.info("═" * 58)

    variant_dirs = sorted(d for d in src_root.iterdir() if d.is_dir())
    if not variant_dirs:
        log.error("Inga variant-kataloger i %s", src_root)
        sys.exit(1)

    ok_count = 0
    for variant_dir in variant_dirs:
        out_gpkg = out_dir / f"{variant_dir.name}.gpkg"
        if out_gpkg.exists():
            log.info("  Hoppar över %s — finns redan", out_gpkg.name)
            ok_count += 1
            continue
        if merge_variant(variant_dir, out_gpkg, log):
            ok_count += 1

    elapsed = time.time() - t0
    log.info("")
    log.info("═" * 58)
    log.info("Steg 10 klart — %d/%d varianter  %.1f min (%.0fs)",
             ok_count, len(variant_dirs), elapsed / 60, elapsed)
    log.info("Output i %s", out_dir)
    log.info("═" * 58)
