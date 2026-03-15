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

# Sieve MMU-steg för conn4 och conn8 metoder (Steg 6a & 6b)
# ═════════════════════════════════════════════════════════════════════════════
# MMU = Minimum Mapping Unit i pixlar för sieve-filtren (conn4 och conn8).
#
# Teknisk förklaring:
#   - Pixelgrupper mindre än MMU-värde blir bort-sievade (sållas ut)
#   - Större MMU = mer generalisering = färre små detaljer
#   - Mindre MMU = mindre generalisering = mer original detalj
#
# Effekt på output:
#   MMU=2:   Nästan original, mycket liten förenkling (detaljer bevarade)
#   MMU=8:   Liten-medium förenkling (några små bitar försvinner)
#   MMU=16:  Medium-stark förenkling (märkbar förenkling visas)
#   MMU=32:  Stark förenkling (många små detaljer försvinner)
#   MMU=64:  Mycket stark förenkling (bara större områden kvar)
#   MMU=100: Extrem förenkling (bara mycket stora områden kvar)
#
# Filstorlek-päverkan (ca guide för steg 7 vectorizer output):
#   MMU=2:    ~100% (baseline)
#   MMU=8:    ~90-95% (små minskning)
#   MMU=16:   ~80-85%
#   MMU=32:   ~60-70%
#   MMU=64:   ~40-50%
#   MMU=100:  ~20-30%
#
# Praktiska val:
#   Snabb test (3 steg, ~40% snabbare):
#     MMU_STEPS = [2, 8, 32]
#
#   Standard (7 steg, rekommenderat):
#     MMU_STEPS = [2, 4, 8, 16, 32, 64, 100]
#
#   Detaljerad analys (9 steg, långsamt men många värdepunkter):
#     MMU_STEPS = [1, 2, 4, 8, 16, 32, 64, 100, 128]
#
# Tips:
#   - Första värdet bör oftast vara 2-4 px (annars för lite förenkling)
#   - Sista värdet bör förenligt med `HALO` för att undvika edge-artefakter
#   - Fler steg = längre körtid men bättre för att jämföra resultat
#
MMU_STEPS    = [2, 4, 8, 16, 32, 64, 100]

# Kernel-storlekar för modal filter (Steg 6c)
# ═════════════════════════════════════════════════════════════════════════════
# k-värde för modal filter genomför "majority voting" över ett k×k pixelfönster.
#
# Teknisk förklaring:
#   - Större k = större fönster = mer generalisering
#   - Mindre k = mindre fönster = mindre generalisering
#   - Algoritm: Ersätt pixel med vanligaste värde i k×k område
#
# Effekt på output:
#   k=3:   Minimal generalisering, nästan original (små brus-borttagning)
#   k=5:   Liten förenkling (små detaljer börjar försvinna)
#   k=7:   Medium generalisering (märkbar förenkling visas)
#   k=9:   Medium-stark generalisering
#   k=11:  Stark generalisering (många små områden borta)
#   k=13:  Mycket stark generalisering
#   k=15:  Extrem generalisering (mycket få smådetaljer kvar)
#
# Filstorlek-påverkan (ca guide för steg 7 vectorizer output):
#   k=3:    ~100% (baseline)
#   k=5:    ~95-98%
#   k=7:    ~90-95%
#   k=9:    ~85-90%
#   k=11:   ~75-85%
#   k=13:   ~60-75%
#   k=15:   ~50-65%
#
# Praktiska val:
#   Snabb test (3 steg, ~50% snabbare):
#     KERNEL_SIZES = [3, 7, 13]
#
#   Standard (6 steg, rekommenderat):
#     KERNEL_SIZES = [3, 5, 7, 11, 13, 15]
#
#   Detaljerad analys (9 steg, långsamt men många värdepunkter):
#     KERNEL_SIZES = [3, 5, 7, 9, 11, 13, 15, 17, 19]
#
# Tips:
#   - Börja med k=3 eller k=5 för att behålla mestadels original detalj
#   - ODD mängd är standard (3, 5, 7, 9, 11, ...) för symmetrisk pixel-fönstring
#   - Större kernel = längre körtid (ungefär kvadratisk komplexitet)
#   - Kernel måste pågå helt inom tile + HALO område
#   - Begränsning: k≤(2*HALO+1) för att undvika edge-artefakter
#
KERNEL_SIZES = [3, 5, 7, 11, 13, 15]

# Mapshaper Simplification Tolerances (Steg 8)
# ═══════════════════════════════════════════════════════════════════════════════
# Dessa värden styr hur aggressiv vertex-förenkling ska vara i Mapshaper.
# 
# Teknisk förklaring:
#   - Mapshaper behåller percentage% av "removable vertices"
#   - Högre värde (ex. p90) = behåller MER detalj = mindre förenkling
#   - Lägre värde (ex. p15) = behåller MINDRE detalj = mer förenkling
#
# VIKTIGT: Dessa är INTE samma som "simplification level 90%" - det är tvärtom!
#   p90  = behåll 90% av removable vertices → minimal förenkling
#   p50  = behåll 50% av removable vertices → medium förenkling
#   p15  = behåll 15% av removable vertices → aggressiv förenkling
#
# Praktiska effekter:
#   p90-p75: Nästan original geometri + små förbättringar (filstorlek -10-20%)
#   p50:     Medium kompromiss (filstorlek -40-50%)
#   p25-p15: Starkt förenklad (filstorlek -70-80%)
#   p5:      Extrem förenkling (filstorlek -90%+)
#
# Exempel:
#   SIMPLIFICATION_TOLERANCES = [90, 50, 15]      # 3 nivåer - snabb test
#   SIMPLIFICATION_TOLERANCES = [90, 75, 50, 25, 15]  # 5 nivåer - standard
#   SIMPLIFICATION_TOLERANCES = [95, 85, 70, 50, 30, 10]  # 6 nivåer - detaljerad
#
# Tips:
#   - Använd p90-p75 för presentationskvalitet
#   - Använd p50 för webb-kartor
#   - Använd p15-p5 för extrem förenkling (lätta filer)
#   - Fler nivåer = längre körtid men bättre att jämföra resultat
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
