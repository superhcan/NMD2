# src/ — Pipeline-kod

Se projektets dokumentation i rotkatalogen och `doc/`:

- [README.md](../README.md) — Projektöversikt och snabbstart
- [doc/INSTALL.md](../doc/INSTALL.md) — Installationsanvisning
- [doc/METOD.md](../doc/METOD.md) — Metodbeskrivning
- [doc/KÖRNING.md](../doc/KÖRNING.md) — Körning och konfiguration

---

Pipelinen körs via orchestratorn i rotkatalogen:

```bash
cd /home/hcn/projects/NMD2
source .venv/bin/activate
python3 run_all_steps.py
```

All konfiguration sker i `src/config.py`.

---

## 📂 Innehål

### 🎯 Master Orchestrator
- **`../run_all_steps.py`** - Orchestrator som kör alla steg i rätt ordning
  - Användning: `python3 run_all_steps.py` (alla 9 steg)
  - Eller: `python3 run_all_steps.py --step 6 9` (endast steg 6-9)
  - Se `--help` för alla alternativ

### 🚀 Pipeline-Steg (i ordning)

**Steg 1: Tileluppdelning**
- **`steg_1_reclassify.py`** - Omklassificerar tiles med CLASS_REMAP (LUT)

**Steg 2: Extrahera skyddade klasser**
- **`steg_2_extract_protected.py`** - Extraherar vägar, byggnader, vatten (klass 51-54, 61-62) för senare sammansättning

**Steg 3: Extrahera landskapsbild**
- **`steg_3_extract_landscape.py`** - Ersätter vägar/byggnader med omkringliggande värden för generalisering

**Steg 4: Ta bort små sjöar**
- **`steg_4_filter_lakes.py`** - Tar bort små sjöar < 1 ha från landskapsbild och fyller med omgivande värden (< 100 pixlar)

**Steg 5: Fylla små öar** (valfritt)
- **`steg_5_filter_islands.py`** - Fyller landöar < 1 ha helt omringade av vatten med dominant vattenklass

**Steg 6: Generalisering**
- **`steg_6_generalize.py`** - Generaliserar med 4 metoder (CONN4, CONN8, modal, semantic) och halo-teknik

**Steg 7: Vektorisering**
- **`steg_7_vectorize.py`** - Konverterar generaliserade raster till GeoPackage-vektorer (CONN4 MMU008, CONN8 MMU008, MODAL K15)

**Steg 8: Mapshaper-förenkling**
- **`steg_8_simplify.py`** - Förenklar vektorer med topologi-bevarad Mapshaper (5 nivåer: p90/p75/p50/p25/p15)

**Steg 99: Bygga QGIS-projekt**
- **`steg_99_build_qgis_project.py`** - Bygger QGIS-projekt från alla steg, organiserar lager i sub_groups per variant

### 🧩 Support & Verktyg
- **`config.py`** - Centraliserad konfiguration (vägar, parametrar, etc.)
- **`logging_setup.py`** - Loggningskonfiguration
- **`qgis_project_builder.py`** - QGIS-projektgenerator
- **`split_tiles.py`** - Äldre tileluppdelning (ersatt av steg 1 i orchestrator)

---

## 🚀 Hur Man Kör

### Med Orchestrator (Rekommenderat)
```bash
cd /home/hcn/projects/NMD2
source .venv/bin/activate

# Kör alla steg
python3 run_all_steps.py

# Eller bara vissa steg
python3 run_all_steps.py --step 6 99    # Endast steg 6-99 (generalisering → QGIS)
python3 run_all_steps.py --list         # Visa alla steg
```

### Individuella Steg (Manuellt)
```bash
cd /home/hcn/projects/NMD2/src

# Steg 1: Tileluppdelning
python3 steg_1_reclassify.py

# Steg 2: Extrahera skyddade klasser
python3 steg_2_extract.py

# Steg 3: Upplös klasser i omgivande mark
python3 steg_3_dissolve.py

# Steg 4: Ta bort små sjöar
python3 steg_4_filter_lakes.py

# Steg 5: Filtrera små öar
python3 steg_5_filter_islands.py

# Steg 6: Generalisering
python3 steg_6_generalize.py

# Steg 7: Vektorisering
python3 steg_7_vectorize.py

# Steg 8: Mapshaper-förenkling
export NVM_DIR="$HOME/.config/nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
python3 steg_8_simplify.py

# Steg 99: Bygga QGIS-projekt (kräver QGIS installerat)
python3 steg_99_build_qgis_project.py
```

---

## ⚙️ Konfiguration

Redigera `src/config.py` för att ändra:
- `OUT_BASE` - Utmappningskatalog (standardvärde: `pipeline_1024_halo_v6`)
- `PARENT_TILES` - Vilka förälder-tiles som ska processeras
- `MMU_ISLAND`, `MMU_STEPS` - Minsta arealstorlekar
- `KERNEL_SIZES` - Modal-filterkärnstorlekar

---

## 📚 Dokumentation

Se `../doc/` för detaljerad dokumentation:
- `doc/README.md` - Projektöversikt
- `doc/workflow.md` - Pipeline arkitektur och arbetsgång
- `doc/STEG_7_FORENKLING_README.md` - Mapshaper-förenkling detaljer
