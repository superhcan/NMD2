#!/usr/bin/env python3
"""
Extrahera skyddade NMD-klasser från original-tiles och vektorisera till GPKG.

VIKTIGT: Utgår från ORIGINAL-tiles i /tiles/ mappen för korrekt georeferensering.

Skyddade klasser (aldrig generaliseras):
- 51 = Exploaterad mark, byggnad
- 52 = Exploaterad mark, ej byggnad eller väg/järnväg
- 53 = Exploaterad mark, väg/järnväg
- 54 = Exploaterad mark, torvtäkt
- 61 = Sjö och vattendrag
- 62 = Hav

Output: Separat vektorskikt av endast dessa klasser.
"""

import logging
from pathlib import Path
import numpy as np
import rasterio
from rasterio.features import shapes
import geopandas as gpd
from shapely.geometry import shape
import time

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

# Inställningar
TILE_DIR = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/tiles")
OUT_DIR = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/protected")
OUT_GPKG = OUT_DIR / "buildings_roads_test.gpkg"  # TEST-version

# Klasser att extrahera
PROTECTED = {51, 53}  # Byggnad och Väg/järnväg

def main():
    log.info("╔" + "═" * 58 + "╗")
    log.info("║ Extrahering av byggnad och vägar (TESTVERSION)")
    log.info("║ Från 4 testiles: r000_c020, r000_c021, r001_c020, r001_c021")
    log.info("╚" + "═" * 58 + "╝")
    
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Välj testiles (endast 4 för snabb testning)
    log.info(f"\n1️⃣  Läser test-tiles...")
    test_tile_names = [
        "NMD2023bas_tile_r000_c020.tif",
        "NMD2023bas_tile_r000_c021.tif",
        "NMD2023bas_tile_r001_c020.tif",
        "NMD2023bas_tile_r001_c021.tif",
    ]
    
    tiles = [TILE_DIR / name for name in test_tile_names]
    tiles = [t for t in tiles if t.exists()]
    
    if not tiles:
        log.error(f"   ✗ Inga testiles hittades i {TILE_DIR}")
        return False
    
    log.info(f"   • {len(tiles)} testiles hittade")
    
    # 2. Iterera över testiles och extrahera skyddade klasser
    log.info(f"\n2️⃣  Extraherar skyddade klasser från {len(tiles)} testiles...")
    t0 = time.time()
    
    polys = []
    crs = None
    
    for i, tile_file in enumerate(tiles, 1):
        if i % 100 == 0 or i == 1:
            log.info(f"   • Tile {i}/{len(tiles)}: {tile_file.name}")
        
        with rasterio.open(tile_file) as src:
            data = src.read(1)
            transform = src.transform
            
            if crs is None:
                crs = src.crs
            
            # Skapa mask för skyddade klasser
            mask = np.isin(data, list(PROTECTED)).astype(np.uint8)
            
            if np.count_nonzero(mask) == 0:
                continue  # Hoppa över tile om ingen skyddad klass
            
            # Vektorisera bara skyddade klasser
            for geom, value in shapes(data, mask=mask, transform=transform):
                if value in PROTECTED:
                    geom_shape = shape(geom)
                    if geom_shape.is_valid and geom_shape.area > 0:
                        polys.append({
                            'geometry': geom_shape,
                            'class': int(value)
                        })
    
    log.info(f"\n3️⃣  Vektorisering komplett")
    log.info(f"   • {len(polys):,} polygoner totalt")
    t1 = time.time()
    log.info(f"   • Tid: {t1-t0:.1f}s")
    
    # 3. Spara till GeoPackage
    log.info(f"\n4️⃣  Sparar till GeoPackage...")
    
    if OUT_GPKG.exists():
        OUT_GPKG.unlink()
    
    gdf = gpd.GeoDataFrame(polys, crs=crs)
    
    # Lägg till klassnamn
    class_names = {
        51: "Byggnad",
        53: "Väg/järnväg"
    }
    gdf['class_name'] = gdf['class'].map(class_names)
    
    gdf.to_file(OUT_GPKG, driver='GPKG', layer='protected_classes')
    
    size_mb = OUT_GPKG.stat().st_size / 1e6
    log.info(f"   ✓ {OUT_GPKG.name}")
    log.info(f"   ✓ {size_mb:.2f} MB")
    
    # 5. Statistik per klass
    log.info(f"\n📊 Statistik per skyddad klass:")
    for cls in sorted(PROTECTED):
        count = len(gdf[gdf['class'] == cls])
        class_name = class_names.get(cls, "Okänd")
        log.info(f"   • {cls:2d} ({class_name:30s}): {count:6d} polygoner")
    
    log.info(f"\n✅ Skyddade klasser extraherade från testiles!")
    log.info(f"   Output: {OUT_GPKG}")
    log.info(f"\n📝 TEST-version - använd buildings_roads.gpkg för full körning senare")
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
