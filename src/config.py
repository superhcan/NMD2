"""
config.py — Centraliserade inställningar för NMD2 pipeline.

Denna fil innehåller alla konstanter, paths, och parametrar som används
av de olika pipelinestegen.
"""

from pathlib import Path
import os
import numpy as np

# ══════════════════════════════════════════════════════════════════════════════
# SÖKVÄGAR
# ══════════════════════════════════════════════════════════════════════════════

#SRC     = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/NMD2023bas_v2_0.tif")
#QML_SRC = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/NMD2023bas_v2_0.qml")
SRC     = Path("/home/hcn/NMD_workspace/NMD2018_basskikt_ogeneraliserad_Sverige_v1_1/2018_clipped.tif")
#QML_SRC = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_1/NMD2023bas_v2_1.qml")
QML_SRC = Path("/home/hcn/NMD_workspace/NMD2018_basskikt_ogeneraliserad_Sverige_v1_1/nmd2018bas_ogeneraliserad_v1_1.qml")

# ══════════════════════════════════════════════════════════════════════════════
# QML — Stilfiler (färgpaletter)
# ══════════════════════════════════════════════════════════════════════════════
# QML_SRC — Färgpalett för det ursprungliga källrastret (används som reserv om andra saknas)
# QML_RECLASSIFY — Omklassificerad färgpalett, används i steg 1 och framåt
# Båda bör ligga i basskiktskatalogen för konsistens

QML_RECLASSIFY = Path("/home/hcn/NMD_workspace/NMD2018_basskikt_ogeneraliserad_Sverige_v1_1/nmd2018_reclassified.qml")

# FOOTPRINT_GPKG — GPKG med täckningsyta för klippning i steg 12 (lager: FOOTPRINT_LAYER)
FOOTPRINT_GPKG  = Path("/home/hcn/NMD_workspace/NMD2018_basskikt_ogeneraliserad_Sverige_v1_1/2018_mask__vectorized.gpkg")
FOOTPRINT_LAYER = "2018_mask__vectorized"

#OUT_BASE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_1/prod_100proc_v03")
OUT_BASE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_1/fjall_2018_verifiering_v01")


# ══════════════════════════════════════════════════════════════════════════════
# TILE-KONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

TILE_SIZE        = 2048          # Huvudtile-storlek (pixlar per sida)
# Vid 2048 px: 35 kolumner × 78 rader = 2730 tiles totalt (71273×157991 px källraster v2.1)
# NMD 2018 clipped: 26 kolumner × 45 rader = 1170 tiles totalt (52805×91800 px)
#PARENT_TILES     = [(r, c) for r in range(39) for c in range(35)]  # rad 43–44 × kol 16–17 = 4 tiles
#PARENT_TILES     = [(r, c) for r in range(78) for c in range(35)]  # 100% av landet
PARENT_TILES     = [(r, c) for r in range(45) for c in range(26)]  # NMD 2018 clipped (1170 tiles)
#PARENT_TILES     = [(r, c) for r in range(43,50) for c in range(35)]  # 30 rader × 35 kol = 1050 tiles (3 chunks à 13+13+4)

# Hela landet: [(r, c) for r in range(78) for c in range(35)]
# 50 %: [(r, c) for r in range(39) for c in range(35)]
# 25 %: [(r, c) for r in range(20) for c in range(35)]
# 5 %:  [(r, c) for r in range(4)  for c in range(35)]
# 1 %:  [(r, c) for r in range(1)  for c in range(35)]
HALO             = 100           # px – kant på varje sida vid generalisering, >= max(MMU_STEPS)

# ══════════════════════════════════════════════════════════════════════════════
# KLASSIFICERINGSKONSTANTER
# ══════════════════════════════════════════════════════════════════════════════

GENERALIZE_PROTECTED = {61, 62}                     # Skyddade klasser i steg 6 (generalisering): maskeras vid sieve/majority, exkluderas från areafilter.
EXTRACT_CLASSES  = {51, 53, 61, 62}                # Klasser som extraheras separat i steg 2 (vektoriseras senare): Byggnad, Väg/järnväg, Vatten
DISSOLVE_CLASSES      = {53}        # Klasser som ersätts med närmaste omgivande klass i steg 3 (distance-transform fill)
DISSOLVE_EMPTY_CLASSES = {}  # Klasser som lämnas tomma (sätts till 0) i steg 3 — ersätts EJ av omgivande mark
DISSOLVE_MAX_DIST = 0              # px — 0 = obegränsad fill (klassiskt beteende)

# ══════════════════════════════════════════════════════════════════════════════
# CLASS REMAPPING — Omklassificering från NMD till slutklasser (Steg 0)
# ══════════════════════════════════════════════════════════════════════════════
# Mappning: NMD-källkod → nya slutkod för förenkling och anpassning till kravspec.
# Originalklasser sparas i separat _original_class-lager per tile.

# CLASS_REMAP = {
#     # Skogsklasser — sammanför fastmark och våtmark för tallskog till samma klass
#     111: 101,  # Tallskog på fastmark → 101
#     121: 101,  # Tallskog på våtmark → 101
#     112: 102,  # Granskog på fastmark → 102
#     122: 102,  # Granskog på våtmark → 102
#     113: 103,  # Barrblandskog på fastmark → 103
#     123: 103,  # Barrblandskog på våtmark → 103
#     114: 104,  # Lövblandad barrskog på fastmark → 104
#     124: 104,  # Lövblandad barrskog på våtmark → 104
#     115: 105,  # Triviallövskog på fastmark → 105
#     125: 105,  # Triviallövskog på våtmark → 105
#     116: 106,  # Ädellövskog på fastmark → 106
#     126: 106,  # Ädellövskog på våtmark → 106
#     117: 107,  # Triviallövskog m. ädellövinslag på fastmark → 107
#     127: 107,  # Triviallövskog m. ädellövinslag på våtmark → 107
#     118: 108,  # Temporärt ej skog på fastmark → 108
#     128: 108,  # Temporärt ej skog på våtmark → 108
    
#     # Våtmarksklasser — grupperas till två huvudgrupper
#     200: 200,  # Öppen våtmark utan underindelning → 200 (oförändrad)
    
#     211: 21,   # Buskmyr → 21 (Öppen våtmark på myr)
#     212: 21,   # Ristuvemyr → 21 (Öppen våtmark på myr)
#     213: 21,   # Fastmattemyr, mager → 21 (Öppen våtmark på myr)
#     214: 21,   # Fastmattemyr, frodig → 21 (Öppen våtmark på myr)
#     215: 21,   # Sumpkärr → 21 (Öppen våtmark på myr)
#     216: 21,   # Mjukmattemyr → 21 (Öppen våtmark på myr)
#     217: 21,   # Lösbottenmyr → 21 (Öppen våtmark på myr)
#     218: 21,   # Övrig öppen myr → 21 (Öppen våtmark på myr)
    
#     221: 22,   # Våtmark med buskar → 22 (Öppen våtmark ej på myr)
#     222: 22,   # Risdominerad våtmark → 22 (Öppen våtmark ej på myr)
#     223: 22,   # Gräsdominerad våtmark, mager → 22 (Öppen våtmark ej på myr)
#     224: 22,   # Gräsdominerad våtmark, frodvuxen → 22 (Öppen våtmark ej på myr)
#     225: 22,   # Gräsdominerad våtmark, högvuxen → 22 (Öppen våtmark ej på myr)
#     226: 22,   # Mossdominerad våtmark → 22 (Öppen våtmark ej på myr)
#     227: 22,   # Våtmark utan växttäcke → 22 (Öppen våtmark ej på myr)
#     228: 22,   # Övrig öppen våtmark → 22 (Öppen våtmark ej på myr)
    
#     # Fjällskogar — sammanför fastmark och våtmark
#     23: 109,   # Låg fjällskog på våtmark → 109
#     43: 109,   # Låg fjällskog på fastmark → 109
#     230: 109,  # Låg fjällskog på övrig våtmark → 109
    
#     # Åkermark
#     3: 3,      # Åkermark → 3 (ingen förändring)
    
#     # Öppen mark
#     411: 41,   # Öppen mark utan vegetation (ej glaciär eller varaktigt snöfält) → 41
#     412: 41,   # Glaciär → 41
#     413: 41,   # Varaktigt snöfält → 41
    
#     4211: 421, # Torr buskdominerad mark → 421
#     4212: 421, # Frisk buskdominerad mark → 421
#     4213: 421, # Frisk-fuktig buskdominerad mark → 421
    
#     4221: 422, # Torr risdominerad mark → 422
#     4222: 422, # Frisk risdominerad mark → 422
#     4223: 422, # Frisk-fuktig risdominerad mark → 422
    
#     4231: 423, # Torr gräsdominerad mark → 423
#     4232: 423, # Frisk gräsdominerad mark → 423
#     4233: 423, # Frisk-fuktig gräsdominerad mark → 423

#     # Bebyggelse och infrastruktur
#     51: 51,    # Exploaterad mark, byggnad → 51 (ingen förändring)
#     52: 52,    # Exploaterad mark, ej byggnad eller väg/järnväg → 52 (ingen förändring)
#     53: 53,    # Exploaterad mark, väg/järnväg → 53 (ingen förändring, ingår ej)
#     54: 54,    # Exploaterad mark, torvtäkt → 54 (ingen förändring)
    
#     # Vatten
#     61: 61,    # Sjö och vattendrag → 61 (ingen förändring)
#     62: 62,    # Hav → 62 (ingen förändring)
# }

# ══════════════════════════════════════════════════════════════════════════════
# NMD2018 KLASSER — Referens med omklassificering enligt CLASS_REMAP
# ══════════════════════════════════════════════════════════════════════════════
# Originalkod: Remappade slutkod, # (Beskrivning) — Klassnamn på slutkod
# 
CLASS_REMAP = {
#   0: 0, # Odefinierad
#   1: 1, # Odefinierad
    2: 200, # (Våtmark) — Öppen våtmark på myr / Öppen våtmark ej myr / Öppen våtmark övrigt
    3: 3, # (Åkermark) — Åkermark
    41: 41, # (Övrig öppen mark utan vegetation) — Öppen mark utan vegetation
    42: 42, # (Övrig öppen mark med vegetation) — Buskdominerad mark / Risdominerad mark / Gräsdominerad mark
    51: 51, # (Exploaterad mark, byggnad) — Byggnad
    52: 52, # (Exploaterad mark, ej byggnad eller väg/järnväg) — Anlagd mark
    53: 53, # (Exploaterad mark, väg/järnväg) — Väg/järnväg
    61: 61, # (Sjö och vattendrag) — Inlandsvatten
    62: 62, # (Hav) — Hav
    111: 101, # (Tallskog utanför våtmark) — Tallskog (sammanfört fastmark + våtmark)
    112: 102, # (Granskog utanför våtmark) — Granskog (sammanfört fastmark + våtmark)
    113: 103, # (Barrblandskog utanför våtmark) — Barrblandskog (sammanfört fastmark + våtmark)
    114: 104, # (Lövblandad barrskog utanför våtmark) — Lövblandad barrskog (sammanfört fastmark + våtmark)
    115: 105, # (Triviallövskog utanför våtmark) — Triviallövskog (sammanfört fastmark + våtmark)
    116: 106, # (Ädellövskog utanför våtmark) — Ädellövskog (sammanfört fastmark + våtmark)
    117: 107, # (Triviallövskog med ädellövinslag utanför våtmark) — Triviallövskog m. ädellövinslag (sammanfört)
    118: 108, # (Temporärt ej skog utanför våtmark) — Temporärt ej skog (sammanfört fastmark + våtmark)
    121: 101, # (Tallskog på våtmark) — Tallskog (sammanfört fastmark + våtmark)
    122: 102, # (Granskog på våtmark) — Granskog (sammanfört fastmark + våtmark)
    123: 103, # (Barrblandskog på våtmark) — Barrblandskog (sammanfört fastmark + våtmark)
    124: 104, # (Lövblandad barrskog på våtmark) — Lövblandad barrskog (sammanfört fastmark + våtmark)
    125: 105, # (Triviallövskog på våtmark) — Triviallövskog (sammanfört fastmark + våtmark)
    126: 106, # (Ädellövskog på våtmark) — Ädellövskog (sammanfört fastmark + våtmark)
    127: 107, # (Triviallövskog med ädellövinslag på våtmark) — Triviallövskog m. ädellövinslag (sammanfört)
    128: 108, # (Temporärt ej skog på våtmark) — Temporärt ej skog (sammanfört fastmark + våtmark)
}
# NOTERING: Klasserna 411, 412, 413, och 4211–4233 är NYA i NMD2023 och fanns
# INTE i NMD2018. Se CLASS_REMAP för hur dessa 2023-klasser remappas till slutkoder.

# ══════════════════════════════════════════════════════════════════════════════
# GENERALISERINGSPARAMETRAR
# ══════════════════════════════════════════════════════════════════════════════

MMU_ISLAND   = 25               # Minsta storlek på öar innan fyllnad (px) — 0,25 ha vid 10 m upplösning

# Klasser som räknas som "omgivande yta" när små landöar ska fyllas (Steg 5)
# En ö fylls bara om ALLA dess grannar tillhör dessa klasser.
# Exempel: {61, 62} = bara sjöar/vatten; {51, 52, 53, 54, 61, 62} = vatten + vägar/byggnader
ISLAND_FILL_SURROUNDS = {61, 62}

# ══════════════════════════════════════════════════════════════════════════════
# GENERALIZATION METHODS — Vilka metoder i Steg 6 ska köras?
# ══════════════════════════════════════════════════════════════════════════════
# Möjliga metoder: "conn4", "conn8"

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
#   Styrs av MMU_STEPS (samma lista som för conn4/conn8).
#
# Exempel:
#   GENERALIZATION_METHODS = {"conn4", "conn8"}            # Bara sieve-metoder
#

GENERALIZATION_METHODS = {"conn4"}


# Sieve MMU-steg för conn4 och conn8 metoder (Steg 6)
# ═════════════════════════════════════════════════════════════════════════════
# MMU = Minimum Mapping Unit i pixlar för sieve-filtren (conn4 och conn8).
#
# Teknisk förklaring:
#   - Pixelgrupper mindre än MMU-värde blir bort-sievade (sållas ut)
#   - Större MMU = mer generalisering = färre små detaljer
#   - Mindre MMU = mindre generalisering = mer original detalj
#
# Praktiska val:
#   Snabb test (3 steg, ~40% snabbare):
#     MMU_STEPS = [2, 8, 32]
#
#   Standard (6 steg, rekommenderat):
#     MMU_STEPS = [2, 4, 6, 12, 25, 50]
#
#   Detaljerad analys (9 steg, långsamt men många värdepunkter):
#     MMU_STEPS = [1, 2, 4, 8, 16, 32, 64, 100, 128]
#
# Tips:
#   - Första värdet bör oftast vara 2-4 px (annars för lite förenkling)
#   - Sista värdet bör förenligt med `HALO` för att undvika edge-artefakter
#   - Fler steg = längre körtid men bättre för att jämföra resultat
#
MMU_STEPS    = [6, 10, 12, 25, 50]


# MMU_POWERLINE_PATH — Sökväg till GPKG med kraftledningsgator (polygoner).
# MMU_POWERLINE_MAX  — Max MMU (px) för pixlar som ligger under en kraftledningsgata.
#   Pixlar under kraftledning skyddas temporärt när MMU-steget ÖVERSKRIDER detta värde,
#   precis som MMU_CLASS_MAX — men per pixel istället för per klass.
#   10 px = 0.1 ha vid 10 m upplösning.
#   None = inaktiverat.
MMU_POWERLINE_PATH = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_1/Kraftledningar/NMD2023_Kraftledning_v1_0.gpkg")
MMU_POWERLINE_MAX  = 10  # px — None = inaktiverat

# Klassspecifika MMU-maxgränser — dessa klasser skyddas när MMU-steget ÖVERSKRIDER angiven gräns.
# Format: {klass_kod: max_mmu_px}
# Klasser som inte listas här följer normal sieve utan extra skydd.
#
# Exempel: {21: 25} innebär att klass 21 sievas bort t.o.m. 25 px, men behålls (skyddas) i större MMU-steg.
#
## 2023
# MMU_CLASS_MAX = {
#     21:  25,   # Öppen våtmark på myr
#     22:  25,   # Öppen våtmark ej myr
#     200: 25,   # Öppen våtmark övrigt
#     421: 25,   # Buskdominerad mark
#     422: 25,   # Risdominerad mark
#     423: 25,   # Gräsdominerad mark
# }

## 2018
MMU_CLASS_MAX = {
    200:  25,   # Öppen våtmark på myr/Öppen våtmark ej myr/Öppen våtmark övrigt
    42:   25,   # Buskdominerad mark/Risdominerad mark/Gräsdominerad mark
}



# ══════════════════════════════════════════════════════════════════════════════
# STEG 7 — Utvidga mark i vattenkanter (expand water)
# ══════════════════════════════════════════════════════════════════════════════
# EXPAND_WATER        — Aktiverar steg 7 (expand water halo).
# EXPAND_WATER_CLASSES — Klasser som tas bort från kanten (f.d. vattenkanter).
#   Pixlar inom EXPAND_WATER_PX avstånd från icke-vattenpixel ersätts med
#   närmaste omgivande klass. Inre pixlar (djupare än EXPAND_WATER_PX) behåller
#   sin originalklass (61/62) och vektoriseras som vatten.
# EXPAND_WATER_PX     — Max antal pixlar från strandlinjen som mark får växa in.
#                       0 = ingen fill alls — hela vattenytan (EXPAND_WATER_CLASSES) nollställs.
#   2 px = 20 m vid 10 m upplösning.
# Utmapp: steg_6_generalize/{metod}_expand{N}px/  (ett TIF per tile, baserat på mmu050)
EXPAND_WATER         = True         # True/False
EXPAND_WATER_CLASSES = {61}         # klasser som "skalar bort" från kanten
EXPAND_WATER_PX      = 2            # pixlar — mark växer in så många px i vattenytorna




# Simplifiering för steg 8.
# "grass"     — GRASS v.generalize (diskbaserad, inga storleksgränser, bevarar topologi)
SIMPLIFY_BACKEND = "grass"

# ══════════════════════════════════════════════════════════════════════════════
# GRASS v.generalize — Algoritm och parametrar (Steg 8)
# ══════════════════════════════════════════════════════════════════════════════
#
# GRASS_SIMPLIFY_METHOD — Vilken algoritm som används:
#   "douglas"            — Douglas-Peucker. Tar bort vertexar.
#   "chaiken"            — Chaikin corner-cutting. Rundar pixeltrappor, lägger till punkter.
#   "douglas+chaiken"    — Douglas städar bort kolineära punkter → Chaikin rundar hörnen.
#   "chaiken+douglas"    — Chaikin rundar → Douglas trimmar. Ger rundade kurvor med färre punkter.
#
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
GRASS_SIMPLIFY_METHOD    = "douglas+chaiken"     # "douglas", "chaiken", "douglas+chaiken", "chaiken+douglas", "sliding_avg", "douglas+sliding_avg"
GRASS_CHAIKEN_THRESHOLD  = 10.0       # meter — Chaikin min-avstånd mellan punkter
GRASS_DOUGLAS_THRESHOLD  = 5.0        # meter — Douglas tröskel

# GRASS_VECTOR_MEMORY — RAM som GRASS får använda för topologinätet (MB).
# Default i GRASS är ~1000 MB. Med mycket RAM: sätt högt för att hålla hela
# topologistrukturen i minnet → undviker paginering → 2–4× snabbare.
# Lämna minst 8–16 GB över till OS + övriga processer.
GRASS_VECTOR_MEMORY = 48000  # MB (48 GB av 56 GB)

# GRASS_OMP_THREADS — antal trådar för OpenMP-stödda delar i GRASS/GDAL.
# Sätts som OMP_NUM_THREADS i steg 8. Om modul saknar OpenMP ignoreras värdet.
GRASS_OMP_THREADS = 22

# GRASS_SNAP_TOLERANCE — Snap-tolerans (meter) i v.clean-steget.
GRASS_SNAP_TOLERANCE   = 0.5   # meter

# ══════════════════════════════════════════════════════════════════════════════
# STRIP-KONFIGURATION — gemensam för steg 8, 9, 10 och 11
# ══════════════════════════════════════════════════════════════════════════════
# Y-axeln delas i STRIP_N horisontella band med STRIP_OVERLAP_M meters överlapp
# per sida. Varje band körs som en oberoende GRASS-session → hanterar hela
# Sverige utan OOM-krascher. Steg 8–10 kör STRIP_WORKERS band parallellt.
# Steg 11 slår ihop alla band till en enda slutlig GPKG per variant.
#
# RAM per jobb ≈ GRASS_VECTOR_MEMORY // STRIP_WORKERS (48000 // 8 = 6 000 MB).
# OMP-trådar per jobb ≈ GRASS_OMP_THREADS // STRIP_WORKERS (22 // 8 ≈ 2).
#
STRIP_N         = 5      # Y-band — 5 för testdata (fjall_2018_v05), 20 för full Sverige
STRIP_OVERLAP_M = 80000  # överlapp i meter per sida — 80 km täcker de största polygonerna (Vänern ~78 km)
STRIP_WORKERS   = 2      # parallella GRASS-jobb — 1 för testkörning med få tiles
STRIP_ONLY      = []     # kör bara dessa band (tom lista = alla)

# FULLSWEDEN_RAW_GPKG — Valfri genväg: om en färdig hel-Sverige-GPKG finns och
# steg 6-katalogen saknas hoppar steg 8 över r.to.vect och läser direkt från filen.
# Sätt till None för att alltid köra från raster-tiles.
FULLSWEDEN_RAW_GPKG = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_1/conn4_raw_vect.gpkg")



# ══════════════════════════════════════════════════════════════════════════════
# OVERLAY_EXTERNAL — Extern vektorfil (vatten, vägar, etc.) (Steg 11)
# ══════════════════════════════════════════════════════════════════════════════
# OVERLAY_EXTERNAL_PATH  — Absolut sökväg till den externa GPKG/SHP-filen.
# OVERLAY_EXTERNAL_LAYER — Lagernamn inuti GPKG:n att läsa (None = första lagret).
# OVERLAY_EXTERNAL_CLASS — Heltal som skrivs i 'markslag'-kolumnen för alla
#   externa polygoner. Sätt till None för att läsa kolumnen från filen själv.
OVERLAY_EXTERNAL_PATH  = "/home/hcn/NMD_workspace/NMD2023_basskikt_v2_1/LM/hydrografi_3006_merged_polygons_all.gpkg"
OVERLAY_EXTERNAL_LAYER = None  # None = första lagret, str eller lista med lagernamn ["Layer1", "Layer2"]".
OVERLAY_EXTERNAL_CLASS = 61               # None = läs 'markslag' från extern fil
# OVERLAY_EXTERNAL_SNAP  — Buffrar externa polygoner med detta antal meter INNAN difference.
# Löser floating-point-sömmar: klippt landskap överlappas å lite med externa polygonens
# ursprungliga kant, vilket hindrar gaps längs gränsen.
# 0.05 m = 5 cm är osynligt vid kartskala men eliminerar precisionsgap.
OVERLAY_EXTERNAL_SNAP  = 0.5             # meter — snap-tolerans längs difference-söm (stänger floating-point-gap)

# VECTOR_MIN_AREA_M2 — Minimiarea (m²) för polygoner i steg 10-output.
# Polygoner under denna gräns tas bort.
# 300 m² = 0.03 ha ≈ 3 px vid 10 m upplösning.
# 0 = inaktiverat.
VECTOR_MIN_AREA_M2 = 300  # m²

# VECTOR_FILL_HOLE_M2 — Hål (interior rings) i externa vattenpolygoner under denna area
# fylls igen före overlay (öar < tröskeln absorberas i vattnet).
# 2500 m² = 0.25 ha.  0 = inaktiverat.
VECTOR_FILL_HOLE_M2 = 2500  # m²

# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE CONFIGURATION — Vilka steg ska köras?
# ══════════════════════════════════════════════════════════════════════════════

ENABLE_STEPS = {
    0: True,    # Verifikation - tileluppdelning utan omklassificering (grunddata för steg 1)
    1: True,    # Tileluppdelning med omklassificering
    2: True,    # Extrahera skyddade klasser
    3: True,    # Lös upp klasser i omgivande mark (DISSOLVE_CLASSES)
    4: False,   # Ta bort små sjöar < 0,5 ha (steg_4_filter_lakes.py)
    5: True,    # Fylla små landöar < MMU_ISLAND px omringade av vatten (steg_5_filter_islands.py)
    6: True,    # Generalisering (sieve + majority + semantic)
    7: True,    # Expand water: mark flödar EXPAND_WATER_PX px in i vattenytor
    8: True,    # GRASS-polygonisering + förenkling per Y-band (steg_8_simplify.py)
    9: False,   # Overlay byggnader från steg 2 på steg 8 (steg_9_overlay_buildings.py)
    10: True,   # Sammanfoga strip-GPKGs från steg 9/8 till en GPKG per variant (steg_10_merge.py)
    11: True,   # Overlay extern vektorfil (OVERLAY_EXTERNAL_PATH) på merged lager (steg_11_overlay_external.py)
    12: True,   # Klipp till rastrets footprint (steg_12_clip_to_footprint.py)
    99: True,   # Bygga QGIS-projekt
}

# ══════════════════════════════════════════════════════════════════════════════
# QGIS-PROJEKT — Vilka steg ska inkluderas i QGIS-projektet? (Steg 99)  
# ══════════════════════════════════════════════════════════════════════════════
# Steg med mycket data (steg 0-5: 980 rasterfiler/steg) kan göra QGIS trögstartat.
# Sätt False för steg du inte behöver granska i QGIS.
#
QGIS_INCLUDE_STEPS = {
    0: True,    # Verifieringstiles (original, 2730 rasterfiler)
    1: True,    # Tiles med omklassificering (2730 rasterfiler)
    2: True,    # Extraherade skyddade klasser (2730 rasterfiler)
    3: True,    # Upplöst landskapsbild (2730 rasterfiler)
    4: False,   # Filtrerade sjöar < 0,5 ha (2730 rasterfiler)
    5: True,    # Fyllda landöar omringade av vatten (2730 rasterfiler)
    6: True,    # Generaliserat raster (steg_6_generalize/)
    7: True,    # Expand water (steg_7_expand_water/)
    8: True,    # Förenklat per strip (GRASS v.generalize)
    9: False,   # Med byggnadsoverlay (steg_9_overlay_buildings/)
    10: True,   # Sammanfogade strips — merged GPKG per variant (steg_10_merge/)
    11: True,   # Overlay extern vektorfil — LM hydrografi (steg_11_overlay_external/)
    12: True,   # Klippt till rastrets footprint (steg_12_clip_to_footprint/)
}


# ══════════════════════════════════════════════════════════════════════════════
# GDAL & RASTERIO-INSTÄLLNINGAR
# ══════════════════════════════════════════════════════════════════════════════

COMPRESS   = "lzw"          # GeoTIFF kompression
NODATA_TMP = 65535          # Temporär nodata-värde för sieve-masking

# Bygg pyramidnivåer (overviews) i steg 1 och steg 6 efter varje tile-skrivning.
# Gör QGIS-navigering snabbare.
# False = ingen overhead; True = något längre körtid men snabbare rendering.
# Resampling: "nearest" — rätt för klassificeringsdata (kategoriska värden).
BUILD_OVERVIEWS = True        # True: bygg overviews i steg 1 och steg 6
OVERVIEW_LEVELS = [2, 4, 8, 16, 32, 64, 128, 256, 512]  # 9 nivåer, faktor 2 (samma som originalrastret)

# ══════════════════════════════════════════════════════════════════════════════
# STRUCTURAL ELEMENTS
# ══════════════════════════════════════════════════════════════════════════════
STRUCT_4 = np.array([[0, 1, 0],
                     [1, 1, 1],
                     [0, 1, 0]], dtype=bool)  # 4-connected

STRUCT_8 = np.array([[1, 1, 1],
                     [1, 1, 1],
                     [1, 1, 1]], dtype=bool)  # 8-connected
