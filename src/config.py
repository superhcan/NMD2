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

# Sieve MMU-steg för conn4 och conn8 metoder
# Större värden = mer generalisering
# Exempel:
#   MMU_STEPS = [2, 4, 8]              # Snabb test (3 nivåer)
#   MMU_STEPS = [2, 4, 8, 16, 32, 64, 100]  # Full upplösning (7 nivåer)
#
MMU_STEPS    = [2, 4, 8, 16, 32, 64, 100]

# Kernel-storlekar för modal filter
# Större värden = mer generalisering, mindre detalj
# Exempel:
#   KERNEL_SIZES = [3, 7, 13]           # Snabb test (3 nivåer)
#   KERNEL_SIZES = [3, 5, 7, 11, 13, 15]  # Full upplösning (6 nivåer)
#
KERNEL_SIZES = [3, 5, 7, 11, 13, 15]
# Värden mellan 0-100 för procentuell förenkling av removable vertices
# Lägre = mer förenkling, högre = mindre förenkling (mer detalj)
#
SIMPLIFICATION_TOLERANCES = [90, 75, 50, 25, 15]

# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE CONFIGURATION — Vilka steg ska köras?
# ══════════════════════════════════════════════════════════════════════════════

ENABLE_STEPS = {
    1: False,   # Tileluppdelning (hoppa över - tiles finns redan)
    2: True,    # Extrahera skyddade klasser
    3: True,    # Extrahera landskapsbild
    4: True,    # Ta bort små sjöar < 1 ha
    5: True,    # Fylla små öar < 1 ha omringade av vatten
    6: True,    # Generalisering
    7: True,    # Vektorisering
    8: True,    # Mapshaper-förenkling
    9: True,    # Bygga QGIS-projekt
}

# ══════════════════════════════════════════════════════════════════════════════
# GENERALIZATION METHODS — Vilka metoder i Steg 6 ska köras?
# ══════════════════════════════════════════════════════════════════════════════
# Möjliga metoder: "conn4", "conn8", "modal", "semantic"
# Steg 7 och 8 kör automatiskt samma metoder som här är aktiverade
# 
# Exempel:
#   GENERALIZATION_METHODS = {"conn4", "conn8", "modal"}  # Skippa semantic
#   eller
#   GENERALIZATION_METHODS = {"conn4", "conn8"}            # Bara sieve-metoder
#

GENERALIZATION_METHODS = {"conn4", "modal"}  # Test: endast conn4 och modal

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
