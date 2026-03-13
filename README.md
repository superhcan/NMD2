# NMD2 — Generalisering och vektorisering av landskapsdata

En Python-pipeline för generalisering av svenska Nationella Mark Data (NMD2023) från raster till vektor med topologibevarandde.

## Sammanfattning

Denna pipeline:
1. **Generaliserar raster** med 4 parallella metoder (sieve, modal filter, semantisk)
2. **Konverterar till vektor** (GeoPackage format)
3. **Förenklar polygongränser** med GRASS v.generalize (Douglas-Peucker)
4. **Bevarar kritiska features** (vägar, sjöar) genom väg-separation

**Resultat:** 111 MB raster → 18 MB vektor (modal_k15) med bevarad topologi, väg-integritet och **skyddade klasser bevarade**.

**Skyddade klasser** (aldrig generaliserade):
- 51 = Byggnad
- 52 = Övrig exploaterad mark
- 53 = Väg/järnväg
- 54 = Torvtäkt
- 61 = Sjö och vattendrag
- 62 = Hav

---

## Installation

### Förutsättningar

- **Linux/macOS** (testad på Linux)
- **Python 3.11+** med venv
- **GDAL-verktyg:** `gdalbuildvrt`, `gdal_polygonize.py`, `ogr2ogr`
- **GRASS GIS 8.2+** för v.generalize
- **Spatial-bibliotek:** rasterio, geopandas, scipy

### Setup

```bash
# Klona repot
git clone git@github.com:superhcan/NMD2.git
cd NMD2

# Skapa virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Installera Python-beroenden
pip install -r requirements.txt

# Installera systemverktyg (Ubuntu/Debian)
sudo apt-get install gdal-bin grass
```

### Dataunderlag

Lägg NMD2023-data i detta format:

```
~/NMD_workspace/NMD2023_basskikt_v2_0/
├── NMD2023bas_v2_0.tif              # Original 5.8 GB raster
├── NMD2023bas_v2_0.qml              # QGIS-färgpalett
└── tiles/                           # Skapas av split_tiles.py
    ├── NMD2023bas_tile_r000_c010.tif
    └── ... (1225 tiles totalt)
```

---

## Snabbstart

### 1. Dela upp rastern i tiles (första gången)

```bash
python split_tiles.py
```

**Output:** `tiles/` mapp med 1225×2048px tiles

### 2. Generalisera rastern

```bash
python pipeline_1024_halo.py
```

Denna pipeline gör följande:

**Steg 1:** Dela upp original-rastern i 1024×1024 px tiles  
**Steg 2:** Extrahera skyddade klasser (51, 52, 53, 54, 61, 62) → `protected/`  
**Steg 3:** Extrahera landskapet (allt utom skyddade) → `landscape/`  
**Steg 4:** Fyll landöar < 1 ha → `filled/`  
**Steg 5:** Fyra parallella generaliseringsmetoder:
- **Sieve conn4/8:** gdal_sieve, konnektivitet 4 eller 8
- **Modal filter:** Majoritetsfilter med fönster k=3–15
- **Semantisk:** Likhet-baserad generalisering

**Output mappar:**
```
~/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/
├── tiles/                  # Original-tiles
├── protected/              # Skyddade klasser (intakta, ej generaliserade)
├── landscape/              # Landskapet (som generaliseras)
├── filled/                 # Efter öfyllnad
├── generalized_conn4/      # 7 MMU-steg × 16 tiles
├── generalized_conn8/
├── generalized_modal/      # k=3,5,7,11,13,15
└── generalized_semantic/   # 7 MMU-steg × 16 tiles
```

**Tid:** ~5-10 sekunder (beroende på hårdvara)

### 3. Vektorisera

```bash
python vectorize_pipeline_1024_halo.py
```

**Output:** GeoPackage-filer
```
~/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/vectorized/
├── generalized_modal_k15.gpkg           (29 MB, ~31k polygoner)
├── generalized_conn4_mmu016.gpkg
├── generalized_conn4_mmu032.gpkg
└── ...
```

**Tid:** <2 minuter

### 4. Förenkla vektorer med väg-bevarandde (rekommenderat)

```bash
bash separate_roads_final.sh
```

**Output:**
```
generalized_modal_k15_roads_preserved.gpkg    (18 MB, vägen bevarad!)
```

---

## Projektstruktur

```
NMD2/
├── pipeline_1024_halo.py              ← HUVUDSKRIPT: Rastergeneralisering (5 steg)
├── vectorize_pipeline_1024_halo.py    ← HUVUDSKRIPT: Raster→Vektor
├── separate_roads_final.sh            ← HUVUDSKRIPT: Vektor-förenkling
│
├── split_tiles.py                     ← Dela originalraster i tiles
├── extract_protected_classes.py       ← Referensskript: extrahering av skyddade
├── extract_landscape_only.py          ← Referensskript: extrahering av landskapet
├── generalize_test_conn4.py           ← Test: Sieve conn4
├── generalize_test_conn8.py           ← Test: Sieve conn8
├── generalize_test_modal.py           ← Test: Modal filter
├── generalize_test_semantic.py        ← Test: Semantisk
│
├── requirements.txt                   ← Python-beroenden
├── INSTALL.md                         ← Installationsguide
├── workflow.md                        ← Arbetsflöde & metoder (uppdaterad)
├── README.md                          ← Du är här
│
├── DOCUMENTATION_INITIAL_WORKFLOW.md  ← Rastergeneralisering + första vektoreisering
└── DOCUMENTATION_VECTOR_SIMPLIFICATION.md ← Problem, försök & final lösning
```

**Notering:** `extract_protected_classes.py` och `extract_landscape_only.py` är nu integrerade som steg 2 och 3 i `pipeline_1024_halo.py`.

---

## Filer & Utgångar

### Rastergeneraliseringens utgångar (pipeline_1024_halo.py)

| Mapp | Innehål | Utgångar | Storlek |
|------|---------|----------|----------|
| `tiles/` | Original-tiles (från split) | 16 TIF | ~50 MB |
| `protected/` | **Skyddade klasser (51-54, 61-62, intakta)** | 16 TIF | ~20 MB |
| `landscape/` | Landskapet utan skyddade | 16 TIF | ~48 MB |
| `filled/` | Efter öfyllnad | 16 TIF | ~48 MB |
| `generalized_conn4/` | Sieve conn4 | 7 MMU × 16 = 112 TIF | ~30 MB |
| `generalized_conn8/` | Sieve conn8 | 7 MMU × 16 = 112 TIF | ~30 MB |
| `generalized_modal/` | Modal filter k=3–15 | 6 kernels × 16 = 96 TIF | ~28 MB |
| `generalized_semantic/` | Semantisk | 7 MMU × 16 = 112 TIF | ~28 MB |

### Vektoreringens utgångar (vectorize_pipeline_1024_halo.py)

| Fil | Polygoner | Storlek | Beskrivning |
|-----|-----------|---------|-----------|
| `generalized_modal_k15.gpkg` | ~31k | 29 MB | Original vektor, taggiga gränser |
| `generalized_modal_k15_roads_preserved.gpkg` | ~39k | **18 MB** | **Vägen bevarad + jämna gränser (rekommenderad)** |
| `generalized_modal_k15_threshold10.gpkg` | ~39k | 11 MB | Generaliserad men vägen försvunnen |
| `generalized_conn4_mmu016.gpkg` | ~8k | 1.8 MB | Sieve conn4 MMU=16px |

---

## Metodbeskrivningar

### Sieve (Largest-neighbour)

Tar bort sammanhängande pixelytor under MMU-tröskel.
- **conn4:** Endast ortogonala grannar (jämnare kanter)
- **conn8:** Inkl. diagonala grannar (snabbare)

*Använd:* Garanterad MMU-compliance

### Modal filter

Ersätter varje pixel med den **vanligaste klassen** i N×N-fönster.
- Kernel-storlek: k=3,5,7,11,13,15 (udda tal)
- **Fördelar:** Jämna, naturliga former
- **Nackdelar:** Ingen MMU-garanti

*Använd:* Visuell kvalitet prioriteras framför matematisk MMU

### Semantisk generalisering

Eliminerar små ytor, väljer angränsande klass med **minst semantiskt avstånd** (NMD-klassgruppering).

*Använd:* Ekologisk relevans önskvärd

---

## Vektor-förenkling

### Problem: Vektorisering från raster

- ✓ Exakt representation av original-klassificering
- ✗ Pixelgränser → "taggiga" polygonkanter
- ✗ Vägar (markslag=53, 1 pixel bred) svåra att förenkla

### Lösning: GRASS v.generalize med väg-separation

```bash
bash separate_roads_final.sh
```

**Steg:**
1. Separera vägar (markslag=53) från annat
2. Importera icke-vägar till GRASS
3. Generalisera med Douglas-Peucker (threshold=10m)
4. Slå ihop vägen + generaliserade features

**Resultat:** Topologi-bevarandde, vägar intakt, 38% mindre fil

---

## Skyddade klassificeringar

Följande markslag **tas aldrig bort** under generalisering:
- **53:** Väg
- **51, 52:** Järnväg, väg (övriga)
- **54:** Väg/järnväg på bro
- **61:** Sjö
- **62:** Vatten

---

## Exempel: Använda filen i QGIS

```bash
# Öppna QGIS
qgis ~/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/vectorized/generalized_modal_k15_roads_preserved.gpkg
```

**Färgning:** Se `.qml`-files i `NMD2023_basskikt_v2_0/` för automatisk stilsättning

---

## Konfiguration

Redigera variabler i skripten för anpassning:

**pipeline_1024_halo.py:**
```python
HALO = 100              # Pixel-överlapp vid tilekanter
PROTECTED = {51,52,53,54,61,62}  # Klassificeringar som bevaras
```

**vectorize_pipeline_1024_halo.py:**
```python
PIPE = Path("...")      # Arbetsmapp
OUT = PIPE / "vectorized"
```

**separate_roads_final.sh:**
```bash
threshold=10            # Douglas-Peucker tröskel (meter)
```

---

## Tidsbudget

| Steg | Tid | Anteckningar |
|------|-----|----------|
| split_tiles.py | ~10 min | Körs endast en gång |
| pipeline_1024_halo.py steg 1-3 | ~5-10 sec | Extrahering av skyddade + landskap |
| pipeline_1024_halo.py steg 4-5 | ~10-15 sec | Öfyllnad + generaliseringsmetoder (parallell) |
| vectorize_pipeline_1024_halo.py | <2 min | Vektoreisering via gdal_polygonize |
| separate_roads_final.sh | ~2 min | GRASS generalisering |
| **TOTALT** | **~2.5-3 min** | (exklusive initial tile-split) |

---

## Dokumentation

Se detaljerade arbetsflöden och problemlösning:

- **`DOCUMENTATION_INITIAL_WORKFLOW.md`** — Rastergeneralisering + vektoreisering
- **`DOCUMENTATION_VECTOR_SIMPLIFICATION.md`** — Vector-förenkling (6 försökta lösningar)
- **`workflow.md`** — Detaljerad metodbeskrivning
- **`INSTALL.md`** — Installation & setup

---

## Resultat & Validering

### Kvalitetsmätningar

**Rastergeneralisering:**
- Vertex-reduktion: 1.1M → 409k (64% mindre) @ threshold=25m
- Polygonantal bevarade: 31,792 (100%)
- Topologi: ✓ Perfekt

**Vektoreisering:**
- Filstorlek: 111 MB (raster) → 18 MB (vektor) = 84% reduktion
- Vägar bevarade: ✓ Alla 284 väg-polygoner intakt
- Gränser: ✓ Jämna efter förenkling

---

## Bidrag & Feedback

Förbättringsförslag? Öppna ett issue eller pull request på GitHub:

https://github.com/superhcan/NMD2

---

## Licens

CC0 1.0 Universal — Public domain

---

## Kontakt

**Projekt:** NMD2 generalisering & vektorisering  
**GitHub:** https://github.com/superhcan/NMD2  
**Data:** Nationella Mark Data 2023 (NMD2023) — MSB

**Senast uppdaterad:** 12 mars 2026
