"""
Topologi-validering: Detekt slivers och gaps mellan polygoner.
"""

import logging
from pathlib import Path

import geopandas as gpd
from shapely.ops import unary_union

log = logging.getLogger("pipeline.debug")


def validate_topology(gpkg_path: Path):
    """
    Validera att det inte finns slivers/gaps mellan polygoner.
    
    Metod:
    1. Union alla polygoner
    2. Buffer in/ut med liten tolerans
    3. Jämför arean före/efter
    4. Om mycket area försvann = slivers/gaps existerar
    """
    log.info(f"Validerar topologi: {gpkg_path.name}")
    
    gdf = gpd.read_file(gpkg_path)
    
    # Originalgeometri
    union_original = unary_union(gdf.geometry)
    area_original = union_original.area
    log.debug(f"  Original union area: {area_original:.0f} m²")
    
    # Buffer tests
    try:
        # Buffer ut och in med samma tolerans  
        buffer_dist = 0.5  # 0.5 m buffer
        buffered_out = union_original.buffer(buffer_dist)
        buffered_in = buffered_out.buffer(-buffer_dist)
        area_after_buffer = buffered_in.area
        
        area_lost = ((area_original - area_after_buffer) / area_original) * 100
        log.debug(f"  Area efter buffer±{buffer_dist}: {area_after_buffer:.0f} m²")
        log.debug(f"  Area förlorad: {area_lost:.3f}%")
        
        if area_lost > 0.1:  # Mer än 0.1% förlorad = problem
            log.warning(f"  ✗ SLIVERS DETEKTADE! {area_lost:.3f}% area förlorad")
            return False
        else:
            log.info(f"  ✓ Topologi OK: Endast {area_lost:.4f}% area variation")
            return True
    
    except Exception as e:
        log.error(f"  Validering misslyckades: {e}")
        return False


if __name__ == "__main__":
    from config import OUT_BASE
    from logging_setup import setup_logging
    setup_logging(OUT_BASE)
    log = logging.getLogger("pipeline.debug")
    
    # Test båda versionerna
    original = OUT_BASE / "simplified/modal_k15_original.gpkg"
    simplified_t10 = OUT_BASE / "simplified/modal_k15_simplified_t10.gpkg"
    
    print("=" * 60)
    print("TOPOLOGI-VALIDERING")
    print("=" * 60)
    
    if original.exists():
        print("\nOriginal (från PostGIS):")
        validate_topology(original)
    
    if simplified_t10.exists():
        print("\nSimplified t10 (från PostGIS):")
        result_postgis = validate_topology(simplified_t10)
        print(f"Resultat PostGIS: {'✓ OK' if result_postgis else '✗ SLIVERS'}")
    
    # Test ogr2ogr version
    test_file = Path("/tmp/test_simplified.gpkg")
    if test_file.exists():
        print("\nSimplified t10 (från ogr2ogr -simplify):")
        result_ogr = validate_topology(test_file)
        print(f"Resultat ogr2ogr: {'✓ OK' if result_ogr else '✗ SLIVERS'}")
    
    print("=" * 60)
