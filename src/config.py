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

# Rotmapp — konfigurerbar via miljövariabel
OUT_BASE_ROOT = Path(os.getenv("OUT_BASE", "/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_batch_v1"))

# ══════════════════════════════════════════════════════════════════════════════
# TILE CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

TILE_SIZE        = 1024          # Huvudtile-storlek (pixlar per sida)

# Explicit tile-lista (används för test):
#   PARENT_TILES = [(0, 19), (0, 20), (1, 19), (1, 20)]
# Sätt till None för att köra batchat över hela rastret:
#   PARENT_TILES = None
PARENT_TILES     = None

# Batch-körning — används när PARENT_TILES = None
# TILE_BATCH_COUNT = 100 innebär att varje batch är ~1% av alla tiles.
# Öka TILE_BATCH_INDEX med 1 för varje körning för att täcka hela rastret.
# Kan också styras via env: TILE_BATCH_INDEX=2 python run_all_steps.py
TILE_BATCH_INDEX = int(os.getenv("TILE_BATCH_INDEX", "1"))   # Vilken batch ska köras (0-baserat)
TILE_BATCH_COUNT = 100           # Totalt antal batchar (100 = ~1% per körning)

# I batch-läge skrivs varje batch till en separat undermapp batch_NNN/
# I testläge (PARENT_TILES satt) används OUT_BASE_ROOT direkt
OUT_BASE = OUT_BASE_ROOT / f"batch_{TILE_BATCH_INDEX:03d}" if PARENT_TILES is None else OUT_BASE_ROOT
PARENT_TILE_SIZE = 1024          # Matchar TILE_SIZE i steg 1
SUB_TILE_SIZE    = 1024          # Sub-tile-storlek (samma som PARENT_TILE_SIZE nu)
HALO             = 100           # px – kant på varje sida vid generalisering, >= max(MMU_STEPS)


def get_active_tiles() -> list[tuple[int, int]]:
    """Returnerar de (row, col)-par som ska processeras i denna körning.

    Om PARENT_TILES är satt: returnerar den listan direkt (test-läge).
    Annars: beräknar hela tile-gridet från källrastern och returnerar
    batch nr TILE_BATCH_INDEX av totalt TILE_BATCH_COUNT batchar.
    """
    if PARENT_TILES is not None:
        return list(PARENT_TILES)
    import rasterio
    with rasterio.open(SRC) as src:
        n_rows = (src.height + TILE_SIZE - 1) // TILE_SIZE
        n_cols = (src.width  + TILE_SIZE - 1) // TILE_SIZE
    all_tiles = [(r, c) for r in range(n_rows) for c in range(n_cols)]
    total = len(all_tiles)
    start = (TILE_BATCH_INDEX * total) // TILE_BATCH_COUNT
    end   = ((TILE_BATCH_INDEX + 1) * total) // TILE_BATCH_COUNT
    return all_tiles[start:end]

# ══════════════════════════════════════════════════════════════════════════════
# CLASSIFICATION CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

GENERALIZE_PROTECTED = {51, 61, 62}                # Skyddade klasser i steg 6 (generalisering): maskeras vid sieve/modal, exkluderas från areafilter.
SIMPLIFY_PROTECTED   = {51}                        # Skyddade klasser i steg 8 (Mapshaper): förenklas aldrig (sp=1.0). Kan skilja sig från GENERALIZE_PROTECTED.
EXTRACT_CLASSES  = {51, 53, 61, 62}                # Klasser som extraheras separat i steg 2 (vektoriseras senare): Byggnad, Väg/järnväg, Vatten
DISSOLVE_CLASSES = {53}                            # Klasser som löses upp i omgivande mark i steg 3: Väg/järnväg

# ══════════════════════════════════════════════════════════════════════════════
# CLASS REMAPPING — Omklassificering från NMD till slutklasser (Steg 0)
# ══════════════════════════════════════════════════════════════════════════════
# Mappning: NMD-källkod → nya slutkod för förenkling och anpassning till kravspec.
# Originalklasser sparas i separat _original_class-lager per tile.

CLASS_REMAP = {
    # Skogsklasser — sammanför fastmark och våtmark till samma klass
    111: 111,  # Tallskog på fastmark → 111
    121: 111,  # Tallskog på våtmark → 111
    112: 112,  # Granskog på fastmark → 112
    122: 112,  # Granskog på våtmark → 112
    113: 113,  # Barrblandskog på fastmark → 113
    123: 113,  # Barrblandskog på våtmark → 113
    114: 114,  # Lövblandad barrskog på fastmark → 114
    124: 114,  # Lövblandad barrskog på våtmark → 114
    115: 115,  # Triviallövskog på fastmark → 115
    125: 115,  # Triviallövskog på våtmark → 115
    116: 116,  # Ädellövskog på fastmark → 116
    126: 116,  # Ädellövskog på våtmark → 116
    117: 117,  # Triviallövskog m. ädellövinslag på fastmark → 117
    127: 117,  # Triviallövskog m. ädellövinslag på våtmark → 117
    118: 118,  # Temporärt ej skog på fastmark → 118
    128: 118,  # Temporärt ej skog på våtmark → 118
    
    # Våtmarksklasser — grupperas till två huvudgrupper
    200: 211,   # Öppen våtmark utan underindelning → 21 (Öppen våtmark på myr)
    211: 211,   # Buskmyr → 21
    212: 211,   # Ristuvemyr → 21
    213: 211,   # Fastmattemyr, mager → 21
    214: 211,   # Fastmattemyr, frodig → 21
    215: 211,   # Sumpcärr → 21
    216: 211,   # Mjukmattemyr → 21
    217: 211,   # Lösbottenmyr → 21
    218: 211,   # Övrig öppen myr → 21
    
    221: 221,   # Våtmark med buskar → 22 (Öppen våtmark ej på myr)
    222: 221,   # Risdominerad våtmark → 22
    223: 221,   # Gräsdominerad våtmark, mager → 22
    224: 221,   # Gräsdominerad våtmark, frodvuxen → 22
    225: 221,   # Gräsdominerad våtmark, högvuxen → 22
    226: 221,   # Mossdominerad våtmark → 22
    227: 221,   # Våtmark utan växtäcke → 22
    228: 221,   # Övrig öppen våtmark → 22
    
    # Fjällskogar — sammanför fastmark och våtmark
    23: 23,    # Låg fjällskog på våtmark → 23
    43: 23,    # Låg fjällskog på fastmark → 23
    
    # Åkermark
    3: 3,      # Åkermark → 3 (ingen förändring)
    
    # Öppen mark
    411: 411,   # Öppen fastmark utan vegetation (ej glaciär, varaktigt snöfält) → 41
    412: 411,   # Samma som 411 → 41
    413: 411,   # Samma som 411 → 41
    
    4211: 4211, # Torr buskdominerad mark → 421
    4212: 4211, # Frisk buskdominerad mark → 421
    4213: 4211, # Frisk-fuktig buskdominerad mark → 421
    
    4221: 4221, # Torr risdominerad mark → 422
    4222: 4221, # Frisk risdominerad mark → 422
    4223: 4221, # Frisk-fuktig risdominerad mark → 422
    
    4231: 4231, # Torr gräsdominerad mark → 423
    4232: 4231, # Frisk gräsdominerad mark → 423
    4233: 4231, # Frisk-fuktig gräsdominerad mark → 423

    # Bebyggelse och infrastruktur
    51: 51,    # Byggnad → 51 (ingen förändring)
    52: 52,    # Anlagd mark, ej byggnad eller väg/järnväg → 52 (ingen förändring)
    53: 53,    # Väg eller järnväg → 53 (ingen förändring)
    54: 54,    # Torvtäkt → 54 (ingen förändring)
    
    # Vatten
    61: 61,    # Inlandsvatten → 61 (ingen förändring, skyddad klass)
    62: 62,    # Hav → 62 (ingen förändring, skyddad klass)
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

# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE CONFIGURATION — Vilka steg ska köras?
# ══════════════════════════════════════════════════════════════════════════════

ENABLE_STEPS = {
    0: True,    # Verifikation - tileluppdelning utan omklassificering (grunddata för steg 1)
    1: True,    # Tileluppdelning med omklassificering
    2: True,    # Extrahera skyddade klasser
    3: True,    # Extrahera landskapsbild
    4: False,   # Ta bort små sjöar < 0,5 ha
    5: True,    # Fylla små öar < 0,5 ha omringade av vatten
    6: True,    # Generalisering
    7: True,    # Vektorisering
    8: True,    # Mapshaper-förenkling
    9: False,   # Overlay byggnader från steg 2 på steg 8
    99: True,   # Bygga QGIS-projekt
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
