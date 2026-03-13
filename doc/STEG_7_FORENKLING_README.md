# Steg 7: Förenkling av Vektordata med Mapshaper

**Status:** ✅ KOMPLETT  
**Datum:** 13 mars 2026  
**Verktyg:** Mapshaper 0.6.113 (Arc-baserad topologi)

---

## 📋 Sammanfattning

**Steg 7** förenklar 20,624 landskapspolygoner (28 MB) från Steg 6 till 4 progressiva nivåer utan att skapa slivers mellan polygoner.

### Varför Mapshaper?

Tidigare försök misslyckades:
- ❌ **Shapely** - Per-polygon processing → slivers
- ❌ **Python topojson** - Alltför långsam (timeout på 20k features)  
- ❌ **PostGIS ST_SimplifyPreserveTopology** - För-polygon processing → slivers
- ❌ **GDAL ogr2ogr -simplify** - Per-polygon processing → slivers
- ✅ **Mapshaper** - Arc-baserad topologi, bevarar gränserna mellan polygoner

---

## 🎯 Resultat

| Nivå | Inställning | Filstorlek | Beskrivning |
|------|-----------|-----------|------------|
| **Minimal** | percentage=90% | 28 MB | 90% av vertices behålls |
| **Lätt** | percentage=75% | 28 MB | 75% av vertices behålls |
| **Måttlig** | percentage=50% | 18 MB | 50% av vertices behålls |
| **Aggressiv** | percentage=25% | 12 MB | 25% av vertices behålls |

**Output-katalog:**  
`/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v2/simplified/`

**Filer:**
- `modal_k15_simplified_p90.gpkg`
- `modal_k15_simplified_p75.gpkg`
- `modal_k15_simplified_p50.gpkg`
- `modal_k15_simplified_p25.gpkg`

---

## 🔧 Inställningar Förklarade

### `percentage=X%` - Vertex Retention (ENKELT)
```bash
percentage=90%   # Behåll 90% av borttagna vertices (minimal förenkling)
percentage=75%   # Behåll 75% av borttagna vertices (lätt)
percentage=50%   # Behåll 50% av borttagna vertices (måttlig)
percentage=25%   # Behåll 25% av borttagna vertices (aggressiv)
```

**Förklaring:** Mapshaper identifierar alla "borttagna" vertices (punkter som inte påverkar formen mycket). `percentage=` säger hur många av dessa som ska behållas.

### `planar` - Koordinatsystem (KRITISK)
```bash
planar   # Behandla som platt 2D (för projekterad data som EPSG:3006)
```

**Varför:** Ditt data använder Swedish RT90 (EPSG:3006), som är projekterad. Utan `planar` försöker Mapshaper räkna med jordens krökning = helt fel.

### `keep-shapes` - Bevara Små Polygoner (VIKTIGT)
```bash
keep-shapes   # Förhindra att små polygoner försvinner
```

**Varför:** Vid aggressiv förenkling kan små polygoner teoretiskt försvinna. `keep-shapes` ser till att alla bevaras.

---

## 💻 Installation & Körning

### Förkunskaper

```bash
# 1. Installera Node.js (en gång)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 18

# 2. Installera Mapshaper (en gång)
npm install -g mapshaper
```

### Köra scriptet

```bash
# Aktivera venv
source /home/hcn/projects/NMD2/.venv/bin/activate

# Ladda Node.js och kör
export NVM_DIR="$HOME/.config/nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

python3 /home/hcn/projects/NMD2/simplify_mapshaper.py
```

**Tid:** ~2 minuter för alla 4 nivåer

---

## 📝 Kod-Highlights

### Huvudfunktion

```python
def simplify_with_mapshaper(input_file, output_dir, 
                            tolerances=[90, 75, 50, 25]):
    """
    Mapshaper CLI wrapper för topology-preserving simplification.
    
    tolerances = % av removable vertices att behålla
    """
```

### Mapshaper Command

```bash
mapshaper input.geojson \
  -simplify percentage=50% \
  planar \
  keep-shapes \
  -o format=geojson output.geojson
```

### CRS Hantering

```bash
# Konvertera GPKG → GeoJSON
ogr2ogr -f GeoJSON input.geojson input.gpkg

# Förenkla med Mapshaper (behåller EPSG:3006-koordinater)
mapshaper input.geojson -simplify percentage=50% planar keep-shapes \
  -o format=geojson output.geojson

# Konvertera tillbaka → GPKG med korrekt CRS
ogr2ogr -f GPKG -a_srs EPSG:3006 output.gpkg output.geojson
```

**VIKTIG NOTERING:** `-a_srs` (assign) istället för `-s_srs/-t_srs` (transform) eftersom GeoJSON redan har rätt koordinater.

---

## 🎓 Vad Vi Lärde Oss

### Mapshaper vs Andra Verktyg

| Verktyg | Approach | Topologi | Resultat |
|---------|----------|----------|----------|
| Shapely | Per-polygon | Nej | ❌ Slivers |
| PostGIS ST_SimplifyPreserveTopology | Per-polygon | Nej | ❌ Slivers |
| ogr2ogr -simplify | Per-polygon | Nej | ❌ Slivers |
| **Mapshaper** | **Arc-based** | **Ja** | ✅ Topp-fri |

### Parameter-Förvirring

**VIKTIGT:** Vi använder `percentage=`, inte `resolution=`:
- ❌ `resolution=5` = Gridupplösning för OUTPUT (inte förenkling!)
- ✅ `percentage=50%` = Behåll 50% av vertices (verklig förenkling!)

**Les:** Läs Mapshaper-dokumentationen noga. `resolution=` låter som förenkling men är något helt annat.

---

## 📂 Filöversikt

**Arkiverade versioner:**
- `simplify_mapshaper.py` - Aktivt script
- `simplify_mapshaper_ARKIV_2026-03-13.py` - Backup med datum

**Dokumentation:**
- `STEG_7_FORENKLING_README.md` - Du läser detta (process + inställningar)
- `MAPSHAPER_SIMPLIFY_GUIDE.md` - Detaljerad Mapshaper-guide (30+ exempel)

**Utdata:**
```
/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v2/simplified/
├── modal_k15_simplified_p90.gpkg   (28 MB - minimal förenkling)
├── modal_k15_simplified_p75.gpkg   (28 MB - lätt förenkling)
├── modal_k15_simplified_p50.gpkg   (18 MB - måttlig förenkling)
└── modal_k15_simplified_p25.gpkg   (12 MB - aggressiv förenkling)
```

---

## ✅ Verifiera Resultat

```bash
# Kontrollera ett exempel-output
ogrinfo -al /home/hcn/NMD_workspace/.../simplified/modal_k15_simplified_p50.gpkg

# Du bör se:
# - Layer name: modal_k15_simplified_p50
# - Geometry: Polygon
# - Feature Count: 20624  (samma som original!)
# - CRS: EPSG:3006 (Swedish RT90)
```

### QGIS Inspektioner

1. Öppna alla 4 filer i QGIS
2. Använd **Semi-transparency** (50%) för att se genom lager
3. Zooma in på gränser mellan polygoner
4. Verifiera: **Inga vita slivers** mellan polygoner ✓

---

## 🚀 Nästa Steg

Efter Steg 7:
- **Steg 8:** Validering i QGIS (topologi, slivers, integritet)
- **Steg 9:** Metadata und dokumentation
- **Steg 10:** Slutlig leverans (välj lämplig förenlingsgrad)

**Rekommendation:** 
- Arkiv: `p90%` (maximala detaljer)
- GIS-analys: `p75%` (bra balans)
- Webkarta: `p50%` (snabb rendering)
- Mobil: `p25%` (minimal storlek)

---

## 📞 Felsökning

### Problem: "bash: mapshaper: command not found"

```bash
export NVM_DIR="$HOME/.config/nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
mapshaper --version  # Testa
```

### Problem: "Cannot find Node.js"

```bash
# Installera nvm (en gång)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 18
```

### Problem: "PROJ: utm: Invalid latitude"

**Orsak:** Fel CRS-omvandling. Använd `-a_srs` istället för `-s_srs/-t_srs`

```bash
# ✅ RÄTT:
ogr2ogr -f GPKG -a_srs EPSG:3006 output.gpkg input.geojson

# ❌ FEL:
ogr2ogr -f GPKG -s_srs EPSG:4326 -t_srs EPSG:3006 output.gpkg input.geojson
```

---

**Version:** 1.0  
**Uppdaterad:** 13 mars 2026  
**Status:** Produktionsklar
