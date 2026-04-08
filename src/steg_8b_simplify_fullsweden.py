"""
steg_8b_simplify_fullsweden.py — Steg 8b: GRASS-förenkling av hela Sverige.

Förenklar FULLSWEDEN_RAW_GPKG (t.ex. conn4_raw_vect.gpkg — hela Sverige
vektoriserat) med GRASS v.generalize via horisontella Y-bandchunks.

Används när datasetet är för stort för en enda GRASS-session (≥ ~5 M polygoner).
Varje band innehåller ~1/FULLSWEDEN_N_STRIPS av Sveriges Y-extent och
körs som en oberoende GRASS-session.

Mikroskopiska glapp längs bandsömmar är möjliga (godkänt vid
"mikroskopiska glapp är ok"-krav).

Konfigureras via config.py:
  FULLSWEDEN_RAW_GPKG   — sökväg till råvektorisering (hela Sverige)
  FULLSWEDEN_N_STRIPS   — antal Y-band (default 15)
  FULLSWEDEN_OVERLAP_M  — överlapp i meter per sida (default 20000)
  GRASS_SIMPLIFY_METHOD — "douglas", "chaiken", "douglas+chaiken", m.fl.
  GRASS_DOUGLAS_THRESHOLD, GRASS_CHAIKEN_THRESHOLD — trösklar
  GRASS_SNAP_TOLERANCE  — ST_Buffer-δ för glapp-läkning efter merge
  GRASS_PARALLEL_GPKG   — max antal parallella GRASS-jobb

Output skrivs till: OUT_BASE / "steg_8b_fullsweden" /
  conn4_raw_vect_dp<N>_chaiken_t<M>.gpkg  (eller lämpligt namnschema)

Kör alltid via run_all_steps.py:
  python3 run_all_steps.py --step 8b
"""

import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Lägg till src i sökvägen (skriptet körs från repo-roten via run_all_steps.py)
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    OUT_BASE,
    GRASS_SIMPLIFY_METHOD,
    GRASS_DOUGLAS_THRESHOLD,
    GRASS_CHAIKEN_THRESHOLD,
    GRASS_SNAP_TOLERANCE,
    FULLSWEDEN_RAW_GPKG,
    FULLSWEDEN_N_STRIPS,
    FULLSWEDEN_OVERLAP_M,
    FULLSWEDEN_WORKERS,
)
from steg_8_simplify import setup_logging, simplify_gpkg_strips


if __name__ == "__main__":
    t_start = time.time()
    log = setup_logging(OUT_BASE)

    output_dir = OUT_BASE / "steg_8b_fullsweden"
    method = GRASS_SIMPLIFY_METHOD

    # Bygg suffix för loggmeddelanden (speglar output-filnamnskonventionen)
    if method == "douglas":
        sfx = f"dp{int(round(GRASS_DOUGLAS_THRESHOLD))}"
    elif method == "chaiken":
        sfx = f"chaiken_t{int(round(GRASS_CHAIKEN_THRESHOLD))}"
    else:
        sfx = (
            f"dp{int(round(GRASS_DOUGLAS_THRESHOLD))}"
            f"_chaiken_t{int(round(GRASS_CHAIKEN_THRESHOLD))}"
        )

    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 8b: GRASS-förenkling av hela Sverige (Y-bandchunking)")
    log.info("  Input    : %s", FULLSWEDEN_RAW_GPKG)
    log.info("  Output   : %s", output_dir)
    log.info("  Metod    : %s (%s)", method, sfx)
    log.info(
        "  Band     : %d st, ±%.0f km överlapp per sida",
        FULLSWEDEN_N_STRIPS,
        FULLSWEDEN_OVERLAP_M / 1000,
    )
    log.info("  Workers  : %d parallella GRASS-jobb", FULLSWEDEN_WORKERS)
    log.info("══════════════════════════════════════════════════════════")

    if not FULLSWEDEN_RAW_GPKG.exists():
        log.error("Input-fil saknas: %s", FULLSWEDEN_RAW_GPKG)
        log.error("  Kontrollera FULLSWEDEN_RAW_GPKG i config.py")
        sys.exit(1)

    variant_name = FULLSWEDEN_RAW_GPKG.stem  # "conn4_raw_vect"

    simplify_gpkg_strips(
        input_gpkg=FULLSWEDEN_RAW_GPKG,
        output_dir=output_dir,
        variant_name=variant_name,
        n_strips=FULLSWEDEN_N_STRIPS,
        overlap_m=FULLSWEDEN_OVERLAP_M,
        method=method,
        douglas_threshold=GRASS_DOUGLAS_THRESHOLD,
        chaiken_threshold=GRASS_CHAIKEN_THRESHOLD,
        snap_tolerance=GRASS_SNAP_TOLERANCE,
        n_workers=FULLSWEDEN_WORKERS,
        log=log,
    )

    elapsed = time.time() - t_start
    log.info("")
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 8b klar: %.1f min", elapsed / 60)
    log.info("Output : %s", output_dir)
    log.info("══════════════════════════════════════════════════════════")
