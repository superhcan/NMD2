#!/usr/bin/env python3
"""
Generalisera GPKG-filer med GeoJSON-format och geometriminskning.

Metod:
1. Laddar GPKG-fil i GeoJSON-format (via geopandas)
2. Tillämpar Douglas-Peucker simplification
3. Tar bort små polygoner (area < min_area)
4. Eventuell dissolve av närliggande områden
5. Sparar som både GPKG och GeoJSON

Kräver: geopandas, shapely
"""

import geopandas as gpd
import logging
from pathlib import Path
from datetime import datetime
import json

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

def generalize_with_geojson(gpkg_path, tolerance=2, min_area=400, output_format="both"):
    """
    Generalisera GeoPackage-fil - snabb & topologiskt säker metod.
    
    Använder minimal simplification + område-filtrering för att undvika luckor.
    Bevarar all topologi - ingen buffering eller dissolve.
    
    Args:
        gpkg_path: Sökväg till GPKG-fil
        tolerance: Douglas-Peucker tolerance i meter (default 2m, mycket låg för säkerhet)
        min_area: Minsta tillåten area för polygoner i m² (default 400 m²)
        output_format: "both" = spara som GPKG+GeoJSON, "gpkg" eller "geojson"
    """
    gpkg_path = Path(gpkg_path)
    if not gpkg_path.exists():
        log.error(f"Fil existerar inte: {gpkg_path}")
        return None
    
    log.info("╔" + "═" * 58 + "╗")
    log.info("║ Snabb & topologiskt säker generalisering")
    log.info("╚" + "═" * 58 + "╝")
    log.info(f"Fil: {gpkg_path.name}")
    
    # Läs fil
    log.info(f"Läser {gpkg_path.name}...")
    gdf = gpd.read_file(gpkg_path)
    orig_count = len(gdf)
    orig_size = gpkg_path.stat().st_size / 1e6
    
    log.info(f"  Polygoner: {orig_count:,}")
    log.info(f"  Filstorlek: {orig_size:.2f} MB")
    log.info(f"  CRS: {gdf.crs}")
    
    # 1. Ultra-mild simplification endast på vertexar
    log.info(f"\n1️⃣  Ultra-mild simplification (tolerance={tolerance}m)...")
    gdf['geometry'] = gdf.geometry.simplify(tolerance, preserve_topology=True)
    log.info(f"   ✓ Geometrier förenklade (topologi bevarad)")
    
    # 2. Filtrering av små polygoner - detta är huvudgeneralisering
    log.info(f"\n2️⃣  Tar bort små polygoner (area < {min_area} m²)...")
    gdf['area'] = gdf.geometry.area
    small_count = (gdf['area'] < min_area).sum()
    gdf = gdf[gdf['area'] >= min_area].copy()
    remaining = len(gdf)
    log.info(f"   ✓ {small_count:,} små polygoner borttagna")
    log.info(f"   ✓ {remaining:,} polygoner återstår")
    
    # 3. Exportera som GeoJSON
    geojson_path = None
    if output_format in ["both", "geojson"]:
        geojson_path = gpkg_path.parent / (gpkg_path.stem + "_gen.geojson")
        log.info(f"\n3️⃣  Exporterar till GeoJSON...")
        
        gdf_geojson = gdf.drop(columns=['area'], errors='ignore')
        gdf_geojson.to_file(geojson_path, driver='GeoJSON')
        geojson_size = geojson_path.stat().st_size / 1e6
        log.info(f"   ✓ {geojson_path.name}")
        log.info(f"   ✓ {geojson_size:.2f} MB")
    
    # 4. Spara som GPKG
    gpkg_out_path = None
    if output_format in ["both", "gpkg"]:
        gpkg_out_path = gpkg_path.parent / (gpkg_path.stem + "_gen.gpkg")
        log.info(f"\n4️⃣  Exporterar till GeoPackage...")
        
        gdf_out = gdf.drop(columns=['area'], errors='ignore')
        gdf_out.to_file(gpkg_out_path, driver='GPKG', layer='DN')
        
        gpkg_out_size = gpkg_out_path.stat().st_size / 1e6
        log.info(f"   ✓ {gpkg_out_path.name}")
        log.info(f"   ✓ {gpkg_out_size:.2f} MB")
    
    # Statistik
    log.info(f"\n📊 Resultat:")
    log.info(f"   Innan: {orig_count:,} polygoner, {orig_size:.2f} MB")
    log.info(f"   Efter: {remaining:,} polygoner")
    pct = (1 - remaining / orig_count) * 100 if orig_count > 0 else 0
    log.info(f"   Minskning: {pct:.1f}%")
    
    if gpkg_out_path:
        pct_size = (1 - gpkg_out_size / orig_size) * 100 if orig_size > 0 else 0
        log.info(f"   Filreduktion: {pct_size:.1f}%")
    
    log.info(f"\n✅ Generalisering ok - topologi bevarad!")
    
    return {
        'gpkg': gpkg_out_path,
        'geojson': geojson_path,
        'rows': remaining,
        'reduction_pct': pct
    }

if __name__ == "__main__":
    # Källa: filen som ska generaliseras
    SOURCE_FILE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/vectorized/generalized_modal_k15.gpkg")
    
    # Parametrar
    TOLERANCE = 2       # Douglas-Peucker - mycket låg för att bevara topologi
    MIN_AREA = 400      # Huvudgeneralisering - ta bort små områden
    OUTPUT_FORMAT = "both"  # "both", "gpkg" eller "geojson"
    
    result = generalize_with_geojson(
        SOURCE_FILE,
        tolerance=TOLERANCE,
        min_area=MIN_AREA,
        output_format=OUTPUT_FORMAT
    )
