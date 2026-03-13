#!/usr/bin/env python3
"""
Extrahera landskapet utan vägar och byggnader från generalized_modal_k15.gpkg
"""

import logging
from pathlib import Path
import geopandas as gpd

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

def main():
    log.info("╔" + "═" * 58 + "╗")
    log.info("║ Extraherar landskapet (utan vägar och byggnader)")
    log.info("╚" + "═" * 58 + "╝")
    
    src_file = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/generalized_modal_k15.gpkg")
    out_file = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/generalized_modal_k15_landscape_only.gpkg")
    
    log.info(f"\n1️⃣  Läser {src_file.name}...")
    gdf = gpd.read_file(src_file)
    log.info(f"   • {len(gdf):,} polygoner innan filtrering")
    log.info(f"   • Klasser: {sorted(gdf['markslag'].unique().tolist())}")
    
    # Filtrera bort vägar (53) och byggnader (51)
    log.info(f"\n2️⃣  Filtrerar bort vägar (53) och byggnader (51)...")
    gdf_landscape = gdf[~gdf['markslag'].isin([51, 53])].copy()
    
    log.info(f"   • {len(gdf_landscape):,} polygoner efter filtrering")
    log.info(f"   • Klasser: {sorted(gdf_landscape['markslag'].unique().tolist())}")
    
    # Spara
    log.info(f"\n3️⃣  Sparar till {out_file.name}...")
    if out_file.exists():
        out_file.unlink()
    
    gdf_landscape.to_file(out_file, driver='GPKG')
    size_mb = out_file.stat().st_size / 1e6
    
    log.info(f"   ✓ Sparad: {size_mb:.2f} MB")
    
    # Statistik per klass
    log.info(f"\n📊 Polygoner per klass:")
    for cls in sorted(gdf_landscape['markslag'].unique()):
        count = len(gdf_landscape[gdf_landscape['markslag'] == cls])
        log.info(f"   • {cls:2d}: {count:6,d} polygoner")
    
    log.info(f"\n✅ Klart!")
    log.info(f"   Input:  {src_file.name} ({len(gdf):,} polygoner)")
    log.info(f"   Output: {out_file.name} ({len(gdf_landscape):,} polygoner)")
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
