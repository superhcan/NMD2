# Installation — NMD2 Pipeline

## Systemberoenden

Installera följande systemmjukvara innan Python-miljön sätts upp.

### GDAL / OGR (≥ 3.6)

```bash
sudo apt install gdal-bin libgdal-dev python3-gdal
gdal-config --version   # verifiera
```

### GRASS GIS (≥ 8.3)

```bash
sudo apt install grass grass-dev
grass --version         # verifiera
```

GRASS används i steg 8 för polygonisering (`r.to.vect`) och vektorförenkling (`v.generalize`). Kommandot `grass` måste finnas i `PATH`.

### QGIS med Python-API (≥ 3.28)

QGIS krävs **enbart** för steg 99 (bygga QGIS-projekt). Om du inte behöver steg 99 kan det hoppas över (`ENABLE_STEPS[99] = False` i config.py).

```bash
sudo apt install qgis python3-qgis
```

---

## Python-miljö

Pipelinen kräver Python ≥ 3.10.

```bash
cd /sökväg/till/NMD2

# Skapa virtuell miljö (om den inte redan finns)
python3 -m venv .venv

# Aktivera
source .venv/bin/activate

# Installera Python-paket
pip install -r requirements.txt
```

### Paket som installeras

| Paket | Version | Syfte |
|-------|---------|-------|
| rasterio | 1.4.4 | Raster-I/O, tile-läsning/skrivning |
| geopandas | 1.1.3 | Vektor-I/O, spatial operationer (steg 10–12) |
| fiona | 1.10.1 | GPKG-läsning/skrivning |
| scipy | 1.17.1 | Distance-transform (steg 3), ndimage (steg 5) |
| numpy | 2.4.3 | Pixeloperationer |
| shapely | 2.1.2 | Geometrioperationer |
| pyproj | 3.7.2 | Koordinattransformationer |

---

## Datakrav

Följande datafiler måste laddas ner och placeras på disk innan pipelinen körs. Sökvägarna konfigureras i `src/config.py`.

### NMD-raster (obligatorisk)

Ladda ner **NMD2018 basskikt** (ogeneraliserad, hela Sverige) från [SLU Naturvårdsanalys](https://www.slu.se/centrumbildningar-och-projekt/slu-nmi-nationell-markinventeringen/nationella-marktackedata-nmd/):

- Fil: `NMD2018bas_ogeneraliserad_Sverige_v1_1.tif` (eller klippt variant)
- Format: GeoTIFF, SWEREF99TM (EPSG:3006), 10 m pixelstorlek
- Sätt sökvägen i config.py: `SRC = Path("...")`

### LM Hydrografi (obligatorisk för steg 11)

Lantmäteriets hydrografi som polygonlager (GPKG), t.ex. `hydrografi_3006_merged_polygons_all.gpkg`:

- Format: GeoPackage, SWEREF99TM
- Sätt sökvägen: `OVERLAY_EXTERNAL_PATH = "..."`

### Kraftledningsgator (valfri, steg 6)

Används för att skydda smala skogskorridorer under kraftledningar från sieve-generalisering:

- Sätt `MMU_POWERLINE_PATH = Path("...")` eller `MMU_POWERLINE_MAX = None` för att inaktivera

### Footprint-polygon (obligatorisk för steg 12)

Polygonlager som definierar rastrets täckningsyta (används för slutklippning):

- Sätt `FOOTPRINT_GPKG = Path("...")`

---

## Konfiguration av sökvägar

Öppna `src/config.py` och justera dessa fyra rader efter din installation:

```python
SRC          = Path("/sökväg/till/NMD2018.tif")
OUT_BASE     = Path("/sökväg/till/output-katalog/körningsnamn_v01")
FOOTPRINT_GPKG = Path("/sökväg/till/footprint.gpkg")
OVERLAY_EXTERNAL_PATH = "/sökväg/till/hydrografi.gpkg"
```

`OUT_BASE` är katalogen dit all output skrivs. En ny katalog skapas automatiskt om den inte finns.

---

## Verifiera installationen

```bash
source .venv/bin/activate

# Kontrollera att config läses utan fel
python3 -c "import sys; sys.path.insert(0, 'src'); from config import SRC, OUT_BASE; print('SRC:', SRC); print('OUT_BASE:', OUT_BASE)"

# Kontrollera att GRASS finns
grass --version | head -1

# Kontrollera att GDAL finns
gdal_sieve.py --version 2>&1 | head -1

# Visa pipeline-steg
python3 run_all_steps.py --list
```

---

## Katalogstruktur (NMD_workspace)

Rekommenderad struktur för indata:

```
/home/hcn/NMD_workspace/
├── NMD2018_basskikt_ogeneraliserad_Sverige_v1_1/
│   ├── 2018_clipped.tif          ← SRC
│   ├── nmd2018_reclassified.qml  ← QML_RECLASSIFY
│   └── 2018_mask__vectorized.gpkg ← FOOTPRINT_GPKG
└── NMD2023_basskikt_v2_1/
    ├── LM/
    │   └── hydrografi_3006_merged_polygons_all.gpkg  ← OVERLAY_EXTERNAL_PATH
    ├── Kraftledningar/
    │   └── NMD2023_Kraftledning_v1_0.gpkg  ← MMU_POWERLINE_PATH
    └── fjall_2018_v07/            ← OUT_BASE (skapas automatiskt)
```
