"""
pipeline.py — Huvudpipeline som orchestrerar alla generaliserings- och vektoriseringssteg.

Anropar de olika stegen i rätt ordning:
  1. split_tiles.py - Dela upp källbilden i 1024×1024 px sub-tiles
  2. extract_protected_classes.py - Extrahera skyddade klasser
  3. replace_roads_buildings.py - Ersätt vägar/byggnader med grannande klasser
  4. fill_islands.py - Fyll landöar < 100 px
  5a-5d. generalize_*.py - Kör fyra parallella generaliseringsmetoder
"""

import logging
import time
from datetime import datetime
from pathlib import Path

from config import OUT_BASE
from logging_setup import setup_logging

# Import steg-funktioner
from rasterize_tiles import rasterize_tiles
from extract_protected_classes import extract_protected_classes
from replace_roads_buildings import replace_roads_buildings
from fill_islands import fill_islands
from generalize_sieve_halo import generalize_sieve_halo
from generalize_modal_halo import generalize_modal_halo
from generalize_semantic_halo import generalize_semantic_halo


def main():
    """Kör hela pipelinen."""
    # Setup loggning
    setup_logging(OUT_BASE)
    log  = logging.getLogger("pipeline.debug")
    info = logging.getLogger("pipeline.summary")
    
    t_total = time.time()
    ts_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    info.info("══════════════════════════════════════════════════════════")
    info.info("NMD pipeline_1024_halo.py  startad %s", ts_start)
    info.info("Utmapp: %s", OUT_BASE)
    info.info("══════════════════════════════════════════════════════════")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Steg 1: Dela upp i tiles
    # ─────────────────────────────────────────────────────────────────────────
    info.info("\nSteg 1: Dela upp i 1024×1024 px tiles")
    tile_paths = rasterize_tiles()
    
    # ─────────────────────────────────────────────────────────────────────────
    # Steg 2: Extrahera skyddade klasser
    # ─────────────────────────────────────────────────────────────────────────
    info.info("\nSteg 2: Extrahera skyddade klasser från original-tiles")
    protected_paths = extract_protected_classes(tile_paths)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Steg 3: Ersätt vägar/byggnader med grannande klasser
    # ─────────────────────────────────────────────────────────────────────────
    info.info("\nSteg 3: Ersätt vägar/byggnader från original-tiles")
    landscape_paths = replace_roads_buildings(tile_paths)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Steg 4: Fyll öar
    # ─────────────────────────────────────────────────────────────────────────
    info.info("\nSteg 4: Fyll landöar")
    filled_paths = fill_islands(landscape_paths)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Steg 5: Generalisering med fyra parallella metoder
    # ─────────────────────────────────────────────────────────────────────────
    
    info.info("\nSteg 5a: Sieve conn4 (med halo)")
    generalize_sieve_halo(filled_paths, conn=4)
    
    info.info("\nSteg 5b: Sieve conn8 (med halo)")
    generalize_sieve_halo(filled_paths, conn=8)
    
    info.info("\nSteg 5c: Modal filter (med halo)")
    generalize_modal_halo(filled_paths)
    
    info.info("\nSteg 5d: Semantisk generalisering (med halo)")
    generalize_semantic_halo(filled_paths)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Sammanfattning
    # ─────────────────────────────────────────────────────────────────────────
    elapsed = time.time() - t_total
    info.info("══════════════════════════════════════════════════════════")
    info.info("Pipeline KLAR  totaltid: %.0fs (%.1f min)", elapsed, elapsed / 60)
    info.info("Utdata: %s", OUT_BASE)
    info.info("══════════════════════════════════════════════════════════")


if __name__ == "__main__":
    main()
