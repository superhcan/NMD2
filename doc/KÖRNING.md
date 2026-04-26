# Körning och konfiguration — NMD2 Pipeline

## Köra pipelinen

Alla steg körs via `run_all_steps.py` från projektets rotkatalog:

```bash
cd /sökväg/till//NMD2
source .venv/bin/activate

# Kör alla aktiverade steg (styrs av ENABLE_STEPS i config.py)
python3 run_all_steps.py

# Kör bara specifika steg
python3 run_all_steps.py --step 6 7 8

# Kör ett intervall av steg (t.ex. steg 8 till 13)
python3 run_all_steps.py --step 8 9 10 11 12 13

# Visa alla steg och om de är aktiverade
python3 run_all_steps.py --list

# Hjälp
python3 run_all_steps.py --help
```

### Enskilda steg manuellt

Varje steg kan också köras direkt:

```bash
cd /sökväg/till//NMD2
source .venv/bin/activate
python3 src/steg_6_generalize.py
```

---

## Steg-översikt och ENABLE_STEPS

Vilka steg som körs styrs av `ENABLE_STEPS` i `src/config.py`. Steg med `False` hoppas över automatiskt.

| Steg | Script | Standardvärde | Beskrivning |
|------|--------|---------------|-------------|
| 0 | `steg_0_verify_tiles.py` | `True` | Tileluppdelning utan omklassificering (kan avnändas för verifikation) |
| 1 | `steg_1_reclassify.py` | `True` | Omklassificering med CLASS_REMAP |
| 2 | `steg_2_extract.py` | `True` | Extrahera vägar/byggnader/vatten till separat lager |
| 3 | `steg_3_dissolve.py` | `True` | Lös upp vägar (klass 53) i omgivande mark |
| 4 | `steg_4_filter_lakes.py` | `False` | Ta bort sjöar < 0,5 ha (vid behv) |
| 5 | `steg_5_filter_islands.py` | `True` | Fylla landöar < 0,25 ha omringade av vatten |
| 6 | `steg_6_generalize.py` | `True` | Iterativ sieve-generalisering med HALO-teknik |
| 7 | `steg_7_expand_water.py` | `True` | Mark flödar 2 px in i vattenytor |
| 8 | `steg_8_simplify.py` | `True` | GRASS-polygonisering + vektorförenkling per Y-band |
| 9 | `steg_9_overlay_buildings.py` | `False` | Byggnadsoverlay (vid behov. kräver QGIS) |
| 10 | `steg_10_merge.py` | `True` | Slå ihop Y-band till en GPKG per variant |
| 11 | `steg_11_overlay_external.py` | `True` | Overlay LM hydrografi |
| 12 | `steg_12_clip_to_footprint.py` | `True` | Klipp till rastrets täckningsyta |
| 99 | `steg_99_build_qgis_project.py` | `True` | Bygg QGIS-projekt |

---

## Konfigurationsreferens

All konfiguration sker i `src/config.py`. Nedan följer de viktigaste parametrarna grupperade per funktion.

---

### Sökvägar

```python
SRC = Path("...")              # NMD-källraster (GeoTIFF)
QML_SRC = Path("...")          # Färgpalett för originalrastret (reserv)
QML_RECLASSIFY = Path("...")   # Färgpalett för omklassificerat raster
FOOTPRINT_GPKG = Path("...")   # Täckningsyta för klippning i steg 12
FOOTPRINT_LAYER = "..."        # Lagernamn i FOOTPRINT_GPKG
OUT_BASE = Path("...")         # Output-rotkatalog (skapas automatiskt)
```

**Tips**: Byt `OUT_BASE` för varje ny körning (t.ex. `_v01`, `_v02`) så att gamla resultat bevaras.

---

### Tile-konfiguration

```python
TILE_SIZE = 2048               # Pixlar per tile-sida (ändra sällan)
HALO = 100                     # Generaliserings-kant i px — måste vara ≥ max(MMU_STEPS)

PARENT_TILES = [(r, c) for r in range(45) for c in range(26)]
# NMD2018 klippt (fjäll): 26 × 45 = 1170 tiles
# NMD2023 hela Sverige:   35 × 78 = 2730 tiles
```

Vanliga förinställda val (kommenterade i config.py):

| Kommentar | Tiles | Täckning |
|-----------|-------|----------|
| `range(78) × range(35)` | 2730 | 100 % av landet |
| `range(39) × range(35)` | 1365 | ~50 % |
| `range(45) × range(26)` | 1170 | NMD2018 fjäll/klippt |
| `range(4) × range(35)` | 140 | ~5 % (snabb test) |

---

### Klassificering

```python
CLASS_REMAP = {
    111: 101,   # Tallskog fastmark → 101
    121: 101,   # Tallskog våtmark  → 101
    # ... (se config.py för fullständig lista)
}

DISSOLVE_CLASSES = {53}        # Klasser som löses upp i steg 3 (vägar)
GENERALIZE_PROTECTED = {61, 62} # Klasser som ALDRIG ändras av sieve (vatten)
EXTRACT_CLASSES = {51, 53, 61, 62} # Klasser som sparas separat i steg 2
```

---

### Generalisering (steg 6)

```python
GENERALIZATION_METHODS = {"conn4"}   # "conn4", "conn8" eller {"conn4", "conn8"}

MMU_STEPS = [6, 10, 12, 25, 50]     # Pixelsteg för sieve, kumulativa
# Snabb test:  [2, 8, 32]
# Standard:    [2, 4, 6, 12, 25, 50]

MMU_ISLAND = 25                      # Öar under detta värde fylls i steg 5 (0,25 ha)

MMU_CLASS_MAX = {
    200: 25,   # Öppen våtmark — skyddas vid MMU > 25 px
    42:  25,   # Busk-/gräsdominerad mark — skyddas vid MMU > 25 px
}

MMU_POWERLINE_PATH = Path("...")     # GPKG med kraftledningsgator
MMU_POWERLINE_MAX  = 10              # px — pixlar under kraftledning skyddas upp till detta MMU
# Sätt MMU_POWERLINE_MAX = None för att inaktivera kraftledningsskyddet
```

**conn4 vs conn8:**
- `conn4` — konservativ (4-konnektivitet), ger skarpare gränser
- `conn8` — aggressivare (8-konnektivitet), rensar ut "pepparkornsmönster" bättre

Varje metod producerar en separat variant i outputkatalogen: `steg_6_generalize/conn4/` respektive `steg_6_generalize/conn8/`.

---

### Expand water (steg 7)

```python
EXPAND_WATER = True              # Aktivera/inaktivera
EXPAND_WATER_CLASSES = {61}      # Klasser som "skalas in" från kanten
EXPAND_WATER_PX = 2              # Antal pixlar mark flödar in (2 px = 20 m vid 10 m upplösning)
```

---

### GRASS-vektorisering (steg 8)

```python
GRASS_SIMPLIFY_METHOD   = "douglas+chaiken"  # Se nedan
GRASS_DOUGLAS_THRESHOLD = 5.0     # meter — Douglas-Peucker tolerans
GRASS_CHAIKEN_THRESHOLD = 10.0    # meter — Chaikin min-avstånd mellan punkter
GRASS_VECTOR_MEMORY     = 48000   # MB RAM för GRASS topologinät (anpassa efter tillgängligt RAM)
GRASS_OMP_THREADS       = 22      # Antal OpenMP-trådar
GRASS_SNAP_TOLERANCE    = 0.5     # meter — snap i v.clean
```

**Tillgängliga metoder:**

| Metod | Beskrivning |
|-------|-------------|
| `"douglas"` | Douglas-Peucker — tar bort vertexar längs raka sträckor |
| `"chaiken"` | Chaikin corner-cutting — rundar pixeltrappor, lägger till punkter |
| `"douglas+chaiken"` | Douglas städar kolineära punkter → Chaikin rundar hörnen **(rekommenderat)** |
| `"chaiken+douglas"` | Chaikin rundar → Douglas trimmar |

---

### Strip-konfiguration (steg 8–11)

```python
STRIP_N         = 5       # Antal Y-band (5 för testkörning, 20 för hela Sverige)
STRIP_OVERLAP_M = 80000   # Överlapp i meter per sida (80 km täcker Vänern ~78 km)
STRIP_WORKERS   = 2       # Parallella GRASS-jobb (anpassa efter CPU/RAM)
STRIP_ONLY      = []      # Kör bara specifika band, t.ex. [0, 1] — tom lista = alla
```

**Minnesdimensionering:**
- RAM per GRASS-jobb ≈ `GRASS_VECTOR_MEMORY ÷ STRIP_WORKERS`
- CPU-trådar per jobb ≈ `GRASS_OMP_THREADS ÷ STRIP_WORKERS`

Exempel med 56 GB RAM: `48000 MB ÷ 2 workers = 24 GB per jobb`.

```python
FULLSWEDEN_RAW_GPKG = Path("...")   # Genväg: om en färdig råvektor-GPKG finns hoppar steg 8 
                                    # över r.to.vect och läser direkt från filen
                                    # Sätt till None för att alltid köra från raster
```

---

### Extern vattenoverlay (steg 11)

```python
OVERLAY_EXTERNAL_PATH  = "/sökväg/till/hydrografi.gpkg"
OVERLAY_EXTERNAL_LAYER = None       # None = första lagret, eller lagernamn som sträng
OVERLAY_EXTERNAL_CLASS = 61         # Klass som skrivs för alla externa vattenpolygoner
OVERLAY_EXTERNAL_SNAP  = 0.5        # meter — buffert som stänger floating-point-gap längs söm

VECTOR_MIN_AREA_M2  = 300           # m² — ta bort polygoner under denna area (0 = inaktiverat)
VECTOR_FILL_HOLE_M2 = 2500          # m² — fyll hål i vattenpolygoner under denna area (0 = inaktiverat)
```

---

### GDAL-inställningar

```python
COMPRESS        = "lzw"     # GeoTIFF-kompression för alla raster-outputs
BUILD_OVERVIEWS = True       # Bygg pyramider — gör QGIS-navigering snabbare
```

---

## Vanliga körscenarier

### Testkörning — litet område (fjäll, ~1170 tiles)

```python
# src/config.py
SRC      = Path(".../2018_clipped.tif")
OUT_BASE = Path(".../fjall_2018_v01")
PARENT_TILES = [(r, c) for r in range(45) for c in range(26)]  # 1170 tiles
MMU_STEPS    = [6, 10, 12, 25, 50]
STRIP_N      = 5
STRIP_WORKERS = 2
GENERALIZATION_METHODS = {"conn4"}
```

```bash
python3 run_all_steps.py
```

### Produktionskörning — hela Sverige (~2730 tiles)

```python
# src/config.py
SRC      = Path(".../NMD2023bas_v2_1.tif")
OUT_BASE = Path(".../prod_100proc_v01")
PARENT_TILES = [(r, c) for r in range(78) for c in range(35)]  # 2730 tiles
MMU_STEPS    = [2, 4, 6, 12, 25, 50]
STRIP_N      = 20
STRIP_WORKERS = 8
GENERALIZATION_METHODS = {"conn4"}
```

### Köra om bara vektordelen (steg 8 och framåt)

Om rastersteget (6–7) redan är klart kan du börja direkt på vektoriseringen:

```bash
python3 run_all_steps.py --step 8 10 11 12 13 99
```

### Jämföra conn4 och conn8

```python
GENERALIZATION_METHODS = {"conn4", "conn8"}
```

Båda varianterna körs i steg 6–8 och producerar separata output-kataloger: `conn4_mmu050/` och `conn8_mmu050/`.

---

## Loggning

Pipelinen loggar till konsolen och till en fil i `OUT_BASE/summary/`:

```
OUT_BASE/
└── summary/
    ├── summary_steg_6_generalize_20260426_141705.log
    ├── summary_steg_8_simplify_20260426_153210.log
    └── ...
```

Loggnivå: `INFO`. Felbeslutningar och varningar loggas med `WARNING`/`ERROR`.
