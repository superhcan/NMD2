"""
config.py — Centraliserade inställningar för NMD2 pipeline.

Denna fil innehåller alla konstanter, paths, och parametrar som används
av de olika pipelinestegen.
"""

from pathlib import Path
import os
import numpy as np

# ══════════════════════════════════════════════════════════════════════════════
# PATHS
# ══════════════════════════════════════════════════════════════════════════════

SRC     = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/NMD2023bas_v2_0.tif")
QML_SRC = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/NMD2023bas_v2_0.qml")

# Låt OUT_BASE vara konfigurerbar via miljövariabel för testa
OUT_BASE = Path(os.getenv("OUT_BASE", "/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v7"))

# ══════════════════════════════════════════════════════════════════════════════
# TILE CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

TILE_SIZE        = 1024          # Huvudtile-storlek (pixlar per sida)
PARENT_TILES     = [(0, 19), (0, 20), (1, 19), (1, 20)]
PARENT_TILE_SIZE = 1024          # Matchar TILE_SIZE i steg 1
SUB_TILE_SIZE    = 1024          # Sub-tile-storlek (samma som PARENT_TILE_SIZE nu)
HALO             = 100           # px – kant på varje sida vid generalisering, >= max(MMU_STEPS)

# ══════════════════════════════════════════════════════════════════════════════
# CLASSIFICATION CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

PROTECTED      = {51, 52, 53, 54, 61, 62}       # Skyddade klasser
WATER_CLASSES  = {61, 62}                        # Vatten (för öfyllnad)
ROADS_BUILDINGS = {51, 53}                       # Väg/järnväg och byggnader (för replace_roads_buildings)

# ══════════════════════════════════════════════════════════════════════════════
# GENERALIZATION PARAMETERS
# ══════════════════════════════════════════════════════════════════════════════

MMU_ISLAND   = 100              # Minsta storlek på öar innan fyllnad (px)
MMU_STEPS    = [2, 4, 8, 16, 32, 64, 100]   # Sieve MMU:er (px)
KERNEL_SIZES = [3, 5, 7, 11, 13, 15]        # Modal filter kernelstorlekar

# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE CONFIGURATION — Vilka steg ska köras?
# ══════════════════════════════════════════════════════════════════════════════

ENABLE_STEPS = {
    1: False,   # Tileluppdelning (hoppa över - tiles finns redan)
    2: True,    # Extrahera skyddade klasser
    3: True,    # Extrahera landskapsbild
    4: True,    # Ta bort små områden (GDAL sieve)
    5: True,    # Generalisering
    6: True,    # Vektorisering
    7: True,    # Mapshaper-förenkling
    8: True,    # Bygga QGIS-projekt
}

# ══════════════════════════════════════════════════════════════════════════════
# GDAL & RASTERIO SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

COMPRESS   = "lzw"          # GeoTIFF kompression
NODATA_TMP = 65535          # Temporär nodata-värde för sieve-masking

# ══════════════════════════════════════════════════════════════════════════════
# STRUCTURAL ELEMENTS
# ══════════════════════════════════════════════════════════════════════════════

STRUCT_4 = np.array([[0, 1, 0],
                     [1, 1, 1],
                     [0, 1, 0]], dtype=bool)  # 4-connected

STRUCT_8 = np.array([[1, 1, 1],
                     [1, 1, 1],
                     [1, 1, 1]], dtype=bool)  # 8-connected
