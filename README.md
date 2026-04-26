# NMD2 — Generaliseringspipeline för NMD

Automatiserad pipeline som omklassificerar och generaliserar **Nationella Marktäckedata (NMD)** från rasterformat till ett topologiskt korrekt, generaliserat vektorlager (GeoPackage) för hela Sverige.

Pipelines primära indata är NMD2018 (10 m pixelstorlek, ~52 000 × 91 800 px för fjällregionen) och slutresultatet är ett sammanhängande polygonlager utan luckor eller överlapp, kombinerad med Lantmäteriets hydrografi.

---

## Snabbstart

```bash
# 1. Aktivera Python-miljö
cd /home/hcn/projects/NMD2
source .venv/bin/activate

# 2. Kontrollera att sökvägarna i config.py pekar rätt
#    (SRC, OUT_BASE, OVERLAY_EXTERNAL_PATH m.fl.)
nano src/config.py

# 3. Kör hela pipelinen
python3 run_all_steps.py

# 4. Kör enskilda steg (t.ex. bara steg 6, 7 och 8)
python3 run_all_steps.py --step 6 7 8

# Visa alla steg och om de är aktiverade
python3 run_all_steps.py --list
```

---

## Pipeline-flöde

```
NMD-raster (GeoTIFF)
        │
        ▼
  [0] Verifikation         Delar raster i tiles utan omklassificering
        │
        ▼
  [1] Omklassificering     Applicerar CLASS_REMAP (t.ex. tall+gran på fastmark/våtmark → 101/102)
        │
        ▼
  [2] Extrahera klasser    Sparar vägar (53), byggnader (51), vatten (61/62) som separat lager
        │
        ▼
  [3] Dissolve             Ersätter vägar (klass 53) med omgivande mark via distance-transform
        │
  [4] Sjö-filter (opt.)     Tar bort sjöar < 0,5 ha och fyller med omgivande mark
        │
        ▼
  [5] Ö-filter              Fyller landöar < 0,25 ha helt omringade av vatten
        │
        ▼
  [6] Generalisering       Iterativ sieve (GDAL) med HALO-teknik; bevarar vatten och skyddade klasser
        │
        ▼
  [7] Expand water         Mark flödar 2 px in i vattenytor; centralt vatten nollställs (skapar plats för overlay)
        │
        ▼
  [8] GRASS-polygonisering Raster → vektor per Y-band; v.generalize (douglas+chaiken)
        │
  [9] Byggnads-overlay (opt.) Lägger byggnader från steg 2 ovanpå steg 8
        │
        ▼
 [10] Merge               Slår ihop Y-band till en GPKG per variant
        │
        ▼
 [11] Vatten-overlay        Klipper in Lantmäteriets hydrografi (extern GPKG) → topologiskt korrekt vatten
        │
        ▼
 [12] Footprint-klippning  Klipper till rastrets täckningsyta
        │
        ▼
 [13] Dataarea-klippning   Tar bort polygoner utanför rastrets giltiga pixlar
        │
        ▼
  Slutlig GPKG (täckande polygonlager, utan luckor eller överlapp)
        │
 [99] QGIS-projekt         Bygger inspektionsbart QGIS-projekt med alla steg
```

---

## Systemberoenden

| Komponent | Version | Syfte |
|-----------|---------|-------|
| Python | ≥ 3.10 | Pipeline-kod |
| GDAL / OGR | ≥ 3.6 | Rasteroperationer, `gdal_sieve` |
| GRASS GIS | ≥ 8.3 | Polygonisering och vektorförenkling (steg 8) |
| QGIS (med Python-API) | ≥ 3.28 | Steg 99: bygga QGIS-projekt |

Python-paket installeras via venv (se [doc/INSTALL.md](doc/INSTALL.md)):

```
rasterio, geopandas, fiona, scipy, numpy, shapely, pyproj, pandas
```

---

## Datakrav

Fyra externa datakällor måste finnas på disk innan körning:

| Data | Variabel i config.py | Används i |
|------|----------------------|-----------|
| NMD-raster (GeoTIFF) | `SRC` | Steg 0–7 |
| LM hydrografi (GPKG) | `OVERLAY_EXTERNAL_PATH` | Steg 11 |
| Kraftledningsgator (GPKG) | `MMU_POWERLINE_PATH` | Steg 6 |
| Footprint-polygon (GPKG) | `FOOTPRINT_GPKG` | Steg 12 |

---

## Dokumentation

| Fil | Innehåll |
|-----|----------|
| [doc/INSTALL.md](doc/INSTALL.md) | Installation av beroenden och miljöinställning |
| [doc/METOD.md](doc/METOD.md) | Metodbeskrivning — hur och varför varje steg fungerar |
| [doc/KÖRNING.md](doc/KÖRNING.md) | Körningsinstruktioner och konfigurationsreferens |

---

## Katalogstruktur

```
NMD2/
├── run_all_steps.py        # Master orchestrator
├── requirements.txt        # Python-beroenden
├── src/
│   ├── config.py           # All konfiguration — ändra här
│   ├── steg_0_verify_tiles.py
│   ├── steg_1_reclassify.py
│   ├── steg_2_extract.py
│   ├── steg_3_dissolve.py
│   ├── steg_4_filter_lakes.py
│   ├── steg_5_filter_islands.py
│   ├── steg_6_generalize.py
│   ├── steg_7_expand_water.py
│   ├── steg_8_simplify.py
│   ├── steg_9_overlay_buildings.py
│   ├── steg_10_merge.py
│   ├── steg_11_overlay_external.py
│   ├── steg_12_clip_to_footprint.py
│   ├── steg_99_build_qgis_project.py
│   └── logging_setup.py
└── doc/
    ├── INSTALL.md
    ├── METOD.md
    └── KÖRNING.md
```

Output skrivs till katalogen angiven i `OUT_BASE` (config.py), t.ex.:
```
/home/hcn/NMD_workspace/.../fjall_2018_v07/
├── steg_0_verify_tiles/
├── steg_1_reclassify/
│   └── ...
├── steg_6_generalize/
│   └── conn4/
│       └── *_mmu050.tif
├── steg_8_simplify/
│   └── conn4_mmu050/
│       ├── strip_000.gpkg
│       └── strip_001.gpkg
├── steg_11_overlay_external/
│   └── conn4_mmu050.gpkg
└── steg_12_clip_to_footprint/
    └── conn4_mmu050.gpkg   ← slutresultat
```
