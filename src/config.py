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
# QML-fil för reklassificerade tiles (steg 1 och framåt).
# Faller tillbaka på QML_SRC om filen saknas.
_RECLASSIFY_QML = Path(__file__).parent / "qml" / "steg_1_reclassify.qml"
QML_RECLASSIFY = _RECLASSIFY_QML if _RECLASSIFY_QML.exists() else QML_SRC

# Låt OUT_BASE vara konfigurerbar via miljövariabel för testa
# TODO: Ta bort miljövariabeln och hårdkoda OUT_BASE när pipeline är stabil och klar för produktion
OUT_BASE = Path(os.getenv("OUT_BASE", "/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_1proc_v03"))

# ══════════════════════════════════════════════════════════════════════════════
# TILE CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

TILE_SIZE        = 1024          # Huvudtile-storlek (pixlar per sida)
# 20% av total yta: rader 30-43 × 70 kolumner = 980 tiles
#PARENT_TILES     = [(row, col) for row in range(30, 44) for col in range(70)]
#PARENT_TILES     = [(row, col) for row in range(35) for col in range(70)]  # Norra halvan (rader 0-34)
#PARENT_TILES     = [(row, col) for row in range(7) for col in range(70)]   # 10% (rader 0-6)
PARENT_TILES     = [(0, col) for col in range(70)]                         # ~1% (rad 0, 70 tiles)
#PARENT_TILES     = [(row, col) for row in range(7) for col in range(70)]   # 10% (rader 0-6)
#PARENT_TILES     = [(row, col) for row in range(18) for col in range(70)]  # ~25% (rader 0-17, 1260 tiles)
#PARENT_TILES     = [(row, col) for row in range(70) for col in range(70)]  # 100% (alla 4900 tiles)
PARENT_TILE_SIZE = 1024          # Matchar TILE_SIZE i steg 1
SUB_TILE_SIZE    = 1024          # Sub-tile-storlek (samma som PARENT_TILE_SIZE nu)
HALO             = 100           # px – kant på varje sida vid generalisering, >= max(MMU_STEPS)

# ══════════════════════════════════════════════════════════════════════════════
# CLASSIFICATION CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

GENERALIZE_PROTECTED = {61, 62}                     # Skyddade klasser i steg 6 (generalisering): maskeras vid sieve/modal, exkluderas från areafilter. (51 borttagen — löses upp i steg 3)
SIMPLIFY_PROTECTED   = set()                       # Skyddade klasser i steg 8 (Mapshaper): förenklas aldrig (sp=1.0). (51 borttagen — löses upp i steg 3)
EXTRACT_CLASSES  = {51, 53, 61, 62}                # Klasser som extraheras separat i steg 2 (vektoriseras senare): Byggnad, Väg/järnväg, Vatten
DISSOLVE_CLASSES = {51, 53}                        # Klasser som löses upp i omgivande mark i steg 3: Byggnad + Väg/järnväg

# ══════════════════════════════════════════════════════════════════════════════
# CLASS REMAPPING — Omklassificering från NMD till slutklasser (Steg 0)
# ══════════════════════════════════════════════════════════════════════════════
# Mappning: NMD-källkod → nya slutkod för förenkling och anpassning till kravspec.
# Originalklasser sparas i separat _original_class-lager per tile.

CLASS_REMAP = {
    # Skogsklasser — sammanför fastmark och våtmark för tallskog till samma klass
    111: 101,  # Tallskog på fastmark → 101
    121: 101,  # Tallskog på våtmark → 101
    112: 102,  # Granskog på fastmark → 102
    122: 102,  # Granskog på våtmark → 102
    113: 103,  # Barrblandskog på fastmark → 103
    123: 103,  # Barrblandskog på våtmark → 103
    114: 104,  # Lövblandad barrskog på fastmark → 104
    124: 104,  # Lövblandad barrskog på våtmark → 104
    115: 105,  # Triviallövskog på fastmark → 105
    125: 105,  # Triviallövskog på våtmark → 105
    116: 106,  # Ädellövskog på fastmark → 106
    126: 106,  # Ädellövskog på våtmark → 106
    117: 107,  # Triviallövskog m. ädellövinslag på fastmark → 107
    127: 107,  # Triviallövskog m. ädellövinslag på våtmark → 107
    118: 108,  # Temporärt ej skog på fastmark → 108
    128: 108,  # Temporärt ej skog på våtmark → 108
    
    # Våtmarksklasser — grupperas till två huvudgrupper
    200: 200,  # Öppen våtmark utan underindelning → 200 (oförändrad)
    
    211: 21,   # Buskmyr → 21 (Öppen våtmark på myr)
    212: 21,   # Ristuvemyr → 21 (Öppen våtmark på myr)
    213: 21,   # Fastmattemyr, mager → 21 (Öppen våtmark på myr)
    214: 21,   # Fastmattemyr, frodig → 21 (Öppen våtmark på myr)
    215: 21,   # Sumpkärr → 21 (Öppen våtmark på myr)
    216: 21,   # Mjukmattemyr → 21 (Öppen våtmark på myr)
    217: 21,   # Lösbottenmyr → 21 (Öppen våtmark på myr)
    218: 21,   # Övrig öppen myr → 21 (Öppen våtmark på myr)
    
    221: 22,   # Våtmark med buskar → 22 (Öppen våtmark ej på myr)
    222: 22,   # Risdominerad våtmark → 22 (Öppen våtmark ej på myr)
    223: 22,   # Gräsdominerad våtmark, mager → 22 (Öppen våtmark ej på myr)
    224: 22,   # Gräsdominerad våtmark, frodvuxen → 22 (Öppen våtmark ej på myr)
    225: 22,   # Gräsdominerad våtmark, högvuxen → 22 (Öppen våtmark ej på myr)
    226: 22,   # Mossdominerad våtmark → 22 (Öppen våtmark ej på myr)
    227: 22,   # Våtmark utan växttäcke → 22 (Öppen våtmark ej på myr)
    228: 22,   # Övrig öppen våtmark → 22 (Öppen våtmark ej på myr)
    
    # Fjällskogar — sammanför fastmark och våtmark
    23: 103,   # Låg fjällskog på våtmark → 103
    43: 103,   # Låg fjällskog på fastmark → 103
    230: 103,  # Låg fjällskog på övrig våtmark → 103
    
    # Åkermark
    3: 3,      # Åkermark → 3 (ingen förändring)
    
    # Öppen mark
    411: 41,   # Öppen mark utan vegetation (ej glaciär eller varaktigt snöfält) → 41
    412: 41,   # Glaciär → 41
    413: 41,   # Varaktigt snöfält → 41
    
    4211: 421, # Torr buskdominerad mark → 421
    4212: 421, # Frisk buskdominerad mark → 421
    4213: 421, # Frisk-fuktig buskdominerad mark → 421
    
    4221: 422, # Torr risdominerad mark → 422
    4222: 422, # Frisk risdominerad mark → 422
    4223: 422, # Frisk-fuktig risdominerad mark → 422
    
    4231: 423, # Torr gräsdominerad mark → 423
    4232: 423, # Frisk gräsdominerad mark → 423
    4233: 423, # Frisk-fuktig gräsdominerad mark → 423

    # Bebyggelse och infrastruktur
    51: 51,    # Exploaterad mark, byggnad → 51 (ingen förändring)
    52: 52,    # Exploaterad mark, ej byggnad eller väg/järnväg → 52 (ingen förändring)
    53: 53,    # Exploaterad mark, väg/järnväg → 53 (ingen förändring, ingår ej)
    54: 54,    # Exploaterad mark, torvtäkt → 54 (ingen förändring)
    
    # Vatten
    61: 61,    # Sjö och vattendrag → 61 (ingen förändring)
    62: 62,    # Hav → 62 (ingen förändring)
}

# ══════════════════════════════════════════════════════════════════════════════
# GENERALIZATION PARAMETERS
# ══════════════════════════════════════════════════════════════════════════════

MMU_ISLAND   = 50               # Minsta storlek på öar innan fyllnad (px) — 0,5 ha vid 10 m upplösning

# Klasser som räknas som "omgivande yta" när små landöar ska fyllas (Steg 5)
# En ö fylls bara om ALLA dess grannar tillhör dessa klasser.
# Exempel: {61, 62} = bara sjöar/vatten; {51, 52, 53, 54, 61, 62} = vatten + vägar/byggnader
ISLAND_FILL_SURROUNDS = {61, 62}

# Sieve MMU-steg för conn4 och conn8 metoder (Steg 6)
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
MMU_STEPS    = [2, 4, 8, 16, 32, 50]

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
KERNEL_SIZES = [3, 7]

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
SIMPLIFICATION_TOLERANCES = [25]

# Förenklingsbackend för steg 8.
# "mapshaper" — Mapshaper CLI (snabb, men kraschar på filer > ~3 GB pga Node.js string-limit)
# "grass"     — GRASS v.generalize (diskbaserad, inga storleksgränser, bevarar topologi)
# "auto"      — Välj mapshaper om GeoJSON < 2 GB, annars grass
SIMPLIFY_BACKEND = "grass"

# ══════════════════════════════════════════════════════════════════════════════
# GRASS v.generalize — Algoritm och parametrar (Steg 8)
# ══════════════════════════════════════════════════════════════════════════════
#
# GRASS_SIMPLIFY_METHOD — Vilken algoritm som används:
#   "douglas"        — Douglas-Peucker. Tar bort vertexer. Dålig på raster-
#                      trappsteg (blockeras av topologikonstraints).
#   "chaiken"        — Chaikin corner-cutting. Mjukar ut rätvinkliga pixelkanter
#                      till rundade kurvor. Rätt verktyg för rasteriserade polygoner.
#   "douglas+chaiken"— Två pass: Douglas tar bort kolineära punkter först,
#                      sedan Chaikin rundar hörnen. Kombinerad effekt.
#
# GRASS_CHAIKEN_THRESHOLD — Minsta avstånd (meter) mellan punkter i Chaikin-output.
#   Lägre värde → fler punkter, slätare kurvor, större fil.
#   Rekommenderat: 5–15 m (pixelstorlek 10 m → 5 m ger ca 2 punkter/pixel).
#
# GRASS_DOUGLAS_THRESHOLD — Tolerans (meter) för Douglas-Peucker-passa.
#   Används bara vid method="douglas" eller "douglas+chaiken".
#   2 m = tar bort kolineära punkter utan att ändra formen (förpass).
#   25 m = aggressiv förenkling.
#
# Exempel:
#   GRASS_SIMPLIFY_METHOD = "chaiken"
#   GRASS_CHAIKEN_THRESHOLD = 5.0     # mjuk utjämning
#
#   GRASS_SIMPLIFY_METHOD = "douglas+chaiken"
#   GRASS_DOUGLAS_THRESHOLD = 2.0     # städa bort kolineära punkter
#   GRASS_CHAIKEN_THRESHOLD = 5.0     # runda sedan hörnen
#
GRASS_SIMPLIFY_METHOD    = "douglas"           # "douglas", "chaiken", "douglas+chaiken"
GRASS_CHAIKEN_THRESHOLD  = 10.0       # meter — Chaikin min-avstånd mellan punkter
GRASS_DOUGLAS_THRESHOLD  = 10.0       # meter — Douglas förpass (douglas+chaiken)
GRASS_SIMPLIFY_THRESHOLD = 10.0       # meter — bakåtkompatibelt (douglas-only tolerance-loop)

# GRASS_VECTOR_MEMORY — RAM som GRASS får använda för topologinätet (MB).
# Default i GRASS är ~1000 MB. Med mycket RAM: sätt högt för att hålla hela
# topologistrukturen i minnet → undviker paginering → 2–4× snabbare.
# Lämna minst 8–16 GB över till OS + övriga processer.
GRASS_VECTOR_MEMORY = 48000  # MB (48 GB av 56 GB)

# GRASS_OMP_THREADS — antal trådar för OpenMP-stödda delar i GRASS/GDAL.
# Sätts som OMP_NUM_THREADS i steg 8. Om modul saknar OpenMP ignoreras värdet.
GRASS_OMP_THREADS = 22

# GRASS_PARALLEL_GPKG — Max antal parallella GRASS-jobb (ett jobb per GPKG).
# Dela ALDRIG en GPKG — ett jobb måste alltid processera hela filen.
GRASS_PARALLEL_GPKG = 8  # begränsas automatiskt av antalet GPKGs

# GRASS_USE_TILED — Tilebaserad parallelism i steg 8.
# Delar input-GPKG:n i horisontella bands (hela tile-rader) med överlapp och kör
# GRASS parallellt på varje band. Klipps sedan tillbaka och sätts ihop.
# GRASS_TILE_ROWS        — Antal tile-rader per GRASS-chunk (1 = max parallelism).
# GRASS_TILE_ROW_OVERLAP — Extra buffert-rader ovanför/nedanför varje chunk.
GRASS_USE_TILED        = True  # True: tilebaserad parallelism; False: ett jobb per GPKG
# GRASS_USE_COMBINED_78 — Kör steg 7+8 som en enda GRASS-session (steg_78_grass.py).
# r.external → r.patch → r.to.vect → v.generalize → v.clean → v.out.ogr.
# Eliminerar topologiska sömsglapp i grunden. Steg 7 hoppas över i run_all_steps.py.
GRASS_USE_COMBINED_78  = True   # True: använd steg_78_grass.py; False: gamla steg 7+8
GRASS_TILE_ROWS        = 1     # Tile-rader per chunk
GRASS_TILE_ROW_OVERLAP = 1     # Buffert-rader (hela tile-rader) som överlapp per sida
# GRASS_MERGE_BEFORE_GENERALIZE — Ny approach: centroid-baserad extraktion i chunks (parallellt),
# sedan enskild GRASS-session med v.in.ogr × N → v.patch → v.generalize → v.clean → v.out.ogr.
# Löser topologiska glapp längs chunkgränser (generaliseringen sker på hela datasetet).
GRASS_MERGE_BEFORE_GENERALIZE = True   # True: merge-first; False: gammal per-chunk-approach
# GRASS_SNAP_TOLERANCE — Snap-tolerans (meter) i v.clean-steget efter chunk-merge.
# Används för att läka topologiska glapp längs chunkgränser som uppstår när samma
# polygon-kant generaliserats oberoende i två olika GRASS-körningar.
# Bör sättas till minst lika stort som GRASS_DOUGLAS_THRESHOLD.
GRASS_SNAP_TOLERANCE   = 0.5   # meter — ST_Buffer(+δ) på varje polygon för att stänga glapp längs chunkgränser

# ══════════════════════════════════════════════════════════════════════════════
# MORFOLOGISK UTJÄMNING — Rasterbaserad kantutjämning (Steg 6, sista pass)
# ══════════════════════════════════════════════════════════════════════════════
#
# MORPH_SMOOTH_METHOD — Metod för kantutjämning på raster INNAN polygonisering.
#   "none"         — Ingen utjämning (standard)
#   "disk_modal"   — Disk-formad majority-filter. Snabb, mjukar pixeltrappor utan
#                    att förflytta gränser mer än ~radius pixlar.
#   "closing"      — Binär morphologisk closing per klass. Fyller konkava notchar
#                    längs gränser ("pixelsteg inåt"). Gränser förflyttas max R px.
#
# MORPH_SMOOTH_RADIUS — Radie i pixlar för strukturelementet.
#   1 px = 10 m vid NMD:s 10 m upplösning.
#   Rekommenderat: 2–4 px (20–40 m).
#
# Katalog- och lagernamn encodar metod+radie automatiskt:
#   disk_modal r2 → undermapp: {method}_morph_disk_r02
#   closing    r2 → undermapp: {method}_morph_close_r02
#   Lagernamn i GPKG: markslag_morph_disk_r02 / markslag_morph_close_r02
#
MORPH_SMOOTH_METHOD = "disk_modal"  # "none", "disk_modal", "closing"
MORPH_SMOOTH_RADIUS = 2        # pixlar — 1 px = 10 m

# MORPH_ONLY — Om True: vektorisera/förenkla BARA morph-katalogerna i steg 7/8.
# Bas-metoderna (conn4 etc.) körs fortfarande i steg 6 (morph bygger på dem),
# men ingen GPKG skapas för originalet. Sparar tid och diskutrymme.
MORPH_ONLY = True

# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE CONFIGURATION — Vilka steg ska köras?
# ══════════════════════════════════════════════════════════════════════════════

ENABLE_STEPS = {
    0: True,    # Verifikation - tileluppdelning utan omklassificering (grunddata för steg 1)
    1: True,    # Tileluppdelning med omklassificering
    2: True,    # Extrahera skyddade klasser
    3: True,    # Extrahera landskapsbild
    4: False,   # Fylla små landöar < MMU_ISLAND px omringade av vatten
    5: True,    # Ta bort (filtrera) små sjöar < 0,5 ha
    6: True,    # Generalisering
    7: True,    # Vektorisering
    8: True,    # Simplifiering
    9: True,    # Overlay byggnader från steg 2 på steg 8
    99: True,   # Bygga QGIS-projekt
}

# ══════════════════════════════════════════════════════════════════════════════
# QGIS-PROJEKT — Vilka steg ska inkluderas i QGIS-projektet?
# ══════════════════════════════════════════════════════════════════════════════
# Steg med mycket data (steg 0-5: 980 rasterfiler/steg) kan göra QGIS trögstartat.
# Sätt False för steg du inte behöver granska i QGIS.
#
QGIS_INCLUDE_STEPS = {
    0: True,   # Verifieringstiles (original, 980 rasterfiler)
    1: True,   # Tiles med omklassificering (980 rasterfiler)
    2: True,  # Extraherade skyddade klasser (980 rasterfiler)
    3: True,   # Upplöst landskapsbild (980 rasterfiler)
    4: False,   # Fyllda sjöar (980 rasterfiler)
    5: True,   # Fyllda öar (980 rasterfiler)
    6: True,    # Generaliserat raster (steg6_generalized_*/)
    7: False,    # Vektoriserade GeoPackage
    8: True,    # Förenklat (Mapshaper)
    9: True,    # Med byggnader
}

# ══════════════════════════════════════════════════════════════════════════════
# GENERALIZATION METHODS — Vilka metoder i Steg 6 ska köras?
# ══════════════════════════════════════════════════════════════════════════════
# Möjliga metoder: "conn4", "conn8", "modal", "semantic"
# Steg 7 och 8 kör automatiskt samma metoder som här är aktiverade
#
# ─── conn4 och conn8 (sieve-baserade metoder) ────────────────────────────────
# Sieve-algoritm: tar bort sammanhängande pixelgrupper (patches) som är
# mindre än MMU-värdet och ersätter dem med den dominerande grannklassen.
#
#   conn4 — 4-konnektivitet (upp/ned/vänster/höger)
#     + Mer konservativ: diagonalt rörande patches anses separata
#     + Ger skarpare och mer "rätvinkliga" gränser
#     - Kan lämna kvar fler isolerade 1-px punkter i diagonalriktning
#
#   conn8 — 8-konnektivitet (alla 8 grannpixlar)
#     + Mer aggressiv: diagonalt rörande patches slås ihop
#     + Rensar ut "pepparkornsmönster" bättre
#     - Kan slå ihop patches som borde vara separata (t.ex. tunna landryggar)
#
#   Styrs av MMU_STEPS (se ovan). Samma lista gäller för conn4 och conn8.
#
# ─── modal (majoritetsfilter) ────────────────────────────────────────────────
# Ersätter varje pixel med den vanligaste klassen i ett k×k pixelfönster
# (majority voting / moving window).
#
#   + Mjukar ut gränser och brus utan att förstöra stora sammanhängande ytor
#   + Bra för att eliminera "salt-and-pepper"-brus
#   - Rundar av skarpa hörn och smala strukturer (t.ex. vägkorridorer)
#   - Kan förskjuta klassgränser upp till k/2 pixlar
#
#   Styrs av KERNEL_SIZES (se ovan). k=3 = liten fönster, k=7 = större fönster.
#
# ─── semantic (semantisk eliminering) ────────────────────────────────────────
# Slår ihop små patches med sin semantiskt *närmaste* grannpatch, baserat på
# NMD:s marktäckehierarki — inte bara den geometriskt störst grann.
#
# Semantisk gruppering via nmd_group():
#   v < 10    → grupp = v itself    (t.ex. 3 = Åkermark → grupp 3)
#   v < 100   → grupp = v // 10     (t.ex. 23,43,51–54,61–62)
#   v < 1000  → grupp = v // 100    (t.ex. 111–128, 200–228, 411)
#   v >= 1000 → grupp = v // 1000   (t.ex. 4211–4233)
#
#   Faktiska grupper med verkliga NMD2023-klasser:
#   Grupp 1 = Skog         (111–128: all skog på fastmark och våtmark)
#   Grupp 2 = Våtmark      (200–228: öppen och trädklädd våtmark; 23: låg fjällskog på våtmark)
#   Grupp 3 = Åkermark     (3: åkermark)
#   Grupp 4 = Öppen mark   (411: öppen fastmark; 4211–4233: busk/ris/gräsmark; 43: låg fjällskog fastmark)
#   Grupp 5 = Bebyggd/infra (51: byggnad; 52: anlagd mark; 53: väg/järnväg; 54: torvtäkt)
#   Grupp 6 = Vatten       (61: inlandsvatten; 62: hav)
#
#   Distanstabell (lägre = mer lika):
#     Våtmark–Öppen mark:  1  (närmast — fuktiga och öppna marker likartade)
#     Skog–Våtmark:        2  Åkermark–Våtmark:        2
#     Skog–Åkermark:       3  Skog–Öppen mark:         3
#     Våtmark–Bebyggd:     3  Öppen mark–Bebyggd:      3
#     Skog–Bebyggd:        4  Åkermark–Bebyggd:        4
#     Åkermark–Vatten:     4  Våtmark–Vatten:          4
#     Öppen mark–Vatten:   4  Bebyggd–Vatten:          4
#     Skog–Vatten:         5  (mest olika)
#
#   Algoritm (heapq-baserat greedy merge):
#     1. Bygg upp alla 4-konnekterade patches och deras grannar
#     2. Lägg alla patches < MMU i en min-heap (minst patch först)
#     3. Slå ihop varje liten patch med den granne som har lägst sem_dist
#        (vid lika distans väljs den *största* grannen)
#     4. Upprepa tills inga patches < MMU finns kvar
#     5. Skyddade klasser {51,52,53,54,61,62} ändras aldrig
#
#   + Bevarar semantisk konsekvens bättre än ren sieve:
#     t.ex. en liten öppen mark (gr.4) bredvid skog (gr.1) och våtmark (gr.2)
#     slås ihop med våtmark (dist=1) istället för skog (dist=3)
#   + Lämpar sig bra för klassbaserade analyser och legend-renhet
#   - Långsammare än conn4/conn8 (O(n log n) per MMU-steg)
#   - Kan ge oväntade resultat om semantisk granntabell inte stämmer med
#     den faktiska markanvändningskontexten i just detta område
#
#   Styrs av MMU_STEPS (samma lista som för conn4/conn8).
#
# Exempel:
#   GENERALIZATION_METHODS = {"conn4", "conn8", "modal"}  # Skippa semantic
#   eller
#   GENERALIZATION_METHODS = {"conn4", "conn8"}            # Bara sieve-metoder
#

GENERALIZATION_METHODS = {"conn4"}

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
