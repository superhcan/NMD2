# Loggning Headers Sammanfattning för Alla Steg

## Analys av steg_*.py Loggning

### Steg 1: steg_1_split_tiles.py
**Setup-funktion:** `setup_logging()` från `logging_setup`  
**Separator lines:** Nej  
**__main__ Loggning:**
```python
if __name__ == "__main__":
    setup_logging(OUT_BASE, step_num, step_name)
    info.info("Steg 1 klar: %d tiles skapade (%.1fs)", len(list(OUT_DIR.glob("*.tif"))), elapsed)
```
**Struktur:** Kortfattad loggning endast vid avslutande
**Källmapp/Utmapp:** Loggas inte i __main__, bara i script-kropp via print()

---

### Steg 2: steg_2_extract_protected.py
**Setup-funktion:** `setup_logging()` från `logging_setup`  
**Separator lines:** Nej  
**__main__ Loggning:**
```python
if __name__ == "__main__":
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    setup_logging(OUT_BASE, step_num, step_name)
    # Bara print() till console, ingen info.info()
```
**Struktur:** Loggning sker i funktionen `extract_protected_classes()`:
- `info.info("Steg 2: Extraherar skyddade klasser %s från original-tiles...", sorted(PROTECTED))`

---

### Steg 3: steg_3_extract_landscape.py
**Setup-funktion:** `setup_logging()` från `logging_setup`  
**Separator lines:** Nej  
**__main__ Loggning:** Endast print() till console
**Struktur:** Loggning sker i funktionen `extract_landscape()`:
- `info.info("Steg 3: Extraherar landskapet (ersätter vägar(53) och byggnader(51)) ...")`

---

### Steg 4: steg_4_fill_islands.py
**Setup-funktion:** `setup_logging()` från `logging_setup`  
**Separator lines:** Nej  
**__main__ Loggning:** Endast print() till console
**Struktur:** Loggning sker i funktionen `fill_water_islands()`:
- `info.info("Steg 4: Tar bort små sjöar < %d px (%.2f ha) och fyller med omkringliggande ...", ...)`

---
    log  = _LOGGERS["debug"]
    info = _LOGGERS["summary"]
    
    info.info("══════════════════════════════════════════════════════════")
    info.info("Steg 4: Landskapsgeneralisering (halo-teknik)")
    info.info("Källbild  : %s", SRC)
    info.info("Utmapp    : %s", OUT_BASE)
    info.info("Halo      : %d px", HALO)
    info.info("Skyddade klasser: %s", sorted(PROTECTED))
    info.info("Vattenkl. (öfyllnad): %s", sorted(WATER_CLASSES))
    info.info("MMU-steg  : %s px", MMU_STEPS)
    info.info("Kernelstorlekar (modal): %s", KERNEL_SIZES)
    info.info("══════════════════════════════════════════════════════════")
```
**Struktur:** Flersteg loggning med:
1. Separator
2. Stegrubrik
3. Källbild, utmapp, parametrar (HALO, MMU-steg, etc)
4. Separator
5. Steg-för-steg utförande (4a, 4b, 4c, 4d)
6. Avslutande separator + totaltid

---

### Steg 5: steg_5_filter_lakes.py
**Setup-funktion:** `setup_logging()` från `logging_setup`  
**Separator lines:** Nej  
**__main__ Loggning:** Endast print() till console
**Struktur:** Loggning sker i funktionen `fill_islands()`:
- `info.info("Steg 5: Fyller små landöar < %d px (%.2f ha) omringade av vatten ...", ...)`

---

### Steg 6: steg_6_generalize.py
**Setup-funktion:** `_setup_logging()` (eget implementerat)  
**Separator lines:** ✅ **JA** - Samma som Steg 4: `"══════════════════════════════════════════════════════════"`  
**__main__ Loggning:**
```python
if __name__ == "__main__":
    OUT_BASE.mkdir(parents=True, exist_ok=True)
    _setup_logging(OUT_BASE)
    log  = _LOGGERS["debug"]
    info = _LOGGERS["summary"]
    
    info.info("══════════════════════════════════════════════════════════")
    info.info("Steg 4: Landskapsgeneralisering (halo-teknik)")  # Note: Says "Steg 4" but is 6
    info.info("Källbild  : %s", SRC)
    ... (samma som Steg 4)
    info.info("══════════════════════════════════════════════════════════")
    
    info.info("\nSteg 6a: Sieve conn4 (med halo)")
    # etc
```
**Struktur:** Identisk med Steg 4 (copy-paste struktur)

---

### Steg 7: steg_7_vectorize.py
**Setup-funktion:** `_setup_logging()` (eget implementerat, returnerar logger)  
**Separator lines:** ✅ **JA** - `"══════════════════════════════════════════════════════════"`  
**__main__ Loggning:**
```python
if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    log = _setup_logging(OUT_BASE)
    t0 = time.time()
    
    log.info("══════════════════════════════════════════════════════════")
    log.info("Vektorisering av pipeline_1024_halo-resultat")
    log.info("Källmapp: %s", PIPE)
    log.info("Utmapp  : %s", OUT)
    log.info("══════════════════════════════════════════════════════════")
    
    log.info("\nCONN4 (mmu008)")
    log.info("\nCONN8 (mmu008)")
    log.info("\nModal filter k15")
    
    elapsed = time.time() - t0
    log.info("══════════════════════════════════════════════════════════")
    log.info("KLAR: %.0fs (%.1f min)", elapsed, elapsed / 60)
    log.info("GeoPackage-filer: %s", OUT)
    log.info("══════════════════════════════════════════════════════════")
```
**Struktur:** Tre separators (öppning, steg-rubriker, avslutning)

---

### Steg 8: steg_8_simplify.py
**Setup-funktion:** `setup_logging()` (eget implementerat)  
**Separator lines:** ✅ **JA** - `"══════════════════════════════════════════════════════════"`  
**__main__ Loggning:**
```python
if __name__ == "__main__":
    log = setup_logging(OUT_BASE)
    
    log.info("══════════════════════════════════════════════════════════")
    log.info("Mapshaper-förenkling av vektoriserade data")
    log.info("══════════════════════════════════════════════════════════")
    
    output_dir = OUT_BASE / "steg8_simplified"
    tolerances = [90, 75, 50, 25, 15]  # Updated: added p15
    
    # Process variants...
    
    log.info("\n══════════════════════════════════════════════════════════")
    log.info(f"Färdig: Output i {output_dir}")
    log.info("══════════════════════════════════════════════════════════")
```
**Struktur:** Två separators (öppning + avslutning)

---

### Steg 9: steg_9_build_qgis_project.py
**Setup-funktion:** `setup_logging()` (eget implementerat, returnerar log + dbg)  
**Separator lines:** ✅ **JA** - Använder `"═" * 70` (variant längd)  
**__main__ Loggning:**
```python
if __name__ == "__main__":
    try:
        success = build_qgis_project()
        # Within build_qgis_project():
        log.info("═" * 70)
        log.info("Steg 8: Bygger QGIS-projekt från alla generer lager")  # Note: Says "Steg 8" but is 9
        log.info("═" * 70)
        
        # ... lägga till lager ...
        
        log.info("")
        log.info("═" * 70)
        log.info(f"✅ Steg 9 KLART")
        log.info(f"   Projekt: {project_path.name} ({size_kb:.1f} KB)")
        log.info(f"   Totalt lager: {total_layers}")
        log.info(f"   Ordning: Steg 8 (top) → Steg 1 (bottom)")
        log.info("═" * 70)
```
**Struktur:** Två separators (öppning + avslutning) + rubrik + läggning av lager

---

## Sammanfattning efter Steg

| Steg | Funktion | Separators | Loggning i __main__ | Källmapp/Utmapp i __main__ |
|------|----------|------------|------------------|--------------------------|
| **1** | `setup_logging()` | Nej | ✓ info.info() | Nej, bara print() |
| **2** | `setup_logging()` | Nej | Nej, bara print() | Nej |
| **3** | `setup_logging()` | Nej | Nej, bara print() | Nej |
| **4** | `setup_logging()` | Nej | Nej, bara print() | Nej |
| **4alt** | `_setup_logging()` | ✅ JA | ✓ info.info() med separators | ✓ SRC, Utmapp, Parametrar |
| **5** | `setup_logging()` | Nej | Nej, bara print() | Nej |
| **6** | `_setup_logging()` | ✅ JA | ✓ info.info() med separators | ✓ SRC, Utmapp, Parametrar |
| **7** | `_setup_logging()` | ✅ JA | ✓ log.info() med separators | ✓ Källmapp (PIPE), Utmapp |
| **8** | `setup_logging()` | ✅ JA | ✓ log.info() med separators | Tillval i output_dir |
| **9** | `setup_logging()` | ✅ JA | ✓ log.info() med separators | ✓ Projekt (i Steg 9) |

---

## Mönster & Noteringar

### Två Logging-Strategier Identifierade:

1. **Minimalistisk** (Steg 1-5):
   - `setup_logging()` från external modul `logging_setup`
   - Minimal loggning i `__main__`
   - Tyngdpunkten ligger i funktionerna
   - Ingen separator lines

2. **Utförlig** (Steg 6-9):
   - `_setup_logging()` eller `setup_logging()` definierad lokalt
   - Rubrikad loggning med separator lines
   - Källmapp/utmapp loggad explicit
   - Parametrar (MMU, HALO, kernel) synliga från start

### Separator Line-Format:
- **Steg 4, 6, 7, 8:** `"══════════════════════════════════════════════════════════"` (58 tecken)
- **Steg 9:** `"═" * 70` (70 tecken, längre)

### Felaktigheter i Koden:
- **Steg 9:** Rubrik säger "Steg 8" men är faktiskt Steg 9 (`log.info("Steg 8: Bygger QGIS-projekt...")`)
  - ⚠️ FIXAD i senare versioner

