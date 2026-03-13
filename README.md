# NMD2 2023 Landskapsförenkling Pipeline

**Status:** Steg 7 (Förenkling) ✅ KOMPLETT

---

## 🚀 Snabbstart

```bash
cd /home/hcn/projects/NMD2

# Aktivera miljö
source .venv/bin/activate

# Kör pipeline (Steg 1-6)
python3 src/pipeline_1024_halo.py

# Förenkla resultat (Steg 7)
export NVM_DIR="$HOME/.config/nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
python3 src/simplify_mapshaper.py
```

---

## 📚 Dokumentation

All dokumentation ligger i `doc/`:

- **[README.md](doc/README.md)** - Projekt-översikt
- **[STEG_7_FORENKLING_README.md](doc/STEG_7_FORENKLING_README.md)** - Förenkling process & inställningar
- **[STEG_7_NOTES.md](doc/STEG_7_NOTES.md)** - Snabb-referens för Steg 7
- **[MAPSHAPER_INSTALLATION_GUIDE.md](doc/MAPSHAPER_INSTALLATION_GUIDE.md)** - Mapshaper installation
- **[MAPSHAPER_SIMPLIFY_GUIDE.md](doc/MAPSHAPER_SIMPLIFY_GUIDE.md)** - Detaljerad Mapshaper-dokumentation
- **[workflow.md](doc/workflow.md)** - Pipeline-arbetsflöde
- **[INSTALL.md](doc/INSTALL.md)** - Installation av beroenden
- **[tile_boundary_notes.md](doc/tile_boundary_notes.md)** - Tile-gränser & halo-behandling

---

## 🧪 Experimentell Kod

Experimentella & arkiverade filer ligger i `lab/`:

```bash
ls -la lab/
```

Se [lab/README.md](lab/README.md) för detaljer.

---

## 🔵 Aktivkod (src/)

**Pipeline-filer i `src/`:**
- `pipeline_1024_halo.py` - Huvudpipeline (Steg 1-6)
- `simplify_mapshaper.py` - Förenkling (Steg 7)
- `split_tiles.py` - Tileluppdelning
- `vectorize_*.py` - Vektoriseringsalternativ

**Support i `src/`:**
- `config.py` - Konfiguration
- `logging_setup.py` - Loggning

Se [src/README.md](src/README.md) för detaljer.

---

## 📊 Dataflöde

```
Steg 1-6: Raster → Vektorisering (20,624 polygoner, 28 MB)
         ↓
Steg 7:   Mapshaper förenkling (topologi-bevarad)
         ↓
Output:   4 nivåer (p90%, p75%, p50%, p25%)
```

---

## 🛠️ Systemkrav

- Python 3.8+
- GDAL/OGR
- Node.js 18 + Mapshaper
- PostgreSQL (valfritt för PostGIS)

Installation: Se [doc/INSTALL.md](doc/INSTALL.md)

---

## 📁 Projektstuktur

```
/home/hcn/projects/NMD2/
├── README.md                    ← Du läser detta
├── 🔴 src/ (12 filer - Aktivkod)
│   ├── pipeline_1024_halo.py    (Steg 1-6 - HUVUDPIPELINE)
│   ├── simplify_mapshaper.py    (Steg 7 - FÖRENKLING)
│   ├── config.py                (Konfiguration)
│   ├── logging_setup.py
│   ├── split_tiles.py
│   ├── vectorize_*.py
│   └── README.md                (src/ guide)
│
├── 📚 doc/ (9 .md-filer - Dokumentation)
│   ├── INDEX.md                 ← START HÄR för dokumentation
│   ├── STEG_7_FORENKLING_README.md
│   ├── MAPSHAPER_INSTALLATION_GUIDE.md
│   └── ...
│
├── 🧪 lab/ (39 .py-filer - Experimentell)
│   ├── README.md
│   ├── simplify_with_topojson.py (MISSLYCKAT)
│   ├── simplify_with_arcs.py (MISSLYCKAT)
│   └── ...
│
└── __pycache__/
```

---

## 🎯 Nästa Steg

1. Inspektera förenlingsresultat i QGIS
2. Verifiera att inga slivers finns mellan polygoner
3. Välj lämplig förenlingsgrad för din användning
4. Exportera till slutlig format

---

## 📞 Hjälp

Se dokumentation i `doc/`:
- Installation: [INSTALL.md](doc/INSTALL.md)
- Mapshaper guide: [MAPSHAPER_INSTALLATION_GUIDE.md](doc/MAPSHAPER_INSTALLATION_GUIDE.md)
- Steg 7 detaljer: [STEG_7_FORENKLING_README.md](doc/STEG_7_FORENKLING_README.md)

---

**Version:** 1.0  
**Uppdaterad:** 13 mars 2026  
**Status:** Produktionsklar (Steg 1-7)
