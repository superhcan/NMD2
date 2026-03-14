# 🏗️ PIPELINE-ARKITEKTUR - NMD2 Modernisering

## Status: Hybrid-arkitektur (~70% färdig)

The NMD2 pipeline är under migration från en monolitisk `pipeline_1024_halo.py` till ett modulärt system med separata steg. **Framsteg: ~70% färdig.**

✅ **Senaste uppdatering**: QGIS-projektet är nu Steg 8 (separat från generalisering)

---

## ✅ FÄRDIGSTÄLLT: Separata Steg (1-4)

Följande steg är nu **helt separerade** och kan köras oberoende:

| Steg | Fil | Status | i/o |
|------|-----|--------|-----|
| 1 | `split_tiles.py` | ✅ Separat | tiles/ → tiles/ |
| 2 | `steg_2_extract_protected.py` | ✅ Separat | tiles/ → protected/ |
| 3 | `steg_3_extract_landscape.py` | ✅ Separat | tiles/ → landscape/ |
| 4a | `steg_4a_fill_islands.py` | ✅ Separat | landscape/ → filled/ |
| 4b | `steg_4b_filter_lakes.py` | ✅ Separat (valfritt) | filled/ → filled_filtered/ |

**Orkestrering**: Alla steg 1-4 kan köras via [`run_all_steps.py`](../run_all_steps.py) orchestrator.

---

## 🔄 PARTIELL: Steg 5 (Ännu ihop i steg_5_generalize.py)

Följande steg är för närvarande **kombinerad** i `steg_5_generalize.py`:

| Steg | Fil | Status | Beskrivning |
|------|-----|--------|-------------|
| 5 | `steg_5_generalize.py` | 🔄 Kombinerad (5a-5d) | Generalisering med sieve, modal, semantic + halo-teknik |
| 6 | `steg_6_vectorize.py` | ✅ Separat | Vektorisering av generaliserade raster |
| 7 | `steg_7_simplify.py` | ✅ Separat | Mapshaper-förenkling |
| 8 | `steg_8_build_qgis_project.py` | ✅ Separat (NY!) | QGIS-projektbyggande |

**Varför Steg 8 ny?** QGIS-projektet byggdes tidigare under Steg 5. Nu är det separerat för att:
- Steg 5 kan köras utan QGIS-beroende
- QGIS-projektet kan omkonstrueras eller uppdateras senare
- Modulär arkitektur

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
python3 run_all_steps.py  # Alla 8 steg
```

**Eller bara vissa steg:**
```bash
python3 run_all_steps.py --step 1 4    # Steg 1-4
python3 run_all_steps.py --step 5 8    # Steg 5-8
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
