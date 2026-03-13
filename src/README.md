# 🔴 src/ - Pipeline-kod

All aktiv pipeline-kod lägger här.

---

## 📂 Innehål

### 🚀 Huvudpipeline
- **`pipeline_1024_halo.py`** - Steg 1-6 (Raster → Vektorisering)

### 🔧 Förenkling (Steg 7)
- **`simplify_mapshaper.py`** - Mapshaper-baserad topologi-bevarad förenkling
- **`simplify_mapshaper_ARKIV_2026-03-13.py`** - Backup av Steg 7

### 📊 Vektorisering (Steg 6)
- **`vectorize_modal_k15.py`** - Modal K15 vektorisering
- **`vectorize_pipeline_1024_halo.py`** - Pipeline vektorisering (med halo)
- **`vectorize_tiles.py`** - Generell vektorisering
- **`vectorize_generalized.py`** - Äldre vektorisering

### 🧩 Support
- **`config.py`** - Konfigurationsfil (vägar, parametrar, etc.)
- **`logging_setup.py`** - Loggningskonfiguration

### 🌳 Tileluppdelning (Steg 1)
- **`split_tiles.py`** - Tileluppdelning

### 🛣️ Vägar & Byggnader (valfritt)
- **`separate_roads_final.sh`** - Vägseparering shell-script
- **`separate_roads_grass.sh`** - GRASS GIS vägseparering

---

## 🚀 Hur Man Kör

### Steg 1-6: Huvudpipeline
```bash
source /path/to/venv/bin/activate
python3 src/pipeline_1024_halo.py
```

### Steg 7: Förenkling
```bash
export NVM_DIR="$HOME/.config/nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

python3 src/simplify_mapshaper.py
```

### Bara Tileluppdelning
```bash
python3 src/split_tiles.py
```

### Bara Vektorisering
```bash
python3 src/vectorize_pipeline_1024_halo.py
# eller annat vektoriserings-script
```

---

## ⚙️ Konfiguration

Redigera `src/config.py` för att ändra:
- Input/output-katalogtruktur
- Parametrar (toleranser, upflösningar, etc.)
- Klassgrupper
- Loggning

---

## 📚 Dokumentation

Se `doc/` för detaljerad dokumentation:
- `doc/README.md` - Projektöversikt
- `doc/workflow.md` - Pipeline arkitektur
- `doc/STEG_7_FORENKLING_README.md` - Steg 7 detaljer

---

## 🔗 Relaterade Mappar

- **`doc/`** - All dokumentation
- **`lab/`** - Experimentell & arkiverad kod
- **`__pycache__/`** - Python cache (ignorera)

---

**Struktur skapad:** 13 mars 2026
