# NMD2 2023 Landskapsförenkling Pipeline

**Status:** Komplett (8 steg) ✅ | Pipeline modernisering: ~70% färdig

---

## 🚀 Snabbstart

### Ny Orchestrator-metod (Rekommenderat)

```bash
cd /home/hcn/projects/NMD2
source .venv/bin/activate

# Kör alla 8 steg via orchestrator
python3 run_all_steps.py

# Eller bara vissa steg
python3 run_all_steps.py --step 1 4    # Bara steg 1-4
python3 run_all_steps.py --step 5 8    # Bara steg 5-8 (generalisering-QGIS)
python3 run_all_steps.py --list        # Visa alla steg
```

### Klassisk metod (Manuella steg)

```bash
cd /home/hcn/projects/NMD2
source .venv/bin/activate

cd src

# Steg 1-4: Förberedelse
python3 steg_1_split_tiles.py
python3 steg_2_extract_protected.py
python3 steg_3_extract_landscape.py
python3 steg_4a_fill_islands.py

# Steg 5-8: Generalisering å QGIS
python3 steg_5_generalize.py
python3 steg_6_vectorize.py
python3 steg_7_simplify.py
python3 steg_8_build_qgis_project.py
```

---

## 📂 Projektstruktur - 8 Steg

**Nya separata steg-filer (i ordning):**
- `steg_1_split_tiles.py` — Tileluppdelning (1024×1024 px)
- `steg_2_extract_protected.py` — Extrahera skyddade klasser
- `steg_3_extract_landscape.py` — Extrahera landskapsbild
- `steg_4a_fill_islands.py` — Fyll små öar
- `steg_4b_filter_lakes.py` — Filtrera små sjöar (valfritt)
- `steg_5_generalize.py` — Generalisering (sieve, modal, semantic)
- `steg_6_vectorize.py` — Vektorisering
- `steg_7_simplify.py` — Mapshaper-förenkling
- `steg_8_build_qgis_project.py` — Bygga QGIS-projekt (NYT steg!)

Se [ARKITEKTUR.md](ARKITEKTUR.md) för detaljgranskning av moderniseringsstatusen.

---

## 📋 Loggfiler

Pipeline-körningar genererar loggfiler i arbetssimulatorn:

- **`log/`** — Debug-loggfiler (`pipeline_debug_<YYYYMMDD_HHMMSS>.log`)
- **`summary/`** — Sammanfattningsloggfiler (`pipeline_summary_<YYYYMMDD_HHMMSS>.log`)

Dessa innehåller detaljerade körningsrapporter från den senaste pipelinekörningen.
Filadresserna skrivs ut i konsolen när pipeline startar.

---

## 📚 Dokumentation

**Arkitektur & Planering:**
- **[ARKITEKTUR.md](ARKITEKTUR.md)** - Pipeline-moderniseringstatus (60% färdig)

**Detaljerad dokumentation i `doc/`:**
- **[README.md](doc/README.md)** - Projekt-översikt
- **[workflow.md](doc/workflow.md)** - Pipeline-arbetsflöde & arkitektur
- **[STEG_7_FORENKLING_README.md](doc/STEG_7_FORENKLING_README.md)** - Förenkling process & inställningar
- **[STEG_7_NOTES.md](doc/STEG_7_NOTES.md)** - Snabb-referens för Steg 7
- **[MAPSHAPER_INSTALLATION_GUIDE.md](doc/MAPSHAPER_INSTALLATION_GUIDE.md)** - Mapshaper installation
- **[MAPSHAPER_SIMPLIFY_GUIDE.md](doc/MAPSHAPER_SIMPLIFY_GUIDE.md)** - Detaljerad Mapshaper-dokumentation
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
