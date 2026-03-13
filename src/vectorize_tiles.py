#!/usr/bin/env python3
"""
Vektorisera generaliserade tiles utan minnesproblem
Gör det tile för tile och slår samman i en GPKG
"""
import time
import logging
from pathlib import Path
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape
from shapely.ops import unary_union
import fiona
from fiona.crs import from_epsg
import re

# ════════════════════════════════════════════════════════════════════════════════

PIPELINE_BASE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo")
OUT_BASE = PIPELINE_BASE / "vectorized"
LAYER_NAME = "polygoner"

# ════════════════════════════════════════════════════════════════════════════════

def setup_logging(out_dir: Path):
    ts = time.strftime("%Y%m%d_%H%M%S")
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)-5s] %(message)s',
        handlers=[
            logging.FileHandler(out_dir / f"vectorize_debug_{ts}.log"),
            logging.StreamHandler()
        ]
    )

def vectorize_method_tilebyti(method: str, filenames_to_mmu: dict):
    """
    Vektorisera en metod genom att göra det tile för tile
    
    filenames_to_mmu: dict från "mmu002" till lista av tif-filer
    """
    logger = logging.getLogger(method)
    
    for mmu_key in sorted(filenames_to_mmu.keys()):
        tif_files = filenames_to_mmu[mmu_key]
        
        # Extrahera siffrorna
        m = re.search(r'(\d+)', mmu_key)
        if not m:
            logger.warning(f"  Kan inte parsa MMU från {mmu_key}")
            continue
        
        mmu_val = int(m.group(1))
        
        gpkg_path = OUT_BASE / f"generalized_{method}_mmu{mmu_val:03d}.gpkg"
        
        logger.info(f"  {method} mmu={mmu_val:3d}: {len(tif_files)} tiles → {gpkg_path.name}")
        t0 = time.time()
        
        # Samla polygoner från alla tiles
        all_polys = []
        
        for tif in tif_files:
            try:
                with rasterio.open(tif) as src:
                    data = src.read(1)
                    crs = src.crs
                    transform = src.transform
                
                mask = (data > 0).astype(np.uint8)
                
                # Polygonisera denna tile
                for geom, val in shapes(data, mask=mask, transform=transform):
                    if val == 0:
                        continue
                    all_polys.append({
                        'geometry': geom,
                        'value': int(val)
                    })
                
                del data, mask  # Fri minne
            except Exception as e:
                logger.error(f"    Kunde inte läsa {tif.name}: {e}")
                continue
        
        if not all_polys:
            logger.warning(f"    Inga polygoner hittade")
            continue
        
        # Skriv GeoPackage
        schema = {
            "geometry": "Polygon",
            "properties": {"klass": "int"},
        }
        
        crs_str = crs.to_epsg() and f"EPSG:{crs.to_epsg()}" or crs.to_wkt()
        
        n_written = 0
        try:
            with fiona.open(
                gpkg_path, "w",
                driver="GPKG",
                crs=crs_str,
                schema=schema,
                layer=LAYER_NAME,
            ) as dst:
                for poly_data in all_polys:
                    try:
                        geom_obj = shape(poly_data['geometry'])
                        # Gör giltiga geometrier
                        if not geom_obj.is_valid:
                            geom_obj = geom_obj.buffer(0)
                        
                        if geom_obj.is_empty:
                            continue
                        
                        dst.write({
                            'geometry': geom_obj.__geo_interface__,
                            'properties': {'klass': poly_data['value']},
                        })
                        n_written += 1
                    except Exception as e:
                        logger.debug(f"      Skippade polygon: {e}")
                        continue
        except Exception as e:
            logger.error(f"    Kunde inte skriva {gpkg_path}: {e}")
            continue
        
        elapsed = time.time() - t0
        logger.info(f"    {n_written} polygoner skrivna (%.1fs)", elapsed)


# ════════════════════════════════════════════════════════════════════════════════

def vectorize_all():
    logger = logging.getLogger("main")
    
    # Sieve conn4
    logger.info("\n=== Sieve conn4 ===")
    in_dir = PIPELINE_BASE / "generalized_conn4"
    if in_dir.exists():
        tifs = sorted(in_dir.glob("*.tif"))
        
        mmu_map = {}
        for tif in tifs:
            m = re.search(r'mmu(\d+)', tif.stem)
            if m:
                mmu = m.group(1)
                if mmu not in mmu_map:
                    mmu_map[mmu] = []
                mmu_map[mmu].append(tif)
        
        vectorize_method_tilebyti("conn4", mmu_map)
    else:
        logger.warning(f"  Mapp saknas: {in_dir}")
    
    # Sieve conn8
    logger.info("\n=== Sieve conn8 ===")
    in_dir = PIPELINE_BASE / "generalized_conn8"
    if in_dir.exists():
        tifs = sorted(in_dir.glob("*.tif"))
        
        mmu_map = {}
        for tif in tifs:
            m = re.search(r'mmu(\d+)', tif.stem)
            if m:
                mmu = m.group(1)
                if mmu not in mmu_map:
                    mmu_map[mmu] = []
                mmu_map[mmu].append(tif)
        
        vectorize_method_tilebyti("conn8", mmu_map)
    else:
        logger.warning(f"  Mapp saknas: {in_dir}")
    
    # Modal
    logger.info("\n=== Modal ===")
    in_dir = PIPELINE_BASE / "generalized_modal"
    if in_dir.exists():
        tifs = sorted(in_dir.glob("*.tif"))
        
        k_map = {}
        for tif in tifs:
            m = re.search(r'_k(\d+)', tif.stem)
            if m:
                k = m.group(1)
                if k not in k_map:
                    k_map[k] = []
                k_map[k].append(tif)
        
        for k_val in sorted(k_map.keys()):
            k_int = int(k_val)
            eff_mmu = k_int * k_int // 2
            
            tif_files = k_map[k_val]
            gpkg_path = OUT_BASE / f"generalized_modal_k{k_int:02d}.gpkg"
            
            logger.info(f"  modal k={k_int} (eff. MMU ≈ {eff_mmu} px): {len(tif_files)} tiles")
            t0 = time.time()
            
            all_polys = []
            for tif in tif_files:
                try:
                    with rasterio.open(tif) as src:
                        data = src.read(1)
                        crs = src.crs
                        transform = src.transform
                    
                    mask = (data > 0).astype(np.uint8)
                    for geom, val in shapes(data, mask=mask, transform=transform):
                        if val == 0:
                            continue
                        all_polys.append({'geometry': geom, 'value': int(val)})
                    
                    del data, mask
                except Exception as e:
                    logger.error(f"    {tif.name}: {e}")
            
            if not all_polys:
                logger.warning(f"    Inga polygoner")
                continue
            
            schema = {"geometry": "Polygon", "properties": {"klass": "int"}}
            crs_str = crs.to_epsg() and f"EPSG:{crs.to_epsg()}" or crs.to_wkt()
            
            n_written = 0
            try:
                with fiona.open(gpkg_path, "w", driver="GPKG", crs=crs_str, schema=schema, layer=LAYER_NAME) as dst:
                    for poly_data in all_polys:
                        try:
                            geom_obj = shape(poly_data['geometry'])
                            if not geom_obj.is_valid:
                                geom_obj = geom_obj.buffer(0)
                            if geom_obj.is_empty:
                                continue
                            
                            dst.write({'geometry': geom_obj.__geo_interface__, 'properties': {'klass': poly_data['value']}})
                            n_written += 1
                        except:
                            continue
            except Exception as e:
                logger.error(f"    Skrivfel: {e}")
            
            elapsed = time.time() - t0
            logger.info(f"    {n_written} polygoner skrivna (%.1fs)", elapsed)
    else:
        logger.warning(f"  Mapp saknas: {in_dir}")
    
    # Semantic
    logger.info("\n=== Semantic ===")
    in_dir = PIPELINE_BASE / "generalized_semantic"
    if in_dir.exists():
        tifs = sorted(in_dir.glob("*.tif"))
        
        mmu_map = {}
        for tif in tifs:
            m = re.search(r'mmu(\d+)', tif.stem)
            if m:
                mmu = m.group(1)
                if mmu not in mmu_map:
                    mmu_map[mmu] = []
                mmu_map[mmu].append(tif)
        
        vectorize_method_tilebyti("semantic", mmu_map)
    else:
        logger.warning(f"  Mapp saknas: {in_dir}")


if __name__ == "__main__":
    OUT_BASE.mkdir(parents=True, exist_ok=True)
    setup_logging(OUT_BASE)
    
    logger = logging.getLogger("main")
    logger.info("════════════════════════════════════════════════════════════")
    logger.info("Vektorisering (tile för tile, minnessmart)")
    logger.info(f"Källmapp: {PIPELINE_BASE}")
    logger.info(f"Utmapp:   {OUT_BASE}")
    logger.info("════════════════════════════════════════════════════════════")
    
    t_total = time.time()
    vectorize_all()
    
    elapsed_total = time.time() - t_total
    logger.info(f"\nFärdig på {elapsed_total:.1f}s")
