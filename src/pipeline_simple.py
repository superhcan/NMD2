#!/usr/bin/env python3
"""
pipeline_simple.py — Simplified version using the new QGIS project builder.
Just focuses on running the pipeline and creating a basic QGIS project.
"""

import sys
import time
import logging
import subprocess
from pathlib import Path
from datetime import datetime

# Add src directory
sys.path.insert(0, str(Path(__file__).parent))

from pipeline_1024_halo import (
    step1_split, step2_extract_protected, step3_extract_landscape,
    step4_fill, step5_sieve_halo, step5_modal_halo, step5_semantic_halo,
    OUT_BASE, _setup_logging
)
from qgis_project_builder_v4 import create_pipeline_project
from simplify_mapshaper import simplify_with_mapshaper

# Setup logging
_setup_logging(OUT_BASE)
info = logging.getLogger("pipeline.summary")
log = logging.getLogger("pipeline.debug")

print(f"🚀 Starting NMD2 Pipeline (Simplified)")
print(f"📁 Output: {OUT_BASE}")

project_builder = create_pipeline_project(OUT_BASE)

t_total = time.time()
ts_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

info.info("Pipeline startat %s", ts_start)

# Step 1: Split tiles
info.info("\nStep 1: Split tiles")
tile_paths = step1_split()
project_builder.add_step_group(1, "Split Tiles")
for tile in tile_paths[:5]:  # Add first 5 tiles only
    project_builder.add_raster_layer(tile, tile.stem, opacity=0.7)
project_builder.pop_subgroup()
project_builder.save()

# Step 2: Extract protected classes
info.info("\nStep 2: Extract protected classes")
protected_paths = step2_extract_protected(tile_paths)
project_builder.add_step_group(2, "Protected Classes")
for tile in protected_paths[:5]:
    project_builder.add_raster_layer(tile, tile.stem + "_prot", opacity=0.7)
project_builder.pop_subgroup()
project_builder.save()

# Step 3: Extract landscape
info.info("\nStep 3: Extract landscape")
landscape_paths = step3_extract_landscape(tile_paths)
project_builder.add_step_group(3, "Landscape Extract")
for tile in landscape_paths[:5]:
    project_builder.add_raster_layer(tile, tile.stem + "_land", opacity=0.7)
project_builder.pop_subgroup()
project_builder.save()

# Step 4: Fill islands
info.info("\nStep 4: Fill islands")
filled_paths = step4_fill(tile_paths)
project_builder.add_step_group(4, "Fill Islands")
for tile in filled_paths[:3]:
    project_builder.add_raster_layer(tile, tile.stem + "_filled", opacity=0.7)
project_builder.pop_subgroup()
project_builder.save()

# Step 5: Generalization
info.info("\nStep 5: Generalization")
project_builder.add_step_group(5, "Generalized")

# Run all generalization methods
step5_sieve_halo(tile_paths, filled_paths, conn=4)
step5_sieve_halo(tile_paths, filled_paths, conn=8)
step5_modal_halo(tile_paths, filled_paths)
step5_semantic_halo(tile_paths, filled_paths)

# Add sample generalized results - Modal
modal_dir = OUT_BASE / "generalized_modal"
if modal_dir.exists():
    project_builder.add_method_subgroup("Modal Filter")
    for tif in sorted(modal_dir.glob("*_modal_k15.tif"))[:2]:
        project_builder.add_raster_layer(tif, tif.stem, opacity=0.6)
    project_builder.pop_subgroup()

project_builder.pop_subgroup()  # Pop Step 5
project_builder.save()

# Step 6: Vectorization (add group structure first)
info.info("\nStep 6: Vectorization of generalized results")
vectorized_dir = OUT_BASE / "vectorized"
vectorized_dir.mkdir(parents=True, exist_ok=True)

project_builder.add_step_group(6, "Vectorized")
project_builder.save()  # Save with Step 6 group added

# Step 7: Mapshaper simplification (add group structure first)
info.info("\nStep 7: Mapshaper topology-preserving simplification")
simplified_dir = OUT_BASE / "simplified"
simplified_dir.mkdir(parents=True, exist_ok=True)

project_builder.add_step_group(7, "Simplified (Mapshaper)")
project_builder.save()  # Save with Step 7 group added

# Now run the actual vectorization and simplification (long-running operations)
info.info("  Running vectorization...")

# Vectorize modal_k15 results
modal_dir = OUT_BASE / "generalized_modal"
if modal_dir.exists():
    modal_k15_tifs = sorted(modal_dir.glob("*_modal_k15.tif"))
    if modal_k15_tifs:
        vrt_file = vectorized_dir / "modal_k15_mosaic.vrt"
        gpkg_file = vectorized_dir / "modal_k15_generalized.gpkg"
        
        # Build VRT from k15 results
        vrt_cmd = ["gdalbuildvrt", "-overwrite", str(vrt_file)] + [str(t) for t in modal_k15_tifs]
        result = subprocess.run(vrt_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            info.info("  VRT built: %s", vrt_file.name)
            
            # Vectorize VRT
            poly_cmd = [
                "gdal_polygonize.py",
                str(vrt_file),
                "-f", "GPKG",
                str(gpkg_file),
                "DN", "markslag"
            ]
            result = subprocess.run(poly_cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                info.info("  Vectorized GPKG: %s", gpkg_file.name)
                # Move back one level to add to Step 6
                project_builder.add_vector_layer(gpkg_file, "Modal K15 Vectorized", "markslag")
            else:
                info.warning("  Vectorization failed: %s", result.stderr[:200])

# Move back to Step 6 completion
project_builder.pop_subgroup()
project_builder.save()

# Now run mapshaper (also long-running)
info.info("  Running Mapshaper...")

# If we have vectorized data, simplify it
if (vectorized_dir / "modal_k15_generalized.gpkg").exists():
    try:
        simplify_with_mapshaper(
            vectorized_dir / "modal_k15_generalized.gpkg",
            simplified_dir,
            tolerances=[90, 75, 50, 25]
        )
        
        # Add simplified results to QGIS project
        for pct in [90, 75, 50, 25]:
            output_file = simplified_dir / f"temp_input_p{pct}.gpkg"
            if output_file.exists():
                project_builder.add_method_subgroup(f"p{pct}% simplification")
                project_builder.add_vector_layer(output_file, f"Simplified p{pct}%", "markslag")
                project_builder.pop_subgroup()
        
        info.info("  Mapshaper simplification completed")
    except Exception as e:
        info.warning("  Mapshaper simplification failed: %s", str(e))

# Close Step 7 group and save final project
project_builder.pop_subgroup()
project_builder.save()

elapsed = time.time() - t_total
info.info("\nPipeline KLAR  totaltid: %.0fs (%.1f min)", elapsed, elapsed / 60)
info.info("QGIS-projekt: %s", project_builder.project_path)

project_builder.cleanup()

print(f"\n✅ Pipeline completed in {elapsed:.0f}s ({elapsed/60:.1f} min)")
print(f"📁 QGIS project: {project_builder.project_path}")
print(f"📁 QGIS project: {project_builder.project_path}")
