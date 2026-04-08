"""
steg_12_clip_to_footprint.py — Steg 12: Klipp vektorlagret till rastrets footprint.

Läser steg_11_overlay_external/{variant}.gpkg och klipper bort polygoner
som ligger utanför rastrets täckningsyta (LM_Saccess_mosaiker i metadata-GPKG:n).

  steg_12_clip_to_footprint/{variant}.gpkg

Approach:
  - Footprint-polygonen extraheras med ogr2ogr från metadata-GPKG:n till en
    temporär fil en gång.
  - Sedan körs ogr2ogr -clipsrc per variant — effektivt och topologibevarade.

Kör: python3 src/steg_12_clip_to_footprint.py
"""

import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from config import OUT_BASE, SRC


# ══════════════════════════════════════════════════════════════════════════════
# Konfiguration
# ══════════════════════════════════════════════════════════════════════════════

# Metadata-GPKG med rastrets footprint
_METADATA_GPKG = SRC.parent / "NMD2023_metadata_v2_0.gpkg"
_FOOTPRINT_LAYER = "LM_Saccess_mosaiker"


# ══════════════════════════════════════════════════════════════════════════════
# Logging
# ══════════════════════════════════════════════════════════════════════════════

def setup_logging(out_base):
    log_dir     = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    step_num  = os.getenv("STEP_NUMBER", "12")
    step_name = os.getenv("STEP_NAME", "clip_to_footprint").lower()
    suffix    = f"steg_{step_num}_{step_name}_{ts}"
    fmt_d = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fmt_s = logging.Formatter(
        "%(asctime)s [%(levelname)-6s] %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("pipeline.clip_to_footprint")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    log.handlers.clear()
    dbg = logging.FileHandler(str(log_dir / f"debug_{suffix}.log"))
    dbg.setLevel(logging.DEBUG); dbg.setFormatter(fmt_d); log.addHandler(dbg)
    fh = logging.FileHandler(str(summary_dir / f"summary_{suffix}.log"))
    fh.setLevel(logging.INFO); fh.setFormatter(fmt_s); log.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO); ch.setFormatter(fmt_s); log.addHandler(ch)
    return log


# ══════════════════════════════════════════════════════════════════════════════
# Huvud
# ══════════════════════════════════════════════════════════════════════════════

def main():
    log = setup_logging(OUT_BASE)
    t0  = time.time()

    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 12: Klipp vektorlager till rastrets footprint")
    log.info("Källmapp : %s", OUT_BASE / "steg_11_overlay_external")
    log.info("Utmapp   : %s", OUT_BASE / "steg_12_clip_to_footprint")
    log.info("Footprint: %s  [%s]", _METADATA_GPKG, _FOOTPRINT_LAYER)
    log.info("══════════════════════════════════════════════════════════")

    # Verifiera källfiler
    if not _METADATA_GPKG.exists():
        log.error("Metadata-GPKG saknas: %s", _METADATA_GPKG)
        sys.exit(1)

    src_dir = OUT_BASE / "steg_11_overlay_external"
    if not src_dir.exists():
        log.error("steg_11_overlay_external/ saknas — kör steg 11 först")
        sys.exit(1)

    gpkgs = sorted(src_dir.glob("*.gpkg"))
    if not gpkgs:
        log.error("Inga GPKG-filer i %s", src_dir)
        sys.exit(1)

    out_dir = OUT_BASE / "steg_12_clip_to_footprint"
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = OUT_BASE / "steg_12_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Steg A: Extrahera footprint-polygon till temporär GPKG (en gång)
    footprint_gpkg = work_dir / "footprint.gpkg"
    if not footprint_gpkg.exists():
        log.info("  Extraherar footprint-polygon...")
        r = subprocess.run([
            "ogr2ogr", "-f", "GPKG", "-overwrite",
            str(footprint_gpkg), str(_METADATA_GPKG), _FOOTPRINT_LAYER,
        ], capture_output=True, text=True)
        if r.returncode != 0:
            log.error("  Kan inte extrahera footprint: %s", r.stderr[:300])
            sys.exit(1)
        log.info("  Footprint extraherad: %s", footprint_gpkg)
    else:
        log.info("  Footprint finns redan: %s", footprint_gpkg)

    # Steg B: Klipp varje variant med -clipsrc
    ok_count = 0
    for gpkg in gpkgs:
        out_gpkg = out_dir / gpkg.name
        if out_gpkg.exists():
            log.info("  Hoppar %s — redan klar", gpkg.name)
            ok_count += 1
            continue

        log.info("  Klipper %s...", gpkg.name)
        t1 = time.time()
        tmp = out_dir / (gpkg.stem + ".tmp.gpkg")
        tmp.unlink(missing_ok=True)

        r = subprocess.run([
            "ogr2ogr", "-f", "GPKG", "-overwrite",
            "-clipsrc", str(footprint_gpkg),
            "-nln", gpkg.stem,
            str(tmp), str(gpkg),
        ], capture_output=True, text=True)

        if r.returncode != 0:
            log.error("  ogr2ogr misslyckades för %s: %s", gpkg.name, r.stderr[:300])
            tmp.unlink(missing_ok=True)
            continue

        tmp.rename(out_gpkg)
        sz = out_gpkg.stat().st_size / 1e9
        elapsed = time.time() - t1
        log.info("  ✓ %s — %.2f GB  (%.1f min)", gpkg.name, sz, elapsed / 60)
        ok_count += 1

    total = time.time() - t0
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 12 klart — %d/%d varianter  %.1f min", ok_count, len(gpkgs), total / 60)
    log.info("Output i %s", out_dir)
    log.info("══════════════════════════════════════════════════════════")


if __name__ == "__main__":
    main()
