# 📚 NMD2 Dokumentation - INDEX

All dokumentation för NMD2 2023 landskapsförenkling pipeline.

---

## 🗂️ Dokumentation efter Ämne

### 🚀 Komma Igång

| Fil | Syfte | Läsning |
|-----|-------|---------|
| [INSTALL.md](INSTALL.md) | Installera beroenden (Python, GDAL, PostgreSQL) | 5 min |
| [README.md](README.md) | **STARTSIDA** - Projektöversikt & snabbstart | 3 min |

### 🔧 Installation & Setup

| Fil | Syfte | Läsning |
|-----|-------|---------|
| [MAPSHAPER_INSTALLATION_GUIDE.md](MAPSHAPER_INSTALLATION_GUIDE.md) | Installera Node.js + Mapshaper | 10 min |
| [workflow.md](workflow.md) | Pipeline-arbetsflöde & arkitektur | 10 min |

### 📊 Steg 7 - Förenkling (AKTUELLT)

| Fil | Syfte | Läsning |
|-----|-------|---------|
| [STEG_7_FORENKLING_README.md](STEG_7_FORENKLING_README.md) | **Komplett guide** - Process, inställningar, felsökning | 15 min |
| [STEG_7_NOTES.md](STEG_7_NOTES.md) | Snabb-referens - Commands & parametrar | 2 min |

### 📖 Detaljinformation

| Fil | Syfte | Läsning |
|-----|-------|---------|
| [MAPSHAPER_SIMPLIFY_GUIDE.md](MAPSHAPER_SIMPLIFY_GUIDE.md) | Mapshaper fördjupning - 30+ exempel | 20 min |
| [tile_boundary_notes.md](tile_boundary_notes.md) | Tile-gränser & halo-behandling | 10 min |

---

## 📍 Vilken Fil Ska Jag Läsa?

### "Jag är ny på projektet"
1. **[README.md](README.md)** (3 min) - Projektöversikt
2. **[INSTALL.md](INSTALL.md)** (5 min) - Installation
3. **[workflow.md](workflow.md)** (10 min) - Hur allt hänger samman

### "Jag vill köra pipelinen"
1. **[INSTALL.md](INSTALL.md)** - Se till att allt är installerat
2. **[README.md](README.md)** - Snabbstart-sektion
3. **[STEG_7_NOTES.md](STEG_7_NOTES.md)** - Snabb-referens för Steg 7

### "Jag behöver installera Mapshaper"
→ **[MAPSHAPER_INSTALLATION_GUIDE.md](MAPSHAPER_INSTALLATION_GUIDE.md)**

### "Jag vill förstå Mapshaper djupare"
1. **[STEG_7_FORENKLING_README.md](STEG_7_FORENKLING_README.md)** - Inställningar förklarade
2. **[MAPSHAPER_SIMPLIFY_GUIDE.md](MAPSHAPER_SIMPLIFY_GUIDE.md)** - Detaljerat

### "Jag får ett felmeddelande"
1. **[STEG_7_FORENKLING_README.md](STEG_7_FORENKLING_README.md)** - Felsökning-sektion
2. **[MAPSHAPER_INSTALLATION_GUIDE.md](MAPSHAPER_INSTALLATION_GUIDE.md)** - Installationsproblem

---

## 📋 Filöversikt

### Introduktion (Nytt? Börja här!)

**[README.md](README.md)**
- Projektöversikt
- Snabbstart
- Projektstuktur
- Systemkrav

### Installation & Setup

**[INSTALL.md](INSTALL.md)**
- Python + venv
- GDAL/OGR
- PostgreSQL (valfritt)
- Systempaket

**[MAPSHAPER_INSTALLATION_GUIDE.md](MAPSHAPER_INSTALLATION_GUIDE.md)**
- nvm installation
- Node.js 18 installation
- Mapshaper global installation
- Felsökning för installations-problem
- Alternativa installationsmetoder

### Pipeline & Arbetsflöde

**[workflow.md](workflow.md)**
- Pipeline-arkitektur (Steg 1-7)
- Data-flows
- Input/Output-katalogstruktur
- Beroenden mellan steg

**[tile_boundary_notes.md](tile_boundary_notes.md)**
- Tile-gränser & överlapp
- Halo-behandling för gränsdäckning
- Gräns-slitning & seamless output

### Steg 7 - Förenkling

**[STEG_7_FORENKLING_README.md](STEG_7_FORENKLING_README.md)** ⭐ HUVUDGUIDE
- Vad förenlingssteget gör
- Varför Mapshaper (vs andra försök)
- Resultat & outputfiler
- Inställningar förklarade (`percentage=`, `planar`, `keep-shapes`)
- Installation & körning
- Felsökning (5 vanliga problem)
- Nästa steg

**[STEG_7_NOTES.md](STEG_7_NOTES.md)** ⚡ SNABB-REFERENS
- Snabbkommando
- Output-summary
- Nyckelparametrar
- Filöversikt

### Mapshaper Detaljinfo

**[MAPSHAPER_SIMPLIFY_GUIDE.md](MAPSHAPER_SIMPLIFY_GUIDE.md)**
- Mapshaper kommandon
- `percentage=` vs `resolution=` vs `interval=`
- Algoritmer (Visvalingam, Douglas-Peucker)
- 30+ kodexempel
- Best practices
- Gränsfall & gotchas

---

## 🎓 Läsväg för Olika Användare

### 👨‍💻 Utvecklare / Underhållare
```
README.md
  ↓
INSTALL.md
  ↓
workflow.md
  ↓
STEG_7_FORENKLING_README.md
  ↓
MAPSHAPER_SIMPLIFY_GUIDE.md
```
**Tid:** ~1 timme

### 👤 GIS-användare
```
README.md
  ↓
STEG_7_NOTES.md
  ↓
(Kör scriptet)
```
**Tid:** ~15 minuter

### 🔧 DevOps / Systemadministratör
```
INSTALL.md
  ↓
MAPSHAPER_INSTALLATION_GUIDE.md
  ↓
workflow.md
```
**Tid:** ~30 minuter

### 🐛 Felsökare
```
STEG_7_FORENKLING_README.md (Felsökning-sektion)
  ↓
MAPSHAPER_INSTALLATION_GUIDE.md (Installationsproblem)
  ↓
workflow.md (Arkitektur)
```
**Tid:** ~20 minuter

---

## 📊 Statistik

| Fil | Rader | Syfte |
|-----|-------|-------|
| README.md | ~70 | Startsida & snabbstart |
| INSTALL.md | ~100 | Installation |
| MAPSHAPER_INSTALLATION_GUIDE.md | ~250 | Mapshaper setup |
| MAPSHAPER_SIMPLIFY_GUIDE.md | ~350 | Detaljerad Mapshaper-guide |
| STEG_7_FORENKLING_README.md | ~380 | Steg 7 komplett guide |
| STEG_7_NOTES.md | ~30 | Snabb-referens |
| workflow.md | ~100 | Pipeline-arkitektur |
| tile_boundary_notes.md | ~80 | Tile & halo |
| **TOTALT** | **~1360** | Omfattande dokumentation |

---

## 🔗 Externa Resurser

- **Mapshaper GitHub:** https://github.com/mbloch/mapshaper/wiki
- **GDAL/OGR Docs:** https://gdal.org/
- **PostGIS Docs:** https://postgis.net/docs/
- **QGIS:** https://qgis.org/en/docs/index.html

---

## ✅ Dokumentations-checklista

- ✅ Installation guide (INSTALL.md)
- ✅ Mapshaper installation (MAPSHAPER_INSTALLATION_GUIDE.md)
- ✅ Steg 7 process guide (STEG_7_FORENKLING_README.md)
- ✅ Steg 7 snabb-referens (STEG_7_NOTES.md)
- ✅ Mapshaper detaljguide (MAPSHAPER_SIMPLIFY_GUIDE.md)
- ✅ Pipeline arkitektur (workflow.md)
- ✅ Tile & halo noteringar (tile_boundary_notes.md)
- ✅ Projektöversikt (README.md på huvudnivå)
- ✅ Dokumentations-index (denna fil)

---

**Status:** Dokumentation komplett & organiserad  
**Uppdaterad:** 13 mars 2026  
**Mottage:** `doc/`
