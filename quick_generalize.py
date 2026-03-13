#!/usr/bin/env python3
"""
Snabb generalisering: Bara ta bort små polygoner.
Ingen simplification - topologi är 100% säker.
"""

import geopandas as gpd
import logging
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

def quick_generalize(gpkg_path, min_area=400):
    """
    Ultrasnabb generalisering - bara område-filtrering.
    
    Args:
        gpkg_path: Sökväg till GPKG-fil
        min_area: Minsta area i m² (radera mindre)
    """
    gpkg_path = Path(gpkg_path)
    
    log.info("═" * 60)
    log.info("⚡ Snabb generalisering (område-filtrering)")
    log.info("═" * 60)
    log.info(f"Läser: {gpkg_path.name}")
    
    gdf = gpd.read_file(gpkg_path)
    orig_count = len(gdf)
    orig_size = gpkg_path.stat().st_size / 1e6
    
    log.info(f"  {orig_count:,} polygoner, {orig_size:.2f} MB")
    log.info(f"  CRS: {gdf.crs}")
    
    # Beräkna area
    log.info(f"\nBeräknar area...")
    gdf['area'] = gdf.geometry.area
    
    # Filtrera
    log.info(f"Filtrerar polygoner < {min_area} m²...")
    removed = (gdf['area'] < min_area).sum()
    gdf = gdf[gdf['area'] >= min_area].copy()
    remaining = len(gdf)
    
    log.info(f"  ✗ Raderad: {removed:,} småpolygoner")
    log.info(f"  ✓ Kvar: {remaining:,} polygoner")
    
    # Spara GPKG
    gpkg_out_path = gpkg_path.parent / (gpkg_path.stem + "_gen.gpkg")
    log.info(f"\nSparar GPKG...")
    gdf_out = gdf.drop(columns=['area'], errors='ignore')
    gdf_out.to_file(gpkg_out_path, driver='GPKG', layer='DN')
    out_size = gpkg_out_path.stat().st_size / 1e6
    
    log.info(f"  {gpkg_out_path.name}")
    log.info(f"  {out_size:.2f} MB ({(1 - out_size/orig_size)*100:.0f}% mindre)")
    
    # Spara GeoJSON
    geojson_path = gpkg_path.parent / (gpkg_path.stem + "_gen.geojson")
    log.info(f"\nSparar GeoJSON...")
    gdf_out.to_file(geojson_path, driver='GeoJSON')
    json_size = geojson_path.stat().st_size / 1e6
    log.info(f"  {geojson_path.name}")
    log.info(f"  {json_size:.2f} MB")
    
    log.info(f"\n✅ Klart! {(1-remaining/orig_count)*100:.1f}% reducering")
    return gpkg_out_path

if __name__ == "__main__":
    SOURCE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/vectorized/generalized_modal_k15.gpkg")
    quick_generalize(SOURCE, min_area=400)
