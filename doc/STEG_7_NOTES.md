# STEG 7 - Snabb Referens

## ⚡ Köra Scriptet (snabbkommando)

```bash
export NVM_DIR="$HOME/.config/nvm" && [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh" && \
cd /home/hcn/projects/NMD2 && python3 simplify_mapshaper.py
```

## 📊 Output

```
modal_k15_simplified_p90.gpkg   → 28 MB (minimal förenkling)
modal_k15_simplified_p75.gpkg   → 28 MB (lätt förenkling)
modal_k15_simplified_p50.gpkg   → 18 MB (måttlig förenkling)
modal_k15_simplified_p25.gpkg   → 12 MB (aggressiv förenkling)
```

## 🔑 Nyckelparametrar

```bash
-simplify percentage=X%    # Behåll X% av vertices (90%, 75%, 50%, 25%)
planar                      # Platt 2D-behandling för EPSG:3006
keep-shapes                 # Förhindra att små polygoner försvinner
```

## 📍 Filer

- **Aktiv kod:** `simplify_mapshaper.py`
- **Arkiv:** `simplify_mapshaper_ARKIV_2026-03-13.py`
- **Detaljdokumentation:** `STEG_7_FORENKLING_README.md`
- **Mapshaper-guide:** `MAPSHAPER_SIMPLIFY_GUIDE.md`

## 🎯 Nästa Steg

Inspektera filerna i QGIS och verifiera att det inte finns slivers mellan polygoner.

---

**Sparad:** 13 mars 2026 kl. 17:58
