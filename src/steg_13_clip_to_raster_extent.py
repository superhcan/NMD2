"""
steg_13_clip_to_raster_extent.py — Steg 13: Klipp vektor till rasters giltiga dataarea.

Läser steg_12_clip_to_footprint/{variant}.gpkg och klipper bort polygoner
som ligger utanför pixlar som inte är 0 i steg_6_generalize/{variant}/_mosaic.vrt.

  steg_13_clip_to_raster_extent/{variant}.gpkg

Approach:
  - Steg 6-rastret läses in
  - En binär mask skapas (pixlar != 0)
  - Masken vektoriseras till polygon
  - Steg 12-vektorn klipps mot masken med ogr2ogr -clipsrc
  - Resultat sparas

Kör: python3 src/steg_13_clip_to_raster_extent.py
"""

import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from shapely.geometry import box

from config import OUT_BASE


# ══════════════════════════════════════════════════════════════════════════════
# Logging
# ══════════════════════════════════════════════════════════════════════════════

def setup_logging(out_base):
    log_dir     = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    step_num  = os.getenv("STEP_NUMBER", "13")
    step_name = os.getenv("STEP_NAME", "clip_to_raster_extent").lower()
    suffix    = f"steg_{step_num}_{step_name}_{ts}"
    fmt_d = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fmt_s = logging.Formatter(
        "%(asctime)s [%(levelname)-6s] %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("pipeline.clip_to_raster_extent")
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
# Maskgenerering från raster
# ══════════════════════════════════════════════════════════════════════════════

def create_raster_mask_polygon(raster_path, work_dir, log):
    """
    Skapar mask från rastrets FAKTISKA giltiga område (alla icke-noll pixlar).
    Inte från steg 10-markpolygoner, utan från rastret själv.
    Detta tar bort ALLT utanför rastret: mark OCH vatten.
    Returnerar GPKG-path med masken.
    """
    log.info("  Skapar mask från rastrets faktiska giltiga område...")
    
    try:
        return create_raster_mask_from_vrt(raster_path, work_dir, log)
            
    except Exception as e:
        log.error("  Fel vid maskering: %s", str(e))
        return None


def create_raster_mask_from_vrt(raster_path, work_dir, log):
    """
    Fallback: Vektoriserar rastret (icke-noll pixlar) med gdal_polygonize.
    Returnerar GPKG-path med den faktiska masken (alla icke-noll polygoner).
    """
    log.info("  Vektoriserar raster från VRT...")
    
    try:
        # Steg 1: Konvertera VRT till temporär GeoTIFF (kan ej skriva direkt till VRT)
        tmp_tif = work_dir / "tmp_raster.tif"
        if not tmp_tif.exists():
            log.info("    Konverterar VRT → GeoTIFF...")
            r = subprocess.run([
                "gdal_translate", "-of", "GTiff",
                str(raster_path), str(tmp_tif)
            ], capture_output=True, text=True, timeout=600)
            
            if r.returncode != 0:
                log.error("    gdal_translate misslyckades: %s", r.stderr[:200])
                return None
        
        # Steg 2: Skapa binär mask från GeoTIFF
        mask_gpkg = work_dir / "raster_mask.gpkg"
        mask_gpkg.unlink(missing_ok=True)
        
        tmp_mask_tif = work_dir / "tmp_mask.tif"
        log.info("    Skapar binär mask...")
        with rasterio.open(str(tmp_tif)) as src:
            data = src.read(1)
            profile = src.profile
            profile.update(dtype=rasterio.uint8, count=1, nodata=0)
            
            # Binär mask: 1 om data != 0
            mask_data = (data != 0).astype(np.uint8)
            
            with rasterio.open(str(tmp_mask_tif), 'w', **profile) as dst:
                dst.write(mask_data, 1)
        
        log.info("    Vektoriserar mask med gdal_polygonize...")
        # gdal_polygonize konverterar rastret till polygoner
        r = subprocess.run([
            "gdal_polygonize.py",
            str(tmp_mask_tif), "-b", "1",
            "-f", "GPKG",
            str(mask_gpkg), "mask", "value"
        ], capture_output=True, text=True, timeout=600)
        
        if r.returncode != 0:
            log.error("    gdal_polygonize misslyckades: %s", r.stderr[:300])
            return None
        
        # Steg 3: Läs mask-GPKG och filtrera på value=1 (icke-noll områden)
        log.info("    Filtrerar mask på icke-noll områden...")
        mask_gdf = gpd.read_file(str(mask_gpkg), layer='mask')
        
        if 'value' in mask_gdf.columns:
            # Behåll bara polygoner där value=1 (icke-noll)
            mask_gdf = mask_gdf[mask_gdf['value'] == 1].copy()
        
        if len(mask_gdf) == 0:
            log.error("  Ingen giltigt område i rastret!")
            return None
        
        # Union alla polygoner till en (eller behåll som multipolygon)
        merged_geom = mask_gdf.geometry.unary_union
        
        # Spara slutgiltig mask
        mask_final_gdf = gpd.GeoDataFrame(
            {'id': [1]},
            geometry=[merged_geom],
            crs='EPSG:3006'
        )
        mask_final_gdf.to_file(str(mask_gpkg), driver='GPKG', layer='mask')
        log.info("  Mask GPKG skapad från rastrets faktiska område")
        
        # Rensa temporära filer
        tmp_tif.unlink(missing_ok=True)
        tmp_mask_tif.unlink(missing_ok=True)
        
        return mask_gpkg, merged_geom
            
    except Exception as e:
        log.error("  Fel vid maskering: %s", str(e))
        import traceback
        log.debug(traceback.format_exc())
        return None


def create_mask_gpkg_from_geometry(merged_geom, output_gpkg, log):
    """
    Sparar merged geometry som GPKG.
    """
    if merged_geom is None:
        return False
        
    try:
        gdf = gpd.GeoDataFrame(
            {'id': [1]},
            geometry=[merged_geom],
            crs='EPSG:3006'
        )
        gdf.to_file(output_gpkg, driver='GPKG', layer='mask')
        log.info("  Mask-GPKG sparad: %s", output_gpkg)
        return True
    except Exception as e:
        log.error("  Fel vid sparande av mask-GPKG: %s", str(e))
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Klippning (parallell)
# ══════════════════════════════════════════════════════════════════════════════

def clip_single_gpkg(gpkg, out_dir, mask_gpkg, log):
    """
    Klipper en GPKG mot masken med ogr2ogr (snabbare än geopandas för stora filer).
    Returnerar (gpkg.name, success, elapsed_time, output_size_gb)
    """
    out_gpkg = out_dir / gpkg.name
    if out_gpkg.exists():
        try:
            return (gpkg.name, True, 0, out_gpkg.stat().st_size / 1e9)
        except:
            pass
    
    t1 = time.time()
    try:
        tmp = out_dir / (gpkg.stem + ".tmp.gpkg")
        tmp.unlink(missing_ok=True)
        
        # Använd ogr2ogr för snabb klippning
        r = subprocess.run([
            "ogr2ogr", "-f", "GPKG", "-overwrite",
            "-clipsrc", str(mask_gpkg),
            str(tmp), str(gpkg),
        ], capture_output=True, text=True, timeout=600)
        
        if r.returncode != 0:
            log.error("  ogr2ogr misslyckades för %s: %s", gpkg.name, r.stderr[:200])
            tmp.unlink(missing_ok=True)
            return (gpkg.name, False, time.time() - t1, 0)
        
        tmp.rename(out_gpkg)
        sz = out_gpkg.stat().st_size / 1e9
        elapsed = time.time() - t1
        
        return (gpkg.name, True, elapsed, sz)
    
    except Exception as e:
        log.error("  Fel vid klippning av %s: %s", gpkg.name, str(e)[:200])
        return (gpkg.name, False, time.time() - t1, 0)


# ══════════════════════════════════════════════════════════════════════════════
# Huvud
# ══════════════════════════════════════════════════════════════════════════════

def main():
    log = setup_logging(OUT_BASE)
    t0  = time.time()

    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 13: Klipp vektor till rasters giltiga dataarea")
    log.info("Källmapp : %s", OUT_BASE / "steg_12_clip_to_footprint")
    log.info("Rastermapp: %s", OUT_BASE / "steg_6_generalize/conn4")
    log.info("Utmapp   : %s", OUT_BASE / "steg_13_clip_to_raster_extent")
    log.info("══════════════════════════════════════════════════════════")

    # Verifiera källfiler
    src_dir = OUT_BASE / "steg_12_clip_to_footprint"
    if not src_dir.exists():
        log.error("steg_12_clip_to_footprint/ saknas — kör steg 12 först")
        sys.exit(1)

    raster_dir = OUT_BASE / "steg_6_generalize" / "conn4"
    raster_file = raster_dir / "_mosaic.vrt"
    if not raster_file.exists():
        log.error("Raster-VRT saknas: %s", raster_file)
        sys.exit(1)

    gpkgs = sorted(src_dir.glob("*.gpkg"))
    if not gpkgs:
        log.error("Inga GPKG-filer i %s", src_dir)
        sys.exit(1)

    out_dir = OUT_BASE / "steg_13_clip_to_raster_extent"
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = OUT_BASE / "steg_13_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Steg A: Skapa mask från raster (en gång)
    log.info("  Skapar raster-mask...")
    result = create_raster_mask_polygon(str(raster_file), work_dir, log)
    
    if result is None:
        log.error("Misslyckades att skapa mask från raster")
        sys.exit(1)
    
    mask_gpkg, mask_geom = result

    # Steg B: Klipp varje variant SEKVENTIELLT med ogr2ogr
    log.info("  Klipper %d GPKG-filer med ogr2ogr...\n", len(gpkgs))
    
    ok_count = 0
    for gpkg in gpkgs:
        out_gpkg = out_dir / gpkg.name
        if out_gpkg.exists():
            log.info("  ✓ %s — redan klar", gpkg.name)
            ok_count += 1
            continue

        log.info("  Klipper %s...", gpkg.name)
        t1 = time.time()
        
        gpkg_name, success, elapsed, sz = clip_single_gpkg(gpkg, out_dir, mask_gpkg, log)
        
        if success:
            log.info("    ✓ %.2f GB  (%.1f s)", sz, elapsed)
            ok_count += 1
        else:
            log.warning("    ✗ Misslyckades  (%.1f s)", elapsed)

    total = time.time() - t0
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 13 klart — %d/%d varianter  %.1f min", ok_count, len(gpkgs), total / 60)
    log.info("Output i %s", out_dir)
    log.info("══════════════════════════════════════════════════════════")


if __name__ == "__main__":
    main()
