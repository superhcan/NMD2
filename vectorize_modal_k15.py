"""
vectorize_modal_k15.py — Vektoriserar modal k15-outputen till GeoPackage.

Använder rasterio.features.shapes för polygonisering och fiona för skrivning.
Varje sammanhängande patch → ett polygon med attributet 'klass' (NMD-klasskod).
"""

import time
from pathlib import Path

import fiona
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape, mapping
from shapely.validation import make_valid

# ── Inställningar ─────────────────────────────────────────────────────────────
SRC_TIF = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/generalized_test_modal/NMD2023bas_tile_r000_c010_modal_k15.tif")
OUT_DIR = SRC_TIF.parent
OUT_GPKG = OUT_DIR / "NMD2023bas_tile_r000_c010_modal_k15.gpkg"
LAYER   = "markslag"
# ──────────────────────────────────────────────────────────────────────────────

t0 = time.time()
print(f"Läser  : {SRC_TIF.name}")

with rasterio.open(SRC_TIF) as src:
    data = src.read(1)
    crs  = src.crs
    transform = src.transform

# Polygonisera: shapes() ger (geojson-geom, pixelvärde) per patch
# Maskera bort bakgrund (0)
mask = (data > 0).astype(np.uint8)

print(f"CRS    : {crs}")
print(f"Pixlar : {data.shape[1]}×{data.shape[0]}  ({mask.sum():,} aktiva)")
print("Polygoniserar … ", end="", flush=True)

t1 = time.time()
polys = list(shapes(data, mask=mask, transform=transform))
t2 = time.time()
print(f"{len(polys):,} polygoner  ({t2-t1:.1f}s)")

# Skriv GeoPackage
schema = {
    "geometry": "Polygon",
    "properties": {"klass": "int"},
}

print(f"Skriver → {OUT_GPKG.name} … ", end="", flush=True)

with fiona.open(
    OUT_GPKG,
    "w",
    driver="GPKG",
    crs=crs.to_epsg() and f"EPSG:{crs.to_epsg()}" or crs.to_wkt(),
    schema=schema,
    layer=LAYER,
) as dst:
    for geom, val in polys:
        val = int(val)
        if val == 0:
            continue
        geom_valid = make_valid(shape(geom))
        dst.write({
            "geometry": mapping(geom_valid),
            "properties": {"klass": val},
        })

elapsed = time.time() - t0
print(f"klar ({elapsed:.1f}s)")
print(f"\nUtdata : {OUT_GPKG}")
print(f"Lager  : {LAYER}  (attribut: klass)")
