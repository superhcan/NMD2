# 🧪 Lab - Experimentella & Arkiverade Filer

**Mål:** Hålla huvudprojektkatalogen ren genom att förflytja experimentella och arkiverade kod hit.

---

## 📂 Innehål

39 Python-filer från utveckling och experiment:

### Forsöksversioner av Generalisering (11 filer)
```
generalize_*.py          (10 gamla försök på rasterförenkling)
generalize_test*.py      (testversioner)
quick_generalize.py      (snabb-version)
```

### Försök på Vektorförenkling (7 filer)
```
simplify_raster_first.py
simplify_vector.py
simplify_with_arcs.py           (ogr2ogr -simplify försök - MISSLYCKAT)
simplify_with_topojson.py       (Python topojson försök - TOO SLOW)
validate_topology.py             (topologi-validator)
smooth_single.py
dissolve_*.py
```

### Vägar & Byggnader Separering (4 filer)
```
separate_roads_*.py v1-v3
remove_roads_buildings_raster.py
replace_roads_buildings.py
```

### Dataöversättning (7 filer)
```
extract_*.py             (extrahering av klassgrupper)
rasterize_tiles.py
respixel_then_vectorize.py
vectorize_generalized.py  (äldre vektorisering)
modal_k15_morphological.py
modal_k15_respixel_test.py
```

### Äldre Pipeline-versioner (3 filer)
```
pipeline.py              (mycket tidig version)
pipeline_1024.py         (utan halo-behandling)
method_*.py              (A/B metoduppsättning)
```

### Övriga Experimentella (7 filer)
```
fill_islands.py
grass_simplify.py
extract_landscape_only.py
extract_protected_classes_old_vectorize.py
extract_protected_classes.py
extract_protected_classes.py
generalize_test_v2.py
```

---

## 🏃 AKTIVA PIPELINEFILER (på huvudnivå)

```
✅ pipeline_1024_halo.py              ← Huvudpipeline (Steg 1-6)
✅ simplify_mapshaper.py               ← Steg 7 (Förenkling med Mapshaper)
✅ simplify_mapshaper_ARKIV_...py      ← Backup av Steg 7

✅ split_tiles.py                      ← Steg 1 (Tileluppdelning)
✅ vectorize_modal_k15.py              ← Steg 6 (Modal vektorisering)
✅ vectorize_pipeline_1024_halo.py     ← Steg 6 (Pipeline vektorisering)
✅ vectorize_tiles.py                  ← Steg 6 (Allman vektorisering)

✅ config.py                           ← Konfiguration
✅ logging_setup.py                    ← Loggning
```

---

## 🔍 För Att Hitta Något

```bash
# Sök i lab-mappen
grep -r "ditt_sökord" /home/hcn/projects/NMD2/lab/

# Lista alla filer
ls -lh /home/hcn/projects/NMD2/lab/

# Visa bara namn
ls /home/hcn/projects/NMD2/lab/*.py
```

---

## 📚 Varför Är De Här?

### ❌ Misslyckat (Ska ALDRIG Användas Igen)
- `simplify_with_topojson.py` - Timeout (alltför långsam)
- `simplify_with_arcs.py` - Slivers i output
- `simplify_with_topojson.py` (PostGIS version) - Slivers i output
- Alla `generalize_test_*.py` - Testversioner som inte fungerar

### ⚠️ Arkiverat (Kan Användas För Referens)
- `separate_roads_*.py` - Tidigare försök på vägseparering
- `method_*.py` - A/B-testningametoder
- `extract_*.py` - Gamla extraktionsmetoder

### 🧪 Experimentellt (Kan Användas För Forskning)
- `modal_k15_morphological.py` - Morphologisk testtransformering
- `grass_simplify.py` - GRASS GIS simplification test
- `fill_islands.py` - Öppfyllningsalgoritm

---

## 🚀 Om Du Behöver En Gammal Fil

```bash
# Kopiera från lab/ till huvudkatalog
cp /home/hcn/projects/NMD2/lab/FILNAMN.py /home/hcn/projects/NMD2/

# Testa sedan
python3 FILNAMN.py
```

---

## 📌 Regler

- **Lägg ALDRIGny experimentkod på huvudnivå** - använd lab/
- **Testa innan du lägger på huvudnivå** - lab/ är för "work in progress"
- **Kommentera varför något är här** - vi måste kunna förstå sen

---

**Sparad:** 13 mars 2026  
**Arkiv av:** Exprimentering under Steg 1-7
