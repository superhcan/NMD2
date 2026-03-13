#!/usr/bin/env python3
"""Single file dissolve + simplify for testing."""
import geopandas as gpd
import logging
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

gpkg_path = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/vectorized/generalized_modal_k15.gpkg")

log.info("Läser: %s", gpkg_path.name)
gdf = gpd.read_file(gpkg_path)
orig_count = len(gdf)
orig_size = gpkg_path.stat().st_size / 1e6
log.info("  Original: %d polygoner, %.1f MB", orig_count, orig_size)

log.info("  Dissolving per markslag...")
gdf_dissolved = gdf.dissolve(by='markslag', as_index=False)
log.info("  Efter dissolve: %d polygoner", len(gdf_dissolved))

log.info("  Simplifying (25m tolerance, preserve_topology)...")
gdf_dissolved['geometry'] = gdf_dissolved.geometry.simplify(25, preserve_topology=True)

out_path = gpkg_path.parent / (gpkg_path.stem + "_smooth.gpkg")
if out_path.exists():
    out_path.unlink()

log.info("  Sparar: %s", out_path.name)
gdf_dissolved.to_file(out_path, driver="GPKG", layer="markslag")

final_size = out_path.stat().st_size / 1e6
reduction = (1 - final_size / orig_size) * 100
log.info("  ✓ Klart: %d polygoner, %.1f MB (%.0f%% mindre)", len(gdf_dissolved), final_size, reduction)
log.info("\nJämför: original vs smooth i QGIS!")
