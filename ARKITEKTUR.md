# 🏗️ PIPELINE-ARKITEKTUR - NMD2 Modernisering

## Status: Fullt modulär arkitektur (~95% färdig)

The NMD2 pipeline är nu ett modulärt system med **9 separata steg** som alla kan köras oberoende. **Framsteg: ~95% färdig.**

✅ **Senaste uppdatering**: Steg 5 (fylla små öar) är nu tillagt, alla steg renumrerade för linjär körning (1-9)

---

## ✅ FÄRDIGSTÄLLT: Separata Steg (1-9)

Följande steg är nu **helt separerade** och kan köras oberoende:

| Steg | Fil | Status | i/o |
|------|-----|--------|-----|
| 1 | `steg_1_split_tiles.py` | ✅ Separat | original TIF → 1024×1024 tiles |
| 2 | `steg_2_extract_protected.py` | ✅ Separat | tiles/ → protected/ (vägar, byggnader, vatten) |
| 3 | `steg_3_extract_landscape.py` | ✅ Separat | tiles/ → landscape/ (ersätter vägar/byggnader) |
| 4 | `steg_4_fill_islands.py` | ✅ Separat | landscape/ → filled/ (tar bort små sjöar < 1 ha) |
| 5 | `steg_4b_filter_lakes.py` | ✅ Separat (valfritt) | filled/ → islands_filled/ (fyller öar omringade av vatten) |
| 6 | `steg_5_generalize.py` | ✅ Separat | landscape/ → generalized/ (sieve, modal, semantic + halo) |
| 7 | `steg_6_vectorize.py` | ✅ Separat | generalized/ → vectorized/ (raster → GeoPackage) |
| 8 | `steg_7_simplify.py` | ✅ Separat | vectorized/ → simplified/ (Mapshaper-förenkling) |
| 9 | `steg_8_build_qgis_project.py` | ✅ Separat | simplified/ → Pipeline.qgs (QGIS-projekt) |

**Orkestrering**: Alla steg 1-9 kan köras via [`run_all_steps.py`](../run_all_steps.py) orchestrator.

---

## 🎯 Framtida Plan: Fullständig Separation

**Nästa fas** (ej implementerad ännu):
1. Extrahera `steg_5_generalize.py` → separera Steg 5a-5d i egna filer (valfritt)
2. Separera Steg 5a-5d i egen fil (`steg_5a_sieve_conn4.py`, etc.) om behövs för bättre modularitet

Status: ✅ **QGIS-projektet är nu separerat!** (Steg 8)

---

## 🚀 MER ANVÄNDNING

### Som det är nu (Hybrid-läge → 60% separerad)

**Kör alla steg separat via orchestrator:**
```bash
python3 run_all_steps.py  # Alla 9 steg
```

**Eller bara vissa steg:**
```bash
python3 run_all_steps.py --step 1 4    # Steg 1-4 (endast sjölösning)
python3 run_all_steps.py --step 6 9    # Steg 6-9 (från generalisering)
```

---

## 📊 Komponenter

### Konfiguration
- **`config.py`** — centraliserad inställning (vägar, MMU-parametrar, etc.)

### Loggning & Support
- **`logging_setup.py`** — dubbel logg-setup (debug + summary)
- **`qgis_project_builder.py`** — QGIS-projektgenerator (ElementTree-baserad)

### Arkiverade / Äldre Versioner
- `pipeline_1024.py` — ursprunglig version (utan halo)
- `split_tiles.py` — ännu i src/, ersatt av steg_1 i orchestrator

---

## 🔗 Se också

- [Pipeline README](../src/README.md) — Steg-beskrivningar
- [Workflow dokumentation](../doc/workflow.md) — Detaljerad arbetsgång
- [Steg 7 – Mapshaper](../doc/STEG_7_FORENKLING_README.md) — Förenkling-detaljer

---

**Skapad**: 13 mars 2026  
**Författare**: NMD2 Pipeline Team  
**Nästa uppdatering**: Efter Steg 5 separation
